import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { Spin } from 'antd'
import MainLayout from './components/Layout/MainLayout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import PolicyList from './pages/Policy/PolicyList'
import PolicyDetail from './pages/Policy/PolicyDetail'
import PolicyCreate from './pages/Policy/PolicyCreate'
import PolicyEdit from './pages/Policy/PolicyEdit'
import ReviewCenter from './pages/Review/ReviewCenter'
import ReviewDetail from './pages/Review/ReviewDetail'
import AdminUsers from './pages/Admin/Users'
import AdminAgents from './pages/Admin/Agents'
import AdminRegions from './pages/Admin/Regions'
import { useAuthStore } from './stores/auth'

function App() {
  const { token, init } = useAuthStore()
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    init().finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!token) {
    return (
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </BrowserRouter>
    )
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="policies" element={<PolicyList />} />
          <Route path="policies/create" element={<PolicyCreate />} />
          <Route path="policies/:id/edit" element={<PolicyEdit />} />
          <Route path="policies/:id" element={<PolicyDetail />} />
          <Route path="reviews" element={<ReviewCenter />} />
          <Route path="reviews/:id" element={<ReviewDetail />} />
          <Route path="admin/users" element={<AdminUsers />} />
          <Route path="admin/agents" element={<AdminAgents />} />
          <Route path="admin/regions" element={<AdminRegions />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
