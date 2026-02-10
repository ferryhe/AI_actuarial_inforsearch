# 2026-02-10 Public Internet Plan: Token Auth, Groups, Permissions (Phase 2/4)

This document is a **detailed plan**. You asked to prefer **per-user API tokens** and assign **permission groups via tokens**.

Implementation will proceed based on this plan.

## Goal

Make the web UI and API safe to expose on the public Internet by adding:

- Token-based authentication (per-user API tokens)
- Authorization (token groups + explicit permission list)
- CSRF protection (because the web UI needs cookie sessions)
- Security headers (CSP, clickjacking, etc.) and production defaults

## Constraints / Current State (as of 2026-02-10)

- The app serves HTML pages via Flask templates. Browsers do not attach custom headers on normal navigation.
- Many API endpoints are currently accessible without authentication.
- No CSRF protection.

## Recommended Approach (Token-First, Web-Compatible)

### Authentication (AuthN)

Primary credential: **per-user API token**.

- Automation access: `Authorization: Bearer <token>` on every request.
- Web UI access:
  - Provide `/login` where a user pastes a token once.
  - Server validates the token, then creates a **cookie session** bound to the token ID.
  - Subsequent UI navigation works without needing headers.

### Authorization (AuthZ)

Authorization is based on **token group**. Each token belongs to exactly one group.

Default groups:

- `admin`: full access (config, delete files, export, run tasks, view task logs, view system logs)
- `operator`: run tasks, edit markdown, view task logs, no config writes or deletes
- `reader`: browse/search/view/download; no writes, no export, no logs, no tasks page, no scheduled tasks page

All enforcement is **server-side**.

## Permissions (Explicit List)

Permission IDs:

- `stats.read`: dashboard stats
- `files.read`: list/search file records
- `files.download`: download local file bytes
- `files.delete`: delete file (soft delete and optional disk deletion)
- `catalog.read`: view catalog metadata (category/summary/keywords)
- `catalog.write`: update catalog metadata (category/summary/keywords)
- `markdown.read`: read markdown content
- `markdown.write`: edit markdown content
- `config.read`: read config endpoints (sites/categories/backend settings)
- `config.write`: write config endpoints
- `tasks.view`: view Tasks page and task history/active list
- `tasks.run`: start tasks (collections, cataloging, markdown conversion)
- `tasks.stop`: stop running tasks
- `logs.task.read`: read per-task logs (`/api/tasks/log/<task_id>`)
- `logs.system.read`: read system/global logs (`/api/logs/global`)
- `export.read`: export DB (`/api/export`)
- `tokens.manage`: create/revoke/list tokens

Group -> permissions (baseline mapping):

- `reader`:
  - `stats.read`, `files.read`, `files.download`, `catalog.read`, `markdown.read`
- `operator`:
  - all `reader`
  - `catalog.write`, `markdown.write`
  - `tasks.view`, `tasks.run`, `tasks.stop`
  - `logs.task.read`
- `admin`:
  - all `operator`
  - `files.delete`, `config.read`, `config.write`, `export.read`
  - `logs.system.read`
  - `tokens.manage`

## Data Model

Store auth data in the same DB used by the app (SQLite initially; PostgreSQL later).

Tables (minimal):

- `auth_tokens`
  - `id` (pk)
  - `subject` (string, e.g. username/email/team name)
  - `group_name` (`admin`/`operator`/`reader`)
  - `token_hash` (never store plaintext)
  - `is_active` (bool)
  - `created_at`, `last_used_at`, `revoked_at`
  - `expires_at` (optional)
- `audit_events` (recommended)
  - `id`, `token_id`, `event_type`, `resource`, `detail`, `ip`, `created_at`

Token hashing:

- Use SHA-256 of the token (acceptable baseline).
- Tokens must be long random secrets (e.g. `secrets.token_urlsafe(32)`).

## Endpoint / Page Protection Map (Draft)

### Public/Anonymous

- `GET /login`
- `POST /login`

Optional:

- `GET /health`

### Reader+

- Pages: `/`, `/database`, `/file/<...>` (view-only)
- APIs: `GET /api/stats`, `GET /api/files`, `GET /api/sources`, `GET /api/categories`, `GET /api/files/<...>/markdown`, `GET /api/download`

### Operator+

- Pages: `/tasks`
- APIs: `POST /api/collections/run`, `POST /api/files/update`, `POST /api/files/<...>/markdown`
- APIs: `GET /api/tasks/active`, `GET /api/tasks/history`, `GET /api/tasks/log/<...>`

### Admin only

- Pages: `/scheduled_tasks`, `/settings` (because they contain write controls)
- APIs: `POST /api/config/*`, `POST /api/files/delete`, `GET /api/export`, `GET /api/logs/global`
- APIs: token management endpoints (new)

## Token Management (Admin)

Add admin-only endpoints:

- `GET /api/auth/tokens` (list)
- `POST /api/auth/tokens` (create token with `subject` + `group_name`)
- `POST /api/auth/tokens/<id>/revoke`

Bootstrap problem:

- Add env `BOOTSTRAP_ADMIN_TOKEN` (plaintext) used only to bootstrap the first admin token record.
- When set, app startup will upsert an `admin` token matching it.

## CSRF (Phase 4)

Because web UI uses cookie sessions:

- Add CSRF protection for mutating requests (POST/PUT/PATCH/DELETE).
- For JSON fetch, send CSRF token in a header (e.g. `X-CSRFToken`) or use SeaSurf defaults.

Preferred library: **Flask-SeaSurf**.

## Security Headers (Phase 4)

Add via `@app.after_request`:

- `X-Frame-Options: SAMEORIGIN`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy` (tuned to actual assets)
- `Strict-Transport-Security` (only when HTTPS is enforced)

## Phase Breakdown (Proposed)

### Phase 2A: Auth required baseline

- Token validation (header + session)
- Permission checks per endpoint + per page
- Add `/login` + `/logout` and `/api/auth/me`
- Add bootstrap admin token support

### Phase 2B: Token management UI

- Admin UI for creating/revoking tokens
- Audit logging for token usage + sensitive operations

### Phase 4: CSRF + security headers + cookie hardening

- CSRF integration
- Cookie flags: `Secure`, `HttpOnly`, `SameSite`
- CSP rollout (optionally report-only first)

## Confirmations (Last Checks)

- Token header: use `Authorization: Bearer <token>`.
- Anonymous access: default to no anonymous access for public.
- Groups: `admin/operator/reader` as defined above.
- CSRF: use SeaSurf.

