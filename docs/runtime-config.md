# Runtime configuration ownership

`CONFIG_PATH` is the single authoritative path for mutable `sites.yaml`
configuration. The tracked `config/sites.yaml` file is a development default
and a bootstrap template only; production must never use it as live state.

## Development

Local commands default to `config/sites.yaml` when `CONFIG_PATH` is unset. To
exercise the external-config contract locally, set `CONFIG_PATH` explicitly:

```bash
export CONFIG_PATH="$PWD/.runtime/sites.yaml"
python -m ai_actuarial --config "$CONFIG_PATH" config-bootstrap --json
```

The bootstrap command creates the destination once. It fails if the destination
already exists and never overwrites operator-managed values.

The legacy `scripts/migrate_env_to_yaml.py` writer is development-only. It may
preview an external file with `--dry-run`, but refuses to modify an explicit
`CONFIG_PATH`; use the create-once bootstrap command for external state.

## Production

Choose an absolute path outside the Git checkout, create it once from the
tracked template, and keep the file and its parent directory writable by the API
process. Directory write access is required because Settings changes use a
temporary file, flush it to disk, and atomically replace the live file.

```bash
sudo install -d -o <service-user> -g <service-group> -m 0750 \
  /var/lib/aiinforsearch/config

export CONFIG_PATH=/var/lib/aiinforsearch/config/sites.yaml
python -m ai_actuarial --config "$CONFIG_PATH" config-bootstrap \
  --source config/sites.yaml --json
```

In production, startup fails closed when `CONFIG_PATH` is absent, points to the
tracked template, or names a missing, invalid, unreadable, or unwritable file.
An explicit path is never replaced by a fallback path.

Compose mounts the containing directory so atomic replacement works:

```bash
export RUNTIME_CONFIG_DIR=/var/lib/aiinforsearch/config
export CONFIG_FILENAME=sites.yaml
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
```

Inside the API container the same file is available as
`/app/runtime-config/sites.yaml`. `CONFIG_PATH` is set to that container path by
Compose. On the host, backup, deployment, and release-record commands use the
host `CONFIG_PATH` value directly.

The guarded deployment helper derives `RUNTIME_CONFIG_DIR` and
`CONFIG_FILENAME` from the canonical host `CONFIG_PATH`. If either variable is
pre-set to a different directory or filename, deployment stops before backup or
container changes so the backup checksum cannot diverge from the mounted file.

## Backup and release contract

Set `CONFIG_PATH` in every production backup service environment file and in
the shell that runs the guarded deployment helper:

```bash
CONFIG_PATH=/var/lib/aiinforsearch/config/sites.yaml
BACKUP_ROOT=/mnt/aiinforsearch-backup/aiinforsearch
```

`production_backup.sh`, `production_full_backup.sh`, and `deploy_update.sh`
refuse to run without `CONFIG_PATH`. Their snapshots and release records contain
the checksum of that effective file, not the tracked template.

## Migration and rollback checklist

The production migration itself belongs to Issue #313 and is not performed by
the #310 code release. During that approved maintenance window:

1. Back up and checksum the currently effective production configuration.
2. Bootstrap the external destination once, then reconcile the current operator
   values into it without replacing stable credential IDs.
3. Set `CONFIG_PATH`, `RUNTIME_CONFIG_DIR`, and `CONFIG_FILENAME` in production.
4. Run configuration validation and a Compose render before restart.
5. Verify Chat and Weekly Explanation resolve the same provider, model, and
   credential ID, and verify a Settings edit survives a service restart.
6. Verify the backup manifest and release record checksum the external file.
7. For rollback, restore the verified external file and previous image; do not
   reset the Git worktree as a way to restore mutable configuration.
