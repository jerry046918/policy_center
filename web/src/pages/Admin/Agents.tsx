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
  message,
  Tooltip,
  Typography,
} from 'antd'
import {
  PlusOutlined,
  KeyOutlined,
  StopOutlined,
  CheckCircleOutlined,
  DeleteOutlined,
  CopyOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  listApiKeys,
  createApiKey,
  toggleApiKeyStatus,
  deleteApiKey,
} from '../../services/apiKeyService'
import type { ApiKeyItem } from '../../services/apiKeyService'
import './Admin.css'

const { Paragraph } = Typography

export default function ApiKeysPage() {
  const [loading, setLoading] = useState(false)
  const [apiKeys, setApiKeys] = useState<ApiKeyItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [modalVisible, setModalVisible] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newKeyModalVisible, setNewKeyModalVisible] = useState(false)
  const [newApiKey, setNewApiKey] = useState('')
  const [form] = Form.useForm()

  useEffect(() => {
    loadApiKeys()
  }, [page, pageSize])

  const loadApiKeys = async () => {
    setLoading(true)
    try {
      const res = await listApiKeys({ page, page_size: pageSize })
      setApiKeys(res.data || [])
      setTotal(res.total || 0)
    } catch (error) {
      console.error('加载 API Key 列表失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async (values: { agent_name: string; description?: string }) => {
    setCreating(true)
    try {
      const result = await createApiKey(values)
      setNewApiKey(result.api_key)
      setModalVisible(false)
      setNewKeyModalVisible(true)
      form.resetFields()
      loadApiKeys()
    } catch (error) {
      message.error('创建失败')
    } finally {
      setCreating(false)
    }
  }

  const handleToggleStatus = async (record: ApiKeyItem) => {
    const newActive = !record.is_active
    try {
      await toggleApiKeyStatus(record.agent_id, newActive)
      message.success(newActive ? '已启用' : '已停用')
      loadApiKeys()
    } catch (error) {
      message.error('操作失败')
    }
  }

  const handleDelete = (record: ApiKeyItem) => {
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除 API Key「${record.agent_name}」吗？删除后将无法恢复。`,
      okText: '删除',
      okType: 'danger',
      onOk: async () => {
        try {
          await deleteApiKey(record.agent_id)
          message.success('已删除')
          loadApiKeys()
        } catch (error) {
          message.error('删除失败')
        }
      },
    })
  }

  const handleCopyKey = (key: string) => {
    navigator.clipboard.writeText(key).then(() => {
      message.success('已复制到剪贴板')
    }).catch(() => {
      message.error('复制失败，请手动复制')
    })
  }

  const columns: ColumnsType<ApiKeyItem> = [
    {
      title: '名称',
      dataIndex: 'agent_name',
      key: 'agent_name',
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      render: (text) => text || '-',
    },
    {
      title: 'Key 前缀',
      dataIndex: 'api_key_prefix',
      key: 'api_key_prefix',
      render: (prefix) => (
        <Tag icon={<KeyOutlined />} color="blue">
          {prefix}****
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (active) => (
        <Tag color={active ? 'green' : 'default'}>
          {active ? '启用' : '停用'}
        </Tag>
      ),
    },
    {
      title: '最后使用',
      dataIndex: 'last_used_at',
      key: 'last_used_at',
      render: (time) => time || '从未使用',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
    },
    {
      title: '操作',
      key: 'action',
      width: 160,
      render: (_, record) => (
        <Space size="small">
          <Tooltip title={record.is_active ? '停用' : '启用'}>
            <Button
              type="text"
              size="small"
              icon={record.is_active ? <StopOutlined /> : <CheckCircleOutlined />}
              onClick={() => handleToggleStatus(record)}
            />
          </Tooltip>
          <Tooltip title="删除">
            <Button
              type="text"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={() => handleDelete(record)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ]

  return (
    <div className="admin-page">
      <Card
        title="API Key 管理"
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setModalVisible(true)}
          >
            创建 API Key
          </Button>
        }
      >
        <Paragraph type="secondary" style={{ marginBottom: 16 }}>
          API Key 用于外部系统接入，持有 Key 即可查询政策、获取 Schema 及提交审核。
        </Paragraph>
        <Table
          columns={columns}
          dataSource={apiKeys}
          rowKey="agent_id"
          loading={loading}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (t) => `共 ${t} 个 API Key`,
            onChange: (p, ps) => {
              setPage(p)
              setPageSize(ps)
            },
          }}
        />
      </Card>

      {/* 创建 API Key 弹窗 */}
      <Modal
        title="创建 API Key"
        open={modalVisible}
        onCancel={() => {
          setModalVisible(false)
          form.resetFields()
        }}
        onOk={() => form.submit()}
        confirmLoading={creating}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            name="agent_name"
            label="名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="如：政策爬虫、外部对接系统" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="用途说明（可选）" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 显示新创建的 API Key */}
      <Modal
        title="API Key 创建成功"
        open={newKeyModalVisible}
        onCancel={() => {
          setNewKeyModalVisible(false)
          setNewApiKey('')
        }}
        footer={[
          <Button key="copy" type="primary" icon={<CopyOutlined />} onClick={() => handleCopyKey(newApiKey)}>
            复制 Key
          </Button>,
          <Button key="close" onClick={() => { setNewKeyModalVisible(false); setNewApiKey('') }}>
            关闭
          </Button>,
        ]}
      >
        <p style={{ marginBottom: 8, color: '#ff4d4f', fontWeight: 500 }}>
          请立即保存此 API Key，关闭后将无法再次查看完整内容。
        </p>
        <Input.TextArea
          value={newApiKey}
          readOnly
          rows={2}
          style={{ fontFamily: 'monospace', fontSize: 13 }}
        />
      </Modal>
    </div>
  )
}
