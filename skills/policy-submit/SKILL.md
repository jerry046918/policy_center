---
name: policy-submit
description: Collect and submit social insurance / housing fund base policies (社保基数/公积金基数) to the Policy Center system via its Agent REST API. Use this skill whenever the user wants to submit (提交), add (新增), update (更新), collect (采集), or sync (录入) policy data for any Chinese province or city -- including vague requests like "帮我查下北京最新社保基数然后提交" or "submit Beijing 2025 social insurance base". Also applies when the user provides a government policy document URL or text for extraction, wants to batch-ingest policies for multiple regions, or asks to check/track submission review status (审核状态). This skill is specifically for operating on policy DATA through the Agent API -- not for developing, debugging, deploying, or modifying the Policy Center application code itself.
---

# Policy Submission Skill

This skill enables you to collect social insurance and housing fund base policies for Chinese provinces and cities and submit them to the Policy Center system through its Agent REST API. The system manages policies for China's 31 provinces (300+ cities). Submissions enter a human review queue; once approved they become active policies.

## Prerequisites

Before using the API, you need two environment variables. Check that they are set before making any API calls:

- `POLICY_CENTER_BASE_URL` -- the base URL of the Policy Center service (e.g. `http://localhost:8000`)
- `POLICY_CENTER_API_KEY` -- the API key issued by an admin

If either is missing, ask the user to provide them. All API requests require the header `Authorization: Bearer <API_KEY>`.

## End-to-End Workflow

Follow these steps in order. Do not skip the duplicate check -- submitting a duplicate as "new" creates extra work for reviewers.

### Step 1: Collect the policy data

The user may provide varying levels of detail -- from a specific URL and exact numbers to a vague request like "北京好像出了新的社保基数通知，帮我查一下提交到系统". Your job is to fill in the gaps.

**If the user provides a URL or document text**, extract the structured data directly from it.

**If the user gives a vague request** (just a city name and year, or "check the latest policy"), you need to actively search for the information:

1. Use the WebFetch tool to retrieve policy pages from the relevant government HR bureau website. Target these official domains by region:

| Region | HR Bureau Domain | Housing Fund Domain |
|--------|-----------------|-------------------|
| 北京 | rsj.beijing.gov.cn | gjj.beijing.gov.cn |
| 上海 | rsj.sh.gov.cn | www.shgjj.com |
| 广东/广州 | hrss.gd.gov.cn / rsj.gz.gov.cn | gjj.gz.gov.cn |
| 深圳 | hrss.sz.gov.cn | gjj.sz.gov.cn |
| 江苏/南京 | jshrss.jiangsu.gov.cn / rsj.nanjing.gov.cn | gjj.nanjing.gov.cn |
| 浙江/杭州 | hrss.zj.gov.cn / hrss.hangzhou.gov.cn | gjj.hangzhou.gov.cn |
| 天津 | hrss.tj.gov.cn | gjj.tj.gov.cn |
| 重庆 | rlsbj.cq.gov.cn | gjj.cq.gov.cn |
| 四川/成都 | rst.sc.gov.cn / cdhrss.chengdu.gov.cn | gjj.chengdu.gov.cn |

For provinces/cities not in this table, the domain pattern is typically `rsj.{city}.gov.cn` or `hrss.{city}.gov.cn` for HR bureaus and `gjj.{city}.gov.cn` for housing fund centers.

2. Search with targeted queries like:
   - `"{城市名} {年份}年 社会保险缴费基数 上下限 通知"`
   - `"{城市名} {年份}年 社保基数调整"`
   - `"{城市名} {年份}年 住房公积金 缴存基数"`

3. Policy announcements are typically published between May-July each year for an annual adjustment starting July 1. Some cities (especially in Guangdong) adjust earlier with retroactive effect from January 1.

4. If you can't find the exact policy page, tell the user what you searched for and ask them to provide the source URL or document text.

Extract the following from the source material:

| Field | Required | Description |
|-------|----------|-------------|
| `title` | yes | Full policy name (max 500 chars), e.g. "关于2024年度北京市社会保险缴费工资基数上下限的通知" |
| `region_code` | yes | 6-digit GB/T 2260 administrative division code (province ends in `0000`, city ends in `00`) |
| `published_at` | yes | Publication date in `YYYY-MM-DD` format |
| `effective_start` | yes | Effective start date in `YYYY-MM-DD` format |
| `effective_end` | no | Effective end date in `YYYY-MM-DD` format (null if still current) |
| `si_upper_limit` | yes | Social insurance base upper limit in CNY/month (integer, > 0) |
| `si_lower_limit` | yes | Social insurance base lower limit in CNY/month (integer, > 0) |
| `hf_upper_limit` | no | Housing fund base upper limit in CNY/month |
| `hf_lower_limit` | no | Housing fund base lower limit in CNY/month |
| `is_retroactive` | no | Whether the policy takes effect retroactively (default false) |
| `retroactive_start` | no | Retroactive start date (required when is_retroactive is true) |
| `coverage_types` | no | Insurance types covered, default `["养老","医疗","失业","工伤","生育"]` |
| `special_notes` | no | Additional notes (max 1000 chars) |

Common region codes for reference:

| Code | Region | Code | Region |
|------|--------|------|--------|
| 110000 | 北京 | 440000 | 广东 |
| 120000 | 天津 | 440100 | 广州 |
| 310000 | 上海 | 440300 | 深圳 |
| 320000 | 江苏 | 500000 | 重庆 |
| 330000 | 浙江 | 510000 | 四川 |

If you are unsure about a region code, check the project's `data/regions.json` file which has the full list of provinces and cities with their GB/T 2260 codes.

### Step 2: Check for duplicates

Before submitting, always check if a policy with the same region and effective date already exists:

```bash
curl -s -H "Authorization: Bearer ${POLICY_CENTER_API_KEY}" \
  "${POLICY_CENTER_BASE_URL}/api/agent/check-duplicate?region_code=REGION_CODE&effective_start=YYYY-MM-DD"
```

Read the response:
- If `is_duplicate` is `false` -- proceed with `submit_type: "new"`
- If `is_duplicate` is `true` -- use `submit_type: "update"` and set `existing_policy_id` from the response. Also prepare a `change_description` explaining what changed.

### Step 3: Optionally query existing policies

If you need context about what policies already exist for a region (e.g. to compare values or detect changes), query existing active policies:

```bash
curl -s -H "Authorization: Bearer ${POLICY_CENTER_API_KEY}" \
  "${POLICY_CENTER_BASE_URL}/api/agent/policies?region_code=REGION_CODE&effective_year=YEAR&limit=10"
```

This helps you catch suspicious data -- for example, if the new upper limit is 50% higher than the previous year, you should note this in `special_notes`.

### Step 4: Submit the policy

Construct and send the submission. Generate a unique `idempotency_key` using the format `{source}-{region_code}-{effective_start}-{short_hash}` to prevent accidental duplicates.

#### For a new policy:

```bash
curl -s -X POST "${POLICY_CENTER_BASE_URL}/api/agent/submit" \
  -H "Authorization: Bearer ${POLICY_CENTER_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "idempotency_key": "crawl-110000-2024-07-01-a1b2c3",
    "submit_type": "new",
    "structured_data": {
      "title": "关于2024年度北京市社会保险缴费工资基数上下限的通知",
      "region_code": "110000",
      "published_at": "2024-06-20",
      "effective_start": "2024-07-01",
      "effective_end": null,
      "si_upper_limit": 35283,
      "si_lower_limit": 6821,
      "hf_upper_limit": 35283,
      "hf_lower_limit": 2420,
      "is_retroactive": false,
      "coverage_types": ["养老", "医疗", "失业", "工伤", "生育"],
      "special_notes": null
    },
    "raw_content": {
      "sources": [
        {
          "title": "北京市人力资源和社会保障局通知",
          "doc_number": "京人社发〔2024〕12号",
          "url": "https://rsj.beijing.gov.cn/xxxx",
          "extracted_text": "经市政府批准，2024年度各项社会保险缴费工资基数上限为35283元..."
        }
      ]
    },
    "priority": "normal"
  }'
```

#### For updating an existing policy:

```bash
curl -s -X POST "${POLICY_CENTER_BASE_URL}/api/agent/submit" \
  -H "Authorization: Bearer ${POLICY_CENTER_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "idempotency_key": "update-110000-2024-07-01-fix1",
    "submit_type": "update",
    "existing_policy_id": "uuid-from-duplicate-check",
    "change_description": "修正社保基数下限，原6821更正为6921",
    "structured_data": {
      "title": "关于2024年度北京市社会保险缴费工资基数上下限的通知",
      "region_code": "110000",
      "published_at": "2024-06-20",
      "effective_start": "2024-07-01",
      "si_upper_limit": 35283,
      "si_lower_limit": 6921,
      "hf_upper_limit": 35283,
      "hf_lower_limit": 2420
    },
    "raw_content": {
      "sources": [
        {
          "url": "https://rsj.beijing.gov.cn/correction",
          "extracted_text": "勘误：下限应为6921元..."
        }
      ]
    },
    "priority": "normal"
  }'
```

### Step 5: Verify the submission

Check the response from the submit call:

```json
{
  "success": true,
  "review_id": "rev_xxx",
  "status": "pending_review",
  "policy_id": "xxx",
  "warnings": [],
  "estimated_review_time": "24h"
}
```

- If `success` is true, report the `review_id` and `estimated_review_time` to the user
- If there are `warnings`, report them -- they don't block the submission but the user should be aware
- If the status is `already_submitted`, the same `idempotency_key` was used before; report the existing `review_id`

### Step 6: Track submission status (optional)

If the user wants to check on their submissions:

```bash
curl -s -H "Authorization: Bearer ${POLICY_CENTER_API_KEY}" \
  "${POLICY_CENTER_BASE_URL}/api/agent/submissions?status=pending&limit=20"
```

Status values: `pending`, `claimed`, `approved`, `rejected`, `needs_clarification`.

For `needs_clarification` submissions, check the `reviewer_notes` field and help the user address the reviewer's questions.

## Validation Awareness

The system automatically validates submissions. Be aware of these rules to avoid unnecessary warnings:

1. **Upper > Lower**: `si_upper_limit` must exceed `si_lower_limit`. Same for housing fund if both are provided.
2. **Retroactive detection**: If `effective_start` is earlier than `published_at`, the system flags it. Set `is_retroactive: true` to acknowledge this intentionally.
3. **Reasonable bounds**: Base limits typically fall between 2,000 and 35,000 CNY/month. Values outside this range get flagged.
4. **Change rate**: If the same region has an existing policy and the new values differ by more than 50%, it gets flagged for closer review.

Warnings don't block submission -- the policy still enters the review queue, but flagged items receive more scrutiny.

## Priority Selection

Choose the right priority based on timing:

| Priority | SLA | When to use |
|----------|-----|-------------|
| `urgent` | 1 hour | Policy takes effect immediately or retroactively |
| `high` | 4 hours | Policy takes effect within 7 days |
| `normal` | 24 hours | Standard submission |
| `low` | 72 hours | Historical data, no urgency |

## Error Handling

| HTTP Status | Meaning | What to do |
|-------------|---------|------------|
| 200 | Success | Process the response normally |
| 400 | Bad request | Read the `detail` field, fix the data, retry |
| 401 | Auth failed | API key is invalid or expired; ask the user |
| 500 | Server error | Wait a few seconds and retry (up to 3 times) |

On 500 errors, use exponential backoff: wait 2s, then 4s, then 8s before retrying.

## Parsing Government Policy Documents

When reading a government policy notice (via WebFetch or from user-pasted text), look for these key patterns in the document:

- **Social insurance base limits** -- Keywords: 社会保险缴费基数上下限, 社保基数, 缴费工资基数. Look for "上限" (upper) and "下限" (lower) followed by numbers in 元/月.
- **Housing fund limits** -- Keywords: 住房公积金缴存基数, 公积金基数. Often in a separate document from SI limits.
- **Effective date** -- Keywords: 自...起施行, ...起执行, 执行日期. Often in format "自2024年7月1日起".
- **Publication date** -- Keywords: 发布日期, 印发日期. Sometimes only visible in the page header or document metadata.
- **Document number** (文号) -- Format like 京人社发〔2024〕12号, 沪人社规〔2025〕8号. The brackets 〔〕 are Chinese-style; don't use regular brackets.
- **Coverage types** -- Keywords: 养老保险, 医疗保险, 失业保险, 工伤保险, 生育保险. Default to all five unless the notice specifies otherwise.
- **Average salary reference** -- Keywords: 社会平均工资, 全口径城镇单位就业人员月平均工资. The upper limit is typically 300% of this value, the lower limit is 60%. This helps verify the numbers.

Include the relevant paragraphs containing the actual numbers in `raw_content.sources[].extracted_text` as evidence for reviewers. Don't include the entire document -- just the key paragraphs.

## Pre-submission Data Verification

Before submitting, do a quick sanity check:

1. **Upper > Lower**: `si_upper_limit` must be greater than `si_lower_limit`. Same for HF.
2. **Reasonable range**: SI limits should typically be between 2,000-40,000 CNY/month. If values are outside this range, double-check the source.
3. **Upper/lower ratio**: The upper limit is typically 3-5x the lower limit. A ratio above 5x is unusual.
4. **Year-over-year change**: If you queried the previous year's policy, the annual change is typically 3-10%. Changes above 20% deserve a note in `special_notes`.
5. **Retroactive check**: If `effective_start` < `published_at`, you must set `is_retroactive: true` and `retroactive_start`.
6. **Date format**: All dates must be `YYYY-MM-DD`. Common effective dates are July 1 (大多数城市) and January 1 (部分广东城市).

## Batch Submission

When the user wants to submit policies for multiple regions at once:

1. Process each region sequentially (not in parallel) to avoid overwhelming the API
2. Check duplicates for each one before submitting
3. Use unique `idempotency_key` values for each submission
4. Report a summary at the end: how many succeeded, how many had warnings, how many were duplicates
