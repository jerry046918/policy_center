"""政策管理 API（支持多类型扩展）"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional, List
from datetime import datetime
import json
import logging

from app.database import get_session
from app.models.policy import Policy, PolicySocialInsurance
from app.models.region import Region
from app.schemas.policy import (
    PolicyCreate,
    PolicyUpdate,
    PolicyResponse,
    PolicyListResponse,
    PolicySocialInsuranceResponse
)
from app.schemas.common import PaginatedResponse
from app.api.auth import get_current_user, UserAuth

from app.services.policy_service import PolicyService
from app.services.policy_type_registry import get_registry

router = APIRouter()
logger = logging.getLogger(__name__)


async def get_region_name(session: AsyncSession, region_code: str) -> Optional[str]:
    """获取地区名称"""
    if not region_code:
        return None
    result = await session.execute(
        select(Region.name).where(Region.code == region_code)
    )
    return result.scalar_one_or_none()


@router.get("")
async def list_policies(
    region_code: Optional[str] = Query(None, min_length=0, max_length=6),
    year: Optional[int] = Query(None, ge=1900, le=2100),
    policy_type: Optional[str] = Query(None, description="政策类型编码筛选"),
    is_retroactive: Optional[bool] = Query(None),
    keyword: Optional[str] = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """
    政策列表查询（仅展示生效中的政策）

    支持筛选:
    - region_code: 地区编码
    - year: 政策年度
    - policy_type: 政策类型
    - is_retroactive: 是否追溯（仅社保类型）
    - keyword: 关键词搜索
    """
    try:
        registry = get_registry()

        base_query = select(Policy).where(
            Policy.deleted_at.is_(None),
            Policy.status == "active"
        )

        if region_code:
            base_query = base_query.where(Policy.region_code == region_code)
        if year:
            base_query = base_query.where(Policy.policy_year == year)
        if policy_type:
            base_query = base_query.where(Policy.policy_type == policy_type)
        if keyword:
            base_query = base_query.where(
                Policy.title.contains(keyword)
            )

        # 追溯筛选（仅社保类型有此概念）
        if is_retroactive is not None:
            si_subquery = select(PolicySocialInsurance.policy_id).where(
                PolicySocialInsurance.is_retroactive == (1 if is_retroactive else 0)
            )
            base_query = base_query.where(Policy.policy_id.in_(si_subquery))

        count_query = select(func.count()).select_from(base_query.subquery())
        total = await session.scalar(count_query) or 0

        base_query = base_query.order_by(Policy.effective_start.desc())
        base_query = base_query.offset((page - 1) * page_size).limit(page_size)

        result = await session.execute(base_query)
        policies = result.scalars().all()

        service = PolicyService(session)
        items = []
        for p in policies:
            region_name = await get_region_name(session, p.region_code)

            # 获取扩展数据
            ext = await service._get_extension(p.policy_id, p.policy_type)
            type_data = service._extension_to_response(ext, p.policy_type)

            # 构建列表摘要
            type_summary = None
            si_upper = None
            si_lower = None
            is_retro = False

            if p.policy_type in ("social_insurance", "social_insurance_base") and ext:
                si_upper = ext.si_upper_limit
                si_lower = ext.si_lower_limit
                is_retro = ext.is_retroactive == 1
                type_summary = {"si_upper_limit": si_upper, "si_lower_limit": si_lower}
            elif p.policy_type == "housing_fund" and ext:
                is_retro = ext.is_retroactive == 1
                type_summary = {"hf_upper_limit": ext.hf_upper_limit, "hf_lower_limit": ext.hf_lower_limit}
            elif type_data:
                # 其他类型，取前几个关键字段作为摘要
                type_summary = {k: v for i, (k, v) in enumerate(type_data.items()) if i < 3 and v is not None}

            items.append(PolicyListResponse(
                policy_id=p.policy_id,
                policy_type=p.policy_type,
                title=p.title,
                region_code=p.region_code,
                region_name=region_name,
                type_summary=type_summary,
                si_upper_limit=si_upper,
                si_lower_limit=si_lower,
                effective_start=p.effective_start,
                status=p.status,
                is_retroactive=is_retro,
            ))

        return PaginatedResponse(
            success=True,
            data=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size if total > 0 else 0
        )

    except Exception as e:
        logger.error(f"Error listing policies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/types")
async def list_policy_types(
    current_user: UserAuth = Depends(get_current_user)
):
    """
    获取所有支持的政策类型

    返回系统中注册的所有政策类型及其元数据。
    """
    registry = get_registry()
    types = registry.list_all()

    return {
        "success": True,
        "data": [
            {
                "type_code": t.type_code,
                "type_name": t.type_name,
                "description": t.description,
                "field_schema": t.field_schema,
                "validation_rules": t.validation_rules,
                "example_data": t.example_data,
            }
            for t in types
        ],
        "total": len(types)
    }


@router.get("/check-duplicate")
async def check_duplicate(
    region_code: Optional[str] = Query(None),
    effective_start: Optional[str] = Query(None),
    policy_type: Optional[str] = Query(None, description="政策类型"),
    exclude_policy_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """检查政策是否重复"""
    try:
        service = PolicyService(session)
        result = await service.check_duplicate(
            region_code=region_code,
            effective_start=effective_start,
            policy_type=policy_type,
            exclude_policy_id=exclude_policy_id
        )
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"Error checking duplicate: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{policy_id}", response_model=PolicyResponse)
async def get_policy(
    policy_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """获取政策详情（支持所有类型）"""
    try:
        service = PolicyService(session)
        data = await service.get_policy_with_extension(policy_id)

        if not data:
            raise HTTPException(status_code=404, detail="政策不存在")

        policy = data["policy"]
        ext = data.get("extension")
        type_data = data.get("type_data")

        region_name = await get_region_name(session, policy.region_code)

        # 向后兼容：如果是社保类型，同时填充 social_insurance
        si_response = None
        if policy.policy_type in ("social_insurance", "social_insurance_base") and ext:
            si_response = PolicySocialInsuranceResponse(
                si_upper_limit=ext.si_upper_limit,
                si_lower_limit=ext.si_lower_limit,
                si_avg_salary_ref=ext.si_avg_salary_ref,
                is_retroactive=ext.is_retroactive == 1,
                retroactive_start=ext.retroactive_start,
                retroactive_months=ext.retroactive_months,
                coverage_types=json.loads(ext.coverage_types) if ext.coverage_types else [],
                change_rate_upper=float(ext.change_rate_upper) if ext.change_rate_upper else None,
                change_rate_lower=float(ext.change_rate_lower) if ext.change_rate_lower else None,
                special_notes=ext.special_notes
            )

        return PolicyResponse(
            policy_id=policy.policy_id,
            policy_type=policy.policy_type,
            title=policy.title,
            region_code=policy.region_code,
            region_name=region_name,
            source_attachments=policy.source_attachments,
            published_at=policy.published_at,
            effective_start=policy.effective_start,
            effective_end=policy.effective_end,
            policy_year=policy.policy_year,
            status=policy.status,
            version=policy.version,
            type_data=type_data,
            social_insurance=si_response,
            created_at=policy.created_at,
            updated_at=policy.updated_at,
            created_by=policy.created_by,
            reviewed_by=policy.reviewed_by
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting policy {policy_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def create_policy(
    request: Request,
    data: PolicyCreate,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """
    创建政策（人工入口，支持多类型）

    通过 policy_type 字段指定政策类型，type_data 中传入对应的扩展数据。
    为兼容旧接口，仍然支持使用 social_insurance 字段。
    """
    try:
        service = PolicyService(session)

        # 检查重复
        duplicate_check = await service.check_duplicate(
            region_code=data.region_code,
            effective_start=data.effective_start,
            policy_type=data.policy_type
        )

        if duplicate_check.get("is_duplicate"):
            logger.warning(f"Potential duplicate policy: {duplicate_check}")

        # 人工提交直接生效
        policy = await service.create_policy(
            data=data,
            created_by=current_user.user_id,
            request_id=getattr(request.state, "request_id", None),
            status="active"
        )

        logger.info(f"Policy created and activated: {policy.policy_id} type={data.policy_type} by {current_user.user_id}")

        return {
            "success": True,
            "policy_id": policy.policy_id,
            "policy_type": policy.policy_type,
            "status": "active",
            "version": policy.version,
            "duplicate_warning": duplicate_check if duplicate_check.get("is_duplicate") else None
        }

    except ValueError as e:
        logger.warning(f"Validation error creating policy: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating policy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{policy_id}")
async def update_policy(
    policy_id: str,
    data: PolicyUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """更新政策"""
    try:
        service = PolicyService(session)

        policy = await service.update_policy(
            policy_id=policy_id,
            data=data,
            updated_by=current_user.user_id,
            request_id=getattr(request.state, "request_id", None)
        )

        logger.info(f"Policy updated: {policy_id} to version {policy.version} by {current_user.user_id}")

        return {
            "success": True,
            "policy_id": policy.policy_id,
            "version": policy.version,
            "updated_at": policy.updated_at
        }

    except ValueError as e:
        logger.warning(f"Validation error updating policy {policy_id}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating policy {policy_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{policy_id}")
async def delete_policy(
    policy_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """软删除政策"""
    try:
        service = PolicyService(session)

        await service.delete_policy(
            policy_id=policy_id,
            deleted_by=current_user.user_id,
            request_id=getattr(request.state, "request_id", None)
        )

        logger.info(f"Policy deleted: {policy_id} by {current_user.user_id}")

        return {"success": True, "message": "政策已删除"}

    except ValueError as e:
        logger.warning(f"Validation error deleting policy {policy_id}: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting policy {policy_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{policy_id}/versions")
async def get_policy_versions(
    policy_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """获取政策版本历史"""
    try:
        from app.models.version import PolicyVersion

        policy_result = await session.execute(
            select(Policy.policy_id).where(Policy.policy_id == policy_id)
        )
        if not policy_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="政策不存在")

        result = await session.execute(
            select(PolicyVersion)
            .where(PolicyVersion.policy_id == policy_id)
            .order_by(PolicyVersion.version_number.desc())
        )
        versions = result.scalars().all()

        return {
            "success": True,
            "data": [
                {
                    "version_id": v.version_id,
                    "version_number": v.version_number,
                    "change_type": v.change_type,
                    "changed_fields": json.loads(v.changed_fields) if v.changed_fields else [],
                    "change_reason": v.change_reason,
                    "changed_by": v.changed_by,
                    "changed_at": v.changed_at
                }
                for v in versions
            ],
            "total": len(versions)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting policy versions {policy_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{policy_id}/activate")
async def activate_policy(
    policy_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """激活政策"""
    try:
        service = PolicyService(session)

        policy = await service.get_policy_by_id(policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="政策不存在")

        if policy.status not in ["pending_review", "draft"]:
            raise HTTPException(status_code=400, detail=f"无法激活状态为 {policy.status} 的政策")

        policy.status = "active"
        policy.reviewed_by = current_user.user_id
        policy.reviewed_at = datetime.utcnow().isoformat()

        await session.commit()

        logger.info(f"Policy activated: {policy_id} by {current_user.user_id}")

        return {
            "success": True,
            "policy_id": policy_id,
            "status": "active"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating policy {policy_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{policy_id}/revoke")
async def revoke_policy(
    policy_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """撤销政策"""
    try:
        service = PolicyService(session)

        policy = await service.get_policy_by_id(policy_id)
        if not policy:
            raise HTTPException(status_code=404, detail="政策不存在")

        if policy.status != "active":
            raise HTTPException(status_code=400, detail=f"只能撤销生效中的政策")

        policy.status = "revoked"
        policy.updated_at = datetime.utcnow().isoformat()

        await session.commit()

        logger.info(f"Policy revoked: {policy_id} by {current_user.user_id}")

        return {
            "success": True,
            "policy_id": policy_id,
            "status": "revoked"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking policy {policy_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
