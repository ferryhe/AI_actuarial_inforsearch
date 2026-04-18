# Deployment Runbook

## Overview

This document covers deployment, configuration, and operations for the AI Actuarial Info Search platform.

## Quick Start

```bash
# Development
docker compose up

# Production
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Docker Compose Commands

### Start Services

```bash
# Start all services in detached mode
docker compose up -d

# Start with logs streaming
docker compose up

# Rebuild before starting (after code changes)
docker compose up --build -d
```

### Stop Services

```bash
# Stop containers (preserves volumes)
docker compose down

# Stop and remove volumes (destroys data)
docker compose down -v
```

### Inspect & Debug

```bash
# View running containers
docker compose ps

# View logs
docker compose logs -f

# Follow logs for a specific service
docker compose logs -f api

# Open a shell in a running container
docker compose exec api sh
```

### Database Operations

```bash
# Backup the SQLite database
cp data/ai_actuarial.db data/ai_actuarial.db.backup.$(date +%Y%m%d_%H%M%S)

# Restore from backup
cp data/ai_actuarial.db.backup.20260101_120000 data/ai_actuarial.db
```

## Environment Variables

All configuration is via environment variables. Copy `.env.example` to `.env` and configure:

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | Flask session secret key | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `TOKEN_ENCRYPTION_KEY` | Fernet key for encrypting API credentials in DB | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

### API Keys

| Variable | Provider | Get from |
|----------|----------|----------|
| `OPENAI_API_KEY` | OpenAI | <https://platform.openai.com/api-keys> |
| `BRAVE_API_KEY` | Brave Search | <https://brave.com/search/api/> |
| `SERPAPI_API_KEY` | SerpAPI | <https://serpapi.com/> |
| `MISTRAL_API_KEY` | Mistral | <https://console.mistral.ai/> |
| `SILICONFLOW_API_KEY` | SiliconFlow | <https://siliconflow.cn/> |

### Optional Overrides

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible API base URL |
| `MISTRAL_BASE_URL` | `https://api.mistral.ai` | Mistral API base URL |
| `DATABASE_PATH` | `./data/ai_actuarial.db` | SQLite database path |

## Configuration Files

### `config/sites.yaml`

Most runtime configuration is in `config/sites.yaml` (AI models, RAG settings, feature flags, server settings). Edit via the Web UI Settings page or directly. Changes take effect immediately without restart.

### `config/sites.yaml` Structure

```yaml
catalog:
  model: gpt-4o
  embedding_model: text-embedding-3-large
chatbot:
  model: gpt-4o
  temperature: 0.7
  max_tokens: 1000
rag:
  chunk_strategy: semantic_structure
  max_chunk_tokens: 800
  similarity_threshold: 0.4
features:
  require_auth: false
  rate_limit_enabled: true
server:
  host: 0.0.0.0
  port: 5000
  max_content_length: 52428800
```

## Common Troubleshooting

### API returns 401 Unauthorized

- Ensure `REQUIRE_AUTH=false` (in `sites.yaml`) for development, or configure valid credentials.
- Check that `SECRET_KEY` is set and stable across restarts.

### Rate limit errors (429)

- Rate limiting is enabled by default. Adjust in `sites.yaml` or set `RATE_LIMIT_ENABLED=false` for development.
- Per-endpoint limits: auth=20/min, chat=30/min, read=100/min, meta=200/min.

### Database locked errors

- Only one write process at a time is supported with SQLite.
- For multi-instance deployments, migrate to a PostgreSQL-compatible backend.

### Provider credential errors

- Ensure `TOKEN_ENCRYPTION_KEY` is set. If lost/changed, previously stored credentials become unreadable.
- Re-enter provider API keys via the Web UI Settings page after fixing the key.

### Container won't start

```bash
# Check logs for errors
docker compose logs api

# Verify .env file exists and is populated
cat .env

# Verify ports are not in use
ss -tlnp | grep 5000
```

### RAG / search not returning results

- Check that documents have been indexed: POST `/api/rag-admin/index`
- Verify embedding model is configured in `sites.yaml`
- Check similarity threshold — too high may filter all results

## Backup & Restore

### Files to Back Up

1. **Database**: `data/ai_actuarial.db`
2. **Configuration**: `config/sites.yaml`
3. **Environment**: `.env` (secrets only — store securely, never in version control)
4. **Uploaded files**: `data/uploads/` (if using file storage)

### Backup Script

```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="./backups/$DATE"
mkdir -p "$BACKUP_DIR"
cp data/ai_actuarial.db "$BACKUP_DIR/"
cp config/sites.yaml "$BACKUP_DIR/"
echo "Backup saved to $BACKUP_DIR"
```

### Restore

```bash
# Stop services
docker compose down

# Replace files
cp backups/20260101_120000/ai_actuarial.db data/
cp backups/20260101_120000/sites.yaml config/

# Restart
docker compose up -d
```

## API Documentation

Once running, interactive API docs are available at:

- **Swagger UI**: `http://localhost:5000/docs`
- **ReDoc**: `http://localhost:5000/redoc`
- **OpenAPI JSON**: `http://localhost:5000/openapi.json`

## Health Checks

```bash
# Basic health
curl http://localhost:5000/api/health

# Detailed health (includes version and service status)
curl http://localhost:5000/api/health/detailed
```

## Updating the Service

```bash
# Pull latest code
git pull origin main

# Rebuild Docker image
docker compose build

# Restart
docker compose up -d

# Run any DB migrations
docker compose exec api python -m ai_actuarial db migrate  # if applicable
```
