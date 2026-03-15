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
  Descriptions,
  Divider,
} from 'antd'
import {
  PlusOutlined,
  KeyOutlined,
  StopOutlined,
  CheckCircleOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons'
import './Admin.css'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'

interface Agent {
  agent_id: string
  name: string
  role: string
  status: string
  api_key: string
  permissions: string[]
  created_at: string
  last_active_at?: string
  request_count: number
}

const { Option } = Select

export default function AgentsPage() {
  const [loading, setLoading] = useState(false)
  const [agents, setAgents] = useState<Agent[]>([])
  const [modalVisible, setModalVisible] = useState(false)
  const [detailVisible, setDetailVisible] = useState(false)
  const [currentAgent, setCurrentAgent] = useState<Agent | null>(null)
  const [form] = Form.useForm()

  useEffect(() => {
    loadAgents()
  }, [])

  const loadAgents = async () => {
    setLoading(true)
    try {
      // Mock data for now
      setAgents([
        {
          agent_id: 'agt_001',
          name: '政策爬虫Agent',
          role: 'collector',
          status: 'active',
          api_key: 'sk-****1234',
          permissions: ['policy:read', 'policy:create'],
          created_at: '2024-01-15 10:30:00',
          last_active_at: '2024-03-13 08:15:00',
          request_count: 1256,
        },
        {
          agent_id: 'agt_002',
          name: 'OCR识别Agent',
          role: 'collector',
          status: 'active',
          api_key: 'sk-****5678',
          permissions: ['policy:read', 'policy:create'],
          created_at: '2024-01-15 10:35:00',
          last_active_at: '2024-03-12 16:45:00',
          request_count: 892,
        },
        {
          agent_id: 'agt_003',
          name: '外部集成Agent',
          role: 'api_consumer',
          status: 'inactive',
          api_key: 'sk-****9012',
          permissions: ['policy:read'],
          created_at: '2024-02-01 09:00:00',
          last_active_at: '2024-02-28 14:30:00',
          request_count: 156,
        },
      ])
    } catch (error) {
      message.error('加载Agent列表失败')
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async (values: any) => {
    try {
      // API call would go here
      message.success('Agent创建成功')
      setModalVisible(false)
      form.resetFields()
      loadAgents()
    } catch (error) {
      message.error('创建失败')
    }
  }

  const handleToggleStatus = async (agent: Agent) => {
    try {
      // API call would go here
      message.success(agent.status === 'active' ? '已停用' : '已启用')
      loadAgents()
    } catch (error) {
      message.error('操作失败')
    }
  }

  const handleRegenerateKey = async (agent: Agent) => {
    Modal.confirm({
      title: '确认重新生成API Key？',
      content: '重新生成后，原API Key将立即失效。',
      onOk: async () => {
        try {
          // API call would go here
          message.success('API Key已重新生成')
          loadAgents()
        } catch (error) {
          message.error('操作失败')
        }
      },
    })
  }

  const getRoleLabel = (role: string) => {
    const roleMap: Record<string, string> = {
      collector: '采集器',
      reviewer: '审核器',
      api_consumer: 'API消费者',
    }
    return roleMap[role] || role
  }

  const columns: ColumnsType<Agent> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (text, record) => (
        <a onClick={() => {
          setCurrentAgent(record)
          setDetailVisible(true)
        }}>
          {text}
        </a>
      ),
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      render: (role) => <Tag>{getRoleLabel(role)}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status) => (
        <Tag color={status === 'active' ? 'green' : 'default'}>
          {status === 'active' ? '活跃' : '停用'}
        </Tag>
      ),
    },
    {
      title: 'API Key',
      dataIndex: 'api_key',
      key: 'api_key',
      render: (key) => (
        <Tag icon={<KeyOutlined />} color="blue">
          {key}
        </Tag>
      ),
    },
    {
      title: '请求数',
      dataIndex: 'request_count',
      key: 'request_count',
      sorter: (a, b) => a.request_count - b.request_count,
      render: (count) => count.toLocaleString(),
    },
    {
      title: '最后活跃',
      dataIndex: 'last_active_at',
      key: 'last_active_at',
      render: (time) => time || '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="重新生成Key">
            <Button
              type="text"
              size="small"
              icon={<KeyOutlined />}
              onClick={() => handleRegenerateKey(record)}
            />
          </Tooltip>
          <Tooltip title={record.status === 'active' ? '停用' : '启用'}>
            <Button
              type="text"
              size="small"
              icon={record.status === 'active' ? <StopOutlined /> : <CheckCircleOutlined />}
              onClick={() => handleToggleStatus(record)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ]

  return (
    <div className="admin-page">
      <Card
        title="Agent管理"
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setModalVisible(true)}
          >
            新建Agent
          </Button>
        }
      >
        <Table
          columns={columns}
          dataSource={agents}
          rowKey="agent_id"
          loading={loading}
          pagination={{
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 个Agent`,
          }}
        />
      </Card>

      {/* 新建Agent弹窗 */}
      <Modal
        title="新建Agent"
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreate}
          initialValues={{ role: 'collector', permissions: ['policy:read'] }}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入Agent名称' }]}
          >
            <Input placeholder="如：政策爬虫Agent" />
          </Form.Item>

          <Form.Item
            name="role"
            label="角色"
            rules={[{ required: true }]}
          >
            <Select>
              <Option value="collector">采集器</Option>
              <Option value="reviewer">审核器</Option>
              <Option value="api_consumer">API消费者</Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="permissions"
            label="权限"
            rules={[{ required: true }]}
          >
            <Select mode="multiple" placeholder="选择权限">
              <Option value="policy:read">政策读取</Option>
              <Option value="policy:create">政策创建</Option>
              <Option value="policy:update">政策更新</Option>
              <Option value="review:read">审核读取</Option>
              <Option value="review:approve">审核通过</Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>

      {/* Agent详情弹窗 */}
      <Modal
        title="Agent详情"
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        footer={null}
        width={600}
      >
        {currentAgent && (
          <>
            <Descriptions column={2} bordered size="small">
              <Descriptions.Item label="名称" span={2}>
                {currentAgent.name}
              </Descriptions.Item>
              <Descriptions.Item label="Agent ID">{currentAgent.agent_id}</Descriptions.Item>
              <Descriptions.Item label="角色">{getRoleLabel(currentAgent.role)}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={currentAgent.status === 'active' ? 'green' : 'default'}>
                  {currentAgent.status === 'active' ? '活跃' : '停用'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="请求数">
                {currentAgent.request_count.toLocaleString()}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间" span={2}>
                {currentAgent.created_at}
              </Descriptions.Item>
              <Descriptions.Item label="最后活跃" span={2}>
                {currentAgent.last_active_at || '-'}
              </Descriptions.Item>
            </Descriptions>

            <Divider>权限列表</Divider>

            <Space wrap>
              {currentAgent.permissions.map((perm) => (
                <Tag key={perm} color="blue">
                  {perm}
                </Tag>
              ))}
            </Space>
          </>
        )}
      </Modal>
    </div>
  )
}
