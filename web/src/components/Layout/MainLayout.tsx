import { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Dropdown, Avatar, Button, Badge, Modal, Form, Input, message } from 'antd'
import {
  DashboardOutlined,
  FileTextOutlined,
  AuditOutlined,
  SettingOutlined,
  UserOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  BellOutlined,
  TeamOutlined,
  LockOutlined,
  GlobalOutlined,
  ApiOutlined,
  AppstoreOutlined,
} from '@ant-design/icons'
import { useAuthStore } from '../../stores/auth'
import { changePassword } from '../../services/userService'
import './MainLayout.css'

const { Header, Sider, Content } = Layout

const menuItems = [
  {
    key: '/',
    icon: <DashboardOutlined />,
    label: '数据看板',
  },
  {
    key: '/policies',
    icon: <FileTextOutlined />,
    label: '政策管理',
  },
  {
    key: '/reviews',
    icon: <AuditOutlined />,
    label: '审核中心',
  },
  {
    key: '/admin',
    icon: <SettingOutlined />,
    label: '系统管理',
    children: [
      { key: '/admin/users', label: '用户管理', icon: <TeamOutlined /> },
      { key: '/admin/agents', label: 'API Key 管理', icon: <ApiOutlined /> },
      { key: '/admin/regions', label: '地区管理', icon: <GlobalOutlined /> },
      { key: '/admin/policy-types', label: '政策类型', icon: <AppstoreOutlined /> },
    ],
  },
]

export default function MainLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const [passwordModalVisible, setPasswordModalVisible] = useState(false)
  const [passwordForm] = Form.useForm()
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()

  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(key)
  }

  const handleChangePassword = async (values: { current_password: string; new_password: string }) => {
    try {
      await changePassword(values)
      message.success('密码修改成功')
      setPasswordModalVisible(false)
      passwordForm.resetFields()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '密码修改失败')
    }
  }

  const userMenuItems = [
    {
      key: 'changePassword',
      icon: <LockOutlined />,
      label: '修改密码',
      onClick: () => setPasswordModalVisible(true),
    },
    {
      type: 'divider' as const,
    },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: logout,
    },
  ]

  const handleUserMenuClick = ({ key }: { key: string }) => {
    if (key === 'logout') {
      logout()
    } else if (key === 'changePassword') {
      setPasswordModalVisible(true)
    }
  }

  const getSelectedKeys = () => {
    const path = location.pathname
    if (path === '/') return ['/']
    if (path.startsWith('/policies')) return ['/policies']
    if (path.startsWith('/reviews')) return ['/reviews']
    if (path.startsWith('/admin/users')) return ['/admin/users']
    if (path.startsWith('/admin/agents')) return ['/admin/agents']
    if (path.startsWith('/admin/regions')) return ['/admin/regions']
    return [path]
  }

  const getOpenKeys = () => {
    if (location.pathname.startsWith('/admin')) return ['/admin']
    return []
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        width={240}
        className="sider"
      >
        <div className="logo">
          {collapsed ? '政' : '政策中心'}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={getSelectedKeys()}
          defaultOpenKeys={getOpenKeys()}
          items={menuItems}
          onClick={handleMenuClick}
        />
      </Sider>
      <Layout>
        <Header className="header">
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
            className="trigger"
          />
          <div className="header-right">
            <Badge count={0} size="small" offset={[-2, 2]}>
              <Button type="text" icon={<BellOutlined />} />
            </Badge>
            <Dropdown menu={{ items: userMenuItems, onClick: handleUserMenuClick }} placement="bottomRight">
              <div className="user-info">
                <Avatar size="small" icon={<UserOutlined />} style={{ backgroundColor: '#1976d2' }} />
                <span className="username">{user?.username || 'User'}</span>
              </div>
            </Dropdown>
          </div>
        </Header>
        <Content className="content">
          <Outlet />
        </Content>
      </Layout>

      {/* 修改密码弹窗 */}
      <Modal
        title="修改密码"
        open={passwordModalVisible}
        onCancel={() => {
          setPasswordModalVisible(false)
          passwordForm.resetFields()
        }}
        onOk={() => passwordForm.submit()}
      >
        <Form
          form={passwordForm}
          layout="vertical"
          onFinish={handleChangePassword}
        >
          <Form.Item
            name="current_password"
            label="当前密码"
            rules={[{ required: true, message: '请输入当前密码' }]}
          >
            <Input.Password placeholder="当前密码" />
          </Form.Item>
          <Form.Item
            name="new_password"
            label="新密码"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 6, message: '密码至少6个字符' },
            ]}
          >
            <Input.Password placeholder="新密码" />
          </Form.Item>
        </Form>
      </Modal>
    </Layout>
  )
}
