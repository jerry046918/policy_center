"""Agent 认证凭据模型"""
from sqlalchemy import Column, Text, Integer
from app.database import Base
from datetime import datetime
import uuid


class AgentCredential(Base):
    """Agent API Key 凭据"""
    __tablename__ = "agent_credentials"

    agent_id = Column(Text, primary_key=True, default=lambda: f"agent_{uuid.uuid4().hex[:12]}")
    agent_name = Column(Text, nullable=False)
    api_key_hash = Column(Text, nullable=False)
    api_key_prefix = Column(Text, nullable=False)

    description = Column(Text)
    permissions = Column(Text, default='["submit"]')
    rate_limit = Column(Integer, default=60)

    is_active = Column(Integer, default=1)
    last_used_at = Column(Text)
    created_at = Column(Text, default=lambda: datetime.utcnow().isoformat())
    expires_at = Column(Text)
    created_by = Column(Text)


class User(Base):
    """Web 用户表"""
    __tablename__ = "users"

    user_id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(Text, unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    email = Column(Text, unique=True)
    display_name = Column(Text)
    role = Column(Text, default="staff")
    is_active = Column(Integer, default=1)
    last_login_at = Column(Text)
    created_at = Column(Text, default=lambda: datetime.utcnow().isoformat())
