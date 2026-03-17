"""人才政策 Pydantic Schema"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict


class TalentPolicyCreate(BaseModel):
    """人才政策数据 - 创建"""
    talent_categories: List[str] = Field(
        default=[],
        description="人才分类/层级列表"
    )
    certification_requirements: Dict[str, str] = Field(
        default={},
        description="认定条件（按人才类别）"
    )
    required_documents: List[str] = Field(
        default=[],
        description="所需材料清单"
    )
    subsidy_standards: Dict[str, str] = Field(
        default={},
        description="补贴标准（按补贴类型）"
    )
    eligibility_summary: Optional[str] = Field(None, max_length=2000, description="申请条件概述")
    age_limit: Optional[int] = Field(None, ge=0, le=100, description="年龄限制")
    education_requirement: Optional[str] = Field(None, max_length=200, description="学历要求")
    service_years_required: Optional[int] = Field(None, ge=0, description="服务年限要求（年）")
    application_channel: Optional[str] = Field(None, max_length=500, description="申报渠道/网址")
    special_notes: Optional[str] = Field(None, max_length=1000, description="特别说明")


class TalentPolicyResponse(BaseModel):
    """人才政策数据 - 响应"""
    talent_categories: List[str] = []
    certification_requirements: Dict[str, str] = {}
    required_documents: List[str] = []
    subsidy_standards: Dict[str, str] = {}
    eligibility_summary: Optional[str] = None
    age_limit: Optional[int] = None
    education_requirement: Optional[str] = None
    service_years_required: Optional[int] = None
    application_channel: Optional[str] = None
    special_notes: Optional[str] = None
