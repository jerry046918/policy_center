# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Policy Center (社保公积金基数政策管理平台) is a data management platform for social insurance and housing fund base policies across China's 31 provinces. It supports multiple policy types (social insurance base, average salary, talent policies, and custom types). External agents submit policy data via Agent REST API (`/api/agent/*`) while a web interface handles human review and administration.

## Development Commands

### Backend (Python/FastAPI)
```bash
# Install dependencies
pip install -r requirements.txt

# Development server
python run.py
# or
uvicorn app.main:app --reload --port 8000

# Run tests
pytest

# Run specific test file
pytest tests/test_main.py -v
```

**Default login**: admin / admin123

### Frontend (React/TypeScript/Vite)
```bash
cd web

# Install dependencies
npm install

# Development server (proxies to backend :8000)
npm run dev

# Build for production
npm run build
```

### Docker
```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f
```

## Architecture

### Single-Container Deployment
- Backend (FastAPI), frontend (React), and SQLite database run in one container
- Frontend is built and served as static files by FastAPI
- Database: SQLite with WAL mode for concurrent reads
- Storage: Local filesystem (`./uploads/`, `./data/`)

### Backend Structure (`app/`)
```
app/
├── api/           # REST API routes (auth, policies, reviews, admin, agent, dashboard)
├── models/        # SQLAlchemy ORM models
├── schemas/       # Pydantic request/response schemas
├── services/      # Business logic layer
├── utils/         # Helpers
├── config.py      # Pydantic Settings configuration
├── database.py    # Async SQLAlchemy setup
└── main.py        # FastAPI app entry point
```

### Frontend Structure (`web/src/`)
```
src/
├── components/    # Shared UI components
├── pages/         # Route pages (Policy, Review, Admin)
├── services/      # API service functions (axios)
├── stores/        # Zustand state management
└── types/         # TypeScript definitions
```

## Key Business Logic

### Policy Status Workflow
- **Agent submissions** → `pending_review` → human review → `active`
- **Human submissions** → `active` directly (no review required)
- Policy Center list only shows `status="active"` policies

### Policy Edit Modes
- **Update current version** (`create_new_version=false`): Minor fixes, no version bump
- **Publish new version** (`create_new_version=true`): Major changes, increments version

### Region Hierarchy
- Uses GB/T 2260 administrative codes (6 digits)
- Provinces (110000, 310000, etc.) → Cities (110100, 440300, etc.)
- Same city with different effective dates = different policy records
- Region data loaded from `data/regions.json` via `/api/admin/regions/init`

### Key Models
- `policies`: Main policy table (title, region_code, effective dates, status, version, policy_type)
- `policy_social_insurance`: Social insurance base limits (si_upper/lower_limit, is_retroactive, coverage_types)
- `policy_housing_fund`: Housing fund base limits (hf_upper/lower_limit, is_retroactive)
- `policy_avg_salary`: Average salary data (avg_salary_total/monthly, statistics_year, growth_rate)
- `policy_talent`: Talent policy data (talent_categories, subsidy_standards, education_requirement)
- `policy_type_definitions`: Registry of all policy types (built-in and dynamic)
- `review_queue`: Pending reviews from agent submissions
- `policy_versions`: Version history with snapshots
- `audit_logs`: Operation audit trail
- `regions`: Administrative regions dictionary
- `agent_credentials`: Agent API key storage

## Agent REST API

External agents interact via REST API at `/api/agent/*`:
- `GET /api/agent/schema`: Get policy type schema and field definitions
- `GET /api/agent/check-duplicate`: Check for duplicate submissions
- `GET /api/agent/policies`: Query published policies
- `POST /api/agent/submit`: Submit new policy data for review
- `GET /api/agent/submissions`: Track submission review status

Authentication: `Authorization: Bearer <api_key>`

## Frontend State Management

- `stores/auth.ts`: JWT token, user info, login/logout
- Other state managed locally in components or via URL params

## API Response Format

```json
{
  "success": true,
  "data": [...],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "total_pages": 5
}
```

## Important Files

- `AGENTS.md`: Agent API reference and submission workflow guide
- `data/regions.json`: Province/city data for initialization
- `.env.example`: Environment configuration template
