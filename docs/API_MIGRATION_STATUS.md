# API Migration Status

This document is the maintainer-facing source of truth for the React/FastAPI migration boundary.

## Rule

**FastAPI is the only long-term API authority for `/api/*`.**

Flask `/api/*` routes are still mounted only as a temporary compatibility layer.

## Runtime snapshot (PR1 baseline)

Current observed route counts:
- **Native FastAPI API paths:** 9
- **Legacy Flask API paths still mounted:** 98

### Native FastAPI API paths
- `/api/health`
- `/api/migration/status`
- `/api/migration/inventory`
- `/api/stats`
- `/api/sources`
- `/api/categories`
- `/api/files`
- `/api/files/detail`
- `/api/files/{file_url:path}/markdown`

### Legacy Flask API paths still mounted (representative groups)

#### Auth / users
- `/api/auth/me`
- `/api/auth/tokens`
- `/api/admin/users`
- `/api/user/me`
- `/api/user/profile`

#### Config / schedule
- `/api/config/sites`
- `/api/config/backend-settings`
- `/api/config/llm-providers`
- `/api/config/ai-models`
- `/api/config/schedule`
- `/api/schedule/status`

#### Tasks / operations
- `/api/collections/run`
- `/api/tasks/active`
- `/api/tasks/history`
- `/api/tasks/log/<task_id>`
- `/api/tasks/stop/<task_id>`

#### Chat / RAG
- `/api/chat/query`
- `/api/chat/conversations`
- `/api/chat/knowledge-bases`
- `/api/rag/knowledge-bases`
- `/api/files/<path:file_url>/chunk-sets`

## Migration policy

### Allowed
- Add new APIs under `ai_actuarial/api/routers/`
- Port existing Flask endpoints into FastAPI routers
- Keep Flask API routes available temporarily when React or legacy pages still depend on them
- Use `GET /api/migration/inventory` to inspect remaining Flask API surface **only in explicitly enabled ops/debug environments** (`FASTAPI_ENABLE_MIGRATION_INVENTORY=1`)

### Not allowed
- Do **not** add new product API routes to `ai_actuarial/web/app.py`
- Do **not** expand Flask API surface as a shortcut for React features
- Do **not** treat mounted Flask `/api/*` routes as the long-term contract

## Practical migration order

### Phase 1 — read surfaces
Status: started
- stats
- sources
- categories
- files listing
- file detail
- markdown read

### Phase 2 — config and task reads
Recommended next:
- schedule status
- active tasks
- task history
- config reads

### Phase 3 — writes and mutations
After read parity:
- task start/stop
- config writes
- site management writes
- markdown writes
- user/admin writes

### Phase 4 — chat and RAG
After contract stabilization:
- chat query
- conversation history
- knowledge base CRUD
- chunk/profile/index operations

## How to verify during development

### Runtime endpoints
- `GET /api/migration/status`
- `GET /api/migration/inventory`

### Tests
- `tests/test_fastapi_entrypoint.py`
- `tests/test_fastapi_read_endpoints.py`

## Completion definition for the migration effort

This migration is only complete when:
1. React product APIs are all served natively by FastAPI
2. No product-critical `/api/*` routes depend on Flask fallback
3. Flask is retained only for legacy HTML pages (or removed entirely later)
