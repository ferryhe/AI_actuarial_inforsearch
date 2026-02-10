# 2026-02-10 Security Hardening Plan (Phase 1/3/5)

This plan applies to branch `copilot/review-code-for-standards`.

## Context

The application will be exposed on the public Internet. Current code has:

- Many API endpoints accessible without authentication.
- Multiple places returning `str(e)` to clients on 500 responses.
- Missing input bounds checks (e.g., `limit/offset`).
- No rate limiting.
- Audit docs containing a few inaccurate statements (e.g., “SQLAlchemy ORM protects SQL injection” while the default path uses `sqlite3`).

This plan covers **Phase 1, Phase 3, Phase 5** only.

## Scope (In)

### Phase 1 (Immediate hardening)

- Add centralized numeric parsing + clamping helpers for query params (e.g., `limit`, `offset`, `tail`).
- Stop returning raw exception details to clients for 500 errors.
- Protect `/api/logs/global` from unauthenticated access (at minimum: feature flag and/or token).
- Reduce leakage of internal details in task history records (keep details in per-task logs).
- Add allowlist validation for dynamic `PRAGMA table_info({table})` usage.

### Phase 3 (Rate limiting)

- Add **optional** rate limiting via `Flask-Limiter` controlled by env toggles.
- Apply stricter limits to the most expensive endpoints.

### Phase 5 (Docs)

- Fix inaccuracies in the audit docs to match the actual implementation.
- Add an implementation report under `docs/`.

## Non-Goals (Out of Scope for this iteration)

- Full user management / role-based authorization.
- CSRF protection and security headers (will be planned separately and implemented after confirmation).
- Full “public deployment” hardening (reverse proxy, HTTPS termination, WAF, etc.).

## Deliverables

1. Code changes
   - `ai_actuarial/web/app.py`: input validation, safe errors, `/api/logs/global` protection, rate limiting integration
   - `ai_actuarial/storage.py`: allowlist for schema table names
   - `.env.example`: new/updated toggles for rate limiting and log access
   - `requirements.txt`: add `Flask-Limiter` dependency (and keep optional behavior in code)
2. Docs changes
   - Update: `CODE_REVIEW_REPORT.md`, `REVIEW_SUMMARY.md`, `SECURITY.md` (accuracy)
   - New: `docs/20260210_security_hardening_phase1_3_5_report.md`
3. Tests
   - Run `pytest` on this branch and keep it green.

## Acceptance Criteria

- `pytest` passes.
- `GET /api/files?limit=999999` does not attempt to fetch an unbounded number of rows (clamped).
- 500 errors from API endpoints return a generic message (details only in logs).
- `/api/logs/global` is not publicly readable by default in a public deployment configuration.
- Rate limiting can be enabled/disabled via env and does not break the app when disabled.

## Rollout Notes

- For public exposure, treat `REQUIRE_AUTH=true` as a mandatory future step.
- Rate limiting defaults should be conservative behind a reverse proxy; ensure correct client IP handling.

