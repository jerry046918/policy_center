"""审核队列表"""
from sqlalchemy import Column, Text, Integer, Index
from app.database import Base
from datetime import datetime
import uuid


class ReviewQueue(Base):
    """审核队列"""
    __tablename__ = "review_queue"

    review_id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_id = Column(Text)
    idempotency_key = Column(Text, unique=True)

    submitted_data = Column(Text, nullable=False)
    raw_evidence = Column(Text)

    ai_validation = Column(Text)
    duplicate_check = Column(Text)
    risk_level = Column(Text, default="low")
    risk_tags = Column(Text, default="[]")

    status = Column(Text, default="pending")
    priority = Column(Text, default="normal")

    # 提交类型相关字段
    submit_type = Column(Text, default="new")  # "new" 或 "update"
    existing_policy_id = Column(Text)  # 更新时指向的原政策ID
    change_description = Column(Text)  # 更新时的修改说明

    # 审核人最终决策
    final_action = Column(Text)  # "new", "update", "new_version" - 审核人可覆盖提交方判断
    final_target_policy_id = Column(Text)  # 最终操作的目标政策ID
    reviewer_modified_data = Column(Text)  # 审核人修改后的数据（JSON）

    claimed_by = Column(Text)
    claimed_at = Column(Text)

    reviewer_notes = Column(Text)
    reviewer_id = Column(Text)
    reviewed_at = Column(Text)
    submitted_at = Column(Text, default=lambda: datetime.utcnow().isoformat())
    submitted_by = Column(Text, nullable=False)

    sla_deadline = Column(Text)


# Indexes for common query patterns
Index('ix_review_queue_status', ReviewQueue.status)
Index('ix_review_queue_submitted_by', ReviewQueue.submitted_by)
Index('ix_review_queue_sla_deadline', ReviewQueue.sla_deadline)
