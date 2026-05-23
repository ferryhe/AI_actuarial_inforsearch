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

## Why this shape

- The committed `Caddyfile` uses placeholder local hostnames and Caddy
  environment placeholders instead of real production domains.
- Docker Compose uses `host.docker.internal:host-gateway` for host-side
  upstreams instead of publishing a fixed bridge subnet or gateway.
- `config/sites.yaml` keeps safe public defaults for CSRF, CSP, and loopback
  server binding. Production Compose passes `CONTENT_SECURITY_POLICY` only when
  the server environment sets it, so the committed Compose files do not carry a
  second inline CSP default.

## Production startup

Use the production override after setting the server-local values:

```bash
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
```

The override requires `FASTAPI_CORS_ORIGINS` and `VITE_API_BASE_URL`, so a
production deployment fails early if the server has not supplied its public
origin values.
