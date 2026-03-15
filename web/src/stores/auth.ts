import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import api from '../services/api'
import { message } from 'antd'

interface User {
  user_id: string
  username: string
  email?: string
  display_name?: string
  role: string
}

interface AuthState {
  token: string | null
  user: User | null
  login: (username: string, password: string) => Promise<boolean>
  logout: () => void
  init: () => Promise<void>
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,

      login: async (username: string, password: string) => {
        try {
          const response: any = await api.post('/auth/login', { username, password })
          set({ token: response.access_token, user: { user_id: response.user_id, username, role: response.role } })
          message.success('登录成功')
          return true
        } catch (error) {
          return false
        }
      },

      logout: () => {
        set({ token: null, user: null })
      },

      init: async () => {
        const token = get().token
        if (token) {
          try {
            const user: any = await api.get('/auth/me')
            set({ user })
          } catch {
            set({ token: null, user: null })
          }
        }
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({ token: state.token }),
    }
  )
)
