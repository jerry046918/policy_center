import api from './api'

export interface DashboardStats {
  total_policies: number
  active_policies: number
  pending_reviews: number
  regions_covered: number
  total_regions: number
  sla_overdue: number
  sla_warning: number
}

export interface RecentPolicy {
  policy_id: string
  title: string
  region_name: string
  region_code: string
  effective_start: string
  status: string
  si_upper_limit: number
  si_lower_limit: number
}

export interface PendingReview {
  review_id: string
  policy_title: string
  region_name: string
  risk_level: string
  priority: string
  submitted_at: string
  sla_remaining_hours: number
  sla_status: string
}

export interface RetroactivePolicy {
  policy_id: string
  title: string
  region_name: string
  effective_start: string
  retroactive_start: string
  retroactive_months: number
  si_upper_limit: number
  si_lower_limit: number
}

export interface DashboardData {
  stats: DashboardStats
  recent_policies: RecentPolicy[]
  pending_reviews: PendingReview[]
  retroactive_policies: RetroactivePolicy[]
}

// 获取看板数据
export async function getDashboard(): Promise<DashboardData> {
  return api.get('/dashboard')
}
