"""政策服务（支持多类型扩展）"""
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
from app.services.policy_type_registry import get_registry

logger = logging.getLogger(__name__)


class PolicyService:
    """政策管理服务（支持多类型扩展）"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.registry = get_registry()

    # ── 扩展数据 CRUD 辅助方法 ─────────────────────────────────

    # 旧类型编码到新编码的兼容映射
    _TYPE_COMPAT = {
        "social_insurance_base": "social_insurance",
    }

    async def _get_extension(self, policy_id: str, policy_type: str):
        """获取政策的扩展数据（内置类型从扩展表读，动态类型从 extension_data 读）"""
        # 兼容旧类型编码
        policy_type = self._TYPE_COMPAT.get(policy_type, policy_type)
        desc = self.registry.get(policy_type)
        if not desc:
            return None

        # 内置类型：从专用扩展表查询
        if desc.is_builtin and desc.extension_model:
            model = desc.extension_model
            result = await self.session.execute(
                select(model).where(model.policy_id == policy_id)
            )
            return result.scalar_one_or_none()

        # 动态类型：从 policies.extension_data 读取
        result = await self.session.execute(
            select(Policy.extension_data).where(Policy.policy_id == policy_id)
        )
        data_json = result.scalar_one_or_none()
        return data_json  # 返回 JSON 字符串，_extension_to_response 会解析

    async def _create_extension(self, policy_id: str, policy_type: str, data: dict):
        """创建扩展数据"""
        desc = self.registry.get(policy_type)
        if not desc:
            return None

        # 内置类型：写入专用扩展表
        if desc.is_builtin and desc.create_extension_func:
            ext = desc.create_extension_func(policy_id, data)
            self.session.add(ext)
            return ext

        # 动态类型：写入 policies.extension_data
        # 只保留 field_schema 中定义的字段
        filtered = self._filter_type_data(desc, data)
        result = await self.session.execute(
            select(Policy).where(Policy.policy_id == policy_id)
        )
        policy = result.scalar_one_or_none()
        if policy:
            policy.extension_data = json.dumps(filtered, ensure_ascii=False)
        return filtered

    async def _update_extension(self, policy_id: str, policy_type: str, data: dict):
        """更新扩展数据"""
        desc = self.registry.get(policy_type)
        if not desc:
            return

        # 内置类型
        if desc.is_builtin:
            ext = await self._get_extension(policy_id, policy_type)
            if ext and desc.update_extension_func:
                desc.update_extension_func(ext, data)
            elif not ext and desc.create_extension_func:
                ext = desc.create_extension_func(policy_id, data)
                self.session.add(ext)
            return

        # 动态类型：合并更新到 extension_data
        result = await self.session.execute(
            select(Policy).where(Policy.policy_id == policy_id)
        )
        policy = result.scalar_one_or_none()
        if policy:
            existing = {}
            if policy.extension_data:
                try:
                    existing = json.loads(policy.extension_data)
                except (json.JSONDecodeError, TypeError):
                    pass
            existing.update(self._filter_type_data(desc, data))
            policy.extension_data = json.dumps(existing, ensure_ascii=False)

    def _extension_to_response(self, ext, policy_type: str) -> Optional[dict]:
        """将扩展模型转为响应 dict"""
        if ext is None:
            return None
        policy_type = self._TYPE_COMPAT.get(policy_type, policy_type)
        desc = self.registry.get(policy_type)
        if not desc:
            return None

        # 内置类型：使用专用转换函数
        if desc.is_builtin and desc.to_response_func:
            return desc.to_response_func(ext)

        # 动态类型：ext 是 JSON 字符串
        if isinstance(ext, str):
            try:
                return json.loads(ext)
            except (json.JSONDecodeError, TypeError):
                return None

        return None

    def _filter_type_data(self, desc, data: dict) -> dict:
        """只保留 field_schema 中定义的字段（过滤通用字段和无关字段）"""
        if not desc.field_schema:
            return data
        common_fields = {
            "title", "region_code", "published_at", "effective_start",
            "effective_end", "policy_type", "source_attachments",
        }
        return {
            k: v for k, v in data.items()
            if k in desc.field_schema and k not in common_fields
        }

    def _validate_type_data(self, policy_type: str, data: dict) -> List[str]:
        """使用类型注册的验证函数验证扩展数据"""
        desc = self.registry.get(policy_type)
        if desc and desc.validator_func:
            return desc.validator_func(data)
        return []


    # ── 核心 CRUD ─────────────────────────────────────────────

    async def create_policy(
        self,
        data: PolicyCreate,
        created_by: str,
        request_id: Optional[str] = None,
        status: str = "pending_review"
    ) -> Policy:
        """
        创建政策（支持多类型）

        Args:
            data: 政策创建数据
            created_by: 创建者ID
            request_id: 请求ID
            status: 政策状态

        Returns:
            创建的政策对象
        """
        policy_type = data.policy_type or "social_insurance"

        # 验证政策类型是否已注册
        desc = self.registry.get(policy_type)
        if not desc:
            raise ValueError(f"不支持的政策类型: {policy_type}。可用类型: {', '.join(self.registry.list_type_codes())}")

        # 生成 policy_id
        policy_id = str(uuid.uuid4())

        # 解析年份
        try:
            effective_date = datetime.strptime(data.effective_start, "%Y-%m-%d")
            policy_year = effective_date.year
        except ValueError:
            raise ValueError(f"无效的生效日期格式: {data.effective_start}")

        # 获取规范化的类型数据
        type_data = data.get_type_data()

        # 类型特定验证
        warnings = self._validate_type_data(policy_type, type_data)
        if warnings:
            # 对于致命验证错误，抛出异常
            fatal = [w for w in warnings if "必须" in w]
            if fatal:
                raise ValueError("; ".join(fatal))

        # 创建政策主记录
        now = datetime.utcnow().isoformat()
        policy = Policy(
            policy_id=policy_id,
            policy_type=policy_type,
            title=data.title,
            region_code=data.region_code,
            published_at=data.published_at,
            effective_start=data.effective_start,
            effective_end=data.effective_end,
            policy_year=policy_year,
            status=status,
            version=1,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.session.add(policy)

        # 创建类型扩展数据
        if type_data:
            # 把通用日期字段传入，某些扩展类型可能需要
            type_data_with_context = {**type_data, "effective_start": data.effective_start}
            await self._create_extension(policy_id, policy_type, type_data_with_context)

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
            new_value={"title": data.title, "region_code": data.region_code, "policy_type": policy_type}
        )

        await self.session.commit()
        await self.session.refresh(policy)

        logger.info(f"Policy created: {policy_id} type={policy_type} by {created_by}")
        return policy

    async def update_policy(
        self,
        policy_id: str,
        data: PolicyUpdate,
        updated_by: str,
        request_id: Optional[str] = None
    ) -> Policy:
        """更新政策（支持多类型）"""
        result = await self.session.execute(
            select(Policy).where(
                Policy.policy_id == policy_id,
                Policy.deleted_at.is_(None)
            )
        )
        policy = result.scalar_one_or_none()

        if not policy:
            raise ValueError(f"政策不存在: {policy_id}")

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

        # 更新年份
        if "effective_start" in changed_fields:
            try:
                effective_date = datetime.strptime(data.effective_start, "%Y-%m-%d")
                policy.policy_year = effective_date.year
            except ValueError:
                pass

        # 更新类型扩展数据
        type_data = data.get_type_data()
        if type_data:
            # 验证
            warnings = self._validate_type_data(policy.policy_type, type_data)
            fatal = [w for w in warnings if "必须" in w]
            if fatal:
                raise ValueError("; ".join(fatal))

            # 传入 effective_start 上下文
            effective_start = data.effective_start or policy.effective_start
            type_data_with_context = {**type_data, "effective_start": effective_start}

            await self._update_extension(policy_id, policy.policy_type, type_data_with_context)
            changed_fields.append("type_data")
            new_values["type_data"] = type_data

        # 如果没有变更，直接返回
        if not changed_fields:
            return policy

        now = datetime.utcnow().isoformat()
        policy.updated_at = now

        if create_new_version:
            policy.version += 1
            change_type = "update"
        else:
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
        """软删除政策"""
        result = await self.session.execute(
            select(Policy).where(
                Policy.policy_id == policy_id,
                Policy.deleted_at.is_(None)
            )
        )
        policy = result.scalar_one_or_none()

        if not policy:
            raise ValueError(f"政策不存在: {policy_id}")

        if policy.status == "active":
            logger.warning(f"Deleting active policy: {policy_id}")

        now = datetime.utcnow().isoformat()
        policy.deleted_at = now
        policy.deleted_by = deleted_by
        policy.status = "deleted"
        policy.updated_at = now

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

    async def get_policy_with_extension(self, policy_id: str) -> Optional[Dict[str, Any]]:
        """
        获取政策及其扩展数据（支持所有类型）

        返回:
            {
                "policy": Policy,
                "extension": <扩展模型实例或None>,
                "type_data": <dict或None>,  # 扩展数据的响应格式
                "social_insurance": <PolicySocialInsurance或None>,  # 兼容旧代码
            }
        """
        policy = await self.get_policy_by_id(policy_id)
        if not policy:
            return None

        ext = await self._get_extension(policy_id, policy.policy_type)
        type_data = self._extension_to_response(ext, policy.policy_type)

        # 向后兼容
        si = ext if policy.policy_type in ("social_insurance", "social_insurance_base") else None

        return {
            "policy": policy,
            "extension": ext,
            "type_data": type_data,
            "social_insurance": si,
        }

    async def check_duplicate(
        self,
        region_code: Optional[str] = None,
        effective_start: Optional[str] = None,
        policy_type: Optional[str] = None,
        exclude_policy_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        检查重复政策

        增加了 policy_type 参数，不同类型的政策互不视为重复。
        """
        if region_code and effective_start:
            conditions = [
                Policy.region_code == region_code,
                Policy.effective_start == effective_start,
                Policy.status == "active",
                Policy.deleted_at.is_(None),
            ]
            if policy_type:
                conditions.append(Policy.policy_type == policy_type)
            if exclude_policy_id:
                conditions.append(Policy.policy_id != exclude_policy_id)

            result = await self.session.execute(
                select(Policy).where(and_(*conditions))
            )
            existing = result.scalar_one_or_none()
            if existing:
                return {
                    "is_duplicate": True,
                    "existing_policy_id": existing.policy_id,
                    "existing_status": existing.status,
                    "existing_policy_type": existing.policy_type,
                    "similarity_score": 0.8,
                    "match_type": "region_date_type"
                }

        return {
            "is_duplicate": False,
            "existing_policy_id": None,
            "similarity_score": 0.0
        }

    async def expire_outdated(self) -> int:
        """将已过期的政策标记为 expired 状态"""
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
