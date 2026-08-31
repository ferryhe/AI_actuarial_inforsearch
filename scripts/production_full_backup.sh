#!/usr/bin/env bash
set -euo pipefail

# Quiesced weekly full snapshot: stop the API, snapshot DB + rag + ready-data
# (re-crawlable source documents under ``files`` are excluded), then recover.
# A trap guarantees the API is restarted even if the snapshot fails mid-way.

umask 077

REPO_DIR="${REPO_DIR:-/opt/ai_actuarial_inforsearch}"
DATA_VOLUME_NAME="${DATA_VOLUME_NAME:-ai_actuarial_inforsearch_ai-data}"
CONFIG_PATH="${CONFIG_PATH:?Set CONFIG_PATH to the external production sites.yaml}"
BACKUP_ROOT="${BACKUP_ROOT:?Set BACKUP_ROOT to a pre-created approved full-backup filesystem}"
BACKUP_LOCK_FILE="${BACKUP_LOCK_FILE:-/run/aiinforsearch-backup.lock}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
API_CONTAINER="${API_CONTAINER:-ai-api}"
STOP_TIMEOUT="${STOP_TIMEOUT:-30}"
HEALTH_WAIT="${HEALTH_WAIT:-120}"

log() { printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# --- Recovery trap: always bring the API back up, regardless of outcome. ---
recover_api() {
  local running
  running=$(docker inspect --format '{{.State.Running}}' "$API_CONTAINER" 2>/dev/null || echo "false")
  if [[ "$running" != "true" ]]; then
    log "recovery: starting $API_CONTAINER"
    docker start "$API_CONTAINER" >/dev/null 2>&1 || true
  fi
}
trap recover_api EXIT
trap 'exit 1' INT TERM

# --- Lock: never overlap with another full snapshot or deployment snapshot. ---
exec 9>"$BACKUP_LOCK_FILE"
if ! flock -n 9; then
  log "another full snapshot or deployment snapshot is already running"
  exit 1
fi

DATA_DIR=$(docker volume inspect "$DATA_VOLUME_NAME" --format '{{ .Mountpoint }}')

# --- Preconditions ---
if [[ ! -d "$BACKUP_ROOT" ]]; then
  log "approved backup root does not exist: $BACKUP_ROOT"
  exit 1
fi
if [[ ! -w "$BACKUP_ROOT" ]]; then
  log "approved backup root is not writable: $BACKUP_ROOT"
  exit 1
fi
if [[ "$(stat -c %d "$DATA_DIR")" == "$(stat -c %d "$BACKUP_ROOT")" ]]; then
  log "backup root must be on a different filesystem from the production data volume"
  exit 1
fi

# No idle-task gate here: active tasks live in the in-process
# NativeTaskRuntime.active_tasks (only visible through the authenticated
# /api/tasks/active endpoint), not in job_history.jsonl, so a file-based check
# would give a false all-clear. The quiesced guarantee instead comes from
# ``docker stop`` gracefully halting the writer before the snapshot; SQLite
# online backup plus copytree stats verification keep the snapshot consistent
# even if a background task is interrupted. Scheduled collections run at 00:30,
# so the 04:00 Sunday window is deliberately offset from collection (operator
# decision: keep this wrapper simple rather than add an authenticated
# active-task gate). Any manual task still in flight is gracefully halted by
# ``docker stop``.

# --- Snapshot ---
START_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
IMAGE_ID=$(docker inspect --format '{{.Image}}' "$API_CONTAINER" 2>/dev/null || echo "unknown")
log "full snapshot start: container=$API_CONTAINER image=$IMAGE_ID"

log "stopping $API_CONTAINER (timeout ${STOP_TIMEOUT}s)"
docker stop -t "$STOP_TIMEOUT" "$API_CONTAINER"
STOPPED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
log "api stopped at $STOPPED_UTC"

# Run the quiesced snapshot. The recovery trap re-starts the API on any exit.
BACKUP_OUTPUT=""
BACKUP_EXIT=0
set +e
BACKUP_OUTPUT=$( "$PYTHON_BIN" "$REPO_DIR/scripts/production_recovery.py" backup \
  --data-dir "$DATA_DIR" \
  --config "$CONFIG_PATH" \
  --backup-root "$BACKUP_ROOT" \
  --include-data --quiesced --retention-days 30 --json 2>&1 )
BACKUP_EXIT=$?
set -e
log "snapshot result (exit=$BACKUP_EXIT): $BACKUP_OUTPUT"

# Recover the API and wait for it to report healthy.
log "recovering $API_CONTAINER"
docker start "$API_CONTAINER" >/dev/null 2>&1 || true

RECOVERED_UTC=""
for _ in $(seq 1 "$HEALTH_WAIT"); do
  health=$(docker inspect --format '{{.State.Health.Status}}' "$API_CONTAINER" 2>/dev/null || echo "none")
  if [[ "$health" == "healthy" ]]; then
    RECOVERED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    break
  fi
  sleep 1
done

if [[ -n "$RECOVERED_UTC" ]]; then
  log "api healthy at $RECOVERED_UTC"
else
  log "WARNING: api did not report healthy within ${HEALTH_WAIT}s"
fi

log "full snapshot end: start=$START_UTC stopped=$STOPPED_UTC recovered=${RECOVERED_UTC:-unknown}"

if [[ "$BACKUP_EXIT" -ne 0 ]]; then
  log "full snapshot FAILED"
  exit "$BACKUP_EXIT"
fi

log "full snapshot OK"
exit 0
