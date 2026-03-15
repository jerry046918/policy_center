import axios from 'axios'
import { message } from 'antd'
import { useAuthStore } from '../stores/auth'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    const token = useAuthStore.getState().token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    const requestId = Math.random().toString(36).substring(2, 10)
    config.headers['X-Request-ID'] = requestId
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response.data
  },
  (error) => {
    const { response } = error

    if (response) {
      switch (response.status) {
        case 401:
          message.error('登录已过期，请重新登录')
          useAuthStore.getState().logout()
          window.location.href = '/login'
          break
        case 403:
          message.error('没有权限访问')
          break
        case 404:
          message.error('资源不存在')
          break
        case 422:
          const errors = response.data?.detail
          if (Array.isArray(errors)) {
            errors.forEach((e: any) => message.error(e.msg))
          } else {
            message.error(response.data?.message || '请求参数错误')
          }
          break
        case 500:
          message.error('服务器错误，请稍后重试')
          break
        default:
          message.error(response.data?.message || '请求失败')
      }
    } else {
      message.error('网络错误，请检查网络连接')
    }

    return Promise.reject(error)
  }
)

export default api
