import api from './api'

export interface ApiKeyItem {
  agent_id: string
  agent_name: string
  api_key_prefix: string
  description?: string
  is_active: boolean
  last_used_at?: string
  created_at: string
}

export interface ApiKeyCreateInput {
  agent_name: string
  description?: string
}

export interface ApiKeyCreateResult {
  agent_id: string
  agent_name: string
  api_key: string
  api_key_prefix: string
  description?: string
  is_active: boolean
  last_used_at?: string
  created_at: string
}

interface ApiKeyListResponse {
  success: boolean
  data: ApiKeyItem[]
  total: number
  page: number
  page_size: number
}

// 获取 API Key 列表
export async function listApiKeys(params?: {
  is_active?: number
  page?: number
  page_size?: number
}): Promise<ApiKeyListResponse> {
  return api.get('/admin/agents', { params })
}

// 创建 API Key
export async function createApiKey(data: ApiKeyCreateInput): Promise<ApiKeyCreateResult> {
  return api.post('/admin/agents', data)
}

// 切换 API Key 状态
export async function toggleApiKeyStatus(agentId: string, isActive: boolean): Promise<{ success: boolean; message: string }> {
  return api.patch(`/admin/agents/${agentId}/status`, { is_active: isActive })
}

// 删除 API Key
export async function deleteApiKey(agentId: string): Promise<{ success: boolean; message: string }> {
  return api.delete(`/admin/agents/${agentId}`)
}
