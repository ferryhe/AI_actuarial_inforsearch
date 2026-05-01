#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${REPO_DIR:-$(pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
APP_SERVICE_NAME="${APP_SERVICE_NAME:-api}"
CADDY_CONTAINER="${CADDY_CONTAINER:-ai-caddy}"
RELOAD_CADDY="${RELOAD_CADDY:-false}"

cd "$REPO_DIR"

echo "[1/4] Git pull"
git fetch
git pull --ff-only

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "docker-compose.yml not found at $REPO_DIR/$COMPOSE_FILE"
  echo "Set COMPOSE_FILE or run in the repo root that contains docker-compose.yml"
  exit 1
fi

echo "[2/4] Build and restart service: $APP_SERVICE_NAME"
docker compose -f "$COMPOSE_FILE" build --pull "$APP_SERVICE_NAME"
docker compose -f "$COMPOSE_FILE" up -d "$APP_SERVICE_NAME"

if [[ "$RELOAD_CADDY" == "true" ]]; then
  echo "[3/4] Reload Caddy: $CADDY_CONTAINER"
  docker exec "$CADDY_CONTAINER" caddy reload --config /etc/caddy/Caddyfile
else
  echo "[3/4] Skip Caddy reload (RELOAD_CADDY=false)"
fi

echo "[4/4] Done"
