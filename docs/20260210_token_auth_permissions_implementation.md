# 2026-02-10 Token Auth + Permission Groups Implementation

Branch: `copilot/review-code-for-standards`

This document describes the implemented **per-user API token** authentication and **group-based permissions** for public deployment.

## Summary

- Added token-based auth with groups: `admin`, `operator`, `reader`.
- Enforced permissions on both HTML pages and API endpoints when `REQUIRE_AUTH=true`.
- Added `/login` token form for browser usage (creates a cookie session).
- Added admin token management APIs to create/revoke tokens.
- Added optional CSRF (SeaSurf) and security headers via env flags.

## Permissions

Permission IDs (implemented in `ai_actuarial/web/app.py`):

- `stats.read`
- `files.read`
- `files.download`
- `files.delete`
- `catalog.read`, `catalog.write`
- `markdown.read`, `markdown.write`
- `config.read`, `config.write`
- `schedule.write`
- `tasks.view`, `tasks.run`, `tasks.stop`
- `logs.task.read`, `logs.system.read`
- `export.read`
- `tokens.manage`

Group mapping:

- `reader`: read-only browsing/downloading/markdown viewing
- `operator`: reader + run/stop tasks + edit catalog/markdown + manage schedule sites + view task logs
- `admin`: full permissions

## Key Endpoints

- Login/logout:
  - `GET /login`
  - `POST /login` (token form)
  - `POST /logout`
- Who am I:
  - `GET /api/auth/me`
- Token management (admin):
  - `GET /api/auth/tokens`
  - `POST /api/auth/tokens` (returns plaintext token once)
  - `POST /api/auth/tokens/<id>/revoke`

## Settings UI (Admin)

In the Settings page, a **Tokens** tab is available for admins:

- List existing tokens (subject/group/active/created/last_used/revoked)
- Create token (shows plaintext once + copy button)
- Revoke token

## Environment Variables

See `.env.example` for full list. Core ones:

- `REQUIRE_AUTH=true`
- `FLASK_SECRET_KEY=...`
- `BOOTSTRAP_ADMIN_TOKEN=...` (bootstrap first admin token record)
- `BOOTSTRAP_ADMIN_SUBJECT=bootstrap-admin`

Optional hardening:

- `ENABLE_CSRF=true` (Flask-SeaSurf)
- `ENABLE_SECURITY_HEADERS=true`
- `CONTENT_SECURITY_POLICY=...` (optional CSP header)

## How To Use (Public Deployment Flow)

1. Set `FLASK_SECRET_KEY` and `REQUIRE_AUTH=true`.
2. Set `BOOTSTRAP_ADMIN_TOKEN` once to create/ensure an admin token.
3. Start the server, then login at `/login` using the admin token.
4. Create additional tokens via `POST /api/auth/tokens` (admin-only).
5. Remove `BOOTSTRAP_ADMIN_TOKEN` after initial setup (recommended).

## Tests

- Added `test_auth_tokens.py` to validate:
  - 401 on unauthenticated API access when `REQUIRE_AUTH=true`
  - bearer token auth works
  - permission group enforcement (reader forbidden on config)
  - admin token create/revoke works
