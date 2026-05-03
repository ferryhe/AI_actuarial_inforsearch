# Deployment Runbook

## Overview

This document covers deployment, configuration, and operations for the AI Actuarial Info Search platform.

## Quick Start

```bash
# Development
docker compose up

# Production
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
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
cp data/index.db data/index.db.backup.$(date +%Y%m%d_%H%M%S)

# Restore from backup
cp data/index.db.backup.20260101_120000 data/index.db
```

## Environment Variables

Use environment variables for deployment secrets and explicit platform overrides. Main non-secret runtime configuration lives in `config/sites.yaml` and can be edited from the Web UI Settings page.

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TOKEN_ENCRYPTION_KEY` | Fernet key for encrypting API credentials in DB | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `FASTAPI_SESSION_SECRET` | Secret for FastAPI browser sessions | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |

### Provider Credentials

Provider API keys should be created from Settings and stored as encrypted DB credentials. Do not put provider keys in `config/sites.yaml`. Environment provider keys are supported only as temporary bootstrap/fallback values.

### Optional Overrides

| Variable | Default | Description |
|----------|---------|-------------|
| `FASTAPI_ENV` | `config/sites.yaml -> server.fastapi_env` | Deployment environment override. Use `production` in production; if unset, the YAML server value is used. |

`config/sites.yaml -> paths.db` is the canonical SQLite path. `DB_PATH` remains supported only as a legacy fallback when that YAML value is absent; do not set both for normal deployments.

## Configuration Files

### `config/sites.yaml`

Most runtime configuration is in `config/sites.yaml` (AI models, RAG settings, feature flags, server settings). Edit via the Web UI Settings page or directly. `server.fastapi_env` is used as the default FastAPI environment when `FASTAPI_ENV` is not set. Changes to Settings-managed values are applied to the running FastAPI process; a restart is still needed after changing process environment variables such as `TOKEN_ENCRYPTION_KEY`, `FASTAPI_SESSION_SECRET`, or `FASTAPI_ENV`.

### `config/sites.yaml` Structure

```yaml
defaults:
  user_agent: 'AI-Actuarial-InfoSearch/0.1 (+contact: you@example.com)'
  max_pages: 200
  max_depth: 2
  delay_seconds: 0.5
paths:
  download_dir: data/files
  db: data/index.db
search:
  enabled: true
  max_results: 5
  languages:
  - en
  - zh
ai_config:
  catalog:
    provider: openai
    model: gpt-4o-mini
  embeddings:
    provider: openai
    model: text-embedding-3-large
    similarity_threshold: 0.4
  chatbot:
    provider: openai
    model: gpt-4-turbo
    temperature: 0.7
    max_tokens: 1000
rag_config:
  chunk_strategy: semantic_structure
  max_chunk_tokens: 800
  min_chunk_tokens: 100
  index_type: Flat
features:
  require_auth: false
  enable_global_logs_api: false
  enable_rate_limiting: true
  rate_limit_defaults: '200 per hour, 50 per minute'
  rate_limit_storage_uri: memory://
  enable_csrf: false
  enable_security_headers: true
  expose_error_details: false
  content_security_policy: ''
server:
  host: 0.0.0.0
  port: 5000
  max_content_length: 52428800
sites:
- name: Example Site
  url: https://example.com
  keywords:
  - artificial intelligence
  - machine learning
```

## Common Troubleshooting

### API returns 401 Unauthorized

- Ensure `require_auth: false` (in `sites.yaml`) for development, or configure valid credentials.
- Check that `TOKEN_ENCRYPTION_KEY` is set and stable across restarts.

### Rate limit errors (429)

- Rate limiting is role-based. Adjust `features.enable_rate_limiting` in `sites.yaml` or from Settings.
- Role-based limits: guest=10/min, registered=30/min, premium=60/min, operator=200/min.

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

- Check that documents have been indexed: POST `/api/rag/knowledge-bases/{kb_id}/index`
- Verify embedding model is configured in `sites.yaml` under `ai_config.embeddings`
- Check similarity threshold — too high may filter all results

## Backup & Restore

### Files to Back Up

1. **Database**: `data/index.db`
2. **Configuration**: `config/sites.yaml`
3. **Environment**: `.env` (secrets only — store securely, never in version control)
4. **Uploaded files**: `data/files/` (if using file storage)

### Backup Script

```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="./backups/$DATE"
mkdir -p "$BACKUP_DIR"
cp data/index.db "$BACKUP_DIR/"
cp config/sites.yaml "$BACKUP_DIR/"
echo "Backup saved to $BACKUP_DIR"
```

### Restore

```bash
# Stop services
docker compose down

# Replace files
cp backups/20260101_120000/index.db data/
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

# Note: Database schema migrations are applied automatically on startup.
# There is no separate `db migrate` command; the application handles schema
# upgrades internally via the db_backend module when it starts.
```
