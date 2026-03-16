"""系统管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
from datetime import datetime
import secrets
import hashlib
import json
import logging
import uuid

from app.database import get_session
from app.models.agent import AgentCredential, User
from app.models.region import Region
from app.api.auth import get_current_user, UserAuth, hash_password
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


class AgentCreate(BaseModel):
    agent_name: str
    description: Optional[str] = None


class AgentResponse(BaseModel):
    agent_id: str
    agent_name: str
    api_key: Optional[str] = None  # 仅创建时返回
    api_key_prefix: str
    description: Optional[str]
    is_active: bool
    last_used_at: Optional[str]
    created_at: str


# ==================== 用户管理 Schemas ====================

class UserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    role: str = "staff"


class UserResponse(BaseModel):
    user_id: str
    username: str
    email: Optional[str]
    display_name: Optional[str]
    role: str
    is_active: bool
    last_login_at: Optional[str]
    created_at: str


class ToggleStatusRequest(BaseModel):
    is_active: bool


class ResetPasswordRequest(BaseModel):
    new_password: str


# ==================== 用户管理 ====================

@router.get("/users", response_model=dict)
async def list_users(
    is_active: Optional[int] = Query(None),
    role: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """用户列表"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")

    query = select(User)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    if role:
        query = query.where(User.role == role)

    count_query = select(func.count()).select_from(query.subquery())
    total = await session.scalar(count_query)

    query = query.order_by(User.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(query)
    users = result.scalars().all()

    return {
        "success": True,
        "data": [
            {
                "user_id": u.user_id,
                "username": u.username,
                "email": u.email,
                "display_name": u.display_name,
                "role": u.role,
                "is_active": u.is_active == 1,
                "last_login_at": u.last_login_at,
                "created_at": u.created_at
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.post("/users", response_model=UserResponse)
async def create_user(
    data: UserCreate,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """创建用户"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")

    # 检查用户名是否已存在
    existing = await session.execute(select(User).where(User.username == data.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")

    # 检查邮箱是否已存在
    if data.email:
        existing_email = await session.execute(select(User).where(User.email == data.email))
        if existing_email.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already exists")

    user = User(
        user_id=str(uuid.uuid4()),
        username=data.username,
        password_hash=hash_password(data.password),
        email=data.email,
        display_name=data.display_name,
        role=data.role,
        is_active=1,
        created_at=datetime.utcnow().isoformat()
    )

    session.add(user)
    await session.commit()
    await session.refresh(user)

    return UserResponse(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=True,
        last_login_at=None,
        created_at=user.created_at
    )


@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """获取用户详情"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")

    result = await session.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "success": True,
        "data": {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "is_active": user.is_active == 1,
            "last_login_at": user.last_login_at,
            "created_at": user.created_at
        }
    }


@router.patch("/users/{user_id}/status")
async def toggle_user_status(
    user_id: str,
    data: ToggleStatusRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """启用/禁用用户"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")

    result = await session.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 防止禁用自己
    if user.user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    user.is_active = 1 if data.is_active else 0
    await session.commit()

    return {
        "success": True,
        "message": f"User {'activated' if data.is_active else 'deactivated'}"
    }


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    data: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """管理员重置用户密码"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")

    result = await session.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = hash_password(data.new_password)
    await session.commit()

    return {"success": True, "message": "Password reset successfully"}


# ==================== Agent 管理 ====================

@router.get("/agents", response_model=dict)
async def list_agents(
    is_active: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """Agent 列表"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")

    query = select(AgentCredential)
    if is_active is not None:
        query = query.where(AgentCredential.is_active == is_active)

    count_query = select(func.count()).select_from(query.subquery())
    total = await session.scalar(count_query)

    query = query.order_by(AgentCredential.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await session.execute(query)
    agents = result.scalars().all()

    return {
        "success": True,
        "data": [
            {
                "agent_id": a.agent_id,
                "agent_name": a.agent_name,
                "api_key_prefix": a.api_key_prefix,
                "description": a.description,
                "is_active": a.is_active == 1,
                "last_used_at": a.last_used_at,
                "created_at": a.created_at
            }
            for a in agents
        ],
        "total": total,
        "page": page,
        "page_size": page_size
    }


@router.post("/agents", response_model=AgentResponse)
async def create_agent(
    data: AgentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """创建 Agent 凭据"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")

    # 生成 API Key
    api_key = f"pk_live_{secrets.token_hex(24)}"
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    api_key_prefix = api_key[:12]

    agent = AgentCredential(
        agent_name=data.agent_name,
        api_key_hash=api_key_hash,
        api_key_prefix=api_key_prefix,
        description=data.description,
        created_by=current_user.user_id
    )

    session.add(agent)
    await session.commit()
    await session.refresh(agent)

    return AgentResponse(
        agent_id=agent.agent_id,
        agent_name=agent.agent_name,
        api_key=api_key,  # 仅此一次返回明文
        api_key_prefix=agent.api_key_prefix,
        description=agent.description,
        is_active=True,
        last_used_at=None,
        created_at=agent.created_at
    )


@router.delete("/agents/{agent_id}")
async def delete_agent(
    agent_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """删除 API Key"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")

    result = await session.execute(
        select(AgentCredential).where(AgentCredential.agent_id == agent_id)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="API Key not found")

    await session.delete(agent)
    await session.commit()

    return {"success": True, "message": "API Key deleted"}


@router.patch("/agents/{agent_id}/status")
async def toggle_agent_status(
    agent_id: str,
    data: ToggleStatusRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """启用/禁用 API Key"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")

    result = await session.execute(
        select(AgentCredential).where(AgentCredential.agent_id == agent_id)
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="API Key not found")

    agent.is_active = 1 if data.is_active else 0
    await session.commit()

    return {
        "success": True,
        "message": f"API Key {'activated' if data.is_active else 'deactivated'}"
    }


# ==================== 地区管理 ====================

@router.get("/regions")
async def list_regions(
    parent_code: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """地区列表"""
    query = select(Region).where(Region.is_active == 1)

    if parent_code:
        query = query.where(Region.parent_code == parent_code)
    if level:
        query = query.where(Region.level == level)

    query = query.order_by(Region.code)

    result = await session.execute(query)
    regions = result.scalars().all()

    return {
        "success": True,
        "data": [
            {
                "code": r.code,
                "name": r.name,
                "level": r.level,
                "parent_code": r.parent_code,
                "full_path": r.full_path,
                "min_wage": r.min_wage,
                "avg_salary": r.avg_salary
            }
            for r in regions
        ]
    }


class RegionCreate(BaseModel):
    code: str
    name: str
    level: str
    parent_code: Optional[str] = None
    min_wage: Optional[int] = None
    avg_salary: Optional[int] = None


@router.post("/regions")
async def create_region(
    data: RegionCreate,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """新增地区"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")

    # 检查编码是否已存在
    existing = await session.execute(select(Region).where(Region.code == data.code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="地区编码已存在")

    # 构建完整路径
    full_path = data.name
    path_materialized = data.code
    if data.parent_code:
        parent = await session.execute(select(Region).where(Region.code == data.parent_code))
        parent_region = parent.scalar_one_or_none()
        if parent_region:
            full_path = f"{parent_region.full_path}/{data.name}"
            path_materialized = f"{parent_region.path_materialized}.{data.code}"

    region = Region(
        code=data.code,
        name=data.name,
        level=data.level,
        parent_code=data.parent_code,
        full_path=full_path,
        path_materialized=path_materialized,
        min_wage=data.min_wage,
        avg_salary=data.avg_salary
    )

    session.add(region)
    await session.commit()

    return {
        "success": True,
        "message": "地区创建成功",
        "data": {
            "code": region.code,
            "name": region.name,
            "level": region.level,
            "parent_code": region.parent_code,
            "full_path": region.full_path
        }
    }


@router.post("/regions/init")
async def init_regions(
    force: bool = Query(False, description="强制重新初始化，清除现有数据"),
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """初始化地区数据（全国31个省级行政区及下属地级市）"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")

    # 检查是否已初始化
    result = await session.execute(select(func.count()).select_from(Region))
    count = result.scalar()

    if count > 0 and not force:
        return {"success": True, "message": f"已存在 {count} 个地区，如需重新初始化请使用 force=true 参数"}

    # 如果强制初始化，先清除现有数据
    if count > 0 and force:
        await session.execute(Region.__table__.delete())
        await session.commit()
        logger.info(f"Cleared {count} existing regions for re-initialization")

    import os

    # 从 JSON 文件加载地区数据
    data_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "regions.json")

    if not os.path.exists(data_file):
        # 如果文件不存在，使用基础数据
        regions_data = _get_basic_regions()
    else:
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        regions_data = _build_regions_from_json(data)

    # 批量插入
    for region_data in regions_data:
        region = Region(**region_data)
        session.add(region)

    await session.commit()

    return {"success": True, "message": f"成功初始化 {len(regions_data)} 个地区", "count": len(regions_data)}


def _get_basic_regions():
    """获取基础地区数据（兜底）"""
    return [
        {"code": "000000", "name": "中国", "level": "country", "parent_code": None, "full_path": "中国", "path_materialized": "000000"},
        {"code": "110000", "name": "北京市", "level": "province", "parent_code": "000000", "full_path": "中国/北京市", "path_materialized": "000000.110000"},
        {"code": "120000", "name": "天津市", "level": "province", "parent_code": "000000", "full_path": "中国/天津市", "path_materialized": "000000.120000"},
        {"code": "310000", "name": "上海市", "level": "province", "parent_code": "000000", "full_path": "中国/上海市", "path_materialized": "000000.310000"},
        {"code": "440000", "name": "广东省", "level": "province", "parent_code": "000000", "full_path": "中国/广东省", "path_materialized": "000000.440000"},
        {"code": "440300", "name": "深圳市", "level": "city", "parent_code": "440000", "full_path": "中国/广东省/深圳市", "path_materialized": "000000.440000.440300"},
        {"code": "500000", "name": "重庆市", "level": "province", "parent_code": "000000", "full_path": "中国/重庆市", "path_materialized": "000000.500000"},
    ]


def _build_regions_from_json(data: dict) -> list:
    """从 JSON 数据构建地区列表"""
    regions = []

    # 添加国家节点
    regions.append({
        "code": "000000",
        "name": "中国",
        "level": "country",
        "parent_code": None,
        "full_path": "中国",
        "path_materialized": "000000"
    })

    # 添加省份和城市
    for province in data.get("provinces", []):
        province_code = province["code"]
        province_name = province["name"]

        # 添加省份
        regions.append({
            "code": province_code,
            "name": province_name,
            "level": "province",
            "parent_code": "000000",
            "full_path": f"中国/{province_name}",
            "path_materialized": f"000000.{province_code}"
        })

        # 添加该省份下的城市
        cities = data.get("cities", {}).get(province_code, [])
        for city in cities:
            city_code = city["code"]
            city_name = city["name"]
            regions.append({
                "code": city_code,
                "name": city_name,
                "level": "city",
                "parent_code": province_code,
                "full_path": f"中国/{province_name}/{city_name}",
                "path_materialized": f"000000.{province_code}.{city_code}"
            })

    return regions


# ==================== 系统状态 ====================

@router.get("/stats")
async def get_system_stats(
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """系统统计"""
    from app.models.policy import Policy
    from app.models.review import ReviewQueue

    # 政策统计
    policy_total = await session.scalar(select(func.count()).select_from(Policy).where(Policy.deleted_at.is_(None)))
    active_policies = await session.scalar(select(func.count()).select_from(Policy).where(Policy.status == "active"))

    # 审核统计
    pending_reviews = await session.scalar(select(func.count()).select_from(ReviewQueue).where(ReviewQueue.status == "pending"))

    # 地区覆盖
    covered_regions = await session.scalar(
        select(func.count(func.distinct(Policy.region_code)))
        .where(Policy.status == "active")
    )

    return {
        "success": True,
        "data": {
            "policies": {
                "total": policy_total,
                "active": active_policies
            },
            "reviews": {
                "pending": pending_reviews
            },
            "coverage": {
                "regions_covered": covered_regions,
                "total_regions": 31
            }
        }
    }
