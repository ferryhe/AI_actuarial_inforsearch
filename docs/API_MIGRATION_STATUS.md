# API Migration Status

This document is the maintainer-facing source of truth for the React/FastAPI boundary.

## Rule

**FastAPI is the only product API authority for `/api/*`.**

The legacy server-rendered runtime has been retired from the active tree. React pages must call native FastAPI routes only.

## Runtime Snapshot

- **Runtime mode:** FastAPI-only API + React SPA
- **Legacy web runtime:** absent from the active source tree
- **Legacy `/api/*` fallback:** retired
- **Unmatched `/api/*`:** FastAPI returns `410`
- **Migration inventory:** available only when `FASTAPI_ENABLE_MIGRATION_INVENTORY=1`

## Product Contract Status

The routed React product shell is expected to use native FastAPI endpoints for:

- Dashboard
- Database
- File Detail / File Preview
- Chat
- Tasks
- Logs
- Knowledge / KB Detail
- Settings
- Login / Register / Profile / Users

## Representative Native FastAPI Surface

### Core Catalog / File Routes

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

### Tasks / Config / Operations

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
- `/api/config/backend-settings`
- `/api/config/ai-models`
- `/api/config/llm-providers`
- `/api/config/categories`
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

### RAG / Knowledge / Chat

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

### Auth / User / Admin

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

## Enforcement

- `tests/test_react_fastapi_authority.py` scans the routed React shell and fails if any referenced endpoint is not native FastAPI.
- `tests/test_fastapi_no_flask_runtime.py` proves `create_app()` starts without a legacy web package.
- `tests/test_fastapi_react_cleanup.py` keeps the cleaned FastAPI + React project boundary from regressing.

## Migration Policy

### Allowed

- Add product APIs under `ai_actuarial/api/routers/`.
- Use `GET /api/migration/inventory` only in explicit ops/debug environments.
- Keep historical migration notes under `docs/archive` or dated planning documents when they are useful as project history.

### Not Allowed

- Do not reintroduce `ai_actuarial/web` as a product runtime surface.
- Do not route React pages to non-API backend pages.
- Do not add Replit-specific runtime files to the root project.

## How To Verify During Development

```bash
python -m pytest tests/test_fastapi_entrypoint.py tests/test_fastapi_no_flask_runtime.py tests/test_react_fastapi_authority.py tests/test_fastapi_react_cleanup.py -q
npm run build
```
