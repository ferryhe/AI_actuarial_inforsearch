"""Offline importer and read-only CLI for the source-attributed content hub."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import sqlite3
import stat
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json

from .postgres import DatabaseConfig
from .sqlite_schema import (
    _OPTIONAL_TABLE_ALLOWED_COLUMNS,
    CURRENT_SQLITE_SCHEMA_VERSION,
    _analyze_connection,
    _current_storage_signature,
)

MANIFEST_FORMAT = "ai_actuarial.content_hub.artifact_manifest"
HUB_SCHEMA = "content_hub"
HUB_SCHEMA_VERSION = 2
_MIGRATION_DIR = Path(__file__).with_name("content_hub_migrations")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SCHEMA_RE = re.compile(r"^(?:content_hub|test_[A-Za-z0-9_]{1,58})$")
_CONTENT_FIELDS = (
    "title",
    "keywords",
    "keywords_json",
    "category",
    "summary",
    "markdown_content",
)
_LANGUAGE_FIELDS = frozenset({"summary", "markdown_content"})


class ContentHubError(RuntimeError):
    """A source snapshot or hub contract cannot be safely applied."""


@dataclass(frozen=True)
class ValidatedManifest:
    source_name: str
    snapshot_sha256: str
    snapshot_bytes: int
    table_counts: dict[str, int]
    manifest_sha256: str
    files: list[dict[str, Any]]
    indexes: list[dict[str, Any]]
    staging_database_name: str | None
    staging_snapshot_sha256: str | None


def _database_url(database_url: DatabaseConfig | str | None = None) -> str:
    if isinstance(database_url, DatabaseConfig):
        return database_url._url
    if database_url:
        return DatabaseConfig(str(database_url))._url
    value = os.getenv("CONTENT_HUB_DATABASE_URL", "").strip()
    if not value:
        raise ContentHubError(
            "CONTENT_HUB_DATABASE_URL must name the dedicated content hub database"
        )
    return DatabaseConfig(value)._url


def _validate_schema(schema: str) -> str:
    if not _SCHEMA_RE.fullmatch(schema):
        raise ContentHubError("Hub schema must be content_hub or an owned test_* schema")
    return schema


def _migrations() -> list[tuple[int, str, bytes]]:
    items = []
    for path in _MIGRATION_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"):
        version = int(path.name.split("_", 1)[0])
        items.append((version, path.name, path.read_bytes()))
    items.sort()
    if [item[0] for item in items] != list(range(1, len(items) + 1)):
        raise RuntimeError("Content hub migrations must be numbered without gaps")
    return items


def _migration_checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _connect(database_url: DatabaseConfig | str | None) -> psycopg2.extensions.connection:
    try:
        return psycopg2.connect(_database_url(database_url))
    except (psycopg2.Error, ValueError) as exc:
        raise ContentHubError("Could not connect to the configured content hub database") from exc


def _set_search_path(cursor: Any, schema: str) -> None:
    cursor.execute(sql.SQL("SET search_path TO {}, pg_catalog").format(sql.Identifier(schema)))


def _namespace_exists(cursor: Any, schema: str) -> bool:
    cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = %s)", (schema,))
    return bool(cursor.fetchone()[0])


def _applied_migrations(cursor: Any, schema: str) -> dict[int, tuple[str, str]]:
    if not _namespace_exists(cursor, schema):
        return {}
    _set_search_path(cursor, schema)
    cursor.execute("SELECT to_regclass('schema_migrations') IS NOT NULL")
    if not cursor.fetchone()[0]:
        return {}
    cursor.execute("SELECT version, filename, checksum FROM schema_migrations ORDER BY version")
    return {int(row[0]): (str(row[1]), str(row[2])) for row in cursor.fetchall()}


def content_hub_schema_plan(
    database_url: DatabaseConfig | str | None = None, *, schema: str = HUB_SCHEMA
) -> dict[str, Any]:
    schema = _validate_schema(schema)
    migrations = _migrations()
    connection = _connect(database_url)
    try:
        with connection.cursor() as cursor:
            applied = _applied_migrations(cursor, schema)
            for version, (filename, checksum) in applied.items():
                expected = next((item for item in migrations if item[0] == version), None)
                if expected is None or (filename, checksum) != (
                    expected[1],
                    _migration_checksum(expected[2]),
                ):
                    raise ContentHubError(
                        "An applied content hub migration does not match this release"
                    )
            current = max(applied, default=0)
            pending = [
                {"version": version, "file": filename}
                for version, filename, _ in migrations
                if version not in applied
            ]
            return {
                "schema": schema,
                "current_version": current,
                "target_version": len(migrations),
                "pending": pending,
            }
    finally:
        connection.close()


def apply_content_hub_schema(
    database_url: DatabaseConfig | str | None = None, *, schema: str = HUB_SCHEMA
) -> dict[str, Any]:
    schema = _validate_schema(schema)
    migrations = _migrations()
    connection = _connect(database_url)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"content_hub:migrations:{schema}",),
            )
            cursor.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
            _set_search_path(cursor, schema)
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, filename TEXT NOT NULL, checksum CHAR(64) NOT NULL, "
                "applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            cursor.execute(
                "SELECT version, filename, checksum FROM schema_migrations ORDER BY version"
            )
            applied = {int(row[0]): (str(row[1]), str(row[2])) for row in cursor.fetchall()}
            for version, (filename, checksum) in applied.items():
                expected = next((item for item in migrations if item[0] == version), None)
                if expected is None or (filename, checksum) != (
                    expected[1],
                    _migration_checksum(expected[2]),
                ):
                    raise ContentHubError(
                        "An applied content hub migration does not match this release"
                    )
            for version, filename, content in migrations:
                if version in applied:
                    continue
                cursor.execute(content.decode("utf-8"))
                cursor.execute(
                    "INSERT INTO schema_migrations (version, filename, checksum) VALUES (%s, %s, %s)",
                    (version, filename, _migration_checksum(content)),
                )
            current = max(len(migrations), 0)
        connection.commit()
        return {"schema": schema, "version": current, "applied": True}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _json_safe(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray, memoryview)):
        import base64

        return {"$sqlite_blob_base64": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and not (float("-inf") < value < float("inf")):
        return {"$sqlite_float": "nan" if value != value else "-inf" if value < 0 else "inf"}
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _json_text(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _source_sha256(path: Path) -> tuple[str, int, tuple[int, int]]:
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ContentHubError("SQLite snapshot changed while its hash was checked")
    return digest.hexdigest(), int(after.st_size), (after.st_size, after.st_mtime_ns)


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _quote_sqlite_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _resolve_artifact(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ContentHubError("Artifact manifest contains an invalid relative path")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ContentHubError("Artifact manifest contains an invalid relative path")
    root = root.resolve()
    target = root.joinpath(*pure.parts).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ContentHubError("Artifact manifest path escapes its configured root") from exc
    return target


def _validate_manifest(path: Path, artifact_root: Path) -> ValidatedManifest:
    try:
        raw = path.read_bytes()
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContentHubError("Artifact manifest is not readable UTF-8 JSON") from exc
    if not isinstance(document, dict) or document.get("format") != MANIFEST_FORMAT:
        raise ContentHubError("Artifact manifest format is not supported")
    if document.get("version") != 1:
        raise ContentHubError("Artifact manifest version is not supported")
    source_name = document.get("source_name")
    if not isinstance(source_name, str) or not _SOURCE_RE.fullmatch(source_name):
        raise ContentHubError("Artifact manifest source_name is invalid")
    snapshot = document.get("snapshot")
    if not isinstance(snapshot, dict):
        raise ContentHubError("Artifact manifest snapshot metadata is missing")
    snapshot_sha256 = snapshot.get("sha256")
    snapshot_bytes = snapshot.get("bytes")
    if not isinstance(snapshot_sha256, str) or not _HASH_RE.fullmatch(snapshot_sha256):
        raise ContentHubError("Artifact manifest snapshot SHA-256 is invalid")
    if type(snapshot_bytes) is not int or snapshot_bytes < 0:
        raise ContentHubError("Artifact manifest snapshot size is invalid")
    if snapshot.get("sqlite_user_version") != CURRENT_SQLITE_SCHEMA_VERSION:
        raise ContentHubError("Artifact manifest must identify a SQLite v16 snapshot")
    if snapshot.get("wal_checkpointed") is not True:
        raise ContentHubError("Artifact manifest snapshot must be checkpointed")
    table_counts = snapshot.get("table_counts")
    if not isinstance(table_counts, dict) or any(
        not isinstance(name, str) or type(count) is not int or count < 0
        for name, count in table_counts.items()
    ):
        raise ContentHubError("Artifact manifest table_counts are invalid")
    files = document.get("files")
    indexes = document.get("indexes")
    if not isinstance(files, list) or not isinstance(indexes, list):
        raise ContentHubError("Artifact manifest files and indexes must be arrays")

    manifest_location = (
        artifact_root.resolve() / "manifests" / source_name / f"{snapshot_sha256}.json"
    )
    try:
        if path.resolve() != manifest_location.resolve():
            raise ContentHubError("Artifact manifest is not stored at its source snapshot path")
    except OSError as exc:
        raise ContentHubError("Artifact manifest path cannot be resolved") from exc

    normalized_files: list[dict[str, Any]] = []
    file_ids: set[int] = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise ContentHubError("Artifact manifest file entry is invalid")
        legacy_id, url = entry.get("legacy_id"), entry.get("url")
        raw_sha256 = entry.get("raw_sha256")
        byte_size = entry.get("bytes")
        state = entry.get("state")
        deleted_at = entry.get("deleted_at")
        if type(legacy_id) is not int or legacy_id in file_ids:
            raise ContentHubError("Artifact manifest file ids must be unique integers")
        file_ids.add(legacy_id)
        if url is not None and not isinstance(url, str):
            raise ContentHubError("Artifact manifest file URL is invalid")
        if raw_sha256 is not None and (
            not isinstance(raw_sha256, str) or not _HASH_RE.fullmatch(raw_sha256)
        ):
            raise ContentHubError("Artifact manifest raw SHA-256 is invalid")
        if byte_size is not None and (type(byte_size) is not int or byte_size < 0):
            raise ContentHubError("Artifact manifest file size is invalid")
        if state not in {"present", "missing"}:
            raise ContentHubError("Artifact manifest file state is invalid")
        if deleted_at is not None and not isinstance(deleted_at, str):
            raise ContentHubError("Artifact manifest deleted_at must be source text or null")
        relpath = entry.get("cas_relpath")
        verified = entry.get("verified_sha256")
        expected_relpath = f"cas/sha256/{raw_sha256[:2]}/{raw_sha256}" if raw_sha256 else None
        if state == "present":
            if raw_sha256 is None or relpath != expected_relpath or verified != raw_sha256:
                raise ContentHubError("Present file artifact must identify its verified CAS object")
        elif relpath is not None or verified is not None:
            raise ContentHubError("Missing file artifact cannot claim a CAS path or verified hash")
        normalized_files.append(
            {
                "legacy_id": legacy_id,
                "url": url,
                "raw_sha256": raw_sha256,
                "bytes": byte_size,
                "state": state,
                "deleted_at": deleted_at,
                "cas_relpath": relpath,
                "verified_sha256": verified,
            }
        )
    normalized_files.sort(key=lambda entry: entry["legacy_id"])

    normalized_indexes: list[dict[str, Any]] = []
    for entry in indexes:
        if not isinstance(entry, dict):
            raise ContentHubError("Artifact manifest index entry is invalid")
        kb_id = entry.get("legacy_kb_id")
        artifact_kind = entry.get("artifact_kind")
        state = entry.get("state")
        if not isinstance(kb_id, (str, int)) or isinstance(kb_id, bool):
            raise ContentHubError("Artifact manifest legacy_kb_id is invalid")
        if not isinstance(artifact_kind, str) or not artifact_kind:
            raise ContentHubError("Artifact manifest artifact_kind is invalid")
        if state not in {"present", "missing"}:
            raise ContentHubError("Artifact manifest index state is invalid")
        relpath = entry.get("artifact_relpath")
        digest = entry.get("sha256")
        size = entry.get("bytes")
        if state == "present":
            prefix = f"legacy/{source_name}/{snapshot_sha256}/"
            if not isinstance(relpath, str) or not relpath.startswith(prefix):
                raise ContentHubError("Legacy index path is outside its source namespace")
            if not isinstance(digest, str) or not _HASH_RE.fullmatch(digest):
                raise ContentHubError("Legacy index artifact SHA-256 is invalid")
            if type(size) is not int or size < 0:
                raise ContentHubError("Legacy index artifact size is invalid")
        elif digest is not None or size is not None:
            raise ContentHubError("Missing legacy index artifacts cannot claim a hash or size")
        if relpath is not None:
            _resolve_artifact(artifact_root, relpath)
        identity = entry.get("embedding_identity") or {}
        if not isinstance(identity, dict):
            raise ContentHubError("Artifact manifest embedding_identity is invalid")
        dimension = identity.get("dimension")
        if dimension is not None and (type(dimension) is not int or dimension <= 0):
            raise ContentHubError("Artifact manifest embedding dimension is invalid")
        normalized_indexes.append(
            {
                "legacy_kb_id": str(kb_id),
                "artifact_kind": artifact_kind,
                "source_path": entry.get("source_path"),
                "artifact_relpath": relpath,
                "sha256": digest,
                "bytes": size,
                "state": state,
                "embedding_identity": {
                    "provider": str(identity.get("provider") or "unknown"),
                    "model": str(identity.get("model") or "unknown"),
                    "dimension": dimension,
                    "profile_id": str(identity.get("profile_id") or "unknown"),
                },
                "source_metadata": entry.get("source_metadata") or {},
            }
        )

    staging = document.get("source_staging") or {}
    if not isinstance(staging, dict):
        raise ContentHubError("Artifact manifest source_staging metadata is invalid")
    staging_database = staging.get("database_name")
    staging_sha = staging.get("snapshot_sha256")
    if staging_database is not None:
        if not isinstance(staging_database, str) or not re.fullmatch(
            r"[A-Za-z0-9_]{1,63}", staging_database
        ):
            raise ContentHubError("Artifact manifest staging database name is invalid")
        if staging_sha != snapshot_sha256:
            raise ContentHubError(
                "Artifact manifest staging database must reference the same snapshot"
            )
    elif staging_sha is not None:
        raise ContentHubError("Artifact manifest staging database identity is incomplete")

    return ValidatedManifest(
        source_name=source_name,
        snapshot_sha256=snapshot_sha256,
        snapshot_bytes=snapshot_bytes,
        table_counts={str(name): int(count) for name, count in table_counts.items()},
        manifest_sha256=hashlib.sha256(raw).hexdigest(),
        files=normalized_files,
        indexes=normalized_indexes,
        staging_database_name=staging_database,
        staging_snapshot_sha256=staging_sha,
    )


def _verify_artifacts(
    manifest: ValidatedManifest, artifact_root: Path
) -> dict[str, dict[str, Any]]:
    verified: dict[str, dict[str, Any]] = {}
    for entry in manifest.files:
        if entry["state"] != "present":
            continue
        digest = entry["raw_sha256"]
        if digest in verified:
            if entry["bytes"] is not None and verified[digest]["size"] != entry["bytes"]:
                raise ContentHubError("Shared CAS objects have conflicting source sizes")
            continue
        path = _resolve_artifact(artifact_root, entry["cas_relpath"])
        if not path.is_file() or stat.S_ISLNK(path.lstat().st_mode):
            raise ContentHubError("Present CAS artifact is unavailable as a regular file")
        actual_sha, actual_size = _sha256_file(path)
        if actual_sha != digest or (entry["bytes"] is not None and actual_size != entry["bytes"]):
            raise ContentHubError("CAS artifact hash or size does not match its manifest")
        verified[digest] = {"size": actual_size, "relpath": entry["cas_relpath"]}
    for entry in manifest.indexes:
        if entry["state"] != "present":
            continue
        path = _resolve_artifact(artifact_root, entry["artifact_relpath"])
        if not path.is_file() or stat.S_ISLNK(path.lstat().st_mode):
            raise ContentHubError("Present legacy index artifact is unavailable as a regular file")
        actual_sha, actual_size = _sha256_file(path)
        if actual_sha != entry["sha256"] or actual_size != entry["bytes"]:
            raise ContentHubError("Legacy index artifact hash or size does not match its manifest")
    return verified


def _hash_source_value(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, bytes):
        try:
            value = value.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ContentHubError("SQLite source contains an invalid content hash") from exc
    value = str(value).lower()
    if not _HASH_RE.fullmatch(value):
        raise ContentHubError("SQLite source contains an invalid content hash")
    return value


def _open_source_snapshot(
    path: Path, manifest: ValidatedManifest
) -> tuple[sqlite3.Connection, dict[str, list[str]], dict[str, int], tuple[int, int]]:
    if not path.is_file():
        raise ContentHubError("SQLite v16 source file does not exist")
    wal_path = Path(str(path) + "-wal")
    if wal_path.exists() and wal_path.stat().st_size:
        raise ContentHubError("SQLite v16 source must be a checkpointed single-file snapshot")
    source_sha, source_size, source_stat = _source_sha256(path)
    if source_sha != manifest.snapshot_sha256 or source_size != manifest.snapshot_bytes:
        raise ContentHubError("SQLite source hash or size does not match the artifact manifest")
    try:
        source = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro&immutable=1", uri=True)
        source.execute("PRAGMA query_only=ON")
        source.execute("BEGIN")
        status = _analyze_connection(source)
        database = status.get("database") if isinstance(status.get("database"), dict) else {}
        if (
            status.get("state") != "current"
            or int(database.get("user_version") or 0) != CURRENT_SQLITE_SCHEMA_VERSION
        ):
            raise ContentHubError("SQLite source must pass the repository v16 schema check")
        quick_check = source.execute("PRAGMA quick_check").fetchall()
        if quick_check != [("ok",)]:
            raise ContentHubError("SQLite source failed its integrity check")
        if source.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ContentHubError("SQLite source failed its foreign key check")
        actual_tables = {
            str(row[0])
            for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        expected_tables = set(_current_storage_signature())
        optional_tables = set(_OPTIONAL_TABLE_ALLOWED_COLUMNS)
        if not expected_tables.issubset(actual_tables) or not actual_tables.issubset(
            expected_tables | optional_tables
        ):
            raise ContentHubError("SQLite source contains an unexpected v16 table set")
        table_counts: dict[str, int] = {}
        table_columns: dict[str, list[str]] = {}
        for table in sorted(actual_tables):
            escaped = _quote_sqlite_identifier(table)
            table_counts[table] = int(
                source.execute(f"SELECT COUNT(*) FROM {escaped}").fetchone()[0]
            )
            table_columns[table] = [
                str(row[1]) for row in source.execute(f"PRAGMA table_info({escaped})").fetchall()
            ]
        if table_counts != manifest.table_counts:
            raise ContentHubError("SQLite table row counts do not match the artifact manifest")
        if "files" not in actual_tables or "catalog_items" not in actual_tables:
            raise ContentHubError("SQLite v16 source is missing its content tables")
        _verify_file_manifest(source, table_columns, manifest)
        return source, table_columns, table_counts, source_stat
    except ContentHubError:
        try:
            source.close()
        except (UnboundLocalError, sqlite3.Error):
            pass
        raise
    except sqlite3.Error as exc:
        try:
            source.close()
        except UnboundLocalError:
            pass
        raise ContentHubError("SQLite source is not a readable, valid v16 snapshot") from exc


def _verify_file_manifest(
    source: sqlite3.Connection,
    table_columns: dict[str, list[str]],
    manifest: ValidatedManifest,
) -> None:
    columns = set(table_columns["files"])
    required = {"id", "url"}
    if not required.issubset(columns):
        raise ContentHubError("SQLite files table has an unsupported v16 shape")
    selected = [name for name in ("id", "url", "sha256", "bytes", "deleted_at") if name in columns]
    projection = ", ".join(_quote_sqlite_identifier(name) for name in selected)
    expected = iter(manifest.files)
    rows = source.execute(f"SELECT {projection} FROM files ORDER BY id")
    count = 0
    for row in rows:
        actual = dict(zip(selected, row))
        item = next(expected, None)
        if item is None:
            raise ContentHubError("Artifact manifest omits SQLite files rows")
        count += 1
        if actual.get("id") != item["legacy_id"] or actual.get("url") != item["url"]:
            raise ContentHubError("Artifact manifest file identity does not match SQLite v16")
        source_hash = _hash_source_value(actual.get("sha256"))
        if source_hash is not None and source_hash != item["raw_sha256"]:
            raise ContentHubError("Artifact manifest raw hash conflicts with the SQLite files row")
        source_size = actual.get("bytes")
        if (
            source_size is not None
            and item["bytes"] is not None
            and int(source_size) != item["bytes"]
        ):
            raise ContentHubError("Artifact manifest byte size conflicts with the SQLite files row")
        if actual.get("deleted_at") != item["deleted_at"]:
            raise ContentHubError(
                "Artifact manifest deletion state conflicts with the SQLite files row"
            )
    if count != len(manifest.files):
        raise ContentHubError("Artifact manifest has file rows absent from SQLite v16")


def _typed_source_rows(
    source: sqlite3.Connection, table: str, columns: list[str], primary_key: list[str]
) -> Iterable[tuple[int | None, dict[str, Any]]]:
    table_sql = _quote_sqlite_identifier(table)
    info = source.execute(f"PRAGMA table_info({table_sql})").fetchall()
    pk = [str(row[1]) for row in sorted(info, key=lambda row: int(row[5])) if row[5]]
    if not pk:
        raise ContentHubError(f"SQLite content table {table} has no stable primary key")
    rowid_column = next((name for name in ("rowid", "_rowid_", "oid") if name not in columns), None)
    projection = ", ".join(_quote_sqlite_identifier(name) for name in columns)
    if rowid_column is not None:
        select = f"SELECT {rowid_column}, {projection} FROM {table_sql} ORDER BY {rowid_column}"
        for row in source.execute(select):
            yield int(row[0]), dict(zip(columns, row[1:]))
    else:
        order = ", ".join(_quote_sqlite_identifier(name) for name in pk)
        select = f"SELECT {projection} FROM {table_sql} ORDER BY {order}"
        for row in source.execute(select):
            yield None, dict(zip(columns, row))


def _primary_key_values(row: dict[str, Any], table: str, rowid: int | None) -> tuple[Any, str]:
    if table == "files":
        primary_key: Any = row.get("id")
    elif table == "catalog_items":
        primary_key = row.get("file_url")
    else:
        primary_key = None
    key = {"pk": _json_safe(primary_key)}
    if rowid is not None:
        key["rowid"] = rowid
    else:
        key["rowid"] = None
    return primary_key, _json_text(key)


def _source_metadata(row: dict[str, Any], table: str) -> dict[str, Any]:
    identity_fields = {"files": {"id", "url"}, "catalog_items": {"file_url"}}[table]
    return {
        name: value
        for name, value in row.items()
        if name not in _CONTENT_FIELDS and name not in identity_fields
    }


def _version_identity_key(
    url: str | None,
    raw_sha256: str | None,
    source_sha256: str,
    source_table: str,
    source_pk_json: str,
) -> str:
    if url is not None and raw_sha256 is not None:
        identity = b"url-version\0" + url.encode("utf-8") + b"\0" + raw_sha256.encode("ascii")
    else:
        identity = (
            b"source-version\0"
            + source_sha256.encode("ascii")
            + b"\0"
            + source_table.encode("ascii")
            + b"\0"
            + source_pk_json.encode("utf-8")
        )
    return hashlib.sha256(identity).hexdigest()


def _ensure_blob(
    cursor: Any,
    raw_sha256: str,
    *,
    byte_size: int | None,
    availability: str,
    cas_relpath: str,
) -> None:
    cursor.execute(
        "SELECT byte_size, cas_relpath, availability FROM content_blobs WHERE sha256 = %s FOR UPDATE",
        (raw_sha256,),
    )
    previous = cursor.fetchone()
    if previous is None:
        cursor.execute(
            "INSERT INTO content_blobs (sha256, byte_size, cas_relpath, availability, verified_at) "
            "VALUES (%s, %s, %s, %s, CASE WHEN %s = 'present' THEN CURRENT_TIMESTAMP ELSE NULL END)",
            (raw_sha256, byte_size, cas_relpath, availability, availability),
        )
        return
    old_size, old_path, old_availability = previous
    if old_path != cas_relpath or (
        old_size is not None and byte_size is not None and int(old_size) != int(byte_size)
    ):
        raise ContentHubError("A shared CAS hash has conflicting metadata")
    if availability == "present":
        cursor.execute(
            "UPDATE content_blobs SET byte_size = COALESCE(byte_size, %s), availability = 'present', "
            "verified_at = COALESCE(verified_at, CURRENT_TIMESTAMP) WHERE sha256 = %s",
            (byte_size, raw_sha256),
        )
    elif old_availability == "missing" and old_size is None and byte_size is not None:
        cursor.execute(
            "UPDATE content_blobs SET byte_size = %s WHERE sha256 = %s", (byte_size, raw_sha256)
        )


def _ensure_content_version(
    cursor: Any,
    *,
    url: str | None,
    raw_sha256: str | None,
    source_sha256: str,
    source_table: str,
    source_pk_json: str,
) -> int:
    url_json = _json_text(url)
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest() if url is not None else None
    identity_key = _version_identity_key(
        url, raw_sha256, source_sha256, source_table, source_pk_json
    )
    cursor.execute(
        "INSERT INTO content_versions (url_value_json, url_identity_sha256, raw_sha256, identity_key, blob_sha256) "
        "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (url_json, url_hash, raw_sha256, identity_key, raw_sha256),
    )
    if raw_sha256 is not None and url is not None:
        cursor.execute(
            "SELECT content_version_id, url_value_json, identity_key FROM content_versions "
            "WHERE url_identity_sha256 = %s AND raw_sha256 = %s",
            (url_hash, raw_sha256),
        )
    else:
        cursor.execute(
            "SELECT content_version_id, url_value_json, identity_key FROM content_versions WHERE identity_key = %s",
            (identity_key,),
        )
    row = cursor.fetchone()
    if row is None or row[1] != url_json or row[2] != identity_key:
        raise ContentHubError("Content version identity conflicts with an existing source")
    return int(row[0])


def _insert_variant(
    cursor: Any,
    *,
    snapshot_id: int,
    version_id: int,
    source_table: str,
    source_pk_json: str,
    field_name: str,
    payload: Any,
    recipe_identity: str,
    provenance: dict[str, Any],
) -> None:
    payload_json = _json_text(payload)
    payload_digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    candidates, language_code, detection = detect_language(payload, field_name)
    cursor.execute(
        "INSERT INTO text_variants (source_snapshot_id, content_version_id, source_table, source_pk_json, "
        "field_name, payload_value_json, payload_is_null, payload_sha256, language_code, "
        "language_candidates_json, language_detection_json, model_identity_json, recipe_identity_json, "
        "provenance_json) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (source_snapshot_id, source_table, source_pk_json, field_name, payload_sha256) DO NOTHING",
        (
            snapshot_id,
            version_id,
            source_table,
            source_pk_json,
            field_name,
            payload_json,
            payload is None,
            payload_digest,
            language_code,
            _json_text(candidates),
            _json_text(detection),
            _json_text("unknown"),
            _json_text(recipe_identity or "unknown"),
            _json_text(provenance),
        ),
    )


def detect_language(
    payload: Any, field_name: str
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    """Classify long summary/markdown text offline and retain uncertainty."""
    if field_name not in _LANGUAGE_FIELDS:
        return [], "und", {"method": "not_applicable", "seed": 0}
    if not isinstance(payload, str) or not payload.strip():
        return [], "und", {"method": "langdetect", "seed": 0, "reason": "empty_or_non_text"}
    sample = payload.strip()
    if len(sample) < 80:
        return [], "und", {"method": "langdetect", "seed": 0, "reason": "short_text"}
    if len(sample) > 6000:
        left, middle, right = (
            sample[:2500],
            sample[len(sample) // 2 - 500 : len(sample) // 2 + 500],
            sample[-2500:],
        )
        sample = left + "\n" + middle + "\n" + right
    try:
        from langdetect import DetectorFactory, detect_langs

        DetectorFactory.seed = 0
        probabilities = detect_langs(sample)
        candidates = [
            {"language": str(item.lang).lower(), "probability": round(float(item.prob), 6)}
            for item in probabilities[:5]
        ]
        version = importlib.metadata.version("langdetect")
    except Exception:
        return [], "und", {"method": "langdetect", "seed": 0, "reason": "detection_failed"}
    top = candidates[0] if candidates else None
    second = candidates[1]["probability"] if len(candidates) > 1 else 0.0
    margin = (top["probability"] - second) if top else 0.0
    detection = {
        "method": "langdetect",
        "version": version,
        "seed": 0,
        "confidence": top["probability"] if top else 0.0,
        "margin": round(margin, 6),
        "minimum_characters": 80,
        "sample_characters": len(sample),
    }
    if top is None or top["probability"] < 0.85 or margin < 0.20:
        detection["reason"] = "low_confidence_or_mixed"
        return candidates, "und", detection
    return candidates, top["language"], detection


def _manifest_row_for_source(
    row: dict[str, Any], manifest_file: dict[str, Any]
) -> tuple[str | None, int | None]:
    raw_sha256 = manifest_file["raw_sha256"]
    source_hash = _hash_source_value(row.get("sha256"))
    if source_hash is not None and source_hash != raw_sha256:
        raise ContentHubError("Source file hash changed after manifest validation")
    source_size = row.get("bytes")
    source_size = int(source_size) if source_size is not None else None
    if (
        source_size is not None
        and manifest_file["bytes"] is not None
        and source_size != manifest_file["bytes"]
    ):
        raise ContentHubError("Source file size changed after manifest validation")
    return raw_sha256, source_size


def import_content_snapshot(
    source_path: str | Path,
    manifest_path: str | Path,
    artifact_root: str | Path,
    data_root: str | Path,
    database_url: DatabaseConfig | str | None = None,
    *,
    schema: str = HUB_SCHEMA,
    expected_source_name: str | None = None,
) -> dict[str, Any]:
    """Verify and append one complete SQLite v16 content projection atomically."""
    schema = _validate_schema(schema)
    source_path = Path(source_path).expanduser().resolve()
    manifest_path = Path(manifest_path).expanduser().resolve()
    artifact_root = Path(artifact_root).expanduser().resolve()
    data_root = Path(data_root).expanduser().resolve()
    manifest = _validate_manifest(manifest_path, artifact_root)
    if expected_source_name is not None and expected_source_name != manifest.source_name:
        raise ContentHubError("Requested source name does not match the artifact manifest")
    verified_artifacts = _verify_artifacts(manifest, artifact_root)
    source, table_columns, table_counts, source_stat = _open_source_snapshot(source_path, manifest)
    pg: psycopg2.extensions.connection | None = None
    try:
        pg = _connect(database_url)
        with pg.cursor() as cursor:
            applied = _applied_migrations(cursor, schema)
            if max(applied, default=0) < HUB_SCHEMA_VERSION:
                raise ContentHubError(
                    "Content hub schema must be applied before importing a source"
                )
            _set_search_path(cursor, schema)
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"content_hub:import:{schema}",),
            )
            cursor.execute(
                "SELECT source_snapshot_id, snapshot_sha256, snapshot_bytes, manifest_sha256, staging_database_name "
                "FROM source_snapshots WHERE source_name = %s FOR UPDATE",
                (manifest.source_name,),
            )
            existing = cursor.fetchone()
            if existing is not None:
                if str(existing[1]) != manifest.snapshot_sha256:
                    raise ContentHubError(
                        "Source name is already bound to a different SQLite snapshot"
                    )
                if (
                    int(existing[2]) != manifest.snapshot_bytes
                    or str(existing[3]) != manifest.manifest_sha256
                    or existing[4] != manifest.staging_database_name
                ):
                    raise ContentHubError("Existing source snapshot conflicts with this manifest")
                _verify_import_counts(
                    cursor,
                    int(existing[0]),
                    table_counts,
                    table_columns,
                    len(manifest.files),
                    len(manifest.indexes),
                )
                pg.commit()
                result = _import_result(
                    manifest,
                    already_imported=True,
                    table_counts=table_counts,
                    file_count=len(manifest.files),
                    index_count=len(manifest.indexes),
                )
                _write_import_receipt(data_root, result)
                return result

            cursor.execute(
                "INSERT INTO source_snapshots (source_name, snapshot_sha256, snapshot_bytes, sqlite_user_version, "
                "manifest_sha256, staging_database_name, staging_snapshot_sha256) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING source_snapshot_id",
                (
                    manifest.source_name,
                    manifest.snapshot_sha256,
                    manifest.snapshot_bytes,
                    CURRENT_SQLITE_SCHEMA_VERSION,
                    manifest.manifest_sha256,
                    manifest.staging_database_name,
                    manifest.staging_snapshot_sha256,
                ),
            )
            snapshot_id = int(cursor.fetchone()[0])
            cursor.executemany(
                "INSERT INTO source_table_counts (source_snapshot_id, table_name, row_count) VALUES (%s, %s, %s)",
                [(snapshot_id, table, count) for table, count in sorted(table_counts.items())],
            )
            for entry in manifest.files:
                raw_sha256 = entry["raw_sha256"]
                if raw_sha256 is None:
                    continue
                artifact = verified_artifacts.get(raw_sha256)
                global_state = "present" if artifact else "missing"
                size = artifact["size"] if artifact else entry["bytes"]
                relpath = (
                    artifact["relpath"] if artifact else f"cas/sha256/{raw_sha256[:2]}/{raw_sha256}"
                )
                _ensure_blob(
                    cursor,
                    raw_sha256,
                    byte_size=size,
                    availability=global_state,
                    cas_relpath=relpath,
                )

            file_entries = {entry["legacy_id"]: entry for entry in manifest.files}
            file_columns = table_columns["files"]
            file_pk_info = source.execute('PRAGMA table_info("files")').fetchall()
            file_pk = [
                str(row[1]) for row in sorted(file_pk_info, key=lambda item: int(item[5])) if row[5]
            ]
            if file_pk != ["id"]:
                raise ContentHubError("SQLite files primary key is not the supported v16 identity")
            for rowid, row in _typed_source_rows(source, "files", file_columns, file_pk):
                legacy_id = int(row["id"])
                manifest_file = file_entries.get(legacy_id)
                if manifest_file is None:
                    raise ContentHubError(
                        "SQLite source file was not present in the validated manifest"
                    )
                raw_sha256, source_size = _manifest_row_for_source(row, manifest_file)
                _, source_pk_json = _primary_key_values(row, "files", rowid)
                url = row.get("url")
                if url is not None and not isinstance(url, str):
                    raise ContentHubError("SQLite file URL is not source text")
                if raw_sha256 is not None and raw_sha256 not in verified_artifacts:
                    _ensure_blob(
                        cursor,
                        raw_sha256,
                        byte_size=(
                            manifest_file["bytes"]
                            if manifest_file["bytes"] is not None
                            else source_size
                        ),
                        availability="missing",
                        cas_relpath=f"cas/sha256/{raw_sha256[:2]}/{raw_sha256}",
                    )
                version_id = _ensure_content_version(
                    cursor,
                    url=url,
                    raw_sha256=raw_sha256,
                    source_sha256=manifest.snapshot_sha256,
                    source_table="files",
                    source_pk_json=source_pk_json,
                )
                cursor.execute(
                    "INSERT INTO source_file_observations (source_snapshot_id, legacy_file_id, content_version_id, "
                    "file_url_json, raw_sha256, source_byte_size, artifact_byte_size, deleted_at_json, availability, "
                    "cas_relpath, verified_sha256, legacy_metadata_json) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        snapshot_id,
                        str(legacy_id),
                        version_id,
                        _json_text(url),
                        raw_sha256,
                        source_size,
                        verified_artifacts.get(raw_sha256, {}).get("size"),
                        _json_text(row.get("deleted_at")),
                        manifest_file["state"],
                        manifest_file["cas_relpath"],
                        manifest_file["verified_sha256"],
                        _json_text(row),
                    ),
                )
                cursor.execute(
                    "INSERT INTO source_record_map (source_snapshot_id, source_table, legacy_pk_json, "
                    "content_version_id, source_metadata_json) VALUES (%s, 'files', %s, %s, %s)",
                    (
                        snapshot_id,
                        source_pk_json,
                        version_id,
                        _json_text(_source_metadata(row, "files")),
                    ),
                )
                _import_text_fields(
                    cursor,
                    snapshot_id=snapshot_id,
                    version_id=version_id,
                    table="files",
                    source_pk_json=source_pk_json,
                    row=row,
                    table_columns=file_columns,
                )

            catalog_columns = table_columns["catalog_items"]
            catalog_pk_info = source.execute('PRAGMA table_info("catalog_items")').fetchall()
            catalog_pk = [
                str(row[1])
                for row in sorted(catalog_pk_info, key=lambda item: int(item[5]))
                if row[5]
            ]
            if catalog_pk != ["file_url"]:
                raise ContentHubError(
                    "SQLite catalog_items primary key is not the supported v16 identity"
                )
            for rowid, row in _typed_source_rows(
                source, "catalog_items", catalog_columns, catalog_pk
            ):
                _, source_pk_json = _primary_key_values(row, "catalog_items", rowid)
                url = row.get("file_url")
                if url is not None and not isinstance(url, str):
                    raise ContentHubError("SQLite catalog URL is not source text")
                raw_sha256 = _hash_source_value(row.get("sha256"))
                if raw_sha256 is None:
                    raw_sha256 = _hash_source_value(row.get("file_sha256"))
                if raw_sha256 is not None:
                    _ensure_blob(
                        cursor,
                        raw_sha256,
                        byte_size=None,
                        availability="missing",
                        cas_relpath=f"cas/sha256/{raw_sha256[:2]}/{raw_sha256}",
                    )
                version_id = _ensure_content_version(
                    cursor,
                    url=url,
                    raw_sha256=raw_sha256,
                    source_sha256=manifest.snapshot_sha256,
                    source_table="catalog_items",
                    source_pk_json=source_pk_json,
                )
                cursor.execute(
                    "INSERT INTO source_record_map (source_snapshot_id, source_table, legacy_pk_json, "
                    "content_version_id, source_metadata_json) VALUES (%s, 'catalog_items', %s, %s, %s)",
                    (
                        snapshot_id,
                        source_pk_json,
                        version_id,
                        _json_text(_source_metadata(row, "catalog_items")),
                    ),
                )
                recipe = str(row.get("pipeline_version") or row.get("catalog_version") or "unknown")
                provenance = {
                    name: row.get(name)
                    for name in (
                        "sha256",
                        "file_sha256",
                        "pipeline_version",
                        "catalog_version",
                        "processed_at",
                        "status",
                        "updated_at",
                    )
                    if name in row
                }
                _import_text_fields(
                    cursor,
                    snapshot_id=snapshot_id,
                    version_id=version_id,
                    table="catalog_items",
                    source_pk_json=source_pk_json,
                    row=row,
                    table_columns=catalog_columns,
                    recipe_identity=recipe,
                    provenance=provenance,
                )

            for entry in manifest.indexes:
                identity = entry["embedding_identity"]
                cursor.execute(
                    "INSERT INTO legacy_index_artifacts (source_snapshot_id, legacy_kb_id_json, artifact_kind, "
                    "source_path_json, artifact_relpath, sha256, byte_size, availability, embedding_provider_json, "
                    "embedding_model_json, embedding_dimension, profile_id_json, source_metadata_json) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        snapshot_id,
                        _json_text(entry["legacy_kb_id"]),
                        entry["artifact_kind"],
                        _json_text(entry["source_path"]),
                        entry["artifact_relpath"],
                        entry["sha256"],
                        entry["bytes"],
                        entry["state"],
                        _json_text(identity["provider"]),
                        _json_text(identity["model"]),
                        identity["dimension"],
                        _json_text(identity["profile_id"]),
                        _json_text(entry["source_metadata"]),
                    ),
                )

            _verify_import_counts(
                cursor,
                snapshot_id,
                table_counts,
                table_columns,
                len(manifest.files),
                len(manifest.indexes),
            )
            after_sha, after_size, after_stat = _source_sha256(source_path)
            if (
                after_sha != manifest.snapshot_sha256
                or after_size != manifest.snapshot_bytes
                or after_stat != source_stat
            ):
                raise ContentHubError(
                    "SQLite source changed while the content hub import was running"
                )
        pg.commit()
    except Exception:
        pg.rollback()
        raise
    finally:
        source.close()
        if pg is not None:
            pg.close()

    result = _import_result(
        manifest,
        already_imported=False,
        table_counts=table_counts,
        file_count=len(manifest.files),
        index_count=len(manifest.indexes),
    )
    _write_import_receipt(data_root, result)
    return result


def _import_text_fields(
    cursor: Any,
    *,
    snapshot_id: int,
    version_id: int,
    table: str,
    source_pk_json: str,
    row: dict[str, Any],
    table_columns: list[str],
    recipe_identity: str = "unknown",
    provenance: dict[str, Any] | None = None,
) -> None:
    provenance = provenance or {}
    for field_name in _CONTENT_FIELDS:
        if field_name not in table_columns:
            continue
        _insert_variant(
            cursor,
            snapshot_id=snapshot_id,
            version_id=version_id,
            source_table=table,
            source_pk_json=source_pk_json,
            field_name=field_name,
            payload=row.get(field_name),
            recipe_identity=recipe_identity,
            provenance=provenance,
        )


def _verify_import_counts(
    cursor: Any,
    snapshot_id: int,
    table_counts: dict[str, int],
    table_columns: dict[str, list[str]],
    file_count: int,
    index_count: int,
) -> None:
    cursor.execute(
        "SELECT table_name, row_count FROM source_table_counts WHERE source_snapshot_id = %s",
        (snapshot_id,),
    )
    recorded_counts = {str(table): int(count) for table, count in cursor.fetchall()}
    if recorded_counts != table_counts:
        raise ContentHubError("Imported source table counts do not match the SQLite snapshot")
    cursor.execute(
        "SELECT COUNT(*) FROM source_file_observations WHERE source_snapshot_id = %s",
        (snapshot_id,),
    )
    if int(cursor.fetchone()[0]) != file_count:
        raise ContentHubError("Imported file observation count does not match the source snapshot")
    cursor.execute(
        "SELECT source_table, COUNT(*) FROM source_record_map WHERE source_snapshot_id = %s "
        "GROUP BY source_table",
        (snapshot_id,),
    )
    record_counts = {str(table): int(count) for table, count in cursor.fetchall()}
    expected_record_counts = {
        table: table_counts[table] for table in ("files", "catalog_items") if table in table_counts
    }
    if record_counts != expected_record_counts:
        raise ContentHubError("Imported content crosswalk count does not match the source snapshot")

    expected_variants = sum(
        table_counts.get(table, 0)
        * sum(field_name in table_columns.get(table, []) for field_name in _CONTENT_FIELDS)
        for table in ("files", "catalog_items")
    )
    cursor.execute(
        "SELECT COUNT(*) FROM text_variants WHERE source_snapshot_id = %s", (snapshot_id,)
    )
    if int(cursor.fetchone()[0]) != expected_variants:
        raise ContentHubError("Imported text variant count does not match the source snapshot")

    cursor.execute(
        "SELECT COUNT(*) FROM legacy_index_artifacts WHERE source_snapshot_id = %s", (snapshot_id,)
    )
    if int(cursor.fetchone()[0]) != index_count:
        raise ContentHubError("Imported index artifact count does not match the source manifest")


def _import_result(
    manifest: ValidatedManifest,
    *,
    already_imported: bool,
    table_counts: dict[str, int],
    file_count: int,
    index_count: int,
) -> dict[str, Any]:
    return {
        "success": True,
        "source_name": manifest.source_name,
        "snapshot_sha256": manifest.snapshot_sha256,
        "manifest_sha256": manifest.manifest_sha256,
        "already_imported": already_imported,
        "table_count": len(table_counts),
        "table_counts": table_counts,
        "file_observation_count": file_count,
        "legacy_index_artifact_count": index_count,
    }


def _validate_bilingual_metadata_input(path: str | Path) -> list[dict[str, Any]]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContentHubError("Bilingual metadata input is not readable UTF-8 JSON") from exc
    if (
        not isinstance(document, dict)
        or document.get("format") != "ai_actuarial.content_hub.generated_metadata"
        or type(document.get("version")) is not int
        or document["version"] != 1
        or set(document) != {"format", "version", "items"}
    ):
        raise ContentHubError("Bilingual metadata input format or version is not supported")
    items = document["items"]
    if not isinstance(items, list) or not items:
        raise ContentHubError("Bilingual metadata input must contain a nonempty items array")

    from .catalog import CATEGORY_RULES

    allowed_categories = {"Other", *(CATEGORY_RULES or {}).keys()}
    required = {
        "content_version_id",
        "language_code",
        "markdown_text_variant_id",
        "markdown_sha256",
        "title",
        "summary",
        "category",
        "keywords",
        "recipe",
        "author",
    }
    normalized: dict[tuple[int, str], dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict) or set(item) != required:
            raise ContentHubError("Bilingual metadata item fields are invalid")
        version_id = item["content_version_id"]
        variant_id = item["markdown_text_variant_id"]
        language = item["language_code"]
        if type(version_id) is not int or version_id <= 0:
            raise ContentHubError(
                "Bilingual metadata content_version_id must be a positive integer"
            )
        if type(variant_id) is not int or variant_id <= 0:
            raise ContentHubError(
                "Bilingual metadata markdown_text_variant_id must be a positive integer"
            )
        if not isinstance(language, str) or language not in {"zh", "en"}:
            raise ContentHubError("Bilingual metadata language_code must be zh or en")
        digest = item["markdown_sha256"]
        if not isinstance(digest, str) or not _HASH_RE.fullmatch(digest):
            raise ContentHubError("Bilingual metadata markdown_sha256 is invalid")
        fields: dict[str, str] = {}
        for field in ("title", "summary", "category", "recipe", "author"):
            value = item[field]
            if not isinstance(value, str) or not value.strip():
                raise ContentHubError(f"Bilingual metadata {field} must be nonempty text")
            fields[field] = value.strip()
        if fields["category"] not in allowed_categories:
            raise ContentHubError("Bilingual metadata category is not in the configured taxonomy")
        keywords = item["keywords"]
        if not isinstance(keywords, list) or not keywords:
            raise ContentHubError("Bilingual metadata keywords must be a nonempty array")
        clean_keywords: list[str] = []
        seen_keywords: set[str] = set()
        for keyword in keywords:
            if not isinstance(keyword, str) or not keyword.strip():
                raise ContentHubError("Bilingual metadata keywords must contain nonempty text")
            value = keyword.strip()
            if value.casefold() not in seen_keywords:
                clean_keywords.append(value)
                seen_keywords.add(value.casefold())
        record = {
            "content_version_id": version_id,
            "language_code": language,
            "markdown_text_variant_id": variant_id,
            "markdown_sha256": digest,
            **fields,
            "keywords": clean_keywords,
        }
        key = (version_id, language)
        previous = normalized.get(key)
        if previous is not None and previous != record:
            raise ContentHubError("Bilingual metadata input has conflicting duplicate records")
        normalized[key] = record
    records = list(normalized.values())
    categories_by_version: dict[int, set[str]] = {}
    for record in records:
        categories_by_version.setdefault(record["content_version_id"], set()).add(
            record["category"]
        )
    if any(len(categories) > 1 for categories in categories_by_version.values()):
        raise ContentHubError(
            "Bilingual metadata languages for one content version must share a canonical category"
        )
    return records


def import_bilingual_metadata(
    input_path: str | Path,
    database_url: DatabaseConfig | str | None = None,
    *,
    schema: str = HUB_SCHEMA,
) -> dict[str, Any]:
    """Import generated zh/en metadata without changing source-attributed rows."""
    schema = _validate_schema(schema)
    records = _validate_bilingual_metadata_input(input_path)
    connection = _connect(database_url)
    inserted = filled = unchanged = 0
    try:
        with connection.cursor() as cursor:
            _require_current_schema(cursor, schema)
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"content_hub:bilingual_metadata:{schema}",),
            )
            locked_versions: set[int] = set()
            for record in records:
                version_id = record["content_version_id"]
                if version_id not in locked_versions:
                    cursor.execute(
                        "SELECT 1 FROM content_versions WHERE content_version_id = %s FOR UPDATE",
                        (version_id,),
                    )
                    if cursor.fetchone() is None:
                        raise ContentHubError(
                            "Bilingual metadata references an unknown content version"
                        )
                    locked_versions.add(version_id)
                cursor.execute(
                    "SELECT payload_value_json, payload_is_null, payload_sha256 "
                    "FROM text_variants WHERE text_variant_id = %s AND content_version_id = %s "
                    "AND field_name = 'markdown_content'",
                    (record["markdown_text_variant_id"], record["content_version_id"]),
                )
                markdown = cursor.fetchone()
                if markdown is None:
                    raise ContentHubError(
                        "Bilingual metadata Markdown variant does not match its content version"
                    )
                markdown_value = _load_json(markdown[0])
                if (
                    bool(markdown[1])
                    or not isinstance(markdown_value, str)
                    or not markdown_value.strip()
                    or str(markdown[2]).strip() != record["markdown_sha256"]
                ):
                    raise ContentHubError(
                        "Bilingual metadata Markdown digest does not match stored content"
                    )

            categories_by_version: dict[int, set[str]] = {}
            for record in records:
                categories_by_version.setdefault(record["content_version_id"], set()).add(
                    record["category"]
                )
            for version_id, incoming_categories in categories_by_version.items():
                if len(incoming_categories) != 1:
                    raise ContentHubError(
                        "Bilingual metadata languages for one content version must share a canonical category"
                    )
                incoming_category = next(iter(incoming_categories))
                cursor.execute(
                    "SELECT language_code, category FROM bilingual_metadata "
                    "WHERE content_version_id = %s FOR UPDATE",
                    (version_id,),
                )
                existing_categories = {
                    str(row[1]).strip()
                    for row in cursor.fetchall()
                    if isinstance(row[1], str) and row[1].strip()
                }
                if len(existing_categories) > 1 or any(
                    category != incoming_category for category in existing_categories
                ):
                    raise ContentHubError(
                        "Bilingual metadata category conflicts with an existing language package"
                    )

            for record in records:
                key = (record["content_version_id"], record["language_code"])
                cursor.execute(
                    "SELECT markdown_text_variant_id, markdown_sha256, title, summary, category, "
                    "keywords_json, provenance_json FROM bilingual_metadata "
                    "WHERE content_version_id = %s AND language_code = %s FOR UPDATE",
                    key,
                )
                existing = cursor.fetchone()
                if existing is None:
                    provenance = [
                        {
                            "recipe": record["recipe"],
                            "author": record["author"],
                            "fields": ["title", "summary", "category", "keywords"],
                        }
                    ]
                    cursor.execute(
                        "INSERT INTO bilingual_metadata (content_version_id, language_code, "
                        "markdown_text_variant_id, markdown_sha256, title, summary, category, "
                        "keywords_json, provenance_json) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            *key,
                            record["markdown_text_variant_id"],
                            record["markdown_sha256"],
                            record["title"],
                            record["summary"],
                            record["category"],
                            Json(record["keywords"]),
                            Json(provenance),
                        ),
                    )
                    inserted += 1
                    continue

                if (
                    int(existing[0]) != record["markdown_text_variant_id"]
                    or str(existing[1]).strip() != record["markdown_sha256"]
                ):
                    raise ContentHubError(
                        "Existing bilingual metadata is bound to a different Markdown variant"
                    )
                current = {
                    "title": existing[2],
                    "summary": existing[3],
                    "category": existing[4],
                    "keywords": existing[5],
                }
                merged = dict(current)
                filled_fields = []
                for field in ("title", "summary", "category", "keywords"):
                    if not current[field]:
                        merged[field] = record[field]
                        filled_fields.append(field)
                if not filled_fields:
                    unchanged += 1
                    continue
                provenance = list(existing[6])
                provenance.append(
                    {
                        "recipe": record["recipe"],
                        "author": record["author"],
                        "fields": filled_fields,
                    }
                )
                cursor.execute(
                    "UPDATE bilingual_metadata SET title = %s, summary = %s, category = %s, "
                    "keywords_json = %s, provenance_json = %s, updated_at = CURRENT_TIMESTAMP "
                    "WHERE content_version_id = %s AND language_code = %s",
                    (
                        merged["title"],
                        merged["summary"],
                        merged["category"],
                        Json(merged["keywords"]),
                        Json(provenance),
                        *key,
                    ),
                )
                filled += 1
        connection.commit()
        return {
            "success": True,
            "schema": schema,
            "item_count": len(records),
            "inserted_count": inserted,
            "filled_count": filled,
            "unchanged_count": unchanged,
        }
    except psycopg2.Error as exc:
        connection.rollback()
        raise ContentHubError("Bilingual metadata import failed") from exc
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _write_import_receipt(data_root: Path, result: dict[str, Any]) -> None:
    receipt_root = data_root / "content-hub" / "import-receipts" / result["source_name"]
    destination = receipt_root / f"{result['snapshot_sha256']}.json"
    temporary = destination.with_suffix(".json.tmp")
    canonical_result = {**result, "already_imported": False}
    payload = _json_text(canonical_result) + "\n"
    try:
        receipt_root.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            existing = destination.read_text(encoding="utf-8")
            if existing != payload:
                raise ContentHubError("Existing import receipt conflicts with the source snapshot")
            return
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        temporary.replace(destination)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ContentHubError("Could not write the sanitized content hub import receipt") from exc


def _require_current_schema(cursor: Any, schema: str) -> None:
    applied = _applied_migrations(cursor, schema)
    if max(applied, default=0) < HUB_SCHEMA_VERSION:
        raise ContentHubError("Content hub schema must be applied before querying it")
    _set_search_path(cursor, schema)


def content_hub_status(
    database_url: DatabaseConfig | str | None = None, *, schema: str = HUB_SCHEMA
) -> dict[str, Any]:
    schema = _validate_schema(schema)
    connection = _connect(database_url)
    try:
        with connection.cursor() as cursor:
            _require_current_schema(cursor, schema)
            cursor.execute(
                "SELECT source_name, snapshot_sha256, manifest_sha256, sqlite_user_version, "
                "staging_database_name, imported_at FROM source_snapshots ORDER BY source_name"
            )
            sources = [
                {
                    "source_name": row[0],
                    "snapshot_sha256": str(row[1]).strip(),
                    "manifest_sha256": str(row[2]).strip(),
                    "sqlite_user_version": int(row[3]),
                    "staging_database_name": row[4],
                    "imported_at": row[5].isoformat(),
                }
                for row in cursor.fetchall()
            ]
            cursor.execute("SELECT COUNT(*) FROM content_versions")
            version_count = int(cursor.fetchone()[0])
            cursor.execute("SELECT availability, COUNT(*) FROM content_blobs GROUP BY availability")
            blob_counts = {str(state): int(count) for state, count in cursor.fetchall()}
            cursor.execute("SELECT COUNT(*) FROM source_file_observations")
            file_observations = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT availability, COUNT(*) FROM source_file_observations GROUP BY availability"
            )
            file_states = {str(state): int(count) for state, count in cursor.fetchall()}
            cursor.execute("SELECT COUNT(*) FROM source_record_map")
            source_records = int(cursor.fetchone()[0])
            cursor.execute("SELECT COUNT(*) FROM text_variants")
            text_variants = int(cursor.fetchone()[0])
            cursor.execute(
                "SELECT language_code, COUNT(*) FROM bilingual_metadata GROUP BY language_code"
            )
            metadata_counts = {str(language): int(count) for language, count in cursor.fetchall()}
            cursor.execute(
                "SELECT availability, COUNT(*) FROM legacy_index_artifacts GROUP BY availability"
            )
            index_states = {str(state): int(count) for state, count in cursor.fetchall()}
            return {
                "success": True,
                "schema": schema,
                "schema_version": HUB_SCHEMA_VERSION,
                "source_count": len(sources),
                "sources": sources,
                "content_version_count": version_count,
                "content_blob_counts": {
                    state: blob_counts.get(state, 0) for state in ("present", "missing")
                },
                "source_file_observation_count": file_observations,
                "source_file_observation_counts": {
                    state: file_states.get(state, 0) for state in ("present", "missing")
                },
                "source_record_count": source_records,
                "text_variant_count": text_variants,
                "bilingual_metadata_count": sum(metadata_counts.values()),
                "bilingual_metadata_by_language": {
                    language: metadata_counts.get(language, 0) for language in ("zh", "en")
                },
                "legacy_index_artifact_counts": {
                    state: index_states.get(state, 0) for state in ("present", "missing")
                },
            }
    except psycopg2.Error as exc:
        raise ContentHubError("Content hub status query failed") from exc
    finally:
        connection.close()


def _load_json(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ContentHubError("Stored content hub JSON text is invalid") from exc


def content_hub_show_url(
    url: str,
    database_url: DatabaseConfig | str | None = None,
    *,
    schema: str = HUB_SCHEMA,
) -> dict[str, Any]:
    """Return every exact URL/hash version and source-attributed text variant."""
    if not isinstance(url, str):
        raise ContentHubError("URL must be source text")
    schema = _validate_schema(schema)
    url_digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    connection = _connect(database_url)
    try:
        with connection.cursor() as cursor:
            _require_current_schema(cursor, schema)
            cursor.execute(
                "SELECT content_version_id, url_value_json, raw_sha256, blob_sha256 "
                "FROM content_versions WHERE url_identity_sha256 = %s ORDER BY raw_sha256 NULLS FIRST, "
                "content_version_id",
                (url_digest,),
            )
            versions = []
            for version_id, url_json, raw_sha256, blob_sha256 in cursor.fetchall():
                stored_url = _load_json(url_json)
                if stored_url != url:
                    raise ContentHubError("Stored URL digest conflicts with its source value")
                versions.append(
                    {
                        "content_version_id": int(version_id),
                        "url": stored_url,
                        "raw_sha256": str(raw_sha256).strip() if raw_sha256 else None,
                        "blob_sha256": str(blob_sha256).strip() if blob_sha256 else None,
                        "bilingual_metadata": {},
                    }
                )
            version_ids = [item["content_version_id"] for item in versions]
            versions_by_id = {item["content_version_id"]: item for item in versions}
            variants: list[dict[str, Any]] = []
            observations: list[dict[str, Any]] = []
            if version_ids:
                cursor.execute(
                    "SELECT s.source_name, r.source_table, r.legacy_pk_json, r.source_metadata_json "
                    "FROM source_record_map r JOIN source_snapshots s USING (source_snapshot_id) "
                    "WHERE r.content_version_id = ANY(%s) "
                    "ORDER BY s.source_name, r.source_table, r.legacy_pk_json",
                    (version_ids,),
                )
                source_records = [
                    {
                        "source_name": row[0],
                        "source_table": row[1],
                        "source_primary_key": _load_json(row[2]),
                        "source_metadata": _load_json(row[3]),
                    }
                    for row in cursor.fetchall()
                ]
                cursor.execute(
                    "SELECT s.source_name, o.legacy_file_id, o.raw_sha256, o.source_byte_size, "
                    "o.artifact_byte_size, o.deleted_at_json, o.availability, o.cas_relpath, "
                    "o.verified_sha256, o.legacy_metadata_json "
                    "FROM source_file_observations o JOIN source_snapshots s USING (source_snapshot_id) "
                    "WHERE o.content_version_id = ANY(%s) ORDER BY s.source_name, o.legacy_file_id",
                    (version_ids,),
                )
                observations = [
                    {
                        "source_name": row[0],
                        "legacy_file_id": row[1],
                        "raw_sha256": str(row[2]).strip() if row[2] else None,
                        "source_byte_size": row[3],
                        "artifact_byte_size": row[4],
                        "deleted_at": _load_json(row[5]),
                        "availability": row[6],
                        "cas_relpath": row[7],
                        "verified_sha256": str(row[8]).strip() if row[8] else None,
                        "legacy_metadata": _load_json(row[9]),
                    }
                    for row in cursor.fetchall()
                ]
                cursor.execute(
                    "SELECT v.text_variant_id, s.source_name, v.source_table, v.source_pk_json, v.field_name, "
                    "v.payload_value_json, v.payload_is_null, v.payload_sha256, v.language_code, "
                    "v.language_candidates_json, v.language_detection_json, v.model_identity_json, "
                    "v.recipe_identity_json, v.provenance_json "
                    "FROM text_variants v JOIN source_snapshots s USING (source_snapshot_id) "
                    "WHERE v.content_version_id = ANY(%s) "
                    "ORDER BY s.source_name, v.source_table, v.source_pk_json, v.field_name, v.payload_sha256",
                    (version_ids,),
                )
                variants = [
                    {
                        "text_variant_id": int(row[0]),
                        "source_name": row[1],
                        "source_table": row[2],
                        "source_primary_key": _load_json(row[3]),
                        "field_name": row[4],
                        "value": _load_json(row[5]),
                        "is_null": bool(row[6]),
                        "payload_sha256": str(row[7]).strip(),
                        "language": row[8],
                        "language_candidates": _load_json(row[9]),
                        "language_detection": _load_json(row[10]),
                        "model_identity": _load_json(row[11]),
                        "recipe_identity": _load_json(row[12]),
                        "provenance": _load_json(row[13]),
                    }
                    for row in cursor.fetchall()
                ]
                cursor.execute(
                    "SELECT content_version_id, language_code, markdown_text_variant_id, "
                    "markdown_sha256, title, summary, category, keywords_json, provenance_json, "
                    "created_at, updated_at FROM bilingual_metadata "
                    "WHERE content_version_id = ANY(%s) ORDER BY content_version_id, language_code",
                    (version_ids,),
                )
                for row in cursor.fetchall():
                    versions_by_id[int(row[0])]["bilingual_metadata"][row[1]] = {
                        "markdown_text_variant_id": int(row[2]),
                        "markdown_sha256": str(row[3]).strip(),
                        "title": row[4],
                        "summary": row[5],
                        "category": row[6],
                        "keywords": row[7],
                        "provenance": row[8],
                        "created_at": row[9].isoformat(),
                        "updated_at": row[10].isoformat(),
                    }
            return {
                "success": True,
                "url": url,
                "versions": versions,
                "source_records": source_records if version_ids else [],
                "source_file_observations": observations,
                "text_variants": variants,
            }
    except psycopg2.Error as exc:
        raise ContentHubError("Content hub URL query failed") from exc
    finally:
        connection.close()


def sync_content_hub_catalog_metadata(
    target_database_url: DatabaseConfig | str,
    hub_database_url: DatabaseConfig | str | None = None,
    *,
    schema: str = HUB_SCHEMA,
) -> dict[str, Any]:
    """Fill missing catalog translations from exact URL and original-file versions.

    The content hub connection is read-only. The target must already be an initialized
    application database; it is checked before Storage is allowed to run migrations.
    """
    schema = _validate_schema(schema)
    from .postgres import PostgresConnection
    from .storage import Storage

    target_config = (
        target_database_url
        if isinstance(target_database_url, DatabaseConfig)
        else DatabaseConfig(str(target_database_url))
    )
    hub_url = _database_url(hub_database_url)
    target_probe = PostgresConnection(target_config, read_only=True)
    try:
        target_identity = target_probe.execute(
            "SELECT current_database(), COALESCE(inet_server_addr()::text, ''), "
            "inet_server_port(), current_schema()"
        ).fetchone()
        if not target_probe.table_exists("files") or not target_probe.table_exists("catalog_items"):
            raise ContentHubError(
                "Target DATABASE_URL must point to an initialized application storage schema"
            )
        target_columns = target_probe.table_columns("catalog_items")
        if not {"file_url", "sha256", "category"}.issubset(target_columns):
            raise ContentHubError("Target catalog_items table is not an application catalog")
        if not target_probe.table_exists("ai_actuarial_schema_migrations"):
            raise ContentHubError("Target database does not have the application migration ledger")
        target_version = int(
            target_probe.execute(
                "SELECT COALESCE(MAX(version), 0) FROM ai_actuarial_schema_migrations"
            ).fetchone()[0]
        )
        if target_version < 2:
            raise ContentHubError("Target application database must be migrated through v2")
    finally:
        target_probe.close()

    hub_connection = _connect(hub_url)
    try:
        hub_connection.set_session(readonly=True, autocommit=False)
        with hub_connection.cursor() as cursor:
            _require_current_schema(cursor, schema)
            cursor.execute(
                "SELECT current_database(), COALESCE(inet_server_addr()::text, ''), "
                "inet_server_port(), current_schema()"
            )
            hub_identity = cursor.fetchone()
            # A separate schema in the same PostgreSQL database is still the same physical
            # database. Reject it before Storage can run application migrations there.
            if (
                str(hub_identity[0]) == str(target_identity[0])
                and str(hub_identity[1]) == str(target_identity[1])
                and hub_identity[2] == target_identity[2]
            ):
                raise ContentHubError(
                    "Content hub and target must be separate PostgreSQL databases"
                )
            cursor.execute(
                "SELECT cv.content_version_id, cv.url_value_json, cv.url_identity_sha256, "
                "cv.raw_sha256, "
                "bm.language_code, bm.markdown_text_variant_id, bm.markdown_sha256, "
                "bm.title, bm.summary, bm.category, bm.keywords_json, "
                "tv.content_version_id, tv.field_name, tv.payload_value_json, "
                "tv.payload_is_null, tv.payload_sha256 "
                "FROM content_versions cv JOIN bilingual_metadata bm "
                "ON bm.content_version_id = cv.content_version_id "
                "LEFT JOIN text_variants tv ON tv.text_variant_id = bm.markdown_text_variant_id "
                "ORDER BY cv.content_version_id, bm.language_code"
            )
            rows = cursor.fetchall()
    except psycopg2.Error as exc:
        raise ContentHubError("Content hub catalog metadata query failed") from exc
    finally:
        hub_connection.close()

    from .catalog import CATEGORY_RULES

    allowed_categories = {"Other", *(CATEGORY_RULES or {}).keys()}
    versions: dict[tuple[str, str], dict[str, Any]] = {}
    invalid_identities: set[tuple[str, str]] = set()
    identity_versions: dict[tuple[str, str], set[int]] = {}
    unmatched_source_rows = 0
    for row in rows:
        (
            version_id,
            url_value,
            url_identity_sha,
            raw_sha,
            language,
            variant_id,
            markdown_sha,
            title,
            summary,
            category,
            keywords,
            variant_version_id,
            field_name,
            markdown_json,
            markdown_is_null,
            variant_sha,
        ) = row
        try:
            url = _load_json(url_value) if isinstance(url_value, str) else url_value
        except ContentHubError:
            url = None
        digest = str(raw_sha or "").strip().lower()
        if not isinstance(url, str) or not url.strip() or not _HASH_RE.fullmatch(digest):
            unmatched_source_rows += 1
            continue
        expected_url_sha = hashlib.sha256(url.encode("utf-8")).hexdigest()
        if str(url_identity_sha or "").strip().lower() != expected_url_sha:
            invalid_identities.add((url, digest))
        identity = (url, digest)
        identity_versions.setdefault(identity, set()).add(int(version_id))
        is_valid_variant = (
            variant_version_id is not None
            and int(variant_version_id) == int(version_id)
            and field_name == "markdown_content"
            and not bool(markdown_is_null)
            and isinstance(markdown_sha, str)
            and _HASH_RE.fullmatch(str(markdown_sha).strip().lower())
            and str(variant_sha or "").strip().lower() == str(markdown_sha).strip().lower()
        )
        try:
            markdown_value = (
                _load_json(markdown_json) if isinstance(markdown_json, str) else markdown_json
            )
        except ContentHubError:
            markdown_value = None
        markdown_json_text = (
            markdown_json if isinstance(markdown_json, str) else _json_text(markdown_json)
        )
        expected_markdown_sha = hashlib.sha256(markdown_json_text.encode("utf-8")).hexdigest()
        if (
            not is_valid_variant
            or not isinstance(markdown_value, str)
            or not markdown_value.strip()
            or str(variant_sha or "").strip().lower() != expected_markdown_sha
        ):
            invalid_identities.add(identity)
            continue
        if language not in {"zh", "en"}:
            invalid_identities.add(identity)
            continue
        clean_title = str(title or "").strip()
        clean_summary = str(summary or "").strip()
        clean_category = str(category or "").strip()
        if (
            not clean_title
            or not clean_summary
            or clean_category not in allowed_categories
            or not isinstance(keywords, list)
            or not [item for item in keywords if isinstance(item, str) and item.strip()]
        ):
            invalid_identities.add(identity)
            continue
        record = versions.setdefault(
            identity,
            {"content_version_id": int(version_id), "metadata_by_language": {}},
        )
        language_record = {
            "title": clean_title,
            "summary": clean_summary,
            "category": clean_category,
            "keywords": [
                item.strip() for item in keywords if isinstance(item, str) and item.strip()
            ],
            "hub_binding": {
                "content_version_id": int(version_id),
                "markdown_text_variant_id": int(variant_id),
                "markdown_sha256": str(markdown_sha).strip().lower(),
            },
        }
        previous = record["metadata_by_language"].get(language)
        if previous is not None and previous != language_record:
            invalid_identities.add(identity)
        record["metadata_by_language"][language] = language_record

    for identity, version_ids in identity_versions.items():
        if len(version_ids) != 1:
            invalid_identities.add(identity)

    # Preflight is complete before this constructor can apply a target schema migration.
    target_storage = Storage(target_config, data_root=Path.cwd())
    try:
        totals = {
            "success": True,
            "source_version_count": len(
                {
                    version_id
                    for version_ids in identity_versions.values()
                    for version_id in version_ids
                }
            ),
            "metadata_record_count": len(rows),
            "updated_count": 0,
            "unchanged_count": 0,
            "unmatched_count": unmatched_source_rows,
            "version_changed_count": 0,
            "conflict_count": 0,
            "field_fill_count": 0,
        }
        for identity in sorted(identity_versions):
            if identity in invalid_identities:
                totals["conflict_count"] += 1
                continue
            record = versions.get(identity)
            if record is None:
                totals["conflict_count"] += 1
                continue
            disposition, filled = target_storage.merge_hub_bilingual_metadata(
                url=identity[0],
                file_sha256=identity[1],
                metadata_by_language=record["metadata_by_language"],
            )
            if disposition == "updated":
                totals["updated_count"] += 1
                totals["field_fill_count"] += filled
            elif disposition == "unchanged":
                totals["unchanged_count"] += 1
            elif disposition == "version_changed":
                totals["version_changed_count"] += 1
            elif disposition == "conflict":
                totals["conflict_count"] += 1
            else:
                totals["unmatched_count"] += 1
        return totals
    finally:
        target_storage.close()
