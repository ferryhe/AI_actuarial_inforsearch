# Project Status

- Date: 2026-06-16
- Branch: `codex/p0-2-customer-dashboard`
- Baseline: `origin/main` at `0f882cf`.
- Scope: P0-2 Dashboard 客户化 customer-facing homepage.
- PR: [#148](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/148) — open; CI in progress at creation time.
- Previous PRs: [#147](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/147) — merged; [#146](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/146) — merged; [#145](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/145) — merged.

## Current State

- Dashboard now presents customer-facing entry points: browse materials, browse categories, and ask Agent.
- Dashboard category list loads from `/api/categories?mode=used`; category rows link into Database with the selected category filter.
- Dashboard weekly additions load from `/api/files?limit=24&order_by=first_seen&order_dir=desc`, filter this calendar week by `first_seen` client-side, and open FileDetail via `buildFileDetailPath`.
- `/api/files` now supports `order_by=first_seen` so the Dashboard samples newest additions rather than most recently re-seen files.
- Dashboard no longer renders backend/ops-oriented cataloged file counts, active task counts, task/knowledge/RAG/chunk/embedding statuses, or Tasks/Knowledge quick actions.
- English and Chinese dashboard i18n strings were updated for customer-facing labels.
- Added a focused source regression test for the Dashboard customer-facing contract.
- Local `docker-compose.override.yml` still has an unrelated production override diff and must remain uncommitted for this PR.

## Verification

- `python3 -m pytest tests/test_dashboard_react_source.py tests/test_react_fastapi_authority.py tests/test_fastapi_read_endpoints.py -q` passed (9 tests; 3 pre-existing SWIG/import warnings).
- `npm test` passed and ran the Vite production build; Vite still emits the existing large chunk warning.
- `git diff --check` passed.
- Independent spec review pass 2: PASS after `first_seen` ordering fix.
- Independent code-quality/security review pass 2: PASS after `first_seen` ordering fix.
- Mandatory local Codex review gate attempted with `codex exec review --base origin/main` but blocked by expired/reused Codex auth refresh token (401); Hermes independent reviewers were used for this gate.

## Notes

- Sibling repositories remain out of scope for this project run.
- Do not copy secrets, `.env` files, generated credentials, active Docker volumes, logs, or local production overrides into this PR.
