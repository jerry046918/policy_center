**政策中心系统技术规格说明书 (Technical Specification)**
**版本**: v2.0
**日期**: 2026-03-13
**状态**: 评审中
**目标读者**: 开发团队、架构师、产品经理

**变更记录**:
- v2.0: 简化为极简部署模式（单容器），移除 Redis/MinIO/Celery
- v1.2: 切换到 SQLite 轻量化数据库
- v1.1: 增加 MCP认证、幂等性设计  

---

## 1. 项目概述

### 1.1 项目背景
构建面向**社保公积金基数政策**的**MCP-First数据基础设施平台**。平台通过**Model Context Protocol (MCP)**向外部Agent开放核心能力，同时提供完善的Web端进行人工审核、政策管理和数据运营。

### 1.2 核心目标
- **开放生态**: 任何采集Agent（Python爬虫、Claude Desktop、n8n等）可通过MCP标准接口提交政策数据
- **精准管理**: 专门针对社保基数上下限、追溯缴纳等强业务逻辑设计数据模型
- **人机协同**: AI辅助自动校验 + 人工审核确认，确保数据准确性
- **全生命周期**: 覆盖采集→审核→发布→版本管理→查询→归档全流程

### 1.3 业务范围（MVP）
**政策类型**: 社保公积金基数调整政策  
**覆盖范围**: 全国31个省级行政区 + 计划单列市（深圳、大连等）  
**核心数据**: 缴费基数上下限、生效时间、追溯标记、险种覆盖范围  

---

## 2. 系统架构

### 2.1 总体架构
```
┌─────────────────────────────────────────────────────────────┐
│                    外部Agent生态层                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │Python爬虫 │  │Claude桌面│  │  n8n     │  │ 其他SaaS │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
└───────┼─────────────┼─────────────┼─────────────┼────────┘
        │             │             │             │
        └─────────────┴──────┬──────┴─────────────┘
                             │
                    ┌────────▼────────┐
                    │   单容器服务     │
                    │  ┌───────────┐  │
                    │  │ MCP Server│  │  ← 标准协议接口
                    │  ├───────────┤  │
                    │  │ FastAPI   │  │  ← REST API
                    │  ├───────────┤  │
                    │  │ 静态前端  │  │  ← Web界面
                    │  └───────────┘  │
                    └────────┬────────┘
                             │
┌────────────────────────────▼───────────────────────────────┐
│                     数据存储（本地）                         │
│  ┌──────────────┐  ┌────────────────────────────────────┐ │
│  │   SQLite     │  │         本地文件系统                │ │
│  │ policy.db    │  │    ./uploads/ (PDF/图片)           │ │
│  └──────────────┘  └────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

### 2.2 技术栈选型

| 层级 | 技术 | 版本 | 说明 |
|------|------|------|------|
| **协议层** | MCP (Model Context Protocol) | 2025-03 Spec | Anthropic开放标准，Agent生态兼容 |
| **MCP框架** | FastMCP | Python 3.11+ | 原生MCP Tool定义支持 |
| **API框架** | FastAPI | 0.100+ | 高性能异步，自动生成OpenAPI文档 |
| **ORM** | SQLAlchemy | 2.0+ | 异步支持，防止SQL注入 |
| **数据库** | SQLite | 3.40+ | 单文件数据库，零配置，WAL模式 |
| **缓存** | cachetools | 5.x | Python 内存缓存 |
| **定时任务** | APScheduler | 3.x | 内嵌到 FastAPI |
| **文件存储** | 本地文件系统 | - | ./uploads/ 目录 |
| **前端** | React + Ant Design Pro | 18.x + 5.x | 预构建后由 FastAPI 托管 |
| **部署** | Docker | - | 单容器部署 |

### 2.3 SQLite 设计说明

**选型理由**:
- 政策数据写入频率低（按月/季度更新），SQLite 完全胜任
- 部署简单，零配置，单文件便于备份和迁移
- 读取性能优秀，完全满足查询需求
- 支持 JSON、全文搜索（FTS5）

**关键适配**:
| PostgreSQL 特性 | SQLite 替代方案 |
|----------------|-----------------|
| JSONB | TEXT + JSON 函数 |
| UUID | TEXT（应用层生成） |
| VECTOR | TEXT（JSON 数组）或外部向量库 |
| ltree | 物化路径 TEXT 字段 |
| GENERATED COLUMN | 应用层计算 |
| 复杂触发器 | 应用层逻辑 |

**并发说明**:
- SQLite 使用 WAL 模式支持并发读
- 写操作通过应用层队列串行化，避免锁冲突
- 对于高并发场景，可切换到 PostgreSQL（无需修改应用代码）

**启用 WAL 模式**:
```python
# 数据库初始化时
async with engine.begin() as conn:
    await conn.execute(text("PRAGMA journal_mode=WAL"))
    await conn.execute(text("PRAGMA synchronous=NORMAL"))
    await conn.execute(text("PRAGMA cache_size=-64000"))  # 64MB cache
```

### 2.3 服务健康检查

所有服务需暴露标准健康检查端点：

```
GET /health      # 服务存活检查（仅检查进程）
GET /ready       # 服务就绪检查（检查DB/Redis连接）
```

Docker Compose 配置示例：
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

---

## 3. 数据模型设计

### 3.1 核心实体关系
- **regions**: 地区字典（国标GB/T 2260）
- **policies**: 政策主表（通用字段）
- **policy_social_insurance**: 社保扩展表（1:1关系）
- **review_queue**: 审核队列表（临时状态）
- **policy_versions**: 版本历史表（变更追踪）
- **audit_logs**: 操作审计表（全量记录）
- **agent_credentials**: Agent认证凭据表（新增）

### 3.2 详细表结构

#### 3.2.1 地区字典 (regions)
```sql
CREATE TABLE regions (
    code TEXT PRIMARY KEY,                    -- 六位行政区划码，如110000
    name TEXT NOT NULL,                       -- 地区名称，如"北京市"
    level TEXT NOT NULL CHECK (level IN ('country', 'province', 'city', 'district')),
    parent_code TEXT REFERENCES regions(code),
    full_path TEXT,                           -- 完整路径，如"中国/北京市"
    path_materialized TEXT,                   -- 物化路径，如"000000.110000"，支持层级查询
    is_active INTEGER DEFAULT 1,

    -- 元数据
    min_wage INTEGER,                         -- 当地最低工资标准（元/月），用于基数校验
    avg_salary INTEGER,                       -- 上年度社平工资（用于基数合理性校验）
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 索引
CREATE INDEX idx_regions_parent ON regions(parent_code);
CREATE INDEX idx_regions_path ON regions(path_materialized);

-- 初始化数据示例
INSERT INTO regions (code, name, level, parent_code, full_path, path_materialized) VALUES
('000000', '中国', 'country', NULL, '中国', '000000'),
('110000', '北京市', 'province', '000000', '中国/北京市', '000000.110000'),
('310000', '上海市', 'province', '000000', '中国/上海市', '000000.310000'),
('440000', '广东省', 'province', '000000', '中国/广东省', '000000.440000'),
('440300', '深圳市', 'city', '440000', '中国/广东省/深圳市', '000000.440000.440300');
```

#### 3.2.2 政策主表 (policies)
```sql
CREATE TABLE policies (
    policy_id TEXT PRIMARY KEY,               -- UUID，由应用层生成
    policy_type TEXT NOT NULL DEFAULT 'social_insurance_base',

    -- 基础信息
    title TEXT NOT NULL,                      -- 政策名称
    doc_number TEXT,                          -- 文号，如"京人社发〔2024〕12号"
    region_code TEXT NOT NULL REFERENCES regions(code),

    -- 来源信息
    source_url TEXT NOT NULL,                 -- 原始公告链接
    source_attachments TEXT DEFAULT '[]',     -- 附件列表 JSON [{name, url, type}]

    -- 时间维度（核心业务字段）
    published_at TEXT NOT NULL,               -- 发布时间（落款日期）YYYY-MM-DD
    effective_start TEXT NOT NULL,            -- 生效开始日期
    effective_end TEXT,                       -- 生效结束日期（NULL表示现行有效）
    policy_year INTEGER,                      -- 政策年度（应用层计算）

    -- 状态管理
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'pending_review', 'active', 'expired', 'revoked')),
    version INTEGER DEFAULT 1,

    -- 原始内容
    raw_content TEXT,                         -- 原始HTML或OCR文本
    raw_snapshot_url TEXT,                    -- 网页快照存储路径

    -- 向量嵌入（可选，用于语义搜索，存储为JSON数组）
    embedding TEXT,                           -- JSON数组格式 [0.1, 0.2, ...]

    -- 审计字段
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    created_by TEXT,                          -- Agent标识或用户ID
    reviewed_by TEXT,
    reviewed_at TEXT,

    -- 软删除
    deleted_at TEXT,
    deleted_by TEXT,

    -- 幂等性：同一文号唯一
    UNIQUE (doc_number)
);

-- 关键索引
CREATE INDEX idx_policies_region_effective ON policies(region_code, effective_start DESC);
CREATE INDEX idx_policies_status ON policies(status);
CREATE INDEX idx_policies_year ON policies(policy_year);

-- 全文搜索索引（FTS5）
CREATE VIRTUAL TABLE policies_fts USING fts5(
    title,
    doc_number,
    raw_content,
    content='policies',
    content_rowid='rowid'
);

-- 触发器：自动更新 updated_at
CREATE TRIGGER policies_update_timestamp
    AFTER UPDATE ON policies
    FOR EACH ROW
BEGIN
    UPDATE policies SET updated_at = datetime('now') WHERE policy_id = NEW.policy_id;
END;

-- 触发器：同步全文搜索索引
CREATE TRIGGER policies_ai AFTER INSERT ON policies BEGIN
    INSERT INTO policies_fts(rowid, title, doc_number, raw_content)
    VALUES (NEW.rowid, NEW.title, NEW.doc_number, NEW.raw_content);
END;

CREATE TRIGGER policies_ad AFTER DELETE ON policies BEGIN
    INSERT INTO policies_fts(policies_fts, rowid, title, doc_number, raw_content)
    VALUES('delete', OLD.rowid, OLD.title, OLD.doc_number, OLD.raw_content);
END;

CREATE TRIGGER policies_au AFTER UPDATE ON policies BEGIN
    INSERT INTO policies_fts(policies_fts, rowid, title, doc_number, raw_content)
    VALUES('delete', OLD.rowid, OLD.title, OLD.doc_number, OLD.raw_content);
    INSERT INTO policies_fts(rowid, title, doc_number, raw_content)
    VALUES (NEW.rowid, NEW.title, NEW.doc_number, NEW.raw_content);
END;
```

#### 3.2.3 社保公积金扩展表 (policy_social_insurance)
```sql
CREATE TABLE policy_social_insurance (
    policy_id TEXT PRIMARY KEY REFERENCES policies(policy_id) ON DELETE CASCADE,

    -- 社保基数（元/月）
    si_upper_limit INTEGER CHECK (si_upper_limit > 0),      -- 上限
    si_lower_limit INTEGER CHECK (si_lower_limit > 0),      -- 下限
    si_avg_salary_ref INTEGER,                              -- 参考社平工资

    -- 公积金基数（元/月）
    hf_upper_limit INTEGER CHECK (hf_upper_limit > 0),
    hf_lower_limit INTEGER CHECK (hf_lower_limit > 0),

    -- 追溯逻辑（核心业务）
    is_retroactive INTEGER DEFAULT 0,                       -- 是否追溯生效 (0=false, 1=true)
    retroactive_start TEXT,                                 -- 追溯开始日期
    retroactive_months INTEGER,                             -- 追溯月数（应用层计算）

    -- 险种覆盖
    coverage_types TEXT DEFAULT '["养老", "医疗", "失业", "工伤", "生育"]',  -- JSON数组

    -- 变更统计（应用层计算）
    prev_si_upper INTEGER,                                  -- 上年度上限
    prev_si_lower INTEGER,
    change_rate_upper REAL,                                 -- 涨幅百分比
    change_rate_lower REAL,

    -- 特殊说明
    special_notes TEXT,

    -- 约束：上限必须大于下限
    CHECK (si_upper_limit IS NULL OR si_lower_limit IS NULL OR si_upper_limit > si_lower_limit),
    CHECK (hf_upper_limit IS NULL OR hf_lower_limit IS NULL OR hf_upper_limit > hf_lower_limit)
);

-- 涨幅计算由应用层处理（SQLite不支持复杂触发器）
-- 伪代码：
-- def calculate_change_rate(policy):
--     prev = get_previous_policy(policy.region_code, policy.effective_start)
--     if prev:
--         policy.change_rate_upper = round((policy.si_upper_limit - prev.si_upper_limit) / prev.si_upper_limit * 100, 2)
--         policy.change_rate_lower = round((policy.si_lower_limit - prev.si_lower_limit) / prev.si_lower_limit * 100, 2)
```

#### 3.2.4 审核队列表 (review_queue)
```sql
CREATE TABLE review_queue (
    review_id TEXT PRIMARY KEY,                              -- UUID，应用层生成
    policy_id TEXT REFERENCES policies(policy_id),           -- 预创建的政策ID

    -- 幂等性字段
    idempotency_key TEXT UNIQUE,                             -- 幂等键（Agent生成，防止重复提交）

    submitted_data TEXT NOT NULL,                            -- 完整提交数据 JSON
    raw_evidence TEXT,                                       -- 证据材料 JSON

    -- AI辅助分析结果
    ai_validation TEXT,                                      -- 自动校验结果 JSON
    duplicate_check TEXT,                                    -- 重复检测信息 JSON
    risk_level TEXT DEFAULT 'low' CHECK (risk_level IN ('low', 'medium', 'high')),
    risk_tags TEXT DEFAULT '[]',                             -- 风险标签 JSON：["追溯", "涨幅异常", "重复"]

    -- 审核流程
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'claimed', 'approved', 'rejected', 'needs_clarification')),
    priority TEXT DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high', 'urgent')),

    -- 任务分配
    claimed_by TEXT,                                         -- 认领人
    claimed_at TEXT,

    -- 操作记录
    reviewer_notes TEXT,
    reviewer_id TEXT,
    reviewed_at TEXT,
    submitted_at TEXT DEFAULT (datetime('now')),
    submitted_by TEXT NOT NULL,                              -- Agent标识（对应agent_credentials.agent_id）

    -- 处理时限（应用层计算）
    sla_deadline TEXT                                        -- 预期处理截止时间
);

-- 索引
CREATE INDEX idx_review_pending ON review_queue(status, priority, submitted_at);
CREATE INDEX idx_review_idempotency ON review_queue(idempotency_key);
CREATE INDEX idx_review_submitted_by ON review_queue(submitted_by, submitted_at DESC);
```

#### 3.2.5 版本历史表 (policy_versions)
```sql
CREATE TABLE policy_versions (
    version_id TEXT PRIMARY KEY,                             -- UUID，应用层生成
    policy_id TEXT REFERENCES policies(policy_id),
    version_number INTEGER NOT NULL,
    change_type TEXT CHECK (change_type IN ('create', 'update', 'rollback', 'correction', 'expire')),
    changed_fields TEXT,                                     -- 变更字段列表 JSON
    old_values TEXT,                                         -- 敏感字段加密存储 JSON
    new_values TEXT,
    change_reason TEXT,
    changed_by TEXT,
    changed_at TEXT DEFAULT (datetime('now')),

    -- 快照：完整版本数据（用于回滚）
    snapshot TEXT NOT NULL,                                  -- 完整的政策+扩展数据快照 JSON

    UNIQUE(policy_id, version_number)
);

CREATE INDEX idx_policy_versions ON policy_versions(policy_id, version_number DESC);
```

#### 3.2.6 操作审计表 (audit_logs)
```sql
CREATE TABLE audit_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id TEXT,
    action TEXT NOT NULL,                                    -- CREATE, UPDATE, DELETE, APPROVE, REJECT, ROLLBACK
    field_name TEXT,
    old_value TEXT,                                          -- 敏感值加密
    new_value TEXT,                                          -- 敏感值加密
    operator_id TEXT NOT NULL,
    operator_type TEXT DEFAULT 'user' CHECK (operator_type IN ('user', 'agent', 'system')),
    operator_role TEXT,                                      -- staff/admin
    ip_address TEXT,
    user_agent TEXT,
    request_id TEXT,                                         -- 请求追踪ID
    operated_at TEXT DEFAULT (datetime('now'))
);

-- 索引：按政策和时间查询
CREATE INDEX idx_audit_policy ON audit_logs(policy_id, operated_at DESC);
CREATE INDEX idx_audit_operator ON audit_logs(operator_id, operated_at DESC);
CREATE INDEX idx_audit_action ON audit_logs(action, operated_at DESC);
```

#### 3.2.7 Agent认证凭据表 (agent_credentials)
```sql
CREATE TABLE agent_credentials (
    agent_id TEXT PRIMARY KEY,                               -- Agent唯一标识
    agent_name TEXT NOT NULL,                                -- Agent名称
    api_key_hash TEXT NOT NULL,                              -- API Key 的 SHA256 哈希
    api_key_prefix TEXT NOT NULL,                            -- API Key 前缀（用于识别，如 "pk_xxxx"）
    description TEXT,
    permissions TEXT DEFAULT '["submit"]',                   -- 权限 JSON：submit, query
    rate_limit INTEGER DEFAULT 60,                           -- 每分钟请求限制
    is_active INTEGER DEFAULT 1,                             -- 是否启用 (0=false, 1=true)
    last_used_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT,                                         -- 过期时间（可选）
    created_by TEXT                                          -- 创建人
);

CREATE INDEX idx_agent_credentials_prefix ON agent_credentials(api_key_prefix);
```

---

## 4. MCP接口规范（Agent接入层）

### 4.1 Agent认证机制

所有 MCP 调用需要在请求头中携带认证信息：

```
Authorization: Bearer <api_key>
X-Agent-ID: <agent_id>
X-Idempotency-Key: <unique_request_key>  # 可选，用于幂等性
```

**API Key 格式**: `pk_live_xxxxxxxxxxxxxxxxxxxxxxxx` (前缀 + 32位随机字符)

### 4.2 MCP Server配置
```json
{
  "mcpServers": {
    "policy_center": {
      "command": "python",
      "args": ["-m", "policy_center.mcp_server"],
      "env": {
        "DATABASE_URL": "postgresql://...",
        "REDIS_URL": "redis://...",
        "MCP_API_KEY": "pk_live_xxx"
      }
    }
  }
}
```

### 4.3 Tool 1: submit_policy_for_review
**用途**: 提交新政策或更新到人工审核队列
**幂等性**: 通过 `idempotency_key` 保证，相同key返回已有结果
**输入Schema**:
```json
{
  "type": "object",
  "required": ["policy_type", "structured_data", "raw_content"],
  "properties": {
    "idempotency_key": {
      "type": "string",
      "description": "幂等键（建议使用 doc_number 的 hash），防止重复提交"
    },
    "policy_type": {
      "type": "string",
      "enum": ["social_insurance_base"],
      "description": "政策类型标识"
    },
    "structured_data": {
      "type": "object",
      "required": ["title", "region_code", "published_at", "effective_start", "si_upper_limit", "si_lower_limit"],
      "properties": {
        "title": {"type": "string", "maxLength": 500, "description": "政策完整名称"},
        "doc_number": {"type": "string", "description": "官方文号（用于幂等性校验）"},
        "region_code": {"type": "string", "pattern": "^[0-9]{6}$", "description": "六位行政区划码"},
        "published_at": {"type": "string", "format": "date"},
        "effective_start": {"type": "string", "format": "date"},
        "effective_end": {"type": "string", "format": "date"},
        "si_upper_limit": {"type": "integer", "minimum": 1000, "description": "社保上限（元/月）"},
        "si_lower_limit": {"type": "integer", "minimum": 1000, "description": "社保下限（元/月）"},
        "hf_upper_limit": {"type": "integer", "minimum": 0, "description": "公积金上限（元/月），可选"},
        "hf_lower_limit": {"type": "integer", "minimum": 0, "description": "公积金下限（元/月），可选"},
        "is_retroactive": {"type": "boolean", "default": false, "description": "是否追溯生效"},
        "retroactive_start": {"type": "string", "format": "date", "description": "追溯开始日期（is_retroactive=true时必填）"},
        "coverage_types": {"type": "array", "default": ["养老", "医疗", "失业", "工伤", "生育"], "items": {"enum": ["养老", "医疗", "失业", "工伤", "生育", "公积金"]}},
        "special_notes": {"type": "string", "maxLength": 1000, "description": "特殊说明"}
      }
    },
    "raw_content": {
      "type": "object",
      "required": ["source_url"],
      "properties": {
        "source_url": {"type": "string", "format": "uri"},
        "extracted_text": {"type": "string", "description": "OCR或爬取的原始文本"},
        "source_document_base64": {"type": "string", "description": "PDF或图片的base64编码"}
      }
    },
    "priority": {
      "type": "string",
      "enum": ["low", "normal", "high", "urgent"],
      "default": "normal",
      "description": "审核优先级"
    }
  }
}
```

**输出**:
```json
{
  "review_id": "rev_550e8400-e29b-41d4-a716-446655440000",
  "status": "pending_review",
  "policy_id": "550e8400-e29b-41d4-a716-446655440001",
  "warnings": ["生效日期(2024-01-01)早于发布日期(2024-06-20)，涉及追溯缴纳"],
  "ai_analysis": {
    "is_duplicate": false,
    "change_rate": 6.3,
    "retroactive_months": 5,
    "risk_level": "medium"
  },
  "estimated_review_time": "24h"
}
```

### 4.4 Tool 2: get_policy_schema
**用途**: 查询指定政策类型的Schema定义
**输入**: `{"policy_type": "social_insurance_base", "include_examples": true}`
**输出**: 完整的JSON Schema（含字段定义、验证规则、示例数据）

### 4.5 Tool 3: query_policies
**用途**: 查询已发布政策（用于去重或获取历史数据）
**输入**:
```json
{
  "filters": {
    "region_code": "110000",
    "effective_year": 2024,
    "is_retroactive": true,
    "status": "active"
  },
  "semantic_query": "北京2024年社保基数上限",
  "limit": 10,
  "offset": 0
}
```
**输出**: 政策列表（含匹配度分数）

### 4.6 Tool 4: get_my_submissions (新增)
**用途**: Agent查询自己提交的审核状态
**输入**:
```json
{
  "status": "pending",  // 可选：pending/approved/rejected/all
  "limit": 20,
  "offset": 0
}
```
**输出**:
```json
{
  "submissions": [
    {
      "review_id": "rev_xxx",
      "policy_title": "2024年北京市社保基数调整通知",
      "status": "pending",
      "submitted_at": "2024-06-15T10:30:00Z",
      "sla_deadline": "2024-06-16T10:30:00Z",
      "risk_level": "medium",
      "risk_tags": ["追溯"]
    }
  ],
  "total": 5,
  "pending_count": 2
}
```

### 4.7 Tool 5: check_duplicate (新增)
**用途**: 提交前检查是否重复（避免无效提交）
**输入**:
```json
{
  "doc_number": "京人社发〔2024〕12号",
  "region_code": "110000",
  "effective_start": "2024-07-01"
}
```
**输出**:
```json
{
  "is_duplicate": false,
  "existing_policy_id": null,
  "existing_review_id": null,
  "similarity_score": 0.0
}
```

### 4.8 Resource: policy_changes (新增)
**用途**: MCP Resource - 订阅政策变更通知
```json
{
  "uri": "policy://changes/{region_code}",
  "description": "订阅指定地区的政策变更事件",
  "mimeType": "application/json"
}
```
**事件格式**:
```json
{
  "event_type": "policy_published",
  "policy_id": "550e8400-...",
  "region_code": "110000",
  "title": "2024年北京市社保基数调整通知",
  "effective_start": "2024-07-01",
  "timestamp": "2024-06-20T15:30:00Z"
}
```

---

## 5. Web平台功能（前端）

### 5.1 页面结构
```
Dashboard (数据看板)
├── 覆盖度统计（31省完成率热力图）
├── 待审核提醒（含SLA倒计时）
├── 近期追溯政策预警
└── 数据趋势图（近5年基数变化）

Policy Management (政策管理)
├── Policy List (政策列表)
│   ├── 高级筛选（地区/时间/状态/追溯标记）
│   ├── 表格视图/卡片视图
│   └── 批量导出/批量导入
├── Policy Detail (政策详情)
│   ├── 元信息编辑（文号、时间、来源）
│   ├── 基数编辑（上下限、公积金）
│   ├── 追溯设置（开关、开始日期）
│   └── 原文预览（PDF/网页快照）
├── Policy Timeline (政策时间线) - 新增
│   └── 某地区历年基数变化趋势图
└── Version History (版本历史)
    ├── 时间轴视图
    ├── 版本对比（Diff）
    └── 回滚操作

Review Center (审核中心)
├── Review Board (审核看板)
│   ├── 待审核列（含SLA倒计时）
│   ├── 处理中列
│   └── 已处理列
├── Review Detail (审核详情)
│   ├── AI风险提示
│   ├── 新旧版本对比（Diff Viewer）
│   ├── 原始证据查看（PDF预览）
│   └── 通过/拒绝/退回操作
└── My Submissions (我的提交) - 新增
    └── Agent提交记录追踪

Data Analysis (数据分析) - 新增
├── Coverage Report (覆盖度报告)
├── Trend Analysis (趋势分析)
├── Region Comparison (地区对比)
└── Retroactive Report (追溯统计)

System Admin (系统管理)
├── User Management (用户管理)
├── Agent Management (Agent管理) - 新增
│   ├── API Key 生成/撤销
│   ├── 权限配置
│   └── 调用统计
└── System Config (系统配置)
```

### 5.2 核心功能组件

#### 5.2.1 政策列表页
- **筛选器**: 地区级联选择（省市区）、时间范围选择器、状态标签、追溯开关
- **表格列**: 标题、地区、社保上下限、公积金上下限、生效日期、状态、操作
- **批量操作**: 批量导出Excel、批量审核（需确认）
- **批量导入**: Excel模板导入（新增）

#### 5.2.2 政策编辑页（三栏布局）
```jsx
// 左侧：元信息
<MetaCard 
  fields={[
    {label: "政策文号", key: "doc_number", editable: true},
    {label: "发布机关", key: "issuing_authority", editable: true},
    {label: "发布时间", key: "published_at", type: "date"},
    {label: "生效时间", key: "effective_start", type: "date"},
    {label: "数据来源", key: "source_url", type: "link"}
  ]}
/>

// 中间：核心业务数据
<BaseLimitEditor 
  title="社保基数"
  upper={si_upper_limit}
  lower={si_lower_limit}
  onChange={handleChange}
  validation={{upperGreaterThanLower: true}}
/>
<BaseLimitEditor title="公积金基数" ... />
<RetroactiveSwitch 
  checked={is_retroactive}
  startDate={retroactive_start}
  months={retroactive_months}
  onChange={handleRetroactiveChange}
/>
<CoverageTypeSelector value={coverage_types} />

// 右侧：辅助信息
<VersionTimeline policyId={id} />
<AuditLogMiniList policyId={id} />
```

#### 5.2.3 审核中心
- **Diff Viewer**: 左右对比视图，红色删除、绿色新增，数值变化显示百分比
- **追溯预警**: 红色高亮显示"涉及X个月追溯缴纳"
- **证据查看**: 嵌入式PDF预览、网页快照iframe
- **快捷操作**: 一键通过（带确认弹窗）、填写拒绝原因、标记需补充材料

#### 5.2.4 版本管理
- **时间轴**: 横向展示各版本发布时间、操作人、变更摘要
- **对比功能**: 选择任意两个版本进行字段级Diff
- **回滚**: 管理员可将当前政策回滚到任意历史版本（产生新版本记录）

---

## 6. REST API规范（Web与外部系统）

### 6.1 认证方式
- **JWT Token**: 登录后获取，有效期8小时，刷新Token有效期7天
- **Header**: `Authorization: Bearer <token>`
- **请求追踪**: 每个请求携带 `X-Request-ID` 用于日志追踪

### 6.2 统一响应格式
```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "request_id": "req_xxx",
    "timestamp": "2024-06-20T15:30:00Z"
  }
}
```

**错误响应格式**:
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "社保上限必须大于下限",
    "details": {
      "field": "si_upper_limit",
      "constraint": "gt:si_lower_limit"
    }
  },
  "meta": {
    "request_id": "req_xxx",
    "timestamp": "2024-06-20T15:30:00Z"
  }
}
```

### 6.3 错误码表

| 错误码 | HTTP状态码 | 说明 |
|--------|-----------|------|
| VALIDATION_ERROR | 400 | 请求参数校验失败 |
| AUTHENTICATION_ERROR | 401 | 认证失败 |
| AUTHORIZATION_ERROR | 403 | 权限不足 |
| NOT_FOUND | 404 | 资源不存在 |
| CONFLICT | 409 | 资源冲突（如重复提交） |
| RATE_LIMIT_EXCEEDED | 429 | 请求频率超限 |
| INTERNAL_ERROR | 500 | 服务器内部错误 |

### 6.4 核心端点

#### 政策管理
```
GET    /api/v1/policies              # 列表查询（支持filters、分页、排序）
GET    /api/v1/policies/:id          # 详情查看
POST   /api/v1/policies              # 人工创建（直接入库为draft）
PUT    /api/v1/policies/:id          # 全量更新
PATCH  /api/v1/policies/:id          # 部分更新（如仅修改备注）
DELETE /api/v1/policies/:id          # 软删除（记录deleted_at）
POST   /api/v1/policies/import       # 批量导入（新增）
GET    /api/v1/policies/export       # 批量导出
```

#### 版本管理
```
GET    /api/v1/policies/:id/versions              # 获取版本历史
GET    /api/v1/policies/:id/versions/:version     # 特定版本详情
POST   /api/v1/policies/:id/rollback              # 回滚到指定版本
GET    /api/v1/policies/:id/compare?from=v1&to=v2 # 版本对比
```

#### 审核流程
```
GET    /api/v1/reviews                # 审核列表（看板数据）
GET    /api/v1/reviews/:id            # 审核详情
POST   /api/v1/reviews/:id/claim      # 认领审核任务
POST   /api/v1/reviews/:id/release    # 释放审核任务（新增）
POST   /api/v1/reviews/:id/approve    # 通过审核（body含发布选项）
POST   /api/v1/reviews/:id/reject     # 拒绝（body含原因）
POST   /api/v1/reviews/:id/clarify    # 退回补充材料（新增）
```

#### Agent管理（管理员）
```
GET    /api/v1/admin/agents           # Agent列表
POST   /api/v1/admin/agents           # 创建Agent凭据
DELETE /api/v1/admin/agents/:id       # 撤销Agent凭据
GET    /api/v1/admin/agents/:id/stats # Agent调用统计
```

#### 数据分析
```
GET    /api/v1/analytics/coverage     # 地区覆盖度统计
GET    /api/v1/analytics/trends       # 趋势分析（近5年）
POST   /api/v1/analytics/compare      # 多地区对比
GET    /api/v1/analytics/retroactive  # 追溯政策统计
GET    /api/v1/analytics/dashboard    # Dashboard汇总数据
```

#### 外部HR系统对接
```
GET    /api/v1/public/si-base         # 标准查询接口（简化版）
       ?region_code=110000&date=2024-07-01

POST   /api/v1/webhooks/subscribe     # 订阅政策变更通知
DELETE /api/v1/webhooks/:id           # 取消订阅
POST   /api/v1/webhooks/:id/test      # 测试Webhook（新增）
```

#### 健康检查
```
GET    /health                        # 存活检查
GET    /ready                         # 就绪检查（含DB/Redis连接）
```
```

---

## 7. 业务流程

### 7.1 标准业务流程（Agent提交 → 人工审核 → 发布）

```
[Agent采集数据]
    ↓
[MCP: check_duplicate] (可选，提前检测重复)
    ↓
[MCP: submit_policy_for_review]
    │
    ├─ 幂等性检查（idempotency_key / doc_number）
    │   └─ 已存在 → 返回已有 review_id，跳过后续
    │
    ├─ Agent认证（API Key校验）
    │   └─ 失败 → 401 错误
    │
    └─ 进入数据校验
    ↓
[系统自动校验（异步任务）]
    ├─ 数值逻辑检查（上限>下限？）
    ├─ 重复检测（同地区同年份已存在？）
    ├─ 追溯逻辑检查（生效<发布？）
    ├─ 涨幅异常检查（>20%？）
    └─ 基数合理性检查（下限≥最低工资？上限≤社平3倍？）
    ↓
[写入review_queue]
    ├─ 状态: pending
    ├─ 风险等级计算（low/medium/high）
    ├─ SLA截止时间设置
    └─ 触发通知（可选：Slack/邮件）
    ↓
[Web审核台展示]
    ├─ AI风险标签（追溯/涨幅异常/重复）
    ├─ Diff对比（如是更新）
    └─ 原始证据查看（PDF预览）
    ↓
[人工审核操作]
    ├─ 通过 → 数据同步到policies表，状态active
    │         → 触发Webhook推送（Celery异步）
    │         → 更新向量索引
    ├─ 拒绝 → 状态改为rejected
    │         → 通知Agent（可选）
    └─ 需补充 → 状态改为needs_clarification
    ↓
[后续处理（Celery异步）]
    ├─ Webhook推送给订阅的HR系统
    ├─ 更新Dashboard统计数据
    └─ 生成向量嵌入（用于语义搜索）
```

### 7.2 人工编辑流程（修正已发布政策）

```
[用户在Web端编辑已发布政策]
    ↓
[系统创建新版本草稿（status=draft）]
    ↓
[修改核心字段（如基数数值）]
    ↓
[强制要求填写修改原因]
    ↓
[提交审核（进入review_queue）]
    ↓
[另一用户审核（或自审，根据配置）]
    ↓
[审核通过后覆盖原政策，version+1]
    ↓
[记录版本历史（含完整快照），保留旧版本]
    ↓
[触发Webhook通知]
```

### 7.3 版本回滚流程

```
[管理员进入版本历史页]
    ↓
[选择目标历史版本]
    ↓
[查看该版本与当前差异（Diff）]
    ↓
[确认回滚]
    ↓
[创建新版本（基于历史快照，标记为rollback）]
    ↓
[更新主表数据]
    ↓
[记录审计日志]
    ↓
[触发Webhook通知]
```

### 7.4 政策自动过期流程（新增）

```
[定时任务：每日凌晨执行]
    ↓
[查询 effective_end <= 今天 且 status='active' 的政策]
    ↓
[批量更新 status 为 'expired']
    ↓
[记录版本历史（change_type='expire'）]
    ↓
[触发过期通知Webhook]
```

---

## 8. 权限与安全

### 8.1 角色定义

| 角色 | 权限范围 | 代表用户 |
|------|---------|---------|
| **Agent** | 通过MCP提交政策、查询政策（仅限自己的提交） | 外部采集程序 |
| **普通用户** (Staff) | 政策全生命周期管理（查看、编辑、审核、导出）+ 个人设置 | 业务人员、审核员 |
| **系统管理员** (Admin) | 普通用户权限 + 用户管理 + Agent管理 + 系统配置 | 技术负责人、主管 |

### 8.2 权限矩阵

| 功能 | Agent | 普通用户 | 管理员 |
|------|-------|---------|--------|
| 提交政策（MCP） | ✅ | - | - |
| 查看自己的提交 | ✅ | - | - |
| 查看所有政策 | - | ✅ | ✅ |
| 编辑政策 | - | ✅ | ✅ |
| 审核操作 | - | ✅ | ✅ |
| 版本回滚 | - | ✅ | ✅ |
| 导出数据 | - | ✅ | ✅ |
| **用户管理** | - | ❌ | ✅ |
| **Agent管理（API Key）** | - | ❌ | ✅ |
| **系统配置** | - | ❌ | ✅ |
| **数据备份/恢复** | - | ❌ | ✅ |

### 8.3 安全措施

#### 8.3.1 Agent认证
- **API Key**: SHA256哈希存储，仅展示一次明文
- **权限隔离**: Agent只能查看和管理自己的提交
- **速率限制**: 可配置（默认60次/分钟）

#### 8.3.2 数据安全
1. **操作审计**: 所有修改操作（无论角色）均记录audit_logs，包含IP、UserAgent、变更前后值、request_id
2. **敏感数据加密**: audit_logs中的敏感字段（如基数变更）使用AES加密存储
3. **关键操作确认**:
   - 删除政策：二次确认弹窗
   - 修改已发布基数：强制填写修改原因
   - 版本回滚：确认差异后执行
4. **数据访问**:
   - 原始PDF下载链接带有时效签名（15分钟有效）
   - API限流：Web用户100次/分钟，Agent按配置
5. **传输安全**: 全站HTTPS，敏感字段（如MinIO密钥）环境变量注入

#### 8.3.3 SQL注入防护
- 强制使用 SQLAlchemy ORM
- 禁止字符串拼接SQL
- 所有用户输入通过参数化查询

---

## 9. 部署与运维

### 9.1 环境变量配置
```env
# .env

# 数据库 - SQLite 单文件
DATABASE_URL=sqlite+aiosqlite:///./data/policy_center.db

# 安全 - 必须修改
JWT_SECRET_KEY=your-super-secret-key-at-least-32-chars

# 存储 - 本地文件系统
STORAGE_TYPE=local
STORAGE_PATH=/app/uploads

# MCP服务
MCP_SERVER_NAME=policy_center
MCP_LOG_LEVEL=INFO

# 可选：AI 语义搜索
# OPENAI_API_KEY=sk-xxx
# EMBEDDING_MODEL=text-embedding-3-small
```

### 9.2 Docker Compose

```yaml
# docker-compose.yml
version: '3.8'
services:
  policy-center:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=sqlite+aiosqlite:///./data/policy_center.db
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - STORAGE_TYPE=local
      - STORAGE_PATH=/app/uploads
    volumes:
      - ./data:/app/data           # SQLite 数据库
      - ./uploads:/app/uploads     # 上传文件存储
      - ./logs:/app/logs           # 日志文件
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
```

### 9.3 Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 创建数据目录
RUN mkdir -p /app/data /app/uploads /app/logs

# 初始化数据库
RUN python -c "from policy_center.db import init_db; init_db()"

EXPOSE 8000

CMD ["uvicorn", "policy_center.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 9.4 核心代码适配

#### 9.4.1 缓存层（替代 Redis）
```python
# policy_center/utils/cache.py
from cachetools import TTLCache

# 内存缓存
cache = TTLCache(maxsize=1000, ttl=300)

def get_cached(key: str):
    return cache.get(key)

def set_cached(key: str, value, ttl: int = 300):
    cache[key] = value
```

#### 9.4.2 定时任务（替代 Celery）
```python
# policy_center/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler()

# 每日凌晨执行政策过期
@scheduler.scheduled_job(CronTrigger(hour=0, minute=5))
async def expire_policies():
    await policy_service.expire_outdated()

# 在 FastAPI 启动时启动调度器
@app.on_event("startup")
async def startup():
    scheduler.start()
```

#### 9.4.3 本地文件存储
```python
# policy_center/storage/local.py
from pathlib import Path
from uuid import uuid4

class LocalStorage:
    def __init__(self, base_path: str = "./uploads"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def save(self, file_data: bytes, filename: str) -> str:
        ext = Path(filename).suffix
        unique_name = f"{uuid4()}{ext}"
        file_path = self.base_path / unique_name
        file_path.write_bytes(file_data)
        return unique_name

    async def read(self, path: str) -> bytes:
        return (self.base_path / path).read_bytes()

    def get_url(self, path: str) -> str:
        return f"/uploads/{path}"
```

#### 9.4.4 FastAPI 静态文件服务
```python
# policy_center/main.py
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# 挂载上传文件目录
app.mount("/uploads", StaticFiles(directory="./uploads"), name="uploads")

# 挂载前端静态文件
app.mount("/", StaticFiles(directory="./web/dist", html=True), name="web")
```

### 9.5 资源占用

| 资源 | 占用 |
|------|------|
| **内存** | ~150MB |
| **磁盘** | ~100MB + 数据 |
| **CPU** | 0.5核 |
| **启动时间** | ~5秒 |

### 9.6 快速启动

```bash
# 1. 克隆项目
git clone https://github.com/xxx/policy_center.git
cd policy_center

# 2. 创建配置文件
cp .env.example .env
# 编辑 .env，修改 JWT_SECRET_KEY

# 3. 启动
docker-compose up -d

# 4. 访问
# - Web界面: http://localhost:8000
# - API文档: http://localhost:8000/docs
# - MCP端点: http://localhost:8000/mcp

# 5. 查看日志
docker-compose logs -f

# 6. 停止
docker-compose down
```

### 9.7 数据备份与恢复

```bash
# 备份
tar -czf policy_backup_$(date +%Y%m%d).tar.gz ./data ./uploads

# 恢复
tar -xzf policy_backup_20260313.tar.gz
docker-compose restart
```

### 9.5 日志规范
```python
# 结构化日志格式
{
    "timestamp": "2024-06-20T15:30:00.123Z",
    "level": "INFO",
    "logger": "policy_center.api",
    "request_id": "req_550e8400",
    "user_id": "user_001",
    "action": "policy.create",
    "message": "Policy created successfully"
}
```

---

## 10. 测试策略

### 10.1 单元测试
- 覆盖率目标: >80%
- 重点: 业务逻辑（涨幅计算、追溯月数、基数校验）

### 10.2 集成测试
- MCP Tool 接口测试
- REST API 端点测试
- 数据库事务测试

### 10.3 E2E测试场景
```
1. Agent提交 → 自动校验 → 审核通过 → 发布成功
2. Agent提交重复政策 → 返回已有review_id
3. 审核拒绝 → Agent收到通知
4. 政策修改 → 版本历史记录正确
5. 版本回滚 → 数据恢复正确
6. 政策过期 → 状态自动更新
```

### 10.4 性能测试
- 并发提交: 20 Agent同时提交，响应时间 < 1s
- 列表查询: 万级数据，加载时间 < 500ms
- 压力测试: 1000 QPS持续5分钟，无错误

---

## 11. 验收标准

### 11.1 功能验收

| 场景 | 验收标准 |
|------|---------|
| **Agent认证** | 无效API Key返回401，有效Key正常调用 |
| **幂等提交** | 相同idempotency_key/doc_number重复提交返回已有review_id |
| **自动校验** | 上限<下限返回明确错误；追溯政策正确计算月数 |
| **人工审核** | 审核台可查看PDF原文、对比版本差异、一键通过并发布 |
| **版本管理** | 修改已发布政策后产生新版本，可查看历史版本并回滚 |
| **权限控制** | Agent只能查看自己的提交，管理员可管理Agent |
| **外部查询** | HR系统可通过REST API查询当前有效基数，接收Webhook通知 |
| **自动过期** | 过期政策每日自动更新状态，触发通知 |

### 11.2 性能验收
- **并发**: 支持20个Agent同时提交，接口响应时间 < 1s
- **查询**: 政策列表页（万级数据）加载时间 < 500ms
- **稳定性**: 7x24小时运行，内存无泄漏

### 11.3 数据质量验收
- **准确性**: 社保基数数值与官方公告一致，追溯逻辑正确
- **完整性**: 覆盖31个省级行政区2024年度数据
- **可追溯**: 所有变更可查审计日志，保留原始PDF证据

---

## 12. 附录

### 12.1 数据字典

#### 政策状态 (status)
| 值 | 说明 |
|----|------|
| draft | 草稿 |
| pending_review | 待审核（已提交MCP） |
| active | 已发布生效 |
| expired | 已过期 |
| revoked | 已撤销 |

#### 审核状态 (review_queue.status)
| 值 | 说明 |
|----|------|
| pending | 待审核 |
| claimed | 已认领（审核中） |
| approved | 已通过 |
| rejected | 已拒绝 |
| needs_clarification | 需补充材料 |

#### 风险等级 (risk_level)
| 值 | 触发条件 |
|----|----------|
| low | 无异常 |
| medium | 涨幅>10% 或 追溯生效 |
| high | 涨幅>20% 或 重复疑似 |

### 12.2 地区编码规则
- 遵循 GB/T 2260 行政区划代码
- 前两位：省级（11=北京，31=上海，44=广东...）
- 中两位：地级
- 后两位：县级

---

**文档维护**: 本Spec随业务需求迭代更新。

**变更记录**:
- v2.0 (2026-03-13): 简化为极简部署模式，移除 Redis/MinIO/Celery
- v1.2: 切换到 SQLite 轻量化数据库
- v1.1: 增加 MCP认证、幂等性设计