#!/usr/bin/env bash
set -euo pipefail

umask 077

REPO_DIR="${REPO_DIR:-/opt/ai_actuarial_inforsearch}"
DATA_VOLUME_NAME="${DATA_VOLUME_NAME:-ai_actuarial_inforsearch_ai-data}"
CONFIG_PATH="${CONFIG_PATH:?Set CONFIG_PATH to the external production sites.yaml}"
BACKUP_ROOT="${BACKUP_ROOT:?Set BACKUP_ROOT to a pre-created approved backup filesystem}"
BACKUP_LOCK_FILE="${BACKUP_LOCK_FILE:-/run/aiinforsearch-backup.lock}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

exec 9>"$BACKUP_LOCK_FILE"
if ! flock -n 9; then
  echo "Another AI InfoSearch backup or deployment snapshot is already running."
  exit 1
fi

DATA_DIR=$(docker volume inspect "$DATA_VOLUME_NAME" --format '{{ .Mountpoint }}')

if [[ ! -d "$BACKUP_ROOT" ]]; then
  echo "Approved backup root does not exist: $BACKUP_ROOT"
  exit 1
fi
if [[ ! -w "$BACKUP_ROOT" ]]; then
  echo "Approved backup root is not writable: $BACKUP_ROOT"
  exit 1
fi
if [[ "$(stat -c %d "$DATA_DIR")" == "$(stat -c %d "$BACKUP_ROOT")" ]]; then
  echo "Backup root must be on a different filesystem from the production data volume."
  exit 1
fi

exec "$PYTHON_BIN" "$REPO_DIR/scripts/production_recovery.py" backup \
  --data-dir "$DATA_DIR" \
  --config "$CONFIG_PATH" \
  --backup-root "$BACKUP_ROOT" \
  --retention-days 30
