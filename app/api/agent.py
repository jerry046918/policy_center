"""Agent REST API - 外部 Agent 调用接口（支持多类型扩展）"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json
import uuid

from app.database import get_session
from app.api.auth import get_current_agent, AgentAuth
from app.models.review import ReviewQueue
from app.models.policy import Policy, PolicySocialInsurance
from app.services.policy_type_registry import get_registry
from app.services.policy_service import PolicyService

router = APIRouter()


# ==================== 请求/响应模型 ====================

class PolicyStructuredData(BaseModel):
    """
    政策结构化数据（通用 + 类型特定）

    通用字段 (title, region_code, dates) 适用于所有类型。
    类型特定字段直接平铺在同一层级，由 policy_type 决定哪些字段有效。

    为向后兼容，社保类型 (social_insurance) 的字段仍然作为顶级字段。
    """
    # ── 通用字段 ──
    title: str = Field(..., max_length=500, description="政策完整名称")
    region_code: str = Field(..., pattern=r"^\d{6}$", description="六位行政区划码")
    published_at: str = Field(..., description="发布日期 YYYY-MM-DD")
    effective_start: str = Field(..., description="生效开始日期 YYYY-MM-DD")
    effective_end: Optional[str] = Field(None, description="生效结束日期 YYYY-MM-DD")

    # ── 社保类型字段（向后兼容，非必填） ──
    si_upper_limit: Optional[int] = Field(None, gt=0, description="社保基数上限（元/月）")
    si_lower_limit: Optional[int] = Field(None, gt=0, description="社保基数下限（元/月）")
    is_retroactive: bool = Field(default=False, description="是否追溯生效")
    retroactive_start: Optional[str] = Field(None, description="追溯生效起始日期")
    coverage_types: List[str] = Field(
        default=["养老", "医疗", "失业", "工伤", "生育"],
        description="覆盖险种"
    )
    special_notes: Optional[str] = Field(None, max_length=1000, description="特别说明")

    # ── 类型扩展数据入口 ──
    type_data: Optional[Dict[str, Any]] = Field(
        None,
        description="类型特定的扩展数据（非 social_insurance 类型时使用此字段传递类型特有数据）"
    )

    # 政策类型标记（嵌入 structured_data 内部，方便审核后使用）
    policy_type: Optional[str] = Field(None, description="政策类型编码（可选，默认由外层决定）")

    model_config = {"extra": "allow"}  # 允许额外字段，以支持未来类型的数据


class SourceDocument(BaseModel):
    """单个来源文档"""
    title: Optional[str] = Field(None, description="来源标题")
    doc_number: Optional[str] = Field(None, max_length=100, description="官方文号")
    url: str = Field(..., description="来源 URL")
    extracted_text: Optional[str] = Field(None, description="提取的文本内容")


class RawContent(BaseModel):
    """原始内容（支持多个来源）"""
    model_config = {"extra": "ignore"}

    sources: List[SourceDocument] | None = Field(default=None, description="来源文档列表（推荐）")
    extracted_text: str | None = Field(default=None, description="提取的文本内容")
    source_document_base64: str | None = Field(default=None, description="原始文档 Base64 编码")

    def to_sources_list(self) -> List[Dict[str, Any]]:
        """转换为统一的来源列表格式"""
        if self.sources:
            return [s.model_dump(exclude_none=True) for s in self.sources]
        return []


class SubmitPolicyRequest(BaseModel):
    """提交政策请求"""
    idempotency_key: Optional[str] = Field(None, description="幂等键")
    policy_type: str = Field(default="social_insurance", description="政策类型编码")
    structured_data: PolicyStructuredData = Field(..., description="结构化政策数据")
    raw_content: RawContent = Field(..., description="原始内容")
    priority: str = Field(default="normal", description="优先级: urgent/high/normal/low")

    submit_type: str = Field(default="new", description="提交类型: new(新增) 或 update(更新)")
    existing_policy_id: Optional[str] = Field(None, description="更新时的原政策ID")
    change_description: Optional[str] = Field(None, max_length=2000, description="更新时的修改说明")


class SubmitPolicyResponse(BaseModel):
    """提交政策响应"""
    success: bool
    review_id: Optional[str] = None
    status: str
    policy_id: Optional[str] = None
    policy_type: Optional[str] = None
    warnings: List[str] = []
    estimated_review_time: Optional[str] = None
    message: Optional[str] = None


class PolicyQueryResponse(BaseModel):
    """政策查询响应"""
    success: bool
    data: List[Dict[str, Any]]
    total: int


class DuplicateCheckResponse(BaseModel):
    """重复检查响应"""
    success: bool
    is_duplicate: bool
    existing_policy_id: Optional[str] = None
    existing_status: Optional[str] = None
    existing_policy_type: Optional[str] = None
    similarity_score: float


class SubmissionResponse(BaseModel):
    """提交记录响应"""
    success: bool
    data: List[Dict[str, Any]]
    total: int


# ==================== AI 分析辅助函数 ====================

async def _run_ai_analysis(data: dict, policy_type: str = "social_insurance") -> Dict[str, Any]:
    """AI 分析（简化版，支持多类型）"""
    warnings = []
    risk_tags = []
    validation = {"limits_valid": True}

    registry = get_registry()
    desc = registry.get(policy_type)

    # 使用注册的验证函数
    if desc and desc.validator_func:
        type_warnings = desc.validator_func(data)
        warnings.extend(type_warnings)

    # 追溯检查（通用）
    effective_start = data.get("effective_start")
    published_at = data.get("published_at")
    is_retroactive = data.get("is_retroactive", False)

    if effective_start and published_at:
        try:
            eff_date = datetime.strptime(effective_start, "%Y-%m-%d")
            pub_date = datetime.strptime(published_at, "%Y-%m-%d")
            if eff_date < pub_date:
                risk_tags.append("追溯生效")
                if not is_retroactive:
                    warnings.append(f"生效日期早于发布日期，建议标记追溯")
        except (ValueError, TypeError):
            pass

    # 风险等级
    risk_level = "low"
    if len(risk_tags) >= 2:
        risk_level = "high"
    elif len(risk_tags) >= 1:
        risk_level = "medium"

    return {
        "validation": validation,
        "warnings": warnings,
        "risk_level": risk_level,
        "risk_tags": risk_tags
    }


# ==================== API 端点 ====================

@router.post("/submit", response_model=SubmitPolicyResponse)
async def submit_policy(
    request: SubmitPolicyRequest,
    agent: AgentAuth = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session)
):
    """
    提交政策到审核队列（支持多类型）

    通过 policy_type 指定政策类型。默认 "social_insurance"。
    type_data 中传递该类型特有的扩展数据。
    """
    registry = get_registry()
    policy_type = request.policy_type

    # 验证政策类型
    if not registry.has(policy_type):
        valid_types = ", ".join(registry.list_type_codes())
        raise HTTPException(
            status_code=400,
            detail=f"不支持的政策类型: '{policy_type}'。可用类型: {valid_types}"
        )

    # 验证提交类型
    if request.submit_type not in ["new", "update"]:
        raise HTTPException(status_code=400, detail="submit_type 必须是 'new' 或 'update'")

    # 更新验证
    if request.submit_type == "update":
        if not request.existing_policy_id:
            raise HTTPException(status_code=400, detail="更新提交必须提供 existing_policy_id")

        existing_policy = await session.execute(
            select(Policy).where(Policy.policy_id == request.existing_policy_id)
        )
        if not existing_policy.scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"原政策 {request.existing_policy_id} 不存在")

        if not request.change_description:
            warnings_msg = "建议提供 change_description 说明修改内容"
        else:
            warnings_msg = None
    else:
        warnings_msg = None

    warnings = []

    # 幂等性检查
    if request.idempotency_key:
        result = await session.execute(
            select(ReviewQueue).where(
                ReviewQueue.idempotency_key == request.idempotency_key
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return SubmitPolicyResponse(
                success=True,
                review_id=existing.review_id,
                status="already_submitted",
                policy_id=existing.policy_id,
                policy_type=policy_type,
                message="该政策已提交，请勿重复提交"
            )

    # 生成 policy_id
    if request.submit_type == "update":
        policy_id = request.existing_policy_id
    else:
        policy_id = str(uuid.uuid4())

    # 构建提交数据（将 policy_type 嵌入，方便审核后使用）
    submitted_data = request.structured_data.model_dump()
    submitted_data["policy_type"] = policy_type

    # AI 分析
    ai_analysis = await _run_ai_analysis(submitted_data, policy_type)
    warnings = ai_analysis.get("warnings", [])

    if warnings_msg:
        warnings.append(warnings_msg)

    # 计算 SLA
    sla_hours = {"urgent": 1, "high": 4, "normal": 24, "low": 72}.get(request.priority, 24)
    sla_deadline = (datetime.utcnow() + timedelta(hours=sla_hours)).isoformat()

    # 转换 raw_evidence
    raw_evidence_data = {"sources": request.raw_content.to_sources_list()}

    # 创建审核记录
    review = ReviewQueue(
        policy_id=policy_id,
        idempotency_key=request.idempotency_key,
        submitted_data=json.dumps(submitted_data, ensure_ascii=False),
        raw_evidence=json.dumps(raw_evidence_data, ensure_ascii=False),
        ai_validation=json.dumps(ai_analysis.get("validation", {}), ensure_ascii=False),
        risk_level=ai_analysis.get("risk_level", "low"),
        risk_tags=json.dumps(ai_analysis.get("risk_tags", []), ensure_ascii=False),
        status="pending",
        priority=request.priority,
        submitted_by=agent.agent_id,
        sla_deadline=sla_deadline,
        submit_type=request.submit_type,
        existing_policy_id=request.existing_policy_id,
        change_description=request.change_description
    )

    session.add(review)
    await session.commit()
    await session.refresh(review)

    return SubmitPolicyResponse(
        success=True,
        review_id=review.review_id,
        status="pending_review",
        policy_id=policy_id,
        policy_type=policy_type,
        warnings=warnings,
        estimated_review_time=f"{sla_hours}h"
    )


@router.get("/policies", response_model=PolicyQueryResponse)
async def query_policies(
    region_code: Optional[str] = Query(default=None, description="地区代码"),
    effective_year: Optional[int] = Query(default=None, description="生效年份"),
    policy_type: Optional[str] = Query(default=None, description="政策类型筛选"),
    is_retroactive: Optional[bool] = Query(default=None, description="是否追溯"),
    limit: int = Query(default=10, ge=1, le=100, description="返回数量限制"),
    agent: AgentAuth = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session)
):
    """
    查询已发布政策（支持多类型筛选）
    """
    service = PolicyService(session)

    query = select(Policy).where(
        Policy.status == "active",
        Policy.deleted_at.is_(None)
    )

    if region_code:
        query = query.where(Policy.region_code == region_code)
    if effective_year:
        query = query.where(Policy.policy_year == effective_year)
    if policy_type:
        query = query.where(Policy.policy_type == policy_type)

    query = query.order_by(Policy.effective_start.desc()).limit(limit)

    result = await session.execute(query)
    policies = result.scalars().all()

    data = []
    for p in policies:
        item = {
            "policy_id": p.policy_id,
            "policy_type": p.policy_type,
            "title": p.title,
            "region_code": p.region_code,
            "effective_start": p.effective_start,
            "effective_end": p.effective_end,
        }

        # 获取扩展数据
        ext = await service._get_extension(p.policy_id, p.policy_type)
        type_data = service._extension_to_response(ext, p.policy_type)
        if type_data:
            item["type_data"] = type_data

        # 向后兼容：社保类型继续平铺
        if p.policy_type == "social_insurance" and ext:
            item.update({
                "si_upper_limit": ext.si_upper_limit,
                "si_lower_limit": ext.si_lower_limit,
                "is_retroactive": ext.is_retroactive == 1,
            })
        elif p.policy_type == "housing_fund" and ext:
            item.update({
                "hf_upper_limit": ext.hf_upper_limit,
                "hf_lower_limit": ext.hf_lower_limit,
                "is_retroactive": ext.is_retroactive == 1,
            })

        data.append(item)

    return PolicyQueryResponse(success=True, data=data, total=len(data))


@router.get("/check-duplicate", response_model=DuplicateCheckResponse)
async def check_duplicate(
    region_code: Optional[str] = Query(default=None, description="地区代码"),
    effective_start: Optional[str] = Query(default=None, description="生效日期"),
    policy_type: Optional[str] = Query(default=None, description="政策类型"),
    agent: AgentAuth = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session)
):
    """
    检查重复政策（考虑 policy_type 维度）

    不同政策类型之间互不视为重复。
    """
    service = PolicyService(session)
    result = await service.check_duplicate(
        region_code=region_code,
        effective_start=effective_start,
        policy_type=policy_type,
    )

    return DuplicateCheckResponse(
        success=True,
        is_duplicate=result.get("is_duplicate", False),
        existing_policy_id=result.get("existing_policy_id"),
        existing_status=result.get("existing_status"),
        existing_policy_type=result.get("existing_policy_type"),
        similarity_score=result.get("similarity_score", 0.0)
    )


@router.get("/schema")
async def get_policy_schema(
    policy_type: str = Query(default="social_insurance", description="政策类型"),
    include_examples: bool = Query(default=True, description="是否包含示例"),
    agent: AgentAuth = Depends(get_current_agent)
):
    """
    获取政策 Schema 定义（支持多类型）

    通过 policy_type 参数获取不同类型的字段定义、校验规则和示例。
    不传 policy_type 时返回所有类型的概览。
    """
    registry = get_registry()

    # 如果请求特定类型
    desc = registry.get(policy_type)
    if not desc:
        # 返回所有类型的概览
        all_types = registry.list_all()
        return {
            "success": True,
            "message": f"未知的政策类型 '{policy_type}'，以下是所有支持的类型",
            "available_types": [
                {
                    "type_code": t.type_code,
                    "type_name": t.type_name,
                    "description": t.description,
                }
                for t in all_types
            ]
        }

    # 通用字段 schema
    common_fields = {
        "title": {"type": "string", "max_length": 500, "required": True, "description": "政策完整名称"},
        "region_code": {"type": "string", "pattern": "^\\d{6}$", "required": True, "description": "六位行政区划码"},
        "published_at": {"type": "date", "format": "YYYY-MM-DD", "required": True, "description": "发布日期"},
        "effective_start": {"type": "date", "format": "YYYY-MM-DD", "required": True, "description": "生效开始日期"},
        "effective_end": {"type": "date", "format": "YYYY-MM-DD", "required": False, "description": "生效结束日期"},
    }

    schema = {
        "policy_type": policy_type,
        "type_name": desc.type_name,
        "description": desc.description,
        "common_fields": common_fields,
        "type_specific_fields": desc.field_schema,
        "raw_content": {
            "sources": {
                "type": "array",
                "description": "来源文档列表",
                "items": {
                    "title": {"type": "string", "description": "来源标题"},
                    "doc_number": {"type": "string", "max_length": 100, "description": "官方文号（可选）"},
                    "url": {"type": "string", "required": True, "description": "来源URL"},
                    "extracted_text": {"type": "string", "description": "提取的文本内容"}
                }
            }
        },
        "validation_rules": desc.validation_rules,
    }

    if include_examples and desc.example_data:
        schema["examples"] = [
            {
                "policy_type": policy_type,
                "structured_data": {
                    "title": f"示例-{desc.type_name}政策",
                    "region_code": "110000",
                    "published_at": "2024-06-20",
                    "effective_start": "2024-07-01",
                    **desc.example_data,
                },
                "raw_content": {
                    "sources": [
                        {
                            "title": "示例来源文档",
                            "url": "https://example.com/policy/123",
                            "extracted_text": "..."
                        }
                    ]
                }
            }
        ]

    # 同时返回所有可用类型的列表
    all_types = registry.list_all()
    schema["available_types"] = [
        {
            "type_code": t.type_code,
            "type_name": t.type_name,
            "description": t.description,
        }
        for t in all_types
    ]

    return {"success": True, "schema": schema}


@router.get("/submissions", response_model=SubmissionResponse)
async def get_submissions(
    status: Optional[str] = Query(default=None, description="审核状态"),
    limit: int = Query(default=20, ge=1, le=100, description="返回数量限制"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
    agent: AgentAuth = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session)
):
    """查询自己的提交记录"""
    query = select(ReviewQueue).where(
        ReviewQueue.submitted_by == agent.agent_id
    )

    if status:
        query = query.where(ReviewQueue.status == status)

    query = query.order_by(ReviewQueue.submitted_at.desc()).offset(offset).limit(limit)

    result = await session.execute(query)
    submissions = result.scalars().all()

    data = []
    for s in submissions:
        submitted_data = json.loads(s.submitted_data) if s.submitted_data else {}
        data.append({
            "review_id": s.review_id,
            "policy_id": s.policy_id,
            "policy_type": submitted_data.get("policy_type", "social_insurance"),
            "status": s.status,
            "priority": s.priority,
            "risk_level": s.risk_level,
            "submitted_at": s.submitted_at,
            "sla_deadline": s.sla_deadline,
            "reviewer_notes": s.reviewer_notes,
            "submit_type": s.submit_type,
            "existing_policy_id": s.existing_policy_id,
            "change_description": s.change_description,
            "final_action": s.final_action
        })

    return SubmissionResponse(success=True, data=data, total=len(data))
