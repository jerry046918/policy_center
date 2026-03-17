import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card,
  Form,
  Input,
  Select,
  DatePicker,
  InputNumber,
  Switch,
  Button,
  Row,
  Col,
  message,
  Space,
  Divider,
} from 'antd'
import { SaveOutlined, ArrowLeftOutlined } from '@ant-design/icons'
import { createPolicy, getRegions, getPolicyTypes } from '../../services/policy'
import type { PolicyTypeItem } from '../../services/policy'
import type { PolicyCreateInput } from '../../types/policy'
import './PolicyCreate.css'

const { TextArea } = Input
const { Option } = Select

export default function PolicyCreate() {
  const [form] = Form.useForm()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [isRetroactive, setIsRetroactive] = useState(false)
  const [regions, setRegions] = useState<any[]>([])
  const [policyType, setPolicyType] = useState<string>('social_insurance')
  const [policyTypes, setPolicyTypes] = useState<PolicyTypeItem[]>([])

  useEffect(() => {
    loadRegions()
    loadPolicyTypes()
  }, [])

  const loadRegions = async () => {
    try {
      const data = await getRegions(undefined, 'province')
      setRegions(data || [])
    } catch (error) {
      console.error('加载地区失败:', error)
    }
  }

  const loadPolicyTypes = async () => {
    try {
      const data = await getPolicyTypes()
      setPolicyTypes(data || [])
    } catch (error) {
      console.error('加载政策类型失败:', error)
    }
  }

  // 获取当前类型的 field_schema
  const currentTypeSchema = policyTypes.find(t => t.type_code === policyType)?.field_schema || {}

  const handleSubmit = async (values: any) => {
    setLoading(true)
    try {
      const baseData: any = {
        policy_type: policyType,
        title: values.title,
        region_code: values.region_code,
        published_at: values.published_at.format('YYYY-MM-DD'),
        effective_start: values.effective_start.format('YYYY-MM-DD'),
        effective_end: values.effective_end?.format('YYYY-MM-DD'),
        raw_content: values.raw_content,
      }

      // 收集 type_data：从 field_schema 中获取所有字段名
      const typeData: Record<string, any> = {}
      for (const [fieldName, fieldDef] of Object.entries(currentTypeSchema) as [string, any][]) {
        const val = values[fieldName]
        if (val !== undefined && val !== null && val !== '') {
          // 处理 DatePicker 类型的值
          if (val && typeof val === 'object' && typeof val.format === 'function') {
            typeData[fieldName] = val.format('YYYY-MM-DD')
          } else if (fieldDef.type === 'object' && typeof val === 'string') {
            // JSON 字符串 -> 对象
            try { typeData[fieldName] = JSON.parse(val) } catch { typeData[fieldName] = val }
          } else {
            typeData[fieldName] = val
          }
        }
      }
      baseData.type_data = typeData

      await createPolicy(baseData)
      message.success('政策创建成功')
      navigate('/policies')
    } catch (error) {
      message.error('创建失败，请检查输入')
    } finally {
      setLoading(false)
    }
  }

  // 根据 field_schema 动态渲染表单字段
  const renderDynamicFields = () => {
    const entries = Object.entries(currentTypeSchema)
    if (entries.length === 0) return null

    return entries.map(([fieldName, schema]: [string, any]) => {
      const { type, description, required, unit, items } = schema
      const label = description + (unit ? ` (${unit})` : '')
      const rules = required ? [{ required: true, message: `请输入${description}` }] : []

      if (type === 'integer' || type === 'number') {
        return (
          <Col span={12} key={fieldName}>
            <Form.Item name={fieldName} label={label} rules={rules}>
              <InputNumber style={{ width: '100%' }} min={0} precision={type === 'integer' ? 0 : 2} />
            </Form.Item>
          </Col>
        )
      }

      if (type === 'boolean') {
        return (
          <Col span={8} key={fieldName}>
            <Form.Item name={fieldName} label={label} valuePropName="checked">
              <Switch onChange={fieldName === 'is_retroactive' ? setIsRetroactive : undefined} />
            </Form.Item>
          </Col>
        )
      }

      if (type === 'date') {
        // 对追溯日期做条件展示
        if (fieldName === 'retroactive_start') {
          if (!isRetroactive) return null
          return (
            <Col span={12} key={fieldName}>
              <Form.Item name={fieldName} label={label} rules={isRetroactive ? [{ required: true, message: `请选择${description}` }] : []}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          )
        }
        return (
          <Col span={12} key={fieldName}>
            <Form.Item name={fieldName} label={label} rules={rules}>
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        )
      }

      if (type === 'array' && items?.enum) {
        return (
          <Col span={24} key={fieldName}>
            <Form.Item name={fieldName} label={label}>
              <Select mode="multiple" placeholder={`选择${description}`}>
                {items.enum.map((v: string) => (
                  <Option key={v} value={v}>{v}</Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
        )
      }

      if (type === 'array') {
        return (
          <Col span={24} key={fieldName}>
            <Form.Item name={fieldName} label={label}>
              <Select mode="tags" placeholder={`输入${description}，按回车添加`} />
            </Form.Item>
          </Col>
        )
      }

      if (type === 'object') {
        return (
          <Col span={24} key={fieldName}>
            <Form.Item name={fieldName} label={label} help="请输入 JSON 格式数据">
              <TextArea rows={3} placeholder={`{"key": "value"}`} />
            </Form.Item>
          </Col>
        )
      }

      // string 类型
      const maxLength = schema.max_length || 1000
      if (maxLength > 200) {
        return (
          <Col span={24} key={fieldName}>
            <Form.Item name={fieldName} label={label} rules={rules}>
              <TextArea rows={3} maxLength={maxLength} placeholder={`请输入${description}`} />
            </Form.Item>
          </Col>
        )
      }
      return (
        <Col span={12} key={fieldName}>
          <Form.Item name={fieldName} label={label} rules={rules}>
            <Input maxLength={maxLength} placeholder={`请输入${description}`} />
          </Form.Item>
        </Col>
      )
    })
  }

  const currentTypeName = policyTypes.find(t => t.type_code === policyType)?.type_name || '类型数据'

  return (
    <div className="policy-create">
      <div className="page-header">
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/policies')}>
          返回
        </Button>
        <h2>新增政策</h2>
      </div>

      <Form
        form={form}
        layout="vertical"
        onFinish={handleSubmit}
        initialValues={{
          policy_type: 'social_insurance',
          is_retroactive: false,
          coverage_types: ['养老', '医疗', '失业', '工伤', '生育'],
        }}
      >
        <Row gutter={24}>
          {/* 左侧：基础信息 */}
          <Col span={16}>
            <Card title="基础信息">
              <Form.Item
                name="title"
                label="政策名称"
                rules={[{ required: true, message: '请输入政策名称' }]}
              >
                <Input placeholder="如：2024年北京市社会保险缴费基数调整通知" maxLength={500} />
              </Form.Item>

              <Row gutter={16}>
                <Col span={24}>
                  <Form.Item
                    name="region_code"
                    label="地区"
                    rules={[{ required: true, message: '请选择地区' }]}
                  >
                    <Select placeholder="选择地区" showSearch optionFilterProp="children">
                      {regions.map((r) => (
                        <Option key={r.code} value={r.code}>
                          {r.name}
                        </Option>
                      ))}
                    </Select>
                  </Form.Item>
                </Col>
              </Row>

              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item
                    name="published_at"
                    label="发布日期"
                    rules={[{ required: true, message: '请选择发布日期' }]}
                  >
                    <DatePicker style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item
                    name="effective_start"
                    label="生效开始"
                    rules={[{ required: true, message: '请选择生效日期' }]}
                  >
                    <DatePicker style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name="effective_end" label="生效结束">
                    <DatePicker style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>

              <Form.Item name="policy_type" label="政策类型" rules={[{ required: true }]}>
                <Select
                  onChange={(v: string) => {
                    setPolicyType(v)
                    setIsRetroactive(false)
                  }}
                >
                  {policyTypes.map((t) => (
                    <Option key={t.type_code} value={t.type_code}>
                      {t.type_name}
                    </Option>
                  ))}
                </Select>
              </Form.Item>
            </Card>

            {/* 类型特定字段 - 动态渲染 */}
            {Object.keys(currentTypeSchema).length > 0 && (
              <Card title={currentTypeName} style={{ marginTop: 16 }}>
                <Row gutter={16}>
                  {renderDynamicFields()}
                </Row>
              </Card>
            )}
          </Col>

          {/* 右侧：原始内容 */}
          <Col span={8}>
            <Card title="原始内容">
              <Form.Item name="raw_content" label="原文内容">
                <TextArea
                  rows={10}
                  placeholder="粘贴 OCR 识别文本或公告原文"
                />
              </Form.Item>
            </Card>

            <Card title="操作" style={{ marginTop: 16 }}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Button
                  type="primary"
                  htmlType="submit"
                  icon={<SaveOutlined />}
                  loading={loading}
                  block
                  size="large"
                >
                  保存并生效
                </Button>
                <Button block size="large" onClick={() => form.resetFields()}>
                  重置表单
                </Button>
              </Space>
            </Card>
          </Col>
        </Row>
      </Form>
    </div>
  )
}
