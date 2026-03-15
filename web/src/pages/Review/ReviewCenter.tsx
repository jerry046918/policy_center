import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card,
  Table,
  Tag,
  Button,
  Space,
  Badge,
  Tabs,
  Tooltip,
} from 'antd'
import { EyeOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { getReviews } from '../../services/review'
import type { ReviewItem } from '../../services/review'
import './ReviewCenter.css'

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: '待审核', color: 'orange' },
  claimed: { label: '审核中', color: 'blue' },
  approved: { label: '已通过', color: 'green' },
  rejected: { label: '已拒绝', color: 'red' },
}

export default function ReviewCenter() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [reviews, setReviews] = useState<ReviewItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [activeTab, setActiveTab] = useState('pending')

  useEffect(() => {
    loadReviews()
  }, [activeTab, page])

  const loadReviews = async () => {
    setLoading(true)
    try {
      const res = await getReviews({
        status: activeTab === 'all' ? undefined : activeTab,
        page,
        page_size: 20,
      })
      setReviews(res.data || [])
      setTotal(res.total || 0)
    } catch (error) {
      console.error('加载审核列表失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const columns: ColumnsType<ReviewItem> = [
    {
      title: '政策名称',
      dataIndex: 'policy_title',
      key: 'policy_title',
      ellipsis: true,
      render: (text, record) => (
        <a onClick={() => navigate(`/reviews/${record.review_id}`)}>{text}</a>
      ),
    },
    {
      title: '地区',
      dataIndex: 'region_name',
      key: 'region_name',
      width: 100,
      render: (text, record) => text || record.region_code,
    },
    {
      title: '提交时间',
      dataIndex: 'submitted_at',
      key: 'submitted_at',
      width: 180,
    },
    {
      title: '提交人',
      dataIndex: 'submitted_by',
      key: 'submitted_by',
      width: 120,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status) => {
        const config = STATUS_MAP[status] || { label: status, color: 'default' }
        return <Tag color={config.color}>{config.label}</Tag>
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      fixed: 'right',
      render: (_, record) => (
        <Tooltip title="查看详情">
          <Button
            type="text"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => navigate(`/reviews/${record.review_id}`)}
          />
        </Tooltip>
      ),
    },
  ]

  const tabItems = [
    { key: 'pending', label: '待审核' },
    { key: 'approved', label: '已通过' },
    { key: 'rejected', label: '已拒绝' },
    { key: 'all', label: '全部' },
  ]

  return (
    <div className="review-center">
      <Card>
        <Tabs activeKey={activeTab} items={tabItems} onChange={setActiveTab} />

        <Table
          columns={columns}
          dataSource={reviews}
          rowKey="review_id"
          loading={loading}
          scroll={{ x: 800 }}
          pagination={{
            current: page,
            pageSize: 20,
            total,
            showSizeChanger: false,
            showQuickJumper: true,
            showTotal: (total) => `共 ${total} 条`,
            onChange: (p) => setPage(p),
          }}
        />
      </Card>
    </div>
  )
}
