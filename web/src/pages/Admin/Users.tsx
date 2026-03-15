import { useEffect, useState } from 'react'
import {
  Card,
  Table,
  Button,
  Space,
  Tag,
  Modal,
  Form,
  Input,
  Select,
  message,
  Tooltip,
  Popconfirm,
} from 'antd'
import {
  PlusOutlined,
  StopOutlined,
  CheckCircleOutlined,
  KeyOutlined,
  UserOutlined,
  MailOutlined,
} from '@ant-design/icons'
import './Admin.css'
import type { ColumnsType } from 'antd/es/table'
import { listUsers, createUser, toggleUserStatus, resetUserPassword } from '../../services/userService'
import type { User } from '../../types/user'
import { ROLE_MAP } from '../../types/user'

const { Option } = Select

export default function UsersPage() {
  const [loading, setLoading] = useState(false)
  const [users, setUsers] = useState<User[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [createModalVisible, setCreateModalVisible] = useState(false)
  const [resetPasswordModalVisible, setResetPasswordModalVisible] = useState(false)
  const [currentUser, setCurrentUser] = useState<User | null>(null)
  const [createForm] = Form.useForm()
  const [resetPasswordForm] = Form.useForm()

  useEffect(() => {
    loadUsers()
  }, [page, pageSize])

  const loadUsers = async () => {
    setLoading(true)
    try {
      const res = await listUsers({ page, page_size: pageSize })
      if (res.success) {
        setUsers(res.data)
        setTotal(res.total)
      }
    } catch (error) {
      message.error('加载用户列表失败')
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async (values: any) => {
    try {
      await createUser(values)
      message.success('用户创建成功')
      setCreateModalVisible(false)
      createForm.resetFields()
      loadUsers()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '创建失败')
    }
  }

  const handleToggleStatus = async (user: User) => {
    try {
      await toggleUserStatus(user.user_id, { is_active: !user.is_active })
      message.success(user.is_active ? '已禁用' : '已启用')
      loadUsers()
    } catch (error: any) {
      message.error(error.response?.data?.detail || '操作失败')
    }
  }

  const handleResetPassword = async (values: { new_password: string }) => {
    if (!currentUser) return
    try {
      await resetUserPassword(currentUser.user_id, values)
      message.success('密码重置成功')
      setResetPasswordModalVisible(false)
      resetPasswordForm.resetFields()
      setCurrentUser(null)
    } catch (error: any) {
      message.error(error.response?.data?.detail || '重置失败')
    }
  }

  const openResetPasswordModal = (user: User) => {
    setCurrentUser(user)
    setResetPasswordModalVisible(true)
  }

  const getRoleLabel = (role: string) => {
    return ROLE_MAP[role]?.label || role
  }

  const getRoleColor = (role: string) => {
    return ROLE_MAP[role]?.color || 'default'
  }

  const columns: ColumnsType<User> = [
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
      render: (text) => (
        <span>
          <UserOutlined style={{ marginRight: 8 }} />
          {text}
        </span>
      ),
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
      render: (email) => email ? (
        <span>
          <MailOutlined style={{ marginRight: 8 }} />
          {email}
        </span>
      ) : '-',
    },
    {
      title: '显示名',
      dataIndex: 'display_name',
      key: 'display_name',
      render: (name) => name || '-',
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      render: (role) => (
        <Tag color={getRoleColor(role)}>{getRoleLabel(role)}</Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (isActive) => (
        <Tag color={isActive ? 'green' : 'default'}>
          {isActive ? '启用' : '禁用'}
        </Tag>
      ),
    },
    {
      title: '最后登录',
      dataIndex: 'last_login_at',
      key: 'last_login_at',
      render: (time) => time || '-',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (time) => time || '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="重置密码">
            <Button
              type="text"
              size="small"
              icon={<KeyOutlined />}
              onClick={() => openResetPasswordModal(record)}
            />
          </Tooltip>
          <Popconfirm
            title={record.is_active ? '确认禁用该用户？' : '确认启用该用户？'}
            onConfirm={() => handleToggleStatus(record)}
          >
            <Tooltip title={record.is_active ? '禁用' : '启用'}>
              <Button
                type="text"
                size="small"
                icon={record.is_active ? <StopOutlined /> : <CheckCircleOutlined />}
                danger={record.is_active}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="admin-page">
      <Card
        title="用户管理"
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateModalVisible(true)}
          >
            新建用户
          </Button>
        }
      >
        <Table
          columns={columns}
          dataSource={users}
          rowKey="user_id"
          loading={loading}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 个用户`,
            onChange: (p, ps) => {
              setPage(p)
              setPageSize(ps)
            },
          }}
        />
      </Card>

      {/* 新建用户弹窗 */}
      <Modal
        title="新建用户"
        open={createModalVisible}
        onCancel={() => setCreateModalVisible(false)}
        onOk={() => createForm.submit()}
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={handleCreate}
          initialValues={{ role: 'staff' }}
        >
          <Form.Item
            name="username"
            label="用户名"
            rules={[
              { required: true, message: '请输入用户名' },
              { min: 3, message: '用户名至少3个字符' },
            ]}
          >
            <Input placeholder="登录用户名" />
          </Form.Item>

          <Form.Item
            name="password"
            label="密码"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 6, message: '密码至少6个字符' },
            ]}
          >
            <Input.Password placeholder="初始密码" />
          </Form.Item>

          <Form.Item
            name="email"
            label="邮箱"
            rules={[{ type: 'email', message: '请输入有效的邮箱地址' }]}
          >
            <Input placeholder="邮箱地址（可选）" />
          </Form.Item>

          <Form.Item
            name="display_name"
            label="显示名"
          >
            <Input placeholder="显示名称（可选）" />
          </Form.Item>

          <Form.Item
            name="role"
            label="角色"
            rules={[{ required: true }]}
          >
            <Select>
              <Option value="admin">管理员</Option>
              <Option value="staff">员工</Option>
              <Option value="viewer">只读</Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      {/* 重置密码弹窗 */}
      <Modal
        title={`重置密码 - ${currentUser?.username}`}
        open={resetPasswordModalVisible}
        onCancel={() => {
          setResetPasswordModalVisible(false)
          resetPasswordForm.resetFields()
          setCurrentUser(null)
        }}
        onOk={() => resetPasswordForm.submit()}
      >
        <Form
          form={resetPasswordForm}
          layout="vertical"
          onFinish={handleResetPassword}
        >
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
    </div>
  )
}
