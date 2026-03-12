# Task / KB / Chat Smoke Checklist

Date: 2026-03-11
Branch: `fix/task-history-kb-chat-bugs-20260311`

Scope:
- `tasks` page and task history APIs
- `rag` list/detail pages and KB status APIs
- `chat` page, KB/doc explorer APIs, and document explain route payload

Method:
- Used project virtualenv: `.venv\Scripts\python.exe`
- Used Flask `test_client()` against local app and current local data/config
- For `POST /api/chat/query` document explain smoke, stubbed `LLMClient.generate_response` to avoid external model calls
- This is a route/API smoke pass, not a visual browser click-through

## 1. Tasks

- `[pass]` `GET /tasks` returned `200`
- `[pass]` `GET /api/tasks/history?limit=5` returned `200`
- `[pass]` task history rows include `display_summary`
- `[pass]` `GET /api/tasks/active` returned `200`

Checks:
- task history now exposes backend-owned summary structure
- no active task at smoke time, so stop/progress UX was not re-verified interactively

## 2. Knowledge Bases

- `[pass]` `GET /rag` returned `200`
- `[pass]` `GET /api/rag/knowledge-bases` returned `200` with `3` KBs
- `[pass]` `GET /rag/KB_20260303_0001` returned `200`
- `[pass]` `GET /api/rag/knowledge-bases/KB_20260303_0001` returned `200` with stats and embedding metadata
- `[pass]` `GET /api/rag/knowledge-bases/KB_20260303_0001/composition/status` returned:
  - `has_index = true`
  - `needs_reindex = false`
  - `file_count = 1`
  - `pending_file_count = 0`
- `[pass]` `GET /api/rag/knowledge-bases/KB_20260303_0001/files` returned `sample_status = indexed`
- `[pass]` `GET /api/rag/knowledge-bases/KB_20260303_0001/tasks?limit=10` returned `200`
- `[pass]` KB task history rows include `display_summary`

Checks:
- legacy index state is now visible through composition fallback
- detail file row status and composition status aligned for sampled KB

## 3. Chat

- `[pass]` `GET /chat` returned `200`
- `[pass]` `GET /api/chat/knowledge-bases` returned `200` with `3` KBs and current embedding metadata
- `[pass]` `GET /api/chat/available-documents` returned `200` with `10` documents
- `[pass]` `GET /api/files/<file_url>/markdown` returned `200` for sampled document and markdown content was present

Document explain smoke:
- `[pass]` `POST /api/chat/query` with `document_sources` returned `200`
- `[pass]` response contained `2` citations for `a.pdf` and `b.pdf`
- `[pass]` response contained `2` retrieved blocks
- `[pass]` citations contained `quote`

Live LLM smoke:
- `[pass]` `POST /api/chat/query` with one real local markdown document returned `200`
- `[pass]` live response contained `1` citation and `1` retrieved block
- `[pass]` live citation contained `quote`

Checks:
- document list is reachable
- markdown fetch path for explain-doc is reachable
- multi-document explain payload now preserves per-file citations and quotes

## Residual Risks

- No real browser click-through was performed, so final DOM rendering was validated only indirectly through template/API wiring.
- Only one small live external LLM call was executed in this smoke pass.
- No active background task was created during smoke, so task completion notifications and stop interaction were not re-exercised live.
