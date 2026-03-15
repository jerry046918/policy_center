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
  Tree,
  Row,
  Col,
  Spin,
  Empty,
  Statistic,
} from 'antd'
import {
  PlusOutlined,
  GlobalOutlined,
  BankOutlined,
  EnvironmentOutlined,
  SyncOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import type { DataNode } from 'antd/es/tree'

import { getRegions, createRegion } from '../../services/policy'
import './Admin.css'

interface Region {
  code: string
  name: string
  level: string
  parent_code?: string
  full_path?: string
  min_wage?: number
  avg_salary?: number
}

const { Option } = Select

export default function RegionsPage() {
  const [loading, setLoading] = useState(false)
  const [allRegions, setAllRegions] = useState<Region[]>([])
  const [filteredRegions, setFilteredRegions] = useState<Region[]>([])
  const [modalVisible, setModalVisible] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()
  const [selectedRegionCode, setSelectedRegionCode] = useState<string | null>(null)
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([])

  useEffect(() => {
    loadRegions()
  }, [])

  const loadRegions = async () => {
    setLoading(true)
    try {
      // 加载所有地区（省份和城市）
      const [provinces, cities] = await Promise.all([
        getRegions(undefined, 'province'),
        getRegions(undefined, 'city'),
      ])

      const allData = [...provinces, ...cities]
      setAllRegions(allData)
      setFilteredRegions(allData)
      setSelectedRegionCode(null)
    } catch (error) {
      console.error('加载地区列表失败:', error)
      message.error('加载地区列表失败')
      setAllRegions([])
      setFilteredRegions([])
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async (values: any) => {
    setSubmitting(true)
    try {
      await createRegion({
        code: values.code,
        name: values.name,
        level: values.level,
        parent_code: values.parent_code || undefined,
      })
      message.success('地区创建成功')
      setModalVisible(false)
      form.resetFields()
      loadRegions()
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '创建失败')
    } finally {
      setSubmitting(false)
    }
  }

  const getLevelLabel = (level: string) => {
    const levelMap: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
      province: { label: '省级', color: 'blue', icon: <GlobalOutlined /> },
      city: { label: '市级', color: 'green', icon: <BankOutlined /> },
      district: { label: '区县级', color: 'orange', icon: <EnvironmentOutlined /> },
      country: { label: '国家', color: 'purple', icon: <TeamOutlined /> },
    }
    return levelMap[level] || { label: level, color: 'default', icon: null }
  }

  // Build tree data for the tree view
  const buildTreeData = (regions: Region[]): DataNode[] => {
    const provinces = regions.filter((r) => r.level === 'province')

    return provinces.map((province) => {
      const cities = regions.filter((r) => r.parent_code === province.code && r.level === 'city')

      return {
        title: (
          <span>
            <GlobalOutlined style={{ marginRight: 6, color: '#1890ff' }} />
            {province.name}
          </span>
        ),
        key: province.code,
        icon: null,
        children:
          cities.length > 0
            ? cities.map((city) => ({
                title: (
                  <span>
                    <BankOutlined style={{ marginRight: 6, color: '#52c41a' }} />
                    {city.name}
                  </span>
                ),
                key: city.code,
                icon: null,
                isLeaf: true,
              }))
            : undefined,
      }
    })
  }

  const handleTreeSelect = (keys: React.Key[]) => {
    if (keys.length > 0) {
      const selectedCode = keys[0] as string
      setSelectedRegionCode(selectedCode)

      // 筛选：选中地区及其下级
      const selectedRegion = allRegions.find((r) => r.code === selectedCode)
      if (selectedRegion) {
        const children = allRegions.filter((r) => r.parent_code === selectedCode)
        setFilteredRegions([selectedRegion, ...children])
      }
    } else {
      // 取消选中时显示全部
      setSelectedRegionCode(null)
      setFilteredRegions(allRegions)
    }
  }

  const handleExpand = (keys: React.Key[]) => {
    setExpandedKeys(keys)
  }

  // 清除筛选，显示全部
  const handleClearFilter = () => {
    setSelectedRegionCode(null)
    setFilteredRegions(allRegions)
  }

  const columns = [
    {
      title: '地区编码',
      dataIndex: 'code',
      key: 'code',
      width: 120,
    },
    {
      title: '地区名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: Region) => {
        const config = getLevelLabel(record.level)
        return (
          <Space>
            {config.icon}
            <strong>{text}</strong>
          </Space>
        )
      },
    },
    {
      title: '级别',
      dataIndex: 'level',
      key: 'level',
      width: 100,
      render: (level: string) => {
        const config = getLevelLabel(level)
        return <Tag color={config.color} icon={config.icon}>{config.label}</Tag>
      },
    },
    {
      title: '完整路径',
      dataIndex: 'full_path',
      key: 'full_path',
      ellipsis: true,
    },
  ]

  // 统计数据
  const provinceCount = allRegions.filter((r) => r.level === 'province').length
  const cityCount = allRegions.filter((r) => r.level === 'city').length

  return (
    <div className="admin-page">
      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="省份/直辖市"
              value={provinceCount}
              prefix={<GlobalOutlined style={{ color: '#1890ff' }} />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="地级市"
              value={cityCount}
              prefix={<BankOutlined style={{ color: '#52c41a' }} />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="地区总数"
              value={allRegions.length}
              prefix={<EnvironmentOutlined style={{ color: '#722ed1' }} />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="覆盖全国"
              value={provinceCount > 0 ? '100%' : '0%'}
              prefix={<TeamOutlined style={{ color: '#fa8c16' }} />}
              valueStyle={{ color: '#fa8c16' }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        {/* 左侧：树形结构 */}
        <Col span={8}>
          <Card
            title={
              <Space>
                <GlobalOutlined />
                <span>地区层级</span>
              </Space>
            }
            className="region-tree-card"
            extra={
              <Button icon={<SyncOutlined />} onClick={loadRegions} size="small">
                刷新
              </Button>
            }
          >
            {loading ? (
              <div style={{ textAlign: 'center', padding: 40 }}>
                <Spin />
              </div>
            ) : allRegions.length === 0 ? (
              <Empty description="暂无地区数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Tree
                showIcon={false}
                expandedKeys={expandedKeys}
                onExpand={handleExpand}
                treeData={buildTreeData(allRegions)}
                onSelect={handleTreeSelect}
                selectedKeys={selectedRegionCode ? [selectedRegionCode] : []}
                style={{ height: 500, overflow: 'auto' }}
              />
            )}
          </Card>
        </Col>

        {/* 右侧：表格 */}
        <Col span={16}>
          <Card
            title={
              <Space>
                <BankOutlined />
                <span>地区列表</span>
                {selectedRegionCode && (
                  <Tag color="blue" closable onClose={handleClearFilter}>
                    筛选: {allRegions.find((r) => r.code === selectedRegionCode)?.name}
                  </Tag>
                )}
              </Space>
            }
            extra={
              <Space>
                {selectedRegionCode && (
                  <Button onClick={handleClearFilter}>显示全部</Button>
                )}
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalVisible(true)}>
                  新增地区
                </Button>
              </Space>
            }
          >
            <Table
              columns={columns}
              dataSource={filteredRegions}
              rowKey="code"
              loading={loading}
              size="small"
              pagination={{
                showSizeChanger: true,
                showQuickJumper: true,
                showTotal: (total) => `共 ${total} 个地区`,
                pageSize: 20,
              }}
            />
          </Card>
        </Col>
      </Row>

      {/* 新增地区弹窗 */}
      <Modal
        title={
          <Space>
            <PlusOutlined style={{ color: '#1890ff' }} />
            <span>新增地区</span>
          </Space>
        }
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
        confirmLoading={submitting}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            name="code"
            label="地区编码"
            rules={[
              { required: true, message: '请输入地区编码' },
              { pattern: /^\d{6}$/, message: '编码必须为6位数字' },
            ]}
          >
            <Input placeholder="如：110101" prefix={<EnvironmentOutlined />} />
          </Form.Item>

          <Form.Item
            name="name"
            label="地区名称"
            rules={[{ required: true, message: '请输入地区名称' }]}
          >
            <Input placeholder="如：东城区" />
          </Form.Item>

          <Form.Item name="level" label="级别" rules={[{ required: true }]}>
            <Select placeholder="选择级别">
              <Option value="province">
                <Space>
                  <GlobalOutlined style={{ color: '#1890ff' }} />
                  省级
                </Space>
              </Option>
              <Option value="city">
                <Space>
                  <BankOutlined style={{ color: '#52c41a' }} />
                  市级
                </Space>
              </Option>
              <Option value="district">
                <Space>
                  <EnvironmentOutlined style={{ color: '#fa8c16' }} />
                  区县级
                </Space>
              </Option>
            </Select>
          </Form.Item>

          <Form.Item name="parent_code" label="上级行政区">
            <Select placeholder="选择上级行政区" allowClear showSearch optionFilterProp="children">
              {allRegions.map((r) => (
                <Option key={r.code} value={r.code}>
                  {r.name} ({r.code})
                </Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
