# Security Policy

## Supported Versions

This project is currently in version 0.1.x. Security updates are provided for the latest release on `main`.

| Version | Supported |
| --- | --- |
| 0.1.x | :white_check_mark: |

---

## Reporting a Vulnerability

If you discover a security vulnerability in this project:

1. **Do not** create a public GitHub issue.
2. Contact the maintainers privately with:
   - vulnerability description;
   - steps to reproduce;
   - potential impact;
   - suggested fix, if available.
3. Allow reasonable time for triage and remediation.
4. Public disclosure should be coordinated with the maintainers.

Do not include real API keys, tokens, database files, or private user documents in vulnerability reports unless explicitly requested through a private channel.

---

## Current Security Posture

The active application is FastAPI + React. Legacy Flask-era guidance is archived under `docs/archive/security/` and should not be used as an implementation checklist.

### Authentication And Authorization

- Browser session login/register is implemented by native FastAPI auth endpoints.
- Token-based access remains available for compatibility and admin/recovery flows.
- `features.require_auth=true` requires session or token authentication.
- `features.require_auth=false` allows read-only guest access while write/admin operations remain permission-gated.
- Permissions are role-based and split by operation class, including `sites.write`, `schedule.write`, `tasks.run`, and `files.import.server`.
- `operator` can manage configured sites but does not receive `files.import.server`; that permission is reserved for admin-only server filesystem helper surfaces.
- `BOOTSTRAP_ADMIN_TOKEN` can be used as a local recovery mechanism. Do not commit real tokens.

### Credential And Secret Handling

- Provider API keys should be stored as encrypted database credentials managed from Settings.
- `TOKEN_ENCRYPTION_KEY` must be stable for encrypted credential decryption.
- `.env` is for process secrets and deployment overrides only; do not commit it.
- Diagnostics scripts are expected to report key names/status without printing secret values.

### Request Boundary Controls

- Public login/register credential submissions are IP-scoped rate limited before session mutation.
- Search/chat/collection endpoints have role/default rate limits when `features.enable_rate_limiting=true`.
- `OPTIONS` CORS preflight requests skip rate limiting.
- `TRUST_PROXY` controls whether `X-Forwarded-For` is trusted for client IP resolution; enable it only behind a trusted reverse proxy.
- CSRF protection, security headers, error-detail exposure, and CORS origins are controlled by `config/sites.yaml -> features` and deployment environment overrides.

### File And URL Handling

- Normal file import uses browser-selected upload batches from the user's machine.
- `type=file` collection runs require an `upload_batch_id`; requests that supply only `directory_path` are rejected.
- API responses should not expose arbitrary absolute server paths.
- Public URL fetching includes SSRF defenses: scheme checks, private/reserved address rejection, redirect revalidation, and DNS/IP drift checks.
- File deduplication uses SHA256.

### Chat/RAG Boundary Controls

- Selected document comparison is limited to 3 document sources per request.
- Document context has per-source and total-size bounds; the API returns truncation metadata and the UI displays a truncation notice.
- Retrieved/document context is labeled as untrusted before being passed to the LLM and must not override system, developer, permission, tool, or output-format instructions.

---

## Production Deployment Checklist

### Required Secrets And Environment

- [ ] Set `FASTAPI_SESSION_SECRET` to a strong random value when session auth is enabled.
- [ ] Set `TOKEN_ENCRYPTION_KEY` to a stable Fernet key before storing encrypted provider credentials.
- [ ] Configure `FASTAPI_CORS_ORIGINS` with explicit browser origins in production.
- [ ] Set `FASTAPI_SESSION_COOKIE_SECURE=true` behind HTTPS.
- [ ] Set `TRUST_PROXY=true` only when direct API access is restricted to trusted reverse proxy traffic.
- [ ] Keep any server `.env` file private and out of git.

Generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Generate a random token:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Application Configuration

- [ ] Enable `features.require_auth` for non-public deployments.
- [ ] Enable `features.enable_rate_limiting` for public deployments.
- [ ] Keep CSRF enabled unless there is a documented exception.
- [ ] Keep security headers enabled and configure CSP consciously.
- [ ] Review role assignments for admin/operator users.
- [ ] Ensure only admins have `files.import.server`.
- [ ] Store provider credentials through Settings rather than committing keys to config files.

### Infrastructure

- [ ] Serve over HTTPS.
- [ ] Put FastAPI behind a trusted reverse proxy such as Caddy or Nginx.
- [ ] Restrict direct API container/host access so only the trusted proxy can reach it when `TRUST_PROXY=true`.
- [ ] Use explicit firewall rules and expose only necessary ports.
- [ ] Configure backups for the database and uploaded/downloaded files.
- [ ] For production scale-out, do not rely on process-local `memory://` rate limiting; add a shared backend first.

### Monitoring And Maintenance

- [ ] Review logs for failed login bursts, unexpected 429 spikes, SSRF rejection events, and repeated 5xx errors.
- [ ] Rotate credentials when personnel or deployment ownership changes.
- [ ] Run dependency audits periodically, for example `pip-audit` and npm audit tooling.
- [ ] Re-run focused security tests after changing auth, rate limiting, file import, URL fetch, or Chat/RAG prompt-boundary code.

---

## Security-Focused Verification Commands

```bash
python -m pytest tests/test_fastapi_auth_endpoints.py tests/test_auth_react_source.py -q
python -m pytest tests/test_fastapi_chat_endpoints.py tests/test_chat_react_source.py -q
python -m pytest tests/test_fastapi_ops_write_endpoints.py tests/test_tasks_react_source.py tests/unit/test_permissions.py -q
npm run build
```

For production configuration notes, see [docs/guides/PRODUCTION_SECURITY_CONFIG.md](docs/guides/PRODUCTION_SECURITY_CONFIG.md). For rate-limit response details, see [docs/rate-limit-config.md](docs/rate-limit-config.md).
