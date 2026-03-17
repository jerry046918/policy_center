import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Row, Col, Statistic, Table, Tag, List, Typography, Button, Space, Badge, Tooltip, Alert, Spin, Empty } from 'antd'
import {
  FileTextOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  WarningOutlined,
  EnvironmentOutlined,
  AlertOutlined,
  RightOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { getDashboard } from '../services/dashboard'
import type { DashboardData, RecentPolicy, PendingReview, RetroactivePolicy } from '../services/dashboard'
import { PRIORITY_MAP, RISK_LEVEL_MAP } from '../types/policy'
import { getPolicyTypeLabel } from '../types/policy'
import './Dashboard.css'

const { Title, Text } = Typography

export default function Dashboard() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<DashboardData | null>(null)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const result = await getDashboard()
      setData(result)
    } catch (error) {
      console.error('加载看板数据失败:', error)
    } finally {
      setLoading(false)
    }
  }

  // 最近政策表格列
  const recentPolicyColumns: ColumnsType<RecentPolicy> = [
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
      width: 100,
    },
    {
      title: '生效日期',
      dataIndex: 'effective_start',
      key: 'effective_start',
      width: 120,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: () => <Tag color="green">生效中</Tag>,
    },
  ]

  // 获取 SLA 颜色
  const getSlaColor = (status: string) => {
    if (status === 'overdue') return '#ff4d4f'
    if (status === 'warning') return '#faad14'
    return '#52c41a'
  }

  // 获取 SLA 文本
  const getSlaText = (item: PendingReview) => {
    if (item.sla_status === 'overdue') return '已超期'
    if (item.sla_remaining_hours <= 1) return `${item.sla_remaining_hours.toFixed(1)}h`
    return `${Math.round(item.sla_remaining_hours)}h`
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!data) {
    return (
      <Card>
        <Empty description="暂无数据" />
      </Card>
    )
  }

  const { stats, recent_policies, pending_reviews, retroactive_policies } = data

  return (
    <div className="dashboard">
      <Title level={4}>数据看板</Title>

      {/* SLA 预警提示 */}
      {(stats.sla_overdue > 0 || stats.sla_warning > 0) && (
        <Alert
          type={stats.sla_overdue > 0 ? 'error' : 'warning'}
          showIcon
          icon={<AlertOutlined />}
          message={stats.sla_overdue > 0 ? 'SLA 超期预警' : 'SLA 即将到期'}
          description={
            stats.sla_overdue > 0
              ? `有 ${stats.sla_overdue} 个审核任务已超期，请立即处理`
              : `有 ${stats.sla_warning} 个审核任务将在4小时内到期`
          }
          style={{ marginBottom: 16 }}
          action={
            <Button size="small" onClick={() => navigate('/reviews')}>
              去处理
            </Button>
          }
        />
      )}

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card className="stat-card" hoverable onClick={() => navigate('/policies')}>
            <Statistic
              title="政策总数"
              value={stats.total_policies}
              prefix={<FileTextOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card className="stat-card" hoverable onClick={() => navigate('/policies?status=active')}>
            <Statistic
              title="生效政策"
              value={stats.active_policies}
              prefix={<CheckCircleOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card className="stat-card" hoverable onClick={() => navigate('/reviews')}>
            <Badge count={stats.sla_overdue + stats.sla_warning} offset={[10, 0]}>
              <Statistic
                title="待审核"
                value={stats.pending_reviews}
                prefix={<ClockCircleOutlined />}
                valueStyle={{ color: stats.pending_reviews > 0 ? '#faad14' : '#52c41a' }}
              />
            </Badge>
          </Card>
        </Col>
        <Col span={6}>
          <Card className="stat-card" hoverable onClick={() => navigate('/admin/regions')}>
            <Statistic
              title="地区覆盖"
              value={stats.regions_covered}
              suffix={`/ ${stats.total_regions}`}
              prefix={<EnvironmentOutlined />}
              valueStyle={{ color: '#722ed1' }}
            />
            <div style={{ marginTop: 8 }}>
              <Tag color={stats.regions_covered > 0 ? 'purple' : 'default'}>
                覆盖率 {((stats.regions_covered / stats.total_regions) * 100).toFixed(1)}%
              </Tag>
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        {/* 最近政策 */}
        <Col span={16}>
          <Card
            title="最近发布的政策"
            extra={<a onClick={() => navigate('/policies')}>查看全部 <RightOutlined /></a>}
          >
            {recent_policies.length > 0 ? (
              <Table
                dataSource={recent_policies}
                columns={recentPolicyColumns}
                rowKey="policy_id"
                pagination={false}
                size="small"
              />
            ) : (
              <Empty description="暂无政策" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>

        {/* 待审核队列 */}
        <Col span={8}>
          <Card
            title="待审核队列"
            extra={<a onClick={() => navigate('/reviews')}>查看全部 <RightOutlined /></a>}
          >
            {pending_reviews.length > 0 ? (
              <List
                dataSource={pending_reviews}
                renderItem={(item) => {
                  const riskConfig = RISK_LEVEL_MAP[item.risk_level] || { label: item.risk_level, color: 'default' }
                  const priorityConfig = PRIORITY_MAP[item.priority] || { label: item.priority, color: 'default' }

                  return (
                    <List.Item
                      className="pending-review-item"
                      onClick={() => navigate(`/reviews/${item.review_id}`)}
                    >
                      <List.Item.Meta
                        title={
                          <Space>
                            <span className="review-title">{item.policy_title}</span>
                            <Tag color={priorityConfig.color} style={{ marginLeft: 4 }}>
                              {priorityConfig.label}
                            </Tag>
                          </Space>
                        }
                        description={
                          <Space split={<Text type="secondary">·</Text>}>
                            <Tag color={getPolicyTypeLabel(item.policy_type).color} style={{ margin: 0 }}>
                              {getPolicyTypeLabel(item.policy_type).label}
                            </Tag>
                            <Text type="secondary">{item.region_name}</Text>
                            <Text type="secondary">{item.submitted_at}</Text>
                          </Space>
                        }
                      />
                      <Space direction="vertical" align="end" size={0}>
                        <Tag color={riskConfig.color}>{riskConfig.label}</Tag>
                        <Tooltip title="SLA 剩余时间">
                          <Text style={{ fontSize: 12, color: getSlaColor(item.sla_status) }}>
                            <ClockCircleOutlined /> {getSlaText(item)}
                          </Text>
                        </Tooltip>
                      </Space>
                    </List.Item>
                  )
                }}
              />
            ) : (
              <Empty description="暂无待审核" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
      </Row>

      {/* 追溯政策预警 */}
      <Card
        title={
          <Space>
            <WarningOutlined style={{ color: '#faad14' }} />
            <span>追溯政策预警</span>
            {retroactive_policies.length > 0 && (
              <Tag color="orange">{retroactive_policies.length}</Tag>
            )}
          </Space>
        }
        style={{ marginTop: 16 }}
      >
        {retroactive_policies.length > 0 ? (
          <List
            dataSource={retroactive_policies}
            renderItem={(item) => (
              <List.Item
                actions={[
                  <Button
                    key="detail"
                    size="small"
                    onClick={() => navigate(`/policies/${item.policy_id}`)}
                  >
                    查看详情
                  </Button>
                ]}
              >
                <List.Item.Meta
                  avatar={<WarningOutlined style={{ color: '#faad14', fontSize: 20 }} />}
                  title={item.title}
                  description={
                    <Space split={<Text type="secondary">·</Text>}>
                      <Text>{item.region_name}</Text>
                      <Text type="warning">追溯 {item.retroactive_months} 个月</Text>
                      <Text type="secondary">生效日期: {item.effective_start}</Text>
                      <Text type="secondary">追溯起始: {item.retroactive_start}</Text>
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        ) : (
          <Empty description="暂无追溯政策" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>
    </div>
  )
}
