#!/usr/bin/env bash
set -euo pipefail

umask 077

REPO_DIR="${REPO_DIR:-$(pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
COMPOSE_OVERRIDE_FILE="${COMPOSE_OVERRIDE_FILE:-docker-compose.override.yml}"
APP_SERVICE_NAME="${APP_SERVICE_NAME:-api}"
CADDY_CONTAINER="${CADDY_CONTAINER:-ai-caddy}"
RELOAD_CADDY="${RELOAD_CADDY:-false}"
DATA_VOLUME_NAME="${DATA_VOLUME_NAME:-ai_actuarial_inforsearch_ai-data}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/aiinforsearch}"
RELEASE_DIR="${RELEASE_DIR:-/var/lib/aiinforsearch/releases}"
CAPACITY_THRESHOLD="${CAPACITY_THRESHOLD:-80}"
API_IMAGE="${API_IMAGE:-ai_actuarial_inforsearch-api:latest}"
BUILD_SOURCE_URL="${BUILD_SOURCE_URL:-https://github.com/ferryhe/AI_actuarial_inforsearch}"

cd "$REPO_DIR"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "docker-compose.yml not found at $REPO_DIR/$COMPOSE_FILE"
  echo "Set COMPOSE_FILE or run in the repo root that contains docker-compose.yml"
  exit 1
fi

compose=(docker compose -f "$COMPOSE_FILE")
if [[ -n "$COMPOSE_OVERRIDE_FILE" ]]; then
  if [[ ! -f "$COMPOSE_OVERRIDE_FILE" ]]; then
    echo "Compose override not found: $REPO_DIR/$COMPOSE_OVERRIDE_FILE"
    exit 1
  fi
  compose+=(-f "$COMPOSE_OVERRIDE_FILE")
fi

echo "[1/7] Refuse to overwrite local production changes"
if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
  echo "Production worktree is dirty. Preserve and review the changes before deployment."
  git status --short
  exit 1
fi

echo "[2/7] Enforce disk capacity gate"
python3 scripts/production_recovery.py capacity-check \
  --path / \
  --threshold "$CAPACITY_THRESHOLD"

echo "[3/7] Create a quiesced database-and-files recovery point"
DATA_DIR=$(docker volume inspect "$DATA_VOLUME_NAME" --format '{{ .Mountpoint }}')
api_container=$("${compose[@]}" ps -q "$APP_SERVICE_NAME")
api_was_running=false
if [[ -n "$api_container" ]] && [[ "$(docker inspect --format '{{ .State.Running }}' "$api_container")" == "true" ]]; then
  api_was_running=true
  "${compose[@]}" stop "$APP_SERVICE_NAME"
fi

restart_api_on_exit() {
  if [[ "$api_was_running" == "true" ]]; then
    "${compose[@]}" start "$APP_SERVICE_NAME" >/dev/null
  fi
}
trap restart_api_on_exit EXIT

python3 scripts/production_recovery.py backup \
  --data-dir "$DATA_DIR" \
  --config config/sites.yaml \
  --backup-root "$BACKUP_ROOT" \
  --include-data \
  --quiesced

restart_api_on_exit
api_was_running=false
trap - EXIT

echo "[4/7] Fast-forward the clean production worktree"
git fetch
git pull --ff-only

export BUILD_GIT_SHA="${BUILD_GIT_SHA:-$(git rev-parse HEAD)}"
export BUILD_GIT_DIRTY="${BUILD_GIT_DIRTY:-false}"
export BUILD_UTC="${BUILD_UTC:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
export BUILD_SOURCE_URL

echo "[5/7] Build and restart service: $APP_SERVICE_NAME"
"${compose[@]}" build --pull "$APP_SERVICE_NAME"
"${compose[@]}" up -d "$APP_SERVICE_NAME"

echo "[6/7] Write the release traceability record"
mkdir -p "$RELEASE_DIR"
python3 scripts/production_recovery.py release-record \
  --image "$API_IMAGE" \
  --config config/sites.yaml \
  --db "$DATA_DIR/index.db" \
  --output "$RELEASE_DIR/$BUILD_GIT_SHA.json"

if [[ "$RELOAD_CADDY" == "true" ]]; then
  echo "[7/7] Reload Caddy: $CADDY_CONTAINER"
  docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile
else
  echo "[7/7] Skip Caddy reload (RELOAD_CADDY=false)"
fi

echo "Deployment completed with backup and release records."
