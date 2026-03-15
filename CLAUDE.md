# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Policy Center (社保公积金基数政策管理平台) is an MCP-First data infrastructure platform for managing social insurance and housing fund base policies across China's 31 provinces. External agents submit policy data via MCP protocol while a web interface handles human review and administration.

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
├── utils/         # Helpers (cache, scheduler)
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
- `policies`: Main policy table (title, region_code, effective dates, status, version)
- `policy_social_insurance`: SI/HF limits (si_upper/lower_limit, hf_upper/lower_limit, is_retroactive)
- `review_queue`: Pending reviews from agent submissions
- `policy_versions`: Version history with snapshots
- `regions`: Administrative regions dictionary

## MCP Interface

**Note**: MCP server implementation is planned in `app/mcp/` but not yet implemented.

External agents interact via MCP tools:
- `submit_policy_for_review`: Submit new policy data
- `query_policies`: Query published policies
- `check_duplicate`: Check for duplicate submissions
- `get_policy_schema`: Get validation schema

Authentication: `Authorization: Bearer <api_key>` + `X-Agent-ID: <agent_id>`

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
  "page_size": 20
}
```

## Important Files

- `technical_spec.md`: Complete system specification
- `data/regions.json`: Province/city data for initialization
- `.env.example`: Environment configuration template
