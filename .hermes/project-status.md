# Project Status

- Date: 2026-06-18
- Branch: `feature/pr-i-web-listening-full-loop`
- Scope: PR-I Web Listening full automatic loop.

## Current State

- PR-A / #156 through PR-H / #163 are merged into `main`.
- PR-I implementation is prepared on `feature/pr-i-web-listening-full-loop`.
- Web Listening rule materialization now creates an enabled `full_pipeline` scheduled task instead of a collection-only `scheduled` task.
- Materialized Web Listening full-pipeline params include `source_collection_type: scheduled`, the selected `site`, a `Full Pipeline: <site>` run name, `check_database: true`, and `run_rag_indexing: false` by default.
- Tasks UI/i18n copy now describes the Web Listening materialized task as a scheduled full-pipeline monitor.
- Sibling repositories remain out of scope.

## Verification

- `python3 -m pytest tests/test_web_listening_rule.py tests/test_task_runtime_full_pipeline.py tests/test_tasks_react_source.py -q`: 32 passed; existing SWIG deprecation warnings.
- `python3 -m pytest tests/test_fastapi_ops_write_endpoints.py::test_scheduled_tasks_write_and_schedule_reinit_roundtrip tests/test_web_listening_rule.py -q`: 5 passed; existing SWIG deprecation warnings.
- `npm run build`: passed; Vite emitted the existing large-chunk warning.
- `git diff --check`: passed.
- Static added-line security scan: no findings.
- Independent reviewer subagent: passed with no blocking security or logic findings.
- `codex exec -s read-only ...`: `NO BLOCKING FINDINGS`.

## Local Notes

- Modified files for PR-I: `.hermes/project-status.md`, `ai_actuarial/web_listening_rule.py`, `client/src/hooks/use-i18n.ts`, `tests/test_tasks_react_source.py`, `tests/test_web_listening_rule.py`.
- Existing protected stashes from earlier work remain untouched, including `protected-project-status-before-pr-f` and `protected-local-files-before-pr-d-review`.
- Next gate: commit, push, open PR-I, then inspect CI/review/Copilot comments before merge.
