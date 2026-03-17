import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Card,
  Descriptions,
  Button,
  Tag,
  Space,
  Row,
  Col,
  Input,
  message,
  Modal,
  Spin,
} from 'antd'
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  PlusCircleOutlined,
  SyncOutlined,
  LinkOutlined,
} from '@ant-design/icons'
import {
  getReview,
  approveReview,
  rejectReview,
} from '../../services/review'
import type { ReviewDetail } from '../../services/review'
import PolicyContentCard from '../../components/PolicyContentCard'
import RawEvidenceCard from '../../components/RawEvidenceCard'
import { REVIEW_STATUS_MAP } from '../../types/policy'
import { getPolicyTypeLabel } from '../../types/policy'
import './ReviewDetail.css'

const { TextArea } = Input

export default function ReviewDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [review, setReview] = useState<ReviewDetail | null>(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [rejectModal, setRejectModal] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [reviewNotes, setReviewNotes] = useState('')

  useEffect(() => {
    if (id) {
      loadReview(id)
    }
  }, [id])

  const loadReview = async (reviewId: string) => {
    setLoading(true)
    try {
      const data = await getReview(reviewId)
      setReview(data)
      setReviewNotes(data.reviewer_notes || '')
    } catch (error) {
      message.error('加载审核详情失败')
    } finally {
      setLoading(false)
    }
  }

  const handleApprove = async () => {
    if (!id) return

    Modal.confirm({
      title: '确认通过',
      content: (
        <div>
          <p>确定通过此政策审核吗？通过后政策将立即生效。</p>
          <TextArea
            rows={3}
            placeholder="审核备注（可选）"
            value={reviewNotes}
            onChange={(e) => setReviewNotes(e.target.value)}
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      ),
      onOk: async () => {
        setActionLoading(true)
        try {
          const result = await approveReview(id, reviewNotes)
          message.success('审核通过，政策已发布')
          navigate(`/policies/${result.policy_id}`)
        } catch (error: any) {
          message.error(error?.response?.data?.detail || '操作失败')
        } finally {
          setActionLoading(false)
        }
      },
    })
  }

  const handleReject = async () => {
    if (!id || !rejectReason.trim()) {
      message.error('请填写拒绝原因')
      return
    }
    setActionLoading(true)
    try {
      await rejectReview(id, rejectReason)
      message.success('已拒绝')
      setRejectModal(false)
      navigate('/reviews')
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '操作失败')
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!review) {
    return (
      <Card>
        <div style={{ textAlign: 'center', padding: 50 }}>
          <p>审核任务不存在</p>
          <Button onClick={() => navigate('/reviews')}>返回列表</Button>
        </div>
      </Card>
    )
  }

  const data = review.submitted_data
  const statusConfig = REVIEW_STATUS_MAP[review.status] || { label: review.status, color: 'default' }
  const typeConfig = getPolicyTypeLabel(review.policy_type || data?.policy_type)

  // 是否为待审核状态
  const isPending = review.status === 'pending' || review.status === 'claimed'

  return (
    <div className="review-detail">
      {/* 头部操作栏 */}
      <div className="detail-header">
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/reviews')}>
          返回列表
        </Button>
        <div className="header-tags">
          <Tag color={statusConfig.color}>{statusConfig.label}</Tag>
          <Tag color={typeConfig.color}>{typeConfig.label}</Tag>
          {review.submit_type === 'update' ? (
            <Tag color="blue" icon={<SyncOutlined />}>更新政策</Tag>
          ) : (
            <Tag color="green" icon={<PlusCircleOutlined />}>新建政策</Tag>
          )}
        </div>
        <div className="header-actions">
          {isPending && (
            <Space>
              <Button
                type="primary"
                icon={<CheckCircleOutlined />}
                onClick={handleApprove}
                loading={actionLoading}
              >
                通过
              </Button>
              <Button
                danger
                icon={<CloseCircleOutlined />}
                onClick={() => setRejectModal(true)}
              >
                拒绝
              </Button>
            </Space>
          )}
        </div>
      </div>

      <Row gutter={24}>
        {/* 左侧：政策内容（统一组件） */}
        <Col span={16}>
          <PolicyContentCard
            data={{
              title: data?.title,
              policy_type: review.policy_type || data?.policy_type,
              region_name: review.region_name,
              region_code: data?.region_code,
              policy_year: data?.effective_start ? new Date(data.effective_start).getFullYear() : undefined,
              published_at: data?.published_at,
              effective_start: data?.effective_start,
              effective_end: data?.effective_end,
              si_upper_limit: data?.si_upper_limit ?? data?.type_data?.si_upper_limit,
              si_lower_limit: data?.si_lower_limit ?? data?.type_data?.si_lower_limit,
              hf_upper_limit: data?.hf_upper_limit ?? data?.type_data?.hf_upper_limit,
              hf_lower_limit: data?.hf_lower_limit ?? data?.type_data?.hf_lower_limit,
              is_retroactive: data?.is_retroactive ?? data?.type_data?.is_retroactive,
              retroactive_start: data?.retroactive_start ?? data?.type_data?.retroactive_start,
              coverage_types: data?.coverage_types ?? data?.type_data?.coverage_types,
              special_notes: data?.special_notes ?? data?.type_data?.special_notes,
            }}
          />
        </Col>

        {/* 右侧：根据状态展示不同内容 */}
        <Col span={8}>
          {isPending || review.status === 'rejected' ? (
            <>
              {/* 待审核/已拒绝：提交信息 */}
              <Card title="提交信息">
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="提交人">{review.submitted_by}</Descriptions.Item>
                  <Descriptions.Item label="提交时间">{review.submitted_at}</Descriptions.Item>
                  <Descriptions.Item label="提交类型">
                    {review.submit_type === 'update' ? (
                      <Space>
                        <Tag color="blue">更新政策</Tag>
                        {review.existing_policy_id && (
                          <Button
                            type="link"
                            size="small"
                            icon={<LinkOutlined />}
                            onClick={() => navigate(`/policies/${review.existing_policy_id}`)}
                          >
                            查看原政策
                          </Button>
                        )}
                      </Space>
                    ) : (
                      <Tag color="green">新建政策</Tag>
                    )}
                  </Descriptions.Item>
                  {review.change_description && (
                    <Descriptions.Item label="修改说明">
                      {review.change_description}
                    </Descriptions.Item>
                  )}
                </Descriptions>
              </Card>

              {/* 审核信息 */}
              {review.claimed_by && (
                <Card title="审核信息" style={{ marginTop: 16 }}>
                  <Descriptions column={1} size="small">
                    <Descriptions.Item label="审核人">{review.claimed_by}</Descriptions.Item>
                    {review.claimed_at && (
                      <Descriptions.Item label="审核时间">{review.claimed_at}</Descriptions.Item>
                    )}
                  </Descriptions>
                </Card>
              )}

              {/* 审核备注 */}
              <Card title="审核备注" style={{ marginTop: 16 }}>
                <TextArea
                  rows={4}
                  placeholder="添加审核备注..."
                  value={reviewNotes}
                  onChange={(e) => setReviewNotes(e.target.value)}
                  disabled={!isPending}
                />
              </Card>

              {/* 原始证据 */}
              <div style={{ marginTop: 16 }}>
                <RawEvidenceCard evidence={review.raw_evidence} />
              </div>
            </>
          ) : (
            <>
              {/* 已通过：版本信息 */}
              <Card title="版本信息">
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="审核人">{review.claimed_by || '-'}</Descriptions.Item>
                  <Descriptions.Item label="审核时间">{review.claimed_at || review.submitted_at}</Descriptions.Item>
                  {review.policy_id && (
                    <Descriptions.Item label="政策ID">
                      <Button
                        type="link"
                        size="small"
                        onClick={() => navigate(`/policies/${review.policy_id}`)}
                      >
                        查看政策详情
                      </Button>
                    </Descriptions.Item>
                  )}
                </Descriptions>
              </Card>

              {/* 原始证据 */}
              <div style={{ marginTop: 16 }}>
                <RawEvidenceCard evidence={review.raw_evidence} />
              </div>
            </>
          )}
        </Col>
      </Row>

      {/* 拒绝弹窗 */}
      <Modal
        title="拒绝原因"
        open={rejectModal}
        onCancel={() => setRejectModal(false)}
        onOk={handleReject}
        confirmLoading={actionLoading}
      >
        <TextArea
          rows={4}
          placeholder="请说明拒绝原因，将反馈给提交者"
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
        />
      </Modal>
    </div>
  )
}
