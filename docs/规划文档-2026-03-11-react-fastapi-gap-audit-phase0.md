# React / FastAPI Gap Audit Phase 0

Date: 2026-03-11
Branch: `review/fastapi-ui-gap-20260311`

## Scope

This audit focused on four questions:

1. Why active tasks appeared impossible to stop.
2. Whether current React buttons have valid code paths.
3. Which backend capabilities still do not line up cleanly with the frontend.
4. How much FastAPI migration work remains after the recent read-endpoint work.

## Current Verification

- `npm run build`: passed
- targeted backend regression: passed
- full backend regression: `435 passed`
- React button/test-id audit:
  - `button/tab/toggle` controls found across page components: `101`
- React API coverage audit:
  - native FastAPI endpoints used by React: `5`
  - legacy Flask endpoints used by React: `70`
  - missing React API paths after this audit: `0`

## Findings

### 1. Task stop support was inconsistent

Before this audit, stop requests were wired through `_active_tasks[task_id]["stop_requested"]`,
but only some task types actually checked that flag while running.

Observed/confirmed behavior:

- already stop-aware:
  - crawler-backed tasks (`url`, `search`, `scheduled`, `quick_check`)
  - `markdown_conversion`
  - `chunk_generation`
- missing stop propagation before this audit:
  - `catalog`
  - `rag_indexing`
  - `kb_index_build`
- still not stop-aware after this audit:
  - local `file` import

### 2. One frontend button was genuinely broken

The Knowledge page deletes chunk profiles via:

- `DELETE /api/chunk/profiles/{profile_id}`

But the backend previously exposed only:

- `GET /api/chunk/profiles`
- `POST /api/chunk/profiles`

That meant the chunk-profile delete button had no matching backend route.

### 3. FastAPI migration is still in an early phase

React is no longer blocked by missing API paths, but almost all non-read behavior still runs
through legacy Flask.

Native FastAPI endpoints currently cover only:

- `/api/stats`
- `/api/sources`
- `/api/categories`
- `/api/files`
- `/api/files/detail`
- `/api/files/{file_url}/markdown`
- plus gateway/meta endpoints such as `/api/health` and `/api/migration/status`

High-click pages still mostly depend on Flask:

- `Tasks`
- `Settings`
- `Knowledge`
- `KBDetail`
- `Chat`
- `Logs`
- `Users`
- `Profile`
- write actions in `FileDetail`

## Changes Made In This Audit

### Task stop improvements

- catalog task runners now accept and honor `stop_check`
- RAG indexing pipeline now accepts and honors `stop_check`
- stop requests now update active-task activity text to `Stop requested`
- stopped RAG index runs no longer record a misleading ready index version

### Button-path fix

- added backend support for `DELETE /api/chunk/profiles/{profile_id}`
- added storage-layer deletion support for chunk profiles
- added regression coverage for chunk-profile deletion

### Regression coverage

- added tests for chunk-profile delete API
- added tests covering catalog immediate-stop handling
- added tests covering RAG indexing stop behavior

## Remaining Work Plan

### Phase 1: finish task-stop semantics

- add stop support to local file import tasks
- add explicit frontend `stopping` UX state instead of only changing activity text
- add API-level tests for `/api/tasks/stop/{id}` across representative task types

### Phase 2: migrate task center endpoints to FastAPI

Priority:
- `/api/tasks/active`
- `/api/tasks/history`
- `/api/tasks/log/{task_id}`
- `/api/tasks/stop/{task_id}`
- `/api/collections/run`
- task stats endpoints used by `Tasks.tsx`

Reason:
- highest click density
- directly related to the user-visible “task cannot stop” problem
- removes reliance on Flask for the operational center of the app

### Phase 3: migrate RAG management endpoints

Priority:
- `/api/chunk/profiles`
- `/api/files/{file_url}/chunk-sets`
- `/api/files/{file_url}/chunk-sets/generate`
- `/api/rag/knowledge-bases*`
- `/api/chunk-sets/cleanup`

Reason:
- powers `Knowledge`, `KBDetail`, and part of `FileDetail`
- currently one of the heaviest frontend/backend interaction areas

### Phase 4: migrate settings/config write APIs

Priority:
- `/api/config/llm-providers*`
- `/api/config/ai-models`
- `/api/config/backend-settings`
- `/api/config/categories`
- `/api/config/search-engines`
- `/api/auth/tokens*`

Reason:
- central admin workflows still sit on Flask
- this is also the dependency root for task-option forms

### Phase 5: migrate chat and admin surfaces

- `/api/chat/*`
- `/api/admin/users*`
- `/api/user/*`
- `/api/logs/global`

## Exit Criteria For The Next Round

1. React task-center flows no longer rely on Flask routes.
2. Stop/cancel behavior is verified for all long-running task classes.
3. Knowledge/chunk-profile/file-detail write operations have matching FastAPI-native APIs.
4. React-to-backend API audit shows the legacy count materially reduced from `70`.
