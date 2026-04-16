# API Migration Status

This document is the maintainer-facing source of truth for the React/FastAPI migration boundary.

## Rule

**FastAPI is the only product API authority for `/api/*`.**

The mounted Flask app is now a historical compatibility payload, not the backend contract for the React shell.

## Runtime snapshot (PR7)

Current observed route counts:
- **Native FastAPI API paths:** 79
- **Legacy Flask API paths still present inside the mounted Flask app:** 98
- **Flask-only API signatures still not ported to FastAPI:** 18
- **Legacy `/api/*` fallback through FastAPI gateway:** blocked by default

### Product contract status

The routed React product shell is expected to use **only native FastAPI endpoints** for:
- Dashboard
- Database
- File Detail / File Preview
- Chat
- Tasks
- Logs
- Knowledge / KB Detail
- Settings (native read-only shell)
- Login / Register / Profile / Users

CI now enforces this boundary with a source-level test over the routed React shell.

## Native FastAPI API surface

Representative native groups now include:

### Core catalog / file routes
- `/api/stats`
- `/api/sources`
- `/api/categories`
- `/api/files`
- `/api/files/detail`
- `/api/files/{file_url:path}/markdown`
- `/api/files/{file_url:path}/chunk-sets`
- `/api/files/{file_url:path}/chunk-sets/generate`
- `/api/download`
- `/api/export`

### Tasks / config / operations
- `/api/config/sites`
- `/api/config/sites/add`
- `/api/config/sites/update`
- `/api/config/sites/delete`
- `/api/config/sites/import`
- `/api/config/sites/export`
- `/api/config/sites/sample`
- `/api/config/backups`
- `/api/config/backups/restore`
- `/api/config/backups/delete`
- `/api/config/search-engines`
- `/api/config/backend-settings` (read)
- `/api/config/ai-models` (read)
- `/api/config/llm-providers` (read)
- `/api/config/categories` (read)
- `/api/schedule/status`
- `/api/schedule/reinit`
- `/api/scheduled-tasks`
- `/api/scheduled-tasks/add`
- `/api/scheduled-tasks/update`
- `/api/scheduled-tasks/delete`
- `/api/tasks/active`
- `/api/tasks/history`
- `/api/tasks/log/{task_id}`
- `/api/tasks/stop/{task_id}`
- `/api/collections/run`
- `/api/utils/browse-folder`

### RAG / knowledge / chat
- `/api/chunk/profiles`
- `/api/chunk/profiles/{profile_id}`
- `/api/chunk-sets/cleanup`
- `/api/rag/knowledge-bases`
- `/api/rag/knowledge-bases/{kb_id}`
- `/api/rag/knowledge-bases/{kb_id}/stats`
- `/api/rag/knowledge-bases/{kb_id}/files`
- `/api/rag/knowledge-bases/{kb_id}/files/{file_url:path}`
- `/api/rag/knowledge-bases/{kb_id}/files/pending`
- `/api/rag/knowledge-bases/{kb_id}/bindings`
- `/api/rag/knowledge-bases/{kb_id}/categories`
- `/api/rag/knowledge-bases/{kb_id}/index`
- `/api/rag/files/preview`
- `/api/rag/files/selectable`
- `/api/rag/categories/unmapped`
- `/api/chat/conversations`
- `/api/chat/conversations/{conversation_id}`
- `/api/chat/knowledge-bases`
- `/api/chat/available-documents`
- `/api/chat/query`

### Auth / user / admin
- `/api/auth/me`
- `/api/auth/login`
- `/api/auth/register`
- `/api/auth/logout`
- `/api/auth/tokens`
- `/api/auth/tokens/{token_id}/revoke`
- `/api/user/me`
- `/api/user/profile`
- `/api/admin/users`
- `/api/admin/users/{user_id}/role`
- `/api/admin/users/{user_id}/enable`
- `/api/admin/users/{user_id}/disable`
- `/api/admin/users/{user_id}/reset-quota`
- `/api/admin/users/{user_id}/activity`

## Remaining Flask-only `/api/*` signatures

These signatures still exist only in `ai_actuarial/web/*` and are no longer part of the React product contract:

- `DELETE /api/config/llm-providers/<provider>`
- `GET /api/collections/history`
- `GET /api/config/search-defaults`
- `GET /api/files/<path:file_url>/indexes`
- `GET /api/logs/global`
- `GET /api/rag/knowledge-bases/<kb_id>/composition/status`
- `GET /api/rag/knowledge-bases/<kb_id>/tasks`
- `GET /api/user/quota`
- `POST /api/admin/users/<int:target_user_id>/active`
- `POST /api/chat/summarize-document`
- `POST /api/config/ai-models`
- `POST /api/config/backend-settings`
- `POST /api/config/categories`
- `POST /api/config/llm-providers`
- `POST /api/config/schedule`
- `POST /api/rag/categories/stats`
- `POST /api/rag/knowledge-bases/<kb_id>/index/build`
- `POST /api/rag/task-metadata`

## Enforcement

### Runtime guard

By default, unmatched `/api/*` requests do **not** fall through to Flask anymore.

- Default: FastAPI returns `410` for unported `/api/*`
- Temporary override for debugging only: `FASTAPI_ALLOW_LEGACY_API_FALLBACK=1`

### CI guardrails

- `tests/test_flask_api_boundary.py`
  - freezes the remaining Flask-only API baseline
  - fails if new Flask-only `/api/*` signatures appear
- `tests/test_react_fastapi_authority.py`
  - scans the routed React product shell
  - fails if any referenced endpoint is not native FastAPI

## Migration policy

### Allowed
- Add new product APIs under `ai_actuarial/api/routers/`
- Port remaining historical Flask-only signatures into FastAPI deliberately
- Use `GET /api/migration/inventory` in explicit ops/debug environments only (`FASTAPI_ENABLE_MIGRATION_INVENTORY=1`)
- Temporarily re-enable Flask `/api/*` fallback only for debugging (`FASTAPI_ALLOW_LEGACY_API_FALLBACK=1`)

### Not allowed
- Do **not** add new product API routes to `ai_actuarial/web/app.py`
- Do **not** point routed React pages at Flask-only endpoints
- Do **not** treat mounted Flask `/api/*` routes as a supported backend contract

## How to verify during development

### Runtime endpoints
- `GET /api/migration/status`
- `GET /api/migration/inventory` (disabled unless `FASTAPI_ENABLE_MIGRATION_INVENTORY=1`)

### Tests
- `tests/test_fastapi_entrypoint.py`
- `tests/test_flask_api_boundary.py`
- `tests/test_react_fastapi_authority.py`

## Completion definition

This migration is only complete when:
1. Routed React product APIs are all served natively by FastAPI
2. Remaining Flask-only `/api/*` signatures are either ported or intentionally retired
3. Flask is retained only for legacy HTML pages or removed entirely later
