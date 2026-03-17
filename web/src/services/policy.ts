import api from './api'
import type { Policy, PolicyListItem, PolicyCreateInput, PolicyUpdateInput } from '../types/policy'

export interface PolicyListParams {
  region_code?: string
  year?: number
  policy_type?: string
  is_retroactive?: boolean
  keyword?: string
  page?: number
  page_size?: number
}

export interface PaginatedResponse<T> {
  success: boolean
  data: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// 获取政策列表
export async function getPolicies(params: PolicyListParams): Promise<PaginatedResponse<PolicyListItem>> {
  // 过滤掉空字符串参数
  const filteredParams: Record<string, any> = {}
  for (const [key, value] of Object.entries(params)) {
    if (value !== '' && value !== undefined && value !== null) {
      filteredParams[key] = value
    }
  }

  const response: any = await api.get('/policies', { params: filteredParams })
  return {
    success: response.success ?? true,
    data: response.data || [],
    total: response.total || 0,
    page: response.page || params.page || 1,
    page_size: response.page_size || params.page_size || 20,
    total_pages: response.total_pages || 0,
  }
}

// 获取政策详情
export async function getPolicy(policyId: string): Promise<Policy> {
  const response: any = await api.get(`/policies/${policyId}`)
  return response
}

// 创建政策
export async function createPolicy(data: PolicyCreateInput): Promise<{ success: boolean; policy_id: string; status?: string; duplicate_warning?: any }> {
  return api.post('/policies', data)
}

// 更新政策
export async function updatePolicy(policyId: string, data: PolicyUpdateInput): Promise<{ success: boolean; policy_id: string; version: number }> {
  return api.put(`/policies/${policyId}`, data)
}

// 删除政策
export async function deletePolicy(policyId: string): Promise<{ success: boolean }> {
  return api.delete(`/policies/${policyId}`)
}

// 获取版本历史
export async function getPolicyVersions(policyId: string): Promise<{ success: boolean; data: any[]; total: number }> {
  return api.get(`/policies/${policyId}/versions`)
}

// 获取地区列表
export async function getRegions(parentCode?: string, level?: string): Promise<any[]> {
  const response: any = await api.get('/admin/regions', { params: { parent_code: parentCode, level } })
  return response.data || []
}

// 新增地区
export async function createRegion(data: {
  code: string
  name: string
  level: string
  parent_code?: string
  min_wage?: number
  avg_salary?: number
}): Promise<{ success: boolean; message: string; data?: any }> {
  return api.post('/admin/regions', data)
}

// 初始化地区数据
export async function initRegions(force: boolean = false): Promise<{ success: boolean; message: string; count?: number }> {
  return api.post('/admin/regions/init', null, { params: { force } })
}

// 获取政策类型列表
export interface PolicyTypeItem {
  type_code: string
  type_name: string
  description: string
  field_schema: Record<string, any>
  validation_rules: string[]
  example_data: Record<string, any>
}

export async function getPolicyTypes(): Promise<PolicyTypeItem[]> {
  const response: any = await api.get('/policies/types')
  return response.data || []
}
