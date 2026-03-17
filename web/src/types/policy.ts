// 政策相关类型定义

// 来源文档类型
export interface SourceDocument {
  title?: string
  doc_number?: string  // 官方文号（非必填）
  url: string
  extracted_text?: string
}

// ── 主政策类型 ──────────────────────────────────────────────

export interface Policy {
  policy_id: string
  policy_type: string
  title: string
  region_code: string
  region_name?: string

  source_attachments?: string  // JSON string of SourceDocument[]

  published_at: string
  effective_start: string
  effective_end?: string
  policy_year?: number

  status: string
  version: number

  // 通用类型扩展数据
  type_data?: Record<string, any>

  // 向后兼容
  social_insurance?: PolicySocialInsurance

  created_at: string
  updated_at: string
  created_by?: string
  reviewed_by?: string
}

// 政策列表项（API返回的扁平化结构）
export interface PolicyListItem {
  policy_id: string
  policy_type: string
  title: string
  region_code: string
  region_name?: string

  // 类型摘要
  type_summary?: Record<string, any>

  // 向后兼容（社保类型）
  si_upper_limit?: number
  si_lower_limit?: number

  effective_start: string
  status: string
  is_retroactive: boolean
}

// ── 社保基数类型 ──────────────────────────────────────

export interface PolicySocialInsurance {
  si_upper_limit?: number
  si_lower_limit?: number
  si_avg_salary_ref?: number
  is_retroactive: boolean
  retroactive_start?: string
  retroactive_months?: number
  coverage_types: string[]
  change_rate_upper?: number
  change_rate_lower?: number
  special_notes?: string
}

export interface PolicyHousingFund {
  hf_upper_limit?: number
  hf_lower_limit?: number
  is_retroactive: boolean
  retroactive_start?: string
  retroactive_months?: number
  change_rate_upper?: number
  change_rate_lower?: number
  special_notes?: string
}

// ── 创建/更新 ────────────────────────────────────────────────

export interface PolicyCreateInput {
  policy_type?: string
  title: string
  region_code: string
  published_at: string
  effective_start: string
  effective_end?: string

  // 通用类型扩展数据入口
  type_data?: Record<string, any>

  // 向后兼容
  social_insurance?: {
    si_upper_limit?: number
    si_lower_limit?: number
    is_retroactive?: boolean
    retroactive_start?: string
    coverage_types?: string[]
    special_notes?: string
  }
  raw_content?: string
}

export interface PolicyUpdateInput {
  title?: string
  published_at?: string
  effective_start?: string
  effective_end?: string

  type_data?: Record<string, any>

  // 向后兼容
  social_insurance?: Partial<PolicyCreateInput['social_insurance']>

  change_reason: string
  create_new_version?: boolean
  special_notes?: string
}

export interface Region {
  code: string
  name: string
  level: 'country' | 'province' | 'city' | 'district'
  parent_code?: string
  full_path?: string
  min_wage?: number
  avg_salary?: number
}

// ── 状态枚举 ────────────────────────────────────────────────

export const POLICY_STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: 'default' },
  pending_review: { label: '待审核', color: 'orange' },
  active: { label: '生效中', color: 'green' },
  expired: { label: '已过期', color: 'red' },
  revoked: { label: '已撤销', color: 'default' },
}

export const REVIEW_STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: '待审核', color: 'orange' },
  claimed: { label: '审核中', color: 'blue' },
  approved: { label: '已通过', color: 'green' },
  rejected: { label: '已拒绝', color: 'red' },
  needs_clarification: { label: '需补充', color: 'purple' },
}

export const PRIORITY_MAP: Record<string, { label: string; color: string }> = {
  urgent: { label: '紧急', color: 'red' },
  high: { label: '高', color: 'orange' },
  normal: { label: '普通', color: 'blue' },
  low: { label: '低', color: 'default' },
}

export const RISK_LEVEL_MAP: Record<string, { label: string; color: string }> = {
  high: { label: '高风险', color: 'red' },
  medium: { label: '中风险', color: 'orange' },
  low: { label: '低风险', color: 'green' },
}

// 政策类型映射
export const POLICY_TYPE_MAP: Record<string, { label: string; color: string }> = {
  social_insurance: { label: '社保基数', color: 'blue' },
  social_insurance_base: { label: '社保基数', color: 'blue' },  // 兼容旧数据
  housing_fund: { label: '公积金基数', color: 'geekblue' },
  avg_salary: { label: '社会平均工资', color: 'cyan' },
  talent_policy: { label: '人才政策', color: 'purple' },
}

// 获取政策类型标签（兼容动态类型）
export function getPolicyTypeLabel(typeCode?: string): { label: string; color: string } {
  if (!typeCode) return { label: '未知', color: 'default' }
  return POLICY_TYPE_MAP[typeCode] || { label: typeCode, color: 'default' }
}
