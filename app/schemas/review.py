"""审核队列相关 Schema"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class ReviewUpdate(BaseModel):
    """审核操作请求"""
    action: str = Field(..., description="approve/reject/clarify")
    notes: Optional[str] = Field(None, description="审核备注")
    rejection_reason: Optional[str] = Field(None, description="拒绝原因")


class ReviewDetailResponse(BaseModel):
    """审核详情响应"""
    review_id: str
    policy_id: Optional[str] = None
    policy_type: Optional[str] = None
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
    policy_type: Optional[str] = None
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
