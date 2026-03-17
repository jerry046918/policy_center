"""审核服务（支持多类型扩展）"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import json
import uuid
import logging

from app.models.review import ReviewQueue
from app.models.policy import Policy, PolicySocialInsurance, PolicyHousingFund
from app.models.version import PolicyVersion
from app.models.audit import AuditLog
from app.services.policy_type_registry import get_registry

logger = logging.getLogger(__name__)


class ReviewService:
    """审核服务（支持多类型扩展）"""

    STATUS_TRANSITIONS = {
        "pending": ["claimed"],
        "claimed": ["approved", "rejected", "needs_clarification", "released"],
        "needs_clarification": ["pending", "rejected"],
        "approved": [],
        "rejected": [],
    }

    SLA_HOURS = {
        "urgent": 1,
        "high": 4,
        "normal": 24,
        "low": 72
    }

    def __init__(self, session: AsyncSession):
        self.session = session
        self.registry = get_registry()

    # ── 扩展数据辅助方法 ─────────────────────────────────────

    async def _get_extension(self, policy_id: str, policy_type: str):
        """获取扩展数据"""
        desc = self.registry.get(policy_type)
        if not desc or not desc.extension_model:
            return None
        model = desc.extension_model
        result = await self.session.execute(
            select(model).where(model.policy_id == policy_id)
        )
        return result.scalar_one_or_none()

    async def _create_extension(self, policy_id: str, policy_type: str, data: dict):
        """创建扩展数据"""
        desc = self.registry.get(policy_type)
        if desc and desc.create_extension_func:
            ext = desc.create_extension_func(policy_id, data)
            self.session.add(ext)
            return ext
        return None

    async def _update_extension(self, policy_id: str, policy_type: str, data: dict):
        """更新扩展数据"""
        desc = self.registry.get(policy_type)
        if not desc:
            return

        ext = await self._get_extension(policy_id, policy_type)
        if ext and desc.update_extension_func:
            desc.update_extension_func(ext, data)
        elif not ext and desc.create_extension_func:
            ext = desc.create_extension_func(policy_id, data)
            self.session.add(ext)

    def _extension_to_response(self, ext, policy_type: str) -> Optional[dict]:
        """扩展模型转为响应 dict"""
        if ext is None:
            return None
        desc = self.registry.get(policy_type)
        if desc and desc.to_response_func:
            return desc.to_response_func(ext)
        return None

    # ── AI 分析 ─────────────────────────────────────────────

    async def _run_ai_analysis(self, data: dict, policy_type: str = "social_insurance") -> Dict[str, Any]:
        """
        AI 分析（支持多类型）

        先运行通用检查，再运行类型特定检查。
        """
        risk_tags = []
        warnings = []
        validation = {"passed": True, "errors": [], "warnings": []}

        # ── 通用检查（适用于所有类型）──────────────────────────

        # 1. 必填字段检查（通用）
        common_required = ["title", "region_code", "effective_start"]
        for field in common_required:
            if not data.get(field):
                validation["errors"].append(f"缺少必填字段: {field}")
                validation["passed"] = False

        # 2. 日期逻辑检查
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

        # ── 类型特定检查 ─────────────────────────────────────

        desc = self.registry.get(policy_type)

        # 使用注册的验证函数
        if desc and desc.validator_func:
            type_warnings = desc.validator_func(data)
            warnings.extend(type_warnings)

        # 社保基数类型的额外分析（涨幅分析、重复检测等）
        if policy_type == "social_insurance":
            # 必填字段扩展
            si_required = ["si_upper_limit", "si_lower_limit"]
            for field in si_required:
                if not data.get(field):
                    validation["errors"].append(f"缺少必填字段: {field}")
                    validation["passed"] = False

            # 涨幅分析
            change_analysis = await self._analyze_change_rate(data, policy_type)
            if change_analysis.get("has_change"):
                validation["change_analysis"] = change_analysis
                if change_analysis.get("upper_change_rate", 0) > 20:
                    risk_tags.append("涨幅异常")
                    warnings.append(f"社保上限涨幅{change_analysis['upper_change_rate']:.1f}%超过20%，请核实")
                elif change_analysis.get("upper_change_rate", 0) > 10:
                    risk_tags.append("涨幅较高")

                if change_analysis.get("lower_change_rate", 0) > 20:
                    risk_tags.append("下限涨幅异常")

        elif policy_type == "housing_fund":
            # 必填字段扩展
            hf_required = ["hf_upper_limit", "hf_lower_limit"]
            for field in hf_required:
                if not data.get(field):
                    validation["errors"].append(f"缺少必填字段: {field}")
                    validation["passed"] = False

            # 涨幅分析
            change_analysis = await self._analyze_change_rate(data, policy_type)
            if change_analysis.get("has_change"):
                validation["change_analysis"] = change_analysis
                if change_analysis.get("upper_change_rate", 0) > 20:
                    risk_tags.append("涨幅异常")
                    warnings.append(f"公积金上限涨幅{change_analysis['upper_change_rate']:.1f}%超过20%，请核实")
                elif change_analysis.get("upper_change_rate", 0) > 10:
                    risk_tags.append("涨幅较高")

                if change_analysis.get("lower_change_rate", 0) > 20:
                    risk_tags.append("下限涨幅异常")

        # 重复检测（通用，考虑 policy_type）
        duplicate_check = await self._check_duplicate(data, policy_type)
        if duplicate_check.get("is_duplicate"):
            risk_tags.append("疑似重复")
            warnings.append(f"发现相似政策: {duplicate_check.get('existing_policy_id')}")
            validation["duplicate_check"] = duplicate_check

        # 风险等级
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
        }

    async def _analyze_change_rate(self, data: dict, policy_type: str = "social_insurance") -> Dict[str, Any]:
        """分析与同地区上一期政策的变更（支持社保和公积金类型）"""
        if policy_type == "social_insurance":
            region_code = data.get("region_code")
            effective_start = data.get("effective_start")

            if not region_code or not effective_start:
                return {"has_change": False}

            result = await self.session.execute(
                select(Policy, PolicySocialInsurance)
                .join(PolicySocialInsurance, Policy.policy_id == PolicySocialInsurance.policy_id)
                .where(
                    Policy.region_code == region_code,
                    Policy.effective_start < effective_start,
                    Policy.status == "active",
                    Policy.policy_type == "social_insurance",
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

        elif policy_type == "housing_fund":
            region_code = data.get("region_code")
            effective_start = data.get("effective_start")

            if not region_code or not effective_start:
                return {"has_change": False}

            result = await self.session.execute(
                select(Policy, PolicyHousingFund)
                .join(PolicyHousingFund, Policy.policy_id == PolicyHousingFund.policy_id)
                .where(
                    Policy.region_code == region_code,
                    Policy.effective_start < effective_start,
                    Policy.status == "active",
                    Policy.policy_type == "housing_fund",
                )
                .order_by(Policy.effective_start.desc())
                .limit(1)
            )
            row = result.first()

            if not row:
                return {"has_change": False}

            prev_policy, prev_hf = row
            new_upper = data.get("hf_upper_limit")
            new_lower = data.get("hf_lower_limit")

            result_data = {
                "has_change": True,
                "previous_policy_id": prev_policy.policy_id,
                "previous_effective_start": prev_policy.effective_start,
                "previous_upper": prev_hf.hf_upper_limit,
                "previous_lower": prev_hf.hf_lower_limit,
            }

            if prev_hf.hf_upper_limit and new_upper:
                result_data["upper_change_rate"] = round(
                    ((new_upper - prev_hf.hf_upper_limit) / prev_hf.hf_upper_limit) * 100, 2
                )
                result_data["upper_change"] = new_upper - prev_hf.hf_upper_limit

            if prev_hf.hf_lower_limit and new_lower:
                result_data["lower_change_rate"] = round(
                    ((new_lower - prev_hf.hf_lower_limit) / prev_hf.hf_lower_limit) * 100, 2
                )
                result_data["lower_change"] = new_lower - prev_hf.hf_lower_limit

            return result_data

        return {"has_change": False}

    async def _check_duplicate(self, data: dict, policy_type: str = "social_insurance") -> Dict[str, Any]:
        """检查重复（考虑 policy_type）"""
        region_code = data.get("region_code")
        effective_start = data.get("effective_start")

        if region_code and effective_start:
            result = await self.session.execute(
                select(Policy).where(
                    Policy.region_code == region_code,
                    Policy.effective_start == effective_start,
                    Policy.status == "active",
                    Policy.policy_type == policy_type,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return {
                    "is_duplicate": True,
                    "match_type": "region_date_type",
                    "existing_policy_id": existing.policy_id,
                    "existing_status": existing.status,
                    "similarity_score": 0.8
                }

        return {"is_duplicate": False}

    # ── 审核通过 ─────────────────────────────────────────────

    async def approve_review(
        self,
        review_id: str,
        reviewer_id: str,
        notes: Optional[str] = None,
        final_action: Optional[str] = None,
        modified_data: Optional[dict] = None,
        final_target_policy_id: Optional[str] = None
    ) -> Policy:
        """通过审核，创建或更新政策"""
        result = await self.session.execute(
            select(ReviewQueue).where(ReviewQueue.review_id == review_id)
        )
        review = result.scalar_one_or_none()

        if not review:
            raise ValueError("审核任务不存在")

        if review.status not in ["claimed", "pending"]:
            raise ValueError(f"当前状态({review.status})无法执行通过操作")

        data = modified_data if modified_data else json.loads(review.submitted_data)

        # 合并 raw_evidence 中的来源信息
        raw_evidence = json.loads(review.raw_evidence) if review.raw_evidence else {}
        sources = raw_evidence.get("sources", [])
        if sources:
            data["source_attachments"] = json.dumps(sources, ensure_ascii=False)

        if not data.get("region_code"):
            data["region_code"] = "000000"

        now = datetime.utcnow().isoformat()

        # 确定最终操作类型
        action = final_action or review.submit_type or "new"
        target_policy_id = final_target_policy_id or review.existing_policy_id or review.policy_id

        # 从 submitted_data 推断 policy_type（优先从数据中获取，否则用默认值）
        policy_type = data.get("policy_type", "social_insurance")

        # 解析生效年份
        policy_year = None
        if data.get("effective_start"):
            try:
                policy_year = datetime.fromisoformat(data["effective_start"]).year
            except ValueError:
                pass

        policy = None

        if action == "update":
            policy = await self._update_existing_policy(
                policy_id=target_policy_id,
                data=data,
                policy_type=policy_type,
                reviewer_id=reviewer_id,
                notes=notes,
                now=now
            )
            change_type = "update"
            change_reason = f"审核通过后更新 - {review.change_description or '无说明'}"

        elif action == "new_version":
            policy = await self._create_new_version(
                existing_policy_id=target_policy_id,
                data=data,
                policy_type=policy_type,
                reviewer_id=reviewer_id,
                submitted_by=review.submitted_by,
                notes=notes,
                now=now
            )
            change_type = "new_version"
            change_reason = f"审核通过后创建新版本 - {review.change_description or '无说明'}"

        else:
            policy = await self._create_new_policy(
                policy_id=review.policy_id,
                data=data,
                policy_type=policy_type,
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
            notes=f"Action: {action}, Type: {policy_type}, Notes: {notes}"
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

        logger.info(f"Review approved: {review_id} -> Policy {policy.policy_id} (action: {action}, type: {policy_type}) by {reviewer_id}")
        return policy

    async def _create_new_policy(
        self,
        policy_id: str,
        data: dict,
        policy_type: str,
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
            policy_type=policy_type,
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

        # 创建类型扩展
        await self._create_extension(policy_id, policy_type, data)

        return policy

    async def _update_existing_policy(
        self,
        policy_id: str,
        data: dict,
        policy_type: str,
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

        policy.title = data.get("title", policy.title)
        policy.source_attachments = data.get("source_attachments", policy.source_attachments)
        policy.published_at = data.get("published_at", policy.published_at)
        policy.effective_start = data.get("effective_start", policy.effective_start)
        policy.effective_end = data.get("effective_end", policy.effective_end)
        policy.updated_at = now
        policy.reviewed_by = reviewer_id
        policy.reviewed_at = now

        if data.get("effective_start"):
            try:
                policy.policy_year = datetime.fromisoformat(data["effective_start"]).year
            except ValueError:
                pass

        # 更新类型扩展
        await self._update_extension(policy_id, policy.policy_type, data)

        return policy

    async def _create_new_version(
        self,
        existing_policy_id: str,
        data: dict,
        policy_type: str,
        reviewer_id: str,
        submitted_by: str,
        notes: Optional[str],
        now: str
    ) -> Policy:
        """基于现有政策创建新版本"""
        result = await self.session.execute(
            select(Policy).where(Policy.policy_id == existing_policy_id)
        )
        old_policy = result.scalar_one_or_none()

        if not old_policy:
            raise ValueError(f"原政策 {existing_policy_id} 不存在")

        new_policy_id = str(uuid.uuid4())

        policy_year = None
        if data.get("effective_start"):
            try:
                policy_year = datetime.fromisoformat(data["effective_start"]).year
            except ValueError:
                pass

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

        # 创建类型扩展
        await self._create_extension(new_policy_id, old_policy.policy_type, data)

        return new_policy

    # ── 其余审核操作（保持不变）──────────────────────────────

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

        if review.claimed_by != user_id:
            raise ValueError("只有认领者可以释放任务")

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

        # 推断 policy_type
        policy_type = updated_data.get("policy_type", "social_insurance")

        review.submitted_data = json.dumps(updated_data, ensure_ascii=False)
        review.status = "pending"

        ai_analysis = await self._run_ai_analysis(updated_data, policy_type)
        review.ai_validation = json.dumps(ai_analysis.get("validation", {}), ensure_ascii=False)
        review.risk_level = ai_analysis.get("risk_level", "low")
        review.risk_tags = json.dumps(ai_analysis.get("risk_tags", []), ensure_ascii=False)

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
        policy_type = submitted_data.get("policy_type", "social_insurance")

        # 获取变更分析
        change_analysis = await self._analyze_change_rate(submitted_data, policy_type)

        # 构建差异对比（支持社保和公积金类型）
        diff = None
        if change_analysis.get("has_change") and policy_type == "social_insurance":
            prev_policy_id = change_analysis.get("previous_policy_id")
            if prev_policy_id:
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
                        },
                        "new_data": {
                            "si_upper_limit": submitted_data.get("si_upper_limit"),
                            "si_lower_limit": submitted_data.get("si_lower_limit"),
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
        elif change_analysis.get("has_change") and policy_type == "housing_fund":
            prev_policy_id = change_analysis.get("previous_policy_id")
            if prev_policy_id:
                prev_result = await self.session.execute(
                    select(Policy, PolicyHousingFund)
                    .join(PolicyHousingFund, Policy.policy_id == PolicyHousingFund.policy_id)
                    .where(Policy.policy_id == prev_policy_id)
                )
                prev_row = prev_result.first()
                if prev_row:
                    prev_policy, prev_hf = prev_row
                    diff = {
                        "previous_policy": {
                            "policy_id": prev_policy.policy_id,
                            "title": prev_policy.title,
                            "effective_start": prev_policy.effective_start,
                            "hf_upper_limit": prev_hf.hf_upper_limit,
                            "hf_lower_limit": prev_hf.hf_lower_limit,
                        },
                        "new_data": {
                            "hf_upper_limit": submitted_data.get("hf_upper_limit"),
                            "hf_lower_limit": submitted_data.get("hf_lower_limit"),
                        },
                        "changes": {
                            "hf_upper": {
                                "old": prev_hf.hf_upper_limit,
                                "new": submitted_data.get("hf_upper_limit"),
                                "change": change_analysis.get("upper_change"),
                                "change_rate": change_analysis.get("upper_change_rate"),
                            },
                            "hf_lower": {
                                "old": prev_hf.hf_lower_limit,
                                "new": submitted_data.get("hf_lower_limit"),
                                "change": change_analysis.get("lower_change"),
                                "change_rate": change_analysis.get("lower_change_rate"),
                            }
                        }
                    }

        return {
            "review": review,
            "submitted_data": submitted_data,
            "change_analysis": change_analysis,
            "diff": diff,
            "policy_type": policy_type,
        }

    async def get_review_stats(self) -> Dict[str, Any]:
        """获取审核统计"""
        status_counts = {}
        for status in ["pending", "claimed", "approved", "rejected", "needs_clarification"]:
            result = await self.session.execute(
                select(ReviewQueue).where(ReviewQueue.status == status)
            )
            reviews = result.scalars().all()
            status_counts[status] = len(reviews)

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

        risk_counts = {}
        for risk in ["low", "medium", "high"]:
            result = await self.session.execute(
                select(ReviewQueue).where(
                    ReviewQueue.status.in_(["pending", "claimed"]),
                    ReviewQueue.risk_level == risk
                )
            )
            risk_counts[risk] = len(result.scalars().all())

        now = datetime.utcnow()
        result = await self.session.execute(
            select(ReviewQueue).where(
                ReviewQueue.status.in_(["pending", "claimed"]),
            )
        )
        pending_reviews = result.scalars().all()

        sla_overdue = 0
        sla_warning = 0
        for r in pending_reviews:
            if r.sla_deadline:
                deadline = datetime.fromisoformat(r.sla_deadline)
                remaining = (deadline - now).total_seconds() / 3600
                if remaining < 0:
                    sla_overdue += 1
                elif remaining < 4:
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
