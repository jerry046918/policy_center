"""认证相关 API"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from typing import Optional
import hashlib
import jwt

from app.database import get_session
from app.models.agent import AgentCredential, User
from app.config import settings
from pydantic import BaseModel
from passlib.context import CryptContext

router = APIRouter()
security = HTTPBearer(auto_error=False)

# 密码哈希工具
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """生成密码哈希"""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain, hashed)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    role: str


class AgentAuth:
    """Agent 认证上下文"""
    def __init__(self, agent_id: str):
        self.agent_id = agent_id


class UserAuth:
    """用户认证上下文"""
    def __init__(self, user_id: str, username: str, role: str):
        self.user_id = user_id
        self.username = username
        self.role = role


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    session: AsyncSession = Depends(get_session)
) -> UserAuth:
    """获取当前用户"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )

    token = credentials.credentials

    try:
        # 验证并解码 JWT
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    # 从数据库获取用户
    result = await session.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()

    if not user or user.is_active != 1:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    return UserAuth(user_id=user.user_id, username=user.username, role=user.role)


async def get_current_agent(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    session: AsyncSession = Depends(get_session)
) -> AgentAuth:
    """获取当前 Agent"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key required"
        )

    api_key = credentials.credentials

    # 验证 API Key
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    key_prefix = api_key[:8] if len(api_key) >= 8 else api_key

    result = await session.execute(
        select(AgentCredential).where(
            AgentCredential.api_key_hash == key_hash,
            AgentCredential.is_active == 1
        )
    )
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )

    # 更新最后使用时间
    agent.last_used_at = datetime.utcnow().isoformat()
    await session.commit()

    return AgentAuth(agent_id=agent.agent_id)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    session: AsyncSession = Depends(get_session)
):
    """用户登录"""
    result = await session.execute(
        select(User).where(User.username == request.username)
    )
    user = result.scalar_one_or_none()

    if not user or user.is_active != 1:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # 验证密码
    if not user.password_hash or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # 更新最后登录时间
    user.last_login_at = datetime.utcnow().isoformat()
    await session.commit()

    # 生成 JWT
    expires = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token = jwt.encode(
        {"sub": user.user_id, "username": user.username, "role": user.role, "exp": expires},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )

    return TokenResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=user.user_id,
        role=user.role
    )


@router.get("/me")
async def get_me(current_user: UserAuth = Depends(get_current_user)):
    """获取当前用户信息"""
    return {
        "user_id": current_user.user_id,
        "username": current_user.username,
        "role": current_user.role
    }


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: UserAuth = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """用户修改自己的密码"""
    # 获取用户
    result = await session.execute(select(User).where(User.user_id == current_user.user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 验证当前密码
    if not user.password_hash or not verify_password(request.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    # 更新密码
    user.password_hash = hash_password(request.new_password)
    await session.commit()

    return {"success": True, "message": "Password changed successfully"}
