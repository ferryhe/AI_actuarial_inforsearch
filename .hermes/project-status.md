# Project Status

- Date: 2026-05-25
- Branch: `fix/public-stats-read`
- Latest baseline: `origin/main` at `16f44c0` (`docs: refresh security rollout documentation (#123)`).
- Scope: Open anonymous/public `stats.read` so the dashboard home route can render without redirecting to login while preserving read-only public browsing of database and file detail.
- Permission change: `PUBLIC_PERMISSIONS_WHEN_AUTH_DISABLED` / guest permissions now include `stats.read` alongside `files.read`, `catalog.read`, `markdown.read`, `chat.view`, and `chat.query`.
- Metrics safety: added `require_authenticated_permissions(...)` for endpoints that should ignore public permissions; `/api/metrics` now requires authenticated `stats.read`, so raw uptime/request/rate-limit metrics remain login-gated even though dashboard `/api/stats` is public.
- Tests updated: auth endpoint coverage asserts anonymous `/api/auth/me` includes `stats.read`, `/api/stats` returns 200, `/api/metrics` remains 401, `/api/files` remains 200, and conversation creation remains 401. Permission unit test now expects guest `stats.read`.
- Verification passed: `/home/ec2-user/.hermes/hermes-agent/venv/bin/python -m pytest tests/test_fastapi_auth_endpoints.py tests/unit/test_permissions.py -q` (39 passed).
- Verification passed: `npm run build`.
- Verification passed: `git diff --check`.
- Browser/API smoke passed with local FastAPI + Vite under auth-required mode: anonymous `/` renders dashboard instead of login, `/database` renders, clicking a file opens file detail, browser console has no JS errors, `/api/auth/me` includes `stats.read`, `/api/stats` returns 200, and `/api/metrics` returns 401.
- Local Codex review gate: first pass flagged global `stats.read` could expose `/api/metrics`; fixed by adding authenticated-only dependency and moving `/api/metrics` to it. Second pass found no discrete actionable regressions.
- Next step: commit, push, create PR, then follow up on GitHub checks/review comments after the standard wait window.
