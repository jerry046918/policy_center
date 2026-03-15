"""审核队列相关 Schema"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
import re


class ReviewSubmit(BaseModel):
    """Agent 提交政策审核请求"""
    idempotency_key: Optional[str] = Field(None, description="幂等键")
    policy_type: str = Field(default="social_insurance_base")

    title: str = Field(..., max_length=500)
    region_code: str = Field(..., pattern=r"^\d{6}$")

    extracted_text: Optional[str] = Field(None, description="OCR 或爬取文本")
    source_document_base64: Optional[str] = Field(None, description="PDF/图片 Base64")

    published_at: str = Field(..., description="发布日期")
    effective_start: str = Field(..., description="生效日期")
    effective_end: Optional[str] = Field(None)

    si_upper_limit: int = Field(..., gt=0, description="社保上限")
    si_lower_limit: int = Field(..., gt=0, description="社保下限")
    hf_upper_limit: Optional[int] = Field(None, gt=0)
    hf_lower_limit: Optional[int] = Field(None, gt=0)

    is_retroactive: bool = Field(default=False)
    retroactive_start: Optional[str] = Field(None)

    coverage_types: List[str] = Field(
        default=["养老", "医疗", "失业", "工伤", "生育"]
    )
    special_notes: Optional[str] = Field(None, max_length=1000)

    priority: str = Field(default="normal")

    @field_validator("si_lower_limit")
    @classmethod
    def validate_si_limits(cls, v, info):
        si_upper = info.data.get("si_upper_limit")
        if si_upper and v >= si_upper:
            raise ValueError("社保上限必须大于下限")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v):
        if v not in ["low", "normal", "high", "urgent"]:
            raise ValueError("优先级必须是 low/normal/high/urgent")
        return v


class ReviewAIAnalysis(BaseModel):
    """AI 分析结果"""
    is_duplicate: bool = False
    duplicate_policy_id: Optional[str] = None
    change_rate: Optional[float] = None
    retroactive_months: Optional[int] = None
    risk_level: str = "low"
    risk_tags: List[str] = []
    warnings: List[str] = []


class ReviewResponse(BaseModel):
    """审核提交响应"""
    review_id: str
    status: str = "pending_review"
    policy_id: Optional[str] = None
    warnings: List[str] = []
    ai_analysis: Optional[ReviewAIAnalysis] = None
    estimated_review_time: str = "24h"


class ReviewUpdate(BaseModel):
    """审核操作请求"""
    action: str = Field(..., description="approve/reject/clarify")
    notes: Optional[str] = Field(None, description="审核备注")
    rejection_reason: Optional[str] = Field(None, description="拒绝原因")


class ReviewDetailResponse(BaseModel):
    """审核详情响应"""
    review_id: str
    policy_id: Optional[str] = None
    status: str
    priority: str

    submitted_data: Dict[str, Any]
    raw_evidence: Optional[Dict[str, Any]] = None

    ai_validation: Optional[Dict[str, Any]] = None
    risk_level: str
    risk_tags: List[str]

    submitted_at: str
    submitted_by: str
    sla_deadline: Optional[str] = None

    claimed_by: Optional[str] = None
    claimed_at: Optional[str] = None
    reviewer_notes: Optional[str] = None

    # 地区名称
    region_name: Optional[str] = None

    # 对比数据（如果是更新）
    previous_policy: Optional[Dict[str, Any]] = None
    diff: Optional[Dict[str, Any]] = None

    # 提交类型信息
    submit_type: Optional[str] = None  # "new" 或 "update"
    existing_policy_id: Optional[str] = None  # 提交方认为要更新的政策
    change_description: Optional[str] = None  # 提交方提供的修改说明

    # 审核人最终决策
    final_action: Optional[str] = None  # 审核人的最终决定
    final_target_policy_id: Optional[str] = None  # 最终操作的政策
    reviewer_modified_data: Optional[Dict[str, Any]] = None  # 审核人修改的数据


class ReviewListResponse(BaseModel):
    """审核列表项"""
    review_id: str
    policy_title: str
    region_code: str
    region_name: Optional[str] = None
    status: str
    priority: str
    risk_level: str
    risk_tags: List[str]
    submitted_at: str
    submitted_by: str
    sla_deadline: Optional[str] = None
    sla_remaining_hours: Optional[float] = None
    sla_status: Optional[str] = "normal"  # normal, warning, overdue
    claimed_by: Optional[str] = None

    # 提交类型信息
    submit_type: Optional[str] = None  # "new" 或 "update"
    existing_policy_id: Optional[str] = None
