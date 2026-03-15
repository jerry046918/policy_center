// 用户相关类型定义

export interface User {
  user_id: string
  username: string
  email?: string
  display_name?: string
  role: string
  is_active: boolean
  last_login_at?: string
  created_at: string
}

export interface UserCreateInput {
  username: string
  password: string
  email?: string
  display_name?: string
  role: string
}

export interface ChangePasswordInput {
  current_password: string
  new_password: string
}

export interface ResetPasswordInput {
  new_password: string
}

export interface ToggleStatusInput {
  is_active: boolean
}

// 角色枚举
export const ROLE_MAP: Record<string, { label: string; color: string }> = {
  admin: { label: '管理员', color: 'red' },
  staff: { label: '员工', color: 'blue' },
  viewer: { label: '只读', color: 'default' },
}
