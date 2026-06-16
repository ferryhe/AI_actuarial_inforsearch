# 2026-02-10 Security Hardening Implementation Report (Phase 1/3/5)

Branch: `copilot/review-code-for-standards`

## What Changed

### Phase 1: Immediate Hardening

- Centralized numeric parsing + clamping helpers in `ai_actuarial/web/app.py`:
  - `limit` is clamped to `1..1000` for `/api/files`
  - task history `limit` is clamped to `1..200`
  - per-task log `tail` is clamped to `1..5000`
- API 500 responses no longer return raw exception strings by default:
  - 500 responses use `_api_error("Internal server error", detail=str(e))` and only expose `detail` when `EXPOSE_ERROR_DETAILS=true` or `FLASK_DEBUG=true`.
- Reduced sensitive error leakage in Markdown conversion task history:
  - detailed exceptions are written to per-task logs; user-visible `errors[]` entries are now generic.
- Protected schema helpers against unsafe table-name interpolation:
  - added allowlist for tables used by schema migration helpers in `ai_actuarial/storage.py`.
- Protected global log API endpoint:
  - `/api/logs/global` now requires `ENABLE_GLOBAL_LOGS_API=true`.
  - if `LOGS_READ_AUTH_TOKEN` is set, it also requires `X-Auth-Token` header.

### Phase 3: Optional Rate Limiting

- Added optional Flask-Limiter integration (disabled by default):
  - Enable with `ENABLE_RATE_LIMITING=true`.
  - Configure defaults with `RATE_LIMIT_DEFAULTS`.
  - Configure backend with `RATE_LIMIT_STORAGE_URI` (use Redis for multi-process deployments).
- Applied endpoint-specific limits when enabled:
  - `POST /api/collections/run`
  - `GET /api/export`
  - `GET /api/download`
  - `GET /api/logs/global`

### Phase 5: Documentation Accuracy

- Updated audit/security docs to remove inaccurate claims (e.g., “SQLAlchemy ORM protects SQL injection” on the default sqlite3 path) and to clarify that CodeQL should be enabled in CI.

## Config Changes

Updated `.env.example`:

- `EXPOSE_ERROR_DETAILS`
- `ENABLE_GLOBAL_LOGS_API`, `LOGS_READ_AUTH_TOKEN`
- `ENABLE_RATE_LIMITING`, `RATE_LIMIT_DEFAULTS`, `RATE_LIMIT_STORAGE_URI`

Updated `requirements.txt`:

- Added `Flask-Limiter>=3.0.0`

## How To Test

### Automated

Run:

```powershell
python -m pytest
```

### Manual Smoke Checks

1. Limit clamping:
   - `GET /api/files?limit=999999` should return with `limit: 1000`.
2. Error detail hiding (default):
   - Trigger a known error and confirm 500 JSON does not include internal details.
3. Global logs protection:
   - With `ENABLE_GLOBAL_LOGS_API=false`, `GET /api/logs/global` should return 403.
   - With `ENABLE_GLOBAL_LOGS_API=true` and `LOGS_READ_AUTH_TOKEN` set, missing/incorrect `X-Auth-Token` should return 403.
4. Rate limiting (optional):
   - With `ENABLE_RATE_LIMITING=true`, repeated calls should eventually get 429 responses on limited endpoints.

## Follow-ups (Not Implemented Yet)

- Public auth, users, roles/permissions, CSRF, and security headers are planned in:
  - `docs/20260210_public_auth_permissions_plan.md`

