import api from './api'

export interface ReviewItem {
  review_id: string
  policy_title: string
  policy_type?: string
  region_code: string
  region_name?: string
  status: string
  priority: string
  risk_level: string
  risk_tags: string[]
  submitted_at: string
  submitted_by: string
  sla_deadline?: string
  sla_remaining_hours?: number
  sla_status?: string
  claimed_by?: string
}

export interface ReviewDetail {
  review_id: string
  policy_id?: string
  policy_type?: string
  status: string
  priority: string
  submitted_data: any
  raw_evidence?: any
  ai_validation?: any
  risk_level: string
  risk_tags: string[]
  submitted_at: string
  submitted_by: string
  sla_deadline?: string
  claimed_by?: string
  claimed_at?: string
  reviewer_notes?: string
  region_name?: string
  previous_policy?: any
  diff?: any
  // 提交类型相关
  submit_type?: 'new' | 'update'  // 提交类型：新建或更新
  existing_policy_id?: string     // 更新时的原政策ID
  change_description?: string     // 更新时的修改说明
  final_action?: string           // 审核人最终决定
  final_target_policy_id?: string // 最终操作的政策ID
  reviewer_modified_data?: any    // 审核人修改的数据
}

export interface ReviewListParams {
  status?: string
  priority?: string
  risk_level?: string
  region_code?: string
  page?: number
  page_size?: number
}

// 获取审核列表
export async function getReviews(params: ReviewListParams): Promise<{ success: boolean; data: ReviewItem[]; total: number; page: number; page_size: number }> {
  return api.get('/reviews', { params })
}

// 获取审核详情
export async function getReview(reviewId: string): Promise<ReviewDetail> {
  return api.get(`/reviews/${reviewId}`)
}

// 通过审核
export async function approveReview(reviewId: string, notes?: string): Promise<{ success: boolean; policy_id: string }> {
  return api.post(`/reviews/${reviewId}/approve`, { notes })
}

// 拒绝审核
export async function rejectReview(reviewId: string, reason: string): Promise<{ success: boolean }> {
  return api.post(`/reviews/${reviewId}/reject`, { reason })
}
