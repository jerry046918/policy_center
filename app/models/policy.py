"""政策模型"""
from sqlalchemy import Column, Text, Integer, ForeignKey, Index
from datetime import datetime
from app.database import Base
import uuid


class Policy(Base):
    """政策主表"""
    __tablename__ = "policies"

    policy_id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_type = Column(Text, default="social_insurance")
    title = Column(Text, nullable=False)
    region_code = Column(Text, nullable=False)

    source_attachments = Column(Text, default="[]")

    published_at = Column(Text, nullable=False)
    effective_start = Column(Text, nullable=False)
    effective_end = Column(Text)
    policy_year = Column(Integer)

    status = Column(Text, default="draft")
    version = Column(Integer, default=1)

    # 动态类型的扩展数据（JSON 存储）
    # 仅用于通过管理后台动态创建的政策类型（无专用扩展表的类型）
    extension_data = Column(Text, default=None)

    raw_content = Column(Text)
    raw_snapshot_url = Column(Text)

    created_at = Column(Text, default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(Text, default=lambda: datetime.utcnow().isoformat())
    created_by = Column(Text)
    reviewed_by = Column(Text)
    reviewed_at = Column(Text)

    deleted_at = Column(Text)
    deleted_by = Column(Text)



# Indexes for common query patterns
Index('ix_policies_region_type_start', Policy.region_code, Policy.policy_type, Policy.effective_start)
Index('ix_policies_status_deleted', Policy.status, Policy.deleted_at)
Index('ix_policies_policy_year', Policy.policy_year)


class PolicySocialInsurance(Base):
    """社保基数扩展表"""
    __tablename__ = "policy_social_insurance"

    policy_id = Column(Text, ForeignKey("policies.policy_id"), primary_key=True)

    si_upper_limit = Column(Integer)
    si_lower_limit = Column(Integer)
    si_avg_salary_ref = Column(Integer)

    is_retroactive = Column(Integer, default=0)
    retroactive_start = Column(Text)
    retroactive_months = Column(Integer)

    coverage_types = Column(Text, default='["养老", "医疗", "失业", "工伤", "生育"]')

    prev_si_upper = Column(Integer)
    prev_si_lower = Column(Integer)
    change_rate_upper = Column(Text)
    change_rate_lower = Column(Text)

    special_notes = Column(Text)


class PolicyHousingFund(Base):
    """公积金基数扩展表"""
    __tablename__ = "policy_housing_fund"

    policy_id = Column(Text, ForeignKey("policies.policy_id"), primary_key=True)

    hf_upper_limit = Column(Integer)
    hf_lower_limit = Column(Integer)

    is_retroactive = Column(Integer, default=0)
    retroactive_start = Column(Text)
    retroactive_months = Column(Integer)

    prev_hf_upper = Column(Integer)
    prev_hf_lower = Column(Integer)
    change_rate_upper = Column(Text)
    change_rate_lower = Column(Text)

    special_notes = Column(Text)
