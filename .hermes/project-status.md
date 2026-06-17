# Project Status

- Date: 2026-06-18
- Branch: `feature/pr-f-scheduled-tasks-typed-wizard`
- Scope: PR-F Scheduled Tasks typed wizard enhancement.

## Current State

- PR-A / #156: merged earlier (product UX baseline).
- PR-B / #157: merged earlier (security and test baseline).
- PR-C / #158: merged earlier (categories browsing page).
- PR-D / #159: merged earlier (Chat guest Demo KB).
- PR-E / #160: merged earlier (Admin UI wrap-up).
- PR-F is implemented on `feature/pr-f-scheduled-tasks-typed-wizard` with narrow frontend/source-test changes only.
- Scheduled Tasks Add/Edit form now exposes typed parameter fields for backend-consumed scheduled task params while retaining the advanced JSON textarea as a preview/fallback so unknown legacy params are preserved.
- `weekly_summary` is exposed in the Scheduled Tasks task type dropdown because the backend write endpoint accepts and runs it.
- Disallowed legacy file scheduling remains unexposed in the Scheduled Tasks UI.
- Sibling repositories remain out of scope.

## Verification

- `python3 -m pytest tests/test_tasks_react_source.py -q`: 19 passed; coverage warning noted no data collected for source-only tests.
- `python3 -m pytest tests/test_fastapi_ops_write_endpoints.py::test_scheduled_tasks_write_and_schedule_reinit_roundtrip -q`: 1 passed, 3 existing SWIG deprecation warnings.
- `npm run build`: passed; Vite emitted the existing large-chunk warning.
- `git diff --check`: passed.
- `codex exec -s read-only review --uncommitted`: initially found backend-param alignment issues; after fixes, passed with no discrete correctness issues.
- Independent reviewer subagent: initially found an ignored `category` typed field for catalog/url; after fixes, passed with no blocking security or logic issues.

## Local Notes

- Modified files: `client/src/pages/tasks/ScheduledTasksSection.tsx`, `client/src/hooks/use-i18n.ts`, `tests/test_tasks_react_source.py`, `.hermes/project-status.md`.
- Existing protected stashes from earlier work remain untouched, including `protected-project-status-before-pr-f` and `protected-local-files-before-pr-d-review`.
- Next roadmap item after PR-F is PR-G (`full_pipeline` automatic chaining), but PR-G should only start after PR-F remote CI/review/comment gates are clean and PR-F is merged.
