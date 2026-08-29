from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from ai_actuarial.storage import Storage


ROOT = Path(__file__).resolve().parents[1]


def _user_version(db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _current_db_at_version_zero(db_path: Path) -> None:
    storage = Storage(str(db_path))
    try:
        storage._conn.execute(
            """
            INSERT INTO files (url, sha256, title, first_seen, last_seen)
            VALUES ('https://example.test/doc.pdf', 'abc123', 'Doc', '2026-08-21T00:00:00Z', '2026-08-21T00:00:00Z')
            """
        )
        storage._conn.execute("PRAGMA user_version=0")
        storage._conn.commit()
    finally:
        storage.close()


def _current_db_at_version_10(
    db_path: Path,
    *,
    snapshot_tables: tuple[str, ...] = (),
) -> None:
    storage = Storage(str(db_path))
    storage.close()
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE weekly_explanations")
        for table in ("weekly_snapshot_members", "weekly_snapshots"):
            if table not in snapshot_tables:
                conn.execute(f"DROP TABLE {table}")
        conn.execute("PRAGMA user_version=10")


def _production_v7_db(db_path: Path) -> None:
    storage = Storage(str(db_path))
    storage.close()
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.executescript(
            """
            ALTER TABLE api_tokens RENAME TO api_tokens_current;
            CREATE TABLE api_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'llm',
                api_key_encrypted TEXT NOT NULL,
                api_base_url TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT,
                updated_at TEXT,
                notes TEXT,
                instance_id TEXT DEFAULT 'default',
                label TEXT,
                is_default INTEGER DEFAULT 1
            );
            DROP TABLE api_tokens_current;
            CREATE UNIQUE INDEX idx_api_tokens_provider_category_instance
                ON api_tokens(provider, category, instance_id);
            CREATE INDEX idx_api_tokens_provider_category_default
                ON api_tokens(provider, category, is_default);

            DROP TABLE IF EXISTS rag_knowledge_bases;
            CREATE TABLE rag_knowledge_bases (
                kb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                kb_mode TEXT DEFAULT 'category',
                embedding_model TEXT NOT NULL,
                chunk_size INTEGER NOT NULL,
                chunk_overlap INTEGER NOT NULL,
                index_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                file_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                index_path TEXT,
                metadata_path TEXT,
                embedding_provider TEXT DEFAULT 'openai',
                embedding_dimension INTEGER,
                chunk_profile_id TEXT,
                index_dirty_at TEXT,
                manifest_profile TEXT DEFAULT 'general'
            );

            DROP TABLE chunk_embeddings;
            DROP TABLE kb_index_items;
            DROP TABLE kb_ready_index_state;
            DROP TABLE kb_index_versions;
            DROP TABLE file_chunk_sets;

            CREATE TABLE file_chunk_sets (
                chunk_set_id TEXT PRIMARY KEY,
                file_url TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                markdown_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ready',
                chunk_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(file_url, profile_id, markdown_hash),
                FOREIGN KEY(file_url) REFERENCES files(url) ON DELETE CASCADE,
                FOREIGN KEY(profile_id) REFERENCES chunk_profiles(profile_id) ON DELETE CASCADE
            );
            CREATE INDEX idx_file_chunk_sets_file_url ON file_chunk_sets(file_url);
            CREATE INDEX idx_file_chunk_sets_profile_id ON file_chunk_sets(profile_id);
            CREATE TABLE chunk_embeddings (
                chunk_id TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                dim INTEGER NOT NULL DEFAULT 0,
                vector_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (chunk_id, embedding_model),
                FOREIGN KEY(chunk_id) REFERENCES global_chunks(chunk_id) ON DELETE CASCADE
            );
            CREATE TABLE kb_index_versions (
                index_version_id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                embedding_provider TEXT NOT NULL DEFAULT 'openai',
                embedding_model TEXT NOT NULL,
                embedding_dimension INTEGER,
                index_type TEXT NOT NULL,
                status TEXT NOT NULL,
                artifact_path TEXT,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                built_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX idx_kb_index_versions_kb_id ON kb_index_versions(kb_id);
            CREATE TABLE kb_ready_index_state (
                kb_id TEXT PRIMARY KEY,
                index_version_id TEXT NOT NULL,
                embedding_provider TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                embedding_dimension INTEGER,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE
            );
            CREATE TABLE kb_index_items (
                index_version_id TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                PRIMARY KEY (index_version_id, chunk_id),
                FOREIGN KEY(index_version_id) REFERENCES kb_index_versions(index_version_id) ON DELETE CASCADE,
                FOREIGN KEY(chunk_id) REFERENCES global_chunks(chunk_id) ON DELETE CASCADE
            );
            ALTER TABLE catalog_items ADD COLUMN title TEXT;
            ALTER TABLE catalog_items ADD COLUMN source_site TEXT;
            ALTER TABLE catalog_items ADD COLUMN original_filename TEXT;
            ALTER TABLE catalog_items ADD COLUMN local_path TEXT;
            ALTER TABLE catalog_items ADD COLUMN keywords_json TEXT;
            INSERT INTO files (url, sha256, title, first_seen, last_seen)
            VALUES ('https://example.test/v7.pdf', 'v7-sha', 'V7', '2026-08-27', '2026-08-27');
            PRAGMA user_version=7;
            """
        )


def _files_count(db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM files").fetchone()[0])


def _schema_rows(db_path: Path) -> list[tuple[str, str, str, str | None]]:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            """
            SELECT type, name, tbl_name, sql
            FROM sqlite_master
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()


def _db_file_state(db_path: Path) -> tuple[tuple[bool, int, str], ...]:
    def file_state(candidate: Path) -> tuple[bool, int, str]:
        if not candidate.exists():
            return False, 0, ""
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        return True, candidate.stat().st_size, digest

    return tuple(
        file_state(candidate)
        for candidate in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm"))
    )


def _api_token_label(db_path: Path) -> str | None:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT label FROM api_tokens LIMIT 1").fetchone()
    return row[0] if row else None


def _run_schema_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "ai_actuarial.cli", "schema", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_fresh_storage_initializes_current_schema_version(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import CURRENT_SQLITE_SCHEMA_VERSION, schema_status

    db_path = tmp_path / "fresh.db"
    storage = Storage(str(db_path))
    storage.close()

    assert _user_version(db_path) == CURRENT_SQLITE_SCHEMA_VERSION
    status = schema_status(db_path)
    assert status["state"] == "current"
    assert status["database"]["user_version"] == CURRENT_SQLITE_SCHEMA_VERSION


def test_storage_open_current_schema_does_not_run_backfills(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import schema_status

    db_path = tmp_path / "current-noop.db"
    storage = Storage(str(db_path))
    try:
        storage._conn.execute(
            """
            INSERT INTO api_tokens (provider, category, api_key_encrypted, label)
            VALUES ('openai', 'llm', 'encrypted-placeholder', NULL)
            """
        )
        storage._conn.commit()
    finally:
        storage.close()

    assert schema_status(db_path)["state"] == "current"
    assert _api_token_label(db_path) is None
    before_schema = _schema_rows(db_path)
    before_state = _db_file_state(db_path)

    reopened = Storage(str(db_path))
    reopened.close()

    assert schema_status(db_path)["state"] == "current"
    assert _api_token_label(db_path) is None
    assert _schema_rows(db_path) == before_schema
    assert _db_file_state(db_path) == before_state


@pytest.mark.parametrize(
    "failing_probe",
    ("has_user_schema_objects", "storage_startup_status"),
)
def test_storage_closes_connection_when_startup_probe_raises_sqlite_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failing_probe: str,
) -> None:
    import ai_actuarial.storage as storage_module

    real_connect = sqlite3.connect
    connections = []

    class TrackingConnection:
        def __init__(self, conn) -> None:
            self._conn = conn
            self.closed = False

        def execute(self, *args, **kwargs):
            return self._conn.execute(*args, **kwargs)

        def close(self) -> None:
            self.closed = True
            self._conn.close()

        def __getattr__(self, name: str):
            return getattr(self._conn, name)

    def tracking_connect(*args, **kwargs):
        conn = TrackingConnection(real_connect(*args, **kwargs))
        connections.append(conn)
        return conn

    def raise_sqlite_error(_conn) -> bool:
        raise sqlite3.DatabaseError("injected startup probe failure")

    monkeypatch.setattr(storage_module.sqlite3, "connect", tracking_connect)
    if failing_probe == "has_user_schema_objects":
        monkeypatch.setattr(storage_module, "has_user_schema_objects", raise_sqlite_error)
    else:
        monkeypatch.setattr(storage_module, "has_user_schema_objects", lambda _conn: True)
        monkeypatch.setattr(storage_module, "storage_startup_status", raise_sqlite_error)

    with pytest.raises(sqlite3.DatabaseError, match="injected startup probe failure"):
        Storage(str(tmp_path / "probe-failure.db"))

    assert connections
    assert connections[-1].closed is True


def test_storage_startup_status_skips_quick_check_but_schema_status_keeps_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_actuarial.sqlite_schema as sqlite_schema

    db_path = tmp_path / "startup-no-quick-check.db"
    storage = Storage(str(db_path))
    storage.close()

    analyze_calls: list[bool] = []
    real_analyze = sqlite_schema._analyze_connection

    def recording_analyze(
        conn: sqlite3.Connection,
        *,
        include_quick_check: bool = True,
    ) -> dict[str, object]:
        analyze_calls.append(include_quick_check)
        return real_analyze(conn, include_quick_check=include_quick_check)

    monkeypatch.setattr(sqlite_schema, "_analyze_connection", recording_analyze)

    with sqlite3.connect(db_path) as conn:
        startup_status = sqlite_schema.storage_startup_status(conn)

    assert startup_status["state"] == "current"
    assert analyze_calls == [False]

    analyze_calls.clear()
    explicit_status = sqlite_schema.schema_status(db_path)

    assert explicit_status["state"] == "current"
    assert analyze_calls == [True]


def test_storage_rejects_non_empty_version_zero_without_mutating(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import schema_status

    db_path = tmp_path / "legacy-zero-storage.db"
    storage = Storage(str(db_path))
    try:
        storage._conn.execute(
            """
            INSERT INTO api_tokens (provider, category, api_key_encrypted, label)
            VALUES ('openai', 'llm', 'encrypted-placeholder', NULL)
            """
        )
        storage._conn.execute("PRAGMA user_version=0")
        storage._conn.commit()
    finally:
        storage.close()

    before_schema = _schema_rows(db_path)
    assert _api_token_label(db_path) is None

    with pytest.raises(RuntimeError, match="schema apply"):
        Storage(str(db_path))

    assert _user_version(db_path) == 0
    assert _schema_rows(db_path) == before_schema
    assert _api_token_label(db_path) is None
    assert schema_status(db_path)["state"] == "needs_migration"


def test_storage_rejects_malformed_current_without_mutating(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import CURRENT_SQLITE_SCHEMA_VERSION, schema_status

    db_path = tmp_path / "malformed-current-storage.db"
    storage = Storage(str(db_path))
    try:
        storage._conn.execute(
            """
            INSERT INTO api_tokens (provider, category, api_key_encrypted, label)
            VALUES ('openai', 'llm', 'encrypted-placeholder', NULL)
            """
        )
        storage._conn.commit()
    finally:
        storage.close()
    with sqlite3.connect(db_path) as conn:
        conn.execute("ALTER TABLE files ADD COLUMN hidden_startup_marker TEXT")
        conn.execute(f"PRAGMA user_version={CURRENT_SQLITE_SCHEMA_VERSION}")

    before_schema = _schema_rows(db_path)
    assert _api_token_label(db_path) is None

    with pytest.raises(RuntimeError, match="schema preflight"):
        Storage(str(db_path))

    assert _user_version(db_path) == CURRENT_SQLITE_SCHEMA_VERSION
    assert _schema_rows(db_path) == before_schema
    assert _api_token_label(db_path) is None
    assert schema_status(db_path)["state"] == "invalid"


def test_status_plan_apply_version_zero_baseline_preserves_data(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import CURRENT_SQLITE_SCHEMA_VERSION, apply_schema, schema_plan, schema_status

    db_path = tmp_path / "legacy-zero.db"
    _current_db_at_version_zero(db_path)

    status = schema_status(db_path)
    assert status["state"] == "needs_migration"
    assert status["can_apply"] is True
    assert _user_version(db_path) == 0

    plan = schema_plan(db_path)
    assert [action["id"] for action in plan["plan"]["actions"]] == [
        "baseline_storage_schema_v1",
        "add_taxonomy_state_v2",
        "add_taxonomy_categories_v3",
        "add_files_content_kind_v4",
        "add_pipeline_state_v5",
        "add_pipeline_fks_v6",
        "add_pipeline_lease_v7",
        "add_chunk_embedding_identity_v8",
        "add_kb_index_contract_v9",
        "add_agentic_ready_manual_operation_state_v10",
        "add_weekly_snapshots_v11",
        "add_weekly_explanations_v12",
    ]
    assert _user_version(db_path) == 0

    applied = apply_schema(db_path)
    assert applied["state"] == "current"
    assert applied["applied_migrations"] == [
        "baseline_storage_schema_v1",
        "add_taxonomy_state_v2",
        "add_taxonomy_categories_v3",
        "add_files_content_kind_v4",
        "add_pipeline_state_v5",
        "add_pipeline_fks_v6",
        "add_pipeline_lease_v7",
        "add_chunk_embedding_identity_v8",
        "add_kb_index_contract_v9",
        "add_agentic_ready_manual_operation_state_v10",
        "add_weekly_snapshots_v11",
        "add_weekly_explanations_v12",
    ]
    assert _user_version(db_path) == CURRENT_SQLITE_SCHEMA_VERSION
    assert _files_count(db_path) == 1

    repeated = apply_schema(db_path)
    assert repeated["state"] == "current"
    assert repeated["applied_migrations"] == []
    assert _files_count(db_path) == 1


def test_status_plan_apply_production_v7_preserves_rows_and_is_idempotent(
    tmp_path: Path,
) -> None:
    from ai_actuarial.sqlite_schema import apply_schema, schema_plan, schema_status

    db_path = tmp_path / "production-v7.db"
    _production_v7_db(db_path)

    status = schema_status(db_path)
    assert status["state"] == "needs_migration"
    assert status["can_apply"] is True
    assert [action["id"] for action in schema_plan(db_path)["plan"]["actions"]] == [
        "add_chunk_embedding_identity_v8",
        "add_kb_index_contract_v9",
        "add_agentic_ready_manual_operation_state_v10",
        "add_weekly_snapshots_v11",
        "add_weekly_explanations_v12",
    ]

    with sqlite3.connect(db_path) as conn:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        before_counts = {
            table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in tables
        }

    applied = apply_schema(db_path)
    assert applied["state"] == "current"
    assert applied["applied_migrations"] == [
        "add_chunk_embedding_identity_v8",
        "add_kb_index_contract_v9",
        "add_agentic_ready_manual_operation_state_v10",
        "add_weekly_snapshots_v11",
        "add_weekly_explanations_v12",
    ]
    assert schema_status(db_path)["state"] == "current"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA quick_check").fetchall() == [("ok",)]
        assert {
            table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in tables
        } == before_counts

    repeated = apply_schema(db_path)
    assert repeated["state"] == "current"
    assert repeated["applied_migrations"] == []


def test_v9_manual_operation_state_migration_is_read_compatible_and_idempotent(
    tmp_path: Path,
) -> None:
    from ai_actuarial.api.services.ready_data_publication import (
        read_public_ready_data_snapshot,
    )
    from ai_actuarial.sqlite_schema import apply_schema, schema_plan, schema_status

    db_path = tmp_path / "manual-operation-v9.db"
    storage = Storage(str(db_path))
    try:
        storage._conn.execute("DROP TABLE agentic_ready_manual_operation_state")
        storage._conn.execute("PRAGMA user_version=9")
        storage._conn.commit()
    finally:
        storage.close()

    legacy = Storage.open_read_only(str(db_path))
    try:
        snapshot = read_public_ready_data_snapshot(
            legacy,
            kb_id="kb-legacy",
            profile="general",
        )
        assert snapshot["publication_state"]["latest_operation_kind"] == "none"
        legacy.assert_read_only_snapshot_unchanged()
    finally:
        legacy.close()

    assert schema_status(db_path)["state"] == "needs_migration"
    assert schema_plan(db_path)["plan"]["actions"] == [
        {
            "id": "add_agentic_ready_manual_operation_state_v10",
            "from_version": 9,
            "to_version": 10,
        },
        {
            "id": "add_weekly_snapshots_v11",
            "from_version": 10,
            "to_version": 11,
        },
        {
            "id": "add_weekly_explanations_v12",
            "from_version": 11,
            "to_version": 12,
        },
    ]
    applied = apply_schema(db_path)
    assert applied["state"] == "current"
    assert applied["applied_migrations"] == [
        "add_agentic_ready_manual_operation_state_v10",
        "add_weekly_snapshots_v11",
        "add_weekly_explanations_v12",
    ]
    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(agentic_ready_manual_operation_state)"
            )
        }
    assert columns == {
        "kb_id",
        "profile",
        "operation_kind",
        "operation_state",
        "operation_at",
    }
    repeated = apply_schema(db_path)
    assert repeated["state"] == "current"
    assert repeated["applied_migrations"] == []


def test_v10_manual_operation_state_migration_rolls_back_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_actuarial.sqlite_schema as sqlite_schema

    db_path = tmp_path / "manual-operation-v10-rollback.db"
    storage = Storage(str(db_path))
    try:
        storage._conn.execute("DROP TABLE agentic_ready_manual_operation_state")
        storage._conn.execute("PRAGMA user_version=9")
        storage._conn.commit()
    finally:
        storage.close()

    migration = sqlite_schema.SQLITE_SCHEMA_MIGRATIONS[-1]

    def fail_after_table_create(conn: sqlite3.Connection) -> None:
        migration.apply(conn)
        raise RuntimeError("injected manual-operation migration failure")

    monkeypatch.setattr(
        sqlite_schema,
        "SQLITE_SCHEMA_MIGRATIONS",
        (
            *sqlite_schema.SQLITE_SCHEMA_MIGRATIONS[:-1],
            sqlite_schema.SQLiteSchemaMigration(
                version=migration.version,
                migration_id=migration.migration_id,
                apply=fail_after_table_create,
                source_validator=migration.source_validator,
            ),
        ),
    )

    with pytest.raises(sqlite_schema.SchemaMigrationError, match="failed"):
        sqlite_schema.apply_schema(db_path)

    assert _user_version(db_path) == 9
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            """
            SELECT 1 FROM sqlite_schema
            WHERE type = 'table' AND name = 'agentic_ready_manual_operation_state'
            """
        ).fetchone() is None


def test_mixed_v7_migration_invalidates_unprovable_kb_index_mapping(
    tmp_path: Path,
) -> None:
    from ai_actuarial.sqlite_schema import apply_schema, schema_status

    db_path = tmp_path / "mixed-v7.db"
    storage = Storage(str(db_path))
    storage.close()
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.executescript(
            """
            INSERT INTO files (url, sha256, title, first_seen, last_seen)
            VALUES ('https://example.test/mixed.pdf', 'mixed-sha', 'Mixed', 'created', 'updated');
            INSERT INTO chunk_profiles (
                profile_id, name, config_hash, config_json, chunk_size, chunk_overlap,
                splitter, tokenizer, version, created_at, updated_at
            ) VALUES ('profile-mixed', 'Mixed', 'profile-hash', '{}', 100, 10,
                      'semantic', 'test', 'v1', 'created', 'updated');
            INSERT INTO file_chunk_sets (
                chunk_set_id, file_url, profile_id, markdown_hash, profile_config_hash,
                status, chunk_count, created_at, updated_at
            ) VALUES ('set-mixed', 'https://example.test/mixed.pdf', 'profile-mixed',
                      'markdown-hash', 'profile-hash', 'ready', 2, 'created', 'updated');
            INSERT INTO global_chunks (
                chunk_id, chunk_set_id, chunk_index, content, token_count, created_at
            ) VALUES
                ('chunk-z', 'set-mixed', 0, 'first vector', 2, 'created'),
                ('chunk-a', 'set-mixed', 1, 'second vector', 2, 'created');
            INSERT INTO chunk_embeddings (
                chunk_id, embedding_identity_key, embedding_provider, embedding_model,
                dimension, config_fingerprint, vector_json, status, created_at, updated_at
            ) VALUES
                ('chunk-z', 'identity-current', 'local', 'mixed-model', 2,
                 'config-current', '[1,0]', 'ready', 'created', 'updated'),
                ('chunk-a', 'identity-current', 'local', 'mixed-model', 2,
                 'config-current', '[0,1]', 'ready', 'created', 'updated');
            CREATE TABLE rag_knowledge_bases (
                kb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                kb_mode TEXT DEFAULT 'category',
                embedding_model TEXT NOT NULL,
                chunk_size INTEGER NOT NULL,
                chunk_overlap INTEGER NOT NULL,
                index_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                file_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                index_path TEXT,
                metadata_path TEXT,
                embedding_provider TEXT DEFAULT 'openai',
                embedding_dimension INTEGER,
                chunk_profile_id TEXT,
                index_dirty_at TEXT,
                manifest_profile TEXT DEFAULT 'general',
                embedding_identity_key TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE rag_kb_category_mappings (
                kb_id TEXT NOT NULL,
                category TEXT NOT NULL,
                auto_sync INTEGER DEFAULT 1,
                created_at TEXT,
                PRIMARY KEY (kb_id, category),
                FOREIGN KEY (kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE
            );
            CREATE INDEX idx_rag_kb_category_kb ON rag_kb_category_mappings(kb_id);
            CREATE INDEX idx_rag_kb_category_cat ON rag_kb_category_mappings(category);
            INSERT INTO rag_knowledge_bases (
                kb_id, name, embedding_model, chunk_size, chunk_overlap, index_type,
                created_at, updated_at, embedding_identity_key
            ) VALUES ('kb-mixed', 'Mixed KB', 'mixed-model', 100, 10, 'faiss',
                      'created', 'updated', 'identity-current');
            INSERT INTO rag_kb_category_mappings (kb_id, category, auto_sync, created_at)
            VALUES ('kb-mixed', 'Safety', 1, 'created');
            INSERT INTO kb_chunk_bindings (
                kb_id, file_url, chunk_set_id, bound_at, bound_by, binding_mode,
                target_profile_id
            ) VALUES ('kb-mixed', 'https://example.test/mixed.pdf', 'set-mixed',
                      'created', 'test', 'pin', 'profile-mixed');
            INSERT INTO kb_index_versions (
                index_version_id, kb_id, embedding_provider, embedding_model,
                embedding_dimension, embedding_identity_key,
                binding_snapshot_fingerprint, index_type, status, artifact_path,
                artifact_digest, chunk_count, built_at, created_at
            ) VALUES ('index-mixed', 'kb-mixed', 'local', 'mixed-model', 2,
                      'identity-current', 'binding-current', 'faiss', 'ready',
                      '/tmp/mixed.faiss', 'artifact-current', 2, 'built', 'created');
            INSERT INTO kb_index_items (index_version_id, chunk_id, vector_ordinal)
            VALUES ('index-mixed', 'chunk-z', 0), ('index-mixed', 'chunk-a', 1);
            INSERT INTO kb_ready_index_state (
                kb_id, index_version_id, embedding_provider, embedding_model,
                embedding_dimension, embedding_identity_key,
                binding_snapshot_fingerprint, artifact_path, artifact_digest, updated_at
            ) VALUES ('kb-mixed', 'index-mixed', 'local', 'mixed-model', 2,
                      'identity-current', 'binding-current', '/tmp/mixed.faiss',
                      'artifact-current', 'updated');

            CREATE TABLE file_chunk_sets_v7 (
                chunk_set_id TEXT PRIMARY KEY,
                file_url TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                markdown_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ready',
                chunk_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(file_url, profile_id, markdown_hash),
                FOREIGN KEY(file_url) REFERENCES files(url) ON DELETE CASCADE,
                FOREIGN KEY(profile_id) REFERENCES chunk_profiles(profile_id) ON DELETE CASCADE
            );
            INSERT INTO file_chunk_sets_v7
            SELECT chunk_set_id, file_url, profile_id, markdown_hash, status,
                   chunk_count, created_at, updated_at
            FROM file_chunk_sets;
            DROP TABLE file_chunk_sets;
            ALTER TABLE file_chunk_sets_v7 RENAME TO file_chunk_sets;

            CREATE TABLE chunk_embeddings_v7 (
                chunk_id TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                dim INTEGER NOT NULL DEFAULT 0,
                vector_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (chunk_id, embedding_model),
                FOREIGN KEY(chunk_id) REFERENCES global_chunks(chunk_id) ON DELETE CASCADE
            );
            INSERT INTO chunk_embeddings_v7
            SELECT chunk_id, embedding_model, dimension, vector_json, created_at
            FROM chunk_embeddings;
            DROP TABLE chunk_embeddings;
            ALTER TABLE chunk_embeddings_v7 RENAME TO chunk_embeddings;
            PRAGMA user_version=7;
            """
        )

    assert schema_status(db_path)["state"] == "needs_migration"
    migrated = apply_schema(db_path)

    assert migrated["state"] == "current"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute(
            "SELECT chunk_id, chunk_index, content FROM global_chunks ORDER BY chunk_index"
        ).fetchall() == [
            ("chunk-z", 0, "first vector"),
            ("chunk-a", 1, "second vector"),
        ]
        assert conn.execute(
            "SELECT chunk_id, vector_json, status FROM chunk_embeddings ORDER BY chunk_id"
        ).fetchall() == [
            ("chunk-a", "[0,1]", "legacy_unusable"),
            ("chunk-z", "[1,0]", "legacy_unusable"),
        ]
        assert conn.execute(
            "SELECT kb_id, file_url, chunk_set_id, target_profile_id FROM kb_chunk_bindings"
        ).fetchall() == [
            (
                "kb-mixed",
                "https://example.test/mixed.pdf",
                "set-mixed",
                "profile-mixed",
            )
        ]
        assert conn.execute(
            "SELECT kb_id, category, auto_sync FROM rag_kb_category_mappings"
        ).fetchall() == [("kb-mixed", "Safety", 1)]
        assert conn.execute("SELECT COUNT(*) FROM kb_index_items").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM kb_ready_index_state").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM kb_index_versions").fetchone()[0] == 0


@pytest.mark.parametrize(
    "unknown_drift",
    (
        "ALTER TABLE kb_index_versions ADD COLUMN unexpected_contract TEXT",
        "CREATE INDEX idx_unexpected_contract ON kb_index_versions(status)",
        "ALTER TABLE rag_knowledge_bases ADD COLUMN unexpected_kb_contract TEXT",
        "CREATE INDEX idx_unexpected_kb_contract ON rag_knowledge_bases(name)",
    ),
)
def test_production_v7_with_unknown_drift_remains_fail_closed(
    tmp_path: Path,
    unknown_drift: str,
) -> None:
    from ai_actuarial.sqlite_schema import schema_plan, schema_status

    db_path = tmp_path / "production-v7-drift.db"
    _production_v7_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(unknown_drift)

    status = schema_status(db_path)
    assert status["state"] == "invalid"
    assert status["can_apply"] is False
    assert schema_plan(db_path)["blocked"] is True


@pytest.mark.parametrize(
    "unknown_object",
    (
        "CREATE VIEW unexpected_v7_view AS SELECT url FROM files",
        """
        CREATE TRIGGER unexpected_v7_trigger
        AFTER INSERT ON files
        BEGIN
            SELECT 1;
        END
        """,
    ),
)
def test_production_v7_with_unknown_view_or_trigger_remains_fail_closed(
    tmp_path: Path,
    unknown_object: str,
) -> None:
    from ai_actuarial.sqlite_schema import schema_plan, schema_status

    db_path = tmp_path / "production-v7-unknown-object.db"
    _production_v7_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(unknown_object)

    status = schema_status(db_path)
    assert status["state"] == "invalid"
    assert status["can_apply"] is False
    assert "unexpected_schema_objects" in status["problems"]
    assert schema_plan(db_path)["blocked"] is True


def test_v6_migration_preserves_pipeline_stage_and_child_run_rows(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import (
        CURRENT_SQLITE_SCHEMA_VERSION,
        _add_pipeline_state_v5,
        apply_schema,
        schema_status,
    )

    db_path = tmp_path / "v5-with-pipeline-data.db"
    storage = Storage(str(db_path))
    try:
        conn = storage._conn
        # Walk the fresh v6 database back to a genuine v5 state: drop the two v6
        # indexes and rebuild the two child tables at their v5 (FK-less) shape.
        conn.execute("DROP INDEX IF EXISTS idx_child_run_parent_run_id")
        conn.execute("DROP INDEX IF EXISTS idx_pipeline_run_status")
        conn.execute("DROP TABLE child_run")
        conn.execute("DROP TABLE pipeline_stage")
        conn.execute("DROP TABLE pipeline_run")
        _add_pipeline_state_v5(conn)
        conn.execute(
            """
            INSERT INTO pipeline_run (run_id, correlation_id, source_type, status, watermark, error, created_at, updated_at)
            VALUES ('run-1', 'corr-1', 'scheduled', 'pending', '', '', '2026-08-25T00:00:00Z', '2026-08-25T00:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO pipeline_stage (run_id, stage_name, stage_order, options_json, status, checkpoint_json, retry_count, committed_artifacts_json, error, updated_at)
            VALUES ('run-1', 'acquisition', 1, '{"sites": 2}', 'pending', '{}', 0, '[]', '', '2026-08-25T00:00:00Z')
            """
        )
        conn.execute(
            """
            INSERT INTO child_run (child_run_id, parent_run_id, correlation_id, status, partial, error, created_at, updated_at)
            VALUES ('child-1', 'run-1', 'corr-1', 'pending', 0, '', '2026-08-25T00:00:00Z', '2026-08-25T00:00:00Z')
            """
        )
        conn.commit()
    finally:
        storage.close()

    assert _user_version(db_path) == 5
    assert schema_status(str(db_path))["state"] == "needs_migration"

    applied = apply_schema(str(db_path))
    assert applied["state"] == "current"
    assert applied["applied_migrations"] == [
        "add_pipeline_fks_v6",
        "add_pipeline_lease_v7",
        "add_chunk_embedding_identity_v8",
        "add_kb_index_contract_v9",
        "add_agentic_ready_manual_operation_state_v10",
        "add_weekly_snapshots_v11",
        "add_weekly_explanations_v12",
    ]
    assert _user_version(db_path) == CURRENT_SQLITE_SCHEMA_VERSION

    conn = sqlite3.connect(db_path)
    try:
        # Existing rows survive the table rebuild.
        stages = conn.execute(
            "SELECT run_id, stage_name, stage_order, options_json FROM pipeline_stage"
        ).fetchall()
        assert stages == [("run-1", "acquisition", 1, '{"sites": 2}')]
        children = conn.execute(
            "SELECT child_run_id, parent_run_id, partial FROM child_run"
        ).fetchall()
        assert children == [("child-1", "run-1", 0)]

        # FK constraints are present after the rebuild.
        stage_fks = conn.execute("PRAGMA foreign_key_list(pipeline_stage)").fetchall()
        assert stage_fks and stage_fks[0][2] == "pipeline_run"
        child_fks = conn.execute("PRAGMA foreign_key_list(child_run)").fetchall()
        assert child_fks and child_fks[0][2] == "pipeline_run"

        # The two indexes are present.
        run_indexes = {r[1] for r in conn.execute("PRAGMA index_list(pipeline_run)").fetchall()}
        assert "idx_pipeline_run_status" in run_indexes
        child_indexes = {r[1] for r in conn.execute("PRAGMA index_list(child_run)").fetchall()}
        assert "idx_child_run_parent_run_id" in child_indexes
    finally:
        conn.close()


def test_schema_runner_plans_registered_old_version_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import ai_actuarial.sqlite_schema as sqlite_schema

    db_path = tmp_path / "future-old-version.db"
    storage = Storage(str(db_path))
    storage.close()

    def apply_v13(conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA user_version=13")

    monkeypatch.setattr(sqlite_schema, "CURRENT_SQLITE_SCHEMA_VERSION", 13)
    monkeypatch.setattr(
        sqlite_schema,
        "SQLITE_SCHEMA_MIGRATIONS",
        (
            *sqlite_schema.SQLITE_SCHEMA_MIGRATIONS,
            sqlite_schema.SQLiteSchemaMigration(
                version=13,
                migration_id="test_schema_v13",
                apply=apply_v13,
            ),
        ),
    )

    status = sqlite_schema.schema_status(db_path)
    assert status["state"] == "needs_migration"
    assert status["database"]["user_version"] == 12

    plan = sqlite_schema.schema_plan(db_path)
    assert plan["plan"]["actions"] == [
        {"id": "test_schema_v13", "from_version": 12, "to_version": 13}
    ]

    applied = sqlite_schema.apply_schema(db_path)
    assert applied["state"] == "current"
    assert applied["database"]["user_version"] == 13
    assert applied["applied_migrations"] == ["test_schema_v13"]
    assert _user_version(db_path) == 13


def test_schema_runner_accepts_registered_old_version_source_signature(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_actuarial.sqlite_schema as sqlite_schema

    db_path = tmp_path / "future-ddl-old-version.db"
    storage = Storage(str(db_path))
    try:
        v6_signature = sqlite_schema._schema_signature(storage._conn)
    finally:
        storage.close()

    expected = Storage(":memory:")
    try:
        expected._conn.execute("ALTER TABLE files ADD COLUMN schema_runner_v7_marker TEXT")
        v7_signature = sqlite_schema._schema_signature(expected._conn)
    finally:
        expected.close()

    def accepts_v6_source(
        _conn: sqlite3.Connection,
        tables: dict[str, sqlite_schema.TableSignature],
    ) -> bool:
        return tables == v6_signature

    def apply_v13(conn: sqlite3.Connection) -> None:
        conn.execute("ALTER TABLE files ADD COLUMN schema_runner_v7_marker TEXT")
        conn.execute("PRAGMA user_version=13")

    monkeypatch.setattr(sqlite_schema, "CURRENT_SQLITE_SCHEMA_VERSION", 13)
    monkeypatch.setattr(sqlite_schema, "_current_storage_signature", lambda: v7_signature)
    monkeypatch.setattr(
        sqlite_schema,
        "SQLITE_SCHEMA_MIGRATIONS",
        (
            *sqlite_schema.SQLITE_SCHEMA_MIGRATIONS,
            sqlite_schema.SQLiteSchemaMigration(
                version=13,
                migration_id="test_schema_v13_add_marker",
                apply=apply_v13,
                source_validator=accepts_v6_source,
            ),
        ),
    )

    status = sqlite_schema.schema_status(db_path)
    assert status["state"] == "needs_migration"
    assert status["database"]["user_version"] == 12

    plan = sqlite_schema.schema_plan(db_path)
    assert plan["plan"]["actions"] == [
        {"id": "test_schema_v13_add_marker", "from_version": 12, "to_version": 13}
    ]

    applied = sqlite_schema.apply_schema(db_path)
    assert applied["state"] == "current"
    assert applied["applied_migrations"] == ["test_schema_v13_add_marker"]
    assert _user_version(db_path) == 13


def test_schema_runner_rejects_mutating_source_validator_during_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ai_actuarial.sqlite_schema as sqlite_schema

    db_path = tmp_path / "mutating-source-validator.db"
    storage = Storage(str(db_path))
    try:
        v6_signature = sqlite_schema._schema_signature(storage._conn)
    finally:
        storage.close()

    expected = Storage(":memory:")
    try:
        expected._conn.execute("ALTER TABLE files ADD COLUMN schema_runner_v7_marker TEXT")
        v7_signature = sqlite_schema._schema_signature(expected._conn)
    finally:
        expected.close()

    validator_calls = 0
    query_only_values: list[int] = []

    def mutating_validator(
        conn: sqlite3.Connection,
        tables: dict[str, sqlite_schema.TableSignature],
    ) -> bool:
        nonlocal validator_calls
        validator_calls += 1
        query_only_values.append(int(conn.execute("PRAGMA query_only").fetchone()[0]))
        if tables != v6_signature:
            return False
        if validator_calls == 1:
            return True
        conn.execute("CREATE TABLE validator_mutation_leak (secret_value TEXT)")
        return True

    def apply_v13(conn: sqlite3.Connection) -> None:
        conn.execute("ALTER TABLE files ADD COLUMN schema_runner_v7_marker TEXT")
        conn.execute("PRAGMA user_version=13")

    monkeypatch.setattr(sqlite_schema, "CURRENT_SQLITE_SCHEMA_VERSION", 13)
    monkeypatch.setattr(sqlite_schema, "_current_storage_signature", lambda: v7_signature)
    monkeypatch.setattr(
        sqlite_schema,
        "SQLITE_SCHEMA_MIGRATIONS",
        (
            *sqlite_schema.SQLITE_SCHEMA_MIGRATIONS,
            sqlite_schema.SQLiteSchemaMigration(
                version=13,
                migration_id="test_schema_v13_block_mutating_validator",
                apply=apply_v13,
                source_validator=mutating_validator,
            ),
        ),
    )

    status = sqlite_schema.schema_status(db_path)
    assert status["state"] == "needs_migration"

    with pytest.raises(sqlite_schema.SchemaMigrationError, match="not safe to migrate"):
        sqlite_schema.apply_schema(db_path)

    assert validator_calls >= 2
    assert query_only_values and set(query_only_values) == {1}
    assert _user_version(db_path) == 12
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            """
            SELECT 1 FROM sqlite_schema
            WHERE type = 'table' AND name = 'validator_mutation_leak'
            """
        ).fetchone() is None
        file_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_xinfo(files)").fetchall()
        }
    assert "schema_runner_v7_marker" not in file_columns


def test_schema_runner_accepts_exported_chat_service_optional_schema(
    tmp_path: Path,
) -> None:
    from ai_actuarial.api.services import ensure_conversation_schema
    from ai_actuarial.sqlite_schema import schema_plan, schema_status

    db_path = tmp_path / "chat-service.db"
    storage = Storage(str(db_path))
    try:
        ensure_conversation_schema(storage)
    finally:
        storage.close()

    status = schema_status(db_path)
    assert status["state"] == "current"

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA user_version=0")

    legacy_plan = schema_plan(db_path)
    assert legacy_plan["state"] == "needs_migration"
    assert [action["id"] for action in legacy_plan["plan"]["actions"]] == [
        "baseline_storage_schema_v1",
        "add_taxonomy_state_v2",
        "add_taxonomy_categories_v3",
        "add_files_content_kind_v4",
        "add_pipeline_state_v5",
        "add_pipeline_fks_v6",
        "add_pipeline_lease_v7",
        "add_chunk_embedding_identity_v8",
        "add_kb_index_contract_v9",
        "add_agentic_ready_manual_operation_state_v10",
        "add_weekly_snapshots_v11",
        "add_weekly_explanations_v12",
    ]


def test_schema_runner_rejects_newer_than_code(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import CURRENT_SQLITE_SCHEMA_VERSION, SchemaMigrationError, apply_schema, schema_status

    db_path = tmp_path / "future.db"
    storage = Storage(str(db_path))
    storage.close()
    with sqlite3.connect(db_path) as conn:
        conn.execute(f"PRAGMA user_version={CURRENT_SQLITE_SCHEMA_VERSION + 1}")

    status = schema_status(db_path)
    assert status["state"] == "newer_than_code"
    assert status["blocked"] is True
    with pytest.raises(SchemaMigrationError, match="newer than code"):
        apply_schema(db_path)


def test_schema_runner_rejects_unknown_and_partial_schema(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import SchemaMigrationError, apply_schema, schema_plan, schema_status

    unknown_db = tmp_path / "unknown.db"
    with sqlite3.connect(unknown_db) as conn:
        conn.execute(
            "CREATE TABLE customer_secret_table (secret_payload_marker TEXT)"
        )
    unknown_status = schema_status(unknown_db)
    assert unknown_status["state"] == "invalid"
    unknown_plan_json = json.dumps(schema_plan(unknown_db), sort_keys=True)
    assert "customer_secret_table" not in unknown_plan_json
    assert "secret_payload_marker" not in unknown_plan_json
    with pytest.raises(SchemaMigrationError, match="not safe to migrate"):
        apply_schema(unknown_db)

    partial_db = tmp_path / "partial.db"
    _current_db_at_version_zero(partial_db)
    with sqlite3.connect(partial_db) as conn:
        conn.execute("CREATE TABLE agentic_ready_publications_attempts_new (id TEXT)")
    partial_status = schema_status(partial_db)
    assert partial_status["state"] == "invalid"
    assert "partial_migration_state" in partial_status["problems"]
    assert "agentic_ready_publications_attempts_new" not in json.dumps(
        partial_status, sort_keys=True
    )


def test_schema_runner_rejects_unexpected_views_and_triggers(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import schema_plan, schema_status

    db_path = tmp_path / "unexpected-objects.db"
    storage = Storage(str(db_path))
    storage.close()
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE VIEW unexpected_business_view AS
            SELECT url AS customer_identifier FROM files;
            CREATE TRIGGER unexpected_business_trigger
            AFTER INSERT ON files
            BEGIN
                SELECT 1;
            END;
            """
        )

    status = schema_status(db_path)
    assert status["state"] == "invalid"
    assert "unexpected_schema_objects" in status["problems"]
    assert status["details"]["unexpected_schema_objects"] == {
        "total": 2,
        "by_type": {"trigger": 1, "view": 1},
    }
    diagnostics = json.dumps(schema_plan(db_path), sort_keys=True)
    for leaked_identifier in (
        "unexpected_business_view",
        "unexpected_business_trigger",
        "customer_identifier",
    ):
        assert leaked_identifier not in diagnostics


def test_version_zero_database_with_only_view_is_not_bootstrapped(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import schema_plan, schema_status

    db_path = tmp_path / "view-only-v0.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE VIEW legacy_secret_view AS SELECT 1 AS legacy_secret_column"
        )
        conn.execute("PRAGMA user_version=0")

    before_schema = _schema_rows(db_path)
    with pytest.raises(RuntimeError, match="schema apply|schema preflight"):
        Storage(str(db_path))

    assert _user_version(db_path) == 0
    assert _schema_rows(db_path) == before_schema
    status = schema_status(db_path)
    assert status["state"] == "invalid"
    diagnostics = json.dumps(schema_plan(db_path), sort_keys=True)
    assert "legacy_secret_view" not in diagnostics
    assert "legacy_secret_column" not in diagnostics


def test_schema_runner_rejects_matching_names_with_wrong_column_metadata(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import schema_plan, schema_status

    db_path = tmp_path / "wrong-metadata.db"
    _current_db_at_version_zero(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("ALTER TABLE files RENAME TO files_old")
        conn.execute(
            """
            CREATE TABLE files (
                id TEXT PRIMARY KEY,
                url INTEGER UNIQUE,
                sha256 TEXT NOT NULL,
                title TEXT,
                source_site TEXT,
                source_page_url TEXT,
                original_filename TEXT,
                local_path TEXT,
                bytes INTEGER,
                content_type TEXT,
                last_modified TEXT,
                etag TEXT,
                published_time TEXT,
                first_seen TEXT,
                last_seen TEXT,
                crawl_time TEXT,
                deleted_at TEXT
            )
            """
        )
        conn.execute("DROP TABLE files_old")
        conn.execute("PRAGMA user_version=0")

    status = schema_status(db_path)
    assert status["state"] == "invalid"
    assert "schema_signature_mismatch" in status["problems"]
    diagnostics = json.dumps(schema_plan(db_path), sort_keys=True)
    for leaked_identifier in ("files", "url", "sha256", "deleted_at"):
        assert leaked_identifier not in diagnostics


def test_schema_runner_accepts_known_catalog_incremental_extra_columns(
    tmp_path: Path,
) -> None:
    from ai_actuarial.sqlite_schema import schema_status

    db_path = tmp_path / "catalog-extra-compatible.db"
    storage = Storage(str(db_path))
    storage.close()
    with sqlite3.connect(db_path) as conn:
        for column in (
            "title",
            "source_site",
            "original_filename",
            "local_path",
            "keywords_json",
        ):
            conn.execute(f"ALTER TABLE catalog_items ADD COLUMN {column} TEXT")

    status = schema_status(db_path)
    assert status["state"] == "current"
    reopened = Storage(str(db_path))
    reopened.close()


def test_schema_runner_rejects_malformed_catalog_incremental_extra_column(
    tmp_path: Path,
) -> None:
    from ai_actuarial.sqlite_schema import schema_plan, schema_status

    db_path = tmp_path / "catalog-extra-malformed.db"
    storage = Storage(str(db_path))
    storage.close()
    with sqlite3.connect(db_path) as conn:
        conn.execute("ALTER TABLE catalog_items ADD COLUMN title TEXT NOT NULL")

    status = schema_status(db_path)
    assert status["state"] == "invalid"
    assert "column_signature_mismatch" in status["problems"]
    diagnostics = json.dumps(schema_plan(db_path), sort_keys=True)
    assert "title" not in diagnostics
    with pytest.raises(RuntimeError, match="schema preflight failed"):
        Storage(str(db_path))


def test_schema_runner_rolls_back_failed_migration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import ai_actuarial.sqlite_schema as sqlite_schema

    db_path = tmp_path / "rollback.db"
    _current_db_at_version_zero(db_path)

    def fail_after_version_write(conn: sqlite3.Connection) -> None:
        conn.execute(f"PRAGMA user_version={sqlite_schema.CURRENT_SQLITE_SCHEMA_VERSION}")
        raise RuntimeError("injected migration failure")

    monkeypatch.setattr(
        sqlite_schema,
        "SQLITE_SCHEMA_MIGRATIONS",
        (
            sqlite_schema.SQLiteSchemaMigration(
                version=1,
                migration_id="baseline_storage_schema_v1",
                apply=fail_after_version_write,
            ),
            *sqlite_schema.SQLITE_SCHEMA_MIGRATIONS[1:],
        ),
    )

    with pytest.raises(sqlite_schema.SchemaMigrationError, match="failed"):
        sqlite_schema.apply_schema(db_path)

    assert _user_version(db_path) == 0
    assert _files_count(db_path) == 1


def test_schema_runner_serializes_concurrent_apply(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import CURRENT_SQLITE_SCHEMA_VERSION, apply_schema

    db_path = tmp_path / "concurrent.db"
    _current_db_at_version_zero(db_path)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: apply_schema(db_path), range(2)))

    applied = [result["applied_migrations"] for result in results]
    assert sorted(len(item) for item in applied) == [0, 12]
    assert _user_version(db_path) == CURRENT_SQLITE_SCHEMA_VERSION
    assert _files_count(db_path) == 1


@pytest.mark.parametrize("precreate_empty_file", (False, True))
def test_schema_runner_serializes_concurrent_fresh_apply(
    tmp_path: Path,
    precreate_empty_file: bool,
) -> None:
    from ai_actuarial.sqlite_schema import CURRENT_SQLITE_SCHEMA_VERSION, apply_schema

    db_path = tmp_path / ("empty-concurrent.db" if precreate_empty_file else "missing-concurrent.db")
    if precreate_empty_file:
        db_path.touch()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: apply_schema(db_path), range(2)))

    applied = [result["applied_migrations"] for result in results]
    assert sorted(len(item) for item in applied) == [0, 1]
    assert any(item == ["create_current_storage_schema"] for item in applied)
    assert _user_version(db_path) == CURRENT_SQLITE_SCHEMA_VERSION
    assert _files_count(db_path) == 0


def test_schema_cli_json_contract_for_status_plan_apply(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import CURRENT_SQLITE_SCHEMA_VERSION

    help_result = subprocess.run(
        [sys.executable, "-m", "ai_actuarial.cli", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "schema" in help_result.stdout

    db_path = tmp_path / "cli.db"
    _current_db_at_version_zero(db_path)

    for command in ("status", "plan"):
        result = _run_schema_cli(command, "--db", str(db_path), "--json")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["success"] is True
        assert str(db_path) not in result.stdout
        assert payload["database"]["user_version"] == 0

    apply_result = _run_schema_cli("apply", "--db", str(db_path), "--json")
    assert apply_result.returncode == 0, apply_result.stderr
    apply_payload = json.loads(apply_result.stdout)
    assert apply_payload["database"]["user_version"] == CURRENT_SQLITE_SCHEMA_VERSION
    assert apply_payload["applied_migrations"] == [
        "baseline_storage_schema_v1",
        "add_taxonomy_state_v2",
        "add_taxonomy_categories_v3",
        "add_files_content_kind_v4",
        "add_pipeline_state_v5",
        "add_pipeline_fks_v6",
        "add_pipeline_lease_v7",
        "add_chunk_embedding_identity_v8",
        "add_kb_index_contract_v9",
        "add_agentic_ready_manual_operation_state_v10",
        "add_weekly_snapshots_v11",
        "add_weekly_explanations_v12",
    ]
    assert str(db_path) not in apply_result.stdout


def test_schema_cli_apply_missing_database_creates_current_schema(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import CURRENT_SQLITE_SCHEMA_VERSION

    db_path = tmp_path / "missing" / "fresh.db"

    plan_result = _run_schema_cli("plan", "--db", str(db_path), "--json")
    assert plan_result.returncode == 0, plan_result.stderr
    plan_payload = json.loads(plan_result.stdout)
    assert plan_payload["state"] == "missing"
    assert plan_payload["plan"]["actions"][0]["id"] == "create_current_storage_schema"
    assert not db_path.exists()

    apply_result = _run_schema_cli("apply", "--db", str(db_path), "--json")
    assert apply_result.returncode == 0, apply_result.stderr
    apply_payload = json.loads(apply_result.stdout)
    assert apply_payload["state"] == "current"
    assert apply_payload["database"]["user_version"] == CURRENT_SQLITE_SCHEMA_VERSION
    assert _user_version(db_path) == CURRENT_SQLITE_SCHEMA_VERSION


def test_legacy_missing_backfill_table_is_migratable(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import (
        CURRENT_SQLITE_SCHEMA_VERSION,
        apply_schema,
        schema_status,
    )

    db_path = tmp_path / "legacy-missing-table.db"
    storage = Storage(str(db_path))
    try:
        storage._conn.execute("DROP TABLE agentic_ready_automation_lock")
        storage._conn.execute("PRAGMA user_version=0")
        storage._conn.commit()
    finally:
        storage.close()

    status = schema_status(db_path)
    assert status["state"] == "needs_migration"
    assert status["can_apply"] is True
    assert status["blocked"] is False

    applied = apply_schema(db_path)
    assert applied["state"] == "current"
    assert applied["applied_migrations"] == [
        "baseline_storage_schema_v1",
        "add_taxonomy_state_v2",
        "add_taxonomy_categories_v3",
        "add_files_content_kind_v4",
        "add_pipeline_state_v5",
        "add_pipeline_fks_v6",
        "add_pipeline_lease_v7",
        "add_chunk_embedding_identity_v8",
        "add_kb_index_contract_v9",
        "add_agentic_ready_manual_operation_state_v10",
        "add_weekly_snapshots_v11",
        "add_weekly_explanations_v12",
    ]
    assert _user_version(db_path) == CURRENT_SQLITE_SCHEMA_VERSION
    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "agentic_ready_automation_lock" in tables


def test_legacy_missing_non_backfill_table_is_invalid(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import schema_status

    db_path = tmp_path / "legacy-missing-core-table.db"
    storage = Storage(str(db_path))
    try:
        storage._conn.execute("DROP TABLE pages")
        storage._conn.execute("PRAGMA user_version=0")
        storage._conn.commit()
    finally:
        storage.close()

    status = schema_status(db_path)
    assert status["state"] == "invalid"
    assert status["blocked"] is True
    assert "missing_required_tables" in status["problems"]


def test_legacy_missing_backfill_column_is_migratable(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import (
        CURRENT_SQLITE_SCHEMA_VERSION,
        apply_schema,
        schema_status,
    )

    db_path = tmp_path / "legacy-missing-column.db"
    storage = Storage(str(db_path))
    try:
        storage._conn.execute("ALTER TABLE agentic_ready_manifests DROP COLUMN artifact_digest")
        storage._conn.execute("PRAGMA user_version=0")
        storage._conn.commit()
    finally:
        storage.close()

    status = schema_status(db_path)
    assert status["state"] == "needs_migration"
    assert status["can_apply"] is True

    applied = apply_schema(db_path)
    assert applied["state"] == "current"
    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(agentic_ready_manifests)")}
    assert "artifact_digest" in columns
    assert _user_version(db_path) == CURRENT_SQLITE_SCHEMA_VERSION


def test_legacy_missing_non_backfill_column_is_invalid(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import schema_status

    db_path = tmp_path / "legacy-missing-core-column.db"
    storage = Storage(str(db_path))
    try:
        storage._conn.execute("ALTER TABLE files DROP COLUMN sha256")
        storage._conn.execute("PRAGMA user_version=0")
        storage._conn.commit()
    finally:
        storage.close()

    status = schema_status(db_path)
    assert status["state"] == "invalid"
    assert status["blocked"] is True
    assert "missing_columns" in status["problems"]


def test_exact_version_10_source_is_migratable(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import schema_status

    db_path = tmp_path / "exact-v10.db"
    _current_db_at_version_10(db_path)

    status = schema_status(db_path)

    assert status["state"] == "needs_migration"
    assert status["can_apply"] is True
    assert status["blocked"] is False


@pytest.mark.parametrize(
    ("snapshot_tables", "case_name"),
    [
        (("weekly_snapshots",), "snapshots-only"),
        (("weekly_snapshot_members",), "members-only"),
        (
            ("weekly_snapshots", "weekly_snapshot_members"),
            "both-snapshot-tables",
        ),
    ],
)
def test_version_10_source_with_v11_snapshot_tables_is_invalid(
    tmp_path: Path,
    snapshot_tables: tuple[str, ...],
    case_name: str,
) -> None:
    from ai_actuarial.sqlite_schema import schema_status

    db_path = tmp_path / f"v10-{case_name}.db"
    _current_db_at_version_10(db_path, snapshot_tables=snapshot_tables)

    status = schema_status(db_path)

    assert status["state"] == "invalid"
    assert status["can_apply"] is False
    assert status["blocked"] is True


def test_version_10_source_missing_auto_backfill_table_is_invalid(
    tmp_path: Path,
) -> None:
    from ai_actuarial.sqlite_schema import schema_status

    db_path = tmp_path / "v10-missing-unrelated-table.db"
    _current_db_at_version_10(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE agentic_ready_automation_lock")

    status = schema_status(db_path)

    assert status["state"] == "invalid"
    assert status["can_apply"] is False
    assert status["blocked"] is True
    assert "missing_required_tables" in status["problems"]


def test_version_10_source_with_unexpected_trigger_is_invalid(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import schema_status

    db_path = tmp_path / "v10-unexpected-trigger.db"
    _current_db_at_version_10(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TRIGGER unexpected_v10_trigger
            AFTER INSERT ON files
            BEGIN
                SELECT 1;
            END
            """
        )

    status = schema_status(db_path)

    assert status["state"] == "invalid"
    assert status["can_apply"] is False
    assert status["blocked"] is True
    assert "unexpected_schema_objects" in status["problems"]


def test_indexes_equivalent_ignores_column_cid() -> None:
    from ai_actuarial.sqlite_schema import _indexes_equivalent

    left = (
        (
            0,
            "c",
            0,
            (
                (0, 1, "provider", 0, "BINARY", 1),
                (1, 2, "category", 0, "BINARY", 1),
                (2, 5, "is_default", 0, "BINARY", 1),
                (3, -1, None, 0, "BINARY", 0),
            ),
        ),
    )
    right = (
        (
            0,
            "c",
            0,
            (
                (0, 1, "provider", 0, "BINARY", 1),
                (1, 2, "category", 0, "BINARY", 1),
                (2, 11, "is_default", 0, "BINARY", 1),
                (3, -1, None, 0, "BINARY", 0),
            ),
        ),
    )
    assert _indexes_equivalent(left, right)


def test_indexes_equivalent_detects_name_difference() -> None:
    from ai_actuarial.sqlite_schema import _indexes_equivalent

    left = (
        (0, "c", 0, ((0, 1, "provider", 0, "BINARY", 1),)),
    )
    right = (
        (0, "c", 0, ((0, 1, "category", 0, "BINARY", 1),)),
    )
    assert not _indexes_equivalent(left, right)


def test_indexes_equivalent_detects_duplicate_index() -> None:
    from ai_actuarial.sqlite_schema import _indexes_equivalent

    # Two redundant indexes over the same columns must not collapse to
    # "equivalent" against a single canonical index.
    redundant = (
        (0, "c", 0, ((0, 1, "provider", 0, "BINARY", 1),)),
        (0, "c", 0, ((0, 2, "provider", 0, "BINARY", 1),)),
    )
    canonical = (
        (0, "c", 0, ((0, 1, "provider", 0, "BINARY", 1),)),
    )
    assert not _indexes_equivalent(redundant, canonical)


def test_column_signature_equivalent_tolerates_allowlisted_notnull() -> None:
    from ai_actuarial.sqlite_schema import _column_signature_equivalent

    actual = ("instance_id", "TEXT", 0, "'default'", 0, 0)
    expected = ("instance_id", "TEXT", 1, "'default'", 0, 0)
    assert _column_signature_equivalent(actual, expected, "api_tokens", "instance_id")


def test_column_signature_equivalent_rejects_non_allowlisted_notnull() -> None:
    from ai_actuarial.sqlite_schema import _column_signature_equivalent

    actual = ("url", "TEXT", 0, None, 0, 0)
    expected = ("url", "TEXT", 1, None, 0, 0)
    assert not _column_signature_equivalent(actual, expected, "files", "url")


def test_accept_version_2_source_requires_taxonomy_state(tmp_path: Path) -> None:
    """#5 regression: a source without taxonomy_state must not be accepted as v2."""
    from ai_actuarial.sqlite_schema import (
        _accept_version_2_source,
        _schema_signature,
    )

    db_path = tmp_path / "v2-missing-taxonomy-state.db"
    storage = Storage(str(db_path))
    try:
        storage._conn.execute("DROP TABLE taxonomy_state")
        storage._conn.commit()
        tables = _schema_signature(storage._conn)
        assert "taxonomy_state" not in tables
        assert _accept_version_2_source(storage._conn, tables) is False
    finally:
        storage.close()
