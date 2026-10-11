# Deployment Runbook

## Overview

This document covers deployment, configuration, and operations for the AI Actuarial Info Search platform.

## Quick Start

```bash
# Development
docker compose up

# Production
export CONFIG_PATH=/var/lib/aiinforsearch/config/sites.yaml
export RUNTIME_CONFIG_DIR=/var/lib/aiinforsearch/config
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
# Resolve the real application data path. PostgreSQL runs independently of this volume.
DATA_VOLUME=ai_actuarial_inforsearch_ai-data
DATA_DIR=$(docker volume inspect "$DATA_VOLUME" --format '{{ .Mountpoint }}')
BACKUP_ROOT=/mnt/aiinforsearch-backup/aiinforsearch
CONFIG_PATH=/var/lib/aiinforsearch/config/sites.yaml
# DATABASE_URL must already be available from a private shell environment or secret store.

# Online PostgreSQL + configuration backup. Keep DATABASE_URL in the private
# process environment/secret store; the tool does not print credentials.
DATABASE_URL="$DATABASE_URL" sudo --preserve-env=DATABASE_URL python3 scripts/production_recovery.py backup \
  --data-dir "$DATA_DIR" \
  --config "$CONFIG_PATH" \
  --backup-root "$BACKUP_ROOT" --json
```

`DATABASE_URL` selects PostgreSQL. `paths.data` or `DATA_DIR` selects the
separate writable directory for downloads, logs, upload batches and RAG/Ready
Data artifacts. Set the latter to an absolute path such as
`D:/AI_actuarial_inforsearch/data` for a local Windows installation. PostgreSQL
schema status/apply and the one-source SQLite v16 importer are documented in
[the database guide](guides/DATABASE_BACKEND_GUIDE.md).

## Environment Variables

Use environment variables for deployment secrets and explicit platform overrides. In production, `CONFIG_PATH` names the external writable `sites.yaml` used by every reader and writer. The tracked `config/sites.yaml` is only a development default and bootstrap template. See [Runtime configuration ownership](runtime-config.md).

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TOKEN_ENCRYPTION_KEY` | Fernet key for encrypting API credentials in DB | `python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"` |
| `FASTAPI_SESSION_SECRET` | Secret for FastAPI browser sessions | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `CONFIG_PATH` | Absolute host path to the external writable runtime configuration | `/var/lib/aiinforsearch/config/sites.yaml` |
| `RUNTIME_CONFIG_DIR` | Directory mounted into the API container for atomic configuration writes | `/var/lib/aiinforsearch/config` |
| `DATABASE_URL` | PostgreSQL connection URL for API, tasks, CLI and native backup tools | private secret value |

### Provider Credentials

Provider API keys should be created from Settings and stored as encrypted DB credentials. Do not put provider keys in `config/sites.yaml`. Environment provider keys are supported only as temporary bootstrap/fallback values.

### Optional Overrides

| Variable | Default | Description |
|----------|---------|-------------|
| `FASTAPI_ENV` | `config/sites.yaml -> server.fastapi_env` | Deployment environment override. Use `production` in production; if unset, the YAML server value is used. |

PostgreSQL is the only application database. `database.url_env` may name an
environment variable other than `DATABASE_URL`; it must contain a PostgreSQL
URL. There is no SQLite runtime path or `DB_PATH` fallback. The independent
`paths.data`/`DATA_DIR` setting controls local files and artifacts.

## Configuration Files

### Runtime `sites.yaml`

Most runtime configuration is in the file named by `CONFIG_PATH` (AI models, RAG settings, feature flags, server settings). Edit via the Web UI Settings page or directly. Settings writes are flushed and atomically replace this file. Production startup fails if the path is missing, invalid, unreadable, unwritable, or points to the tracked template. `server.fastapi_env` is used as the default FastAPI environment when `FASTAPI_ENV` is not set. Changes to Settings-managed values are applied to the running FastAPI process; a restart is still needed after changing process environment variables such as `TOKEN_ENCRYPTION_KEY`, `FASTAPI_SESSION_SECRET`, or `FASTAPI_ENV`.

### `sites.yaml` structure

```yaml
defaults:
  user_agent: 'AI-Actuarial-InfoSearch/0.1 (+contact: you@example.com)'
  max_pages: 200
  max_depth: 2
  delay_seconds: 0.5
paths:
  data: /var/lib/aiinforsearch/data
  download_dir: data/files
database:
  type: postgresql
  url_env: DATABASE_URL
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

- Check PostgreSQL connectivity, transaction errors and database capacity.
- PostgreSQL is the supported runtime; do not switch to a local SQLite file.

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

- Default: online PostgreSQL dump plus `config/sites.yaml`. This is suitable for a
  scheduled daily job and does not copy `.env` or reveal credentials.
- `--include-data --quiesced`: PostgreSQL plus `rag/` and `agentic_ready_data/`.
  Re-crawlable source documents under `files/` are intentionally excluded from
  full snapshots (their metadata is still captured in PostgreSQL). Keep a
  separate backup/transfer of raw originals before removing any old copy.
  Stop application writers first so the database and index artifacts share one
  recovery point.

Each run appends a success or failure record to `backup-events.jsonl`. A
successful PostgreSQL dump is checked with matching-major-version native
clients before publication; its manifest records checksums, schema version,
directory sizes, and the included data directories.

### Daily verified database backup

The repository includes a systemd service and timer template. Review the paths,
then install them during an approved operations change:

```bash
sudo install -d -m 0750 /etc/aiinforsearch
# The mount must already exist and be distinct from the production volume.
findmnt -M /mnt/aiinforsearch-backup
sudo install -d -m 0700 /mnt/aiinforsearch-backup/aiinforsearch
sudo install -m 0600 /dev/null /etc/aiinforsearch/backup.conf
sudoedit /etc/aiinforsearch/backup.conf
sudo install -m 0644 ops/systemd/aiinforsearch-backup.service /etc/systemd/system/
sudo install -m 0644 ops/systemd/aiinforsearch-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aiinforsearch-backup.timer
sudo systemctl start aiinforsearch-backup.service
sudo systemctl status aiinforsearch-backup.service --no-pager
```

The private `backup.conf` must define `BACKUP_ROOT`, `CONFIG_PATH`, and the
database connection variable selected by the application (`DATABASE_URL` by
default, or the name configured by `url_env`). Enter the connection value with
`sudoedit` or a secret manager; do not put it in a `tee` command or terminal
output. The PostgreSQL endpoint must be reachable from the host running this
backup service. For a loopback-published database container, use the host's
loopback address and published port.

### Weekly quiesced full snapshot

A second service and timer capture `rag/` and `agentic_ready_data/` on top of
the database by briefly stopping the API (a quiesced snapshot). Install it
alongside the daily job with its own config and full-snapshot root:

```bash
sudo install -d -m 0700 /mnt/aiinforsearch-backup/aiinforsearch-full
sudo install -m 0600 /dev/null /etc/aiinforsearch/full-backup.conf
sudoedit /etc/aiinforsearch/full-backup.conf
sudo install -m 0644 ops/systemd/aiinforsearch-full-backup.service /etc/systemd/system/
sudo install -m 0644 ops/systemd/aiinforsearch-full-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now aiinforsearch-full-backup.timer
```

Define `BACKUP_ROOT`, `CONFIG_PATH`, and the configured PostgreSQL connection
variable in `full-backup.conf` too. Keep the connection value private as for
`backup.conf`; the endpoint must be reachable from the host running the timer.

The wrapper stops only the API container, runs the quiesced snapshot, and
restarts the API through an EXIT/INT/TERM trap even if the snapshot fails. It
reuses the same shared lock as the daily backup and deployment snapshot and
retains 30 days via `--retention-days 30`. The quiesced guarantee comes from
`docker stop` halting the writer, not from an idle-task check: active tasks
live in the in-process runtime and are not visible to a file-based gate, and
scheduled collections run at 00:30, so the 04:00 Sunday window is normally
idle. The timer is evaluated in the host's local timezone (Asia/Shanghai CST on
the production host); `RandomizedDelaySec=15m` shifts the actual start up to 15
minutes later.

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

### Quiesced database-and-data snapshot

`--include-data` now snapshots `rag/` and `agentic_ready_data/` on top of the
database; re-crawlable source documents under `files/` are excluded.

```bash
DATA_VOLUME=ai_actuarial_inforsearch_ai-data
DATA_DIR=$(docker volume inspect "$DATA_VOLUME" --format '{{ .Mountpoint }}')
BACKUP_ROOT=/mnt/aiinforsearch-backup/aiinforsearch
CONFIG_PATH=/var/lib/aiinforsearch/config/sites.yaml
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.override.yml"
# DATABASE_URL must be available from a private shell environment or secret store.

$COMPOSE stop api
DATABASE_URL="$DATABASE_URL" sudo --preserve-env=DATABASE_URL python3 scripts/production_recovery.py backup \
  --data-dir "$DATA_DIR" \
  --config "$CONFIG_PATH" \
  --backup-root "$BACKUP_ROOT" \
  --include-data \
  --quiesced \
  --retention-days 30
$COMPOSE start api
```

Set `DATABASE_URL` privately before this command; the `sudo --preserve-env`
invocation carries it into the backup process without placing the connection
value in the command text.

If backup creation fails after the API is stopped, restart the unchanged API
before investigating. A maintenance-window wrapper should use a shell `trap` to
guarantee that restart; do not paste these commands into unattended automation.

Back up `.env` separately in the approved secret store. The recovery tool never
reads or copies it.

### Verify and rehearse a restore

```bash
BACKUP_DIR=/mnt/aiinforsearch-backup/aiinforsearch/backup-<UTC timestamp>
RESTORE_DIR=/mnt/aiinforsearch-backup/restore-smoke-<UTC timestamp>
POSTGRES_RESTORE_URL='postgresql://<user>:<password>@<postgres-host>:5432/restore_test'

python3 scripts/production_recovery.py verify "$BACKUP_DIR"
POSTGRES_RESTORE_URL="$POSTGRES_RESTORE_URL" \
  python3 scripts/production_recovery.py restore-smoke "$BACKUP_DIR" \
    --restore-dir "$RESTORE_DIR" --database-url-env POSTGRES_RESTORE_URL
```

`restore-smoke` requires a pre-provisioned empty PostgreSQL restore database. It
verifies checksums, restores with native `pg_restore`, checks the schema and
business table counts, reports file/KB/Ready Data counts, and checks referenced
artifact paths in the isolated copy. It never replaces the live database.

After that check, an operator may start the restored copy in an unexposed
container and call only GET smoke endpoints:

```bash
IMAGE=ai_actuarial_inforsearch-api:latest
RESTORE_SMOKE_KEY=$(python3 -c 'import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())')
docker run --rm -d --name ai-restore-smoke \
  -e FASTAPI_ENV=development \
  -e FASTAPI_SESSION_SECRET=restore-smoke-only \
  -e TOKEN_ENCRYPTION_KEY="$RESTORE_SMOKE_KEY" \
  -e DATABASE_URL="$POSTGRES_RESTORE_URL" \
  -e CONFIG_PATH=/app/runtime-config/sites.yaml \
  -v "$RESTORE_DIR/data:/app/data:rw" \
  -v "$RESTORE_DIR/config:/app/runtime-config:rw" \
  "$IMAGE"
docker exec ai-restore-smoke curl -fsS http://127.0.0.1:5000/api/health
docker exec ai-restore-smoke curl -fsS http://127.0.0.1:5000/api/rag/knowledge-bases
docker stop ai-restore-smoke
```

The smoke container has no published port and operates only on the isolated
restore. Record its image digest and results in the recovery rehearsal log.

### Release traceability

Builds must supply one unique release manifest ID, Git SHA, dirty flag, UTC
timestamp, and source URL. `scripts/deploy_update.sh` generates the ID once and
builds and publishes both the API and static frontend. The production frontend
serves image-built `/opt/frontend`, so an old host `dist/public` cannot replace
the newly built assets. This does not change the separate #313 config rollout.

Use the project-owned `docker-container` builder, default name
`aiinforsearch-provenance`. The server's classic/default Docker driver was
observed to return the config ID as `containerimage.digest`; release-record now
rejects that shape. The dedicated driver produces a real manifest digest with
an independent classic-store config ID and keeps the existing `--load` handoff.
`scripts/deploy_update.sh` creates or reuses this named builder, rejects an
existing wrong driver and requires successful bootstrap before building.
It selects `--builder` only for that Bake command, without changing the default
builder, Docker daemon or image store. Every failure precedes Compose `up`.

First creation requires explicit `BUILD_BUILDER_MEMORY` (Docker memory syntax)
and `BUILD_BUILDER_CPU_QUOTA` (microseconds per100000us period) chosen for the
full API/frontend build alongside running services. There is no inferred app
budget: the tested384MiB/20000us limits proved only the tiny scratch producer.
The first bootstrap pulls the official pinned image
`moby/buildkit@sha256:cec9f139f45e93c5c69c60f8b07cfad9f43f4ef6b6a6cd917527fea5ff2e3dea`
and creates the builder container plus its dedicated persistent state/cache
volume. `memory-swap` equals memory (no additional swap). Cache consumes Docker
filesystem space and persists across runs; no automatic prune/removal is added.
`BUILD_BUILDER` and `BUILD_BUILDKIT_IMAGE` allow an explicitly reviewed name/image.
An existing approved builder reuses its driver/resource configuration.

For the manual flow below, create that builder once (with the same approved
budgets), then retain it for later runs:

```bash
: "${BUILD_BUILDER_MEMORY:?Set the approved full-build memory budget}"
: "${BUILD_BUILDER_CPU_QUOTA:?Set the approved quota for a 100000us period}"
docker buildx create --name aiinforsearch-provenance --driver docker-container \
  --driver-opt "image=moby/buildkit@sha256:cec9f139f45e93c5c69c60f8b07cfad9f43f4ef6b6a6cd917527fea5ff2e3dea,memory=$BUILD_BUILDER_MEMORY,memory-swap=$BUILD_BUILDER_MEMORY,cpu-quota=$BUILD_BUILDER_CPU_QUOTA,cpu-period=100000"
```

```bash
export BUILD_GIT_SHA=$(git rev-parse HEAD)
export BUILD_RELEASE_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
export BUILD_GIT_DIRTY=false
export BUILD_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
export BUILD_SOURCE_URL=https://github.com/ferryhe/AI_actuarial_inforsearch
export API_IMAGE=ai_actuarial_inforsearch-api:latest
export FRONTEND_IMAGE=ai_actuarial_inforsearch-frontend:latest
export BUILD_BUILDER=aiinforsearch-provenance
mkdir -p /var/lib/aiinforsearch/releases
BUILD_METADATA=/var/lib/aiinforsearch/releases/"$BUILD_RELEASE_ID".build.json
docker buildx inspect --bootstrap "$BUILD_BUILDER"
docker buildx bake --builder "$BUILD_BUILDER" -f docker-compose.yml -f docker-compose.override.yml \
  --pull --load --metadata-file "$BUILD_METADATA" api frontend
```

After the image is built, write a release record containing its digest, safe OCI
labels, configuration checksum, and PostgreSQL schema version:

```bash
DATA_VOLUME=ai_actuarial_inforsearch_ai-data
DATA_DIR=$(docker volume inspect "$DATA_VOLUME" --format '{{ .Mountpoint }}')
CONFIG_PATH=/var/lib/aiinforsearch/config/sites.yaml
DATABASE_URL='postgresql://<user>:<password>@<postgres-host>:5432/ai_actuarial' \
DATABASE_URL="$DATABASE_URL" python3 scripts/production_recovery.py release-record \
  --image "$API_IMAGE" \
  --frontend-image "$FRONTEND_IMAGE" \
  --build-metadata "$BUILD_METADATA" \
  --config "$CONFIG_PATH" \
  --output /var/lib/aiinforsearch/releases/"$BUILD_RELEASE_ID".json
export API_IMAGE_DIGEST=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["image_digest"].rsplit("@", 1)[-1])' /var/lib/aiinforsearch/releases/"$BUILD_RELEASE_ID".json)
docker compose -f docker-compose.yml -f docker-compose.override.yml \
  up -d --wait --wait-timeout 180 api frontend
```

The record rejects different frontend/API release IDs, SHAs, build timestamps,
or source URLs before startup. It records both image digests after building;
local unpushed images use Buildx's post-build `containerimage.digest` manifest
digest. The freshly loaded tag must match the metadata's manifest/repository
digest (containerd store) or config ID (classic store); the record stores
`containerimage.config.digest` separately when present. When raw metadata omits
it and a classic store exposes only a config ID, the record uses that build's
`buildx.build.ref` to read native BuildKit content through
`docker buildx history inspect attachment`. It verifies the metadata's index or
manifest hash, the referenced manifest and config hashes, and the loaded tag's
config ID before recording that separately verified config digest. It never
substitutes a config ID for a manifest digest. Containerd/repository identities
that already match the manifest may retain an absent config as `unknown`.
Missing/stale metadata or unavailable build content fails before startup.
Buildx with `bake --metadata-file` and `history inspect attachment` support
(tested with Buildx0.30.1), and Compose with `up --wait`, are required. Create the
release record on the building host before pruning BuildKit history/content;
preserve the raw metadata and paired release record for later image transfers.
The deployment waits up to `DEPLOY_WAIT_TIMEOUT` seconds (default 180) for both
API and frontend healthchecks; timeout/failure prevents its success message.
A digest is never a build argument. `/api/health` exposes only
the release ID and short SHA; `/api/health/detailed` and `/api/metrics` require
authenticated `logs.system.read`. Their explicit build projection includes
the full SHA, build timestamp, post-build API digest, config hash, and the
logical config source `external` or `tracked-development`, with no config
contents or host paths. Metrics reports a storage backend label rather than
a connection URI. The Settings page compares the complete
`release_manifest_id`, warns on mismatch, and continues to operate; unknown
identities are reported as unavailable rather than treated as a match.

Non-production provenance rehearsal (no production configuration or credentials):

```bash
python -m pytest tests/test_issue_364_build_info.py --no-cov -q
BUILD_RELEASE_ID=fixture-browser-release BUILD_GIT_SHA=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa BUILD_UTC=2026-10-04T12:00:00Z npm run build
npm run preview -- --host 127.0.0.1 --port 5184
# In a second local shell (set CHROME_PATH to a local Chromium executable):
node client/src/components/BuildInfo.browser-smoke.mjs
```

The deploy test uses fake Git, Docker/Compose, capacity, and backup operations
plus an isolated PostgreSQL/config fixture. It executes the actual shell deploy
flow and release-record implementation, checks both builds precede image
inspection, and checks the runtime digest handoff. The browser fixture exercises
canary mismatch and a return to the previous frontend identity. For a live
canary or rollback, retain and select the paired API/frontend images and their
release record together; preserve the record's build identity and pass its
post-build digest in the deployment environment. A schema rollback still
requires the paired database restore described below. Production observations
and live canary/rollback remain an unverified gate until separately authorized;
these local fixtures do not claim a live rollout succeeded.

PostgreSQL schema versions are recorded in
`ai_actuarial_schema_migrations`. After a verified backup, inspect and apply
the versioned migration before application startup:

```bash
python -m ai_actuarial schema status --json
python -m ai_actuarial schema plan --json
python -m ai_actuarial schema apply --json
```

For an initial SQLite migration, prepare an empty PostgreSQL schema, run
`schema apply` and `schema import-sqlite-v16`, verify the import, then start the
API. Starting the API first may seed rows and the importer will reject that
target. A rollback across a schema change is paired: restore the matching
verified PostgreSQL backup with the previous application image. Never edit the
schema version by hand.

### Live restore and rollback

Replacing the live named volume is a separate, destructive production action.
It requires explicit authorization, a maintenance window, a verified isolated
restore, and the rollback checklist from the release Issue. Do not restore by
copying files into a running container or by using `docker compose down -v`.


## API Documentation

Development and test environments expose interactive API docs at:

- **Swagger UI**: `http://localhost:5000/docs`
- **ReDoc**: `http://localhost:5000/redoc`
- **OpenAPI JSON**: `http://localhost:5000/openapi.json`

Production disables these routes. Use an authenticated admin session for
production diagnostics instead of exposing the API schema publicly.

## Health Checks

```bash
# Basic health
curl http://localhost:5000/api/health

# Detailed health (includes version and service status; admin token required)
curl -H "Authorization: Bearer $ADMIN_API_TOKEN" http://localhost:5000/api/health/detailed
```

## Updating the Service

Before pulling and building, remove or rebase old whole-file overrides against
the current tracked source; a complete-file override can drop newer code and
migration definitions. Keep `auth_tokens.token_type` in the v16 migration and
the v15 latest-chunk index when reconciling storage changes. Both current KB
status paths already use the latest-row query, so do not restore the obsolete
window-CTE version. Keep production `CONFIG_PATH` outside the checkout and the
PostgreSQL URL in the private runtime environment; `.dockerignore` excludes
nested environment files, SQLite migration sources, and runtime/work directories
from image builds.

```bash
# The guarded updater refuses a dirty worktree or root-disk use >=80%, creates a
# quiesced full snapshot, fast-forwards main, builds with OCI revision labels,
# restarts the API, and writes a release record.
export CONFIG_PATH=/var/lib/aiinforsearch/config/sites.yaml
scripts/deploy_update.sh
```

The updater intentionally refuses the known production
`.hermes/project-status.md` modification. Preserve it outside the checkout and
review it before retrying; do not reset, overwrite, or silently stash it. The
script also requires a successful full snapshot before changing the running API.
