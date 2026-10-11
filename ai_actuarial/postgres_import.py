"""Explicit, read-only, bounded-memory import of a validated SQLite v16 database."""

from __future__ import annotations

import hashlib
import itertools
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterator

from ai_actuarial.postgres import (
    POSTGRES_SCHEMA_VERSION,
    DatabaseConfig,
    PostgresConnection,
    initialize_postgresql_schema,
)
from ai_actuarial.sqlite_schema import (
    _OPTIONAL_TABLE_ALLOWED_COLUMNS,
    CURRENT_SQLITE_SCHEMA_VERSION,
    _analyze_connection,
    _current_storage_signature,
)

_IMPORT_BATCH_SIZE = 500


class SQLiteImportError(RuntimeError):
    """The explicit SQLite source cannot be safely imported."""


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _source_snapshot(
    path: Path,
) -> tuple[
    sqlite3.Connection,
    dict[str, tuple[list[str], list[str], set[str]]],
    dict[str, int],
    str,
]:
    if not path.is_file():
        raise SQLiteImportError("SQLite import source does not exist")
    wal_path = Path(str(path) + "-wal")
    if wal_path.exists() and wal_path.stat().st_size:
        raise SQLiteImportError("SQLite import source must be a checkpointed single-file snapshot")

    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    try:
        source = sqlite3.connect(uri, uri=True, isolation_level=None)
    except sqlite3.Error as exc:
        raise SQLiteImportError("SQLite import source is not a valid v16 database") from exc
    try:
        source.execute("PRAGMA query_only=ON")
        source.execute("BEGIN")
        status = _analyze_connection(source)
        database_status = status.get("database") if isinstance(status.get("database"), dict) else {}
        if (
            status.get("state") != "current"
            or int(database_status.get("user_version") or 0) != CURRENT_SQLITE_SCHEMA_VERSION
        ):
            raise SQLiteImportError("SQLite import source must pass schema checks as version 16")

        required_tables = set(_current_storage_signature())
        actual_tables = {
            str(row[0])
            for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        optional_tables = set(_OPTIONAL_TABLE_ALLOWED_COLUMNS)
        if not required_tables.issubset(actual_tables) or not actual_tables.issubset(
            required_tables | optional_tables
        ):
            raise SQLiteImportError("SQLite v16 source contains an unexpected table set")

        table_metadata: dict[str, tuple[list[str], list[str], set[str]]] = {}
        row_counts: dict[str, int] = {}
        for table in sorted(actual_tables):
            info = source.execute(f"PRAGMA table_info({_quote_identifier(table)})").fetchall()
            columns = [str(row[1]) for row in info]
            primary_key = [
                str(row[1]) for row in sorted(info, key=lambda row: int(row[5])) if row[5]
            ]
            if not primary_key:
                raise SQLiteImportError("SQLite v16 source table is missing a stable primary key")
            text_key_columns = {
                str(row[1])
                for row in info
                if row[5]
                and any(token in str(row[2] or "").upper() for token in ("CHAR", "CLOB", "TEXT"))
            }
            table_metadata[table] = (columns, primary_key, text_key_columns)
            row_counts[table] = int(
                source.execute(f"SELECT COUNT(*) FROM {_quote_identifier(table)}").fetchone()[0]
            )

        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise SQLiteImportError("SQLite import source changed while it was being read")
        return source, table_metadata, row_counts, digest.hexdigest()
    except sqlite3.Error as exc:
        try:
            source.rollback()
        except sqlite3.Error:
            pass
        finally:
            source.close()
        raise SQLiteImportError("SQLite import source is not a valid v16 database") from exc
    except Exception:
        try:
            source.rollback()
        finally:
            source.close()
        raise


def _import_order(source: sqlite3.Connection, tables: set[str]) -> list[str]:
    dependencies: dict[str, set[str]] = {}
    for table in tables:
        parents = {
            str(row[2])
            for row in source.execute(f"PRAGMA foreign_key_list({_quote_identifier(table)})")
            if str(row[2]) in tables and str(row[2]) != table
        }
        dependencies[table] = parents

    order: list[str] = []
    while dependencies:
        ready = sorted(table for table, parents in dependencies.items() if not parents)
        if not ready:
            raise SQLiteImportError("SQLite v16 table references contain a cycle")
        order.extend(ready)
        for table in ready:
            dependencies.pop(table)
        for parents in dependencies.values():
            parents.difference_update(ready)
    return order


def _stable_row(value: tuple[Any, ...]) -> str:
    normalized = [
        bytes(item).hex() if isinstance(item, (bytes, bytearray, memoryview)) else item
        for item in value
    ]
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), default=repr)


def _select_rows(
    table: str,
    columns: list[str],
    primary_key: list[str],
    *,
    postgresql: bool = False,
    text_key_columns: set[str] | None = None,
) -> str:
    names = ", ".join(_quote_identifier(column) for column in columns)
    text_keys = text_key_columns or set()
    order_columns = [
        (
            f'{_quote_identifier(column)} COLLATE "C"'
            if postgresql and column in text_keys
            else _quote_identifier(column)
        )
        for column in primary_key
    ]
    order = ", ".join(order_columns)
    return f"SELECT {names} FROM {_quote_identifier(table)} ORDER BY {order}"


def _sqlite_batches(source: sqlite3.Connection, statement: str) -> Iterator[list[tuple[Any, ...]]]:
    cursor = source.execute(statement)
    while batch := cursor.fetchmany(_IMPORT_BATCH_SIZE):
        yield [tuple(row) for row in batch]


def _verify_table_contents(
    source: sqlite3.Connection,
    pg: PostgresConnection,
    table: str,
    columns: list[str],
    primary_key: list[str],
    text_key_columns: set[str],
) -> None:
    source_batches = _sqlite_batches(source, _select_rows(table, columns, primary_key))
    target_statement = _select_rows(
        table,
        columns,
        primary_key,
        postgresql=True,
        text_key_columns=text_key_columns,
    )
    target_batches = pg.iter_batches(target_statement, batch_size=_IMPORT_BATCH_SIZE)
    missing = object()
    for source_batch, target_batch in itertools.zip_longest(
        source_batches, target_batches, fillvalue=missing
    ):
        if source_batch is missing or target_batch is missing:
            raise SQLiteImportError("Imported content does not match the SQLite snapshot")
        if len(source_batch) != len(target_batch) or any(
            _stable_row(source_row) != _stable_row(tuple(target_row))
            for source_row, target_row in zip(source_batch, target_batch)
        ):
            raise SQLiteImportError("Imported content does not match the SQLite snapshot")


def import_sqlite_v16(
    source_path: str | Path,
    database: DatabaseConfig | str,
) -> dict[str, Any]:
    """Import one validated SQLite v16 snapshot into an empty PostgreSQL schema."""
    path = Path(source_path).expanduser().resolve()
    initialize_postgresql_schema(database)
    source, table_metadata, row_counts, source_sha256 = _source_snapshot(path)
    pg = PostgresConnection(database, autocommit=False)
    try:
        migration_version = pg.execute(
            "SELECT COALESCE(MAX(version), 0) FROM ai_actuarial_schema_migrations"
        ).fetchone()[0]
        if int(migration_version) != POSTGRES_SCHEMA_VERSION:
            raise SQLiteImportError("PostgreSQL schema version is not ready for SQLite v16 import")

        tables = set(table_metadata)
        business_tables = set(_current_storage_signature()) | set(_OPTIONAL_TABLE_ALLOWED_COLUMNS)
        for table in sorted(business_tables):
            if not pg.table_exists(table):
                raise SQLiteImportError(
                    "PostgreSQL target is missing a required v16 business table"
                )
            pg.execute(f"LOCK TABLE {_quote_identifier(table)} IN ACCESS EXCLUSIVE MODE")

        previous = pg.execute(
            "SELECT source_schema_version, row_counts_json FROM ai_actuarial_sqlite_imports "
            "WHERE source_sha256 = ?",
            (source_sha256,),
        ).fetchone()
        counts_json = json.dumps(row_counts, sort_keys=True, separators=(",", ":"))
        if previous is not None:
            if int(previous[0]) != CURRENT_SQLITE_SCHEMA_VERSION or previous[1] != counts_json:
                raise SQLiteImportError(
                    "Existing SQLite import provenance conflicts with this source"
                )
            pg.commit()
            return {
                "source_sha256": source_sha256,
                "source_schema_version": CURRENT_SQLITE_SCHEMA_VERSION,
                "row_counts": row_counts,
                "already_imported": True,
            }

        existing_source = pg.execute("SELECT 1 FROM ai_actuarial_sqlite_imports LIMIT 1").fetchone()
        if existing_source is not None:
            raise SQLiteImportError(
                "PostgreSQL schema already has SQLite import provenance for another source"
            )

        populated = [
            table
            for table in sorted(business_tables)
            if pg.execute(f"SELECT 1 FROM {_quote_identifier(table)} LIMIT 1").fetchone()
            is not None
        ]
        if populated:
            raise SQLiteImportError(
                "SQLite v16 import requires an empty PostgreSQL business schema"
            )

        for table, (columns, _primary_key, _text_key_columns) in table_metadata.items():
            target_columns = pg.table_columns(table)
            if not set(columns).issubset(target_columns):
                raise SQLiteImportError("PostgreSQL target columns do not cover the v16 source")

        for table in _import_order(source, tables):
            columns, _primary_key, _text_key_columns = table_metadata[table]
            import_columns = list(columns)
            if table == "messages":
                import_columns.append("message_order")
                source_rows = source.execute(
                    "SELECT "
                    + ", ".join(_quote_identifier(column) for column in columns)
                    + ", rowid FROM messages ORDER BY rowid"
                )
            else:
                source_rows = source.execute(_select_rows(table, columns, table_metadata[table][1]))
            names = ", ".join(_quote_identifier(column) for column in import_columns)
            placeholders = ", ".join("?" for _ in import_columns)
            statement = f"INSERT INTO {_quote_identifier(table)} ({names}) VALUES ({placeholders})"
            while batch := source_rows.fetchmany(_IMPORT_BATCH_SIZE):
                pg.executemany(statement, (tuple(row) for row in batch))

        pg.execute("SET CONSTRAINTS ALL IMMEDIATE")
        for table, expected_count in row_counts.items():
            actual_count = int(
                pg.execute(f"SELECT COUNT(*) FROM {_quote_identifier(table)}").fetchone()[0]
            )
            if actual_count != expected_count:
                raise SQLiteImportError("Imported row count does not match the SQLite snapshot")
            columns, primary_key, text_key_columns = table_metadata[table]
            _verify_table_contents(source, pg, table, columns, primary_key, text_key_columns)
            if table == "messages":
                source_order = source.execute(
                    "SELECT message_id, rowid FROM messages ORDER BY rowid"
                )
                target_order = pg.iter_batches(
                    "SELECT message_id, message_order FROM messages ORDER BY message_order",
                    batch_size=_IMPORT_BATCH_SIZE,
                )
                source_batch = source_order.fetchmany(_IMPORT_BATCH_SIZE)
                target_iterator = iter(target_order)
                for target_batch in target_iterator:
                    if len(source_batch) != len(target_batch) or any(
                        str(source_row[0]) != str(target_row[0])
                        or int(source_row[1]) != int(target_row[1])
                        for source_row, target_row in zip(source_batch, target_batch)
                    ):
                        raise SQLiteImportError(
                            "Imported chat history order does not match the SQLite snapshot"
                        )
                    source_batch = source_order.fetchmany(_IMPORT_BATCH_SIZE)
                if source_batch:
                    raise SQLiteImportError(
                        "Imported chat history order does not match the SQLite snapshot"
                    )

        for table in sorted(tables):
            identity_columns = pg.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = ? "
                "AND is_identity = 'YES'",
                (table,),
            ).fetchall()
            for identity in identity_columns:
                column = str(identity[0])
                sequence = pg.execute(
                    "SELECT pg_get_serial_sequence(?, ?)", (table, column)
                ).fetchone()[0]
                if not sequence:
                    raise SQLiteImportError(
                        "PostgreSQL identity sequence is unavailable after import"
                    )
                max_value = pg.execute(
                    f"SELECT MAX({_quote_identifier(column)}) FROM {_quote_identifier(table)}"
                ).fetchone()[0]
                if max_value is None:
                    pg.execute("SELECT setval(?::regclass, 1, false)", (sequence,))
                else:
                    pg.execute("SELECT setval(?::regclass, ?, true)", (sequence, int(max_value)))

        pg.execute(
            "INSERT INTO ai_actuarial_sqlite_imports "
            "(source_sha256, source_schema_version, row_counts_json, source_path) "
            "VALUES (?, ?, ?, ?)",
            (source_sha256, CURRENT_SQLITE_SCHEMA_VERSION, counts_json, str(path)),
        )
        pg.commit()
        return {
            "source_sha256": source_sha256,
            "source_schema_version": CURRENT_SQLITE_SCHEMA_VERSION,
            "row_counts": row_counts,
            "already_imported": False,
        }
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()
        source.rollback()
        source.close()
