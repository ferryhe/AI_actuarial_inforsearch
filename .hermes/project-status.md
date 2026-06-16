# Project Status

- Date: 2026-06-16
- Branch: `task/p0-3-web-listening-agent-rule`
- Baseline: `origin/main` at `014dd30`.
- Scope: P0-3 web-listening agent rule backend support.
- PR: not opened in this delegated coder step.
- Previous PRs: [#148](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/148) — merged; [#147](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/147) — merged; [#146](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/146) — merged; [#145](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/145) — merged.

## Current State

- Added backend-first web-listening rule support for schema version `web-listening-agent-rule.v1`.
- New rule helpers generate deterministic human-editable YAML drafts from `website_url` + `goal` without fetching the target site, validate YAML/object payloads, and materialize rules into the existing `sites` and `scheduled_tasks` config shapes.
- Added API endpoints:
  - `POST /api/web-listening/rules/draft`
  - `POST /api/web-listening/rules/validate`
  - `POST /api/web-listening/rules/materialize`
- Materialization backs up `sites.yaml` with collision-resistant backup names, upserts by site/task name for idempotency, notifies the runtime config bridge, and returns `requires_scheduler_reinit: false`.
- `task_runtime` now passes `collect_page_content` from YAML site rows into `SiteConfig`.
- Ops read now exposes advanced site fields needed by web-listening rules: `allow_url_patterns`, `queries`, `file_exts`, and `collect_page_content`.
- Agentic RAG code was not touched.
- Local `docker-compose.override.yml` still has an unrelated production override diff and must remain uncommitted.

## Verification

- `python3 -m pytest tests/test_web_listening_rule.py -q` passed (4 tests; 3 pre-existing SWIG/import warnings).
- `python3 -m pytest tests/test_fastapi_ops_write_endpoints.py tests/test_web_listening_rule.py -q` passed (29 tests; 3 pre-existing SWIG/import warnings).
- `python3 -m py_compile ai_actuarial/web_listening_rule.py ai_actuarial/api/services/ops_write.py ai_actuarial/api/routers/ops_write.py ai_actuarial/api/services/ops_read.py ai_actuarial/task_runtime.py` passed.
- `git diff --check` passed.
- Broader combined command `python3 -m pytest tests/test_fastapi_ops_write_endpoints.py tests/test_fastapi_ops_read_endpoints.py tests/test_web_listening_rule.py -q` had 34 passed and 1 failed in `test_rate_limit_defaults_are_enforced_from_runtime_features`: expected 400 but got 403 because the operator token was rate-limited during the combined run. The same single test also fails on a clean `origin/main` worktree, so this is pre-existing and not caused by this branch.
- Independent spec review initially flagged untracked new files and protected `docker-compose.override.yml` as PR packaging blockers; task files must be explicitly added and the production override must stay uncommitted.
- Independent code-quality/security review flagged backup filename collision on rapid idempotent materialization; fixed by adding microsecond precision and regression assertions for distinct backups.
- Mandatory local Codex CLI review gate was attempted and blocked by expired/reused Codex auth refresh token (401); Hermes independent spec and code-quality reviewers passed after the backup fix.

## Notes

- Sibling repositories remain out of scope for this project run.
- Do not copy secrets, `.env` files, generated credentials, active Docker volumes, logs, or local production overrides into this PR.
- No push/PR was performed per delegated task instruction.
