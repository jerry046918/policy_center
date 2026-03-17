"""社会平均工资政策 Pydantic Schema"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional


class AvgSalaryCreate(BaseModel):
    """社会平均工资数据 - 创建"""
    avg_salary_total: int = Field(..., gt=0, description="全口径城镇单位就业人员平均工资（元/年）")
    avg_salary_monthly: Optional[int] = Field(None, gt=0, description="月平均工资（元/月）")
    avg_salary_on_post: Optional[int] = Field(None, gt=0, description="在岗职工平均工资（元/年）")
    avg_salary_non_private: Optional[int] = Field(None, gt=0, description="城镇非私营单位平均工资（元/年）")
    avg_salary_private: Optional[int] = Field(None, gt=0, description="城镇私营单位平均工资（元/年）")
    statistics_year: Optional[int] = Field(None, ge=2000, le=2100, description="统计年度")
    growth_rate: Optional[float] = Field(None, description="增长率（%）")
    special_notes: Optional[str] = Field(None, max_length=1000, description="特别说明")

    @field_validator("avg_salary_monthly", mode="before")
    @classmethod
    def compute_monthly(cls, v, info):
        """如果未提供月均，自动从年均计算"""
        if v is None:
            total = info.data.get("avg_salary_total")
            if total:
                return round(total / 12)
        return v


class AvgSalaryResponse(BaseModel):
    """社会平均工资数据 - 响应"""
    avg_salary_total: Optional[int] = None
    avg_salary_monthly: Optional[int] = None
    avg_salary_on_post: Optional[int] = None
    avg_salary_non_private: Optional[int] = None
    avg_salary_private: Optional[int] = None
    statistics_year: Optional[int] = None
    growth_rate: Optional[float] = None
    prev_avg_salary_total: Optional[int] = None
    special_notes: Optional[str] = None
