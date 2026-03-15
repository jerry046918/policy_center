"""应用配置"""
from pydantic_settings import BaseSettings
from typing import Optional
from functools import lru_cache
import os


class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "Policy Center"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # 数据库
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/policy_center.db"

    # 安全
    JWT_SECRET_KEY: str = "your-super-secret-key-change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # 存储
    STORAGE_TYPE: str = "local"
    STORAGE_PATH: str = "./uploads"

    # MCP
    MCP_SERVER_NAME: str = "policy_center"
    MCP_LOG_LEVEL: str = "INFO"

    # AI（可选）
    OPENAI_API_KEY: Optional[str] = None
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # 限流
    RATE_LIMIT_WEB: int = 100
    RATE_LIMIT_AGENT_DEFAULT: int = 60

    # 审计日志加密
    AES_ENCRYPTION_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
