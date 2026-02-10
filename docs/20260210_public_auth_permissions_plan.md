# 2026-02-10 Public Internet Plan: Users, Auth, Permissions (Phase 2/4)

This is a **detailed plan only**. Implementation will start after you confirm the decisions in **Confirmations**.

## Goal

Make the web UI and API safe to expose on the public Internet by adding:

- User management (accounts, login/logout, password policy)
- Authorization (roles/permissions for API endpoints and UI actions)
- CSRF protection (for cookie-based sessions)
- Security headers (CSP, clickjacking, etc.) and production defaults

## Current State (as of 2026-02-10)

- Most endpoints are accessible without authentication.
- Some write endpoints use optional `X-Auth-Token` checks only if a token env var is set.
- No CSRF protection.
- No rate limiting by default (Phase 3 adds optional limiter).

## Threat Model (Public)

We must assume:

- Untrusted clients and bots will hit all endpoints.
- Credential stuffing, brute force, scraping, and DoS attempts.
- CSRF is relevant if we use cookies/sessions.
- Logs and exports can leak sensitive data if not protected.

## Recommended Approach (Pragmatic, Web-UI Friendly)

### AuthN (Authentication)

Use **Flask-Login (session cookie)** for the web UI and UI-driven API calls, because:

- It fits browser usage and is simpler than rolling custom tokens.
- It works well with CSRF (Flask-WTF/SeaSurf).

Additionally, for non-browser / automation access:

- Add **per-user API tokens** (header-based, e.g. `Authorization: Bearer ...`) as an optional path.

### AuthZ (Authorization)

Add **RBAC** (role-based access control) with a small set of roles:

- `admin`: full access (config, delete files, export, run tasks, view logs)
- `operator`: run tasks, edit markdown, view logs; no config writes or deletes
- `reader`: browse/search/view/download; no writes, no export, no logs

We will enforce authorization **server-side** for every endpoint, not in the UI.

## Data Model

Store users in the same DB used by the app (SQLite initially; PostgreSQL later).

Tables (minimal):

- `users`
  - `id` (pk)
  - `username` (unique)
  - `password_hash`
  - `role` (enum-like string)
  - `is_active` (bool)
  - `created_at`, `last_login_at`
- `api_tokens` (optional but recommended for automation)
  - `id` (pk)
  - `user_id` (fk)
  - `token_hash`
  - `created_at`, `last_used_at`, `revoked_at`
- `audit_events` (recommended)
  - `id`, `user_id`, `event_type`, `resource`, `detail`, `ip`, `created_at`

Password hashing:

- Prefer `argon2-cffi` (best) or `bcrypt`.
- Never store plaintext tokens; hash API tokens too.

## Endpoint Protection Map (Draft)

Protect everything except the login page and static assets.

### Public/Anonymous

- `GET /` (optional: redirect to login; recommended for public)
- `GET /login` (new)
- `POST /login` (new)
- `POST /logout` (new, CSRF-protected)
- `GET /health` (optional; new minimal endpoint)

### Reader+

- `GET /api/stats`
- `GET /api/files`
- `GET /api/sources`
- `GET /api/categories`
- `GET /api/files/<url>/markdown`
- `GET /api/download`

### Operator+

- `POST /api/collections/run`
- `POST /api/files/<url>/markdown` (edit markdown)
- `GET /api/tasks/*` (active/history/log)
- `GET /api/logs/global`

### Admin only

- `GET /api/export`
- `POST /api/files/delete`
- `POST /api/config/*` (all config writes)

## CSRF (Phase 4)

If using session cookies:

- Add CSRF protection for all mutating requests (POST/PUT/PATCH/DELETE).
- For JSON `fetch()` requests, include CSRF token in a header (e.g. `X-CSRFToken`).

Implementation options:

- `Flask-SeaSurf` (simple global CSRF protection)
- `Flask-WTF` CSRF (more “Flask standard” if forms are used)

## Security Headers (Phase 4)

Add via `@app.after_request`:

- `X-Frame-Options: SAMEORIGIN`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy` (needs tuning for current templates and any CDN usage)
- `Strict-Transport-Security` (only when HTTPS is enforced)

## Phase Breakdown (Proposed)

### Phase 2A: “Auth required” baseline (fast)

- Add login/logout (Flask-Login)
- Gate all endpoints behind auth, with minimal RBAC (admin vs non-admin)
- Protect logs/export immediately
- Add audit logging for sensitive actions

### Phase 2B: Full RBAC + API tokens

- Implement roles: admin/operator/reader
- Add per-user API tokens (create/revoke UI, header auth path)
- Add brute-force controls (lockouts, exponential backoff, rate limit login)

### Phase 4: CSRF + security headers + cookie hardening

- CSRF across all write endpoints
- Cookie flags: `Secure`, `HttpOnly`, `SameSite`
- CSP rollout with report-only mode first (optional)

## Confirmations Needed (Before Implementation)

1. Auth mode:
   - A) Flask-Login sessions for UI (recommended)
   - B) Global API key only (fastest, no users)
   - C) Reverse proxy SSO (Caddy/Nginx/OAuth) + app trusts headers
2. Anonymous access:
   - A) No anonymous access (recommended for public)
   - B) Allow read-only browsing without login
3. Roles:
   - A) admin/operator/reader (recommended)
   - B) admin/reader only (simpler)
4. Automation access:
   - A) Per-user API tokens (recommended)
   - B) None (UI only)
5. CSRF library preference:
   - A) SeaSurf (simple)
   - B) Flask-WTF (standard)

Once you answer these, I will convert this plan into an implementation PR series with tests and migration notes.

