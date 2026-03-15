"""审核服务"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime, timedelta
from typing import Tuple, List, Dict, Any, Optional
import json
import uuid
import logging

from app.models.review import ReviewQueue
from app.models.policy import Policy, PolicySocialInsurance
from app.models.version import PolicyVersion
from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


class ReviewService:
    """审核服务"""

    # 审核状态流转
    STATUS_TRANSITIONS = {
        "pending": ["claimed"],
        "claimed": ["approved", "rejected", "needs_clarification", "released"],
        "needs_clarification": ["pending", "rejected"],
        "approved": [],
        "rejected": [],
    }

    # SLA 配置（小时）
    SLA_HOURS = {
        "urgent": 1,
        "high": 4,
        "normal": 24,
        "low": 72
    }

    def __init__(self, session: AsyncSession):
        self.session = session

    async def submit_for_review(
        self,
        policy_type: str,
        structured_data: dict,
        raw_content: dict,
        submitted_by: str,
        idempotency_key: Optional[str] = None,
        priority: str = "normal"
    ) -> Tuple[ReviewQueue, List[str], Dict[str, Any]]:
        """
        提交政策到审核队列

        Returns:
            (review, warnings, ai_analysis)
        """
        warnings = []
        ai_analysis = {}

        # 幂等性检查
        if idempotency_key:
            existing = await self.session.execute(
                select(ReviewQueue).where(
                    ReviewQueue.idempotency_key == idempotency_key
                )
            )
            existing_review = existing.scalar_one_or_none()
            if existing_review:
                return existing_review, [], {"is_duplicate": True}

        # 生成 review_id
        review_id = str(uuid.uuid4())

        # AI 分析
        ai_analysis = await self._run_ai_analysis(structured_data)
        warnings = ai_analysis.get("warnings", [])

        # 计算 SLA
        sla_hours = self.SLA_HOURS.get(priority, 24)
        sla_deadline = (datetime.utcnow() + timedelta(hours=sla_hours)).isoformat()

        # 创建审核记录
        review = ReviewQueue(
            review_id=review_id,
            policy_id=str(uuid.uuid4()),  # 预生成 policy_id
            idempotency_key=idempotency_key,
            submitted_data=json.dumps(structured_data, ensure_ascii=False),
            raw_evidence=json.dumps(raw_content, ensure_ascii=False),
            ai_validation=json.dumps(ai_analysis.get("validation", {}), ensure_ascii=False),
            risk_level=ai_analysis.get("risk_level", "low"),
            risk_tags=json.dumps(ai_analysis.get("risk_tags", []), ensure_ascii=False),
            status="pending",
            priority=priority,
            submitted_by=submitted_by,
            sla_deadline=sla_deadline
        )

        self.session.add(review)
        await self.session.commit()
        await self.session.refresh(review)

        logger.info(f"Review submitted: {review_id} by {submitted_by}")
        return review, warnings, ai_analysis

    async def _run_ai_analysis(self, data: dict) -> Dict[str, Any]:
        """AI 分析"""
        risk_tags = []
        warnings = []
        validation = {"passed": True, "errors": [], "warnings": []}

        # 1. 必填字段检查
        required_fields = ["title", "region_code", "effective_start", "si_upper_limit", "si_lower_limit"]
        for field in required_fields:
            if not data.get(field):
                validation["errors"].append(f"缺少必填字段: {field}")
                validation["passed"] = False

        # 2. 数值逻辑检查
        si_upper = data.get("si_upper_limit")
        si_lower = data.get("si_lower_limit")
        if si_upper and si_lower and si_upper <= si_lower:
            validation["errors"].append("社保上限必须大于下限")
            validation["passed"] = False

        hf_upper = data.get("hf_upper_limit")
        hf_lower = data.get("hf_lower_limit")
        if hf_upper and hf_lower and hf_upper <= hf_lower:
            validation["errors"].append("公积金上限必须大于下限")
            validation["passed"] = False

        # 3. 日期逻辑检查
        published_at = data.get("published_at")
        effective_start = data.get("effective_start")
        is_retroactive = data.get("is_retroactive", False)

        if published_at and effective_start:
            try:
                pub_date = datetime.fromisoformat(published_at)
                eff_date = datetime.fromisoformat(effective_start)

                if eff_date < pub_date:
                    retro_months = (pub_date.year - eff_date.year) * 12 + (pub_date.month - eff_date.month)
                    if not is_retroactive:
                        warnings.append(f"生效日期({effective_start})早于发布日期({published_at})，涉及{retro_months}个月追溯，建议标记为追溯")
                    risk_tags.append("追溯生效")
                    validation["retroactive_months"] = retro_months
            except (ValueError, TypeError):
                pass

        # 4. 涨幅分析（与同地区上一期政策对比）
        change_analysis = await self._analyze_change_rate(data)
        if change_analysis.get("has_change"):
            validation["change_analysis"] = change_analysis
            if change_analysis.get("upper_change_rate", 0) > 20:
                risk_tags.append("涨幅异常")
                warnings.append(f"社保上限涨幅{change_analysis['upper_change_rate']:.1f}%超过20%，请核实")
            elif change_analysis.get("upper_change_rate", 0) > 10:
                risk_tags.append("涨幅较高")

            if change_analysis.get("lower_change_rate", 0) > 20:
                risk_tags.append("下限涨幅异常")

        # 5. 重复检测
        duplicate_check = await self._check_duplicate(data)
        if duplicate_check.get("is_duplicate"):
            risk_tags.append("疑似重复")
            warnings.append(f"发现相似政策: {duplicate_check.get('existing_policy_id')}")
            validation["duplicate_check"] = duplicate_check

        # 6. 基数合理性检查
        reasonability_check = self._check_base_reasonability(data)
        if not reasonability_check.get("passed"):
            validation["warnings"].extend(reasonability_check.get("warnings", []))
            if reasonability_check.get("severe"):
                risk_tags.append("基数异常")

        # 7. 风险等级
        risk_level = "low"
        if not validation["passed"]:
            risk_level = "high"
        elif len(risk_tags) >= 2:
            risk_level = "high"
        elif len(risk_tags) >= 1:
            risk_level = "medium"

        return {
            "validation": validation,
            "warnings": warnings,
            "risk_level": risk_level,
            "risk_tags": risk_tags,
            "duplicate_check": duplicate_check,
            "change_analysis": change_analysis
        }

    async def _analyze_change_rate(self, data: dict) -> Dict[str, Any]:
        """分析与同地区上一期政策的变更"""
        region_code = data.get("region_code")
        effective_start = data.get("effective_start")

        if not region_code or not effective_start:
            return {"has_change": False}

        # 查找同地区上一期生效的政策
        result = await self.session.execute(
            select(Policy, PolicySocialInsurance)
            .join(PolicySocialInsurance, Policy.policy_id == PolicySocialInsurance.policy_id)
            .where(
                Policy.region_code == region_code,
                Policy.effective_start < effective_start,
                Policy.status == "active"
            )
            .order_by(Policy.effective_start.desc())
            .limit(1)
        )
        row = result.first()

        if not row:
            return {"has_change": False}

        prev_policy, prev_si = row
        new_upper = data.get("si_upper_limit")
        new_lower = data.get("si_lower_limit")

        result_data = {
            "has_change": True,
            "previous_policy_id": prev_policy.policy_id,
            "previous_effective_start": prev_policy.effective_start,
            "previous_upper": prev_si.si_upper_limit,
            "previous_lower": prev_si.si_lower_limit,
        }

        # 计算涨幅
        if prev_si.si_upper_limit and new_upper:
            result_data["upper_change_rate"] = round(
                ((new_upper - prev_si.si_upper_limit) / prev_si.si_upper_limit) * 100, 2
            )
            result_data["upper_change"] = new_upper - prev_si.si_upper_limit

        if prev_si.si_lower_limit and new_lower:
            result_data["lower_change_rate"] = round(
                ((new_lower - prev_si.si_lower_limit) / prev_si.si_lower_limit) * 100, 2
            )
            result_data["lower_change"] = new_lower - prev_si.si_lower_limit

        return result_data

    def _check_base_reasonability(self, data: dict) -> Dict[str, Any]:
        """检查基数合理性"""
        warnings = []
        severe = False

        si_lower = data.get("si_lower_limit")
        si_upper = data.get("si_upper_limit")

        # 下限不应低于最低工资标准（假设约2000元）
        if si_lower and si_lower < 2000:
            warnings.append(f"社保下限({si_lower})低于最低工资标准，请核实")
            severe = True

        # 上限不应超过社平工资3倍（假设约30000元）
        if si_upper and si_upper > 35000:
            warnings.append(f"社保上限({si_upper})超过社平工资3倍，请核实")

        # 上下限差距不应过大
        if si_upper and si_lower:
            ratio = si_upper / si_lower
            if ratio > 5:
                warnings.append(f"上下限比值({ratio:.1f})过大，请核实")

        return {
            "passed": len(warnings) == 0,
            "warnings": warnings,
            "severe": severe
        }

    async def _check_duplicate(self, data: dict) -> Dict[str, Any]:
        """检查重复"""
        region_code = data.get("region_code")
        effective_start = data.get("effective_start")

        # 按地区+时间检查
        if region_code and effective_start:
            result = await self.session.execute(
                select(Policy).where(
                    Policy.region_code == region_code,
                    Policy.effective_start == effective_start,
                    Policy.status == "active"
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return {
                    "is_duplicate": True,
                    "match_type": "region_date",
                    "existing_policy_id": existing.policy_id,
                    "existing_status": existing.status,
                    "similarity_score": 0.8
                }

        return {"is_duplicate": False}

    async def approve_review(
        self,
        review_id: str,
        reviewer_id: str,
        notes: Optional[str] = None,
        final_action: Optional[str] = None,
        modified_data: Optional[dict] = None,
        final_target_policy_id: Optional[str] = None
    ) -> Policy:
        """
        通过审核，创建或更新政策

        Args:
            review_id: 审核ID
            reviewer_id: 审核人ID
            notes: 审核备注
            final_action: 审核人最终决定 (可选，用于覆盖提交方判断)
                - "new": 创建新政策
                - "update": 更新现有政策
                - "new_version": 创建新版本
            modified_data: 审核人修改后的数据 (可选)
            final_target_policy_id: 最终操作的目标政策ID (可选，用于审核人指定)
        """
        result = await self.session.execute(
            select(ReviewQueue).where(ReviewQueue.review_id == review_id)
        )
        review = result.scalar_one_or_none()

        if not review:
            raise ValueError("审核任务不存在")

        if review.status not in ["claimed", "pending"]:
            raise ValueError(f"当前状态({review.status})无法执行通过操作")

        # 使用审核人修改的数据或原始提交数据
        data = modified_data if modified_data else json.loads(review.submitted_data)

        # 合并 raw_evidence 中的来源信息到 data
        raw_evidence = json.loads(review.raw_evidence) if review.raw_evidence else {}

        # 处理新的多来源格式
        sources = raw_evidence.get("sources", [])
        if sources:
            # 将所有来源存储到 source_attachments
            data["source_attachments"] = json.dumps(sources, ensure_ascii=False)

        # 确保必填字段有默认值
        if not data.get("region_code"):
            data["region_code"] = "000000"  # 默认地区代码

        now = datetime.utcnow().isoformat()

        # 确定最终操作类型
        action = final_action or review.submit_type or "new"
        target_policy_id = final_target_policy_id or review.existing_policy_id or review.policy_id

        # 解析生效年份
        policy_year = None
        if data.get("effective_start"):
            try:
                policy_year = datetime.fromisoformat(data["effective_start"]).year
            except ValueError:
                pass

        policy = None

        if action == "update":
            # 更新模式：更新现有政策
            policy = await self._update_existing_policy(
                policy_id=target_policy_id,
                data=data,
                reviewer_id=reviewer_id,
                notes=notes,
                now=now
            )
            change_type = "update"
            change_reason = f"审核通过后更新 - {review.change_description or '无说明'}"

        elif action == "new_version":
            # 创建新版本：基于现有政策创建新版本
            policy = await self._create_new_version(
                existing_policy_id=target_policy_id,
                data=data,
                reviewer_id=reviewer_id,
                submitted_by=review.submitted_by,
                notes=notes,
                now=now
            )
            change_type = "new_version"
            change_reason = f"审核通过后创建新版本 - {review.change_description or '无说明'}"

        else:
            # 新增模式：创建新政策
            policy = await self._create_new_policy(
                policy_id=review.policy_id,
                data=data,
                submitted_by=review.submitted_by,
                reviewer_id=reviewer_id,
                now=now
            )
            change_type = "create"
            change_reason = "审核通过后创建"

        # 创建版本记录
        version = PolicyVersion(
            policy_id=policy.policy_id,
            version_number=policy.version,
            change_type=change_type,
            changed_by=reviewer_id,
            changed_at=now,
            snapshot=json.dumps(data, ensure_ascii=False),
            change_reason=change_reason
        )
        self.session.add(version)

        # 创建审计日志
        await self._create_audit_log(
            review=review,
            action="approve",
            operator_id=reviewer_id,
            notes=f"Action: {action}, Notes: {notes}"
        )

        # 更新审核状态
        review.status = "approved"
        review.reviewer_id = reviewer_id
        review.reviewer_notes = notes
        review.reviewed_at = now
        review.final_action = action
        review.final_target_policy_id = target_policy_id
        if modified_data:
            review.reviewer_modified_data = json.dumps(modified_data, ensure_ascii=False)

        await self.session.commit()
        await self.session.refresh(policy)

        logger.info(f"Review approved: {review_id} -> Policy {policy.policy_id} (action: {action}) by {reviewer_id}")
        return policy

    async def _create_new_policy(
        self,
        policy_id: str,
        data: dict,
        submitted_by: str,
        reviewer_id: str,
        now: str
    ) -> Policy:
        """创建新政策"""
        policy_year = None
        if data.get("effective_start"):
            try:
                policy_year = datetime.fromisoformat(data["effective_start"]).year
            except ValueError:
                pass

        policy = Policy(
            policy_id=policy_id,
            policy_type="social_insurance",
            title=data.get("title"),
            region_code=data.get("region_code"),
            source_attachments=data.get("source_attachments", "[]"),
            published_at=data.get("published_at"),
            effective_start=data.get("effective_start"),
            effective_end=data.get("effective_end"),
            policy_year=policy_year,
            status="active",
            version=1,
            created_by=submitted_by,
            created_at=now,
            updated_at=now,
            reviewed_by=reviewer_id,
            reviewed_at=now
        )

        self.session.add(policy)

        # 创建社保扩展
        await self._create_or_update_si_extension(policy_id, data)

        return policy

    async def _update_existing_policy(
        self,
        policy_id: str,
        data: dict,
        reviewer_id: str,
        notes: Optional[str],
        now: str
    ) -> Policy:
        """更新现有政策"""
        result = await self.session.execute(
            select(Policy).where(Policy.policy_id == policy_id)
        )
        policy = result.scalar_one_or_none()

        if not policy:
            raise ValueError(f"政策 {policy_id} 不存在")

        # 更新政策基本信息
        policy.title = data.get("title", policy.title)
        policy.source_attachments = data.get("source_attachments", policy.source_attachments)
        policy.published_at = data.get("published_at", policy.published_at)
        policy.effective_start = data.get("effective_start", policy.effective_start)
        policy.effective_end = data.get("effective_end", policy.effective_end)
        policy.updated_at = now
        policy.reviewed_by = reviewer_id
        policy.reviewed_at = now

        # 更新生效年份
        if data.get("effective_start"):
            try:
                policy.policy_year = datetime.fromisoformat(data["effective_start"]).year
            except ValueError:
                pass

        # 更新社保扩展
        await self._create_or_update_si_extension(policy_id, data, update=True)

        return policy

    async def _create_new_version(
        self,
        existing_policy_id: str,
        data: dict,
        reviewer_id: str,
        submitted_by: str,
        notes: Optional[str],
        now: str
    ) -> Policy:
        """基于现有政策创建新版本"""
        # 获取原政策
        result = await self.session.execute(
            select(Policy).where(Policy.policy_id == existing_policy_id)
        )
        old_policy = result.scalar_one_or_none()

        if not old_policy:
            raise ValueError(f"原政策 {existing_policy_id} 不存在")

        # 生成新政策ID
        import uuid
        new_policy_id = str(uuid.uuid4())

        policy_year = None
        if data.get("effective_start"):
            try:
                policy_year = datetime.fromisoformat(data["effective_start"]).year
            except ValueError:
                pass

        # 创建新版本政策
        new_policy = Policy(
            policy_id=new_policy_id,
            policy_type=old_policy.policy_type,
            title=data.get("title", old_policy.title),
            region_code=data.get("region_code", old_policy.region_code),
            source_attachments=data.get("source_attachments", old_policy.source_attachments),
            published_at=data.get("published_at", old_policy.published_at),
            effective_start=data.get("effective_start"),
            effective_end=data.get("effective_end"),
            policy_year=policy_year,
            status="active",
            version=old_policy.version + 1,
            created_by=submitted_by,
            created_at=now,
            updated_at=now,
            reviewed_by=reviewer_id,
            reviewed_at=now
        )

        self.session.add(new_policy)

        # 创建社保扩展
        await self._create_or_update_si_extension(new_policy_id, data)

        return new_policy

    async def _create_or_update_si_extension(
        self,
        policy_id: str,
        data: dict,
        update: bool = False
    ):
        """创建或更新社保扩展数据"""
        # 计算追溯月数
        retroactive_months = None
        if data.get("is_retroactive") and data.get("retroactive_start") and data.get("effective_start"):
            try:
                retro_start = datetime.fromisoformat(data["retroactive_start"])
                eff_start = datetime.fromisoformat(data["effective_start"])
                retroactive_months = (eff_start.year - retro_start.year) * 12 + (eff_start.month - retro_start.month)
            except ValueError:
                pass

        if update:
            # 更新现有记录
            result = await self.session.execute(
                select(PolicySocialInsurance).where(PolicySocialInsurance.policy_id == policy_id)
            )
            si = result.scalar_one_or_none()
            if si:
                si.si_upper_limit = data.get("si_upper_limit", si.si_upper_limit)
                si.si_lower_limit = data.get("si_lower_limit", si.si_lower_limit)
                si.hf_upper_limit = data.get("hf_upper_limit", si.hf_upper_limit)
                si.hf_lower_limit = data.get("hf_lower_limit", si.hf_lower_limit)
                si.is_retroactive = 1 if data.get("is_retroactive") else 0
                si.retroactive_start = data.get("retroactive_start", si.retroactive_start)
                si.retroactive_months = retroactive_months
                si.coverage_types = json.dumps(data.get("coverage_types", []), ensure_ascii=False)
                si.special_notes = data.get("special_notes", si.special_notes)
                return

        # 创建新记录
        si = PolicySocialInsurance(
            policy_id=policy_id,
            si_upper_limit=data.get("si_upper_limit"),
            si_lower_limit=data.get("si_lower_limit"),
            hf_upper_limit=data.get("hf_upper_limit"),
            hf_lower_limit=data.get("hf_lower_limit"),
            is_retroactive=1 if data.get("is_retroactive") else 0,
            retroactive_start=data.get("retroactive_start"),
            retroactive_months=retroactive_months,
            coverage_types=json.dumps(data.get("coverage_types", []), ensure_ascii=False),
            special_notes=data.get("special_notes")
        )
        self.session.add(si)

    async def reject_review(
        self,
        review_id: str,
        reviewer_id: str,
        reason: str
    ):
        """拒绝审核"""
        result = await self.session.execute(
            select(ReviewQueue).where(ReviewQueue.review_id == review_id)
        )
        review = result.scalar_one_or_none()

        if not review:
            raise ValueError("审核任务不存在")

        if review.status not in ["claimed", "pending"]:
            raise ValueError(f"当前状态({review.status})无法执行拒绝操作")

        now = datetime.utcnow().isoformat()

        # 创建审计日志
        await self._create_audit_log(
            review=review,
            action="reject",
            operator_id=reviewer_id,
            notes=reason
        )

        review.status = "rejected"
        review.reviewer_id = reviewer_id
        review.reviewer_notes = reason
        review.reviewed_at = now

        await self.session.commit()
        logger.info(f"Review rejected: {review_id} by {reviewer_id}")

    async def claim_review(
        self,
        review_id: str,
        user_id: str
    ):
        """认领审核任务"""
        result = await self.session.execute(
            select(ReviewQueue).where(
                ReviewQueue.review_id == review_id,
                ReviewQueue.status == "pending"
            )
        )
        review = result.scalar_one_or_none()

        if not review:
            raise ValueError("审核任务不存在或已被认领")

        review.status = "claimed"
        review.claimed_by = user_id
        review.claimed_at = datetime.utcnow().isoformat()

        await self.session.commit()
        logger.info(f"Review claimed: {review_id} by {user_id}")

    async def release_review(
        self,
        review_id: str,
        user_id: str,
        reason: Optional[str] = None
    ):
        """释放已认领的审核任务"""
        result = await self.session.execute(
            select(ReviewQueue).where(
                ReviewQueue.review_id == review_id,
                ReviewQueue.status == "claimed"
            )
        )
        review = result.scalar_one_or_none()

        if not review:
            raise ValueError("审核任务不存在或未被认领")

        # 只有认领者可以释放
        if review.claimed_by != user_id:
            raise ValueError("只有认领者可以释放任务")

        # 创建审计日志
        await self._create_audit_log(
            review=review,
            action="release",
            operator_id=user_id,
            notes=reason or "释放认领"
        )

        review.status = "pending"
        review.claimed_by = None
        review.claimed_at = None

        await self.session.commit()
        logger.info(f"Review released: {review_id} by {user_id}")

    async def request_clarification(
        self,
        review_id: str,
        reviewer_id: str,
        clarification_request: str
    ):
        """请求补充材料"""
        result = await self.session.execute(
            select(ReviewQueue).where(ReviewQueue.review_id == review_id)
        )
        review = result.scalar_one_or_none()

        if not review:
            raise ValueError("审核任务不存在")

        if review.status not in ["claimed", "pending"]:
            raise ValueError(f"当前状态({review.status})无法请求补充")

        # 创建审计日志
        await self._create_audit_log(
            review=review,
            action="request_clarification",
            operator_id=reviewer_id,
            notes=clarification_request
        )

        review.status = "needs_clarification"
        review.reviewer_id = reviewer_id
        review.reviewer_notes = clarification_request
        review.reviewed_at = datetime.utcnow().isoformat()

        await self.session.commit()
        logger.info(f"Review clarification requested: {review_id} by {reviewer_id}")

    async def resubmit_with_clarification(
        self,
        review_id: str,
        updated_data: dict,
        clarification_notes: str
    ):
        """补充材料后重新提交"""
        result = await self.session.execute(
            select(ReviewQueue).where(ReviewQueue.review_id == review_id)
        )
        review = result.scalar_one_or_none()

        if not review:
            raise ValueError("审核任务不存在")

        if review.status != "needs_clarification":
            raise ValueError(f"当前状态({review.status})无法重新提交")

        # 更新提交数据
        review.submitted_data = json.dumps(updated_data, ensure_ascii=False)
        review.status = "pending"

        # 重新运行 AI 分析
        ai_analysis = await self._run_ai_analysis(updated_data)
        review.ai_validation = json.dumps(ai_analysis.get("validation", {}), ensure_ascii=False)
        review.risk_level = ai_analysis.get("risk_level", "low")
        review.risk_tags = json.dumps(ai_analysis.get("risk_tags", []), ensure_ascii=False)

        # 创建审计日志
        await self._create_audit_log(
            review=review,
            action="resubmit",
            operator_id=review.submitted_by,
            notes=clarification_notes
        )

        await self.session.commit()
        logger.info(f"Review resubmitted with clarification: {review_id}")

    async def get_review_with_diff(
        self,
        review_id: str
    ) -> Dict[str, Any]:
        """获取审核详情（含与历史政策的对比）"""
        result = await self.session.execute(
            select(ReviewQueue).where(ReviewQueue.review_id == review_id)
        )
        review = result.scalar_one_or_none()

        if not review:
            raise ValueError("审核任务不存在")

        submitted_data = json.loads(review.submitted_data) if review.submitted_data else {}

        # 获取变更分析
        change_analysis = await self._analyze_change_rate(submitted_data)

        # 构建差异对比
        diff = None
        if change_analysis.get("has_change"):
            prev_policy_id = change_analysis.get("previous_policy_id")
            if prev_policy_id:
                # 获取旧政策详情
                prev_result = await self.session.execute(
                    select(Policy, PolicySocialInsurance)
                    .join(PolicySocialInsurance, Policy.policy_id == PolicySocialInsurance.policy_id)
                    .where(Policy.policy_id == prev_policy_id)
                )
                prev_row = prev_result.first()
                if prev_row:
                    prev_policy, prev_si = prev_row
                    diff = {
                        "previous_policy": {
                            "policy_id": prev_policy.policy_id,
                            "title": prev_policy.title,
                            "effective_start": prev_policy.effective_start,
                            "si_upper_limit": prev_si.si_upper_limit,
                            "si_lower_limit": prev_si.si_lower_limit,
                            "hf_upper_limit": prev_si.hf_upper_limit,
                            "hf_lower_limit": prev_si.hf_lower_limit,
                        },
                        "new_data": {
                            "si_upper_limit": submitted_data.get("si_upper_limit"),
                            "si_lower_limit": submitted_data.get("si_lower_limit"),
                            "hf_upper_limit": submitted_data.get("hf_upper_limit"),
                            "hf_lower_limit": submitted_data.get("hf_lower_limit"),
                        },
                        "changes": {
                            "si_upper": {
                                "old": prev_si.si_upper_limit,
                                "new": submitted_data.get("si_upper_limit"),
                                "change": change_analysis.get("upper_change"),
                                "change_rate": change_analysis.get("upper_change_rate"),
                            },
                            "si_lower": {
                                "old": prev_si.si_lower_limit,
                                "new": submitted_data.get("si_lower_limit"),
                                "change": change_analysis.get("lower_change"),
                                "change_rate": change_analysis.get("lower_change_rate"),
                            }
                        }
                    }

        return {
            "review": review,
            "submitted_data": submitted_data,
            "change_analysis": change_analysis,
            "diff": diff
        }

    async def get_review_stats(self) -> Dict[str, Any]:
        """获取审核统计"""
        # 按状态统计
        status_counts = {}
        for status in ["pending", "claimed", "approved", "rejected", "needs_clarification"]:
            result = await self.session.execute(
                select(ReviewQueue).where(ReviewQueue.status == status)
            )
            reviews = result.scalars().all()
            status_counts[status] = len(reviews)

        # 按优先级统计待审核
        priority_counts = {}
        for priority in ["urgent", "high", "normal", "low"]:
            result = await self.session.execute(
                select(ReviewQueue).where(
                    and_(
                        ReviewQueue.status.in_(["pending", "claimed"]),
                        ReviewQueue.priority == priority
                    )
                )
            )
            priority_counts[priority] = len(result.scalars().all())

        # 按风险等级统计
        risk_counts = {}
        for risk in ["low", "medium", "high"]:
            result = await self.session.execute(
                select(ReviewQueue).where(
                    ReviewQueue.status.in_(["pending", "claimed"]),
                    ReviewQueue.risk_level == risk
                )
            )
            risk_counts[risk] = len(result.scalars().all())

        # SLA 超期统计
        now = datetime.utcnow()
        result = await self.session.execute(
            select(ReviewQueue).where(
                ReviewQueue.status.in_(["pending", "claimed"]),
            )
        )
        pending_reviews = result.scalars().all()

        sla_overdue = 0
        sla_warning = 0  # 临近超期
        for r in pending_reviews:
            if r.sla_deadline:
                deadline = datetime.fromisoformat(r.sla_deadline)
                remaining = (deadline - now).total_seconds() / 3600
                if remaining < 0:
                    sla_overdue += 1
                elif remaining < 4:  # 4小时内
                    sla_warning += 1

        return {
            "status_counts": status_counts,
            "pending_by_priority": priority_counts,
            "pending_by_risk": risk_counts,
            "total_pending": status_counts.get("pending", 0) + status_counts.get("claimed", 0),
            "sla_overdue": sla_overdue,
            "sla_warning": sla_warning
        }

    async def _create_audit_log(
        self,
        review: ReviewQueue,
        action: str,
        operator_id: str,
        notes: Optional[str] = None
    ):
        """创建审计日志"""
        log = AuditLog(
            policy_id=review.policy_id,
            action=f"review.{action}",
            new_value=json.dumps({
                "review_id": review.review_id,
                "notes": notes
            }, ensure_ascii=False),
            operator_id=operator_id,
            operator_type="user",
            operated_at=datetime.utcnow().isoformat()
        )
        self.session.add(log)
