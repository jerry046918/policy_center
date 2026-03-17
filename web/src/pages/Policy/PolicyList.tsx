import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card,
  Table,
  Button,
  Input,
  Select,
  Space,
  Tag,
  Tooltip,
  message,
  Popconfirm,
  Row,
  Col,
  Alert,
} from 'antd'
import {
  SearchOutlined,
  PlusOutlined,
  EyeOutlined,
  DeleteOutlined,
  HistoryOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { getPolicies, deletePolicy, getRegions } from '../../services/policy'
import type { PolicyListItem, Region } from '../../types/policy'
import { getPolicyTypeLabel } from '../../types/policy'
import './PolicyList.css'

const { Search } = Input
const { Option } = Select

export default function PolicyList() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [policies, setPolicies] = useState<PolicyListItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [regions, setRegions] = useState<Region[]>([])
  const [filters, setFilters] = useState({
    region_code: '',
    year: undefined as number | undefined,
    keyword: '',
  })

  useEffect(() => {
    loadPolicies()
    loadRegions()
  }, [page, pageSize])

  const loadPolicies = async () => {
    setLoading(true)
    try {
      const res = await getPolicies({
        ...filters,
        page,
        page_size: pageSize,
      })
      setPolicies(res.data || [])
      setTotal(res.total || 0)
    } catch (error) {
      console.error('加载政策列表失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadRegions = async () => {
    try {
      const data = await getRegions(undefined, 'province')
      setRegions(data || [])
    } catch (error) {
      // 如果加载失败，使用空数组
      setRegions([])
    }
  }

  const handleSearch = () => {
    setPage(1)
    loadPolicies()
  }

  const handleDelete = async (policyId: string) => {
    try {
      await deletePolicy(policyId)
      message.success('删除成功')
      loadPolicies()
    } catch (error) {
      message.error('删除失败')
    }
  }

  const columns: ColumnsType<PolicyListItem> = [
    {
      title: '政策名称',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (text, record) => (
        <a onClick={() => navigate(`/policies/${record.policy_id}`)}>{text}</a>
      ),
    },
    {
      title: '类型',
      dataIndex: 'policy_type',
      key: 'policy_type',
      width: 130,
      render: (type: string) => {
        const config = getPolicyTypeLabel(type)
        return <Tag color={config.color}>{config.label}</Tag>
      },
    },
    {
      title: '地区',
      dataIndex: 'region_name',
      key: 'region_name',
      width: 120,
      render: (_, record) => record.region_name || record.region_code,
    },
    {
      title: '社保上限',
      dataIndex: 'si_upper_limit',
      key: 'si_upper',
      width: 120,
      align: 'right',
      render: (value) => (value ? `¥${value.toLocaleString()}` : '-'),
    },
    {
      title: '社保下限',
      dataIndex: 'si_lower_limit',
      key: 'si_lower',
      width: 120,
      align: 'right',
      render: (value) => (value ? `¥${value.toLocaleString()}` : '-'),
    },
    {
      title: '生效日期',
      dataIndex: 'effective_start',
      key: 'effective_start',
      width: 120,
    },
    {
      title: '追溯',
      dataIndex: 'is_retroactive',
      key: 'is_retroactive',
      width: 80,
      align: 'center',
      render: (value) =>
        value ? (
          <Tooltip title="追溯生效">
            <Tag color="orange">是</Tag>
          </Tooltip>
        ) : (
          '-'
        ),
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          <Tooltip title="查看详情">
            <Button
              type="text"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => navigate(`/policies/${record.policy_id}`)}
            />
          </Tooltip>
          <Tooltip title="版本历史">
            <Button
              type="text"
              size="small"
              icon={<HistoryOutlined />}
              onClick={() => navigate(`/policies/${record.policy_id}?tab=versions`)}
            />
          </Tooltip>
          <Popconfirm
            title="确定要删除该政策吗？"
            onConfirm={() => handleDelete(record.policy_id)}
          >
            <Tooltip title="删除">
              <Button type="text" size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="policy-list">
      <Alert
        message="政策条目说明"
        description="同一城市不同适用日期的政策视为不同的政策条目。例如：北京市2024年和2025年的社保基数政策是两条独立的记录。如需添加新年份的政策，请点击「新增政策」。"
        type="info"
        showIcon
        closable
        style={{ marginBottom: 16 }}
      />
      <Card>
        {/* 搜索筛选栏 */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={4}>
            <Select
              placeholder="选择地区"
              allowClear
              style={{ width: '100%' }}
              value={filters.region_code || undefined}
              onChange={(value) => setFilters({ ...filters, region_code: value || '' })}
            >
              {regions.map((r) => (
                <Option key={r.code} value={r.code}>
                  {r.name}
                </Option>
              ))}
            </Select>
          </Col>
          <Col span={3}>
            <Select
              placeholder="政策年度"
              allowClear
              style={{ width: '100%' }}
              onChange={(value) => setFilters({ ...filters, year: value })}
            >
              {[2026, 2025, 2024, 2023, 2022, 2021, 2020].map((y) => (
                <Option key={y} value={y}>
                  {y}年
                </Option>
              ))}
            </Select>
          </Col>
          <Col span={6}>
            <Search
              placeholder="搜索政策名称/文号"
              allowClear
              enterButton={<SearchOutlined />}
              onSearch={(value) => {
                setFilters({ ...filters, keyword: value })
                loadPolicies()
              }}
            />
          </Col>
          <Col span={11} style={{ textAlign: 'right' }}>
            <Space>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => navigate('/policies/create')}
              >
                新增政策
              </Button>
            </Space>
          </Col>
        </Row>

        {/* 表格 */}
        <Table
          columns={columns}
          dataSource={policies}
          rowKey="policy_id"
          loading={loading}
          scroll={{ x: 1200 }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 条`,
            onChange: (p, ps) => {
              setPage(p)
              setPageSize(ps)
            },
          }}
        />
      </Card>
    </div>
  )
}
