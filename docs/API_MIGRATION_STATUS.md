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
- **RAG modes:** standard vector RAG and Agentic RAG both use native FastAPI endpoints.
- **Roadmap surfaces:** Markdown conversion config, typed scheduled tasks, `weekly_summary`, `full_pipeline`, web-listening rule draft/validate/materialize, weekly updates, customer Dashboard, and KB-first Chat are all native FastAPI + React surfaces.

## Product Contract Status

The routed React product shell is expected to use native FastAPI endpoints for:

- Dashboard
  - Customer-facing sources, categories, latest weekly additions from `/api/weekly-updates/latest`, file-detail links, and Agent entry points
  - Backend processing metrics stay in admin/ops surfaces rather than the homepage
- Database
- File Detail / File Preview
- Chat
  - Knowledge-base-first entry point
  - Standard multi-KB mode
  - Agentic single-ready-KB mode
- Tasks
  - Typed scheduled task parameters for backend-supported `catalog`, `url`, `weekly_summary`, and `full_pipeline` params
- Logs
- Knowledge / KB Detail
- Agentic ready_data manifest status/build actions
- Agentic RAG Chat mode, evidence rendering, and tool trace display
- Settings
  - AI/search credentials
  - Markdown conversion config
  - site, schedule, security, and model settings
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
- `/api/config/markdown-conversion`
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
- `/api/collections/run` (`scheduled`, `weekly_summary`, and `full_pipeline` run types)
- `/api/utils/browse-folder`

### Weekly Updates

- `/api/weekly-updates`
- `/api/weekly-updates/latest`

### Web-listening Rules

- `/api/web-listening/rules/draft`
- `/api/web-listening/rules/validate`
- `/api/web-listening/rules/materialize`

### RAG / Knowledge / Chat

- `/api/chunk/profiles`
- `/api/chunk/profiles/{profile_id}`
- `/api/chunk-sets/cleanup`
- `/api/rag/knowledge-bases`
- `/api/rag/knowledge-bases/{kb_id}`
- `/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest`
- `/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build`
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

### Agentic RAG

- `/api/agentic-rag/search/summaries`
- `/api/agentic-rag/search/titles`
- `/api/agentic-rag/search/sections`
- `/api/agentic-rag/search/formula-cards`
- `/api/agentic-rag/search/tables`
- `/api/agentic-rag/search/calculation-terms`
- `/api/agentic-rag/trace/relations`
- `/api/agentic-rag/chat`

Agentic Chat is also exposed through the main chat contract by sending `rag_mode="agentic"` to `/api/chat/query`. That path preserves chat quotas, conversation persistence, and UI evidence rendering. Agentic Chat currently requires exactly one ready KB and rejects direct selected-document context.

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

- `tests/test_fastapi_entrypoint.py`, `tests/test_fastapi_no_flask_runtime.py`, `tests/test_react_fastapi_authority.py`, and `tests/test_fastapi_react_cleanup.py` keep the FastAPI + React product boundary from regressing.
- `tests/test_markdown_conversion_config.py` and related ops endpoint tests cover Markdown conversion config normalization, caching, and Settings read/write behavior.
- `tests/test_web_listening_rule.py` covers rule draft/validate/materialize behavior, YAML coercion, and materialized `full_pipeline` monitor tasks.
- `tests/test_weekly_updates.py` covers weekly summary API/task behavior using `files.first_seen`, including previous-week relative periods.
- `tests/test_task_runtime_full_pipeline.py` covers automatic full-pipeline chaining and failure handling.
- `tests/test_fastapi_chat_endpoints.py` and source-level Chat tests cover KB-first Chat behavior.
- `tests/agentic_rag/test_eval.py` and the CI Agentic eval smoke keep the deterministic ready_data eval path active.

## Migration Policy

### Allowed

- Add product APIs under `ai_actuarial/api/routers/`.
- Use `GET /api/migration/inventory` only in explicit ops/debug environments.
- Keep historical migration notes as dated planning documents when they are useful as project history.

### Not Allowed

- Do not reintroduce `ai_actuarial/web` as a product runtime surface.
- Do not route React pages to non-API backend pages.
- Do not add Replit-specific runtime files to the root project.

## How To Verify During Development

```bash
python -m pytest tests/test_fastapi_entrypoint.py tests/test_fastapi_no_flask_runtime.py tests/test_react_fastapi_authority.py tests/test_fastapi_react_cleanup.py -q
python -m pytest tests/test_markdown_conversion_config.py tests/test_web_listening_rule.py tests/test_weekly_updates.py tests/test_task_runtime_full_pipeline.py -q
python -m pytest tests/test_fastapi_chat_endpoints.py tests/test_tasks_react_source.py -q
npm run build
python -m pytest tests/agentic_rag/test_eval.py -q
python -m ai_actuarial.agentic_rag.eval --mode agentic --cases eval/agentic_cases.jsonl --output-dir eval/fixtures/agentic_ready_data --profile formula --json
```
