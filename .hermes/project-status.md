# Project Status

- Date: 2026-06-18
- Branch: `docs/final-state-readme-refresh`
- Scope: Final-state README/docs refresh after managed roadmap completion; deploy latest `main` afterward.

## Current State

- PR-A / #156 through PR-I / #164 are merged into `main`.
- There are no open PRs for the managed roadmap.
- PR-I / #164 completed the Web Listening automatic loop: materialized rules now create scheduled `full_pipeline` tasks rather than collection-only `scheduled` tasks.
- Materialized Web Listening full-pipeline params include `source_collection_type: scheduled`, the selected `site`, a `Full Pipeline: <site>` run name, `check_database: true`, and `run_rag_indexing: false` by default.
- Tasks UI/i18n copy describes the Web Listening materialized task as a scheduled full-pipeline monitor.
- Documentation refresh is in progress on `docs/final-state-readme-refresh`: README, Chinese README, docs index, architecture, and API migration status are being updated to reflect PR-A through PR-I, weekly summaries, typed scheduled tasks, and `full_pipeline`.
- Sibling repositories remain out of scope.

## Verification

- PR-I local focused tests before merge:
  - `python3 -m pytest tests/test_web_listening_rule.py tests/test_task_runtime_full_pipeline.py tests/test_tasks_react_source.py -q`: 32 passed; existing SWIG deprecation warnings.
  - `python3 -m pytest tests/test_fastapi_ops_write_endpoints.py::test_scheduled_tasks_write_and_schedule_reinit_roundtrip tests/test_web_listening_rule.py -q`: 5 passed; existing SWIG deprecation warnings.
  - `npm run build`: passed; Vite emitted the existing large-chunk warning.
  - `git diff --check`: passed.
  - Static added-line security scan: no findings.
  - Independent reviewer subagent: passed with no blocking security or logic findings.
  - `codex exec -s read-only ...`: `NO BLOCKING FINDINGS`.
- PR #164 remote CI: `python-smoke` succeeded.
- PR #164 Copilot review: generated no inline comments.
- Post-merge: `git fetch origin --prune` confirmed the remote PR-I branch is deleted; `gh pr list --state open` returned no open PRs.
- Docs refresh verification on `docs/final-state-readme-refresh`:
  - Active doc relative-link scan: passed.
  - Active doc stale-current-status scan: passed.
  - `python3 -m ai_actuarial --help`: passed.
  - `python3 -m pytest tests/test_web_listening_rule.py tests/test_weekly_updates.py tests/test_task_runtime_full_pipeline.py tests/test_tasks_react_source.py -q`: 40 passed; existing SWIG deprecation warnings.
  - `npm run build`: passed; Vite emitted the existing large-chunk warning.
  - `git diff --check`: passed.
  - Independent reviewer subagents: one found an incorrect `web_page` typed-param doc claim; fixed. Follow-up links/stale reviewer passed.
  - `codex exec -s read-only ...`: `NO BLOCKING FINDINGS`.

## Local Notes

- Existing protected stashes from earlier work remain untouched, including `protected-project-status-before-pr-f` and `protected-local-files-before-pr-d-review`.
- Next gate: verify docs refresh, commit/push/open/merge docs PR, sync `main`, then update the website service to latest `main` and run public health checks.
