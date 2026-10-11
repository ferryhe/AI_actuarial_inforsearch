from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ai_actuarial.api.services.rag_admin import _KBListStorageView
from ai_actuarial.kb_status import classify_kb_status
from ai_actuarial.postgres import PostgresConnection
from ai_actuarial.sqlite_schema import (
    CURRENT_SQLITE_SCHEMA_VERSION,
    apply_schema,
    schema_plan,
    schema_status,
)
from ai_actuarial.storage import Storage
from tests.postgres_helpers import postgres_url_for_path

LATEST_INDEX = "idx_file_chunk_sets_latest"
LATEST_INDEX_COLUMNS = (
    ("file_url", 0),
    ("profile_id", 0),
    ("updated_at", 1),
    ("created_at", 1),
    ("chunk_set_id", 1),
)


def _seed_tied_chunk_sets(db_path: Path) -> tuple[str, str, str]:
    storage = Storage(postgres_url_for_path(str(db_path)))
    try:
        file_url = "https://issue-376.test/tied.pdf"
        storage.insert_file(
            url=file_url,
            sha256="issue-376",
            title="Issue 376 tie",
            source_site="issue-376.test",
            source_page_url="https://issue-376.test",
            original_filename="tied.pdf",
            local_path=str(db_path.with_suffix(".pdf")),
            bytes=1,
            content_type="application/pdf",
        )
        profile = storage.create_chunk_profile(
            name="issue-376-profile", chunk_size=128, chunk_overlap=16
        )
        profile_id = str(profile["profile_id"])
        tied_at = "2026-09-14T12:00:00+00:00"
        storage._conn.executemany(
            """
            INSERT INTO file_chunk_sets (
                chunk_set_id, file_url, profile_id, markdown_hash,
                profile_config_hash, status, chunk_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    "cs-a",
                    file_url,
                    profile_id,
                    "hash-a",
                    str(profile["config_hash"]),
                    "ready",
                    1,
                    tied_at,
                    tied_at,
                ),
                (
                    "cs-z",
                    file_url,
                    profile_id,
                    "hash-z",
                    str(profile["config_hash"]),
                    "failed",
                    0,
                    tied_at,
                    tied_at,
                ),
            ),
        )
        storage._conn.execute(
            """
            INSERT INTO kb_chunk_bindings (
                kb_id, file_url, chunk_set_id, bound_at, bound_by,
                binding_mode, target_profile_id
            ) VALUES ('kb-376', ?, 'cs-a', ?, 'test', 'follow_latest', ?)
            """,
            (file_url, tied_at, profile_id),
        )
        storage._conn.execute(
            """
            INSERT INTO rag_knowledge_bases (
                kb_id, name, embedding_model, chunk_profile_id, chunk_size,
                chunk_overlap, index_type, created_at, updated_at
            ) VALUES (?, 'Issue 376', 'issue-376-model', ?, 128, 16, 'Flat', ?, ?)
            """,
            ("kb-376", profile_id, tied_at, tied_at),
        )
        storage._conn.commit()
        return file_url, profile_id, "kb-376"
    finally:
        storage.close()


def _index_columns(conn: sqlite3.Connection) -> tuple[tuple[str, int], ...]:
    return tuple(
        (str(row[2]), int(row[3]))
        for row in conn.execute(f"PRAGMA index_xinfo({LATEST_INDEX})")
        if int(row[5]) == 1
    )


def test_v15_migration_plan_apply_and_strict_source_validation(tmp_path: Path) -> None:
    db_path = tmp_path / "v14.db"
    storage = Storage._legacy_sqlite_schema_for_validation(db_path)
    storage.close()
    with sqlite3.connect(db_path) as conn:
        conn.execute(f"DROP INDEX IF EXISTS {LATEST_INDEX}")
        conn.execute("PRAGMA user_version=14")

    status = schema_status(db_path)
    assert CURRENT_SQLITE_SCHEMA_VERSION == 16
    assert status["state"] == "needs_migration"
    assert schema_plan(db_path)["plan"]["actions"] == [
        {
            "id": "add_file_chunk_sets_latest_index_v15",
            "from_version": 14,
            "to_version": 15,
        },
        {"id": "add_auth_token_type_v16", "from_version": 15, "to_version": 16},
    ]

    applied = apply_schema(db_path)
    assert applied["applied_migrations"] == [
        "add_file_chunk_sets_latest_index_v15",
        "add_auth_token_type_v16",
    ]
    assert apply_schema(db_path)["applied_migrations"] == []
    with sqlite3.connect(db_path) as conn:
        assert _index_columns(conn) == LATEST_INDEX_COLUMNS

    invalid_path = tmp_path / "premature-index.db"
    invalid_storage = Storage._legacy_sqlite_schema_for_validation(invalid_path)
    invalid_storage.close()
    with sqlite3.connect(invalid_path) as conn:
        conn.execute("PRAGMA user_version=14")
    invalid = schema_status(invalid_path)
    assert invalid["state"] == "invalid"
    assert invalid["blocked"] is True


def test_version_zero_pre_v15_source_migrates_and_preserves_data(tmp_path: Path) -> None:
    db_path = tmp_path / "version-zero-pre-v15.db"
    storage = Storage._legacy_sqlite_schema_for_validation(db_path)
    try:
        storage.insert_file(
            url="https://issue-376.test/version-zero.pdf",
            sha256="version-zero-sha",
            title="Version zero source",
            source_site="issue-376.test",
            source_page_url="https://issue-376.test",
            original_filename="version-zero.pdf",
            local_path=str(tmp_path / "version-zero.pdf"),
            bytes=376,
            content_type="application/pdf",
        )
        storage._conn.execute(f"DROP INDEX {LATEST_INDEX}")
        storage._conn.execute("PRAGMA user_version=0")
        storage._conn.commit()
    finally:
        storage.close()

    status = schema_status(db_path)
    assert status["state"] == "needs_migration"
    assert status["can_apply"] is True
    assert status["blocked"] is False
    assert "add_file_chunk_sets_latest_index_v15" in {
        action["id"] for action in schema_plan(db_path)["plan"]["actions"]
    }

    applied = apply_schema(db_path)
    assert applied["state"] == "current"
    assert "add_file_chunk_sets_latest_index_v15" in applied["applied_migrations"]
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT sha256, title FROM files WHERE url = ?",
            ("https://issue-376.test/version-zero.pdf",),
        ).fetchone() == ("version-zero-sha", "Version zero source")
        assert _index_columns(conn) == LATEST_INDEX_COLUMNS

    repeated = apply_schema(db_path)
    assert repeated["state"] == "current"
    assert repeated["applied_migrations"] == []


@pytest.mark.parametrize(
    ("version", "replacement"),
    (
        (
            15,
            "CREATE INDEX renamed_latest ON file_chunk_sets("
            "file_url, profile_id, updated_at DESC, created_at DESC, chunk_set_id DESC)",
        ),
        (
            14,
            "CREATE INDEX renamed_latest ON file_chunk_sets("
            "file_url, profile_id, updated_at DESC, created_at DESC, chunk_set_id DESC)",
        ),
        (
            15,
            f"CREATE INDEX {LATEST_INDEX} ON file_chunk_sets("
            "file_url, profile_id, created_at DESC, updated_at DESC, chunk_set_id DESC)",
        ),
        (
            15,
            f"CREATE INDEX {LATEST_INDEX} ON file_chunk_sets("
            "file_url, profile_id, updated_at DESC, created_at DESC, markdown_hash DESC)",
        ),
    ),
    ids=(
        "renamed-current",
        "renamed-premature",
        "wrong-order",
        "wrong-column",
    ),
)
def test_v15_latest_index_contract_rejects_impostors(
    tmp_path: Path, version: int, replacement: str
) -> None:
    db_path = tmp_path / f"impostor-{version}.db"
    storage = Storage._legacy_sqlite_schema_for_validation(db_path)
    storage.close()
    with sqlite3.connect(db_path) as conn:
        conn.execute(f"DROP INDEX {LATEST_INDEX}")
        conn.execute(replacement)
        conn.execute(f"PRAGMA user_version={version}")

    status = schema_status(db_path)
    assert status["state"] == "invalid"
    assert status["can_apply"] is False
    assert status["blocked"] is True


def test_v15_unknown_index_remains_fail_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "unknown-index.db"
    storage = Storage._legacy_sqlite_schema_for_validation(db_path)
    storage.close()
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE INDEX issue_376_unknown ON files(title)")

    status = schema_status(db_path)
    assert status["state"] == "invalid"
    assert "schema_signature_mismatch" in status["problems"]


def test_fresh_legacy_schema_includes_latest_covering_index(tmp_path: Path) -> None:
    storage = Storage._legacy_sqlite_schema_for_validation(tmp_path / "fresh.db")
    try:
        assert int(storage._conn.execute("PRAGMA user_version").fetchone()[0]) == 16
        assert _index_columns(storage._conn) == LATEST_INDEX_COLUMNS
    finally:
        storage.close()


def test_postgresql_schema_includes_latest_covering_index(tmp_path: Path) -> None:
    storage = Storage(postgres_url_for_path(tmp_path / "latest-index.db"))
    try:
        indexdef = storage._conn.execute(
            "SELECT indexdef FROM pg_indexes "
            "WHERE schemaname = current_schema() AND indexname = ?",
            (LATEST_INDEX,),
        ).fetchone()[0]
    finally:
        storage.close()
    normalized = " ".join(str(indexdef).lower().split())
    assert (
        "(file_url, profile_id, updated_at desc, created_at desc, chunk_set_id desc)" in normalized
    )


def test_storage_latest_selectors_break_timestamp_ties_by_chunk_set_id(tmp_path: Path) -> None:
    db_path = tmp_path / "storage.db"
    _file_url, _profile_id, kb_id = _seed_tied_chunk_sets(db_path)
    storage = Storage(postgres_url_for_path(str(db_path)))
    try:
        binding = storage.list_kb_chunk_bindings(kb_id)[0]
        composition = storage.get_kb_composition_status(kb_id)
    finally:
        storage.close()
    assert binding["latest_chunk_set_id"] == "cs-z"
    assert binding["is_latest_for_profile"] is False
    assert composition["outdated_binding_count"] == 1
    assert composition["new_chunk_versions_available"] is True


def test_latest_any_status_isolated_composition_matrix(tmp_path: Path) -> None:
    db_path = tmp_path / "composition-matrix.db"
    file_url, profile_id, stale_kb = _seed_tied_chunk_sets(db_path)
    storage = Storage(postgres_url_for_path(str(db_path)))
    try:
        other_profile = storage.create_chunk_profile(
            name="issue-376-other-profile", chunk_size=256, chunk_overlap=32
        )
        other_url = "https://issue-376.test/other.pdf"
        storage.insert_file(
            url=other_url,
            sha256="other",
            title="Other",
            source_site="issue-376.test",
            source_page_url="https://issue-376.test",
            original_filename="other.pdf",
            local_path=str(db_path.with_name("other.pdf")),
            bytes=1,
            content_type="application/pdf",
        )
        later = "2026-09-14T13:00:00+00:00"
        storage._conn.executemany(
            """
            INSERT INTO file_chunk_sets (
                chunk_set_id, file_url, profile_id, markdown_hash,
                profile_config_hash, status, chunk_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    "cs-building",
                    file_url,
                    profile_id,
                    "building",
                    "cfg",
                    "building",
                    0,
                    later,
                    later,
                ),
                (
                    "cs-other-profile",
                    file_url,
                    other_profile["profile_id"],
                    "other-profile",
                    "cfg",
                    "ready",
                    9,
                    later,
                    later,
                ),
                (
                    "cs-cross-file",
                    other_url,
                    profile_id,
                    "cross-file",
                    "cfg",
                    "ready",
                    9,
                    later,
                    later,
                ),
            ),
        )
        storage._conn.executemany(
            """
            INSERT INTO rag_knowledge_bases (
                kb_id, name, embedding_model, chunk_profile_id, chunk_size,
                chunk_overlap, index_type, created_at, updated_at
            ) VALUES (?, ?, 'issue-376-model', ?, 128, 16, 'Flat', ?, ?)
            """,
            (
                ("kb-current", "Current", profile_id, later, later),
                ("kb-empty", "Empty", profile_id, later, later),
                ("kb-other", "Other KB", profile_id, later, later),
            ),
        )
        storage._conn.executemany(
            """
            INSERT INTO kb_chunk_bindings (
                kb_id, file_url, chunk_set_id, bound_at, bound_by,
                binding_mode, target_profile_id
            ) VALUES (?, ?, ?, ?, 'test', 'follow_latest', ?)
            """,
            (
                ("kb-current", file_url, "cs-building", later, profile_id),
                ("kb-other", other_url, "cs-cross-file", later, profile_id),
            ),
        )
        storage._conn.commit()
        storage.create_kb_index_version(
            kb_id=stale_kb,
            embedding_provider="openai",
            embedding_model="issue-376-model",
            embedding_dimension=1536,
            index_type="Flat",
            status="ready",
            chunk_count=1,
        )

        stale = storage.get_kb_composition_status(stale_kb)
        current = storage.get_kb_composition_status("kb-current")
        empty = storage.get_kb_composition_status("kb-empty")
        other = storage.get_kb_composition_status("kb-other")
        stale_binding = storage.list_kb_chunk_bindings(stale_kb)[0]
    finally:
        storage.close()

    assert stale_binding["latest_chunk_set_id"] == "cs-building"
    assert stale["outdated_binding_count"] == 1
    assert stale["needs_reindex"] is True
    assert stale["new_chunk_versions_available"] is True
    assert classify_kb_status(composition=stale, embedding_compatible=True)["reason"] == (
        "binding_dirty"
    )
    assert current["outdated_binding_count"] == 0
    assert other["outdated_binding_count"] == 0
    assert empty["binding_file_count"] == 0
    assert empty["outdated_binding_count"] == 0


@pytest.mark.parametrize("prepared", (False, True), ids=("fallback", "batch"))
def test_kb_list_view_latest_selectors_break_timestamp_ties(tmp_path: Path, prepared: bool) -> None:
    db_path = tmp_path / f"list-{prepared}.db"
    database_url = postgres_url_for_path(str(db_path))
    _file_url, _profile_id, kb_id = _seed_tied_chunk_sets(db_path)
    conn = PostgresConnection(database_url, read_only=True)
    conn.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
    view = _KBListStorageView(database_url, conn)
    try:
        if prepared:
            view.prepare(({"kb_id": kb_id, "manifest_profile": "general"},))
        bindings = view.list_kb_chunk_bindings(kb_id)
        composition = view.get_kb_composition_status(kb_id)
    finally:
        view.close()
    if prepared:
        assert bindings == [{"profile_id": bindings[0]["profile_id"]}]
    else:
        assert bindings[0]["latest_chunk_set_id"] == "cs-z"
        assert bindings[0]["is_latest"] is False
    assert composition["outdated_binding_count"] == 1
    assert composition["new_chunk_versions_available"] is True
