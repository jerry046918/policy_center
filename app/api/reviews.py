"""审核中心 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, case
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
import json

from app.database import get_session
from app.models.review import ReviewQueue
from app.models.policy import Policy, PolicySocialInsurance
from app.models.region import Region
from app.schemas.review import (
    ReviewUpdate,
    ReviewDetailResponse,
    ReviewListResponse
)
from app.schemas.common import PaginatedResponse
from app.api.auth import get_current_user, UserAuth
from app.services.review_service import ReviewService
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


class ApproveRequest(BaseModel):
    notes: Optional[str] = None


class ApproveWithOverrideRequest(BaseModel):
    """带覆盖的审核通过请求"""
    # 审核人最终决定，可覆盖提交方判断
    final_action: Optional[str] = None  # "new", "update", "new_version"
    # 如果是 update 或 new_version，需要指定目标政策
    final_target_policy_id: Optional[str] = None
    # 审核人修改后的数据
    modified_data: Optional[dict] = None
    notes: Optional[str] = None


class RejectRequest(BaseModel):
    reason: str


class ClarificationRequest(BaseModel):
    request: str


class ResubmitRequest(BaseModel):
    updated_data: dict
    notes: str


class ReleaseRequest(BaseModel):
    reason: Optional[str] = None


@router.get("", response_model=PaginatedResponse[ReviewListResponse])
async def list_reviews(
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    region_code: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """审核列表（看板数据）"""
    query = select(ReviewQueue)

    if status:
        # 支持多状态筛选
        statuses = status.split(",")
        if len(statuses) == 1:
            query = query.where(ReviewQueue.status == status)
        else:
            query = query.where(ReviewQueue.status.in_(statuses))

    if priority:
        query = query.where(ReviewQueue.priority == priority)
    if risk_level:
        query = query.where(ReviewQueue.risk_level == risk_level)

    # 地区筛选（需要解析 JSON）
    if region_code:
        query = query.where(
            ReviewQueue.submitted_data.contains(f'"region_code": "{region_code}"')
        )

    # 统计
    count_query = select(func.count()).select_from(query.subquery())
    total = await session.scalar(count_query)

    # 排序：优先级 > SLA > 提交时间
    priority_order = case(
        (ReviewQueue.priority == "urgent", 0),
        (ReviewQueue.priority == "high", 1),
        (ReviewQueue.priority == "normal", 2),
        (ReviewQueue.priority == "low", 3),
        else_=4
    )

    query = query.order_by(
        priority_order.asc(),
        ReviewQueue.sla_deadline.asc().nulls_last(),
        ReviewQueue.submitted_at.asc()
    )
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(query)
    reviews = result.scalars().all()

    items = []
    for r in reviews:
        submitted_data = json.loads(r.submitted_data) if r.submitted_data else {}

        # 计算 SLA 剩余时间
        sla_remaining = None
        sla_status = "normal"
        if r.sla_deadline:
            try:
                deadline = datetime.fromisoformat(r.sla_deadline)
                sla_remaining = (deadline - datetime.utcnow()).total_seconds() / 3600
                if sla_remaining < 0:
                    sla_status = "overdue"
                elif sla_remaining < 4:
                    sla_status = "warning"
            except ValueError:
                pass

        # 获取地区名称
        region_name = None
        region_code_val = submitted_data.get("region_code")
        if region_code_val:
            region_result = await session.execute(
                select(Region.name).where(Region.code == region_code_val)
            )
            region_name = region_result.scalar_one_or_none()

        items.append(ReviewListResponse(
            review_id=r.review_id,
            policy_title=submitted_data.get("title", ""),
            region_code=submitted_data.get("region_code", ""),
            region_name=region_name,
            status=r.status,
            priority=r.priority,
            risk_level=r.risk_level,
            risk_tags=json.loads(r.risk_tags) if r.risk_tags else [],
            submitted_at=r.submitted_at,
            submitted_by=r.submitted_by,
            sla_deadline=r.sla_deadline,
            sla_remaining_hours=max(0, sla_remaining) if sla_remaining else None,
            sla_status=sla_status,
            claimed_by=r.claimed_by,
            # 新增字段
            submit_type=r.submit_type,
            existing_policy_id=r.existing_policy_id
        ))

    return PaginatedResponse(
        success=True,
        data=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total > 0 else 0
    )


@router.get("/stats/summary")
async def get_review_stats(
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """获取审核统计"""
    service = ReviewService(session)
    stats = await service.get_review_stats()

    return {
        "success": True,
        "data": stats
    }


@router.get("/my/tasks")
async def get_my_review_tasks(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """获取当前用户的审核任务"""
    query = select(ReviewQueue).where(
        or_(
            ReviewQueue.claimed_by == current_user.user_id,
            ReviewQueue.reviewer_id == current_user.user_id
        )
    )

    if status:
        query = query.where(ReviewQueue.status == status)

    # 统计
    count_query = select(func.count()).select_from(query.subquery())
    total = await session.scalar(count_query)

    # 分页
    query = query.order_by(ReviewQueue.reviewed_at.desc().nulls_last())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(query)
    reviews = result.scalars().all()

    items = []
    for r in reviews:
        submitted_data = json.loads(r.submitted_data) if r.submitted_data else {}
        items.append({
            "review_id": r.review_id,
            "policy_title": submitted_data.get("title", ""),
            "status": r.status,
            "submitted_at": r.submitted_at,
            "reviewed_at": r.reviewed_at
        })

    return {
        "success": True,
        "data": items,
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.get("/{review_id}", response_model=ReviewDetailResponse)
async def get_review(
    review_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """获取审核详情"""
    service = ReviewService(session)

    try:
        review_data = await service.get_review_with_diff(review_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    review = review_data["review"]
    submitted_data = review_data["submitted_data"]
    diff = review_data["diff"]

    # 获取地区名称
    region_name = None
    region_code = submitted_data.get("region_code")
    if region_code:
        region_result = await session.execute(
            select(Region.name).where(Region.code == region_code)
        )
        region_name = region_result.scalar_one_or_none()

    return ReviewDetailResponse(
        review_id=review.review_id,
        policy_id=review.policy_id,
        status=review.status,
        priority=review.priority,
        submitted_data=submitted_data,
        raw_evidence=json.loads(review.raw_evidence) if review.raw_evidence else None,
        ai_validation=json.loads(review.ai_validation) if review.ai_validation else None,
        risk_level=review.risk_level,
        risk_tags=json.loads(review.risk_tags) if review.risk_tags else [],
        submitted_at=review.submitted_at,
        submitted_by=review.submitted_by,
        sla_deadline=review.sla_deadline,
        claimed_by=review.claimed_by,
        claimed_at=review.claimed_at,
        reviewer_notes=review.reviewer_notes,
        diff=diff,
        region_name=region_name,
        # 新增字段
        submit_type=review.submit_type,
        existing_policy_id=review.existing_policy_id,
        change_description=review.change_description,
        final_action=review.final_action,
        final_target_policy_id=review.final_target_policy_id,
        reviewer_modified_data=json.loads(review.reviewer_modified_data) if review.reviewer_modified_data else None
    )


@router.post("/{review_id}/claim")
async def claim_review(
    review_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """认领审核任务"""
    service = ReviewService(session)

    try:
        await service.claim_review(review_id, current_user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"success": True, "message": "任务已认领"}


@router.post("/{review_id}/release")
async def release_review(
    review_id: str,
    request: ReleaseRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """释放已认领的审核任务"""
    service = ReviewService(session)

    try:
        await service.release_review(
            review_id=review_id,
            user_id=current_user.user_id,
            reason=request.reason
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"success": True, "message": "任务已释放"}


@router.post("/{review_id}/approve")
async def approve_review(
    review_id: str,
    request: ApproveRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """通过审核"""
    service = ReviewService(session)

    try:
        policy = await service.approve_review(
            review_id=review_id,
            reviewer_id=current_user.user_id,
            notes=request.notes
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # 捕获数据库约束错误等其他异常
        logger.error(f"Approve review failed: {e}")
        error_msg = str(e)
        if "UNIQUE constraint" in error_msg:
            raise HTTPException(status_code=400, detail=f"数据约束冲突：{error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"操作失败：{error_msg}")

    return {
        "success": True,
        "policy_id": policy.policy_id,
        "message": "政策已发布"
    }


@router.post("/{review_id}/approve-with-override")
async def approve_review_with_override(
    review_id: str,
    request: ApproveWithOverrideRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """
    通过审核（带覆盖选项）

    审核人可以使用此接口覆盖提交方的判断：
    - final_action: "new"(新建政策), "update"(更新现有政策), "new_version"(创建新版本)
    - final_target_policy_id: 当 action 为 update 或 new_version 时，指定目标政策
    - modified_data: 审核人修改后的政策数据
    - notes: 审核备注

    场景示例：
    1. 提交方认为是新政策，审核人判断是更新：final_action="update", final_target_policy_id="xxx"
    2. 提交方认为是更新，审核人判断是新政策：final_action="new"
    3. 审核人修改了数据后通过：modified_data={...}
    """
    service = ReviewService(session)

    # 验证 final_action
    if request.final_action and request.final_action not in ["new", "update", "new_version"]:
        raise HTTPException(status_code=400, detail="final_action 必须是 'new', 'update' 或 'new_version'")

    # 如果是 update 或 new_version，需要提供 target_policy_id
    if request.final_action in ["update", "new_version"] and not request.final_target_policy_id:
        raise HTTPException(status_code=400, detail=f"final_action={request.final_action} 时必须提供 final_target_policy_id")

    try:
        policy = await service.approve_review(
            review_id=review_id,
            reviewer_id=current_user.user_id,
            notes=request.notes,
            final_action=request.final_action,
            modified_data=request.modified_data,
            final_target_policy_id=request.final_target_policy_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # 捕获数据库约束错误等其他异常
        logger.error(f"Approve review with override failed: {e}")
        error_msg = str(e)
        if "UNIQUE constraint" in error_msg:
            raise HTTPException(status_code=400, detail=f"数据约束冲突：{error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"操作失败：{error_msg}")

    return {
        "success": True,
        "policy_id": policy.policy_id,
        "action_taken": request.final_action or "default",
        "message": "政策已发布"
    }


@router.post("/{review_id}/reject")
async def reject_review(
    review_id: str,
    request: RejectRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """拒绝审核"""
    service = ReviewService(session)

    try:
        await service.reject_review(
            review_id=review_id,
            reviewer_id=current_user.user_id,
            reason=request.reason
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"success": True, "message": "已拒绝"}


@router.post("/{review_id}/clarify")
async def request_clarification(
    review_id: str,
    request: ClarificationRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """请求补充材料"""
    service = ReviewService(session)

    try:
        await service.request_clarification(
            review_id=review_id,
            reviewer_id=current_user.user_id,
            clarification_request=request.request
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"success": True, "message": "已请求补充材料"}


@router.post("/{review_id}/resubmit")
async def resubmit_review(
    review_id: str,
    request: ResubmitRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """补充材料后重新提交"""
    service = ReviewService(session)

    try:
        await service.resubmit_with_clarification(
            review_id=review_id,
            updated_data=request.updated_data,
            clarification_notes=request.notes
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"success": True, "message": "已重新提交"}
