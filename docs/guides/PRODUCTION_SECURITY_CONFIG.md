# Production Security Configuration

This repository keeps public deployment files generic. Real hostnames, host-only
upstream addresses, and production-only security policy values should be set on
the server through environment variables or a private `.env` file.

## Server-local values

Set these only on the deployment server:

- `CADDY_APP_SITE_HOSTS`: comma-separated public app hostnames.
- `CADDY_CROSS_SITE_HOST`: optional secondary hostname for the host-side app.
- `CADDY_CROSS_UPSTREAM`: host or service target for the secondary app.
- `FASTAPI_CORS_ORIGINS`: comma-separated browser origins allowed to call the API.
- `VITE_API_BASE_URL`: public API URL used by the frontend build.
- `FASTAPI_SESSION_SECRET`: strong random session secret.
- `TOKEN_ENCRYPTION_KEY`: stable Fernet key for encrypted provider credentials.
- `ENABLE_CSRF`: keep `true` in production unless there is a documented exception.
- `FASTAPI_SESSION_COOKIE_SECURE`: keep `true` behind HTTPS.
- `TRUST_PROXY`: set `true` only when direct API access is restricted to trusted reverse proxy traffic.
- `CONTENT_SECURITY_POLICY`: optional override when the frontend needs an explicit CSP change.

Do not commit the server's real `.env` file.

## Agentic RAG production notes

Agentic RAG does not require new production secrets. It does create and read ready_data artifacts derived from catalog and chunk text, so treat those files as application data:

- Persist the database-adjacent `agentic_ready_data/` directory together with the configured SQLite database or other app data volume.
- Do not expose `data/`, `agentic_ready_data/`, converted Markdown, or downloaded source files as static public directories.
- Keep filesystem permissions aligned with the API process user; ready_data builds need write access under the database-adjacent data directory.
- Build ready_data manifests through the authenticated Knowledge UI or `/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build`; do not run ad hoc builders against untrusted output paths.
- Agentic read APIs require product permissions and should stay behind the same FastAPI authentication/CORS boundary as the rest of `/api/*`.

## Why this shape

- The committed `Caddyfile` uses placeholder local hostnames and Caddy
  environment placeholders instead of real production domains.
- Docker Compose uses `host.docker.internal:host-gateway` for host-side
  upstreams instead of publishing a fixed bridge subnet or gateway.
- `config/sites.yaml` keeps safe public defaults for CSRF, CSP, and loopback
  server binding. Compose passes `CONTENT_SECURITY_POLICY` through from the
  server environment; when it is unset or blank, the FastAPI app and Caddy use
  their committed defaults instead of a second inline Compose default.

## Production startup

Use the production override after setting the server-local values:

```bash
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
```

The override requires `FASTAPI_CORS_ORIGINS` and `VITE_API_BASE_URL`, so a
production deployment fails early if the server has not supplied its public
origin values.
