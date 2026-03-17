"""
政策类型注册中心（Python 侧）

提供政策类型的注册、发现和调度能力。

类型分两种：
  - 内置类型 (is_builtin=True): 有专用扩展表、代码级验证函数
  - 动态类型 (is_builtin=False): 数据存入 policies.extension_data，按 field_schema JSON 验证
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import (
    Any, Callable, Dict, List, Optional, Type, TYPE_CHECKING
)
from pydantic import BaseModel

if TYPE_CHECKING:
    from sqlalchemy.orm import DeclarativeBase


@dataclass
class PolicyTypeDescriptor:
    """政策类型描述符"""
    type_code: str  # 唯一标识
    type_name: str  # 显示名称
    description: str  # 类型描述
    extension_table: Optional[str] = None  # 扩展表名（动态类型为 None）

    # 是否内置类型
    is_builtin: bool = False

    # SQLAlchemy 扩展模型类（仅内置类型）
    extension_model: Type[Any] = None

    # Pydantic Schema 类（仅内置类型）
    create_schema: Type[BaseModel] = None
    response_schema: Type[BaseModel] = None

    # 字段 schema（JSON Schema 格式）
    field_schema: Dict[str, Any] = field(default_factory=dict)

    # 验证规则描述（人类可读）
    validation_rules: List[str] = field(default_factory=list)

    # 示例数据
    example_data: Dict[str, Any] = field(default_factory=dict)

    # 自定义验证函数 (data: dict) -> List[str]
    validator_func: Optional[Callable[[dict], List[str]]] = None

    # 自定义 AI 分析函数
    ai_analysis_func: Optional[Callable] = None

    # 扩展记录 CRUD 函数（仅内置类型）
    create_extension_func: Optional[Callable[[str, dict], Any]] = None
    update_extension_func: Optional[Callable[[Any, dict], None]] = None
    to_response_func: Optional[Callable[[Any], dict]] = None

    # 前端图标
    icon: Optional[str] = None

    # 排序权重
    sort_order: int = 0


def _dynamic_validator(field_schema: Dict[str, Any]) -> Callable[[dict], List[str]]:
    """
    根据 field_schema 生成动态验证函数。

    支持的验证规则:
      - required: 必填检查
      - type: 类型检查 (integer, number, string, boolean, array, object)
      - gt/ge/lt/le: 数值范围
      - max_length: 字符串长度
    """
    def validate(data: dict) -> List[str]:
        warnings = []
        for field_name, spec in field_schema.items():
            value = data.get(field_name)
            required = spec.get("required", False)
            field_type = spec.get("type", "string")
            desc = spec.get("description", field_name)

            # 必填检查
            if required and (value is None or value == ""):
                warnings.append(f"缺少必填字段: {desc}")
                continue

            if value is None:
                continue

            # 类型检查
            if field_type in ("integer", "number"):
                if not isinstance(value, (int, float)):
                    warnings.append(f"{desc}: 应为数值类型")
                    continue
                if "gt" in spec and value <= spec["gt"]:
                    warnings.append(f"{desc}: 应大于 {spec['gt']}")
                if "ge" in spec and value < spec["ge"]:
                    warnings.append(f"{desc}: 应大于等于 {spec['ge']}")
                if "lt" in spec and value >= spec["lt"]:
                    warnings.append(f"{desc}: 应小于 {spec['lt']}")
                if "le" in spec and value > spec["le"]:
                    warnings.append(f"{desc}: 应小于等于 {spec['le']}")

            if field_type == "string" and isinstance(value, str):
                max_len = spec.get("max_length")
                if max_len and len(value) > max_len:
                    warnings.append(f"{desc}: 长度不能超过 {max_len}")

        return warnings

    return validate


def _dynamic_to_response(data_json: Optional[str]) -> Optional[dict]:
    """将 extension_data JSON 转为响应 dict"""
    if not data_json:
        return None
    try:
        return json.loads(data_json)
    except (json.JSONDecodeError, TypeError):
        return None


class PolicyTypeRegistry:
    """
    政策类型注册中心（单例）

    管理内置类型和动态类型的注册与发现。
    """

    _instance: Optional[PolicyTypeRegistry] = None
    _types: Dict[str, PolicyTypeDescriptor]

    def __new__(cls) -> PolicyTypeRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._types = {}
        return cls._instance

    def register(self, descriptor: PolicyTypeDescriptor) -> None:
        """注册一个政策类型"""
        if descriptor.type_code in self._types:
            raise ValueError(
                f"Policy type '{descriptor.type_code}' is already registered"
            )
        self._types[descriptor.type_code] = descriptor

    def register_or_update(self, descriptor: PolicyTypeDescriptor) -> None:
        """注册或更新一个政策类型（用于动态类型同步）"""
        self._types[descriptor.type_code] = descriptor

    def get(self, type_code: str) -> Optional[PolicyTypeDescriptor]:
        """获取政策类型描述符"""
        return self._types.get(type_code)

    def get_or_raise(self, type_code: str) -> PolicyTypeDescriptor:
        """获取政策类型描述符，不存在则抛异常"""
        desc = self._types.get(type_code)
        if desc is None:
            valid = ", ".join(self._types.keys())
            raise ValueError(
                f"Unknown policy type: '{type_code}'. Valid types: {valid}"
            )
        return desc

    def list_all(self, active_only: bool = True) -> List[PolicyTypeDescriptor]:
        """列出所有已注册的政策类型"""
        types = list(self._types.values())
        types.sort(key=lambda t: t.sort_order)
        return types

    def list_type_codes(self) -> List[str]:
        """列出所有类型编码"""
        return list(self._types.keys())

    def has(self, type_code: str) -> bool:
        """判断类型是否已注册"""
        return type_code in self._types

    def is_builtin(self, type_code: str) -> bool:
        """判断是否内置类型"""
        desc = self._types.get(type_code)
        return desc.is_builtin if desc else False

    def is_dynamic(self, type_code: str) -> bool:
        """判断是否动态类型"""
        desc = self._types.get(type_code)
        return not desc.is_builtin if desc else False

    def unregister(self, type_code: str) -> None:
        """注销一个政策类型"""
        self._types.pop(type_code, None)

    def clear(self) -> None:
        """清空所有注册（主要用于测试）"""
        self._types.clear()


# 全局单例
registry = PolicyTypeRegistry()


def get_registry() -> PolicyTypeRegistry:
    """获取全局注册中心实例"""
    return registry
