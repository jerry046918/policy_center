import api from './api'

// 政策类型接口
export interface PolicyTypeItem {
  type_code: string
  type_name: string
  description?: string
  extension_table?: string
  field_schema: Record<string, any>
  validation_rules: string[]
  example_data: Record<string, any>
  is_builtin: boolean
  is_active: boolean
  sort_order: number
  icon?: string
  policy_count: number
  created_at: string
  updated_at: string
}

export interface PolicyTypeCreateInput {
  type_code: string
  type_name: string
  description?: string
  field_schema: Record<string, any>
  validation_rules?: string[]
  example_data?: Record<string, any>
  icon?: string
  sort_order?: number
}

export interface PolicyTypeUpdateInput {
  type_name?: string
  description?: string
  field_schema?: Record<string, any>
  validation_rules?: string[]
  example_data?: Record<string, any>
  icon?: string
  sort_order?: number
  is_active?: boolean
}

export const listPolicyTypes = () =>
  api.get('/admin/policy-types')

export const createPolicyType = (data: PolicyTypeCreateInput) =>
  api.post('/admin/policy-types', data)

export const updatePolicyType = (typeCode: string, data: PolicyTypeUpdateInput) =>
  api.put(`/admin/policy-types/${typeCode}`, data)

export const deletePolicyType = (typeCode: string) =>
  api.delete(`/admin/policy-types/${typeCode}`)
