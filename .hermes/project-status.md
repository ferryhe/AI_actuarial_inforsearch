# Project Status — Issue #232 Legacy Token Gate Cleanup

- Updated: 2026-08-26
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Project\AI_actuarial_inforsearch\.codex-worktrees\issue-232`
- Branch: `agent/issue-232` (based on `fd9dc705ac89bf32cb1cf669645e6b1308df52f6`)

## Delivered behavior

- `GET /api/logs/global` now uses the existing `logs.system.read` permission without the later duplicate shared-token check.
- The global logs feature flag and endpoint-specific rate limit remain unchanged.
- `POST /api/files/delete` now uses the existing `files.delete` permission, deletion feature flag, and explicit `confirm: "DELETE"` requirement without the later duplicate service token check.
- Session, Bearer, and `X-API-Token` authorization continue through the shared FastAPI auth dependency.
- Removed configuration, runtime diagnostics, compose wiring, examples, and documentation references that existed only for the two retired endpoint gates.
- `CONFIG_WRITE_AUTH_TOKEN` and its RAG compatibility path remain unchanged.

## Verification

- TDD reproduction before the implementation: `5 failed, 2 passed`; focused green rerun: `9 passed`.
- Independent local reviewer suite: `120 passed, 7 skipped`.
- Final focused API/auth/RBAC/RAG/CI selection: `158 passed, 7 skipped`; one unrelated RAG test failed once from shared temporary-path state and passed immediately when rerun alone with the two CONFIG_WRITE compatibility tests: `3 passed`.
- Codex CLI review gate independently ran the related suite: `120 passed, 7 skipped`, and returned no findings.
- Changed frontend source assertions passed; four unchanged Windows tests that invoke literal `npm` remain blocked because this host exposes `npm.cmd`/`npm.ps1`.
- Ruff on all changed Python passed with baseline `F401` ignored for one unchanged unused import.
- `python -m compileall -q ai_actuarial tests scripts/diagnose_secrets_runtime.py`: passed.
- `git diff --check`: passed.
- Active runtime/config/deploy/docs scan found no remaining references to the two retired gate names.
- No production addition or behavioral change involving `CONFIG_WRITE_AUTH_TOKEN` was found.

## Review evidence

- Scripted local review Round 1: PASS; no concrete normal-path regression or Issue acceptance failure.
- Mandatory Codex CLI review gate: PASS; no finding after tracing the shared auth/RBAC paths and running focused regressions.
- Speculative multi-process limits, malformed clients, corrupt state, hidden external callers, retry/recovery, and extra hardening were excluded per user scope.

## Scope decisions

- No roles, permissions, frontend production behavior, database/schema, crawler, RAG, model, retry, recovery, or new security mechanisms were changed.
- The only additional observed issue was an unrelated pre-existing File Detail catch-all UX concern from PR #231; it is not included in Issue #232.

## Worktree state

- The Issue #232 implementation and tests are complete and ready for Draft PR publication.
- No unrelated worktree changes or untracked files were identified.
