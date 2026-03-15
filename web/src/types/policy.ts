// 政策相关类型定义

// 来源文档类型
export interface SourceDocument {
  title?: string
  doc_number?: string  // 官方文号（非必填）
  url: string
  extracted_text?: string
}

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

  social_insurance?: PolicySocialInsurance

  created_at: string
  updated_at: string
  created_by?: string
  reviewed_by?: string
}

// 政策列表项（API返回的扁平化结构）
export interface PolicyListItem {
  policy_id: string
  title: string
  region_code: string
  region_name?: string
  si_upper_limit?: number
  si_lower_limit?: number
  effective_start: string
  status: string
  is_retroactive: boolean
}

export interface PolicySocialInsurance {
  si_upper_limit?: number
  si_lower_limit?: number
  si_avg_salary_ref?: number
  hf_upper_limit?: number
  hf_lower_limit?: number
  is_retroactive: boolean
  retroactive_start?: string
  retroactive_months?: number
  coverage_types: string[]
  change_rate_upper?: number
  change_rate_lower?: number
  special_notes?: string
}

export interface PolicyCreateInput {
  title: string
  region_code: string
  published_at: string
  effective_start: string
  effective_end?: string
  social_insurance: {
    si_upper_limit?: number
    si_lower_limit?: number
    hf_upper_limit?: number
    hf_lower_limit?: number
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
  social_insurance?: Partial<PolicyCreateInput['social_insurance']>
  change_reason: string
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

// 状态枚举
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
