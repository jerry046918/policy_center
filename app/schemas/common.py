"""通用响应 Schema"""
from pydantic import BaseModel
from typing import Generic, TypeVar, List, Optional
from datetime import datetime

T = TypeVar("T")


class BaseResponse(BaseModel):
    """基础响应"""
    success: bool = True
    message: Optional[str] = None
    request_id: Optional[str] = None


class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = False
    error: dict
    request_id: Optional[str] = None


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应"""
    success: bool = True
    data: List[T]
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 0
    request_id: Optional[str] = None

    class Config:
        # 允许额外字段
        extra = "ignore"


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    database: str
    version: str
    timestamp: str
