# Project Status

- Date: 2026-06-17
- Branch: `feature/pr-e-admin-ui-wrapup`
- Scope: PR-E Admin UI wrap-up for Markdown configuration and Web Listening management entry.

## Current State

- PR-A / #156: merged earlier (product UX baseline).
- PR-B / #157: merged earlier (security and test baseline).
- PR-C / #158: merged earlier (categories browsing page).
- PR-D / #159: merged on 2026-06-17 at merge commit `056ab425e222190546145015563e6e511cd80322`; branch `feature/pr-d-chat-demo-kb` was deleted on origin and no local branch remains.
- PR-E branch `feature/pr-e-admin-ui-wrapup` is in progress from `main` / `origin/main` at `056ab425e222190546145015563e6e511cd80322`.
- No open GitHub PRs were present before starting PR-E.
- PR-E changes are intentionally narrow:
  - expose the Web Listening entry using its required `sites.write` permission instead of hiding it behind `tasks.run` only;
  - add the missing RAG Indexing task-history filter for discoverability;
  - prevent invalid/empty/negative Markdown conversion limit edits from being coerced to `0` in the settings UI.

## Verification

- Startup checks run from `/opt/ai_actuarial_inforsearch`: `git status --short --branch`, `git remote -v`, `gh auth status`, `git fetch --prune origin`, `gh pr list --state open`, and stash inspection.
- Read-only planning subagent inspected PR-E scope and ran `python3 -m pytest tests/test_settings_react_source.py tests/test_tasks_react_source.py tests/test_web_listening_rule.py -q`: 28 passed, 3 warnings.
- Focused implementation checks run locally:
  - `python3 -m pytest tests/test_settings_react_source.py tests/test_tasks_react_source.py tests/test_web_listening_rule.py tests/test_fastapi_ops_write_endpoints.py::test_markdown_conversion_config_read_write_endpoint_roundtrip -q`: 30 passed, 3 warnings.
  - `npm run build`: passed; Vite emitted only the existing large-chunk warning.
  - `git diff --check`: passed.
- Codex CLI pre-PR review initially found two valid P2 issues (non-matching Web Listening history filter and schedule-only Web Listening visibility); both were fixed before opening PR #160. Copilot then left one valid Markdown limit-edit UX comment on PR #160; this branch now uses editable per-limit draft strings and resets invalid drafts on blur.

## Notes

- Sibling repositories remain out of scope.
- Do not commit local `.env`, secrets, generated credentials, or production-only overrides such as `docker-compose.override.yml` unless explicitly scoped.
- A stash named `protected-local-files-before-pr-d-review` remains in git stash from earlier protected-local-file handling; do not drop it without confirming it is no longer needed.
- Existing older stashes (`fix/chat-retrieval-no-results`, `main` WIP, `fix/caddy-fail2ban-access-log`) remain untouched.
