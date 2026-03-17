"""社会平均工资政策扩展模型"""
from sqlalchemy import Column, Text, Integer, ForeignKey
from app.database import Base


class PolicyAvgSalary(Base):
    """
    社会平均工资政策扩展表

    记录各地区公布的社会平均工资数据，包括全口径、在岗职工、
    城镇非私营单位等不同统计口径的平均工资。
    """
    __tablename__ = "policy_avg_salary"

    policy_id = Column(Text, ForeignKey("policies.policy_id"), primary_key=True)

    # 全口径城镇单位就业人员平均工资（元/年）
    avg_salary_total = Column(Integer, nullable=False)

    # 全口径月平均工资（元/月，由 avg_salary_total / 12 计算）
    avg_salary_monthly = Column(Integer)

    # 在岗职工平均工资（元/年）
    avg_salary_on_post = Column(Integer)

    # 城镇非私营单位就业人员平均工资（元/年）
    avg_salary_non_private = Column(Integer)

    # 城镇私营单位就业人员平均工资（元/年）
    avg_salary_private = Column(Integer)

    # 统计年度（如 2023 表示 2023年度社平工资）
    statistics_year = Column(Integer)

    # 增长率（相比上一年，百分比，如 5.5 表示 5.5%）
    growth_rate = Column(Text)

    # 上一年度金额（元/年，用于计算增长率）
    prev_avg_salary_total = Column(Integer)

    # 数据来源说明
    special_notes = Column(Text)
