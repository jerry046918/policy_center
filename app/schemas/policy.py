"""政策相关 Schema"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
import re


class PolicySocialInsuranceCreate(BaseModel):
    """社保公积金数据"""
    si_upper_limit: Optional[int] = Field(None, gt=0, description="社保上限（元/月）")
    si_lower_limit: Optional[int] = Field(None, gt=0, description="社保下限（元/月）")
    si_avg_salary_ref: Optional[int] = Field(None, description="参考社平工资")

    hf_upper_limit: Optional[int] = Field(None, gt=0, description="公积金上限")
    hf_lower_limit: Optional[int] = Field(None, gt=0, description="公积金下限")

    is_retroactive: bool = Field(default=False, description="是否追溯生效")
    retroactive_start: Optional[str] = Field(None, description="追溯开始日期")

    coverage_types: List[str] = Field(
        default=["养老", "医疗", "失业", "工伤", "生育"],
        description="险种覆盖"
    )
    special_notes: Optional[str] = Field(None, max_length=1000)

    @field_validator("si_lower_limit")
    @classmethod
    def validate_limits(cls, v, info):
        """校验上限必须大于下限"""
        si_upper = info.data.get("si_upper_limit")
        if si_upper and v and si_upper <= v:
            raise ValueError("社保上限必须大于下限")
        return v


class PolicyCreate(BaseModel):
    """创建政策请求"""
    title: str = Field(..., max_length=500, description="政策名称")
    region_code: str = Field(..., pattern=r"^\d{6}$", description="六位行政区划码")

    published_at: str = Field(..., description="发布日期 YYYY-MM-DD")
    effective_start: str = Field(..., description="生效开始日期")
    effective_end: Optional[str] = Field(None, description="生效结束日期")

    social_insurance: PolicySocialInsuranceCreate

    raw_content: Optional[str] = Field(None, description="原始文本")

    @field_validator("region_code")
    @classmethod
    def validate_region_code(cls, v):
        if not re.match(r"^\d{6}$", v):
            raise ValueError("地区编码必须是6位数字")
        return v

    @field_validator("published_at", "effective_start", "effective_end")
    @classmethod
    def validate_date(cls, v):
        if v is None:
            return v
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("日期格式必须是 YYYY-MM-DD")
        return v


class PolicyUpdate(BaseModel):
    """更新政策请求"""
    title: Optional[str] = Field(None, max_length=500)
    published_at: Optional[str] = None
    effective_start: Optional[str] = None
    effective_end: Optional[str] = None
    social_insurance: Optional[PolicySocialInsuranceCreate] = None
    special_notes: Optional[str] = None
    change_reason: str = Field(..., min_length=5, description="修改原因（必填）")
    create_new_version: bool = Field(default=False, description="是否创建新版本（True=发布新版本，False=更新当前版本）")


class PolicySocialInsuranceResponse(BaseModel):
    """社保公积金响应"""
    si_upper_limit: Optional[int] = None
    si_lower_limit: Optional[int] = None
    si_avg_salary_ref: Optional[int] = None
    hf_upper_limit: Optional[int] = None
    hf_lower_limit: Optional[int] = None
    is_retroactive: bool = False
    retroactive_start: Optional[str] = None
    retroactive_months: Optional[int] = None
    coverage_types: List[str] = []
    change_rate_upper: Optional[float] = None
    change_rate_lower: Optional[float] = None
    special_notes: Optional[str] = None


class PolicyResponse(BaseModel):
    """政策详情响应"""
    policy_id: str
    policy_type: str
    title: str
    region_code: str
    region_name: Optional[str] = None

    source_attachments: Optional[str] = None  # JSON string of SourceDocument[]

    published_at: str
    effective_start: str
    effective_end: Optional[str] = None
    policy_year: Optional[int] = None

    status: str
    version: int

    social_insurance: Optional[PolicySocialInsuranceResponse] = None

    created_at: str
    updated_at: str
    created_by: Optional[str] = None
    reviewed_by: Optional[str] = None

    class Config:
        from_attributes = True


class PolicyListResponse(BaseModel):
    """政策列表项"""
    policy_id: str
    title: str
    region_code: str
    region_name: Optional[str] = None
    si_upper_limit: Optional[int] = None
    si_lower_limit: Optional[int] = None
    effective_start: str
    status: str
    is_retroactive: bool = False
