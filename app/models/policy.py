"""政策模型"""
from sqlalchemy import Column, Text, Integer, ForeignKey
from datetime import datetime
from app.database import Base
import uuid


class Policy(Base):
    """政策主表"""
    __tablename__ = "policies"

    policy_id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_type = Column(Text, default="social_insurance_base")
    title = Column(Text, nullable=False)
    region_code = Column(Text, nullable=False)

    source_attachments = Column(Text, default="[]")

    published_at = Column(Text, nullable=False)
    effective_start = Column(Text, nullable=False)
    effective_end = Column(Text)
    policy_year = Column(Integer)

    status = Column(Text, default="draft")
    version = Column(Integer, default=1)

    raw_content = Column(Text)
    raw_snapshot_url = Column(Text)

    created_at = Column(Text, default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(Text, default=lambda: datetime.utcnow().isoformat())
    created_by = Column(Text)
    reviewed_by = Column(Text)
    reviewed_at = Column(Text)

    deleted_at = Column(Text)
    deleted_by = Column(Text)


class PolicySocialInsurance(Base):
    """社保公积金扩展表"""
    __tablename__ = "policy_social_insurance"

    policy_id = Column(Text, ForeignKey("policies.policy_id"), primary_key=True)

    si_upper_limit = Column(Integer)
    si_lower_limit = Column(Integer)
    si_avg_salary_ref = Column(Integer)

    hf_upper_limit = Column(Integer)
    hf_lower_limit = Column(Integer)

    is_retroactive = Column(Integer, default=0)
    retroactive_start = Column(Text)
    retroactive_months = Column(Integer)

    coverage_types = Column(Text, default='["养老", "医疗", "失业", "工伤", "生育"]')

    prev_si_upper = Column(Integer)
    prev_si_lower = Column(Integer)
    change_rate_upper = Column(Text)
    change_rate_lower = Column(Text)

    special_notes = Column(Text)
