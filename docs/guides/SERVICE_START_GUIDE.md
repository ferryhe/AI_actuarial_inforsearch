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
export CADDY_DOMAIN=<domain>
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
- `features.require_auth` in `config/sites.yaml`: set to `true` to require authentication.
- `BOOTSTRAP_ADMIN_TOKEN`: optional local admin bootstrap token.
- Provider credentials: create them from Settings so they are stored encrypted in the DB.

## Troubleshooting

- Port in use: change FastAPI with `--port` and keep `vite.config.ts` proxy aligned.
- Missing provider key: add or repair the encrypted provider credential in Settings, then run `python scripts/diagnose_secrets_runtime.py --json`.
- Auth issues: check `features.require_auth`, `FASTAPI_SESSION_SECRET`, and `BOOTSTRAP_ADMIN_TOKEN`.
