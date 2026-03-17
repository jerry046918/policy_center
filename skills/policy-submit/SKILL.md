---
name: policy-submit
description: Collect and submit policy data (社保基数/公积金基数/社平工资/人才政策等) to the Policy Center system via its Agent REST API. Use this skill whenever the user wants to submit (提交), add (新增), update (更新), collect (采集), or sync (录入) policy data for any Chinese province or city -- including vague requests like "帮我查下北京最新社保基数然后提交" or "submit Beijing 2025 housing fund base". Also applies when the user provides a government policy document URL or text for extraction, wants to batch-ingest policies for multiple regions, or asks to check/track submission review status (审核状态). This skill is specifically for operating on policy DATA through the Agent API -- not for developing, debugging, deploying, or modifying the Policy Center application code itself.
---

# Policy Submission Skill

This skill enables you to collect policy data for Chinese provinces and cities and submit them to the Policy Center system through its Agent REST API. The system supports **multiple policy types** (社保基数, 公积金基数, 社平工资, 人才政策, and custom types defined by administrators). Social insurance and housing fund are **separate** policy types -- submit them independently. Submissions enter a human review queue; once approved they become active policies.

## Prerequisites

Before using the API, you need two environment variables. Check that they are set before making any API calls:

- `POLICY_CENTER_BASE_URL` -- the base URL of the Policy Center service (e.g. `http://localhost:8000`)
- `POLICY_CENTER_API_KEY` -- the API key issued by an admin

If either is missing, ask the user to provide them. All API requests require the header `Authorization: Bearer <API_KEY>`.

## CRITICAL: Character Encoding

**All HTTP requests MUST use UTF-8 encoding.** Chinese characters will be permanently corrupted (replaced with `?`) if sent in any other encoding. Follow these rules strictly:

1. **Always set the Content-Type header explicitly**:
   ```
   Content-Type: application/json; charset=utf-8
   ```

2. **When using curl**, pass `--json` or ensure the request body file is saved as UTF-8:
   ```bash
   curl -X POST ... -H "Content-Type: application/json; charset=utf-8" --data-binary @payload.json
   ```
   If constructing the JSON inline, make sure your shell environment uses UTF-8 (`export LANG=en_US.UTF-8` or equivalent).

3. **When using Python `requests`**, always use the `json=` parameter (which auto-encodes as UTF-8). Never use `data=json.dumps(...).encode('ascii')` or `data=json.dumps(...).encode('latin-1')`:
   ```python
   # CORRECT
   response = requests.post(url, json=payload, headers=headers)

   # WRONG -- may destroy Chinese characters
   response = requests.post(url, data=json.dumps(payload), headers=headers)
   ```

4. **When using the Bash tool to build JSON**, never pipe Chinese text through commands that may alter encoding. Build the JSON in a single string or write it to a temp file with explicit UTF-8 encoding first.

5. **Verify before submitting**: confirm that the `title` field and any other Chinese text in your payload are not garbled. If you see `?`, `\ufffd`, or mojibake in your data, stop and fix the encoding before submitting -- corrupted data cannot be recovered.

## End-to-End Workflow

Follow these steps in order. Do not skip the schema fetch or duplicate check.

**Note**: Social insurance (社保) and housing fund (公积金) are separate policy types. If a government document contains both, run Steps 2-5 **twice** -- once for `social_insurance` and once for `housing_fund`.

```
Step 0: GET /api/agent/schema?policy_type=...   ← understand the target type's fields
Step 1: Collect the policy data                  ← web search + parse
Step 2: GET /api/agent/check-duplicate           ← check if it already exists
Step 3: GET /api/agent/policies                  ← (optional) compare with existing
Step 4: POST /api/agent/submit                   ← submit structured data + evidence
Step 5: Verify the response                      ← check warnings
Step 6: GET /api/agent/submissions               ← (optional) track review status
```

### Step 0: Fetch the schema for the target policy type

**Always call the schema endpoint first** to understand what fields are required for the policy type you are about to submit. The system supports multiple policy types, each with different fields.

```bash
# Get schema for a specific type (response is wrapped in { "success": true, "schema": { ... } })
curl -s -H "Authorization: Bearer ${POLICY_CENTER_API_KEY}" \
  "${POLICY_CENTER_BASE_URL}/api/agent/schema?policy_type=social_insurance&include_examples=true"

# To list all available types, pass an unrecognized policy_type to trigger the fallback listing:
curl -s -H "Authorization: Bearer ${POLICY_CENTER_API_KEY}" \
  "${POLICY_CENTER_BASE_URL}/api/agent/schema?policy_type=_list_all"
```

The response is wrapped in `{ "success": true, "schema": { ... } }`. Inside `schema` you'll find:
- `common_fields` -- fields shared by ALL policy types (title, region_code, dates)
- `type_specific_fields` -- fields unique to this policy type (e.g. si_upper_limit for social insurance)
- `validation_rules` -- what checks the system runs
- `examples` -- a complete example submission
- `available_types` -- list of all registered policy types

**Built-in policy types:**

| type_code | Name | Key Fields |
|-----------|------|------------|
| `social_insurance` | 社保基数 | si_upper_limit, si_lower_limit, is_retroactive, coverage_types |
| `housing_fund` | 公积金基数 | hf_upper_limit, hf_lower_limit, is_retroactive |
| `avg_salary` | 社会平均工资 | avg_salary_total, avg_salary_monthly, statistics_year, growth_rate |
| `talent_policy` | 人才政策 | talent_categories, certification_requirements, required_documents |

Additional types may be dynamically created by system administrators. Always check the schema endpoint to discover the latest available types and their fields.

### Step 1: Collect the policy data

The user may provide varying levels of detail -- from a specific URL and exact numbers to a vague request like "北京好像出了新的社保基数通知，帮我查一下提交到系统". Your job is to fill in the gaps.

**If the user provides a URL or document text**, extract the structured data directly from it using WebFetch.

**If the user gives a vague request** (just a city name and year, or "check the latest policy"), you need to actively search for the information.

#### Web Search Strategy (IMPORTANT)

**Always prefer web search over directly fetching specific government URLs.** Government websites frequently change their URL structures, move content, or block automated access. Directly fetching a guessed URL (e.g. `https://rsj.beijing.gov.cn/xxxx`) will very likely fail with 404, 403, or return irrelevant content.

**Correct approach -- use web search first:**

1. Use a web search tool (e.g. WebSearch, Google, Bing) with targeted Chinese queries:
   - `"{城市名} {年份}年 社会保险缴费基数 上下限 通知"` -- for SI base limits
   - `"{城市名} {年份}年 社保基数调整 site:gov.cn"` -- restrict to government sites
   - `"{城市名} {年份}年 住房公积金 缴存基数 调整"` -- for HF limits
   - `"{城市名} {年份}年 社会平均工资 全口径"` -- for average salary
   - `"{城市名} {年份}年 人才引进 认定 补贴政策"` -- for talent policies

2. From the search results, identify the official government source URL (prefer `*.gov.cn` domains).

3. Then use WebFetch to retrieve the content from the actual URL found in search results.

4. If web search returns no results, try alternative query patterns:
   - Replace 社保基数 with 缴费工资基数
   - Replace 社会保险 with 社保
   - Add 人社局 or 人力资源 to the query
   - Try the province-level query if the city-level search fails

**Do NOT do this:**
- Do not guess or construct government website URLs from memory
- Do not directly WebFetch `https://rsj.{city}.gov.cn/xxxx` without first confirming the URL exists via search
- Do not assume a URL pattern works because it worked for another city

**Reference: official domain patterns** (use these to verify search results, NOT to construct URLs to fetch):

| Region | HR Bureau Pattern | Housing Fund Pattern |
|--------|-----------------|---------------------|
| 北京 | rsj.beijing.gov.cn | gjj.beijing.gov.cn |
| 上海 | rsj.sh.gov.cn | www.shgjj.com |
| 广东/广州 | hrss.gd.gov.cn / rsj.gz.gov.cn | gjj.gz.gov.cn |
| 深圳 | hrss.sz.gov.cn | gjj.sz.gov.cn |
| 江苏/南京 | jshrss.jiangsu.gov.cn | gjj.nanjing.gov.cn |
| 浙江/杭州 | hrss.zj.gov.cn | gjj.hangzhou.gov.cn |
| 天津 | hrss.tj.gov.cn | gjj.tj.gov.cn |
| 重庆 | rlsbj.cq.gov.cn | gjj.cq.gov.cn |
| 四川/成都 | rst.sc.gov.cn | gjj.chengdu.gov.cn |

5. Policy announcements are typically published between May-July each year for an annual adjustment starting July 1. Some cities (especially in Guangdong) adjust earlier with retroactive effect from January 1.

6. If you can't find the exact policy page after searching, tell the user what you searched for and ask them to provide the source URL or document text.

#### Extracting Structured Data

After locating the source document, extract the fields required by the schema you fetched in Step 0.

**For `social_insurance` type:**

| Field | How to find it in the document |
|-------|-------------------------------|
| `title` | The full title of the policy notice |
| `region_code` | 6-digit GB/T 2260 code -- look up from the region name |
| `published_at` | 发布日期 / 印发日期 in the header |
| `effective_start` | 自...起施行 / ...起执行 / 执行日期 |
| `si_upper_limit` | 社保基数上限 / 缴费工资基数上限 (元/月) |
| `si_lower_limit` | 社保基数下限 / 缴费工资基数下限 (元/月) |
| `is_retroactive` | Set `true` if `effective_start` is **earlier** than `published_at` (see below) |
| `retroactive_start` | The actual start date of the retroactive period (often Jan 1 or Jul 1 of the previous year) |

**For `housing_fund` type** (often published in a separate document):

| Field | How to find it in the document |
|-------|-------------------------------|
| `title` | The full title of the housing fund notice |
| `region_code` | Same 6-digit GB/T 2260 code |
| `published_at` | 发布日期 / 印发日期 |
| `effective_start` | 自...起施行 / ...起执行 |
| `hf_upper_limit` | 公积金缴存基数上限 (元/月) |
| `hf_lower_limit` | 公积金缴存基数下限 (元/月) |
| `is_retroactive` | Set `true` if `effective_start` is earlier than `published_at` |
| `retroactive_start` | The actual start date of the retroactive period |

**Important**: Social insurance and housing fund are **separate policy types**. If a government document contains both SI and HF limits, submit them as **two separate policies** with `policy_type=social_insurance` and `policy_type=housing_fund` respectively.

**Parsing tips for Chinese policy documents:**

- **Social insurance base limits**: Keywords: 社会保险缴费基数上下限, 社保基数, 缴费工资基数. Look for "上限" (upper) and "下限" (lower) followed by numbers in 元/月.
- **Housing fund limits**: Keywords: 住房公积金缴存基数, 公积金基数. Often in a separate document from SI limits.
- **Effective date**: Keywords: 自...起施行, ...起执行, 执行日期. Often "自2024年7月1日起".
- **Retroactive policies (追溯生效)**: This is very common -- a policy is published in, say, September 2024 but states it takes effect from July 1, 2024. Clues:
  - `published_at` (e.g. 2024-09-15) is **later** than `effective_start` (e.g. 2024-07-01)
  - Keywords: 追溯执行, 补缴, 从...起补缴差额, 自...起执行（含补缴...）
  - Guangdong cities frequently publish in Q3-Q4 with retroactive effect from January 1
  - When detected, set `is_retroactive: true` and `retroactive_start` to the earliest date the policy applies
  - Also set `priority: "urgent"` or `"high"` since retroactive policies have immediate impact on back-payments
- **Document number** (文号): Format like 京人社发〔2024〕12号. Use Chinese brackets 〔〕.
- **Coverage types**: 养老保险, 医疗保险, 失业保险, 工伤保险, 生育保险. Default to all five.
- **Average salary reference**: 全口径城镇单位就业人员月平均工资. Upper limit is typically 300% of this, lower limit is 60%.

Common region codes:

| Code | Region | Code | Region |
|------|--------|------|--------|
| 110000 | 北京 | 440000 | 广东 |
| 120000 | 天津 | 440100 | 广州 |
| 310000 | 上海 | 440300 | 深圳 |
| 320000 | 江苏 | 500000 | 重庆 |
| 330000 | 浙江 | 510000 | 四川 |

If unsure about a region code, check the project's `data/regions.json` for the full list.

### Step 2: Check for duplicates

Before submitting, always check if a policy with the same region, effective date, **and policy type** already exists:

```bash
curl -s -H "Authorization: Bearer ${POLICY_CENTER_API_KEY}" \
  "${POLICY_CENTER_BASE_URL}/api/agent/check-duplicate?region_code=REGION_CODE&effective_start=YYYY-MM-DD&policy_type=social_insurance"
```

Note the `policy_type` parameter -- different types are independent. A social insurance policy and an average salary policy for the same region and date are NOT duplicates.

Read the response:
- If `is_duplicate` is `false` -- proceed with `submit_type: "new"`
- If `is_duplicate` is `true` -- use `submit_type: "update"` and set `existing_policy_id` from the response. Also prepare a `change_description` explaining what changed.

### Step 3: Optionally query existing policies

If you need context about what policies already exist for a region (e.g. to compare values or detect changes):

```bash
curl -s -H "Authorization: Bearer ${POLICY_CENTER_API_KEY}" \
  "${POLICY_CENTER_BASE_URL}/api/agent/policies?region_code=REGION_CODE&effective_year=YEAR&policy_type=social_insurance&limit=10"
```

### Step 4: Submit the policy

Construct and send the submission. Generate a unique `idempotency_key` using the format `{source}-{region_code}-{effective_start}-{short_hash}`.

**Remember: set `Content-Type: application/json; charset=utf-8` to preserve Chinese characters.**

The `policy_type` field determines which type-specific fields are expected in `structured_data`. Use the fields defined in the schema you fetched in Step 0.

#### Example: social_insurance

```bash
curl -s -X POST "${POLICY_CENTER_BASE_URL}/api/agent/submit" \
  -H "Authorization: Bearer ${POLICY_CENTER_API_KEY}" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "idempotency_key": "crawl-110000-2024-07-01-a1b2c3",
    "policy_type": "social_insurance",
    "submit_type": "new",
    "structured_data": {
      "title": "关于2024年度北京市社会保险缴费工资基数上下限的通知",
      "region_code": "110000",
      "published_at": "2024-06-20",
      "effective_start": "2024-07-01",
      "effective_end": null,
      "si_upper_limit": 35283,
      "si_lower_limit": 6821,
      "is_retroactive": false,
      "coverage_types": ["养老", "医疗", "失业", "工伤", "生育"],
      "special_notes": null
    },
    "raw_content": {
      "sources": [
        {
          "title": "北京市人力资源和社会保障局通知",
          "doc_number": "京人社发〔2024〕12号",
          "url": "https://rsj.beijing.gov.cn/actual-url-from-search",
          "extracted_text": "经市政府批准，2024年度各项社会保险缴费工资基数上限为35283元..."
        }
      ]
    },
    "priority": "normal"
  }'
```

#### Example: housing_fund

```bash
curl -s -X POST "${POLICY_CENTER_BASE_URL}/api/agent/submit" \
  -H "Authorization: Bearer ${POLICY_CENTER_API_KEY}" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "idempotency_key": "crawl-110000-hf-2024-07-01-d4e5f6",
    "policy_type": "housing_fund",
    "submit_type": "new",
    "structured_data": {
      "title": "关于2024年度北京市住房公积金缴存基数上下限的通知",
      "region_code": "110000",
      "published_at": "2024-06-25",
      "effective_start": "2024-07-01",
      "hf_upper_limit": 35283,
      "hf_lower_limit": 2420,
      "is_retroactive": false
    },
    "raw_content": {
      "sources": [
        {
          "title": "北京住房公积金管理中心通知",
          "url": "https://gjj.beijing.gov.cn/actual-url-from-search",
          "extracted_text": "2024年度住房公积金缴存基数上限为35283元，下限为2420元..."
        }
      ]
    },
    "priority": "normal"
  }'
```

#### Example: retroactive social_insurance (追溯生效)

A very common scenario: the policy is published months after the effective date. For example, Guangzhou publishes in November 2024 that SI base limits apply retroactively from July 1, 2024. Employers must back-pay the difference for July-November.

```bash
curl -s -X POST "${POLICY_CENTER_BASE_URL}/api/agent/submit" \
  -H "Authorization: Bearer ${POLICY_CENTER_API_KEY}" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "idempotency_key": "crawl-440100-si-2024-07-01-retro",
    "policy_type": "social_insurance",
    "submit_type": "new",
    "structured_data": {
      "title": "关于公布2024年度广州市社会保险缴费基数上下限的通知",
      "region_code": "440100",
      "published_at": "2024-11-08",
      "effective_start": "2024-07-01",
      "si_upper_limit": 27501,
      "si_lower_limit": 5500,
      "is_retroactive": true,
      "retroactive_start": "2024-07-01",
      "coverage_types": ["养老", "医疗", "失业", "工伤", "生育"],
      "special_notes": "自2024年7月起执行，7-11月差额需补缴"
    },
    "raw_content": {
      "sources": [
        {
          "title": "广州市人力资源和社会保障局通知",
          "url": "https://rsj.gz.gov.cn/actual-url-from-search",
          "extracted_text": "经市政府批准，我市2024年度社保缴费基数上限为27501元，下限为5500元，自2024年7月1日起执行。用人单位应补缴7月至今的差额部分..."
        }
      ]
    },
    "priority": "urgent"
  }'
```

Key points for retroactive submissions:
- `published_at` (2024-11-08) is **later** than `effective_start` (2024-07-01) -- this is the defining characteristic
- `is_retroactive: true` must be set, otherwise the system will flag it as a warning
- `retroactive_start` should be set to the earliest date the new base applies (usually equals `effective_start`)
- Use `priority: "urgent"` because retroactive policies have immediate financial impact (employers need to back-pay)
- Add a `special_notes` explaining the back-payment requirement

#### Example: avg_salary

```bash
curl -s -X POST "${POLICY_CENTER_BASE_URL}/api/agent/submit" \
  -H "Authorization: Bearer ${POLICY_CENTER_API_KEY}" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "idempotency_key": "crawl-110000-avg-2023-b2c3d4",
    "policy_type": "avg_salary",
    "submit_type": "new",
    "structured_data": {
      "title": "关于公布2023年度北京市全口径城镇单位就业人员平均工资的通知",
      "region_code": "110000",
      "published_at": "2024-06-15",
      "effective_start": "2024-07-01",
      "avg_salary_total": 124000,
      "avg_salary_monthly": 10333,
      "statistics_year": 2023,
      "growth_rate": 5.8
    },
    "raw_content": {
      "sources": [
        {
          "url": "https://rsj.beijing.gov.cn/actual-url-from-search",
          "extracted_text": "2023年度全口径城镇单位就业人员平均工资为124000元..."
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
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{
    "idempotency_key": "update-110000-2024-07-01-fix1",
    "policy_type": "social_insurance",
    "submit_type": "update",
    "existing_policy_id": "uuid-from-duplicate-check",
    "change_description": "修正社保基数下限，原6821更正为6921",
    "structured_data": { ... },
    "raw_content": { ... },
    "priority": "normal"
  }'
```

### Step 5: Verify the submission

Check the response:

```json
{
  "success": true,
  "review_id": "rev_xxx",
  "status": "pending_review",
  "policy_id": "xxx",
  "policy_type": "social_insurance",
  "warnings": [],
  "estimated_review_time": "24h"
}
```

- If `success` is true, report the `review_id` and `estimated_review_time` to the user
- If there are `warnings`, report them -- they don't block the submission but the user should be aware
- If the status is `already_submitted`, the same `idempotency_key` was used before; report the existing `review_id`

### Step 6: Track submission status (optional)

```bash
curl -s -H "Authorization: Bearer ${POLICY_CENTER_API_KEY}" \
  "${POLICY_CENTER_BASE_URL}/api/agent/submissions?status=pending&limit=20"
```

Status values: `pending`, `claimed`, `approved`, `rejected`, `needs_clarification`.

For `needs_clarification` submissions, check the `reviewer_notes` field and help the user address the reviewer's questions.

## Validation Awareness

The system automatically validates submissions. Be aware of these rules to avoid unnecessary warnings:

1. **Upper > Lower**: `si_upper_limit` must exceed `si_lower_limit` (for social insurance). `hf_upper_limit` must exceed `hf_lower_limit` (for housing fund).
2. **Retroactive detection**: If `effective_start` is earlier than `published_at`, the system flags it. Set `is_retroactive: true` to acknowledge this intentionally.
3. **Reasonable bounds**: SI base lower limits typically fall above 2,000 CNY/month, and upper limits above 35,000 may trigger warnings. HF lower limits below 1,000 or upper limits above 40,000 may also be flagged. Values outside these ranges are still accepted but receive closer review.
4. **Change rate**: If the same region has an existing policy and the new values differ by more than 50%, it gets flagged for closer review.
5. **Type-specific validation**: Each policy type has its own validation rules returned in the schema. Check those before submitting.

Warnings don't block submission -- the policy still enters the review queue, but flagged items receive more scrutiny.

## Pre-submission Data Verification

Before submitting, do a quick sanity check:

1. **Encoding check**: Verify all Chinese text (title, coverage_types, special_notes, extracted_text) is readable and not garbled. If you see `?`, `??`, or mojibake, fix the encoding before submitting.
2. **Schema compliance**: Ensure you have all required fields for the target `policy_type` as defined in the schema response from Step 0.
3. **Upper > Lower**: `si_upper_limit > si_lower_limit` for SI; `hf_upper_limit > hf_lower_limit` for HF.
4. **Reasonable range**: SI lower limits above 2,000 and upper limits may exceed 35,000 in larger cities; HF lower limits above 1,000.
5. **Upper/lower ratio**: The upper limit is typically 3-5x the lower limit. A ratio above 5x is unusual.
6. **Year-over-year change**: If you queried the previous year's policy, the annual change is typically 3-10%. Changes above 20% deserve a note in `special_notes`.
7. **Retroactive check**: If `effective_start` < `published_at`, set `is_retroactive: true` and `retroactive_start`.
8. **Date format**: All dates must be `YYYY-MM-DD`.

## Priority Selection

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
| 500 | Server error | Response has `error.code` and `error.message`; wait and retry |

On 500 errors, use exponential backoff: wait 2s, then 4s, then 8s before retrying.

## Batch Submission

When the user wants to submit policies for multiple regions at once:

1. Fetch the schema once (Step 0), reuse for all submissions of the same type
2. Process each region sequentially (not in parallel) to avoid overwhelming the API
3. Check duplicates for each one before submitting
4. Use unique `idempotency_key` values for each submission
5. Ensure each payload is correctly UTF-8 encoded (especially when building payloads in a loop)
6. Report a summary at the end: how many succeeded, how many had warnings, how many were duplicates
