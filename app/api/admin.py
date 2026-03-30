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
from app.database import _build_regions_from_json
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
    password: str = Field(..., min_length=8)
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
    new_password: str = Field(..., min_length=8)


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


# ==================== 政策类型管理 ====================

class PolicyTypeCreate(BaseModel):
    type_code: str
    type_name: str
    description: Optional[str] = None
    field_schema: dict = {}
    validation_rules: list = []
    example_data: dict = {}
    icon: Optional[str] = None
    sort_order: int = 0


class PolicyTypeUpdate(BaseModel):
    type_name: Optional[str] = None
    description: Optional[str] = None
    field_schema: Optional[dict] = None
    validation_rules: Optional[list] = None
    example_data: Optional[dict] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


@router.get("/policy-types")
async def list_policy_types(
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """
    获取所有政策类型定义（包括内置和动态）

    返回数据库中的完整类型信息，供管理后台展示和编辑。
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")

    from app.models.policy_type import PolicyTypeDefinition
    from app.models.policy import Policy

    result = await session.execute(
        select(PolicyTypeDefinition).order_by(
            PolicyTypeDefinition.sort_order.asc(),
            PolicyTypeDefinition.created_at.asc()
        )
    )
    types = result.scalars().all()

    # 统计每种类型的使用量
    data = []
    for t in types:
        count_result = await session.scalar(
            select(func.count()).select_from(Policy).where(
                Policy.policy_type == t.type_code,
                Policy.deleted_at.is_(None)
            )
        )

        data.append({
            "type_code": t.type_code,
            "type_name": t.type_name,
            "description": t.description,
            "extension_table": t.extension_table,
            "field_schema": json.loads(t.field_schema) if t.field_schema else {},
            "validation_rules": json.loads(t.validation_rules) if t.validation_rules else [],
            "example_data": json.loads(t.example_data) if t.example_data else {},
            "is_builtin": t.is_builtin == 1,
            "is_active": t.is_active == 1,
            "sort_order": t.sort_order,
            "icon": t.icon,
            "policy_count": count_result or 0,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        })

    return {"success": True, "data": data, "total": len(data)}


@router.post("/policy-types")
async def create_policy_type(
    data: PolicyTypeCreate,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """
    创建新的动态政策类型

    管理员可以通过此接口定义新的政策类型，指定其字段结构、验证规则和示例数据。
    动态类型的扩展数据存储在 policies.extension_data JSON 字段中。
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")

    from app.models.policy_type import PolicyTypeDefinition

    # 检查编码格式
    if not data.type_code or not data.type_code.replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="type_code 只能包含字母、数字和下划线")

    # 检查编码是否已存在
    result = await session.execute(
        select(PolicyTypeDefinition).where(
            PolicyTypeDefinition.type_code == data.type_code
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"类型编码 '{data.type_code}' 已存在")

    now = datetime.utcnow().isoformat()
    td = PolicyTypeDefinition(
        type_code=data.type_code,
        type_name=data.type_name,
        description=data.description,
        extension_table=None,  # 动态类型无专用表
        field_schema=json.dumps(data.field_schema, ensure_ascii=False),
        validation_rules=json.dumps(data.validation_rules, ensure_ascii=False),
        example_data=json.dumps(data.example_data, ensure_ascii=False),
        is_builtin=0,
        is_active=1,
        sort_order=data.sort_order,
        icon=data.icon,
        created_at=now,
        updated_at=now,
    )

    session.add(td)
    await session.commit()

    # 同步到 Python Registry
    from app.services.builtin_policy_types import sync_db_policy_types
    await sync_db_policy_types(session)

    logger.info(f"Policy type created: {data.type_code} by {current_user.user_id}")

    return {
        "success": True,
        "message": f"政策类型 '{data.type_name}' 创建成功",
        "data": {
            "type_code": td.type_code,
            "type_name": td.type_name,
            "is_builtin": False,
        }
    }


@router.put("/policy-types/{type_code}")
async def update_policy_type(
    type_code: str,
    data: PolicyTypeUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """
    更新政策类型定义

    内置类型只能修改 description, icon, sort_order, is_active。
    动态类型可以修改所有字段。
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")

    from app.models.policy_type import PolicyTypeDefinition

    result = await session.execute(
        select(PolicyTypeDefinition).where(
            PolicyTypeDefinition.type_code == type_code
        )
    )
    td = result.scalar_one_or_none()

    if not td:
        raise HTTPException(status_code=404, detail=f"政策类型 '{type_code}' 不存在")

    is_builtin = td.is_builtin == 1

    # 内置类型限制可修改字段
    if is_builtin:
        if data.description is not None:
            td.description = data.description
        if data.icon is not None:
            td.icon = data.icon
        if data.sort_order is not None:
            td.sort_order = data.sort_order
        if data.is_active is not None:
            td.is_active = 1 if data.is_active else 0
    else:
        # 动态类型：所有字段可修改
        if data.type_name is not None:
            td.type_name = data.type_name
        if data.description is not None:
            td.description = data.description
        if data.field_schema is not None:
            td.field_schema = json.dumps(data.field_schema, ensure_ascii=False)
        if data.validation_rules is not None:
            td.validation_rules = json.dumps(data.validation_rules, ensure_ascii=False)
        if data.example_data is not None:
            td.example_data = json.dumps(data.example_data, ensure_ascii=False)
        if data.icon is not None:
            td.icon = data.icon
        if data.sort_order is not None:
            td.sort_order = data.sort_order
        if data.is_active is not None:
            td.is_active = 1 if data.is_active else 0

    td.updated_at = datetime.utcnow().isoformat()
    await session.commit()

    # 同步到 Python Registry（仅动态类型需要重新加载）
    if not is_builtin:
        from app.services.builtin_policy_types import sync_db_policy_types
        await sync_db_policy_types(session)

    logger.info(f"Policy type updated: {type_code} by {current_user.user_id}")

    return {"success": True, "message": f"政策类型 '{type_code}' 已更新"}


@router.delete("/policy-types/{type_code}")
async def delete_policy_type(
    type_code: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserAuth = Depends(get_current_user)
):
    """
    删除政策类型

    内置类型不可删除。有关联政策的类型不可删除。
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")

    from app.models.policy_type import PolicyTypeDefinition
    from app.models.policy import Policy

    result = await session.execute(
        select(PolicyTypeDefinition).where(
            PolicyTypeDefinition.type_code == type_code
        )
    )
    td = result.scalar_one_or_none()

    if not td:
        raise HTTPException(status_code=404, detail=f"政策类型 '{type_code}' 不存在")

    if td.is_builtin == 1:
        raise HTTPException(status_code=400, detail="内置类型不可删除")

    # 检查是否有关联政策
    policy_count = await session.scalar(
        select(func.count()).select_from(Policy).where(
            Policy.policy_type == type_code,
            Policy.deleted_at.is_(None)
        )
    )
    if policy_count and policy_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"该类型下有 {policy_count} 条政策，无法删除。请先删除或迁移相关政策。"
        )

    await session.delete(td)
    await session.commit()

    # 从 Python Registry 移除
    from app.services.policy_type_registry import get_registry
    get_registry().unregister(type_code)

    logger.info(f"Policy type deleted: {type_code} by {current_user.user_id}")

    return {"success": True, "message": f"政策类型 '{type_code}' 已删除"}


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
