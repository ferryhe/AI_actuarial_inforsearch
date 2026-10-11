# PostgreSQL Runtime and SQLite v16 Import

PostgreSQL 16 is the only application database runtime. API, CLI, crawler,
scheduled-task, RAG, chat, and maintenance processes all use the same configured
PostgreSQL URL. SQLite is supported only as a read-only source for the explicit
v16 importer and by legacy-schema validation tests.

## Configure PostgreSQL

Install PostgreSQL 16, create an application database and role, and provide the
connection URL through a private process environment or secret store:

```bash
export DATABASE_URL='postgresql://<user>:<password>@127.0.0.1:5432/ai_actuarial'
```

The URL may instead be selected with `database.url_env` in the active
`CONFIG_PATH` YAML. The value named by that setting must be present in the
process environment. Missing or non-PostgreSQL URLs fail closed; no local
SQLite database or alternate backend is selected implicitly.

PostgreSQL schema is versioned and initialized by the runtime. Operators can
inspect and apply it explicitly before startup:

```bash
python -m ai_actuarial schema status --json
python -m ai_actuarial schema plan --json
python -m ai_actuarial schema apply --json
```

The service must have PostgreSQL 16 client tools available for native backup and
restore operations. Use clients matching the server's major version.

## Keep database and file paths separate

`DATABASE_URL` selects PostgreSQL. `paths.data` in the active YAML (or the
`DATA_DIR` process override) selects the independent directory for downloads,
logs, upload batches, RAG and Ready Data artifacts, and task history. Use an
absolute writable path for a local deployment that stores data on another disk:

```yaml
paths:
  data: D:/AI_actuarial_inforsearch/data
  download_dir: data/files
database:
  type: postgresql
  url_env: DATABASE_URL
```

Relative runtime paths resolve under `paths.data`. An explicit absolute path
remains an override. The data root does not select or locate the PostgreSQL
database.

### Windows local PostgreSQL 16 on D:

With Docker Desktop running, a new local instance can keep its database files
on D: while exposing PostgreSQL only to this computer. Use a new or empty
directory for this instance; do not point it at the migration-test container
or any existing production data directory.

```powershell
$pgData = 'D:/AI_actuarial_inforsearch/postgres'
$dataRoot = 'D:/AI_actuarial_inforsearch/data'
New-Item -ItemType Directory -Force $pgData, $dataRoot | Out-Null
$env:POSTGRES_PASSWORD = '<private-password>'
docker run --detach --name ai-actuarial-postgres16 --restart unless-stopped `
  --env POSTGRES_DB=ai_actuarial `
  --env POSTGRES_USER=ai_actuarial `
  --env POSTGRES_PASSWORD=$env:POSTGRES_PASSWORD `
  --publish 127.0.0.1:5432:5432 `
  --volume "${pgData}:/var/lib/postgresql/data" `
  postgres:16

$env:DATABASE_URL = 'postgresql://ai_actuarial:<URL-encoded-password>@127.0.0.1:5432/ai_actuarial'
$env:DATA_DIR = $dataRoot
docker exec ai-actuarial-postgres16 pg_isready -U ai_actuarial -d ai_actuarial
python -m ai_actuarial schema apply --json
```

Replace the URL placeholder using a private secret store or the local process
environment; percent-encode reserved characters in the URL password. The
`postgres` bind mount contains PostgreSQL's physical database files, while
`DATA_DIR` contains application artifacts and uploaded/downloaded files. Both
roots are on D: and serve different purposes. This is a setup example for a
new local instance; it does not migrate, merge, or cut over production data.

## Import one SQLite v16 database

The importer accepts one checkpointed SQLite v16 snapshot, validates it
read-only, and imports all supported core and optional RAG/chat/catalog tables
into an empty PostgreSQL schema. It preserves source IDs, row contents, foreign
keys, and identity sequences, records source provenance, and can safely repeat
the same source. A different source or any pre-existing business row is
rejected. This operation does not merge two databases.

Use this order: prepare an empty PostgreSQL database/schema, apply the schema,
import the SQLite snapshot, verify the result, then start the API. Starting the
API or a `Storage` caller first may seed taxonomy or a bootstrap token; the
importer correctly rejects that non-empty target.

```bash
export DATABASE_URL='postgresql://<user>:<password>@127.0.0.1:5432/ai_actuarial'
python -m ai_actuarial schema apply --json
python -m ai_actuarial schema import-sqlite-v16 \
  --source /secure/backup/index-v16.db --json
python -m ai_actuarial schema status --json
```

The source must be a single checkpointed file with no non-empty `-wal` file,
pass SQLite integrity/schema checks, and report `user_version=16`. Keep it
unchanged until import and application-level checks complete. The import reads
in bounded batches and verifies all imported rows before committing. Protect
the source file separately; raw downloaded/original documents are not part of
the database snapshot or import contract and must be separately backed up and
transferred before any old copy is cleaned up.

## Backup, verification, and restore rehearsal

`scripts/production_recovery.py` uses native PostgreSQL tools and emits
credential-free JSON. An online database backup includes the PostgreSQL dump
and configuration. A full data snapshot also includes RAG and Ready Data
artifacts, so first stop application writers and pass `--include-data
--quiesced`:

```bash
python scripts/production_recovery.py backup \
  --data-dir "$DATA_DIR" --config "$CONFIG_PATH" \
  --backup-root "$BACKUP_ROOT" --json
python scripts/production_recovery.py verify "$BACKUP_DIR" --json
```

For a restore rehearsal, provision a separate empty PostgreSQL database, set
`POSTGRES_RESTORE_URL` for that process, and restore into an isolated directory:

```bash
POSTGRES_RESTORE_URL='postgresql://<user>:<password>@127.0.0.1:5432/restore_test' \
  python scripts/production_recovery.py restore-smoke "$BACKUP_DIR" \
  --restore-dir "$RESTORE_DIR" --database-url-env POSTGRES_RESTORE_URL --json
```

The rehearsal refuses a target schema that already contains tables and does
not modify production. Database dumps contain database rows and schema; the
source documents under `files/` are intentionally excluded from the full
artifact snapshot and need their own backup/transfer process.
