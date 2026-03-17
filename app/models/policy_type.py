"""政策类型注册表模型"""
from sqlalchemy import Column, Text, Integer
from datetime import datetime
from app.database import Base


class PolicyTypeDefinition(Base):
    """
    政策类型定义表

    存储系统支持的所有政策类型及其元数据。
    内置类型（is_builtin=1）对应专用扩展表；
    动态类型（is_builtin=0）将数据存入 policies.extension_data JSON 列。
    """
    __tablename__ = "policy_type_definitions"

    type_code = Column(Text, primary_key=True)  # 类型编码，如 "social_insurance"
    type_name = Column(Text, nullable=False)  # 类型名称，如 "社保基数"
    description = Column(Text)  # 类型描述
    extension_table = Column(Text, default=None)  # 扩展表名（内置类型才有）

    # 扩展字段的 JSON Schema 定义
    # 格式: { "field_name": { "type": "integer", "required": true, "description": "...", ... } }
    field_schema = Column(Text, nullable=False, default="{}")

    # 验证规则（JSON 数组，人类可读）
    # 格式: ["si_upper_limit > si_lower_limit", ...]
    validation_rules = Column(Text, default="[]")

    # 示例数据（JSON），用于 Agent API schema 返回
    example_data = Column(Text, default="{}")

    # 是否内置类型
    # 内置类型: 有专用扩展表和代码级验证，不可删除，字段定义不可修改
    # 动态类型: 数据存入 policies.extension_data，字段由 field_schema 动态定义
    is_builtin = Column(Integer, default=0)  # 0=动态, 1=内置

    # 类型状态
    is_active = Column(Integer, default=1)  # 0=禁用, 1=启用
    sort_order = Column(Integer, default=0)  # 排序权重

    # 图标（用于前端展示，可选，如 "SafetyCertificateOutlined"）
    icon = Column(Text, default=None)

    # 使用此类型的政策数量（缓存，定期更新）
    policy_count = Column(Integer, default=0)

    created_at = Column(Text, default=lambda: datetime.utcnow().isoformat())
    updated_at = Column(Text, default=lambda: datetime.utcnow().isoformat())
