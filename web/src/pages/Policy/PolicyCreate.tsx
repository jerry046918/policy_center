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
import { createPolicy, getRegions, initRegions } from '../../services/policy'
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

  useEffect(() => {
    loadRegions()
  }, [])

  const loadRegions = async () => {
    try {
      // 先初始化地区数据
      await initRegions()
      const data = await getRegions(undefined, 'province')
      setRegions(data || [])
    } catch (error) {
      console.error('加载地区失败:', error)
    }
  }

  const handleSubmit = async (values: any) => {
    setLoading(true)
    try {
      const data: PolicyCreateInput = {
        title: values.title,
        region_code: values.region_code,
        published_at: values.published_at.format('YYYY-MM-DD'),
        effective_start: values.effective_start.format('YYYY-MM-DD'),
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
        raw_content: values.raw_content,
      }

      await createPolicy(data)
      message.success('政策创建成功，已直接生效')
      navigate('/policies')
    } catch (error) {
      message.error('创建失败，请检查输入')
    } finally {
      setLoading(false)
    }
  }

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
