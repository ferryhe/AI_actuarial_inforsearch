# 20260208 Service Start Guide (Linux + Windows)

This guide describes how to start the AI Actuarial Info Search service locally on Windows and on a Linux server with Docker + Caddy.

## Linux Server (Docker + Caddy)

### Start / Update Service (one command)

Use the root script `deploy_update.sh`.

```bash
# From repo root
chmod +x deploy_update.sh
./deploy_update.sh
```

### Common Overrides

```bash
# If your compose file is named differently
COMPOSE_FILE=docker-compose.prod.yml ./deploy_update.sh

# If your service name differs in compose
APP_SERVICE_NAME=ai-actuarial-app ./deploy_update.sh

# If you want to reload Caddy (when Caddyfile changed)
RELOAD_CADDY=true CADDY_CONTAINER=caddy ./deploy_update.sh
```

### Notes

- The script runs `git pull`, rebuilds the target service, and restarts only that service.
- It does **not** restart other services, so it’s safe for hosts with 5–6 existing web services.
- If you changed Caddy config, set `RELOAD_CADDY=true`.

## Windows (Local Development)

### 1. Create and activate virtual environment

```powershell
python -m venv .venv
# If PowerShell blocks activation, use:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Start the web service

```powershell
python -m ai_actuarial web
```

Open `http://localhost:5000` in your browser.

### Optional: Use venv Python without activation

```powershell
.\.venv\Scripts\python -m ai_actuarial web
```

---

## Service Variables (Optional)

- `BRAVE_API_KEY` / `SERPAPI_API_KEY` for web search expansion
- `ENABLE_FILE_DELETION=true` to enable file deletion in UI

---

## Troubleshooting

- **Port in use**: Start with `python -m ai_actuarial web --port 8080`
- **PowerShell execution policy**: Use the Process scope bypass as shown above
