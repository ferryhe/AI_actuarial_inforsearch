# Project Status

- Date: 2026-06-18
- Branch: `feature/pr-g-full-pipeline-automatic-chaining`
- Scope: PR-G full_pipeline automatic chaining.

## Current State

- PR-A / #156: merged earlier (product UX baseline).
- PR-B / #157: merged earlier (security and test baseline).
- PR-C / #158: merged earlier (categories browsing page).
- PR-D / #159: merged earlier (Chat guest Demo KB).
- PR-E / #160: merged earlier (Admin UI wrap-up).
- PR-F / #161: merged into `main`; remote branch appears deleted/pruned.
- PR-G is implemented on `feature/pr-g-full-pipeline-automatic-chaining`.
- Backend accepts `full_pipeline` for immediate runs and scheduled tasks.
- Native runtime chains source collection, Markdown conversion, cataloging, chunk generation, and optional RAG indexing, with per-stage metadata/error/stopped reporting.
- Downstream stages use recently collected file URLs when available, including unscoped scheduled/search runs with no explicit site/url, falling back to explicit source URLs only when no collected files are found.
- `full_pipeline` dispatch now avoids opening an outer Storage connection before nested stage calls, reducing SQLite lock contention.
- Tasks UI exposes a Full Pipeline form/card; Scheduled Tasks typed params and task history filter include `full_pipeline`.
- Sibling repositories remain out of scope.

## Verification

- `python3 -m pytest tests/test_task_runtime_full_pipeline.py -q`: 8 passed; existing SWIG deprecation warnings.
- `python3 -m pytest tests/test_fastapi_ops_write_endpoints.py::test_scheduled_tasks_write_and_schedule_reinit_roundtrip -q`: 1 passed; existing SWIG deprecation warnings.
- `python3 -m pytest tests/test_tasks_react_source.py -q`: 20 passed; coverage warning noted no data collected for source-only tests.
- `npm run build`: passed; Vite emitted the existing large-chunk warning.
- `git diff --check`: passed.
- `codex exec -s read-only review --uncommitted`: final PR-G implementation review returned `NO BLOCKING FINDINGS`; follow-up Copilot comment fix review returned `NO BLOCKING FINDINGS` (sandbox pytest attempt blocked by read-only tempdir, but local pytest passed outside sandbox).
- Independent reviewer subagent: follow-up Copilot comment fix review passed with no blocking findings; nonblocking suggestions were extra OR-semantics coverage and avoiding direct `_conn` test coupling.

## Local Notes

- Modified files: `.hermes/project-status.md`, `ai_actuarial/api/services/ops_write.py`, `ai_actuarial/task_runtime.py`, `client/src/hooks/use-i18n.ts`, `client/src/pages/Tasks.tsx`, `client/src/pages/tasks/FilterBar.tsx`, `client/src/pages/tasks/ScheduledTasksSection.tsx`, `tests/test_fastapi_ops_write_endpoints.py`, `tests/test_tasks_react_source.py`.
- New files: `client/src/pages/tasks/FullPipelineForm.tsx`, `tests/test_task_runtime_full_pipeline.py`.
- Latest follow-up fixes address Copilot comments on PR #162: unscoped scheduled full_pipeline downstream URL propagation and avoiding an outer Storage connection during full_pipeline dispatch.
- Existing protected stashes from earlier work remain untouched, including `protected-project-status-before-pr-f` and `protected-local-files-before-pr-d-review`.
- Next gate: commit and push follow-up fixes, then re-check PR #162 CI/Copilot/comments before merge.
