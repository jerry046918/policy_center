"""Agent REST API - 外部 Agent 调用接口"""
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

router = APIRouter()


# ==================== 请求/响应模型 ====================

class PolicyStructuredData(BaseModel):
    """政策结构化数据"""
    title: str = Field(..., max_length=500, description="政策完整名称")
    region_code: str = Field(..., pattern=r"^\d{6}$", description="六位行政区划码")
    published_at: str = Field(..., description="发布日期 YYYY-MM-DD")
    effective_start: str = Field(..., description="生效开始日期 YYYY-MM-DD")
    effective_end: Optional[str] = Field(None, description="生效结束日期 YYYY-MM-DD")
    si_upper_limit: int = Field(..., gt=0, description="社保基数上限（元/月）")
    si_lower_limit: int = Field(..., gt=0, description="社保基数下限（元/月）")
    hf_upper_limit: Optional[int] = Field(None, gt=0, description="公积金上限（元/月）")
    hf_lower_limit: Optional[int] = Field(None, gt=0, description="公积金下限（元/月）")
    is_retroactive: bool = Field(default=False, description="是否追溯生效")
    retroactive_start: Optional[str] = Field(None, description="追溯生效起始日期")
    coverage_types: List[str] = Field(
        default=["养老", "医疗", "失业", "工伤", "生育"],
        description="覆盖险种"
    )
    special_notes: Optional[str] = Field(None, max_length=1000, description="特别说明")


class SourceDocument(BaseModel):
    """单个来源文档"""
    title: Optional[str] = Field(None, description="来源标题，如：社保政策文件、公积金政策文件")
    doc_number: Optional[str] = Field(None, max_length=100, description="官方文号")
    url: str = Field(..., description="来源 URL")
    extracted_text: Optional[str] = Field(None, description="提取的文本内容")


class RawContent(BaseModel):
    """原始内容（支持多个来源）"""
    model_config = {"extra": "ignore"}

    # 新格式：多个来源
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
    idempotency_key: Optional[str] = Field(None, description="幂等键，防止重复提交")
    policy_type: str = Field(default="social_insurance_base", description="政策类型")
    structured_data: PolicyStructuredData = Field(..., description="结构化政策数据")
    raw_content: RawContent = Field(..., description="原始内容")
    priority: str = Field(default="normal", description="优先级: urgent/high/normal/low")

    # 提交类型相关字段
    submit_type: str = Field(default="new", description="提交类型: new(新增) 或 update(更新)")
    existing_policy_id: Optional[str] = Field(None, description="更新时的原政策ID")
    change_description: Optional[str] = Field(None, max_length=2000, description="更新时的修改说明")


class SubmitPolicyResponse(BaseModel):
    """提交政策响应"""
    success: bool
    review_id: Optional[str] = None
    status: str
    policy_id: Optional[str] = None
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
    similarity_score: float


class SubmissionResponse(BaseModel):
    """提交记录响应"""
    success: bool
    data: List[Dict[str, Any]]
    total: int


# ==================== AI 分析辅助函数 ====================

async def _run_ai_analysis(data: dict) -> Dict[str, Any]:
    """AI 分析（简化版）"""
    warnings = []
    risk_tags = []

    validation = {"limits_valid": True}

    # 1. 上下限校验
    si_upper = data.get("si_upper_limit")
    si_lower = data.get("si_lower_limit")
    if si_upper and si_lower and si_upper <= si_lower:
        validation["limits_valid"] = False
        warnings.append("上限必须大于下限")

    # 2. 追溯检查
    effective_start = data.get("effective_start")
    published_at = data.get("published_at")
    is_retroactive = data.get("is_retroactive", False)

    if effective_start and published_at:
        eff_date = datetime.strptime(effective_start, "%Y-%m-%d")
        pub_date = datetime.strptime(published_at, "%Y-%m-%d")
        if eff_date < pub_date:
            risk_tags.append("追溯生效")
            if not is_retroactive:
                warnings.append(f"生效日期早于发布日期，建议标记追溯")

    # 3. 风险等级
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
    提交政策到审核队列

    Agent 提交的政策会进入审核队列，等待人工审核后才能发布。
    使用 idempotency_key 可以防止重复提交。

    提交类型:
    - new: 新增政策（默认）
    - update: 更新已有政策，需提供 existing_policy_id 和 change_description
    """
    # 检查权限
    if "submit" not in agent.permissions:
        raise HTTPException(status_code=403, detail="No permission to submit policies")

    # 验证提交类型
    if request.submit_type not in ["new", "update"]:
        raise HTTPException(status_code=400, detail="submit_type 必须是 'new' 或 'update'")

    # 如果是更新，验证原政策存在
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
    ai_analysis = {}

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
                message="该政策已提交，请勿重复提交"
            )

    # 生成 policy_id（如果是更新，则使用原政策ID）
    if request.submit_type == "update":
        policy_id = request.existing_policy_id
    else:
        policy_id = str(uuid.uuid4())

    # AI 分析
    ai_analysis = await _run_ai_analysis(request.structured_data.model_dump())
    warnings = ai_analysis.get("warnings", [])

    if warnings_msg:
        warnings.append(warnings_msg)

    # 计算 SLA
    sla_hours = {"urgent": 1, "high": 4, "normal": 24, "low": 72}.get(request.priority, 24)
    sla_deadline = (datetime.utcnow() + timedelta(hours=sla_hours)).isoformat()

    # 转换 raw_evidence 为统一格式（支持多来源)
    raw_evidence_data = {"sources": request.raw_content.to_sources_list()}

    # 创建审核记录
    review = ReviewQueue(
        policy_id=policy_id,
        idempotency_key=request.idempotency_key,
        submitted_data=json.dumps(request.structured_data.model_dump(), ensure_ascii=False),
        raw_evidence=json.dumps(raw_evidence_data, ensure_ascii=False),
        ai_validation=json.dumps(ai_analysis.get("validation", {}), ensure_ascii=False),
        risk_level=ai_analysis.get("risk_level", "low"),
        risk_tags=json.dumps(ai_analysis.get("risk_tags", []), ensure_ascii=False),
        status="pending",
        priority=request.priority,
        submitted_by=agent.agent_id,
        sla_deadline=sla_deadline,
        # 新增字段
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
        warnings=warnings,
        estimated_review_time=f"{sla_hours}h"
    )


@router.get("/policies", response_model=PolicyQueryResponse)
async def query_policies(
    region_code: Optional[str] = Query(default=None, description="地区代码"),
    effective_year: Optional[int] = Query(default=None, description="生效年份"),
    is_retroactive: Optional[bool] = Query(default=None, description="是否追溯"),
    limit: int = Query(default=10, ge=1, le=100, description="返回数量限制"),
    agent: AgentAuth = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session)
):
    """
    查询已发布政策

    用于去重检查或获取历史数据。只返回已发布（active）状态的政策。
    """
    query = select(Policy).where(
        Policy.status == "active",
        Policy.deleted_at.is_(None)
    )

    if region_code:
        query = query.where(Policy.region_code == region_code)
    if effective_year:
        query = query.where(Policy.policy_year == effective_year)

    query = query.order_by(Policy.effective_start.desc()).limit(limit)

    result = await session.execute(query)
    policies = result.scalars().all()

    data = []
    for p in policies:
        # 获取社保数据
        si_result = await session.execute(
            select(PolicySocialInsurance).where(PolicySocialInsurance.policy_id == p.policy_id)
        )
        si = si_result.scalar_one_or_none()

        data.append({
            "policy_id": p.policy_id,
            "title": p.title,
            "region_code": p.region_code,
            "effective_start": p.effective_start,
            "effective_end": p.effective_end,
            "si_upper_limit": si.si_upper_limit if si else None,
            "si_lower_limit": si.si_lower_limit if si else None,
            "hf_upper_limit": si.hf_upper_limit if si else None,
            "hf_lower_limit": si.hf_lower_limit if si else None,
            "is_retroactive": si.is_retroactive == 1 if si else False
        })

    return PolicyQueryResponse(success=True, data=data, total=len(data))


@router.get("/check-duplicate", response_model=DuplicateCheckResponse)
async def check_duplicate(
    region_code: Optional[str] = Query(default=None, description="地区代码"),
    effective_start: Optional[str] = Query(default=None, description="生效日期"),
    agent: AgentAuth = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session)
):
    """
    检查重复政策

    提交前调用此接口检查政策是否重复，避免无效提交。
    按地区+时间匹配。
    """
    # 按地区+时间检查
    if region_code and effective_start:
        result = await session.execute(
            select(Policy).where(
                Policy.region_code == region_code,
                Policy.effective_start == effective_start,
                Policy.status == "active"
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return DuplicateCheckResponse(
                success=True,
                is_duplicate=True,
                existing_policy_id=existing.policy_id,
                existing_status=existing.status,
                similarity_score=0.8
            )

    return DuplicateCheckResponse(
        success=True,
        is_duplicate=False,
        existing_policy_id=None,
        similarity_score=0.0
    )


@router.get("/schema")
async def get_policy_schema(
    policy_type: str = Query(default="social_insurance_base", description="政策类型"),
    include_examples: bool = Query(default=True, description="是否包含示例"),
    agent: AgentAuth = Depends(get_current_agent)
):
    """
    获取政策 Schema 定义

    返回政策数据的字段定义、校验规则和示例，帮助 Agent 正确构造请求数据。
    """
    schema = {
        "policy_type": "social_insurance_base",
        "fields": {
            "title": {"type": "string", "max_length": 500, "required": True, "description": "政策完整名称"},
            "region_code": {"type": "string", "pattern": "^\\d{6}$", "required": True, "description": "六位行政区划码"},
            "published_at": {"type": "date", "format": "YYYY-MM-DD", "required": True, "description": "发布日期"},
            "effective_start": {"type": "date", "format": "YYYY-MM-DD", "required": True, "description": "生效开始日期"},
            "si_upper_limit": {"type": "integer", "unit": "元/月", "required": True, "description": "社保基数上限"},
            "si_lower_limit": {"type": "integer", "unit": "元/月", "required": True, "description": "社保基数下限"},
            "hf_upper_limit": {"type": "integer", "unit": "元/月", "required": False, "description": "公积金上限"},
            "hf_lower_limit": {"type": "integer", "unit": "元/月", "required": False, "description": "公积金下限"},
            "is_retroactive": {"type": "boolean", "default": False, "description": "是否追溯生效"},
            "coverage_types": {
                "type": "array",
                "items": {"enum": ["养老", "医疗", "失业", "工伤", "生育", "公积金"]},
                "default": ["养老", "医疗", "失业", "工伤", "生育"]
            }
        },
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
        "validation_rules": [
            "si_upper_limit > si_lower_limit",
            "hf_upper_limit > hf_lower_limit (if provided)",
            "effective_start >= published_at (unless is_retroactive=true)"
        ]
    }

    if include_examples:
        schema["examples"] = [
            {
                "structured_data": {
                    "title": "2024年北京市社会保险缴费基数上下限调整通知",
                    "region_code": "110000",
                    "published_at": "2024-06-20",
                    "effective_start": "2024-07-01",
                    "si_upper_limit": 35283,
                    "si_lower_limit": 6821,
                    "hf_upper_limit": 35283,
                    "hf_lower_limit": 2420,
                    "is_retroactive": False,
                    "coverage_types": ["养老", "医疗", "失业", "工伤", "生育"]
                },
                "raw_content": {
                    "sources": [
                        {
                            "title": "北京市人力资源和社会保障局通知",
                            "doc_number": "京人社发〔2024〕12号",
                            "url": "https://example.com/policy/123",
                            "extracted_text": "..."
                        }
                    ]
                }
            }
        ]

    return {"success": True, "schema": schema}


@router.get("/submissions", response_model=SubmissionResponse)
async def get_submissions(
    status: Optional[str] = Query(default=None, description="审核状态: pending/approved/rejected"),
    limit: int = Query(default=20, ge=1, le=100, description="返回数量限制"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
    agent: AgentAuth = Depends(get_current_agent),
    session: AsyncSession = Depends(get_session)
):
    """
    查询自己的提交记录

    返回当前 Agent 提交的所有政策审核记录，支持按状态筛选。
    """
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
        data.append({
            "review_id": s.review_id,
            "policy_id": s.policy_id,
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
