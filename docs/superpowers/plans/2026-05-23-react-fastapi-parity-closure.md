# React FastAPI Parity Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining Flask-to-React/FastAPI parity gaps identified after PR #114, with source/API coverage for the user-visible controls.

**Architecture:** Keep the React UI as the source of truth for workflow orchestration and use existing FastAPI endpoints instead of reintroducing Flask concepts. Prefer small source-level regression tests for UI contracts and focused API tests where URL or payload contracts change.

**Tech Stack:** React 19 + Wouter + Vite, FastAPI routers/services, pytest source/API tests, existing `/api/config`, `/api/rag`, `/api/files`, `/api/tasks`, and `/api/chat` contracts.

---

## File Structure

- Modify `client/src/pages/Settings.tsx`: preserve `ai_keywords`, expose provider env import/model refresh/re-encrypt actions, and improve search credential maintenance.
- Modify `client/src/pages/tasks/RagIndexForm.tsx`: let RAG indexing target explicit file URLs in addition to whole KBs.
- Modify `client/src/pages/tasks/CatalogForm.tsx`, `MarkdownForm.tsx`, `ChunkForm.tsx`: replace free-text category datalist inputs with backend-backed selects and keep stats in sync.
- Modify `client/src/pages/Tasks.tsx`: refresh history when active tasks complete, confirm stops, and expose global logs.
- Modify `client/src/pages/FileDetail.tsx`: add AI Explain, render markdown as structured HTML, enforce permissions, and expose profile/KB controls for chunk generation.
- Modify `client/src/pages/FilePreview.tsx`: pass download permission into non-preview fallback.
- Modify `client/src/pages/Chat.tsx`: normalize citation links to React routes.
- Modify `ai_actuarial/api/services/chat.py`: emit React file detail/preview URLs for retrieved block citations.
- Modify `tests/test_*_react_source.py` and focused FastAPI tests: lock the contracts above.
- Modify `.hermes/project-status.md`: record final state and remaining decisions.

## Task 1: Settings Category Keyword Contract

**Files:**
- Modify: `client/src/pages/Settings.tsx`
- Modify: `tests/test_settings_react_source.py`
- Modify: `tests/test_fastapi_ops_write_endpoints.py`

- [ ] Add source test asserting `CategoriesTab` reads `res.ai_keywords || res.ai_filter_keywords || []`.
- [ ] Add source test asserting category save posts both `ai_filter_keywords: aiFilterKw` and `ai_keywords: aiFilterKw`.
- [ ] Update backend write test to post `ai_keywords` and assert it survives response and YAML write.
- [ ] Implement the minimal `Settings.tsx` change.
- [ ] Run `python -m pytest tests/test_settings_react_source.py tests/test_fastapi_ops_write_endpoints.py::test_categories_and_ai_models_write_roundtrip_is_native_fastapi -q`.

## Task 2: Task Category Selects And RAG File URLs

**Files:**
- Modify: `client/src/pages/tasks/CatalogForm.tsx`
- Modify: `client/src/pages/tasks/MarkdownForm.tsx`
- Modify: `client/src/pages/tasks/ChunkForm.tsx`
- Modify: `client/src/pages/tasks/RagIndexForm.tsx`
- Modify: `client/src/hooks/use-i18n.ts`
- Modify: `tests/test_tasks_react_source.py`

- [ ] Add source tests that `CatalogForm`, `MarkdownForm`, and `ChunkForm` no longer render `<datalist>` and use `SelectField` category controls.
- [ ] Add source test that `RagIndexForm` posts `file_urls` parsed from a multiline input.
- [ ] Implement `categoryOptions` with an empty disabled choice and call `loadStats(value)` when category changes.
- [ ] Add `textarea` in `RagIndexForm` with one URL per line and include `file_urls` only when non-empty.
- [ ] Run `python -m pytest tests/test_tasks_react_source.py -q`.

## Task 3: Task UX Completion, Stop, And Logs

**Files:**
- Modify: `client/src/pages/Tasks.tsx`
- Modify: `tests/test_tasks_react_source.py`

- [ ] Add source test for `previousActiveTaskIdsRef`, `fetchHistory()`, and completion notice when a task disappears from active list.
- [ ] Add source test for `window.confirm(t("tasks.confirm_stop"))` before `/api/tasks/stop`.
- [ ] Add source test for `/api/logs/global` and a `button-global-logs` control.
- [ ] Implement active-task transition detection in `fetchTasks`.
- [ ] Implement stop confirmation and user-visible success/error messages.
- [ ] Add a global logs button that opens the existing log modal with a synthetic task name.
- [ ] Run `python -m pytest tests/test_tasks_react_source.py -q`.

## Task 4: File Detail And Preview Parity

**Files:**
- Modify: `client/src/pages/FileDetail.tsx`
- Modify: `client/src/pages/FilePreview.tsx`
- Modify: `client/src/hooks/use-i18n.ts`
- Modify: `tests/test_file_detail_react_source.py`

- [ ] Add source test for FileDetail AI Explain navigation state containing `document_content`, `file_url`, `filename`, `title`, `category`, and `keywords`.
- [ ] Add source test for markdown rendering via a local `MarkdownRenderer` rather than a raw-only `<pre>`.
- [ ] Add source test for permission gating using `permissions.includes("files.download")`, `files.delete`, `catalog.write`, `markdown.write`, and `rag.write`.
- [ ] Add source test for `OriginalPane` receiving `canDownload={canDownload}`.
- [ ] Implement FileDetail AI Explain using already loaded markdown content and Wouter state.
- [ ] Implement a small markdown renderer for headings, paragraphs, lists, code fences, blockquotes, and links without adding a dependency.
- [ ] Pass `canDownload` into `OriginalPane`.
- [ ] Run `python -m pytest tests/test_file_detail_react_source.py -q`.

## Task 5: Chat Citation Routes

**Files:**
- Modify: `ai_actuarial/api/services/chat.py`
- Modify: `client/src/pages/Chat.tsx`
- Modify: `tests/test_chat_react_source.py`
- Modify: `tests/test_fastapi_chat_endpoints.py`

- [ ] Add source/API tests that citations use `/file-detail?url=` and `/file-preview?file_url=` instead of `/file/` and `/file_preview`.
- [ ] Update `_build_file_links()` to emit React routes and preserve safe `from=/chat`.
- [ ] Update Chat citation fallback to use `buildFileDetailPath`/`buildFilePreviewPath` when only `file_url` is present.
- [ ] Run `python -m pytest tests/test_chat_react_source.py tests/test_fastapi_chat_endpoints.py::test_fastapi_chat_conversation_and_catalog_surfaces_work -q`.

## Task 6: Settings Ops Maintenance

**Files:**
- Modify: `client/src/pages/Settings.tsx`
- Modify: `tests/test_settings_react_source.py`

- [ ] Add source test for provider env import button posting `/api/config/provider-credentials/import-env`.
- [ ] Add source test for model catalog refresh using `/api/config/model-catalog?refresh=true`.
- [ ] Add source test for credential re-encryption controls posting `/api/config/provider-credentials/re-encrypt`.
- [ ] Add source test for search credential deletion using `apiDelete("/api/config/provider-credentials/${providerId}?category=search")`.
- [ ] Implement compact maintenance controls in AI/Search tabs.
- [ ] Run `python -m pytest tests/test_settings_react_source.py -q`.

## Task 7: Verification And PR

**Files:**
- Modify: `.hermes/project-status.md`

- [ ] Run focused pytest suite for touched source/API tests.
- [ ] Run `npm.cmd run build -- --outDir C:/tmp/ai-actuarial-parity-closure-build`.
- [ ] Run a local UI smoke for `/settings`, `/tasks`, `/database`, `/chat`, and one file detail/preview route if seed data is available.
- [ ] Run `git diff --check`.
- [ ] Run the mandatory Codex CLI review gate; if blocked by `codex.exe Access is denied`, record it.
- [ ] Commit, push, create a PR, then schedule a 15-minute follow-up PR check.

## Self-Review

- Spec coverage: P0 category keyword preservation, task/KB category controls, RAG index file URLs, file detail explain, chat citation routes, FilePreview download fallback, task completion/log UX, and Settings ops maintenance all have tasks.
- Known decisions: old `/collection/url` and `/collection/file` deep links plus chunk `version`/`chunk_model` restoration are recorded as decisions because no current FastAPI contract requires them.
- Placeholder scan: no task uses TBD/TODO language; every task has concrete files and commands.
