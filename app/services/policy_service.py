"""政策服务"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime
from typing import Optional, List, Dict, Any
import json
import uuid
import logging

from app.models.policy import Policy, PolicySocialInsurance
from app.models.version import PolicyVersion
from app.models.audit import AuditLog
from app.schemas.policy import PolicyCreate, PolicyUpdate

logger = logging.getLogger(__name__)


class PolicyService:
    """政策管理服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_policy(
        self,
        data: PolicyCreate,
        created_by: str,
        request_id: Optional[str] = None,
        status: str = "pending_review"
    ) -> Policy:
        """
        创建政策

        Args:
            data: 政策创建数据
            created_by: 创建者ID
            request_id: 请求ID
            status: 政策状态（人工提交默认active，Agent提交默认pending_review）

        Returns:
            创建的政策对象

        Raises:
            ValueError: 数据验证失败
        """
        # 生成 policy_id
        policy_id = str(uuid.uuid4())

        # 解析年份
        try:
            effective_date = datetime.strptime(data.effective_start, "%Y-%m-%d")
            policy_year = effective_date.year
        except ValueError:
            raise ValueError(f"无效的生效日期格式: {data.effective_start}")

        # 验证上下限
        if data.social_insurance:
            si_upper = data.social_insurance.si_upper_limit
            si_lower = data.social_insurance.si_lower_limit
            if si_upper and si_lower and si_upper <= si_lower:
                raise ValueError("社保上限必须大于下限")

            hf_upper = data.social_insurance.hf_upper_limit
            hf_lower = data.social_insurance.hf_lower_limit
            if hf_upper and hf_lower and hf_upper <= hf_lower:
                raise ValueError("公积金上限必须大于下限")

        # 创建政策主记录
        now = datetime.utcnow().isoformat()
        policy = Policy(
            policy_id=policy_id,
            policy_type="social_insurance",
            title=data.title,
            region_code=data.region_code,
            published_at=data.published_at,
            effective_start=data.effective_start,
            effective_end=data.effective_end,
            policy_year=policy_year,
            status=status,  # 根据来源决定状态
            version=1,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )

        self.session.add(policy)

        # 创建社保扩展数据
        if data.social_insurance:
            # 计算追溯月数
            retroactive_months = None
            if data.social_insurance.is_retroactive and data.social_insurance.retroactive_start:
                try:
                    retro_start = datetime.strptime(data.social_insurance.retroactive_start, "%Y-%m-%d")
                    eff_start = datetime.strptime(data.effective_start, "%Y-%m-%d")
                    retroactive_months = (eff_start.year - retro_start.year) * 12 + (eff_start.month - retro_start.month)
                except ValueError:
                    pass

            si = PolicySocialInsurance(
                policy_id=policy_id,
                si_upper_limit=data.social_insurance.si_upper_limit,
                si_lower_limit=data.social_insurance.si_lower_limit,
                hf_upper_limit=data.social_insurance.hf_upper_limit,
                hf_lower_limit=data.social_insurance.hf_lower_limit,
                is_retroactive=1 if data.social_insurance.is_retroactive else 0,
                retroactive_start=data.social_insurance.retroactive_start,
                retroactive_months=retroactive_months,
                coverage_types=json.dumps(data.social_insurance.coverage_types or [], ensure_ascii=False),
                special_notes=data.social_insurance.special_notes,
            )
            self.session.add(si)

        # 创建初始版本记录
        version = PolicyVersion(
            policy_id=policy_id,
            version_number=1,
            change_type="create",
            changed_by=created_by,
            changed_at=now,
            snapshot=json.dumps(data.model_dump(), ensure_ascii=False),
        )
        self.session.add(version)

        # 创建审计日志
        await self._create_audit_log(
            policy_id=policy_id,
            action="create",
            operator_id=created_by,
            request_id=request_id,
            new_value={"title": data.title, "region_code": data.region_code}
        )

        await self.session.commit()
        await self.session.refresh(policy)

        logger.info(f"Policy created: {policy_id} by {created_by}")
        return policy

    async def update_policy(
        self,
        policy_id: str,
        data: PolicyUpdate,
        updated_by: str,
        request_id: Optional[str] = None
    ) -> Policy:
        """
        更新政策

        Args:
            policy_id: 政策ID
            data: 更新数据
            updated_by: 更新者ID
            request_id: 请求ID

        Returns:
            更新后的政策对象

        Raises:
            ValueError: 政策不存在或数据验证失败
        """
        result = await self.session.execute(
            select(Policy).where(
                Policy.policy_id == policy_id,
                Policy.deleted_at.is_(None)
            )
        )
        policy = result.scalar_one_or_none()

        if not policy:
            raise ValueError(f"政策不存在: {policy_id}")

        # 判断是否创建新版本
        create_new_version = data.create_new_version

        if policy.status == "active" and create_new_version:
            logger.info(f"Creating new version for active policy {policy_id}")

        # 记录旧值用于审计
        old_values = {}
        new_values = {}
        changed_fields = []

        # 更新基础字段
        update_data = data.model_dump(exclude_unset=True)

        for field in ["title", "published_at", "effective_start", "effective_end"]:
            if field in update_data and update_data[field] is not None:
                old_value = getattr(policy, field)
                if old_value != update_data[field]:
                    old_values[field] = old_value
                    new_values[field] = update_data[field]
                    setattr(policy, field, update_data[field])
                    changed_fields.append(field)

        # 更新年份（如果生效日期变更）
        if "effective_start" in changed_fields:
            try:
                effective_date = datetime.strptime(data.effective_start, "%Y-%m-%d")
                policy.policy_year = effective_date.year
            except ValueError:
                pass

        # 更新社保数据
        if data.social_insurance:
            # 验证上下限
            si_upper = data.social_insurance.si_upper_limit
            si_lower = data.social_insurance.si_lower_limit
            if si_upper and si_lower and si_upper <= si_lower:
                raise ValueError("社保上限必须大于下限")

            si_result = await self.session.execute(
                select(PolicySocialInsurance).where(PolicySocialInsurance.policy_id == policy_id)
            )
            si = si_result.scalar_one_or_none()

            if si:
                si_fields = {
                    "si_upper_limit": data.social_insurance.si_upper_limit,
                    "si_lower_limit": data.social_insurance.si_lower_limit,
                    "hf_upper_limit": data.social_insurance.hf_upper_limit,
                    "hf_lower_limit": data.social_insurance.hf_lower_limit,
                    "is_retroactive": 1 if data.social_insurance.is_retroactive else 0,
                    "retroactive_start": data.social_insurance.retroactive_start,
                    "coverage_types": json.dumps(data.social_insurance.coverage_types or [], ensure_ascii=False),
                    "special_notes": data.social_insurance.special_notes,
                }

                for field, value in si_fields.items():
                    if value is not None:
                        old_value = getattr(si, field)
                        if old_value != value:
                            old_values[f"social_insurance.{field}"] = old_value
                            new_values[f"social_insurance.{field}"] = value
                            setattr(si, field, value)

                if any(f.startswith("social_insurance.") for f in new_values):
                    changed_fields.append("social_insurance")

        # 如果没有变更，直接返回
        if not changed_fields:
            return policy

        now = datetime.utcnow().isoformat()
        policy.updated_at = now

        # 根据更新模式决定是否增加版本号
        if create_new_version:
            # 发布新版本：增加版本号
            policy.version += 1
            change_type = "update"
        else:
            # 微调更新：不增加版本号，记录为修订
            change_type = "minor_update"

        # 创建版本记录
        version = PolicyVersion(
            policy_id=policy_id,
            version_number=policy.version,
            change_type=change_type,
            changed_fields=json.dumps(changed_fields, ensure_ascii=False),
            change_reason=data.change_reason,
            changed_by=updated_by,
            changed_at=now,
            snapshot=json.dumps(update_data, ensure_ascii=False),
        )
        self.session.add(version)

        # 创建审计日志
        await self._create_audit_log(
            policy_id=policy_id,
            action=change_type,
            operator_id=updated_by,
            request_id=request_id,
            old_value=old_values,
            new_value=new_values,
            notes=data.change_reason
        )

        await self.session.commit()
        await self.session.refresh(policy)

        logger.info(f"Policy {'new version' if create_new_version else 'minor update'}: {policy_id} v{policy.version} by {updated_by}")
        return policy

    async def delete_policy(
        self,
        policy_id: str,
        deleted_by: str,
        request_id: Optional[str] = None,
        reason: Optional[str] = None
    ):
        """
        软删除政策

        Args:
            policy_id: 政策ID
            deleted_by: 删除者ID
            request_id: 请求ID
            reason: 删除原因
        """
        result = await self.session.execute(
            select(Policy).where(
                Policy.policy_id == policy_id,
                Policy.deleted_at.is_(None)
            )
        )
        policy = result.scalar_one_or_none()

        if not policy:
            raise ValueError(f"政策不存在: {policy_id}")

        # 检查是否可以删除
        if policy.status == "active":
            logger.warning(f"Deleting active policy: {policy_id}")

        now = datetime.utcnow().isoformat()
        policy.deleted_at = now
        policy.deleted_by = deleted_by
        policy.status = "deleted"
        policy.updated_at = now

        # 创建审计日志
        await self._create_audit_log(
            policy_id=policy_id,
            action="delete",
            operator_id=deleted_by,
            request_id=request_id,
            notes=reason or "软删除"
        )

        await self.session.commit()
        logger.info(f"Policy deleted: {policy_id} by {deleted_by}")

    async def get_policy_by_id(self, policy_id: str) -> Optional[Policy]:
        """根据ID获取政策"""
        result = await self.session.execute(
            select(Policy).where(
                Policy.policy_id == policy_id,
                Policy.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()

    async def get_policy_with_si(self, policy_id: str) -> Optional[Dict[str, Any]]:
        """获取政策及其社保扩展数据"""
        policy = await self.get_policy_by_id(policy_id)
        if not policy:
            return None

        si_result = await self.session.execute(
            select(PolicySocialInsurance).where(PolicySocialInsurance.policy_id == policy_id)
        )
        si = si_result.scalar_one_or_none()

        return {
            "policy": policy,
            "social_insurance": si,
        }

    async def check_duplicate(
        self,
        region_code: Optional[str] = None,
        effective_start: Optional[str] = None,
        exclude_policy_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        检查重复政策

        Returns:
            包含 is_duplicate, existing_policy_id, similarity_score 的字典
        """
        # 按地区+生效日期检查
        if region_code and effective_start:
            result = await self.session.execute(
                select(Policy).where(
                    and_(
                        Policy.region_code == region_code,
                        Policy.effective_start == effective_start,
                        Policy.status == "active",
                        Policy.deleted_at.is_(None),
                        Policy.policy_id != exclude_policy_id if exclude_policy_id else True
                    )
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return {
                    "is_duplicate": True,
                    "existing_policy_id": existing.policy_id,
                    "existing_status": existing.status,
                    "similarity_score": 0.8,
                    "match_type": "region_date"
                }

        return {
            "is_duplicate": False,
            "existing_policy_id": None,
            "similarity_score": 0.0
        }

    async def expire_outdated(self) -> int:
        """
        将已过期的政策标记为 expired 状态

        检查 effective_end < 当前日期 且状态为 active 的政策

        Returns:
            过期的政策数量
        """
        now = datetime.utcnow().strftime("%Y-%m-%d")
        result = await self.session.execute(
            select(Policy).where(
                and_(
                    Policy.status == "active",
                    Policy.deleted_at.is_(None),
                    Policy.effective_end.isnot(None),
                    Policy.effective_end < now
                )
            )
        )
        policies = result.scalars().all()

        count = 0
        for policy in policies:
            policy.status = "expired"
            policy.updated_at = datetime.utcnow().isoformat()
            count += 1

        if count > 0:
            await self.session.commit()
            logger.info(f"Expired {count} outdated policies")

        return count

    async def _create_audit_log(
        self,
        policy_id: str,
        action: str,
        operator_id: str,
        request_id: Optional[str] = None,
        field_name: Optional[str] = None,
        old_value: Optional[Any] = None,
        new_value: Optional[Any] = None,
        notes: Optional[str] = None
    ):
        """创建审计日志"""
        log = AuditLog(
            policy_id=policy_id,
            action=action,
            field_name=field_name,
            old_value=json.dumps(old_value, ensure_ascii=False) if old_value else None,
            new_value=json.dumps(new_value, ensure_ascii=False) if new_value else None,
            operator_id=operator_id,
            operator_type="user",
            request_id=request_id,
            operated_at=datetime.utcnow().isoformat(),
        )
        self.session.add(log)
