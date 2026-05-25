# Project Status

- Date: 2026-05-25
- Branch: `feat/auth-rate-limit-ui`
- Latest baseline: `origin/main` after PR #121 Chat/RAG request boundaries merged.
- Scope: PR4 security hardening for login/register rate limiting plus 429/system-error UI. Sibling repositories were not read or modified.
- Backend auth rate limit: `/api/auth/login` and `/api/auth/register` are now rate-limited as public credential POST mutations before session mutation work.
- Backend auth limit policy: default auth mutation limit is 5 requests/minute per endpoint and client IP.
- Proxy handling: auth rate-limit IP key respects trusted `X-Forwarded-For` only when `TRUST_PROXY` is enabled.
- CORS handling: auth 429 responses include `Retry-After` and preserve allowed CORS headers so browser clients can surface the 429 UI.
- Preflight handling: `OPTIONS` requests skip rate limiting.
- Non-auth compatibility: existing role/default endpoint 429 detail remains human-readable and does not gain the auth-specific `error` field.
- Frontend login/register UX: 429 errors show localized “too many attempts” copy; 5xx errors show localized service-unavailable copy.
- Tests: FastAPI auth tests cover login limit, register limit, CORS preflight skip, trusted forwarded IP separation, CORS headers on auth 429, and non-auth 429 compatibility.
- Tests: React auth source test covers 429/system error handling and Chinese translations.
- Verification passed: `/home/ec2-user/.hermes/hermes-agent/venv/bin/python -m pytest tests/test_fastapi_auth_endpoints.py tests/test_auth_react_source.py -q` (20 passed, 3 warnings).
- Frontend build passed: `npm run build` from `client/`.
- Diff whitespace check passed: `git diff --check`.
- Local Codex review gate passed after fixing CORS and Retry-After rounding findings.
- Next step: commit/push PR4 branch, create PR, then check remote CI/comments after the usual follow-up window.
