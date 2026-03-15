"""版本历史模型"""
from sqlalchemy import Column, Text, Integer, ForeignKey
from app.database import Base
from datetime import datetime
import uuid


class PolicyVersion(Base):
    """政策版本历史"""
    __tablename__ = "policy_versions"

    version_id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_id = Column(Text, ForeignKey("policies.policy_id"))
    version_number = Column(Integer, nullable=False)

    change_type = Column(Text)
    changed_fields = Column(Text)
    old_values = Column(Text)
    new_values = Column(Text)
    change_reason = Column(Text)

    snapshot = Column(Text, nullable=False)

    changed_by = Column(Text)
    changed_at = Column(Text, default=lambda: datetime.utcnow().isoformat())
