# Production Security Configuration

This repository keeps Caddy configuration limited to the app. Set hostnames,
the canonical redirect origin, and production-only security policy values on
the server through environment variables or a private `.env` file.

## Server-local values

Set these only on the deployment server:

- `CADDY_APP_SITE_HOSTS`: comma-separated public app hostnames.
- `CADDY_APP_REDIRECT_HOSTS`: space-separated HTTP hostnames accepted by the app redirect matcher.
- `CADDY_APP_REDIRECT_ORIGIN`: fixed trusted HTTPS origin, without a trailing slash; Caddy appends the original path and query.
- `FASTAPI_CORS_ORIGINS`: comma-separated browser origins allowed to call the API.
- `VITE_API_BASE_URL`: public API URL used by the frontend build.
- `FASTAPI_SESSION_SECRET`: strong random session secret.
- `TOKEN_ENCRYPTION_KEY`: stable Fernet key for encrypted provider credentials.
- `ENABLE_CSRF`: keep `true` in production unless there is a documented exception.
- `FASTAPI_SESSION_COOKIE_SECURE`: keep `true` behind HTTPS.
- `TRUST_PROXY`: set `true` only when direct API access is restricted to trusted reverse proxy traffic.
- `CONTENT_SECURITY_POLICY`: optional override when the frontend needs an explicit CSP change.

## API diagnostics and documentation

- Production (`FASTAPI_ENV=prod` or `production`) does not expose `/docs`,
  `/redoc`, or `/openapi.json`.
- Keep `GET /api/health` public for Caddy and container health checks.
- `GET /api/health/detailed` and production migration diagnostics require an
  admin API token with `logs.system.read`.
- Development and test environments keep the native FastAPI documentation
  routes available. Production migration inventory also requires
  `FASTAPI_ENABLE_MIGRATION_INVENTORY=1`.

Do not commit the server's real `.env` file.

## Agentic RAG production notes

Agentic RAG does not require new production secrets. It does create and read ready_data artifacts derived from catalog and chunk text, so treat those files as application data:

- Persist the database-adjacent `agentic_ready_data/` directory together with the configured SQLite database or other app data volume.
- Do not expose `data/`, `agentic_ready_data/`, converted Markdown, or downloaded source files as static public directories.
- Keep filesystem permissions aligned with the API process user; ready_data builds need write access under the database-adjacent data directory.
- Build ready_data manifests through the authenticated Knowledge UI or `/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build`; do not run ad hoc builders against untrusted output paths.
- Agentic read APIs require product permissions and should stay behind the same FastAPI authentication/CORS boundary as the rest of `/api/*`.

## Why this shape

- The committed `Caddyfile` is an app-only template. HTTP redirect hosts and the
  fixed HTTPS origin come from environment variables; unmatched HTTP hosts are
  rejected, and the `localhost` health endpoint remains available to Caddy.
- Local development defaults these values to `localhost`. The production
  Compose override requires `CADDY_APP_SITE_HOSTS`,
  `CADDY_APP_REDIRECT_HOSTS`, and `CADDY_APP_REDIRECT_ORIGIN` to be set.
- `config/sites.yaml` keeps safe public defaults for CSRF, CSP, and loopback
  server binding. Compose passes `CONTENT_SECURITY_POLICY` through from the
  server environment; when it is unset or blank, the FastAPI app and Caddy use
  their committed defaults instead of a second inline Compose default.

## Production startup

Use the production override after setting the server-local values:

```bash
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
```

## Shared host Caddy configuration

`Caddyfile.app` contains only this app's routes. The standalone `Caddyfile`
imports it from `/etc/caddy/app.caddy`; Compose mounts it at that generic path.
For a shared Caddy host, the local entrypoint imports the same app fragment and
keeps all other site routes and upstreams in server-local configuration. The
shared entrypoint owns global options once, including
`auto_https disable_redirects` so the configured fixed-origin redirect remains
in effect. This repository does not name or proxy independent sites.

Before replacing a shared single-file Caddy bind mount, operations must save and
prepare the other site configuration, then adapt and validate the combined
configuration. Replacing a host file can leave a single-file bind mount attached
to its previous inode. Compare hashes and inodes for the host file and the
container-mounted file, then inspect the active Caddy configuration and confirm
it matches the validated entrypoint. If the mount is stale, recreate the Caddy
container because reload reads the mounted file again and does not refresh the
mount. This repository change does not deploy the new variables or change
production configuration.

The override requires `FASTAPI_CORS_ORIGINS` and `VITE_API_BASE_URL`, so a
production deployment fails early if the server has not supplied its public
origin values.
