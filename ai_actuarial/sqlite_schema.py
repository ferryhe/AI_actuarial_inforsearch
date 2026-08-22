from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable


CURRENT_SQLITE_SCHEMA_VERSION = 1

_CREATE_CURRENT_SCHEMA_ACTION_ID = "create_current_storage_schema_v1"
_BASELINE_ACTION_ID = "baseline_storage_schema_v1"
_PARTIAL_MIGRATION_TABLES = frozenset(
    {
        "agentic_ready_publications_attempts_new",
    }
)

# Legacy databases predating the explicit schema runner can be missing a small,
# well-understood set of ready-data tables and columns. These tables have no
# historical rows in production and are re-created idempotently by
# Storage._init_schema(), so a version-0 legacy database missing exactly these
# objects is safe to auto-backfill via `schema apply` rather than fail-closed.
_AUTO_BACKFILL_TABLES = frozenset(
    {
        "agentic_ready_automation",
        "agentic_ready_automation_lock",
        "agentic_ready_publication_gc",
        "agentic_ready_publications",
        "agentic_ready_slots",
        "agentic_ready_source_state",
        "kb_ready_index_state",
    }
)

_AUTO_BACKFILL_COLUMNS: dict[str, frozenset[str]] = {
    "agentic_ready_manifests": frozenset(
        {
            "artifact_digest",
            "index_version_id",
            "publication_id",
            "source_version_id",
            "source_version_kind",
        }
    ),
}

# Columns whose NOT NULL flag may legitimately differ from the canonical
# current schema. SQLite cannot ALTER a column's NOT NULL constraint without a
# table rebuild, and these differences are runtime-harmless (each column has a
# DEFAULT and is always written by application code). Comparing column
# signatures for these columns ignores the NOT NULL bit only.
_NOTNULL_TOLERANCE_COLUMNS: dict[str, frozenset[str]] = {
    "api_tokens": frozenset({"instance_id", "is_default"}),
    "rag_knowledge_bases": frozenset({"embedding_provider"}),
}

ColumnSignature = tuple[str, str, int, str | None, int, int]
IndexColumnSignature = tuple[int, int, str | None, int, str, int]
IndexSignature = tuple[int, str, int, tuple[IndexColumnSignature, ...]]
ForeignKeySignature = tuple[int, int, str, str, str, str, str, str]
SchemaObject = tuple[str, str, str]


@dataclass(frozen=True)
class TableSignature:
    columns: tuple[ColumnSignature, ...]
    indexes: tuple[IndexSignature, ...]
    foreign_keys: tuple[ForeignKeySignature, ...]


SchemaSourceValidator = Callable[[sqlite3.Connection, dict[str, TableSignature]], bool]


_OPTIONAL_TABLE_ALLOWED_COLUMNS: dict[str, frozenset[str]] = {
    "rag_knowledge_bases": frozenset(
        {
            "kb_id",
            "name",
            "description",
            "kb_mode",
            "chunk_profile_id",
            "manifest_profile",
            "embedding_provider",
            "embedding_model",
            "embedding_dimension",
            "chunk_size",
            "chunk_overlap",
            "index_type",
            "created_at",
            "updated_at",
            "file_count",
            "chunk_count",
            "index_dirty_at",
            "index_path",
            "metadata_path",
        }
    ),
    "rag_kb_files": frozenset(
        {"kb_id", "file_url", "added_at", "chunk_count", "indexed_at"}
    ),
    "rag_chunks": frozenset(
        {
            "chunk_id",
            "kb_id",
            "file_url",
            "chunk_index",
            "content",
            "token_count",
            "section_hierarchy",
            "embedding_hash",
            "created_at",
        }
    ),
    "rag_kb_category_mappings": frozenset(
        {"kb_id", "category", "auto_sync", "created_at"}
    ),
    "conversations": frozenset(
        {
            "conversation_id",
            "user_id",
            "title",
            "kb_id",
            "mode",
            "created_at",
            "updated_at",
            "message_count",
            "metadata",
        }
    ),
    "messages": frozenset(
        {
            "message_id",
            "conversation_id",
            "role",
            "content",
            "citations",
            "created_at",
            "token_count",
            "metadata",
        }
    ),
}

_OPTIONAL_TABLE_REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    "rag_knowledge_bases": frozenset(
        {
            "kb_id",
            "name",
            "description",
            "kb_mode",
            "chunk_profile_id",
            "manifest_profile",
            "embedding_provider",
            "embedding_model",
            "embedding_dimension",
            "chunk_size",
            "chunk_overlap",
            "index_type",
            "created_at",
            "updated_at",
            "file_count",
            "chunk_count",
            "index_dirty_at",
        }
    ),
    "rag_kb_files": _OPTIONAL_TABLE_ALLOWED_COLUMNS["rag_kb_files"],
    "rag_chunks": _OPTIONAL_TABLE_ALLOWED_COLUMNS["rag_chunks"],
    "rag_kb_category_mappings": _OPTIONAL_TABLE_ALLOWED_COLUMNS[
        "rag_kb_category_mappings"
    ],
    "conversations": _OPTIONAL_TABLE_ALLOWED_COLUMNS["conversations"],
    "messages": _OPTIONAL_TABLE_ALLOWED_COLUMNS["messages"],
}

_CORE_TABLE_ALLOWED_EXTRA_COLUMNS: dict[str, frozenset[str]] = {
    "catalog_items": frozenset(
        {
            "title",
            "source_site",
            "original_filename",
            "local_path",
            "keywords_json",
        }
    ),
}

_CORE_TABLE_ALLOWED_EXTRA_COLUMN_SIGNATURES: dict[str, dict[str, frozenset[ColumnSignature]]] = {
    "catalog_items": {
        name: frozenset({(name, "TEXT", 0, None, 0, 0)})
        for name in _CORE_TABLE_ALLOWED_EXTRA_COLUMNS["catalog_items"]
    }
}


class SchemaMigrationError(RuntimeError):
    """Raised when a SQLite schema action must fail closed."""


@dataclass(frozen=True)
class SQLiteSchemaMigration:
    version: int
    migration_id: str
    apply: Callable[[sqlite3.Connection], None]
    source_validator: SchemaSourceValidator | None = None


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _user_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _set_user_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version={int(version)}")


def _init_schema_on_connection(conn: sqlite3.Connection, db_path: str = "") -> None:
    from ai_actuarial.storage import Storage

    storage = Storage.__new__(Storage)
    storage.db_path = db_path
    storage._conn = conn
    storage._tx_depth = 0
    storage._agentic_ready_publication_columns_cache = None
    storage._defer_schema_commits = True
    storage._init_schema()


def _baseline_storage_schema_v1(conn: sqlite3.Connection) -> None:
    _init_schema_on_connection(conn)
    _set_user_version(conn, 1)


SQLITE_SCHEMA_MIGRATIONS: tuple[SQLiteSchemaMigration, ...] = (
    SQLiteSchemaMigration(
        version=1,
        migration_id=_BASELINE_ACTION_ID,
        apply=_baseline_storage_schema_v1,
    ),
)


def _normalize_sqlite_type(value: Any) -> str:
    return " ".join(str(value or "").upper().split())


def _normalize_sqlite_default(value: Any) -> str | None:
    if value is None:
        return None
    return " ".join(str(value).split())


def _index_columns(
    conn: sqlite3.Connection,
    index_name: str,
) -> tuple[IndexColumnSignature, ...]:
    rows = conn.execute(
        f"PRAGMA index_xinfo({_quote_identifier(index_name)})"
    ).fetchall()
    return tuple(
        (
            int(row[0]),
            int(row[1]),
            str(row[2]) if row[2] is not None else None,
            int(row[3]),
            str(row[4] or ""),
            int(row[5]),
        )
        for row in rows
    )


def _table_signature(conn: sqlite3.Connection, table: str) -> TableSignature:
    columns = tuple(
        (
            str(row[1]),
            _normalize_sqlite_type(row[2]),
            int(row[3]),
            _normalize_sqlite_default(row[4]),
            int(row[5]),
            int(row[6]),
        )
        for row in conn.execute(
            f"PRAGMA table_xinfo({_quote_identifier(table)})"
        ).fetchall()
    )
    indexes = tuple(
        sorted(
            (
                int(row[2]),
                str(row[3] or ""),
                int(row[4]),
                _index_columns(conn, str(row[1])),
            )
            for row in conn.execute(
                f"PRAGMA index_list({_quote_identifier(table)})"
            ).fetchall()
        )
    )
    foreign_keys = tuple(
        sorted(
            (
                int(row[0]),
                int(row[1]),
                str(row[2] or ""),
                str(row[3] or ""),
                str(row[4] or ""),
                str(row[5] or ""),
                str(row[6] or ""),
                str(row[7] or ""),
            )
            for row in conn.execute(
                f"PRAGMA foreign_key_list({_quote_identifier(table)})"
            ).fetchall()
        )
    )
    return TableSignature(
        columns=columns,
        indexes=indexes,
        foreign_keys=foreign_keys,
    )


def _schema_signature(conn: sqlite3.Connection) -> dict[str, TableSignature]:
    rows = conn.execute(
        "SELECT name FROM sqlite_schema WHERE type = 'table' ORDER BY name"
    ).fetchall()
    tables: dict[str, TableSignature] = {}
    for (name,) in rows:
        table = str(name)
        if table.startswith("sqlite_"):
            continue
        tables[table] = _table_signature(conn, table)
    return tables


def _user_schema_objects(conn: sqlite3.Connection) -> tuple[SchemaObject, ...]:
    rows = conn.execute(
        """
        SELECT type, name, tbl_name
        FROM sqlite_schema
        WHERE name NOT LIKE 'sqlite_%'
        ORDER BY type, name, tbl_name
        """
    ).fetchall()
    return tuple(
        (
            str(row[0] or ""),
            str(row[1] or ""),
            str(row[2] or ""),
        )
        for row in rows
    )


def has_user_schema_objects(conn: sqlite3.Connection) -> bool:
    return bool(_user_schema_objects(conn))


def _captured_index_names(
    conn: sqlite3.Connection,
    tables: dict[str, TableSignature],
) -> frozenset[str]:
    names: set[str] = set()
    for table in tables:
        rows = conn.execute(
            f"PRAGMA index_list({_quote_identifier(table)})"
        ).fetchall()
        names.update(str(row[1]) for row in rows)
    return frozenset(names)


def _unexpected_schema_object_counts(
    conn: sqlite3.Connection,
    tables: dict[str, TableSignature],
) -> dict[str, int]:
    captured_indexes = _captured_index_names(conn, tables)
    counts: dict[str, int] = {}
    for object_type, name, _table_name in _user_schema_objects(conn):
        if object_type == "table":
            continue
        if object_type == "index" and name in captured_indexes:
            continue
        category = object_type if object_type in {"index", "view", "trigger"} else "other"
        counts[category] = counts.get(category, 0) + 1
    return dict(sorted(counts.items()))


@lru_cache(maxsize=1)
def _current_storage_signature() -> dict[str, TableSignature]:
    from ai_actuarial.storage import Storage

    storage = Storage(":memory:")
    try:
        return _schema_signature(storage._conn)
    finally:
        storage.close()


def _execute_statements(
    conn: sqlite3.Connection,
    statements: tuple[str, ...],
) -> None:
    for statement in statements:
        conn.execute(statement)


@lru_cache(maxsize=1)
def _optional_table_signature_variants() -> dict[str, frozenset[TableSignature]]:
    variants: dict[str, set[TableSignature]] = {
        table: set() for table in _OPTIONAL_TABLE_ALLOWED_COLUMNS
    }
    optional_schema_variants: tuple[tuple[str, ...], ...] = (
        (
            """
            CREATE TABLE rag_knowledge_bases (
                kb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                kb_mode TEXT DEFAULT 'category',
                chunk_profile_id TEXT,
                manifest_profile TEXT DEFAULT 'general',
                embedding_provider TEXT DEFAULT 'openai',
                embedding_model TEXT NOT NULL,
                embedding_dimension INTEGER,
                chunk_size INTEGER NOT NULL,
                chunk_overlap INTEGER NOT NULL,
                index_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                file_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                index_dirty_at TEXT,
                index_path TEXT,
                metadata_path TEXT
            )
            """,
            """
            CREATE TABLE rag_kb_files (
                kb_id TEXT NOT NULL,
                file_url TEXT NOT NULL,
                added_at TEXT NOT NULL,
                chunk_count INTEGER DEFAULT 0,
                indexed_at TEXT,
                PRIMARY KEY (kb_id, file_url),
                FOREIGN KEY (kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE,
                FOREIGN KEY (file_url) REFERENCES files(url) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE rag_chunks (
                chunk_id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                file_url TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                token_count INTEGER NOT NULL,
                section_hierarchy TEXT,
                embedding_hash TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE,
                FOREIGN KEY (file_url) REFERENCES files(url) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX idx_rag_kb_files_kb_id ON rag_kb_files(kb_id)",
            "CREATE INDEX idx_rag_chunks_kb_file ON rag_chunks(kb_id, file_url)",
        ),
        (
            """
            CREATE TABLE rag_knowledge_bases (
                kb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                kb_mode TEXT DEFAULT 'category',
                chunk_profile_id TEXT,
                manifest_profile TEXT DEFAULT 'general',
                embedding_provider TEXT DEFAULT 'openai',
                embedding_model TEXT NOT NULL,
                embedding_dimension INTEGER,
                chunk_size INTEGER NOT NULL,
                chunk_overlap INTEGER NOT NULL,
                index_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                file_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                index_dirty_at TEXT
            )
            """,
            """
            CREATE TABLE rag_kb_files (
                kb_id TEXT NOT NULL,
                file_url TEXT NOT NULL,
                added_at TEXT NOT NULL,
                chunk_count INTEGER DEFAULT 0,
                indexed_at TEXT,
                PRIMARY KEY (kb_id, file_url),
                FOREIGN KEY (kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE,
                FOREIGN KEY (file_url) REFERENCES files(url) ON DELETE CASCADE
            )
            """,
        ),
        (
            """
            CREATE TABLE rag_kb_category_mappings (
                kb_id TEXT NOT NULL,
                category TEXT NOT NULL,
                auto_sync INTEGER DEFAULT 1,
                created_at TEXT,
                PRIMARY KEY (kb_id, category),
                FOREIGN KEY (kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX idx_rag_kb_category_kb ON rag_kb_category_mappings(kb_id)",
            "CREATE INDEX idx_rag_kb_category_cat ON rag_kb_category_mappings(category)",
        ),
        (
            """
            CREATE TABLE conversations (
                conversation_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT,
                kb_id TEXT,
                mode TEXT DEFAULT 'expert',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                message_count INTEGER DEFAULT 0,
                metadata TEXT
            )
            """,
            """
            CREATE TABLE messages (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                citations TEXT,
                created_at TEXT NOT NULL,
                token_count INTEGER,
                metadata TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
            )
            """,
            "CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at)",
            "CREATE INDEX idx_conversations_user ON conversations(user_id, updated_at DESC)",
        ),
        (
            """
            CREATE TABLE conversations (
                conversation_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT,
                kb_id TEXT,
                mode TEXT DEFAULT 'expert',
                created_at TEXT,
                updated_at TEXT
            )
            """,
            """
            CREATE TABLE messages (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                citations TEXT,
                metadata TEXT,
                created_at TEXT,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(conversation_id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX idx_messages_conversation ON messages(conversation_id)",
        ),
    )
    for statements in optional_schema_variants:
        with sqlite3.connect(":memory:") as conn:
            _execute_statements(conn, statements)
            signature = _schema_signature(conn)
        for table, table_signature in signature.items():
            if table in variants:
                variants[table].add(table_signature)
    return {table: frozenset(signatures) for table, signatures in variants.items()}


@lru_cache(maxsize=1)
def _optional_column_signature_variants() -> dict[str, dict[str, frozenset[ColumnSignature]]]:
    table_variants = _optional_table_signature_variants()
    column_variants: dict[str, dict[str, set[ColumnSignature]]] = {}
    for table, signatures in table_variants.items():
        per_table: dict[str, set[ColumnSignature]] = {}
        for signature in signatures:
            for column in signature.columns:
                per_table.setdefault(column[0], set()).add(column)
        column_variants[table] = per_table
    return {
        table: {
            column: frozenset(signatures)
            for column, signatures in per_table.items()
        }
        for table, per_table in column_variants.items()
    }


def _column_names(signature: TableSignature) -> frozenset[str]:
    return frozenset(column[0] for column in signature.columns)


def _add_problem(problems: list[str], code: str) -> None:
    if code not in problems:
        problems.append(code)


def _count_columns(groups: dict[str, list[str]]) -> int:
    return sum(len(columns) for columns in groups.values())


def _column_signature_equivalent(
    actual: ColumnSignature,
    expected: ColumnSignature,
    table: str,
    name: str,
) -> bool:
    if actual == expected:
        return True
    if name in _NOTNULL_TOLERANCE_COLUMNS.get(table, frozenset()):
        # Ignore the NOT NULL bit (index 2); see _NOTNULL_TOLERANCE_COLUMNS.
        return actual[:2] == expected[:2] and actual[3:] == expected[3:]
    return False


def _indexes_equivalent(
    left: tuple[IndexSignature, ...],
    right: tuple[IndexSignature, ...],
) -> bool:
    def normalize(
        indexes: tuple[IndexSignature, ...],
    ) -> frozenset[tuple[int, str, int, tuple[tuple[int, str | None, int, str, int], ...]]]:
        normalized: set[tuple[int, str, int, tuple[tuple[int, str | None, int, str, int], ...]]] = set()
        for unique, origin, partial, columns in indexes:
            norm_columns = tuple(
                (seqno, name, desc, coll, key)
                for seqno, _cid, name, desc, coll, key in columns
            )
            normalized.add((unique, origin, partial, norm_columns))
        return frozenset(normalized)

    return normalize(left) == normalize(right)


def _table_signature_equivalent_ignoring_notnull(
    actual: TableSignature,
    expected: TableSignature,
    table: str,
) -> bool:
    tolerance = _NOTNULL_TOLERANCE_COLUMNS.get(table, frozenset())
    if not tolerance or _column_names(actual) != _column_names(expected):
        return False
    actual_by_name = {column[0]: column for column in actual.columns}
    expected_by_name = {column[0]: column for column in expected.columns}
    for name, actual_column in actual_by_name.items():
        expected_column = expected_by_name[name]
        if name in tolerance:
            if actual_column[:2] != expected_column[:2] or actual_column[3:] != expected_column[3:]:
                return False
        elif actual_column != expected_column:
            return False
    if not _indexes_equivalent(actual.indexes, expected.indexes):
        return False
    return actual.foreign_keys == expected.foreign_keys


def _schema_validation(
    tables: dict[str, TableSignature],
    *,
    unexpected_schema_objects: dict[str, int] | None = None,
    tolerate_backfill: bool = False,
) -> tuple[bool, list[str], dict[str, Any]]:
    expected_core = _current_storage_signature()
    optional_table_variants = _optional_table_signature_variants()
    optional_column_variants = _optional_column_signature_variants()
    known_tables = set(expected_core) | set(_OPTIONAL_TABLE_ALLOWED_COLUMNS)
    actual_tables = set(tables)
    problems: list[str] = []
    details: dict[str, Any] = {}

    partial_tables = sorted(actual_tables & set(_PARTIAL_MIGRATION_TABLES))
    if partial_tables:
        _add_problem(problems, "partial_migration_state")
        details["partial_migration_state"] = {"count": len(partial_tables)}

    unexpected_objects = dict(unexpected_schema_objects or {})
    if unexpected_objects:
        _add_problem(problems, "unexpected_schema_objects")
        details["unexpected_schema_objects"] = {
            "total": sum(unexpected_objects.values()),
            "by_type": unexpected_objects,
        }

    unknown_tables = sorted(actual_tables - known_tables - set(_PARTIAL_MIGRATION_TABLES))
    if unknown_tables:
        _add_problem(problems, "unknown_tables")
        details["unknown_tables"] = {"count": len(unknown_tables)}

    missing_core_tables = sorted(set(expected_core) - actual_tables)
    if tolerate_backfill:
        missing_core_tables = sorted(set(missing_core_tables) - _AUTO_BACKFILL_TABLES)
    if missing_core_tables:
        _add_problem(problems, "missing_required_tables")
        details["missing_required_tables"] = {"count": len(missing_core_tables)}

    missing_columns: dict[str, list[str]] = {}
    unexpected_columns: dict[str, list[str]] = {}
    column_signature_mismatch: dict[str, list[str]] = {}
    table_signature_mismatch = 0

    for table, expected_signature in expected_core.items():
        if table not in tables:
            continue
        expected_columns = _column_names(expected_signature)
        actual_columns = _column_names(tables[table])
        allowed_extra_columns = _CORE_TABLE_ALLOWED_EXTRA_COLUMNS.get(
            table,
            frozenset(),
        )
        allowed_extra_signatures = _CORE_TABLE_ALLOWED_EXTRA_COLUMN_SIGNATURES.get(
            table,
            {},
        )
        missing = sorted(expected_columns - actual_columns)
        if tolerate_backfill:
            missing = sorted(set(missing) - _AUTO_BACKFILL_COLUMNS.get(table, frozenset()))
        extra = sorted(actual_columns - expected_columns - allowed_extra_columns)
        if missing:
            missing_columns[table] = missing
        if extra:
            unexpected_columns[table] = extra
        expected_by_name = {column[0]: column for column in expected_signature.columns}
        actual_by_name = {column[0]: column for column in tables[table].columns}
        mismatched_columns = sorted(
            name
            for name, column in expected_by_name.items()
            if name in actual_by_name
            and not _column_signature_equivalent(
                actual_by_name[name],
                column,
                table,
                name,
            )
        )
        mismatched_columns.extend(
            sorted(
                name
                for name in actual_columns & allowed_extra_columns
                if actual_by_name[name] not in allowed_extra_signatures.get(
                    name,
                    frozenset(),
                )
            )
        )
        if mismatched_columns:
            column_signature_mismatch[table] = mismatched_columns
        if (
            mismatched_columns
            or not _indexes_equivalent(tables[table].indexes, expected_signature.indexes)
            or tables[table].foreign_keys != expected_signature.foreign_keys
        ):
            table_signature_mismatch += 1

    for table, allowed_columns in _OPTIONAL_TABLE_ALLOWED_COLUMNS.items():
        if table not in tables:
            continue
        actual_signature = tables[table]
        table_variants = optional_table_variants.get(table, frozenset())
        if actual_signature in table_variants or any(
            _table_signature_equivalent_ignoring_notnull(actual_signature, variant, table)
            for variant in table_variants
        ):
            continue
        required_columns = _OPTIONAL_TABLE_REQUIRED_COLUMNS[table]
        actual_columns = _column_names(actual_signature)
        missing = sorted(required_columns - actual_columns)
        extra = sorted(actual_columns - allowed_columns)
        if missing:
            missing_columns[table] = missing
        if extra:
            unexpected_columns[table] = extra
        actual_by_name = {column[0]: column for column in actual_signature.columns}
        allowed_by_name = optional_column_variants.get(table, {})
        mismatched = sorted(
            name
            for name in actual_columns & allowed_columns
            if not any(
                _column_signature_equivalent(
                    actual_by_name[name],
                    variant,
                    table,
                    name,
                )
                for variant in allowed_by_name.get(name, frozenset())
            )
        )
        if mismatched:
            column_signature_mismatch[table] = mismatched
        if not missing and not extra and not mismatched:
            table_signature_mismatch += 1

    if missing_columns:
        _add_problem(problems, "missing_columns")
        details["missing_columns"] = {
            "tables": len(missing_columns),
            "columns": _count_columns(missing_columns),
        }
    if unexpected_columns:
        _add_problem(problems, "unexpected_columns")
        details["unexpected_columns"] = {
            "tables": len(unexpected_columns),
            "columns": _count_columns(unexpected_columns),
        }
    if column_signature_mismatch:
        _add_problem(problems, "column_signature_mismatch")
        details["column_signature_mismatch"] = {
            "tables": len(column_signature_mismatch),
            "columns": _count_columns(column_signature_mismatch),
        }
    if table_signature_mismatch:
        _add_problem(problems, "schema_signature_mismatch")
        details["schema_signature_mismatch"] = {"tables": table_signature_mismatch}

    return not problems, problems, details


def _base_payload(
    *,
    state: str,
    user_version: int | None,
    schema: str,
    can_apply: bool,
    blocked: bool,
    problems: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "success": True,
        "current_version": CURRENT_SQLITE_SCHEMA_VERSION,
        "state": state,
        "blocked": blocked,
        "can_apply": can_apply,
        "database": {
            "user_version": user_version,
            "schema": schema,
        },
        "problems": list(problems or []),
        "details": dict(details or {}),
    }


def _migration_map() -> dict[int, SQLiteSchemaMigration]:
    versions = [migration.version for migration in SQLITE_SCHEMA_MIGRATIONS]
    if versions != sorted(versions) or len(versions) != len(set(versions)):
        raise SchemaMigrationError("SQLite schema migration registry is not ordered")
    if any(version <= 0 for version in versions):
        raise SchemaMigrationError("SQLite schema migration versions must be positive")
    return {migration.version: migration for migration in SQLITE_SCHEMA_MIGRATIONS}


def _migration_path_from(start_version: int) -> list[SQLiteSchemaMigration] | None:
    migrations = _migration_map()
    path: list[SQLiteSchemaMigration] = []
    for version in range(start_version + 1, CURRENT_SQLITE_SCHEMA_VERSION + 1):
        migration = migrations.get(version)
        if migration is None:
            return None
        path.append(migration)
    return path


def _migration_accepts_source(
    conn: sqlite3.Connection,
    tables: dict[str, TableSignature],
    *,
    start_version: int,
) -> bool:
    path = _migration_path_from(start_version)
    if not path:
        return False
    first_migration = path[0]
    if first_migration.source_validator is None:
        return False
    previous_query_only = int(conn.execute("PRAGMA query_only").fetchone()[0])
    restore_value = "ON" if previous_query_only else "OFF"
    try:
        conn.execute("PRAGMA query_only=ON")
        return bool(first_migration.source_validator(conn, tables))
    except Exception:
        return False
    finally:
        conn.execute(f"PRAGMA query_only={restore_value}")


def _analyze_connection(
    conn: sqlite3.Connection,
    *,
    include_quick_check: bool = True,
) -> dict[str, Any]:
    if include_quick_check:
        quick_rows = [str(row[0]) for row in conn.execute("PRAGMA quick_check")]
        if quick_rows != ["ok"]:
            return _base_payload(
                state="invalid",
                user_version=None,
                schema="unreadable",
                can_apply=False,
                blocked=True,
                problems=["quick_check_failed"],
                details={"quick_check": {"result_count": len(quick_rows)}},
            )

    version = _user_version(conn)
    schema_objects = _user_schema_objects(conn)
    tables = _schema_signature(conn)
    if not schema_objects:
        if version == 0:
            return _base_payload(
                state="empty",
                user_version=0,
                schema="empty",
                can_apply=True,
                blocked=False,
            )
        return _base_payload(
            state="invalid",
            user_version=version,
            schema="empty",
            can_apply=False,
            blocked=True,
            problems=["version_without_schema"],
        )

    if version > CURRENT_SQLITE_SCHEMA_VERSION:
        return _base_payload(
            state="newer_than_code",
            user_version=version,
            schema="not_checked",
            can_apply=False,
            blocked=True,
            problems=["database_newer_than_code"],
        )

    unexpected_schema_objects = _unexpected_schema_object_counts(conn, tables)
    valid, problems, details = _schema_validation(
        tables,
        unexpected_schema_objects=unexpected_schema_objects,
    )
    if not valid:
        if version == 0 and _migration_path_from(0) is not None:
            tolerant_valid, _, _ = _schema_validation(
                tables,
                unexpected_schema_objects=unexpected_schema_objects,
                tolerate_backfill=True,
            )
            if tolerant_valid:
                return _base_payload(
                    state="needs_migration",
                    user_version=version,
                    schema="recognized_legacy_storage_schema_pending_backfill",
                    can_apply=True,
                    blocked=False,
                )
        if 0 < version < CURRENT_SQLITE_SCHEMA_VERSION and _migration_accepts_source(
            conn,
            tables,
            start_version=version,
        ):
            return _base_payload(
                state="needs_migration",
                user_version=version,
                schema="recognized_source_schema_pending_migrations",
                can_apply=True,
                blocked=False,
            )
        return _base_payload(
            state="invalid",
            user_version=version,
            schema="unrecognized",
            can_apply=False,
            blocked=True,
            problems=problems,
            details=details,
        )

    if version == CURRENT_SQLITE_SCHEMA_VERSION:
        return _base_payload(
            state="current",
            user_version=version,
            schema="current_storage_schema_v1",
            can_apply=False,
            blocked=False,
        )
    if version == 0:
        if _migration_path_from(0) is None:
            return _base_payload(
                state="unsupported_old_version",
                user_version=0,
                schema="recognized_but_missing_migration_path",
                can_apply=False,
                blocked=True,
                problems=["missing_migration_path"],
            )
        return _base_payload(
            state="needs_migration",
            user_version=0,
            schema="recognized_storage_schema_v1_with_legacy_version",
            can_apply=True,
            blocked=False,
        )
    if version < CURRENT_SQLITE_SCHEMA_VERSION and _migration_path_from(version):
        return _base_payload(
            state="needs_migration",
            user_version=version,
            schema="recognized_storage_schema_pending_migrations",
            can_apply=True,
            blocked=False,
        )

    return _base_payload(
        state="unsupported_old_version",
        user_version=version,
        schema="recognized_but_unsupported_version",
        can_apply=False,
        blocked=True,
        problems=["missing_migration_path"],
    )


def storage_startup_status(conn: sqlite3.Connection) -> dict[str, Any]:
    return _analyze_connection(conn, include_quick_check=False)


def schema_status(db_path: str | Path) -> dict[str, Any]:
    path = Path(db_path)
    if not path.exists():
        return _base_payload(
            state="missing",
            user_version=None,
            schema="absent",
            can_apply=True,
            blocked=False,
        )
    if path.is_file() and path.stat().st_size == 0:
        return _base_payload(
            state="empty",
            user_version=0,
            schema="empty",
            can_apply=True,
            blocked=False,
        )

    try:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        try:
            return _analyze_connection(conn)
        finally:
            conn.close()
    except sqlite3.Error:
        return _base_payload(
            state="invalid",
            user_version=None,
            schema="unreadable",
            can_apply=False,
            blocked=True,
            problems=["sqlite_unreadable"],
        )


def _plan_actions(status: dict[str, Any]) -> list[dict[str, Any]]:
    state = status["state"]
    if state in {"missing", "empty"}:
        return [
            {
                "id": _CREATE_CURRENT_SCHEMA_ACTION_ID,
                "from_version": 0,
                "to_version": CURRENT_SQLITE_SCHEMA_VERSION,
            }
        ]
    if state == "needs_migration":
        start_version = int((status.get("database") or {}).get("user_version") or 0)
        migrations = _migration_path_from(start_version) or []
        return [
            {
                "id": migration.migration_id,
                "from_version": migration.version - 1,
                "to_version": migration.version,
            }
            for migration in migrations
        ]
    return []


def schema_plan(db_path: str | Path) -> dict[str, Any]:
    status = schema_status(db_path)
    return {
        **status,
        "plan": {
            "actions": _plan_actions(status),
        },
    }


def _initialize_current_schema_on_connection(conn: sqlite3.Connection, path: Path) -> None:
    _init_schema_on_connection(conn, str(path))
    conn.execute(f"PRAGMA user_version={CURRENT_SQLITE_SCHEMA_VERSION}")


def _migration_for_version(version: int) -> SQLiteSchemaMigration:
    migration = _migration_map().get(version)
    if migration is not None:
        return migration
    raise SchemaMigrationError(f"missing SQLite schema migration for version {version}")


def apply_schema(db_path: str | Path) -> dict[str, Any]:
    path = Path(db_path)
    initial = schema_status(path)
    if initial["state"] == "current":
        return {
            **initial,
            "applied_migrations": [],
        }
    if initial["state"] == "newer_than_code":
        raise SchemaMigrationError("database schema version is newer than code")
    if initial["state"] not in {"missing", "empty", "needs_migration"}:
        raise SchemaMigrationError("database schema is not safe to migrate")

    path.parent.mkdir(parents=True, exist_ok=True)
    applied: list[str] = []
    remove_created_file = False
    created_new_file = not path.exists()
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        locked = _analyze_connection(conn)
        if locked["state"] == "current":
            conn.rollback()
            return {
                **locked,
                "applied_migrations": [],
            }
        if locked["state"] == "empty":
            try:
                _initialize_current_schema_on_connection(conn, path)
                final = _analyze_connection(conn)
                if final["state"] != "current":
                    raise SchemaMigrationError(
                        "fresh schema initialization did not reach current version"
                    )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                remove_created_file = created_new_file
                raise SchemaMigrationError("SQLite schema migration failed") from exc
            return {
                **schema_status(path),
                "applied_migrations": [_CREATE_CURRENT_SCHEMA_ACTION_ID],
            }
        if locked["state"] != "needs_migration":
            conn.rollback()
            raise SchemaMigrationError("database schema is not safe to migrate")

        start_version = int(locked["database"]["user_version"])
        try:
            for version in range(start_version + 1, CURRENT_SQLITE_SCHEMA_VERSION + 1):
                migration = _migration_for_version(version)
                migration.apply(conn)
                if _user_version(conn) != version:
                    raise SchemaMigrationError(
                        f"migration {migration.migration_id} did not set user_version"
                    )
                applied.append(migration.migration_id)
            final = _analyze_connection(conn)
            if final["state"] != "current":
                raise SchemaMigrationError("migration finished with a non-current schema")
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise SchemaMigrationError("SQLite schema migration failed") from exc

        return {
            **schema_status(path),
            "applied_migrations": applied,
        }
    finally:
        conn.close()
        if remove_created_file and path.exists():
            try:
                path.unlink()
            except OSError:
                pass


def json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
