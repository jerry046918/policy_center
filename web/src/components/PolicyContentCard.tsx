import { Card, Descriptions, Tag, Row, Col, Divider, Statistic } from 'antd'
import './PolicyContentCard.css'

interface PolicyContentData {
  // 基本信息
  title: string
  region_name?: string
  region_code: string
  policy_year?: number
  published_at?: string
  effective_start: string
  effective_end?: string
  // 社保公积金
  si_upper_limit?: number
  si_lower_limit?: number
  hf_upper_limit?: number
  hf_lower_limit?: number
  is_retroactive?: boolean
  retroactive_start?: string
  coverage_types?: string[]
  special_notes?: string
}

interface PolicyContentCardProps {
  data: PolicyContentData
}

export default function PolicyContentCard({ data }: PolicyContentCardProps) {
  const policyYear = data.effective_start ? new Date(data.effective_start).getFullYear() : '-'

  return (
    <>
      {/* 政策基本信息 */}
      <Card title="政策基本信息" className="info-card">
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="政策名称" span={2}>
            {data.title}
          </Descriptions.Item>
          <Descriptions.Item label="适用地区">
            {data.region_name || data.region_code}
          </Descriptions.Item>
          <Descriptions.Item label="政策年度">
            {data.policy_year || policyYear}年
          </Descriptions.Item>
          <Descriptions.Item label="发布日期">
            {data.published_at || '-'}
          </Descriptions.Item>
          <Descriptions.Item label="生效日期">
            {data.effective_start}
          </Descriptions.Item>
          <Descriptions.Item label="失效日期">
            {data.effective_end || '-'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 社保公积金基数 */}
      <Card title="社保公积金基数" style={{ marginTop: 16 }}>
        <Row gutter={24}>
          <Col span={12}>
            <Card className="limit-card" size="small">
              <Statistic
                title="社保基数上限"
                value={data.si_upper_limit || 0}
                prefix="¥"
                suffix="/月"
              />
              <Divider />
              <Statistic
                title="社保基数下限"
                value={data.si_lower_limit || 0}
                prefix="¥"
                suffix="/月"
              />
            </Card>
          </Col>
          <Col span={12}>
            <Card className="limit-card" size="small">
              <Statistic
                title="公积金上限"
                value={data.hf_upper_limit || 0}
                prefix="¥"
                suffix="/月"
              />
              <Divider />
              <Statistic
                title="公积金下限"
                value={data.hf_lower_limit || 0}
                prefix="¥"
                suffix="/月"
              />
            </Card>
          </Col>
        </Row>

        {/* 追溯信息 */}
        {data.is_retroactive && (
          <div className="retroactive-info" style={{ marginTop: 16 }}>
            <Tag color="orange">追溯生效</Tag>
            <span>追溯开始日期: {data.retroactive_start}</span>
          </div>
        )}

        {/* 险种覆盖 */}
        {data.coverage_types && data.coverage_types.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <span style={{ marginRight: 8 }}>覆盖险种:</span>
            {data.coverage_types.map((type) => (
              <Tag key={type}>{type}</Tag>
            ))}
          </div>
        )}

        {/* 特殊说明 */}
        {data.special_notes && (
          <div style={{ marginTop: 16 }}>
            <strong>特殊说明:</strong>
            <p
              className="special-notes-text"
              style={{
                margin: '8px 0 0',
                padding: 12,
                background: '#f5f5f5',
                borderRadius: 8,
                color: '#595959',
                whiteSpace: 'pre-wrap',
                wordWrap: 'break-word',
                lineHeight: 1.7,
                fontSize: 14,
              }}
            >
              {data.special_notes}
            </p>
          </div>
        )}
      </Card>
    </>
  )
}
