import { Card, Collapse, Empty, Tag } from 'antd'
import { FileTextOutlined, LinkOutlined } from '@ant-design/icons'
import type { SourceDocument } from '../types/policy'
import './RawEvidenceCard.css'

interface RawEvidence {
  // 新格式：多来源（审核队列使用）
  sources?: (SourceDocument & { document_type?: string })[]
  // 政策表使用的字段（JSON字符串）
  source_attachments?: string
}

interface RawEvidenceCardProps {
  evidence?: RawEvidence
  // 兼容直接传入 rawEvidence 对象
  rawEvidence?: RawEvidence
  title?: string
}

export default function RawEvidenceCard({ evidence, rawEvidence, title = "原始证据" }: RawEvidenceCardProps) {
  // 兼容两种参数名
  const data = evidence || rawEvidence

  if (!data) {
    return (
      <Card title={title} className="evidence-card">
        <Empty description="无原始证据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </Card>
    )
  }

  // 获取来源列表（兼容新旧格式）
  const getSources = (): SourceDocument[] => {
    // 新格式：sources 数组
    if (data.sources && data.sources.length > 0) {
      return data.sources
    }
    // 政策表格式：source_attachments JSON 字符串
    if (data.source_attachments) {
      try {
        const parsed = JSON.parse(data.source_attachments)
        if (Array.isArray(parsed) && parsed.length > 0) {
          return parsed
        }
      } catch (e) {
        console.error('Failed to parse source_attachments:', e)
      }
    }
    return []
  }

  const sources = getSources()

  if (sources.length === 0) {
    return (
      <Card title={title} className="evidence-card">
        <Empty description="无原始证据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </Card>
    )
  }

  // 单个来源的简洁展示
  if (sources.length === 1) {
    const source = sources[0]
    return (
      <Card title={title} className="evidence-card" style={{ marginTop: 16 }}>
        {source.doc_number && (
          <div className="evidence-field">
            <span className="evidence-label">官方文号:</span>
            <span className="evidence-value">{source.doc_number}</span>
          </div>
        )}
        <div className="evidence-field">
          <span className="evidence-label">网站链接:</span>
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="evidence-link"
          >
            <LinkOutlined style={{ marginRight: 6 }} />
            <span className="evidence-url">{source.url}</span>
          </a>
        </div>
        {source.extracted_text && (
          <div className="extracted-text-container">
            <div className="extracted-text-label">提取文字内容:</div>
            <div className="extracted-text">
              {source.extracted_text}
            </div>
          </div>
        )}
      </Card>
    )
  }

  // 多个来源的可折叠展示
  return (
    <Card title={`${title} (${sources.length}个来源)`} className="evidence-card" style={{ marginTop: 16 }}>
      <Collapse
        accordion={false}
        defaultActiveKey={sources.map((_, i) => `source-${i}`)}
        className="evidence-collapse"
        items={sources.map((source, index) => ({
          key: `source-${index}`,
          label: (
            <span className="collapse-header">
              <FileTextOutlined style={{ marginRight: 8 }} />
              {source.title || `来源 ${index + 1}`}
              {source.document_type && (
                <Tag color="blue" style={{ marginLeft: 8 }}>{source.document_type}</Tag>
              )}
            </span>
          ),
          children: (
            <div>
              {source.doc_number && (
                <div className="evidence-field">
                  <span className="evidence-label">官方文号:</span>
                  <span className="evidence-value">{source.doc_number}</span>
                </div>
              )}
              <div className="evidence-field">
                <span className="evidence-label">网站链接:</span>
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="evidence-link"
                >
                  <LinkOutlined style={{ marginRight: 6 }} />
                  <span className="evidence-url">{source.url}</span>
                </a>
              </div>
              {source.extracted_text && (
                <div className="extracted-text-container">
                  <div className="extracted-text-label">提取文字内容:</div>
                  <div className="extracted-text">
                    {source.extracted_text}
                  </div>
                </div>
              )}
            </div>
          )
        }))}
      />
    </Card>
  )
}
