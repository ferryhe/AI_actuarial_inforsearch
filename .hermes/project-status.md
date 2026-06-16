# Project Status

- Date: 2026-06-16
- Branch: `task/p1-1-weekly-updates`
- Baseline: `origin/main` at `63a0e54` per delegated task context.
- Scope: P1-1 Weekly Updates API backend/storage/task-runtime support with focused tests.
- PR: not opened in this delegated coder step.
- Previous PRs: [#148](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/148) — merged; [#147](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/147) — merged; [#146](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/146) — merged; [#145](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/145) — merged.

## Current State

- Added `weekly_update_summaries` SQLite table initialization plus storage helpers to upsert/list/latest weekly summaries.
- Added first-seen period query for weekly new files using `files.first_seen >= period_start AND files.first_seen < period_end`; `last_seen` is not used for new-file inclusion.
- Added Weekly Updates read API endpoints protected by `files.read`:
  - `GET /api/weekly-updates`
  - `GET /api/weekly-updates/latest`
- Empty latest response returns HTTP 200 with `{"summary": null}`.
- Added weekly summary generation service with UTC ISO week default period convention `[Monday 00:00, next Monday 00:00)` and metadata explicitly marking content-change detection as disabled for v1.
- Added `NativeTaskRuntime` support for collection type `weekly_summary` to generate and persist a summary.
- Added `weekly_summary` to ops write scheduled-task and collection-run validation allowlists so it can be launched through the existing UI/API task paths.
- Agentic RAG code was not touched.
- Local `docker-compose.override.yml` still has an unrelated production override diff and must remain uncommitted.

## Verification

- `python3 -m pytest tests/test_weekly_updates.py -q` passed (4 tests; 3 pre-existing SWIG/import warnings).
- `python3 -m pytest tests/test_fastapi_read_endpoints.py tests/test_weekly_updates.py -q` passed (10 tests; 3 pre-existing SWIG/import warnings).
- `python3 -m pytest tests/test_fastapi_ops_write_endpoints.py::test_scheduled_tasks_write_and_schedule_reinit_roundtrip -q` passed (1 test; 3 pre-existing SWIG/import warnings) after adding `weekly_summary` validation allowlist coverage.
- `python3 -m py_compile ai_actuarial/storage.py ai_actuarial/api/services/weekly_updates.py ai_actuarial/api/routers/weekly_updates.py ai_actuarial/api/app.py ai_actuarial/task_runtime.py ai_actuarial/api/services/ops_write.py tests/test_weekly_updates.py tests/test_fastapi_ops_write_endpoints.py` passed.
- `git diff --check` passed.

## Notes

- Focused regression coverage confirms a file with recent `last_seen` but old `first_seen` is excluded, while current-period `first_seen` is included.
- Sibling repositories remain out of scope for this project run.
- Do not copy secrets, `.env` files, generated credentials, active Docker volumes, logs, or local production overrides into this PR.
- No commit, push, or PR was performed per delegated task instruction.
