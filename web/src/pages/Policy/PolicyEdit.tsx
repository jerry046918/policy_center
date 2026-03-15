import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
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
  Spin,
  Alert,
  Radio,
} from 'antd'
import { SaveOutlined, ArrowLeftOutlined, PlusOutlined, EditOutlined } from '@ant-design/icons'
import { getPolicy, updatePolicy, getRegions } from '../../services/policy'
import type { Policy } from '../../types/policy'
import dayjs from 'dayjs'
import './PolicyCreate.css'

const { TextArea } = Input
const { Option } = Select

type UpdateMode = 'minor' | 'major'

export default function PolicyEdit() {
  const { id } = useParams<{ id: string }>()
  const [form] = Form.useForm()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [isRetroactive, setIsRetroactive] = useState(false)
  const [regions, setRegions] = useState<any[]>([])
  const [policy, setPolicy] = useState<Policy | null>(null)
  const [updateMode, setUpdateMode] = useState<UpdateMode>('minor')

  useEffect(() => {
    if (id) {
      loadPolicy(id)
      loadRegions()
    }
  }, [id])

  const loadPolicy = async (policyId: string) => {
    setLoading(true)
    try {
      const data = await getPolicy(policyId)
      setPolicy(data)

      // 填充表单
      form.setFieldsValue({
        title: data.title,
        region_code: data.region_code,
        published_at: data.published_at ? dayjs(data.published_at) : null,
        effective_start: data.effective_start ? dayjs(data.effective_start) : null,
        effective_end: data.effective_end ? dayjs(data.effective_end) : null,
        si_upper_limit: data.social_insurance?.si_upper_limit,
        si_lower_limit: data.social_insurance?.si_lower_limit,
        hf_upper_limit: data.social_insurance?.hf_upper_limit,
        hf_lower_limit: data.social_insurance?.hf_lower_limit,
        is_retroactive: data.social_insurance?.is_retroactive || false,
        retroactive_start: data.social_insurance?.retroactive_start ? dayjs(data.social_insurance.retroactive_start) : null,
        coverage_types: data.social_insurance?.coverage_types || ['养老', '医疗', '失业', '工伤', '生育'],
        special_notes: data.social_insurance?.special_notes,
      })

      setIsRetroactive(data.social_insurance?.is_retroactive || false)
    } catch (error) {
      message.error('加载政策详情失败')
      navigate('/policies')
    } finally {
      setLoading(false)
    }
  }

  const loadRegions = async () => {
    try {
      const data = await getRegions(undefined, 'province')
      setRegions(data || [])
    } catch (error) {
      console.error('加载地区失败:', error)
    }
  }

  const handleUpdate = async (values: any, mode: UpdateMode) => {
    if (!id) return

    setSaving(true)
    try {
      const data = {
        title: values.title,
        published_at: values.published_at?.format('YYYY-MM-DD'),
        effective_start: values.effective_start?.format('YYYY-MM-DD'),
        effective_end: values.effective_end?.format('YYYY-MM-DD'),
        social_insurance: {
          si_upper_limit: values.si_upper_limit,
          si_lower_limit: values.si_lower_limit,
          hf_upper_limit: values.hf_upper_limit,
          hf_lower_limit: values.hf_lower_limit,
          is_retroactive: values.is_retroactive,
          retroactive_start: values.retroactive_start?.format('YYYY-MM-DD'),
          coverage_types: values.coverage_types,
          special_notes: values.special_notes,
        },
        change_reason: values.change_reason || (mode === 'major' ? '发布新版本' : '微调更新'),
        create_new_version: mode === 'major',
      }

      await updatePolicy(id, data)
      message.success(mode === 'major' ? '新版本发布成功' : '当前版本更新成功')
      navigate(`/policies/${id}`)
    } catch (error) {
      message.error('更新失败，请检查输入')
    } finally {
      setSaving(false)
    }
  }

  const handleModeChange = (mode: UpdateMode) => {
    setUpdateMode(mode)
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div className="policy-create">
      <div className="page-header">
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(`/policies/${id}`)}>
          返回
        </Button>
        <h2>编辑政策</h2>
      </div>

      <Form
        form={form}
        layout="vertical"
        initialValues={{
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
                  >
                    <Select placeholder="选择地区" showSearch optionFilterProp="children" disabled>
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
            </Card>

            {/* 社保基数 */}
            <Card title="社保公积金基数" style={{ marginTop: 16 }}>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item
                    name="si_upper_limit"
                    label="社保基数上限（元/月）"
                    rules={[{ required: true, message: '请输入上限' }]}
                  >
                    <InputNumber
                      style={{ width: '100%' }}
                      min={0}
                      precision={0}
                      formatter={(value) => `¥ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                      parser={(value) => value!.replace(/\¥\s?|(,*)/g, '') as any}
                    />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    name="si_lower_limit"
                    label="社保基数下限（元/月）"
                    rules={[{ required: true, message: '请输入下限' }]}
                  >
                    <InputNumber
                      style={{ width: '100%' }}
                      min={0}
                      precision={0}
                      formatter={(value) => `¥ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                      parser={(value) => value!.replace(/\¥\s?|(,*)/g, '') as any}
                    />
                  </Form.Item>
                </Col>
              </Row>

              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="hf_upper_limit" label="公积金上限（元/月）">
                    <InputNumber
                      style={{ width: '100%' }}
                      min={0}
                      precision={0}
                      formatter={(value) => `¥ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                      parser={(value) => value!.replace(/\¥\s?|(,*)/g, '') as any}
                    />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="hf_lower_limit" label="公积金下限（元/月）">
                    <InputNumber
                      style={{ width: '100%' }}
                      min={0}
                      precision={0}
                      formatter={(value) => `¥ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                      parser={(value) => value!.replace(/\¥\s?|(,*)/g, '') as any}
                    />
                  </Form.Item>
                </Col>
              </Row>

              <Divider />

              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item name="is_retroactive" label="追溯生效" valuePropName="checked">
                    <Switch onChange={setIsRetroactive} />
                  </Form.Item>
                </Col>
                {isRetroactive && (
                  <Col span={16}>
                    <Form.Item
                      name="retroactive_start"
                      label="追溯开始日期"
                      rules={[{ required: isRetroactive, message: '请选择追溯日期' }]}
                    >
                      <DatePicker style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                )}
              </Row>

              <Form.Item name="coverage_types" label="险种覆盖">
                <Select mode="multiple" placeholder="选择覆盖险种">
                  <Option value="养老">养老</Option>
                  <Option value="医疗">医疗</Option>
                  <Option value="失业">失业</Option>
                  <Option value="工伤">工伤</Option>
                  <Option value="生育">生育</Option>
                  <Option value="公积金">公积金</Option>
                </Select>
              </Form.Item>

              <Form.Item name="special_notes" label="特殊说明">
                <TextArea rows={3} placeholder="如基数计算公式、特殊情况说明等" maxLength={1000} />
              </Form.Item>
            </Card>

            {/* 更新说明 */}
            <Card title="更新说明" style={{ marginTop: 16 }}>
              <Form.Item
                name="change_reason"
                label="更新备注"
                rules={[{ required: true, message: '请填写更新说明' }]}
              >
                <TextArea
                  rows={4}
                  placeholder="请描述本次更新的内容，例如：调整社保上限从31884调整为35283元"
                  maxLength={500}
                  showCount
                />
              </Form.Item>
            </Card>
          </Col>

          {/* 右侧：操作 */}
          <Col span={8}>
            <Card title="版本信息">
              <p>当前版本: <strong>v{policy?.version || 1}</strong></p>
              <p style={{ color: '#8c8c8c', fontSize: 12 }}>
                地区: {policy?.region_name || policy?.region_code}
              </p>
              <p style={{ color: '#8c8c8c', fontSize: 12 }}>
                生效日期: {policy?.effective_start}
              </p>
            </Card>

            <Card title="选择更新方式" style={{ marginTop: 16 }}>
              <Radio.Group
                value={updateMode}
                onChange={(e) => handleModeChange(e.target.value)}
                style={{ width: '100%' }}
              >
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Radio.Button
                    value="minor"
                    style={{ width: '100%', height: 'auto', padding: '12px 16px', textAlign: 'left' }}
                  >
                    <div>
                      <EditOutlined style={{ marginRight: 8 }} />
                      <strong>更新当前版本</strong>
                    </div>
                    <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 4 }}>
                      适用于微调（如修正错别字、补充说明），不增加版本号
                    </div>
                  </Radio.Button>
                  <Radio.Button
                    value="major"
                    style={{ width: '100%', height: 'auto', padding: '12px 16px', textAlign: 'left', marginTop: 8 }}
                  >
                    <div>
                      <PlusOutlined style={{ marginRight: 8 }} />
                      <strong>发布新版本</strong>
                    </div>
                    <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 4 }}>
                      适用于政策内容变更（如基数调整），创建新版本 v{(policy?.version || 1) + 1}
                    </div>
                  </Radio.Button>
                </Space>
              </Radio.Group>

              {updateMode === 'major' && (
                <Alert
                  message="新版本说明"
                  description="发布新版本后，当前版本将被归档，新版本成为生效版本。适用于政策内容发生实质性变更的情况。"
                  type="info"
                  showIcon
                  style={{ marginTop: 16 }}
                />
              )}
            </Card>

            <Card title="操作" style={{ marginTop: 16 }}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <Button
                  type="primary"
                  icon={updateMode === 'major' ? <PlusOutlined /> : <EditOutlined />}
                  loading={saving}
                  block
                  size="large"
                  onClick={() => {
                    form.validateFields().then((values) => {
                      handleUpdate(values, updateMode)
                    })
                  }}
                >
                  {updateMode === 'major' ? '发布新版本' : '更新当前版本'}
                </Button>
                <Button block size="large" onClick={() => navigate(`/policies/${id}`)}>
                  取消
                </Button>
              </Space>
            </Card>

            <Alert
              message="提示"
              description="同一城市不同适用日期的政策视为不同的政策条目。如需新增不同年度的政策，请使用「新增政策」功能。"
              type="warning"
              showIcon
              style={{ marginTop: 16 }}
            />
          </Col>
        </Row>
      </Form>
    </div>
  )
}
