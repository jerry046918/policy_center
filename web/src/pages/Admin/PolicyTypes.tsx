import { useState, useEffect } from 'react'
import {
  Card, Table, Button, Modal, Form, Input, Switch, Tag, Space,
  Popconfirm, message, Tooltip, Badge, InputNumber, Typography
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined,
  LockOutlined, AppstoreOutlined, ExperimentOutlined
} from '@ant-design/icons'
import {
  listPolicyTypes, createPolicyType, updatePolicyType, deletePolicyType,
  PolicyTypeItem, PolicyTypeCreateInput, PolicyTypeUpdateInput
} from '../../services/policyTypeService'
import './Admin.css'

const { TextArea } = Input
const { Text } = Typography

export default function PolicyTypes() {
  const [loading, setLoading] = useState(false)
  const [types, setTypes] = useState<PolicyTypeItem[]>([])
  const [createModalVisible, setCreateModalVisible] = useState(false)
  const [editModalVisible, setEditModalVisible] = useState(false)
  const [currentType, setCurrentType] = useState<PolicyTypeItem | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [createForm] = Form.useForm()
  const [editForm] = Form.useForm()

  const loadTypes = async () => {
    setLoading(true)
    try {
      const res: any = await listPolicyTypes()
      setTypes(res.data || [])
    } catch {
      message.error('加载政策类型失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadTypes() }, [])

  const handleCreate = async (values: any) => {
    setSubmitting(true)
    try {
      // 解析 JSON 字段
      const input: PolicyTypeCreateInput = {
        type_code: values.type_code,
        type_name: values.type_name,
        description: values.description,
        field_schema: values.field_schema_json ? JSON.parse(values.field_schema_json) : {},
        validation_rules: values.validation_rules_text
          ? values.validation_rules_text.split('\n').filter((s: string) => s.trim())
          : [],
        example_data: values.example_data_json ? JSON.parse(values.example_data_json) : {},
        icon: values.icon,
        sort_order: values.sort_order || 0,
      }
      await createPolicyType(input)
      message.success('政策类型创建成功')
      setCreateModalVisible(false)
      createForm.resetFields()
      loadTypes()
    } catch (e: any) {
      message.error(e?.message || '创建失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleEdit = (record: PolicyTypeItem) => {
    setCurrentType(record)
    editForm.setFieldsValue({
      type_name: record.type_name,
      description: record.description,
      field_schema_json: JSON.stringify(record.field_schema, null, 2),
      validation_rules_text: record.validation_rules.join('\n'),
      example_data_json: JSON.stringify(record.example_data, null, 2),
      icon: record.icon,
      sort_order: record.sort_order,
      is_active: record.is_active,
    })
    setEditModalVisible(true)
  }

  const handleUpdate = async (values: any) => {
    if (!currentType) return
    setSubmitting(true)
    try {
      const input: PolicyTypeUpdateInput = {}

      if (currentType.is_builtin) {
        // 内置类型只能改有限字段
        if (values.description !== undefined) input.description = values.description
        if (values.icon !== undefined) input.icon = values.icon
        if (values.sort_order !== undefined) input.sort_order = values.sort_order
        if (values.is_active !== undefined) input.is_active = values.is_active
      } else {
        input.type_name = values.type_name
        input.description = values.description
        input.icon = values.icon
        input.sort_order = values.sort_order
        input.is_active = values.is_active
        if (values.field_schema_json) {
          input.field_schema = JSON.parse(values.field_schema_json)
        }
        if (values.validation_rules_text !== undefined) {
          input.validation_rules = values.validation_rules_text
            ? values.validation_rules_text.split('\n').filter((s: string) => s.trim())
            : []
        }
        if (values.example_data_json) {
          input.example_data = JSON.parse(values.example_data_json)
        }
      }

      await updatePolicyType(currentType.type_code, input)
      message.success('更新成功')
      setEditModalVisible(false)
      loadTypes()
    } catch (e: any) {
      message.error(e?.message || '更新失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (typeCode: string) => {
    try {
      await deletePolicyType(typeCode)
      message.success('删除成功')
      loadTypes()
    } catch (e: any) {
      message.error(e?.message || '删除失败')
    }
  }

  const handleToggleActive = async (record: PolicyTypeItem) => {
    try {
      await updatePolicyType(record.type_code, { is_active: !record.is_active })
      message.success(record.is_active ? '已禁用' : '已启用')
      loadTypes()
    } catch (e: any) {
      message.error(e?.message || '操作失败')
    }
  }

  const columns = [
    {
      title: '类型编码',
      dataIndex: 'type_code',
      key: 'type_code',
      width: 180,
      render: (code: string, record: PolicyTypeItem) => (
        <Space>
          {record.is_builtin
            ? <LockOutlined style={{ color: '#8c8c8c' }} />
            : <ExperimentOutlined style={{ color: '#722ed1' }} />
          }
          <Text code>{code}</Text>
        </Space>
      ),
    },
    {
      title: '名称',
      dataIndex: 'type_name',
      key: 'type_name',
      width: 160,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '字段数',
      key: 'field_count',
      width: 80,
      render: (_: any, record: PolicyTypeItem) =>
        Object.keys(record.field_schema).length,
    },
    {
      title: '关联政策',
      dataIndex: 'policy_count',
      key: 'policy_count',
      width: 100,
      render: (count: number) => (
        <Badge count={count} showZero style={{ backgroundColor: count > 0 ? '#1677ff' : '#d9d9d9' }} />
      ),
    },
    {
      title: '类型',
      key: 'source',
      width: 80,
      render: (_: any, record: PolicyTypeItem) => (
        record.is_builtin
          ? <Tag color="default">内置</Tag>
          : <Tag color="purple">自定义</Tag>
      ),
    },
    {
      title: '状态',
      key: 'is_active',
      width: 80,
      render: (_: any, record: PolicyTypeItem) => (
        <Tag color={record.is_active ? 'green' : 'default'}>
          {record.is_active ? '启用' : '禁用'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_: any, record: PolicyTypeItem) => (
        <Space size="small">
          <Tooltip title="编辑">
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEdit(record)}
            />
          </Tooltip>
          <Tooltip title={record.is_active ? '禁用' : '启用'}>
            <Button
              type="text"
              size="small"
              onClick={() => handleToggleActive(record)}
            >
              {record.is_active ? '禁用' : '启用'}
            </Button>
          </Tooltip>
          {!record.is_builtin && (
            <Popconfirm
              title="确定删除此政策类型?"
              description={record.policy_count > 0 ? '该类型下有关联政策，无法删除' : undefined}
              onConfirm={() => handleDelete(record.type_code)}
              disabled={record.policy_count > 0}
            >
              <Tooltip title={record.policy_count > 0 ? '有关联政策，无法删除' : '删除'}>
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  disabled={record.policy_count > 0}
                />
              </Tooltip>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  const fieldSchemaPlaceholder = `{
  "amount": {
    "type": "integer",
    "required": true,
    "description": "金额（元）",
    "gt": 0
  },
  "notes": {
    "type": "string",
    "required": false,
    "max_length": 1000,
    "description": "备注"
  }
}`

  return (
    <div className="admin-page">
      <Card
        title={
          <Space>
            <AppstoreOutlined />
            政策类型管理
          </Space>
        }
        extra={
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateModalVisible(true)}
          >
            新建类型
          </Button>
        }
      >
        <Table
          columns={columns}
          dataSource={types}
          rowKey="type_code"
          loading={loading}
          pagination={false}
          size="middle"
        />
      </Card>

      {/* 创建弹窗 */}
      <Modal
        title="新建政策类型"
        open={createModalVisible}
        onCancel={() => { setCreateModalVisible(false); createForm.resetFields() }}
        onOk={() => createForm.submit()}
        confirmLoading={submitting}
        width={640}
      >
        <Form form={createForm} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="type_code" label="类型编码" rules={[
            { required: true, message: '请输入类型编码' },
            { pattern: /^[a-z][a-z0-9_]*$/, message: '小写字母开头，仅含字母、数字、下划线' }
          ]}>
            <Input placeholder="如: minimum_wage" />
          </Form.Item>
          <Form.Item name="type_name" label="类型名称" rules={[{ required: true }]}>
            <Input placeholder="如: 最低工资标准" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="描述该政策类型的用途" />
          </Form.Item>
          <Form.Item
            name="field_schema_json"
            label="字段定义 (JSON)"
            rules={[{
              validator: (_, v) => {
                if (!v) return Promise.resolve()
                try { JSON.parse(v); return Promise.resolve() }
                catch { return Promise.reject('JSON 格式无效') }
              }
            }]}
          >
            <TextArea
              rows={8}
              placeholder={fieldSchemaPlaceholder}
              style={{ fontFamily: 'monospace', fontSize: 12 }}
            />
          </Form.Item>
          <Form.Item name="validation_rules_text" label="验证规则（每行一条）">
            <TextArea rows={3} placeholder="如: amount > 0" />
          </Form.Item>
          <Form.Item
            name="example_data_json"
            label="示例数据 (JSON)"
            rules={[{
              validator: (_, v) => {
                if (!v) return Promise.resolve()
                try { JSON.parse(v); return Promise.resolve() }
                catch { return Promise.reject('JSON 格式无效') }
              }
            }]}
          >
            <TextArea rows={4} style={{ fontFamily: 'monospace', fontSize: 12 }} />
          </Form.Item>
          <Form.Item name="sort_order" label="排序权重">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑弹窗 */}
      <Modal
        title={`编辑: ${currentType?.type_name || ''}`}
        open={editModalVisible}
        onCancel={() => { setEditModalVisible(false); setCurrentType(null) }}
        onOk={() => editForm.submit()}
        confirmLoading={submitting}
        width={640}
      >
        <Form form={editForm} layout="vertical" onFinish={handleUpdate}>
          {currentType?.is_builtin && (
            <div style={{ marginBottom: 16, padding: '8px 12px', background: '#fff7e6', borderRadius: 6 }}>
              <LockOutlined style={{ marginRight: 6, color: '#fa8c16' }} />
              <Text type="warning">内置类型，仅可修改描述、排序和启用状态</Text>
            </div>
          )}
          <Form.Item name="type_name" label="类型名称" rules={[{ required: true }]}>
            <Input disabled={currentType?.is_builtin} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <TextArea rows={2} />
          </Form.Item>
          {!currentType?.is_builtin && (
            <>
              <Form.Item
                name="field_schema_json"
                label="字段定义 (JSON)"
                rules={[{
                  validator: (_, v) => {
                    if (!v) return Promise.resolve()
                    try { JSON.parse(v); return Promise.resolve() }
                    catch { return Promise.reject('JSON 格式无效') }
                  }
                }]}
              >
                <TextArea rows={8} style={{ fontFamily: 'monospace', fontSize: 12 }} />
              </Form.Item>
              <Form.Item name="validation_rules_text" label="验证规则（每行一条）">
                <TextArea rows={3} />
              </Form.Item>
              <Form.Item
                name="example_data_json"
                label="示例数据 (JSON)"
                rules={[{
                  validator: (_, v) => {
                    if (!v) return Promise.resolve()
                    try { JSON.parse(v); return Promise.resolve() }
                    catch { return Promise.reject('JSON 格式无效') }
                  }
                }]}
              >
                <TextArea rows={4} style={{ fontFamily: 'monospace', fontSize: 12 }} />
              </Form.Item>
            </>
          )}
          <Form.Item name="sort_order" label="排序权重">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="is_active" label="启用状态" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
