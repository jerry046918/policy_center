"""地区字典模型"""
from sqlalchemy import Column, Text, Integer
from datetime import datetime
from app.database import Base


class Region(Base):
    """地区字典（国标GB/T 2260）"""
    __tablename__ = "regions"

    code = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    level = Column(Text, nullable=False)
    parent_code = Column(Text)
    full_path = Column(Text)
    path_materialized = Column(Text)
    is_active = Column(Integer, default=1)
    min_wage = Column(Integer)
    avg_salary = Column(Integer)
    updated_at = Column(Text, default=lambda: datetime.utcnow().isoformat())
