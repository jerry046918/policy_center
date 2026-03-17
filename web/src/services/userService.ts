import api from './api'
import type { User, UserCreateInput, ChangePasswordInput, ResetPasswordInput, ToggleStatusInput } from '../types/user'

interface UserListResponse {
  success: boolean
  data: User[]
  total: number
  page: number
  page_size: number
}

// 获取用户列表
export async function listUsers(params?: {
  is_active?: number
  role?: string
  page?: number
  page_size?: number
}): Promise<UserListResponse> {
  return api.get('/admin/users', { params })
}

// 创建用户
export async function createUser(data: UserCreateInput): Promise<User> {
  return api.post('/admin/users', data)
}

// 切换用户状态
export async function toggleUserStatus(userId: string, data: ToggleStatusInput): Promise<{ success: boolean; message: string }> {
  return api.patch(`/admin/users/${userId}/status`, data)
}

// 重置用户密码（管理员）
export async function resetUserPassword(userId: string, data: ResetPasswordInput): Promise<{ success: boolean; message: string }> {
  return api.post(`/admin/users/${userId}/reset-password`, data)
}

// 修改自己的密码
export async function changePassword(data: ChangePasswordInput): Promise<{ success: boolean; message: string }> {
  return api.post('/auth/change-password', data)
}
