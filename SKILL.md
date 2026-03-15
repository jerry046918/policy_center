# Policy Center Agent Skill

社保公积金基数政策管理平台的 Agent 技能定义，用于外部 AI Agent 提交和查询政策数据。

## 概述

- **名称**: `policy_center`
- **描述**: 提交、查询中国各省市的社保公积金基数政策数据
- **版本**: 1.0.0
- **基础 URL**: `http://localhost:8000/api/agent`

## 认证

所有 API 请求需要以下认证头：

```
Authorization: Bearer <api_key>
```

API Key 需要在系统管理中创建 Agent 凭据后获取。

## API 端点

### 1. 提交政策

**POST** `/api/agent/submit`

提交政策数据到审核队列。提交后会进入人工审核流程。

#### 提交类型

支持两种提交类型：

| 类型 | 说明 | 必填字段 |
|------|------|----------|
| `new` | 新增政策（默认） | 常规字段 |
| `update` | 更新已有政策 | 需提供 `existing_policy_id` 和 `change_description` |

**重要说明**：
- 提交方需要提供充分的信息和自己的判断（新增/更新）
- 审核人是最终决策人，可以修改提交方的判断
- 如果提交方认为是更新但审核人判断是新政策，审核人可以修改
- 如果提交方认为是新政策但审核人判断是更新，审核人也可以修改

#### 请求体

```json
{
  "idempotency_key": "unique-request-id",
  "policy_type": "social_insurance_base",
  "submit_type": "new",
  "structured_data": {
    "title": "2024年北京市社保基数调整通知",
    "doc_number": "京人社发〔2024〕12号",
    "region_code": "110000",
    "published_at": "2024-06-20",
    "effective_start": "2024-07-01",
    "effective_end": null,
    "si_upper_limit": 35283,
    "si_lower_limit": 6821,
    "hf_upper_limit": 35283,
    "hf_lower_limit": 2420,
    "is_retroactive": false,
    "retroactive_start": null,
    "coverage_types": ["养老", "医疗", "失业", "工伤", "生育"],
    "special_notes": null
  },
  "raw_content": {
    "sources": [
      {
        "title": "社保政策文件",
        "url": "https://rsj.beijing.gov.cn/policy/123",
        "extracted_text": "政策原文..."
      },
      {
        "title": "公积金政策文件",
        "url": "https://gjj.beijing.gov.cn/policy/456",
        "extracted_text": "公积金政策原文..."
      }
    ]
  },
  "priority": "normal"
}
```

#### raw_content 格式说明

支持两种格式，推荐使用多来源格式：

**格式一：多来源（推荐）**
```json
{
  "raw_content": {
    "sources": [
      {
        "title": "社保政策文件",
        "url": "https://rsj.beijing.gov.cn/policy/123",
        "extracted_text": "政策原文..."
      },
      {
        "title": "公积金政策文件",
        "url": "https://gjj.beijing.gov.cn/policy/456",
        "extracted_text": "公积金政策原文..."
      }
    ]
  }
}
```

**格式二：单来源（向后兼容）**
```json
{
  "raw_content": {
    "source_url": "https://example.com/policy/123",
    "extracted_text": "政策原文..."
  }
}
```

#### sources 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title` | string | 否 | 来源标题，如"社保政策文件"、"公积金政策文件" |
| `url` | string | 是 | 来源 URL |
| `extracted_text` | string | 否 | 从来源提取的文本内容 |

#### 更新政策示例

```json
{
  "submit_type": "update",
  "existing_policy_id": "policy-uuid-to-update",
  "change_description": "根据最新通知调整社保基数上限，从35283调整为36000",
  "structured_data": {
    "title": "2024年北京市社保基数调整通知（修订）",
    "doc_number": "京人社发〔2024〕15号",
    "region_code": "110000",
    "published_at": "2024-07-15",
    "effective_start": "2024-08-01",
    "si_upper_limit": 36000,
    "si_lower_limit": 6821
  },
  "raw_content": {
    "source_url": "https://example.com/policy/update"
  }
}
```

#### 请求字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `idempotency_key` | string | 否 | 幂等键，防止重复提交 |
| `policy_type` | string | 否 | 政策类型（默认 social_insurance_base）|
| `submit_type` | string | 否 | 提交类型: `new` 或 `update`（默认 new）|
| `existing_policy_id` | string | 更新时必填 | 要更新的政策 ID |
| `change_description` | string | 更新时建议 | 修改内容说明 |
| `structured_data` | object | 是 | 结构化政策数据 |
| `raw_content` | object | 是 | 原始内容 |
| `priority` | string | 否 | 优先级（默认 normal）|

#### 响应

```json
{
  "success": true,
  "review_id": "uuid-review-id",
  "status": "pending_review",
  "policy_id": "uuid-policy-id",
  "warnings": [],
  "estimated_review_time": "24h"
}
```

### 2. 查询政策

**GET** `/api/agent/policies`

查询已发布的政策列表，用于去重检查或获取历史数据。

#### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `region_code` | string | 否 | 六位行政区划码 |
| `effective_year` | int | 否 | 生效年份 |
| `is_retroactive` | bool | 否 | 是否追溯 |
| `limit` | int | 否 | 返回数量（默认 10，最大 100）|

#### 示例

```
GET /api/agent/policies?region_code=110000&effective_year=2024&limit=10
```

#### 响应

```json
{
  "success": true,
  "data": [
    {
      "policy_id": "uuid",
      "title": "2024年北京市社会保险缴费基数上下限调整通知",
      "doc_number": "京人社发〔2024〕12号",
      "region_code": "110000",
      "effective_start": "2024-07-01",
      "si_upper_limit": 35283,
      "si_lower_limit": 6821,
      "is_retroactive": false
    }
  ],
  "total": 1
}
```

### 3. 检查重复

**GET** `/api/agent/check-duplicate`

提交前检查政策是否重复，避免无效提交。

#### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `doc_number` | string | 否 | 官方文号（精确匹配）|
| `region_code` | string | 否 | 地区代码（需配合 effective_start）|
| `effective_start` | string | 否 | 生效日期（需配合 region_code）|

#### 示例

```
GET /api/agent/check-duplicate?doc_number=京人社发〔2024〕12号
```

#### 响应

```json
{
  "success": true,
  "is_duplicate": true,
  "existing_policy_id": "uuid",
  "existing_status": "active",
  "similarity_score": 1.0
}
```

### 4. 获取 Schema

**GET** `/api/agent/schema`

获取政策数据的字段定义和校验规则。

#### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `policy_type` | string | 否 | 政策类型（默认 social_insurance_base）|
| `include_examples` | bool | 否 | 是否包含示例（默认 true）|

#### 响应

```json
{
  "success": true,
  "schema": {
    "policy_type": "social_insurance_base",
    "fields": {
      "title": {"type": "string", "max_length": 500, "required": true},
      "region_code": {"type": "string", "pattern": "^\\d{6}$", "required": true},
      "si_upper_limit": {"type": "integer", "required": true}
    },
    "validation_rules": ["si_upper_limit > si_lower_limit"],
    "examples": [...]
  }
}
```

### 5. 查询提交记录

**GET** `/api/agent/submissions`

查询当前 Agent 的提交记录和审核状态。

#### 参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `status` | string | 否 | 审核状态: pending/approved/rejected |
| `limit` | int | 否 | 返回数量（默认 20，最大 100）|
| `offset` | int | 否 | 偏移量 |

#### 响应

```json
{
  "success": true,
  "data": [
    {
      "review_id": "uuid",
      "policy_id": "uuid",
      "status": "pending",
      "priority": "normal",
      "risk_level": "low",
      "submitted_at": "2024-01-15T10:30:00",
      "sla_deadline": "2024-01-16T10:30:00",
      "submit_type": "new",
      "existing_policy_id": null,
      "change_description": null,
      "final_action": null
    }
  ],
  "total": 1
}
```

## 使用流程

1. **获取 Schema**: 调用 `/api/agent/schema` 了解数据格式要求
2. **检查重复**: 调用 `/api/agent/check-duplicate` 确认政策是否已存在
3. **判断类型**:
   - 如果政策完全不存在：`submit_type="new"`
   - 如果是对现有政策的修正/更新：`submit_type="update"`，并提供原政策ID和修改说明
4. **提交政策**: 调用 `/api/agent/submit` 提交政策数据
5. **跟踪状态**: 调用 `/api/agent/submissions` 查询审核状态

## 提交类型判断指南

### 应该使用 "new" 的场景

- 该地区首次发布的政策
- 新年度的基数调整（如2024年发布2025年基数）
- 完全不同的政策文号

### 应该使用 "update" 的场景

- 发现已发布政策的数据错误需要修正
- 政策本身有修订或补充说明
- 同一文号的勘误或更新

### 提交时的最佳实践

1. **提供充分的 change_description**: 说明具体修改了什么、为什么修改
2. **附上原始证据**: 在 `raw_content` 中提供来源 URL 和原文
3. **使用 idempotency_key**: 防止网络重试导致重复提交
4. **审核人拥有最终决定权**: 即使你的判断有误，审核人会修正

## 字段说明

### 地区代码 (region_code)

使用 GB/T 2260 六位行政区划码：
- 省级: 110000（北京）、310000（上海）、440000（广东）
- 市级: 110100（北京市）、440300（深圳市）

### 优先级 (priority)

- `urgent`: 1 小时内处理
- `high`: 4 小时内处理
- `normal`: 24 小时内处理（默认）
- `low`: 72 小时内处理

### 覆盖险种 (coverage_types)

可选值: `养老`, `医疗`, `失业`, `工伤`, `生育`, `公积金`

## 错误处理

所有错误响应格式：

```json
{
  "detail": "错误描述",
  "status_code": 400
}
```

常见错误码：
- `401`: API Key 无效或缺失
- `403`: 权限不足
- `422`: 请求数据验证失败

## 完整示例

### Python 示例

```python
import requests

API_BASE = "http://localhost:8000/api/agent"
API_KEY = "your-api-key"

headers = {"Authorization": f"Bearer {API_KEY}"}

# 1. 获取 Schema
schema = requests.get(f"{API_BASE}/schema", headers=headers).json()

# 2. 检查重复
dup_check = requests.get(
    f"{API_BASE}/check-duplicate",
    params={"doc_number": "京人社发〔2024〕12号"},
    headers=headers
).json()

if dup_check["is_duplicate"]:
    # 发现重复，提交为更新
    response = requests.post(
        f"{API_BASE}/submit",
        json={
            "idempotency_key": "update-key-123",
            "submit_type": "update",
            "existing_policy_id": dup_check["existing_policy_id"],
            "change_description": "根据最新文件更新社保基数上下限",
            "structured_data": {
                "title": "2024年北京市社保基数调整通知（更新）",
                "region_code": "110000",
                "published_at": "2024-06-20",
                "effective_start": "2024-07-01",
                "si_upper_limit": 36000,  # 更新后的值
                "si_lower_limit": 7000
            },
            "raw_content": {
                "source_url": "https://example.com/policy/updated"
            }
        },
        headers=headers
    )
else:
    # 无重复，提交为新政策
    response = requests.post(
        f"{API_BASE}/submit",
        json={
            "idempotency_key": "new-key-123",
            "submit_type": "new",
            "structured_data": {
                "title": "2024年北京市社保基数调整通知",
                "doc_number": "京人社发〔2024〕12号",
                "region_code": "110000",
                "published_at": "2024-06-20",
                "effective_start": "2024-07-01",
                "si_upper_limit": 35283,
                "si_lower_limit": 6821
            },
            "raw_content": {
                "source_url": "https://example.com/policy"
            }
        },
        headers=headers
    )
print(response.json())
```

### cURL 示例

```bash
# 提交政策
curl -X POST http://localhost:8000/api/agent/submit \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "structured_data": {
      "title": "2024年北京市社保基数调整通知",
      "region_code": "110000",
      "published_at": "2024-06-20",
      "effective_start": "2024-07-01",
      "si_upper_limit": 35283,
      "si_lower_limit": 6821
    },
    "raw_content": {
      "source_url": "https://example.com/policy"
    }
  }'
```
