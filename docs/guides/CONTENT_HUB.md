# Local content hub and source staging

The content hub is an offline, source-attributed content projection. The current API, crawler, and RAG runtime do not read from it. This change does not merge the two serving databases, publish a new API, or combine FAISS indexes.

## Data boundaries

The content-hub database stores validated metadata and text variants for URLs, file hashes, and source-specific legacy IDs. It keeps every source version and URL alias. It stores a file under a shared content-addressed path only after the artifact manifest verifies its SHA-256. Missing originals remain explicit as `missing`; a deleted timestamp is recorded separately, so a deleted file whose bytes still exist remains `present` and is retained.

The lossless source-stage database is a separate, restricted archive. It stores every row from one checkpointed SQLite v16 database, including users, tokens, chats, tasks, RAG/index state, BLOBs, rowids, and source schema metadata. Row JSON is stored as PostgreSQL `TEXT`, with NUL escaped by JSON and BLOBs encoded as hexadecimal, because PostgreSQL text and JSONB cannot hold an embedded NUL. Do not expose or query this archive as the content hub. Its full-row copy can contain credentials and personal data even though the content-hub projection excludes those tables.

`pg_dump` covers PostgreSQL metadata and staged rows. It does not include the original PDFs or other files in the shared CAS. Back up the CAS and any original-file archive separately before deleting or moving source files.

## Configure PostgreSQL and D-drive roots

Set `CONTENT_HUB_DATABASE_URL` to the dedicated hub database and `CONTENT_HUB_STAGE_DATABASE_URL` to a different database for the complete source archive. Supply both through a private environment or secret store. Do not put real connection strings in command lines, checked-in files, logs, or screenshots. The command rejects URLs that identify the same PostgreSQL database; the two databases can share a PostgreSQL endpoint.

Keep the PostgreSQL data directory and application files on D as separate roots. For example, configure PostgreSQL `PGDATA` at `D:\AI_actuarial_inforsearch\postgres\content-hub-pg16` (or bind that directory to `/var/lib/postgresql/data` for a PostgreSQL 16 container), and use `D:\AI_actuarial_inforsearch\hub` as the shared artifact root. A `DATA_DIR` setting controls application artifacts; it does not move PostgreSQL's own data directory.

## Stage and import one source snapshot

Use a closed, checkpointed v16 source file. The source name is permanently bound to that snapshot and its manifest. A different source snapshot must use a new source name such as `overseas_20261011`; this command does not refresh, merge, or deduplicate two different SQLite snapshots.

Example PowerShell sequence (the connection variables are placeholders; load the actual values privately):

```powershell
$env:CONTENT_HUB_STAGE_DATABASE_URL = '<private PostgreSQL URL for the separate raw-stage database>'
$env:CONTENT_HUB_DATABASE_URL = '<private PostgreSQL URL for the content-hub database>'

python -m ai_actuarial content-hub stage-plan --json
python -m ai_actuarial content-hub stage `
  --source-name overseas_20261011 `
  --source 'D:\AI_actuarial_inforsearch\archives\20261011-content-hub\overseas\index-v16.db' `
  --json

python -m ai_actuarial content-hub schema plan --json
python -m ai_actuarial content-hub schema apply --json
python -m ai_actuarial content-hub import `
  --source-name overseas_20261011 `
  --source 'D:\AI_actuarial_inforsearch\archives\20261011-content-hub\overseas\index-v16.db' `
  --manifest 'D:\AI_actuarial_inforsearch\hub\manifests\overseas_20261011\<snapshot-sha256>.json' `
  --artifact-root 'D:\AI_actuarial_inforsearch\hub' `
  --data-root 'D:\AI_actuarial_inforsearch\data' `
  --json
python -m ai_actuarial content-hub status --json
```

Stage first, then apply the hub schema, then import. The stage operation initializes the separate `raw_source` schema if needed. A PostgreSQL restore using `pg_restore --schema=raw_source` does not create the schema; create that schema in the destination database before restoring a source-stage dump. Restore into a restricted stage database, not the hub database.

The manifest must name the same source and snapshot hash as the read-only SQLite file and provide its validated table counts, every file row, verified CAS availability, and source-specific index/artifact metadata. The importer rechecks the source file, manifest, and available CAS artifacts before committing. Use the shared root layout `manifests/<source>/<snapshot-sha256>.json` and `cas/sha256/<first-two-hash-characters>/<sha256>`.

## Querying and language metadata

`content-hub show --url <exact-url> --json` returns every content version for that exact URL, all source file observations, and all stored text variants. `content-hub status --json` reports sources, variants, files, blobs, and legacy index artifacts. Error JSON omits database credentials.

Summary and markdown text are detected independently with the offline language detector. The original text is stored unchanged. Low-confidence or too-short text is marked `und`; a language label is not a locale or legal jurisdiction. Existing provider, model, recipe, and profile values are preserved when present, otherwise they are recorded as `unknown`. Source index artifacts remain source-namespaced and their embedding dimensions are never treated as interchangeable.

## Failure and rerun behavior

Use `--json` for scripts. A successful exact rerun returns `already_imported: true` for a hub import or `state: "unchanged"` for a source stage after checking stored counts and hashes. A changed source, manifest, conflicting source name, nonempty stage database, invalid declared-present CAS payload, or corrupted stored stage aborts before a successful response. Files explicitly marked missing remain recorded as missing. CLI failures return exit code 2 and a JSON error when `--json` is set. Never resolve a conflict by deleting source rows or replacing the manifest in place; preserve the archive and start a new, explicitly named snapshot workflow.
