#!/usr/bin/env bash
set -euo pipefail

umask 077

REPO_DIR="${REPO_DIR:-/opt/ai_actuarial_inforsearch}"
DATA_VOLUME_NAME="${DATA_VOLUME_NAME:-ai_actuarial_inforsearch_ai-data}"
CONFIG_PATH="${CONFIG_PATH:-$REPO_DIR/config/sites.yaml}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/aiinforsearch}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

DATA_DIR=$(docker volume inspect "$DATA_VOLUME_NAME" --format '{{ .Mountpoint }}')

exec "$PYTHON_BIN" "$REPO_DIR/scripts/production_recovery.py" backup \
  --data-dir "$DATA_DIR" \
  --config "$CONFIG_PATH" \
  --backup-root "$BACKUP_ROOT"
