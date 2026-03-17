import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Card,
  Descriptions,
  Button,
  Tag,
  Table,
  Timeline,
  Spin,
  message,
  Row,
  Col,
} from 'antd'
import {
  ArrowLeftOutlined,
  EditOutlined,
  HistoryOutlined,
} from '@ant-design/icons'
import { getPolicy, getPolicyVersions } from '../../services/policy'
import type { Policy } from '../../types/policy'
import { POLICY_STATUS_MAP } from '../../types/policy'
import { getPolicyTypeLabel } from '../../types/policy'
import PolicyContentCard from '../../components/PolicyContentCard'
import RawEvidenceCard from '../../components/RawEvidenceCard'
import './PolicyDetail.css'

export default function PolicyDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [policy, setPolicy] = useState<Policy | null>(null)
  const [versions, setVersions] = useState<any[]>([])

  useEffect(() => {
    if (id) {
      loadPolicy(id)
      loadVersions(id)
    }
  }, [id])

  const loadPolicy = async (policyId: string) => {
    setLoading(true)
    try {
      const data = await getPolicy(policyId)
      setPolicy(data)
    } catch (error) {
      message.error('加载政策详情失败')
    } finally {
      setLoading(false)
    }
  }

  const loadVersions = async (policyId: string) => {
    try {
      const response = await getPolicyVersions(policyId)
      setVersions(response.data || [])
    } catch (error) {
      console.error('加载版本历史失败:', error)
    }
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!policy) {
    return (
      <Card>
        <div style={{ textAlign: 'center', padding: 50 }}>
          <p>政策不存在或已删除</p>
          <Button onClick={() => navigate('/policies')}>返回列表</Button>
        </div>
      </Card>
    )
  }

  const statusConfig = POLICY_STATUS_MAP[policy.status] || { label: policy.status, color: 'default' }
  const typeConfig = getPolicyTypeLabel(policy.policy_type)

  const versionColumns = [
    { title: '版本', dataIndex: 'version_number', key: 'version', width: 80 },
    {
      title: '变更类型',
      dataIndex: 'change_type',
      key: 'change_type',
      render: (type: string) => {
        const typeMap: Record<string, { label: string; color: string }> = {
          create: { label: '创建', color: 'blue' },
          update: { label: '更新', color: 'green' },
          rollback: { label: '回滚', color: 'orange' },
          correction: { label: '修正', color: 'purple' },
        }
        const config = typeMap[type] || { label: type, color: 'default' }
        return <Tag color={config.color}>{config.label}</Tag>
      },
    },
    { title: '变更说明', dataIndex: 'change_reason', key: 'reason' },
    { title: '操作人', dataIndex: 'changed_by', key: 'changed_by', width: 100 },
    { title: '变更时间', dataIndex: 'changed_at', key: 'changed_at', width: 180 },
  ]

  return (
    <div className="policy-detail">
      {/* 头部操作栏 */}
      <div className="detail-header">
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/policies')}>
          返回列表
        </Button>
        <div className="header-tags">
          <Tag color={statusConfig.color}>{statusConfig.label}</Tag>
          <Tag color={typeConfig.color}>{typeConfig.label}</Tag>
          {policy.region_name && <Tag color="blue">{policy.region_name}</Tag>}
        </div>
        <div className="header-actions">
          <Button icon={<EditOutlined />} type="primary" onClick={() => navigate(`/policies/${id}/edit`)}>
            编辑
          </Button>
        </div>
      </div>

      <Row gutter={24}>
        {/* 左侧：政策内容（统一组件） */}
        <Col span={16}>
          <PolicyContentCard
            data={{
              title: policy.title,
              policy_type: policy.policy_type,
              region_name: policy.region_name,
              region_code: policy.region_code,
              policy_year: policy.policy_year,
              published_at: policy.published_at,
              effective_start: policy.effective_start,
              effective_end: policy.effective_end,
              si_upper_limit: policy.social_insurance?.si_upper_limit ?? policy.type_data?.si_upper_limit,
              si_lower_limit: policy.social_insurance?.si_lower_limit ?? policy.type_data?.si_lower_limit,
              hf_upper_limit: policy.type_data?.hf_upper_limit,
              hf_lower_limit: policy.type_data?.hf_lower_limit,
              is_retroactive: policy.social_insurance?.is_retroactive ?? policy.type_data?.is_retroactive,
              retroactive_start: policy.social_insurance?.retroactive_start ?? policy.type_data?.retroactive_start,
              coverage_types: policy.social_insurance?.coverage_types ?? policy.type_data?.coverage_types,
              special_notes: policy.social_insurance?.special_notes ?? policy.type_data?.special_notes,
            }}
          />
        </Col>

        {/* 右侧：版本信息 & 原始证据 */}
        <Col span={8}>
          <Card title="版本历史" extra={<HistoryOutlined />}>
            <Timeline
              items={versions.slice(0, 5).map((v) => ({
                color: v.change_type === 'create' ? 'green' : 'blue',
                children: (
                  <div>
                    <div>
                      <Tag>{`v${v.version_number}`}</Tag>
                      {v.change_type}
                    </div>
                    <div style={{ fontSize: 12, color: '#8c8c8c' }}>{v.changed_at}</div>
                  </div>
                ),
              }))}
            />
            {versions.length > 5 && (
              <Button type="link" block>
                查看全部版本
              </Button>
            )}
          </Card>

          {/* 创建信息 */}
          <Card title="创建信息" style={{ marginTop: 16 }}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="创建时间">{policy.created_at}</Descriptions.Item>
              <Descriptions.Item label="创建人">{policy.created_by || '-'}</Descriptions.Item>
              {policy.reviewed_by && (
                <Descriptions.Item label="审核人">{policy.reviewed_by}</Descriptions.Item>
              )}
            </Descriptions>
          </Card>

          {/* 原始证据 */}
          <RawEvidenceCard
            rawEvidence={{
              source_attachments: policy.source_attachments,
            }}
          />
        </Col>
      </Row>

      {/* 版本历史表格 */}
      <Card title="版本历史详情" style={{ marginTop: 16 }}>
        <Table
          columns={versionColumns}
          dataSource={versions}
          rowKey="version_id"
          pagination={false}
          size="small"
        />
      </Card>
    </div>
  )
}
