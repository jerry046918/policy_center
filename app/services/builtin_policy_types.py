"""
内置政策类型注册

在应用启动时调用 register_builtin_types() 将所有内置政策类型注册到全局注册中心。
新增政策类型只需在此文件中添加新的注册代码块。
"""
import json
from typing import Any, Dict, List, Optional

from app.services.policy_type_registry import (
    PolicyTypeDescriptor,
    get_registry,
)

# ── 模型导入 ────────────────────────────────────────────────
from app.models.policy import PolicySocialInsurance, PolicyHousingFund
from app.models.policy_avg_salary import PolicyAvgSalary
from app.models.policy_talent import PolicyTalent

# ── Schema 导入 ─────────────────────────────────────────────
from app.schemas.policy import (
    PolicySocialInsuranceCreate,
    PolicySocialInsuranceResponse,
    PolicyHousingFundCreate,
    PolicyHousingFundResponse,
)
from app.schemas.policy_avg_salary import AvgSalaryCreate, AvgSalaryResponse
from app.schemas.policy_talent import TalentPolicyCreate, TalentPolicyResponse


# ============================================================
# 1. 社保基数 (social_insurance)
# ============================================================

def _si_validate(data: dict) -> List[str]:
    """社保数据验证"""
    warnings = []
    si_upper = data.get("si_upper_limit")
    si_lower = data.get("si_lower_limit")
    if si_upper and si_lower and si_upper <= si_lower:
        warnings.append("社保上限必须大于下限")
    # 合理性检查
    if si_lower and si_lower < 2000:
        warnings.append(f"社保下限({si_lower})低于最低工资标准，请核实")
    if si_upper and si_upper > 35000:
        warnings.append(f"社保上限({si_upper})超过社平工资3倍，请核实")
    if si_upper and si_lower and si_lower > 0:
        ratio = si_upper / si_lower
        if ratio > 5:
            warnings.append(f"上下限比值({ratio:.1f})过大，请核实")
    return warnings


def _si_create_extension(policy_id: str, data: dict) -> PolicySocialInsurance:
    """从提交数据创建社保扩展记录"""
    from datetime import datetime

    retroactive_months = None
    if data.get("is_retroactive") and data.get("retroactive_start") and data.get("effective_start"):
        try:
            retro_start = datetime.fromisoformat(data["retroactive_start"])
            eff_start = datetime.fromisoformat(data["effective_start"])
            retroactive_months = (
                (eff_start.year - retro_start.year) * 12
                + (eff_start.month - retro_start.month)
            )
        except ValueError:
            pass

    return PolicySocialInsurance(
        policy_id=policy_id,
        si_upper_limit=data.get("si_upper_limit"),
        si_lower_limit=data.get("si_lower_limit"),
        si_avg_salary_ref=data.get("si_avg_salary_ref"),
        is_retroactive=1 if data.get("is_retroactive") else 0,
        retroactive_start=data.get("retroactive_start"),
        retroactive_months=retroactive_months,
        coverage_types=json.dumps(
            data.get("coverage_types", ["养老", "医疗", "失业", "工伤", "生育"]),
            ensure_ascii=False,
        ),
        special_notes=data.get("special_notes"),
    )


def _si_update_extension(ext: PolicySocialInsurance, data: dict) -> None:
    """更新社保扩展记录"""
    from datetime import datetime

    for field in [
        "si_upper_limit", "si_lower_limit", "si_avg_salary_ref",
        "retroactive_start", "special_notes",
    ]:
        if data.get(field) is not None:
            setattr(ext, field, data[field])

    if "is_retroactive" in data:
        ext.is_retroactive = 1 if data["is_retroactive"] else 0

    if "coverage_types" in data:
        ext.coverage_types = json.dumps(data["coverage_types"], ensure_ascii=False)

    # 重新计算追溯月数
    if ext.is_retroactive and ext.retroactive_start and data.get("effective_start"):
        try:
            retro_start = datetime.fromisoformat(ext.retroactive_start)
            eff_start = datetime.fromisoformat(data["effective_start"])
            ext.retroactive_months = (
                (eff_start.year - retro_start.year) * 12
                + (eff_start.month - retro_start.month)
            )
        except ValueError:
            pass


def _si_to_response(ext: PolicySocialInsurance) -> dict:
    """将社保扩展模型转为响应 dict"""
    return {
        "si_upper_limit": ext.si_upper_limit,
        "si_lower_limit": ext.si_lower_limit,
        "si_avg_salary_ref": ext.si_avg_salary_ref,
        "is_retroactive": ext.is_retroactive == 1,
        "retroactive_start": ext.retroactive_start,
        "retroactive_months": ext.retroactive_months,
        "coverage_types": json.loads(ext.coverage_types) if ext.coverage_types else [],
        "change_rate_upper": float(ext.change_rate_upper) if ext.change_rate_upper else None,
        "change_rate_lower": float(ext.change_rate_lower) if ext.change_rate_lower else None,
        "special_notes": ext.special_notes,
    }


SI_FIELD_SCHEMA = {
    "si_upper_limit": {
        "type": "integer", "unit": "元/月", "required": True,
        "description": "社保基数上限",
        "search_keywords": ["社保基数上限", "缴费工资基数上限", "社会保险缴费基数上限"],
    },
    "si_lower_limit": {
        "type": "integer", "unit": "元/月", "required": True,
        "description": "社保基数下限",
        "search_keywords": ["社保基数下限", "缴费工资基数下限", "社会保险缴费基数下限"],
    },
    "is_retroactive": {
        "type": "boolean", "default": False,
        "description": "是否追溯生效",
        "search_keywords": ["追溯执行", "追溯生效", "补缴", "从...起补缴差额"],
    },
    "retroactive_start": {
        "type": "date", "format": "YYYY-MM-DD", "required": False,
        "description": "追溯生效起始日期",
        "search_keywords": ["追溯生效起始", "自...起执行（含补缴）", "补缴起始日期"],
    },
    "coverage_types": {
        "type": "array",
        "items": {"enum": ["养老", "医疗", "失业", "工伤", "生育"]},
        "default": ["养老", "医疗", "失业", "工伤", "生育"],
        "description": "覆盖险种",
        "search_keywords": ["养老保险", "医疗保险", "失业保险", "工伤保险", "生育保险"],
    },
    "special_notes": {
        "type": "string", "max_length": 1000, "required": False,
        "description": "特别说明",
        "search_keywords": ["特别说明", "备注", "注意事项"],
    },
}

SI_EXAMPLE = {
    "si_upper_limit": 35283,
    "si_lower_limit": 6821,
    "is_retroactive": False,
    "coverage_types": ["养老", "医疗", "失业", "工伤", "生育"],
}


# ============================================================
# 1b. 公积金基数 (housing_fund)
# ============================================================

def _hf_validate(data: dict) -> List[str]:
    """公积金数据验证"""
    warnings = []
    hf_upper = data.get("hf_upper_limit")
    hf_lower = data.get("hf_lower_limit")
    if hf_upper and hf_lower and hf_upper <= hf_lower:
        warnings.append("公积金上限必须大于下限")
    if hf_lower and hf_lower < 1000:
        warnings.append(f"公积金下限({hf_lower})偏低，请核实")
    if hf_upper and hf_upper > 40000:
        warnings.append(f"公积金上限({hf_upper})偏高，请核实")
    return warnings


def _hf_create_extension(policy_id: str, data: dict) -> PolicyHousingFund:
    """从提交数据创建公积金扩展记录"""
    from datetime import datetime

    retroactive_months = None
    if data.get("is_retroactive") and data.get("retroactive_start") and data.get("effective_start"):
        try:
            retro_start = datetime.fromisoformat(data["retroactive_start"])
            eff_start = datetime.fromisoformat(data["effective_start"])
            retroactive_months = (
                (eff_start.year - retro_start.year) * 12
                + (eff_start.month - retro_start.month)
            )
        except ValueError:
            pass

    return PolicyHousingFund(
        policy_id=policy_id,
        hf_upper_limit=data.get("hf_upper_limit"),
        hf_lower_limit=data.get("hf_lower_limit"),
        is_retroactive=1 if data.get("is_retroactive") else 0,
        retroactive_start=data.get("retroactive_start"),
        retroactive_months=retroactive_months,
        special_notes=data.get("special_notes"),
    )


def _hf_update_extension(ext: PolicyHousingFund, data: dict) -> None:
    """更新公积金扩展记录"""
    from datetime import datetime

    for field in ["hf_upper_limit", "hf_lower_limit", "retroactive_start", "special_notes"]:
        if data.get(field) is not None:
            setattr(ext, field, data[field])

    if "is_retroactive" in data:
        ext.is_retroactive = 1 if data["is_retroactive"] else 0

    if ext.is_retroactive and ext.retroactive_start and data.get("effective_start"):
        try:
            retro_start = datetime.fromisoformat(ext.retroactive_start)
            eff_start = datetime.fromisoformat(data["effective_start"])
            ext.retroactive_months = (
                (eff_start.year - retro_start.year) * 12
                + (eff_start.month - retro_start.month)
            )
        except ValueError:
            pass


def _hf_to_response(ext: PolicyHousingFund) -> dict:
    """将公积金扩展模型转为响应 dict"""
    return {
        "hf_upper_limit": ext.hf_upper_limit,
        "hf_lower_limit": ext.hf_lower_limit,
        "is_retroactive": ext.is_retroactive == 1,
        "retroactive_start": ext.retroactive_start,
        "retroactive_months": ext.retroactive_months,
        "change_rate_upper": float(ext.change_rate_upper) if ext.change_rate_upper else None,
        "change_rate_lower": float(ext.change_rate_lower) if ext.change_rate_lower else None,
        "special_notes": ext.special_notes,
    }


HF_FIELD_SCHEMA = {
    "hf_upper_limit": {
        "type": "integer", "unit": "元/月", "required": True,
        "description": "公积金缴存基数上限",
        "search_keywords": ["公积金缴存基数上限", "住房公积金基数上限", "公积金上限"],
    },
    "hf_lower_limit": {
        "type": "integer", "unit": "元/月", "required": True,
        "description": "公积金缴存基数下限",
        "search_keywords": ["公积金缴存基数下限", "住房公积金基数下限", "公积金下限"],
    },
    "is_retroactive": {
        "type": "boolean", "default": False,
        "description": "是否追溯生效",
        "search_keywords": ["追溯执行", "追溯生效", "补缴", "从...起补缴差额"],
    },
    "retroactive_start": {
        "type": "date", "format": "YYYY-MM-DD", "required": False,
        "description": "追溯生效起始日期",
        "search_keywords": ["追溯生效起始", "自...起执行（含补缴）", "补缴起始日期"],
    },
    "special_notes": {
        "type": "string", "max_length": 1000, "required": False,
        "description": "特别说明",
        "search_keywords": ["特别说明", "备注", "注意事项"],
    },
}

HF_EXAMPLE = {
    "hf_upper_limit": 35283,
    "hf_lower_limit": 2420,
    "is_retroactive": False,
}


# ============================================================
# 2. 社会平均工资 (avg_salary)
# ============================================================

def _avg_validate(data: dict) -> List[str]:
    """社会平均工资数据验证"""
    warnings = []
    total = data.get("avg_salary_total")
    if total and total < 20000:
        warnings.append(f"年平均工资({total})偏低，请核实")
    if total and total > 300000:
        warnings.append(f"年平均工资({total})偏高，请核实")
    return warnings


def _avg_create_extension(policy_id: str, data: dict) -> PolicyAvgSalary:
    """从提交数据创建社平工资扩展记录"""
    total = data.get("avg_salary_total")
    monthly = data.get("avg_salary_monthly")
    if not monthly and total:
        monthly = round(total / 12)

    return PolicyAvgSalary(
        policy_id=policy_id,
        avg_salary_total=total,
        avg_salary_monthly=monthly,
        avg_salary_on_post=data.get("avg_salary_on_post"),
        avg_salary_non_private=data.get("avg_salary_non_private"),
        avg_salary_private=data.get("avg_salary_private"),
        statistics_year=data.get("statistics_year"),
        growth_rate=str(data["growth_rate"]) if data.get("growth_rate") is not None else None,
        prev_avg_salary_total=data.get("prev_avg_salary_total"),
        special_notes=data.get("special_notes"),
    )


def _avg_update_extension(ext: PolicyAvgSalary, data: dict) -> None:
    """更新社平工资扩展记录"""
    for field in [
        "avg_salary_total", "avg_salary_monthly",
        "avg_salary_on_post", "avg_salary_non_private", "avg_salary_private",
        "statistics_year", "prev_avg_salary_total", "special_notes",
    ]:
        if data.get(field) is not None:
            setattr(ext, field, data[field])

    if "growth_rate" in data and data["growth_rate"] is not None:
        ext.growth_rate = str(data["growth_rate"])

    # 自动计算月均
    if ext.avg_salary_total and not ext.avg_salary_monthly:
        ext.avg_salary_monthly = round(ext.avg_salary_total / 12)


def _avg_to_response(ext: PolicyAvgSalary) -> dict:
    """将社平工资扩展模型转为响应 dict"""
    return {
        "avg_salary_total": ext.avg_salary_total,
        "avg_salary_monthly": ext.avg_salary_monthly,
        "avg_salary_on_post": ext.avg_salary_on_post,
        "avg_salary_non_private": ext.avg_salary_non_private,
        "avg_salary_private": ext.avg_salary_private,
        "statistics_year": ext.statistics_year,
        "growth_rate": float(ext.growth_rate) if ext.growth_rate else None,
        "prev_avg_salary_total": ext.prev_avg_salary_total,
        "special_notes": ext.special_notes,
    }


AVG_FIELD_SCHEMA = {
    "avg_salary_total": {
        "type": "integer", "unit": "元/年", "required": True,
        "description": "全口径城镇单位就业人员平均工资",
        "search_keywords": ["全口径城镇单位就业人员平均工资", "年平均工资", "平均工资"],
    },
    "avg_salary_monthly": {
        "type": "integer", "unit": "元/月", "required": False,
        "description": "月平均工资（自动计算）",
        "search_keywords": ["月平均工资", "月均工资"],
    },
    "avg_salary_on_post": {
        "type": "integer", "unit": "元/年", "required": False,
        "description": "在岗职工平均工资",
        "search_keywords": ["在岗职工平均工资", "在岗职工年均工资"],
    },
    "avg_salary_non_private": {
        "type": "integer", "unit": "元/年", "required": False,
        "description": "城镇非私营单位平均工资",
        "search_keywords": ["城镇非私营单位平均工资", "非私营单位年均工资"],
    },
    "avg_salary_private": {
        "type": "integer", "unit": "元/年", "required": False,
        "description": "城镇私营单位平均工资",
        "search_keywords": ["城镇私营单位平均工资", "私营单位年均工资"],
    },
    "statistics_year": {
        "type": "integer", "required": False,
        "description": "统计年度",
        "search_keywords": ["统计年度", "数据年份", "年度"],
    },
    "growth_rate": {
        "type": "number", "unit": "%", "required": False,
        "description": "增长率",
        "search_keywords": ["增长率", "同比增长", "涨幅"],
    },
    "special_notes": {
        "type": "string", "max_length": 1000, "required": False,
        "description": "特别说明",
        "search_keywords": ["特别说明", "备注", "注意事项"],
    },
}

AVG_EXAMPLE = {
    "avg_salary_total": 124000,
    "avg_salary_monthly": 10333,
    "avg_salary_non_private": 134000,
    "avg_salary_private": 72000,
    "statistics_year": 2023,
    "growth_rate": 5.8,
}


# ============================================================
# 3. 人才政策 (talent_policy)
# ============================================================

def _talent_validate(data: dict) -> List[str]:
    """人才政策数据验证"""
    warnings = []
    categories = data.get("talent_categories", [])
    if not categories:
        warnings.append("建议提供人才分类信息")
    docs = data.get("required_documents", [])
    if not docs:
        warnings.append("建议提供所需材料清单")
    return warnings


def _talent_create_extension(policy_id: str, data: dict) -> PolicyTalent:
    """从提交数据创建人才政策扩展记录"""
    return PolicyTalent(
        policy_id=policy_id,
        talent_categories=json.dumps(
            data.get("talent_categories", []), ensure_ascii=False
        ),
        certification_requirements=json.dumps(
            data.get("certification_requirements", {}), ensure_ascii=False
        ),
        required_documents=json.dumps(
            data.get("required_documents", []), ensure_ascii=False
        ),
        subsidy_standards=json.dumps(
            data.get("subsidy_standards", {}), ensure_ascii=False
        ),
        eligibility_summary=data.get("eligibility_summary"),
        age_limit=data.get("age_limit"),
        education_requirement=data.get("education_requirement"),
        service_years_required=data.get("service_years_required"),
        application_channel=data.get("application_channel"),
        special_notes=data.get("special_notes"),
    )


def _talent_update_extension(ext: PolicyTalent, data: dict) -> None:
    """更新人才政策扩展记录"""
    json_fields = [
        "talent_categories", "certification_requirements",
        "required_documents", "subsidy_standards",
    ]
    for field in json_fields:
        if field in data:
            setattr(ext, field, json.dumps(data[field], ensure_ascii=False))

    str_fields = [
        "eligibility_summary", "education_requirement",
        "application_channel", "special_notes",
    ]
    for field in str_fields:
        if data.get(field) is not None:
            setattr(ext, field, data[field])

    int_fields = ["age_limit", "service_years_required"]
    for field in int_fields:
        if data.get(field) is not None:
            setattr(ext, field, data[field])


def _talent_to_response(ext: PolicyTalent) -> dict:
    """将人才政策扩展模型转为响应 dict"""
    return {
        "talent_categories": json.loads(ext.talent_categories) if ext.talent_categories else [],
        "certification_requirements": json.loads(ext.certification_requirements) if ext.certification_requirements else {},
        "required_documents": json.loads(ext.required_documents) if ext.required_documents else [],
        "subsidy_standards": json.loads(ext.subsidy_standards) if ext.subsidy_standards else {},
        "eligibility_summary": ext.eligibility_summary,
        "age_limit": ext.age_limit,
        "education_requirement": ext.education_requirement,
        "service_years_required": ext.service_years_required,
        "application_channel": ext.application_channel,
        "special_notes": ext.special_notes,
    }


TALENT_FIELD_SCHEMA = {
    "talent_categories": {
        "type": "array", "items": {"type": "string"}, "required": False,
        "description": "人才分类/层级列表",
        "search_keywords": ["人才层次", "人才类型", "人才分类", "A类", "B类", "C类"],
    },
    "certification_requirements": {
        "type": "object", "required": False,
        "description": "认定条件（按人才类别，key=类别名, value=条件描述）",
        "search_keywords": ["认定条件", "认定标准", "申报条件", "资格条件"],
    },
    "required_documents": {
        "type": "array", "items": {"type": "string"}, "required": False,
        "description": "所需材料清单",
        "search_keywords": ["所需材料", "申报材料", "提交材料", "申请材料"],
    },
    "subsidy_standards": {
        "type": "object", "required": False,
        "description": "补贴标准（key=补贴类型, value=标准描述）",
        "search_keywords": ["补贴标准", "奖励标准", "资助金额", "补助标准"],
    },
    "eligibility_summary": {
        "type": "string", "max_length": 2000, "required": False,
        "description": "申请条件概述",
        "search_keywords": ["申请条件", "认定条件概述", "基本条件"],
    },
    "age_limit": {
        "type": "integer", "required": False,
        "description": "年龄限制",
        "search_keywords": ["年龄要求", "年龄限制", "不超过...周岁"],
    },
    "education_requirement": {
        "type": "string", "required": False,
        "description": "学历要求",
        "search_keywords": ["学历要求", "学位要求", "本科及以上", "硕士", "博士"],
    },
    "service_years_required": {
        "type": "integer", "required": False,
        "description": "服务年限要求（年）",
        "search_keywords": ["服务年限", "在本市工作不少于", "劳动合同期限"],
    },
    "application_channel": {
        "type": "string", "required": False,
        "description": "申报渠道/网址",
        "search_keywords": ["申报渠道", "申报网址", "办理方式", "线上申报"],
    },
    "special_notes": {
        "type": "string", "max_length": 1000, "required": False,
        "description": "特别说明",
        "search_keywords": ["特别说明", "备注", "注意事项"],
    },
}

TALENT_EXAMPLE = {
    "talent_categories": ["A类（国际顶尖人才）", "B类（国家级领军人才）", "C类（地方高层次人才）"],
    "certification_requirements": {
        "A类": "诺贝尔奖、图灵奖等国际大奖获得者",
        "B类": "国家级学术技术带头人、长江学者等",
        "C类": "省级以上专业技术拔尖人才",
    },
    "required_documents": ["身份证明", "学历学位证书", "工作合同", "社保缴纳证明", "人才认定申请表"],
    "subsidy_standards": {
        "住房补贴": "A类最高200万，B类最高100万，C类最高50万",
        "生活补贴": "A类每月10000元，B类每月5000元",
    },
    "eligibility_summary": "在本市全职工作，签订3年以上劳动合同，缴纳社保满6个月",
    "age_limit": 55,
    "education_requirement": "本科及以上",
}


# ============================================================
# 注册入口
# ============================================================

def register_builtin_types() -> None:
    """注册所有内置政策类型，应在应用启动时调用"""
    reg = get_registry()

    # 避免重复注册（热重载时）
    if reg.has("social_insurance"):
        return

    # 1. 社保基数
    reg.register(PolicyTypeDescriptor(
        type_code="social_insurance",
        type_name="社保基数",
        description="各地区社会保险缴费基数上下限政策",
        extension_table="policy_social_insurance",
        is_builtin=True,
        extension_model=PolicySocialInsurance,
        create_schema=PolicySocialInsuranceCreate,
        response_schema=PolicySocialInsuranceResponse,
        field_schema=SI_FIELD_SCHEMA,
        validation_rules=[
            "si_upper_limit > si_lower_limit",
            "effective_start >= published_at (unless is_retroactive=true)",
        ],
        example_data=SI_EXAMPLE,
        validator_func=_si_validate,
        create_extension_func=_si_create_extension,
        update_extension_func=_si_update_extension,
        to_response_func=_si_to_response,
        sort_order=0,
    ))

    # 1b. 公积金基数
    reg.register(PolicyTypeDescriptor(
        type_code="housing_fund",
        type_name="公积金基数",
        description="各地区住房公积金缴存基数上下限政策",
        extension_table="policy_housing_fund",
        is_builtin=True,
        extension_model=PolicyHousingFund,
        create_schema=PolicyHousingFundCreate,
        response_schema=PolicyHousingFundResponse,
        field_schema=HF_FIELD_SCHEMA,
        validation_rules=[
            "hf_upper_limit > hf_lower_limit",
            "effective_start >= published_at (unless is_retroactive=true)",
        ],
        example_data=HF_EXAMPLE,
        validator_func=_hf_validate,
        create_extension_func=_hf_create_extension,
        update_extension_func=_hf_update_extension,
        to_response_func=_hf_to_response,
        sort_order=1,
    ))

    # 2. 社会平均工资
    reg.register(PolicyTypeDescriptor(
        type_code="avg_salary",
        type_name="社会平均工资",
        description="各地区社会平均工资（全口径、在岗职工、非私营/私营单位等）",
        extension_table="policy_avg_salary",
        is_builtin=True,
        extension_model=PolicyAvgSalary,
        create_schema=AvgSalaryCreate,
        response_schema=AvgSalaryResponse,
        field_schema=AVG_FIELD_SCHEMA,
        validation_rules=[
            "avg_salary_total > 0",
            "avg_salary_total 通常在 20000-300000 元/年范围内",
        ],
        example_data=AVG_EXAMPLE,
        validator_func=_avg_validate,
        create_extension_func=_avg_create_extension,
        update_extension_func=_avg_update_extension,
        to_response_func=_avg_to_response,
        sort_order=2,
    ))

    # 3. 人才政策
    reg.register(PolicyTypeDescriptor(
        type_code="talent_policy",
        type_name="人才政策",
        description="各地区人才引进、认定、补贴相关政策",
        extension_table="policy_talent",
        is_builtin=True,
        extension_model=PolicyTalent,
        create_schema=TalentPolicyCreate,
        response_schema=TalentPolicyResponse,
        field_schema=TALENT_FIELD_SCHEMA,
        validation_rules=[
            "建议提供人才分类信息",
            "建议提供所需材料清单",
        ],
        example_data=TALENT_EXAMPLE,
        validator_func=_talent_validate,
        create_extension_func=_talent_create_extension,
        update_extension_func=_talent_update_extension,
        to_response_func=_talent_to_response,
        sort_order=3,
    ))


async def sync_db_policy_types(session) -> int:
    """
    从数据库加载动态政策类型并注册到 Python Registry。

    在应用启动时调用（在 register_builtin_types 之后）。
    也在管理后台创建/更新/删除类型后调用以刷新内存。

    Returns:
        注册的动态类型数量
    """
    from sqlalchemy import select
    from app.models.policy_type import PolicyTypeDefinition
    from app.services.policy_type_registry import (
        PolicyTypeDescriptor,
        _dynamic_validator,
        get_registry,
    )

    reg = get_registry()

    result = await session.execute(
        select(PolicyTypeDefinition).where(
            PolicyTypeDefinition.is_builtin == 0,
            PolicyTypeDefinition.is_active == 1,
        )
    )
    db_types = result.scalars().all()

    count = 0
    for t in db_types:
        field_schema = json.loads(t.field_schema) if t.field_schema else {}
        validation_rules = json.loads(t.validation_rules) if t.validation_rules else []
        example_data = json.loads(t.example_data) if t.example_data else {}

        desc = PolicyTypeDescriptor(
            type_code=t.type_code,
            type_name=t.type_name,
            description=t.description or "",
            extension_table=None,
            is_builtin=False,
            field_schema=field_schema,
            validation_rules=validation_rules,
            example_data=example_data,
            validator_func=_dynamic_validator(field_schema),
            icon=t.icon,
            sort_order=t.sort_order or 100 + count,
        )

        reg.register_or_update(desc)
        count += 1

    return count


async def sync_builtin_types_to_db(session) -> int:
    """
    将内置类型写入数据库（如果还不存在）。

    这样管理后台可以展示所有类型（包括内置的），但内置类型标记为不可删除。
    """
    from sqlalchemy import select
    from app.models.policy_type import PolicyTypeDefinition

    reg = get_registry()
    count = 0

    for desc in reg.list_all():
        if not desc.is_builtin:
            continue

        result = await session.execute(
            select(PolicyTypeDefinition).where(
                PolicyTypeDefinition.type_code == desc.type_code
            )
        )
        existing = result.scalar_one_or_none()

        if not existing:
            from datetime import datetime
            now = datetime.utcnow().isoformat()

            td = PolicyTypeDefinition(
                type_code=desc.type_code,
                type_name=desc.type_name,
                description=desc.description,
                extension_table=desc.extension_table,
                field_schema=json.dumps(desc.field_schema, ensure_ascii=False),
                validation_rules=json.dumps(desc.validation_rules, ensure_ascii=False),
                example_data=json.dumps(desc.example_data, ensure_ascii=False),
                is_builtin=1,
                is_active=1,
                sort_order=desc.sort_order,
                icon=desc.icon,
                created_at=now,
                updated_at=now,
            )
            session.add(td)
            count += 1

    if count > 0:
        await session.commit()

    return count
