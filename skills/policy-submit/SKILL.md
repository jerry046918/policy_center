---
name: policy-submit
description: Collect and submit policy data (社保基数/公积金基数/社平工资/人才政策等) to the Policy Center system via its Agent REST API. Use this skill whenever the user wants to submit (提交), add (新增), update (更新), collect (采集), or sync (录入) policy data for any Chinese province or city -- including vague requests like "帮我查下北京最新社保基数然后提交", "submit Beijing 2025 housing fund base", or "把这个文件里的社保数据录入系统". Also applies when the user provides a government policy document URL or text for extraction, wants to batch-ingest policies for multiple regions, asks to check/track submission review status (审核状态), or asks "这个政策有没有提交过". This skill covers the full workflow: schema fetch, data collection via web search, duplicate check, submission, and status tracking. It is specifically for operating on policy DATA through the Agent API -- not for developing, debugging, deploying, or modifying the Policy Center application code itself.
---

# Policy Submission Skill

This skill enables you to collect policy data for Chinese provinces and cities and submit them to the Policy Center system through its Agent REST API. The system supports **multiple policy types** (社保基数, 公积金基数, 社平工资, 人才政策, and custom types defined by administrators). Social insurance and housing fund are **separate** policy types -- submit them independently. Submissions enter a human review queue; once approved they become active policies.

## Prerequisites

Before making any API calls, you must confirm two values with the user:

- `POLICY_CENTER_BASE_URL` -- the base URL of the Policy Center service (e.g. `http://localhost:8000`)
- `POLICY_CENTER_API_KEY` -- an Agent API key issued by a Policy Center admin

**Do not proceed until both values are confirmed.** Follow this flow:

1. Check whether the environment variables `POLICY_CENTER_BASE_URL` and `POLICY_CENTER_API_KEY` are already set.
2. If both are set, confirm them with the user before making any requests:
   > "I'll use `<BASE_URL>` with the configured API key. Is that correct?"
3. If either is missing, **ask the user to provide them explicitly**:
   > "To submit policies to Policy Center, I need two things:
   > 1. The base URL of your Policy Center instance (e.g. `http://your-server:8000`)
   > 2. An Agent API key (an admin can generate one under Admin > API Keys)
   >
   > Please provide both before we proceed."
4. Do not assume or default to any URL. Do not proceed with the demo environment unless the user explicitly asks to use it.

All API requests require the header `Authorization: Bearer <API_KEY>`.

### Demo Environment (only when explicitly requested)

If the user explicitly says they want to test with the demo instance, use:

- **Base URL**: `https://uhawkrwrpffr.ap-northeast-1.clawcloudrun.com`
- **Agent API Key**: visible in the demo admin UI under Admin > API Keys (login: `admin` / `admin123`)

```bash
export POLICY_CENTER_BASE_URL="https://uhawkrwrpffr.ap-northeast-1.clawcloudrun.com"
export POLICY_CENTER_API_KEY="<demo-api-key-from-admin>"
```

Note: the demo instance resets all data daily at 03:00 Beijing time (region data and policy type definitions are preserved). Do not use the demo environment for real policy submissions.

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
# Get schema for a specific type
curl -s -H "Authorization: Bearer ${POLICY_CENTER_API_KEY}" \
  "${POLICY_CENTER_BASE_URL}/api/agent/schema?policy_type=social_insurance&include_examples=true"

# Discover all available types (built-in + any admin-created custom types):
curl -s -H "Authorization: Bearer ${POLICY_CENTER_API_KEY}" \
  "${POLICY_CENTER_BASE_URL}/api/agent/schema?policy_type=_list_all"
```

The response is `{ "success": true, "schema": { ... } }`. Inside `schema`:
- `common_fields` -- fields shared by ALL types: `title`, `region_code`, `published_at`, `effective_start`, `effective_end`
- `type_specific_fields` -- field descriptors unique to this type (see below for how to read them)
- `validation_rules` -- human-readable list of checks the system runs
- `examples` -- ready-to-use example `structured_data` + `raw_content` (use this as your payload template)
- `available_types` -- list of every registered type with `type_code`, `type_name`, `description`

#### How to read `type_specific_fields` and build your payload

Each entry in `type_specific_fields` is a field descriptor object. The attributes that matter for submission:

| Attribute | Meaning |
|-----------|---------|
| `required: true` | Must be present in `structured_data`; omitting it generates a validation warning |
| `type` | Expected value type: `"integer"`, `"number"`, `"string"`, `"boolean"`, `"array"`, `"object"` |
| `gt` / `ge` | Value must be greater than / greater-than-or-equal-to this number |
| `lt` / `le` | Value must be less than / less-than-or-equal-to this number |
| `max_length` | String must not exceed this character count |
| `description` | Chinese label for the field (appears in reviewer UI and warning messages) |
| `unit`, `format`, `default`, `items`, `enum` | Advisory / display only; not enforced at submission time |

**The fastest way to build a correct payload**: look at `schema.examples[0].structured_data`. It is a complete, ready-to-copy example with all type-specific fields filled in. Use it as your template and replace the values with the real data you collected.

#### Workflow for any policy type (built-in or custom)

```
1. GET /api/agent/schema?policy_type=<type_code>&include_examples=true
2. Read schema.examples[0].structured_data  ← use as payload template
3. Read schema.type_specific_fields         ← verify which fields are required
4. Read schema.validation_rules             ← know what will trigger warnings
5. Fill in the template with real data, then proceed to Step 1 (data collection)
```

**Built-in policy types:**

| type_code | Name | Key Fields |
|-----------|------|------------|
| `social_insurance` | 社保基数 | si_upper_limit, si_lower_limit, is_retroactive, coverage_types |
| `housing_fund` | 公积金基数 | hf_upper_limit, hf_lower_limit, is_retroactive |
| `avg_salary` | 社会平均工资 | avg_salary_total, avg_salary_monthly, statistics_year, growth_rate |
| `talent_policy` | 人才政策 | talent_categories, certification_requirements, required_documents, subsidy_standards, eligibility_summary, age_limit, education_requirement, service_years_required, application_channel |

Administrators may add custom types at any time. Always check `_list_all` to discover the latest types.

#### Submitting custom (admin-defined) types

The submission body is identical in structure to built-in types. The only difference is that you learn the field names from `type_specific_fields` rather than from this document.

Put all type-specific fields **flat inside `structured_data`**, alongside the common fields:

```json
{
  "policy_type": "<custom_type_code>",
  "submit_type": "new",
  "structured_data": {
    "title": "...",
    "region_code": "110000",
    "published_at": "2024-06-20",
    "effective_start": "2024-07-01",
    "<field_from_schema>": <value>,
    "<another_field>": <value>
  },
  "raw_content": { "sources": [{ "url": "...", "extracted_text": "..." }] }
}
```

The backend accepts any extra keys in `structured_data` and filters them down to the fields declared in the type's `field_schema`. This flat placement works for all types -- both built-in and custom.

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

After locating the source document, use `schema.examples[0].structured_data` (from Step 0) as your field template.

For each field in `schema.type_specific_fields`, the descriptor includes a `search_keywords` array — these are the Chinese terms to look for in the government document to find the value for that field. For example:

```
type_specific_fields.si_upper_limit.search_keywords
  → ["社保基数上限", "缴费工资基数上限", "社会保险缴费基数上限"]
```

Use these keywords directly as your extraction hints. For custom admin-defined types, the admin should have filled in `search_keywords` when creating the type — if the field is missing keywords, fall back to `description` as a search hint.

**Common fields (all types) — document location hints:**

| Field | Where to find it |
|-------|-----------------|
| `title` | The full heading / 通知标题 of the document |
| `published_at` | 发布日期 / 印发日期 / 落款日期 |
| `effective_start` | 自...起施行 / ...起执行 / 执行日期 |

**Important**: Social insurance and housing fund are **separate policy types**. If one government document contains both, submit them as two separate policies (`policy_type=social_insurance` and `policy_type=housing_fund`).

**Additional parsing tips:**

- **Retroactive policies (追溯生效)**: very common — a policy published in Sep 2024 may state it takes effect from Jul 1, 2024. Clues: `published_at > effective_start`; keywords 追溯执行 / 补缴 / 从...起补缴差额. When detected: set `is_retroactive: true`, `retroactive_start` = earliest applicable date, `priority: "urgent"`.
- **Document number** (文号): format like 京人社发〔2024〕12号 — use Chinese brackets 〔〕.
- **Upper limit derivation**: SI/HF upper limit is typically 300% of the local average monthly salary; lower limit is 60%.


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

The `policy_type` field determines which type-specific fields go in `structured_data`. Use `schema.examples[0]` from Step 0 as your payload template, then fill in the real values.

**Note on `avg_salary_monthly`**: omit it and the system auto-computes `round(avg_salary_total / 12)`. Only provide it explicitly if the official document states a different monthly figure.

#### Full example: retroactive social_insurance

This is the most complex scenario and covers all the fields you'll encounter. A very common case — a policy is published months after it took effect, requiring employers to back-pay the difference.

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
      "sources": [{
        "title": "广州市人力资源和社会保障局通知",
        "doc_number": "穗人社发〔2024〕XX号",
        "url": "https://rsj.gz.gov.cn/actual-url-from-search",
        "extracted_text": "经市政府批准，我市2024年度社保缴费基数上限为27501元，下限为5500元，自2024年7月1日起执行..."
      }]
    },
    "priority": "urgent"
  }'
```

For a **non-retroactive** submission, set `is_retroactive: false`, remove `retroactive_start`, and use `priority: "normal"` or `"high"`.

#### Updating an existing policy

When `check-duplicate` returns `is_duplicate: true`, submit as an update:

```json
{
  "idempotency_key": "update-110000-si-2024-07-01-fix1",
  "policy_type": "social_insurance",
  "submit_type": "update",
  "existing_policy_id": "<uuid-from-duplicate-check>",
  "change_description": "修正社保基数下限，原6821更正为6921",
  "structured_data": { "...all fields with corrected values..." },
  "raw_content": { "..." },
  "priority": "normal"
}
```


### Step 5: Verify the submission

Check the response:

```json
{
  "success": true,
  "review_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "pending_review",
  "policy_id": "a1b2c3d4-...",
  "policy_type": "social_insurance",
  "warnings": [],
  "estimated_review_time": "24h",
  "message": null
}
```

- If `success` is true, report the `review_id` and `estimated_review_time` to the user
- If there are `warnings`, report them -- they don't block the submission but the user should be aware
- If `status` is `"already_submitted"`, the same `idempotency_key` was already processed; the `message` field (e.g. `"该政策已提交，请勿重复提交"`) explains this. Report the existing `review_id` to the user and do not resubmit.

### Step 6: Track submission status (optional)

```bash
curl -s -H "Authorization: Bearer ${POLICY_CENTER_API_KEY}" \
  "${POLICY_CENTER_BASE_URL}/api/agent/submissions?status=pending&limit=20"
```

Status values: `pending`, `claimed`, `released`, `approved`, `rejected`, `needs_clarification`.

- `released` means a reviewer claimed the submission but released it back to the queue without a decision.

For `needs_clarification` submissions, check the `reviewer_notes` field and help the user address the reviewer's questions.

## Pre-submission Checklist

Run through this before calling the submit endpoint. All warnings are non-blocking — the submission still enters the review queue — but flagged items receive closer scrutiny from reviewers.

**Encoding**
- All Chinese text (title, special_notes, extracted_text) is readable and not garbled (`?` or mojibake → fix encoding first)
- `Content-Type: application/json; charset=utf-8` is set

**Fields**
- All `required: true` fields from `schema.type_specific_fields` are present
- All dates are `YYYY-MM-DD`
- If `effective_start` < `published_at`: set `is_retroactive: true` and `retroactive_start`

**Value sanity (triggers warnings if violated)**
- `si_upper_limit > si_lower_limit`; `hf_upper_limit > hf_lower_limit`
- SI lower limit > 2,000 CNY/month; HF lower limit > 1,000 CNY/month
- Upper/lower ratio typically 3–5×; above 5× is unusual
- Year-over-year change typically 3–10%; above 20% add a note in `special_notes`
- Change rate > 10% → `涨幅较高` tag; > 20% → `涨幅异常` (both non-blocking)
- Custom type fields: check `schema.validation_rules` for type-specific bounds

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
| 500 | Server error | Response has `error.code`, `error.message`, and `request_id`; wait and retry |

On 500 errors, use exponential backoff: wait 2s, then 4s, then 8s before retrying.

**Common 400 causes to watch for:**

- `"不支持的政策类型: '...'"` -- the `policy_type` value is not recognized; call `GET /api/agent/schema?policy_type=_list_all` to get valid values.
- `"submit_type 必须是 'new' 或 'update'"` -- only those two values are accepted; anything else is rejected.
- `"原政策 {id} 不存在"` -- when using `submit_type: "update"`, the `existing_policy_id` was not found (policy may have been deleted between the duplicate check and the submit). Re-run the duplicate check and use the refreshed `existing_policy_id`.

**Duplicate-check blind spot**: `GET /api/agent/check-duplicate` only considers policies with `status: "active"`. A submission currently sitting in the review queue (pending approval) is invisible to this check. This means two agents could both pass the duplicate check and both submit the same policy simultaneously. Reviewers will catch this, but be aware that `is_duplicate: false` does not guarantee no pending submission already exists for the same region/type/date.

## Batch Submission

When the user wants to submit policies for multiple regions at once:

1. Fetch the schema once (Step 0), reuse for all submissions of the same type
2. Process each region sequentially rather than in parallel -- this makes it easier to detect and handle per-region errors (duplicate hits, 400 validation failures) without racing conditions on the SQLite backend
3. Check duplicates for each one before submitting
4. Use unique `idempotency_key` values for each submission
5. Ensure each payload is correctly UTF-8 encoded (especially when building payloads in a loop)
6. Report a summary at the end: how many succeeded, how many had warnings, how many were duplicates
