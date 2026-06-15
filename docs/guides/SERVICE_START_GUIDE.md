# Service Start Guide

This guide covers the current FastAPI + React service shape.

## Local Development

### 1. Install Python Dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 2. Install Frontend Dependencies

```powershell
npm install
```

### 3. Start FastAPI

Use port `8000` for local Vite proxy compatibility:

```powershell
python -m ai_actuarial api --host 127.0.0.1 --port 8000
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

### 4. Start React

```powershell
npm run dev
```

Open `http://127.0.0.1:5173/`. Vite proxies `/api/*` to FastAPI.

If `http://127.0.0.1:5173/` returns `404`, a different Node process is probably listening on that port. Restart the UI from this repository and use the URL printed by Vite:

```powershell
npm run dev
```

If Vite selects a different port, keep the browser on that printed URL. The API should still be `http://127.0.0.1:8000` unless you also changed `vite.config.ts`.

## Agentic RAG Local Checks

After the API has a populated database with knowledge-base chunk data, build a KB-scoped ready_data manifest:

```powershell
python -m ai_actuarial.agentic_rag.ready_data_builder --db data/index.db --kb-id <kb-id> --profile general --validate
python -m ai_actuarial.agentic_rag.ready_data_builder --db data/index.db --kb-id <kb-id> --profile regulation --validate
python -m ai_actuarial.agentic_rag.ready_data_builder --db data/index.db --kb-id <kb-id> --profile formula --validate
```

Run the deterministic Agentic eval smoke, which does not require provider keys:

```powershell
python -m ai_actuarial.agentic_rag.eval --mode agentic --cases eval/agentic_cases.jsonl --output-dir eval/fixtures/agentic_ready_data --profile formula --json
```

In the UI:

1. Open Knowledge and choose a KB `manifest_profile`.
2. Build the Agentic manifest.
3. Open Chat, switch from Standard to Agentic RAG, and select exactly one KB whose Agentic manifest is ready.

## Docker Compose

Start the stack:

```bash
docker compose up --build
```

Default ports:

- API: `5000` inside Docker, exposed as `${API_PORT:-5000}`
- Frontend: `${FRONTEND_PORT:-5173}`
- Caddy: `${CADDY_HTTP_PORT:-80}` and `${CADDY_HTTPS_PORT:-443}`

Production-style override:

```bash
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d --build
```

Set production secrets before using the override:

```bash
export FASTAPI_SESSION_SECRET=<strong-random-key>
export LOGS_READ_AUTH_TOKEN=<strong-random-token>
export CONFIG_WRITE_AUTH_TOKEN=<strong-random-token>
export TOKEN_ENCRYPTION_KEY=<fernet-key>
export FASTAPI_CORS_ORIGINS=https://<public-app-host>
export VITE_API_BASE_URL=https://<public-app-host>/api
export CADDY_APP_SITE_HOSTS=<public-app-host>[,www.<public-app-host>]
export CADDY_CROSS_SITE_HOST=<optional-secondary-host>
export CADDY_CROSS_UPSTREAM=<host-or-service>:<port>
```

## Update Helper

The update helper lives at `scripts/deploy_update.sh`.

```bash
APP_SERVICE_NAME=api bash scripts/deploy_update.sh
```

Useful overrides:

```bash
COMPOSE_FILE=docker-compose.yml APP_SERVICE_NAME=api bash scripts/deploy_update.sh
RELOAD_CADDY=true CADDY_CONTAINER=ai-caddy APP_SERVICE_NAME=api bash scripts/deploy_update.sh
```

## Common Environment Variables

- `FASTAPI_SESSION_SECRET`: required for session login.
- `TOKEN_ENCRYPTION_KEY`: required for decrypting database-stored provider credentials.
- `FASTAPI_CORS_ORIGINS`: comma-separated public frontend origins allowed to call the API.
- `VITE_API_BASE_URL`: public API URL embedded into the frontend build.
- `CADDY_APP_SITE_HOSTS`: public hostnames Caddy should serve for the main app.
- `CADDY_CROSS_SITE_HOST` / `CADDY_CROSS_UPSTREAM`: optional secondary host and upstream target.
- `features.require_auth` in `config/sites.yaml`: set to `true` to require authentication.
- `FASTAPI_ENV`: optional deployment override. If unset, FastAPI uses `config/sites.yaml -> server.fastapi_env`.
- `BOOTSTRAP_ADMIN_TOKEN`: optional local admin bootstrap token.
- Provider credentials: create them from Settings so they are stored encrypted in the DB.

## Troubleshooting

- Port in use: change FastAPI with `--port` and keep `vite.config.ts` proxy aligned.
- Missing provider key: add or repair the encrypted provider credential in Settings, then run `python scripts/diagnose_secrets_runtime.py --json`.
- Auth issues: check `features.require_auth`, `FASTAPI_SESSION_SECRET`, and `BOOTSTRAP_ADMIN_TOKEN`.
- Agentic RAG says no ready KB: build the KB's Agentic manifest from Knowledge or with `ready_data_builder --kb-id <kb-id> --profile <profile> --validate`.
- Agentic Chat rejects the request: select exactly one ready KB and remove direct selected-document context; Agentic mode intentionally does not combine with `document_sources`.
