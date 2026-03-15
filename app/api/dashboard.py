"""数据看板 API"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, distinct
from typing import Dict, Any, List
from datetime import datetime, timedelta
from pydantic import BaseModel

from app.database import get_session
from app.models.policy import Policy, PolicySocialInsurance
from app.models.review import ReviewQueue
from app.models.region import Region
from app.api.auth import get_current_user, UserAuth

router = APIRouter()


class DashboardStats(BaseModel):
    """看板统计数据"""
    total_policies: int
    active_policies: int
    pending_reviews: int
    regions_covered: int
    total_regions: int
    sla_overdue: int
    sla_warning: int


class RecentPolicy(BaseModel):
    """最近政策"""
    policy_id: str
    title: str
    region_name: str
    region_code: str
    effective_start: str
    status: str
    si_upper_limit: int
    si_lower_limit: int


class PendingReview(BaseModel):
    """待审核项"""
    review_id: str
    policy_title: str
    region_name: str
    risk_level: str
    priority: str
    submitted_at: str
    sla_remaining_hours: float
    sla_status: str


class RetroactivePolicy(BaseModel):
    """追溯政策预警"""
    policy_id: str
    title: str
    region_name: str
    effective_start: str
    retroactive_start: str
    retroactive_months: int
    si_upper_limit: int
    si_lower_limit: int


class DashboardResponse(BaseModel):
    """看板响应"""
    stats: DashboardStats
    recent_policies: List[RecentPolicy]
    pending_reviews: List[PendingReview]
    retroactive_policies: List[RetroactivePolicy]


@router.get("", response_model=DashboardResponse)
async def get_dashboard(
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """获取看板数据"""
    now = datetime.utcnow()

    # 1. 统计数据
    # 政策总数
    total_policies = await session.scalar(
        select(func.count()).select_from(Policy)
    )

    # 生效政策数
    active_policies = await session.scalar(
        select(func.count()).select_from(Policy).where(Policy.status == "active")
    )

    # 待审核数
    pending_reviews_count = await session.scalar(
        select(func.count()).select_from(ReviewQueue).where(
            ReviewQueue.status.in_(["pending", "claimed"])
        )
    )

    # 已覆盖地区数（有政策的城市）
    regions_with_policies = await session.execute(
        select(distinct(Policy.region_code)).where(Policy.status == "active")
    )
    region_codes = [r[0] for r in regions_with_policies.fetchall()]
    regions_covered = len(region_codes)

    # 总地区数
    total_regions = await session.scalar(
        select(func.count()).select_from(Region).where(Region.level == 2)
    )

    # SLA 统计
    sla_result = await session.execute(
        select(ReviewQueue).where(
            ReviewQueue.status.in_(["pending", "claimed"])
        )
    )
    pending_reviews_all = sla_result.scalars().all()

    sla_overdue = 0
    sla_warning = 0
    for r in pending_reviews_all:
        if r.sla_deadline:
            try:
                deadline = datetime.fromisoformat(r.sla_deadline)
                remaining = (deadline - now).total_seconds() / 3600
                if remaining < 0:
                    sla_overdue += 1
                elif remaining < 4:
                    sla_warning += 1
            except ValueError:
                pass

    stats = DashboardStats(
        total_policies=total_policies or 0,
        active_policies=active_policies or 0,
        pending_reviews=pending_reviews_count or 0,
        regions_covered=regions_covered,
        total_regions=total_regions or 343,
        sla_overdue=sla_overdue,
        sla_warning=sla_warning
    )

    # 2. 最近发布的政策（最近10条）
    recent_result = await session.execute(
        select(Policy, PolicySocialInsurance)
        .join(PolicySocialInsurance, Policy.policy_id == PolicySocialInsurance.policy_id)
        .where(Policy.status == "active")
        .order_by(Policy.created_at.desc())
        .limit(10)
    )
    recent_rows = recent_result.fetchall()

    recent_policies = []
    for policy, si in recent_rows:
        # 获取地区名称
        region_name = await session.scalar(
            select(Region.name).where(Region.code == policy.region_code)
        )

        recent_policies.append(RecentPolicy(
            policy_id=policy.policy_id,
            title=policy.title,
            region_name=region_name or policy.region_code,
            region_code=policy.region_code,
            effective_start=policy.effective_start,
            status=policy.status,
            si_upper_limit=si.si_upper_limit,
            si_lower_limit=si.si_lower_limit
        ))

    # 3. 待审核队列（优先级排序，最多10条）
    pending_result = await session.execute(
        select(ReviewQueue)
        .where(ReviewQueue.status == "pending")
        .order_by(
            ReviewQueue.priority.desc(),
            ReviewQueue.sla_deadline.asc().nulls_last(),
            ReviewQueue.submitted_at.desc()
        )
        .limit(10)
    )
    pending_reviews = pending_result.scalars().all()

    pending_list = []
    for r in pending_reviews:
        import json
        submitted_data = json.loads(r.submitted_data) if r.submitted_data else {}

        # 获取地区名称
        region_code = submitted_data.get("region_code")
        region_name = await session.scalar(
            select(Region.name).where(Region.code == region_code)
        ) if region_code else None

        # 计算 SLA
        sla_remaining = None
        sla_status = "normal"
        if r.sla_deadline:
            try:
                deadline = datetime.fromisoformat(r.sla_deadline)
                sla_remaining = (deadline - now).total_seconds() / 3600
                if sla_remaining < 0:
                    sla_status = "overdue"
                elif sla_remaining < 4:
                    sla_status = "warning"
            except ValueError:
                pass

        pending_list.append(PendingReview(
            review_id=r.review_id,
            policy_title=submitted_data.get("title", ""),
            region_name=region_name or region_code or "",
            risk_level=r.risk_level,
            priority=r.priority,
            submitted_at=r.submitted_at,
            sla_remaining_hours=max(0, sla_remaining) if sla_remaining else 0,
            sla_status=sla_status
        ))

    # 4. 追溯政策预警（有追溯生效的政策）
    retro_result = await session.execute(
        select(Policy, PolicySocialInsurance)
        .join(PolicySocialInsurance, Policy.policy_id == PolicySocialInsurance.policy_id)
        .where(
            Policy.status == "active",
            PolicySocialInsurance.is_retroactive == 1
        )
        .order_by(Policy.effective_start.desc())
        .limit(10)
    )
    retro_rows = retro_result.fetchall()

    retroactive_policies = []
    for policy, si in retro_rows:
        region_name = await session.scalar(
            select(Region.name).where(Region.code == policy.region_code)
        )

        retroactive_policies.append(RetroactivePolicy(
            policy_id=policy.policy_id,
            title=policy.title,
            region_name=region_name or policy.region_code,
            effective_start=policy.effective_start,
            retroactive_start=si.retroactive_start or "",
            retroactive_months=si.retroactive_months or 0,
            si_upper_limit=si.si_upper_limit,
            si_lower_limit=si.si_lower_limit
        ))

    return DashboardResponse(
        stats=stats,
        recent_policies=recent_policies,
        pending_reviews=pending_list,
        retroactive_policies=retroactive_policies
    )
