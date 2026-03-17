"""Pydantic Schemas"""
from app.schemas.policy import (
    PolicyCreate,
    PolicyUpdate,
    PolicyResponse,
    PolicySocialInsuranceCreate,
    PolicySocialInsuranceResponse,
    PolicyHousingFundCreate,
    PolicyHousingFundResponse,
    PolicyListResponse,
)
from app.schemas.policy_avg_salary import (
    AvgSalaryCreate,
    AvgSalaryResponse,
)
from app.schemas.policy_talent import (
    TalentPolicyCreate,
    TalentPolicyResponse,
)
from app.schemas.review import (
    ReviewUpdate,
)
from app.schemas.common import PaginatedResponse

__all__ = [
    "PolicyCreate",
    "PolicyUpdate",
    "PolicyResponse",
    "PolicySocialInsuranceCreate",
    "PolicySocialInsuranceResponse",
    "PolicyHousingFundCreate",
    "PolicyHousingFundResponse",
    "PolicyListResponse",
    "AvgSalaryCreate",
    "AvgSalaryResponse",
    "TalentPolicyCreate",
    "TalentPolicyResponse",
    "ReviewUpdate",
    "PaginatedResponse",
]
