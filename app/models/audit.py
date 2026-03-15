"""审计日志模型"""
from sqlalchemy import Column, Text, Integer
from app.database import Base
from datetime import datetime


class AuditLog(Base):
    """操作审计日志"""
    __tablename__ = "audit_logs"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    policy_id = Column(Text)

    action = Column(Text, nullable=False)
    field_name = Column(Text)
    old_value = Column(Text)
    new_value = Column(Text)

    operator_id = Column(Text, nullable=False)
    operator_type = Column(Text, default="user")
    operator_role = Column(Text)

    ip_address = Column(Text)
    user_agent = Column(Text)
    request_id = Column(Text)

    operated_at = Column(Text, default=lambda: datetime.utcnow().isoformat())
