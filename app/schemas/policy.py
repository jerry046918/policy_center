"""政策相关 Schema"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
import re


# ── 社保基数（保留，兼容旧代码引用） ──────────────────────

class PolicySocialInsuranceCreate(BaseModel):
    """社保基数数据"""
    si_upper_limit: Optional[int] = Field(None, gt=0, description="社保上限（元/月）")
    si_lower_limit: Optional[int] = Field(None, gt=0, description="社保下限（元/月）")
    si_avg_salary_ref: Optional[int] = Field(None, description="参考社平工资")

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


class PolicySocialInsuranceResponse(BaseModel):
    """社保基数响应"""
    si_upper_limit: Optional[int] = None
    si_lower_limit: Optional[int] = None
    si_avg_salary_ref: Optional[int] = None
    is_retroactive: bool = False
    retroactive_start: Optional[str] = None
    retroactive_months: Optional[int] = None
    coverage_types: List[str] = []
    change_rate_upper: Optional[float] = None
    change_rate_lower: Optional[float] = None
    special_notes: Optional[str] = None


# ── 公积金基数 ──────────────────────────────────────────

class PolicyHousingFundCreate(BaseModel):
    """公积金基数数据"""
    hf_upper_limit: Optional[int] = Field(None, gt=0, description="公积金上限（元/月）")
    hf_lower_limit: Optional[int] = Field(None, gt=0, description="公积金下限（元/月）")
    is_retroactive: bool = Field(default=False, description="是否追溯生效")
    retroactive_start: Optional[str] = Field(None, description="追溯开始日期")
    special_notes: Optional[str] = Field(None, max_length=1000)

    @field_validator("hf_lower_limit")
    @classmethod
    def validate_limits(cls, v, info):
        hf_upper = info.data.get("hf_upper_limit")
        if hf_upper and v and hf_upper <= v:
            raise ValueError("公积金上限必须大于下限")
        return v


class PolicyHousingFundResponse(BaseModel):
    """公积金基数响应"""
    hf_upper_limit: Optional[int] = None
    hf_lower_limit: Optional[int] = None
    is_retroactive: bool = False
    retroactive_start: Optional[str] = None
    retroactive_months: Optional[int] = None
    change_rate_upper: Optional[float] = None
    change_rate_lower: Optional[float] = None
    special_notes: Optional[str] = None


# ── 通用政策 Schema（支持多类型） ──────────────────────────────

class PolicyCreate(BaseModel):
    """
    创建政策请求（支持多种政策类型）

    policy_type 决定了 type_data 中应该包含哪些字段。
    为保持向后兼容，仍然支持 social_insurance 字段。
    """
    policy_type: str = Field(
        default="social_insurance",
        description="政策类型编码"
    )
    title: str = Field(..., max_length=500, description="政策名称")
    region_code: str = Field(..., pattern=r"^\d{6}$", description="六位行政区划码")

    published_at: str = Field(..., description="发布日期 YYYY-MM-DD")
    effective_start: str = Field(..., description="生效开始日期")
    effective_end: Optional[str] = Field(None, description="生效结束日期")

    # 类型扩展数据（通用入口）
    type_data: Optional[Dict[str, Any]] = Field(
        None,
        description="类型特定的扩展数据，字段由 policy_type 决定"
    )

    # 向后兼容：保留 social_insurance 字段
    social_insurance: Optional[PolicySocialInsuranceCreate] = Field(
        None,
        description="[兼容] 社保数据，等价于 policy_type=social_insurance 时的 type_data"
    )

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

    @model_validator(mode="after")
    def normalize_type_data(self):
        """
        向后兼容处理：
        如果用户使用旧的 social_insurance 字段，自动转换为 type_data
        """
        if self.social_insurance and not self.type_data:
            self.policy_type = "social_insurance"
            self.type_data = self.social_insurance.model_dump()
        return self

    def get_type_data(self) -> Dict[str, Any]:
        """获取规范化后的类型扩展数据"""
        if self.type_data:
            return self.type_data
        if self.social_insurance:
            return self.social_insurance.model_dump()
        return {}


class PolicyUpdate(BaseModel):
    """更新政策请求"""
    title: Optional[str] = Field(None, max_length=500)
    published_at: Optional[str] = None
    effective_start: Optional[str] = None
    effective_end: Optional[str] = None

    # 类型扩展数据（通用入口）
    type_data: Optional[Dict[str, Any]] = Field(
        None,
        description="类型特定的扩展数据"
    )

    # 向后兼容
    social_insurance: Optional[PolicySocialInsuranceCreate] = None

    special_notes: Optional[str] = None
    change_reason: str = Field(..., min_length=5, description="修改原因（必填）")
    create_new_version: bool = Field(default=False, description="是否创建新版本")

    @model_validator(mode="after")
    def normalize_type_data(self):
        """向后兼容：social_insurance -> type_data"""
        if self.social_insurance and not self.type_data:
            self.type_data = self.social_insurance.model_dump(exclude_unset=True)
        return self

    def get_type_data(self) -> Optional[Dict[str, Any]]:
        """获取规范化后的类型扩展数据"""
        if self.type_data:
            return self.type_data
        if self.social_insurance:
            return self.social_insurance.model_dump(exclude_unset=True)
        return None


class PolicyResponse(BaseModel):
    """
    政策详情响应（支持多种政策类型）

    type_data 中包含该政策类型特定的扩展数据。
    对于 social_insurance 类型，同时填充 social_insurance 字段以保持兼容。
    """
    policy_id: str
    policy_type: str
    title: str
    region_code: str
    region_name: Optional[str] = None

    source_attachments: Optional[str] = None

    published_at: str
    effective_start: str
    effective_end: Optional[str] = None
    policy_year: Optional[int] = None

    status: str
    version: int

    # 通用类型扩展数据（所有政策类型）
    type_data: Optional[Dict[str, Any]] = Field(
        None,
        description="类型特定的扩展数据"
    )

    # 向后兼容：社保数据
    social_insurance: Optional[PolicySocialInsuranceResponse] = None

    created_at: str
    updated_at: str
    created_by: Optional[str] = None
    reviewed_by: Optional[str] = None

    model_config = {"from_attributes": True}


class PolicyListResponse(BaseModel):
    """政策列表项"""
    policy_id: str
    policy_type: str = "social_insurance"
    title: str
    region_code: str
    region_name: Optional[str] = None

    # 通用摘要数据（从 type_data 中提取关键信息）
    type_summary: Optional[Dict[str, Any]] = Field(
        None,
        description="类型特定的摘要数据（用于列表展示）"
    )

    # 向后兼容
    si_upper_limit: Optional[int] = None
    si_lower_limit: Optional[int] = None

    effective_start: str
    status: str
    is_retroactive: bool = False
