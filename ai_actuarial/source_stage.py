"""Versioned, lossless SQLite-v16 row staging in the established raw_source layout."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import re
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

import psycopg2
from psycopg2 import sql

from .postgres import DatabaseConfig
from .postgres_import import SQLiteImportError, _source_snapshot

SOURCE_STAGE_SCHEMA = "raw_source"
SOURCE_STAGE_VERSION = 1
SOURCE_STAGE_FORMAT = "lossless-sqlite-row-json-text-v1"
_BATCH_SIZE = 500
_SOURCE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SCHEMA_RE = re.compile(r"^(?:raw_source|test_[A-Za-z0-9_]{1,58})$")
_MIGRATION_DIR = Path(__file__).with_name("source_stage_migrations")


class SourceStageError(RuntimeError):
    """A lossless source stage could not be safely created or verified."""


def _validate_schema(schema: str) -> str:
    if not isinstance(schema, str) or not _SCHEMA_RE.fullmatch(schema):
        raise SourceStageError("Source stage schema must be raw_source or an owned test_* schema")
    return schema


def _migration_files() -> list[tuple[int, str, bytes]]:
    migrations = []
    for path in _MIGRATION_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"):
        migrations.append((int(path.name.split("_", 1)[0]), path.name, path.read_bytes()))
    migrations.sort()
    if [item[0] for item in migrations] != list(range(1, len(migrations) + 1)):
        raise SourceStageError("Source-stage migrations must be numbered without gaps")
    return migrations


def _checksum(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _connect(database_url: DatabaseConfig | str | None) -> psycopg2.extensions.connection:
    value = database_url
    if value is None:
        value = os.getenv("CONTENT_HUB_STAGE_DATABASE_URL", "").strip()
    if not value:
        raise SourceStageError(
            "CONTENT_HUB_STAGE_DATABASE_URL must name the dedicated lossless source-stage database"
        )
    try:
        return psycopg2.connect(DatabaseConfig(str(value))._url)
    except (psycopg2.Error, ValueError) as exc:
        raise SourceStageError("Could not connect to the configured source-stage database") from exc


def _database_identity(value: DatabaseConfig | str) -> tuple[str, int, str]:
    config = value if isinstance(value, DatabaseConfig) else DatabaseConfig(str(value))
    parsed = urlsplit(config._url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    host = (
        (query.get("hostaddr") or parsed.hostname or query.get("host", "")).rstrip(".").casefold()
    )
    if host == "localhost":
        host = "<loopback>"
    else:
        try:
            address = ipaddress.ip_address(host)
            if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
                address = address.ipv4_mapped
            if address.is_loopback:
                host = "<loopback>"
            else:
                host = address.compressed
        except ValueError:
            pass
    port = parsed.port or int(query.get("port", "5432"))
    database = unquote(parsed.path.lstrip("/")) or unquote(query.get("dbname", ""))
    return host, port, database


def _require_separate_database(
    stage_database_url: DatabaseConfig | str,
    hub_database_url: DatabaseConfig | str | None,
) -> None:
    hub_url = hub_database_url
    if hub_url is None:
        hub_url = os.getenv("CONTENT_HUB_DATABASE_URL", "").strip()
    if not hub_url:
        raise SourceStageError(
            "CONTENT_HUB_DATABASE_URL is required so source staging cannot target the content hub database"
        )
    try:
        if _database_identity(stage_database_url) == _database_identity(hub_url):
            raise SourceStageError(
                "Source staging and the content hub must use separate PostgreSQL databases"
            )
    except ValueError as exc:
        raise SourceStageError("Configured PostgreSQL database identity is invalid") from exc


def _set_search_path(cursor: Any, schema: str) -> None:
    cursor.execute(sql.SQL("SET search_path TO {}, pg_catalog").format(sql.Identifier(schema)))


def _schema_exists(cursor: Any, schema: str) -> bool:
    cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = %s)", (schema,))
    return bool(cursor.fetchone()[0])


def _applied_migrations(cursor: Any, schema: str) -> dict[int, tuple[str, str]]:
    if not _schema_exists(cursor, schema):
        return {}
    _set_search_path(cursor, schema)
    cursor.execute("SELECT to_regclass('schema_migrations') IS NOT NULL")
    if not cursor.fetchone()[0]:
        return {}
    cursor.execute("SELECT version, filename, checksum FROM schema_migrations ORDER BY version")
    return {int(row[0]): (str(row[1]), str(row[2])) for row in cursor.fetchall()}


def source_stage_schema_plan(
    database_url: DatabaseConfig | str | None = None, *, schema: str = SOURCE_STAGE_SCHEMA
) -> dict[str, Any]:
    schema = _validate_schema(schema)
    migrations = _migration_files()
    connection = _connect(database_url)
    try:
        with connection.cursor() as cursor:
            applied = _applied_migrations(cursor, schema)
            for version, (filename, checksum) in applied.items():
                expected = next((item for item in migrations if item[0] == version), None)
                if expected is None or (expected[1], _checksum(expected[2])) != (
                    filename,
                    checksum,
                ):
                    raise SourceStageError(
                        "An applied source-stage migration does not match this release"
                    )
            return {
                "schema": schema,
                "current_version": max(applied, default=0),
                "target_version": len(migrations),
                "pending": [
                    {"version": version, "file": filename}
                    for version, filename, _ in migrations
                    if version not in applied
                ],
            }
    finally:
        connection.close()


def _apply_schema(cursor: Any, schema: str) -> int:
    cursor.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
    cursor.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = %s ORDER BY tablename", (schema,)
    )
    existing_tables = {str(row[0]) for row in cursor.fetchall()}
    expected_tables = {"schema_migrations", "snapshot", "table_rows"}
    if existing_tables - expected_tables:
        raise SourceStageError("Source-stage schema contains unrelated tables")

    _set_search_path(cursor, schema)
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, filename TEXT NOT NULL, checksum CHAR(64) NOT NULL, "
        "applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    migrations = _migration_files()
    cursor.execute("SELECT version, filename, checksum FROM schema_migrations ORDER BY version")
    applied = {int(row[0]): (str(row[1]), str(row[2])) for row in cursor.fetchall()}
    for version, (filename, checksum) in applied.items():
        expected = next((item for item in migrations if item[0] == version), None)
        if expected is None or (expected[1], _checksum(expected[2])) != (filename, checksum):
            raise SourceStageError("An applied source-stage migration does not match this release")
    for version, filename, payload in migrations:
        if version in applied:
            continue
        cursor.execute(payload.decode("utf-8"))
        cursor.execute(
            "INSERT INTO schema_migrations (version, filename, checksum) VALUES (%s, %s, %s)",
            (version, filename, _checksum(payload)),
        )

    cursor.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = %s ORDER BY tablename", (schema,)
    )
    if {str(row[0]) for row in cursor.fetchall()} != expected_tables:
        raise SourceStageError("Source-stage schema does not match its migration")
    return len(migrations)


def encode_source_row(rowid: int | None, values: tuple[Any, ...]) -> str:
    """Keep the established JSON row encoding, escaping NUL and hex-encoding BLOBs."""
    normalized = []
    for value in values:
        if isinstance(value, bytes):
            normalized.append({"sqlite_blob_hex": value.hex()})
        elif isinstance(value, float) and not math.isfinite(value):
            normalized.append({"sqlite_float": repr(value)})
        else:
            normalized.append(value)
    return json.dumps(
        {"rowid": rowid, "values": normalized},
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sqlite_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _schema_json(
    source: sqlite3.Connection,
    metadata: dict[str, tuple[list[str], list[str], set[str]]],
) -> str:
    objects = [
        tuple(row)
        for row in source.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
        )
    ]
    sequence = []
    if source.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sqlite_sequence'"
    ).fetchone():
        sequence = source.execute("SELECT name, seq FROM sqlite_sequence").fetchall()
    document = {
        "sqlite_user_version": 16,
        "sqlite_master": objects,
        "columns": {table: item[0] for table, item in metadata.items()},
        "primary_keys": {table: item[1] for table, item in metadata.items()},
        "sqlite_sequence": sequence,
    }
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"))


def _rowid_column(source: sqlite3.Connection, table: str, columns: list[str]) -> str | None:
    column_names = {name.casefold() for name in columns}
    table_name = _sqlite_identifier(table)
    for candidate in ("rowid", "_rowid_", "oid"):
        if candidate in column_names:
            continue
        try:
            source.execute(f"SELECT {candidate} FROM {table_name} LIMIT 0")
            return candidate
        except sqlite3.OperationalError:
            continue
    return None


def _sqlite_rows(
    source: sqlite3.Connection,
    table: str,
    columns: list[str],
    primary_key: list[str],
) -> tuple[sqlite3.Cursor, bool]:
    quoted_table = _sqlite_identifier(table)
    quoted_columns = ",".join(_sqlite_identifier(column) for column in columns)
    rowid_column = _rowid_column(source, table, columns)
    order = ",".join(_sqlite_identifier(column) for column in primary_key)
    if rowid_column is None:
        return (
            source.execute(f"SELECT {quoted_columns} FROM {quoted_table} ORDER BY {order}"),
            False,
        )
    return (
        source.execute(
            f"SELECT {rowid_column},{quoted_columns} FROM {quoted_table} ORDER BY {order}"
        ),
        True,
    )


def _file_sha256(path: Path) -> tuple[str, int, tuple[int, int]]:
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise SourceStageError("SQLite source changed while its hash was checked")
    return digest.hexdigest(), int(after.st_size), (after.st_size, after.st_mtime_ns)


def _verify_stored_rows(
    connection: psycopg2.extensions.connection,
    schema: str,
    expected_counts: dict[str, int],
    expected_digests: dict[str, str],
) -> None:
    counts: dict[str, int] = {}
    hashes: dict[str, Any] = {}
    previous_ordinals: dict[str, int] = {}
    with connection.cursor(name="verify_lossless_source_rows") as cursor:
        cursor.execute(
            sql.SQL(
                "SELECT table_name, row_number, row_json FROM {} ORDER BY table_name, row_number"
            ).format(sql.Identifier(schema, "table_rows"))
        )
        while rows := cursor.fetchmany(_BATCH_SIZE):
            for table, row_number, payload in rows:
                table = str(table)
                ordinal = int(row_number)
                if ordinal != previous_ordinals.get(table, 0):
                    raise SourceStageError("Stored source-stage row ordinals are not contiguous")
                previous_ordinals[table] = ordinal + 1
                counts[table] = counts.get(table, 0) + 1
                hashes.setdefault(table, hashlib.sha256()).update(
                    str(payload).encode("utf-8") + b"\n"
                )
    observed_counts = {table: counts.get(table, 0) for table in expected_counts}
    observed_digests = {
        table: hashes[table].hexdigest() if table in hashes else hashlib.sha256().hexdigest()
        for table in expected_counts
    }
    if counts.keys() - expected_counts.keys() or observed_counts != expected_counts:
        raise SourceStageError("Stored source-stage row counts do not match their snapshot")
    if observed_digests != expected_digests:
        raise SourceStageError("Stored source-stage rows do not match their recorded digests")


def _existing_snapshot(
    cursor: Any,
    source_name: str,
    source_sha256: str,
    schema_json: str,
    row_counts: dict[str, int],
) -> tuple[dict[str, int], dict[str, str]] | None:
    cursor.execute(
        "SELECT source_name, source_sha256, schema_json, table_counts_json, "
        "table_digests_json, format_version FROM snapshot"
    )
    rows = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) FROM table_rows")
    staged_rows = int(cursor.fetchone()[0])
    if not rows:
        if staged_rows:
            raise SourceStageError("Source-stage rows exist without snapshot metadata")
        return None
    if len(rows) != 1:
        raise SourceStageError("Source-stage database contains more than one source snapshot")
    old_name, old_sha, old_schema, old_counts_json, old_digests_json, version = rows[0]
    if old_name != source_name or str(old_sha) != source_sha256 or int(version) != 1:
        raise SourceStageError(
            "Source-stage database is already bound to a different source snapshot"
        )
    if old_schema != schema_json:
        raise SourceStageError("Source-stage schema metadata conflicts with this source snapshot")
    try:
        old_counts = json.loads(old_counts_json)
        old_digests = json.loads(old_digests_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise SourceStageError("Stored source-stage verification metadata is invalid") from exc
    normalized_counts = {str(name): int(count) for name, count in old_counts.items()}
    normalized_digests = {str(name): str(value) for name, value in old_digests.items()}
    if normalized_counts != row_counts or set(normalized_digests) != set(row_counts):
        raise SourceStageError("Source-stage row counts conflict with this snapshot")
    if staged_rows != sum(row_counts.values()):
        raise SourceStageError("Stored source-stage row count does not match its metadata")
    return normalized_counts, normalized_digests


def stage_sqlite_v16(
    source_path: str | Path,
    source_name: str,
    database_url: DatabaseConfig | str | None = None,
    *,
    hub_database_url: DatabaseConfig | str | None = None,
    schema: str = SOURCE_STAGE_SCHEMA,
) -> dict[str, Any]:
    """Stage a validated v16 source in bounded batches and verify its stored JSON rows."""
    schema = _validate_schema(schema)
    if not isinstance(source_name, str) or not _SOURCE_NAME_RE.fullmatch(source_name):
        raise SourceStageError("source_name must be a lowercase identifier")
    stage_url_value = database_url or os.getenv("CONTENT_HUB_STAGE_DATABASE_URL", "").strip()
    if not stage_url_value:
        raise SourceStageError("CONTENT_HUB_STAGE_DATABASE_URL is required")
    _require_separate_database(stage_url_value, hub_database_url)

    path = Path(source_path).expanduser().resolve()
    try:
        before_stat = path.stat()
        source, table_metadata, row_counts, source_sha256 = _source_snapshot(path)
    except (OSError, SQLiteImportError) as exc:
        raise SourceStageError(
            "SQLite v16 source could not be read as a checkpointed snapshot"
        ) from exc

    connection: psycopg2.extensions.connection | None = None
    digests: dict[str, str] = {}
    try:
        schema_json = _schema_json(source, table_metadata)
        initial_sha, source_bytes, source_stat = _file_sha256(path)
        if initial_sha != source_sha256:
            raise SourceStageError("SQLite source changed after read-only validation")

        connection = _connect(stage_url_value)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"source_stage:import:{schema}",),
            )
            migration_version = _apply_schema(cursor, schema)
            if migration_version != SOURCE_STAGE_VERSION:
                raise SourceStageError(
                    "Source-stage PostgreSQL schema is not at the current version"
                )
            _set_search_path(cursor, schema)
            existing = _existing_snapshot(
                cursor, source_name, source_sha256, schema_json, row_counts
            )
            if existing is not None:
                stored_counts, stored_digests = existing
                _verify_stored_rows(connection, schema, stored_counts, stored_digests)
                final_sha, final_bytes, final_stat = _file_sha256(path)
                if (
                    final_sha != source_sha256
                    or final_bytes != source_bytes
                    or final_stat != source_stat
                ):
                    raise SourceStageError("SQLite source changed while its stage was verified")
                connection.commit()
                return {
                    "success": True,
                    "state": "unchanged",
                    "source_name": source_name,
                    "snapshot_sha256": source_sha256,
                    "table_count": len(row_counts),
                    "table_counts": row_counts,
                    "row_format": SOURCE_STAGE_FORMAT,
                }

            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM snapshot) OR EXISTS (SELECT 1 FROM table_rows)"
            )
            if cursor.fetchone()[0]:
                raise SourceStageError("Source-stage database is not empty")

            for table in sorted(table_metadata):
                columns, primary_key, _text_key_columns = table_metadata[table]
                reader, has_rowid = _sqlite_rows(source, table, columns, primary_key)
                digest = hashlib.sha256()
                row_number = 0
                while rows := reader.fetchmany(_BATCH_SIZE):
                    batch = []
                    for source_row in rows:
                        if has_rowid:
                            rowid, values = int(source_row[0]), tuple(source_row[1:])
                        else:
                            rowid, values = None, tuple(source_row)
                        payload = encode_source_row(rowid, values)
                        if "\x00" in payload:
                            raise SourceStageError(
                                "Encoded SQLite row contains an invalid PostgreSQL TEXT NUL"
                            )
                        digest.update(payload.encode("utf-8") + b"\n")
                        batch.append((table, row_number, payload))
                        row_number += 1
                    cursor.executemany(
                        "INSERT INTO table_rows (table_name, row_number, row_json) VALUES (%s, %s, %s)",
                        batch,
                    )
                if row_number != row_counts[table]:
                    raise SourceStageError("SQLite row count changed while the source was staged")
                digests[table] = digest.hexdigest()

            counts_json = json.dumps(row_counts)
            digests_json = json.dumps(digests)
            cursor.execute(
                "INSERT INTO snapshot "
                "(source_name, source_sha256, schema_json, table_counts_json, table_digests_json, format_version) "
                "VALUES (%s, %s, %s, %s, %s, 1)",
                (source_name, source_sha256, schema_json, counts_json, digests_json),
            )
            _verify_stored_rows(connection, schema, row_counts, digests)
            final_sha, final_bytes, final_stat = _file_sha256(path)
            if (
                final_sha != source_sha256
                or final_bytes != source_bytes
                or final_stat != source_stat
                or (before_stat.st_size, before_stat.st_mtime_ns) != final_stat
            ):
                raise SourceStageError("SQLite source changed while its stage was written")
        connection.commit()
        return {
            "success": True,
            "state": "verified",
            "source_name": source_name,
            "snapshot_sha256": source_sha256,
            "table_count": len(row_counts),
            "table_counts": row_counts,
            "table_digests": digests,
            "row_format": SOURCE_STAGE_FORMAT,
        }
    except SourceStageError:
        if connection is not None:
            connection.rollback()
        raise
    except (psycopg2.Error, OSError, sqlite3.Error, ValueError, TypeError) as exc:
        if connection is not None:
            connection.rollback()
        raise SourceStageError("Lossless SQLite source staging failed") from exc
    finally:
        if connection is not None:
            connection.close()
        try:
            source.rollback()
        except sqlite3.Error:
            pass
        source.close()
