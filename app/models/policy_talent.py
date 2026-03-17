"""人才政策扩展模型"""
from sqlalchemy import Column, Text, Integer, ForeignKey
from app.database import Base


class PolicyTalent(Base):
    """
    人才政策扩展表

    记录各地区人才引进、人才认定相关政策的特有信息，
    包括人才分类、认定条件、补贴标准、所需材料等。
    """
    __tablename__ = "policy_talent"

    policy_id = Column(Text, ForeignKey("policies.policy_id"), primary_key=True)

    # 人才分类/层级（JSON 数组）
    # 如 ["A类（国际顶尖人才）", "B类（国家级领军人才）", "C类（地方高层次人才）"]
    talent_categories = Column(Text, default="[]")

    # 认定条件描述（结构化 JSON）
    # 如 { "A类": "诺贝尔奖获得者...", "B类": "国家级学术带头人..." }
    certification_requirements = Column(Text, default="{}")

    # 所需材料清单（JSON 数组）
    # 如 ["身份证明", "学历证书", "工作合同", "社保缴纳证明"]
    required_documents = Column(Text, default="[]")

    # 补贴标准描述（结构化 JSON）
    # 如 { "住房补贴": "最高200万", "生活补贴": "每月5000元", "安家费": "一次性50万" }
    subsidy_standards = Column(Text, default="{}")

    # 申请条件概述
    eligibility_summary = Column(Text)

    # 年龄限制（如 45 表示 45 岁以下）
    age_limit = Column(Integer)

    # 学历要求（如 "本科及以上"、"硕士及以上"）
    education_requirement = Column(Text)

    # 服务年限要求（年）
    service_years_required = Column(Integer)

    # 申报渠道/网址
    application_channel = Column(Text)

    # 特别说明
    special_notes = Column(Text)
