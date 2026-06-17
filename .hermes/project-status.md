# Project Status

- Date: 2026-06-18
- Branch: `feature/pr-h-weekly-summary-dashboard-schedule`
- Scope: PR-H weekly_summary Dashboard data source and default schedule.

## Current State

- PR-A / #156 through PR-G / #162 are merged into `main`.
- PR-H is implemented locally on `feature/pr-h-weekly-summary-dashboard-schedule`.
- Dashboard now reads latest weekly update data from `GET /api/weekly-updates/latest` instead of deriving weekly additions from `/api/files` in the browser.
- Dashboard weekly count uses latest summary `file_count`; displayed rows use latest summary `files` capped to the existing Dashboard list limit.
- Dashboard weekly labels now use customer-facing “latest weekly additions / 周报新增” wording instead of browser-local “this week” wording.
- Default `config/sites.yaml` now includes an enabled weekly `weekly_summary` scheduled task with `relative_period: previous_week` and `max_files: 500`.
- Weekly summary runtime accepts `relative_period`; `previous_week` resolves to the previous completed UTC ISO week so Monday 00:30 schedules summarize the completed week rather than the just-started current week.
- Sibling repositories remain out of scope.

## Verification

- `python3 -m pytest tests/test_weekly_updates.py tests/test_dashboard_react_source.py tests/test_fastapi_ops_write_endpoints.py::test_scheduled_tasks_write_and_schedule_reinit_roundtrip tests/test_tasks_react_source.py -q`: 31 passed; existing SWIG deprecation warnings.
- `npm run build`: passed; Vite emitted the existing large-chunk warning.
- `git diff --check`: passed.
- Static added-line security scan: no findings.
- Independent reviewer subagent: passed with no blocking security or logic findings.
- `codex exec -s read-only ...`: `NO BLOCKING FINDINGS`.

## Local Notes

- Modified files: `.hermes/project-status.md`, `ai_actuarial/api/services/weekly_updates.py`, `ai_actuarial/task_runtime.py`, `client/src/hooks/use-i18n.ts`, `client/src/pages/Dashboard.tsx`, `config/sites.yaml`, `tests/test_dashboard_react_source.py`, `tests/test_weekly_updates.py`.
- Existing protected stashes from earlier work remain untouched, including `protected-project-status-before-pr-f` and `protected-local-files-before-pr-d-review`.
- Next gate: commit, push, open PR-H, then inspect CI/Copilot/review comments after the initial and delayed GitHub checks.
