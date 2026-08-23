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
# Resolve the real production data path. Do not use the repository's data/ path.
DATA_VOLUME=ai_actuarial_inforsearch_ai-data
DATA_DIR=$(docker volume inspect "$DATA_VOLUME" --format '{{ .Mountpoint }}')
BACKUP_ROOT=/mnt/aiinforsearch-backup/aiinforsearch

# Online SQLite + configuration backup. Output is JSON and the database copy is
# created with sqlite3's backup API, followed by PRAGMA quick_check.
sudo python3 scripts/production_recovery.py backup \
  --data-dir "$DATA_DIR" \
  --config config/sites.yaml \
  --backup-root "$BACKUP_ROOT"
```

The production SQLite database is `/app/data/index.db` inside `ai-api` and
`/var/lib/docker/volumes/ai_actuarial_inforsearch_ai-data/_data/index.db` with
the current Compose project name. Always resolve the mountpoint with
`docker volume inspect`; never assume a repository-local host `data/` directory.

## Environment Variables

Use environment variables for deployment secrets and explicit platform overrides. Main non-secret runtime configuration lives in `config/sites.yaml` and can be edited from the Web UI Settings page.

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TOKEN_ENCRYPTION_KEY` | Fernet key for encrypting API credentials in DB | `python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"` |
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

### Backup scopes

The recovery tool has two scopes:

- Default: online SQLite backup plus `config/sites.yaml`. This is suitable for a
  scheduled daily job and does not copy `.env` or reveal credentials.
- `--include-data --quiesced`: SQLite plus `rag/` and `agentic_ready_data/`.
  Re-crawlable source documents under `files/` are intentionally excluded from
  full snapshots (their metadata is still captured in the database backup).
  Stop application writers first so the database and index artifacts share one
  recovery point.

Each run appends a success or failure record to `backup-events.jsonl`. A
successful snapshot is published only after its database passes
`PRAGMA quick_check`; its manifest records checksums, WAL checkpoint results,
directory sizes, and `PRAGMA user_version`.

### Daily verified database backup

The repository includes a systemd service and timer template. Review the paths,
then install them during an approved operations change:

```bash
sudo install -d -m 0750 /etc/aiinforsearch
# The mount must already exist and be distinct from the production volume.
findmnt -M /mnt/aiinforsearch-backup
sudo install -d -m 0700 /mnt/aiinforsearch-backup/aiinforsearch
echo 'BACKUP_ROOT=/mnt/aiinforsearch-backup/aiinforsearch' | sudo tee /etc/aiinforsearch/backup.conf
sudo chmod 0600 /etc/aiinforsearch/backup.conf
sudo install -m 0644 ops/systemd/aiinforsearch-backup.service /etc/systemd/system/
sudo install -m 0644 ops/systemd/aiinforsearch-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aiinforsearch-backup.timer
sudo systemctl start aiinforsearch-backup.service
sudo systemctl status aiinforsearch-backup.service --no-pager
```

### Weekly quiesced full snapshot

A second service and timer capture `rag/` and `agentic_ready_data/` on top of
the database by briefly stopping the API (a quiesced snapshot). Install it
alongside the daily job with its own config and full-snapshot root:

```bash
sudo install -d -m 0700 /mnt/aiinforsearch-backup/aiinforsearch-full
echo 'BACKUP_ROOT=/mnt/aiinforsearch-backup/aiinforsearch-full' | sudo tee /etc/aiinforsearch/full-backup.conf
sudo chmod 0600 /etc/aiinforsearch/full-backup.conf
sudo install -m 0644 ops/systemd/aiinforsearch-full-backup.service /etc/systemd/system/
sudo install -m 0644 ops/systemd/aiinforsearch-full-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aiinforsearch-full-backup.timer
```

The wrapper stops only the API container, runs the quiesced snapshot, and
restarts the API through an EXIT/INT/TERM trap even if the snapshot fails. It
reuses the same shared lock as the daily backup and deployment snapshot, skips
the run when a write task is active, and retains 30 days via
`--retention-days 30`. The timer is evaluated in the host's local timezone
(Asia/Shanghai CST on the production host); `RandomizedDelaySec=15m` shifts the
actual start up to 15 minutes later.

The scheduled job is database-plus-configuration only, so it does not stop the
API. The service fails closed if `/etc/aiinforsearch/backup.conf` is absent, if
the configured directory is missing, or if it is on the production data
filesystem. The wrapper also uses a shared non-blocking lock so a daily backup
cannot overlap a deployment snapshot. Every wrapper passes `--retention-days 30`,
so published snapshots older than 30 days are pruned automatically after each
successful backup; keep at least one off-host copy before relying on pruning.
Do not configure a FUSE/object-storage mount such as COSFS until its
write, rename, interruption, and read-back checksum semantics have been
qualified in a disposable prefix.

### Capacity gate

```bash
python3 scripts/production_recovery.py capacity-check --path / --threshold 80
```

Exit code `3` means the threshold has been reached. At or above 80%, do not run
full artifact retention, reclassification, full indexing, or a deployment that
needs a same-disk snapshot. Expand the disk or move immutable artifacts/backups
to separate storage first.

### Quiesced database-and-files snapshot

```bash
DATA_VOLUME=ai_actuarial_inforsearch_ai-data
DATA_DIR=$(docker volume inspect "$DATA_VOLUME" --format '{{ .Mountpoint }}')
BACKUP_ROOT=/mnt/aiinforsearch-backup/aiinforsearch
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.override.yml"

$COMPOSE stop api
sudo python3 scripts/production_recovery.py backup \
  --data-dir "$DATA_DIR" \
  --config config/sites.yaml \
  --backup-root "$BACKUP_ROOT" \
  --include-data \
  --quiesced
$COMPOSE start api
```

If backup creation fails after the API is stopped, restart the unchanged API
before investigating. A maintenance-window wrapper should use a shell `trap` to
guarantee that restart; do not paste these commands into unattended automation.

Back up `.env` separately in the approved secret store. The recovery tool never
reads or copies it.

### Verify and rehearse a restore

```bash
BACKUP_DIR=/mnt/aiinforsearch-backup/aiinforsearch/backup-<UTC timestamp>
RESTORE_DIR=/mnt/aiinforsearch-backup/restore-smoke-<UTC timestamp>

python3 scripts/production_recovery.py verify "$BACKUP_DIR"
python3 scripts/production_recovery.py restore-smoke "$BACKUP_DIR" \
  --restore-dir "$RESTORE_DIR"
```

`restore-smoke` refuses a non-empty target. It verifies checksums, opens the
restored SQLite database read-only, runs `PRAGMA quick_check`, reports file/KB/
ready-manifest counts, and checks that database file paths exist in the isolated
copy. It never replaces the live named volume.

After that check, an operator may start the restored copy in an unexposed
container and call only GET smoke endpoints:

```bash
IMAGE=ai_actuarial_inforsearch-api:latest
RESTORE_SMOKE_KEY=$(python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())')
docker run --rm -d --name ai-restore-smoke \
  -e FASTAPI_ENV=development \
  -e FASTAPI_SESSION_SECRET=restore-smoke-only \
  -e TOKEN_ENCRYPTION_KEY="$RESTORE_SMOKE_KEY" \
  -v "$RESTORE_DIR/data:/app/data:rw" \
  -v "$RESTORE_DIR/config/sites.yaml:/app/config/sites.yaml:ro" \
  "$IMAGE"
docker exec ai-restore-smoke curl -fsS http://127.0.0.1:5000/api/health
docker exec ai-restore-smoke curl -fsS http://127.0.0.1:5000/api/rag/knowledge-bases
docker stop ai-restore-smoke
```

The smoke container has no published port and operates only on the isolated
restore. Record its image digest and results in the recovery rehearsal log.

### Release traceability

Builds must supply the Git SHA, dirty flag, UTC timestamp, and source URL:

```bash
export BUILD_GIT_SHA=$(git rev-parse HEAD)
export BUILD_GIT_DIRTY=false
export BUILD_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
export BUILD_SOURCE_URL=https://github.com/ferryhe/AI_actuarial_inforsearch
docker compose build api
```

After the image is built, write a release record containing its digest, safe OCI
labels, configuration checksum, and SQLite `PRAGMA user_version`:

```bash
DATA_VOLUME=ai_actuarial_inforsearch_ai-data
DATA_DIR=$(docker volume inspect "$DATA_VOLUME" --format '{{ .Mountpoint }}')
python3 scripts/production_recovery.py release-record \
  --image ai_actuarial_inforsearch-api:latest \
  --config config/sites.yaml \
  --db "$DATA_DIR/index.db" \
  --output /var/lib/aiinforsearch/releases/"$BUILD_GIT_SHA".json
```

`PRAGMA user_version` is the current explicit schema-version field. Legacy
databases may still report `0` until the reviewed migration runner assigns the
repository baseline. A schema-changing deployment must run the explicit,
idempotent SQLite preflight after verified backup and before application
startup:

```bash
ai-actuarial schema status --db "$DATA_DIR/index.db" --json
ai-actuarial schema plan --db "$DATA_DIR/index.db" --json
ai-actuarial schema apply --db "$DATA_DIR/index.db" --json
```

Do not treat the application's historical startup-time `CREATE/ALTER` behavior
as a sufficient production migration plan.

### Live restore and rollback

Replacing the live named volume is a separate, destructive production action.
It requires explicit authorization, a maintenance window, a verified isolated
restore, and the rollback checklist from the release Issue. Do not restore by
copying files into a running container or by using `docker compose down -v`.


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
# The guarded updater refuses a dirty worktree or root-disk use >=80%, creates a
# quiesced full snapshot, fast-forwards main, builds with OCI revision labels,
# restarts the API, and writes a release record.
scripts/deploy_update.sh
```

The updater intentionally refuses the known production
`.hermes/project-status.md` modification. Preserve it outside the checkout and
review it before retrying; do not reset, overwrite, or silently stash it. The
script also requires a successful full snapshot before changing the running API.
