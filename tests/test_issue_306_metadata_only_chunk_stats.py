from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from ai_actuarial.api.services import ops_write
from ai_actuarial.embedding_service import EmbeddingIdentity
from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.storage import Storage


def _identity(*, dimension: int = 3) -> EmbeddingIdentity:
    return EmbeddingIdentity(
        embedding_identity_key="emb-issue-306",
        provider="local",
        model="issue-306-model",
        dimension=dimension,
        config_fingerprint="issue-306-config",
        config=RAGConfig(
            embedding_provider="local",
            embedding_model="issue-306-model",
            data_dir="unused",
        ),
    )


def _add_file(
    storage: Storage,
    *,
    suffix: str,
    category: str,
    chunk_kinds: tuple[str, ...] | None,
    identity: EmbeddingIdentity,
    vector_json: str,
    chunk_set_status: str = "ready",
) -> tuple[str, list[str]]:
    file_url = f"https://issue-306.test/{suffix}.pdf"
    storage.insert_file(
        url=file_url,
        sha256=f"sha-{suffix}",
        title=suffix,
        source_site="issue-306.test",
        source_page_url="https://issue-306.test",
        original_filename=f"{suffix}.pdf",
        local_path=f"/{suffix}.pdf",
        bytes=64,
        content_type="application/pdf",
    )
    assert storage.update_file_markdown(file_url, f"# {suffix}") == (True, None)
    storage._conn.execute(
        "UPDATE catalog_items SET category = ? WHERE file_url = ?",
        (category, file_url),
    )
    if chunk_kinds is None:
        storage._conn.commit()
        return file_url, []

    profile = storage.create_chunk_profile(
        name=f"profile-{suffix}",
        chunk_size=128,
        chunk_overlap=16,
        version=suffix,
    )
    chunk_set = storage.get_or_create_file_chunk_set(
        file_url=file_url,
        profile_id=str(profile["profile_id"]),
        markdown_hash=f"md-{suffix}",
        profile_config_hash=str(profile["config_hash"]),
        status="building",
    )
    chunk_set_id = str(chunk_set["chunk_set_id"])
    storage.replace_global_chunks(
        chunk_set_id=chunk_set_id,
        chunks=[
            {
                "chunk_index": index,
                "content": f"{suffix} content {index}",
                "token_count": 3,
            }
            for index in range(len(chunk_kinds))
        ],
    )
    if chunk_set_status != "ready":
        storage._conn.execute(
            "UPDATE file_chunk_sets SET status = ? WHERE chunk_set_id = ?",
            (chunk_set_status, chunk_set_id),
        )
    chunk_ids = [f"{chunk_set_id}:{index}" for index in range(len(chunk_kinds))]
    now = storage.now()
    for chunk_id, kind in zip(chunk_ids, chunk_kinds, strict=True):
        if kind == "missing":
            continue
        provider = identity.provider
        model = identity.model
        dimension = identity.dimension
        fingerprint = identity.config_fingerprint
        status = "ready"
        body = vector_json
        if kind == "provider_mismatch":
            provider = "other-provider"
        elif kind == "model_mismatch":
            model = "other-model"
        elif kind == "dimension_mismatch":
            dimension += 1
        elif kind == "fingerprint_mismatch":
            fingerprint = "other-fingerprint"
        elif kind == "status_invalid":
            status = "failed"
        elif kind == "malformed_body":
            body = "{malformed-vector"
        elif kind != "ready":
            raise AssertionError(f"unknown chunk kind: {kind}")
        storage._conn.execute(
            """
            INSERT INTO chunk_embeddings (
                chunk_id, embedding_identity_key, embedding_provider,
                embedding_model, dimension, config_fingerprint, vector_json,
                status, created_at, updated_at, validated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk_id,
                identity.embedding_identity_key,
                provider,
                model,
                dimension,
                fingerprint,
                body,
                status,
                now,
                now,
                now,
            ),
        )
    storage._conn.commit()
    return file_url, chunk_ids


def _seed_matrix(
    db_path: Path,
    *,
    identity: EmbeddingIdentity,
    vector_json: str | None = None,
) -> dict[str, Any]:
    body = vector_json or json.dumps([0.0] * identity.dimension)
    storage = Storage(str(db_path))
    try:
        _add_file(
            storage,
            suffix="matrix",
            category="Pricing; Featured",
            chunk_kinds=(
                "ready",
                "missing",
                "status_invalid",
                "provider_mismatch",
                "model_mismatch",
                "dimension_mismatch",
                "fingerprint_mismatch",
                "malformed_body",
            ),
            identity=identity,
            vector_json=body,
        )
        _add_file(
            storage,
            suffix="without-chunks",
            category="Pricing",
            chunk_kinds=None,
            identity=identity,
            vector_json=body,
        )
        _add_file(
            storage,
            suffix="other-category",
            category="Reserving",
            chunk_kinds=("ready",),
            identity=identity,
            vector_json=body,
        )
        _add_file(
            storage,
            suffix="building",
            category="Pricing",
            chunk_kinds=("ready",),
            identity=identity,
            vector_json=body,
            chunk_set_status="building",
        )
        matrix_set_id = str(
            storage._conn.execute(
                "SELECT chunk_set_id FROM file_chunk_sets WHERE file_url = ?",
                ("https://issue-306.test/matrix.pdf",),
            ).fetchone()[0]
        )
        return {"matrix_set_id": matrix_set_id}
    finally:
        storage.close()


def _patch_identity(
    monkeypatch: pytest.MonkeyPatch,
    identity: EmbeddingIdentity,
) -> None:
    monkeypatch.setattr(
        ops_write,
        "resolve_server_embedding_identity",
        lambda _storage: identity,
    )


def test_chunk_stats_are_metadata_only_and_preserve_selection_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "stats.db"
    identity = _identity()
    _seed_matrix(db_path, identity=identity)
    _patch_identity(monkeypatch, identity)

    def fail(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("ordinary chunk stats performed a forbidden deep read")

    monkeypatch.setattr(Storage, "embedding_coverage", fail)
    monkeypatch.setattr(Storage, "list_chunks_for_embedding", fail)
    monkeypatch.setattr(Storage, "read_valid_chunk_embeddings", fail)

    pricing = ops_write.get_chunk_generation_stats(
        db_path=str(db_path),
        category="Pricing",
    )
    assert pricing == {
        "success": True,
        "order": "id_desc",
        "category": "Pricing",
        "total_with_markdown": 3,
        "total_with_chunks": 2,
        "chunks_ready": 8,
        "embeddings_ready": 2,
        "embeddings_missing": 1,
        "embeddings_invalid": 5,
        "embedding_provider": identity.provider,
        "embedding_model": identity.model,
        "embedding_dimension": identity.dimension,
        "first_without_chunks_index": 2,
    }

    unfiltered = ops_write.get_chunk_generation_stats(db_path=str(db_path))
    assert unfiltered["category"] == ""
    assert unfiltered["total_with_markdown"] == 4
    assert unfiltered["total_with_chunks"] == 3
    assert unfiltered["chunks_ready"] == 9
    assert unfiltered["embeddings_ready"] == 3
    assert unfiltered["embeddings_missing"] == 1
    assert unfiltered["embeddings_invalid"] == 5
    assert unfiltered["first_without_chunks_index"] == 3


def test_chunk_stats_use_covering_indexes_without_reading_payload_columns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "authorizer.db"
    identity = _identity()
    _seed_matrix(db_path, identity=identity)
    _patch_identity(monkeypatch, identity)

    storage = Storage(str(db_path))
    statements: list[str] = []
    reads: list[tuple[str, str]] = []

    def authorize(
        action: int,
        table: str | None,
        column: str | None,
        _database: str | None,
        _trigger: str | None,
    ) -> int:
        if action == sqlite3.SQLITE_READ:
            reads.append((str(table or ""), str(column or "")))
        return sqlite3.SQLITE_OK

    storage._conn.set_authorizer(authorize)
    storage._conn.set_trace_callback(statements.append)
    monkeypatch.setattr(storage, "close", lambda: None)
    monkeypatch.setattr(ops_write, "Storage", lambda _db_path: storage)
    try:
        result = ops_write.get_chunk_generation_stats(db_path=str(db_path), category="Pricing")
        assert result["chunks_ready"] == 8
    finally:
        storage._conn.set_authorizer(None)
        storage._conn.set_trace_callback(None)

    assert ("global_chunks", "content") not in reads
    assert ("chunk_embeddings", "vector_json") not in reads
    metadata_sql = next(
        statement
        for statement in statements
        if "LEFT JOIN chunk_embeddings" in statement and "EXPLAIN QUERY PLAN" not in statement
    )
    plan = [
        str(row[3])
        for row in storage._conn.execute(f"EXPLAIN QUERY PLAN {metadata_sql}").fetchall()
    ]
    assert any(
        "USING COVERING INDEX idx_global_chunks_stats_metadata" in detail for detail in plan
    ), plan
    assert any(
        "USING COVERING INDEX idx_chunk_embeddings_stats_metadata" in detail for detail in plan
    ), plan
    storage._conn.close()


def test_malformed_vector_body_is_metadata_ready_but_deep_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "malformed.db"
    identity = _identity()
    seeded = _seed_matrix(db_path, identity=identity)
    _patch_identity(monkeypatch, identity)

    stats = ops_write.get_chunk_generation_stats(db_path=str(db_path), category="Pricing")
    assert stats["embeddings_ready"] == 2
    assert stats["embeddings_invalid"] == 5

    storage = Storage(str(db_path))
    try:
        deep = storage.embedding_coverage(
            chunk_set_ids=[str(seeded["matrix_set_id"])],
            identity=identity.as_dict(),
        )
    finally:
        storage.close()
    assert deep["expected_count"] == 8
    assert deep["ready_count"] == 1
    assert deep["missing"] == 1
    assert deep["invalid"] == 6


def test_metadata_counts_match_deep_coverage_on_valid_vectors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "valid.db"
    identity = _identity()
    seeded = _seed_matrix(db_path, identity=identity)
    _patch_identity(monkeypatch, identity)
    storage = Storage(str(db_path))
    try:
        storage._conn.execute(
            """
            UPDATE chunk_embeddings
            SET vector_json = ?
            WHERE vector_json = '{malformed-vector'
            """,
            (json.dumps([0.0] * identity.dimension),),
        )
        storage._conn.commit()
        deep = storage.embedding_coverage(
            chunk_set_ids=[str(seeded["matrix_set_id"])],
            identity=identity.as_dict(),
        )
    finally:
        storage.close()

    stats = ops_write.get_chunk_generation_stats(db_path=str(db_path), category="Pricing")
    assert (
        stats["chunks_ready"],
        stats["embeddings_ready"],
        stats["embeddings_missing"],
        stats["embeddings_invalid"],
    ) == (
        deep["expected_count"],
        deep["ready_count"],
        deep["missing"],
        deep["invalid"],
    )


def test_stats_work_is_independent_of_vector_dimension_and_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results: list[tuple[int, int, dict[str, Any]]] = []
    for label, dimension in (("small", 3), ("large", 3_072)):
        db_path = tmp_path / f"{label}.db"
        identity = _identity(dimension=dimension)
        vector_json = json.dumps([0.0] * dimension, separators=(",", ":"))
        _seed_matrix(db_path, identity=identity, vector_json=vector_json)
        _patch_identity(monkeypatch, identity)

        storage = Storage(str(db_path))
        steps = 0

        def count_step() -> int:
            nonlocal steps
            steps += 1
            return 0

        storage._conn.set_progress_handler(count_step, 1)
        monkeypatch.setattr(storage, "close", lambda: None)
        monkeypatch.setattr(ops_write, "Storage", lambda _db_path: storage)
        result = ops_write.get_chunk_generation_stats(db_path=str(db_path), category="Pricing")
        storage._conn.set_progress_handler(None, 0)
        stored_bytes = int(
            storage._conn.execute(
                "SELECT SUM(length(CAST(vector_json AS BLOB))) FROM chunk_embeddings"
            ).fetchone()[0]
        )
        storage._conn.close()
        results.append((steps, stored_bytes, result))

    small, large = results
    assert large[1] > small[1] * 500
    assert abs(large[0] - small[0]) <= 5
    assert {key: value for key, value in large[2].items() if key != "embedding_dimension"} == {
        key: value for key, value in small[2].items() if key != "embedding_dimension"
    }


@pytest.mark.parametrize(
    ("source_version", "future_tables", "expected_migrations"),
    [
        (
            10,
            (
                "weekly_explanations",
                "weekly_snapshot_members",
                "weekly_snapshots",
                "markdown_terminal_source_state",
            ),
            [
                "add_weekly_snapshots_v11",
                "add_weekly_explanations_v12",
                "add_chunk_stats_metadata_indexes_v13",
                "add_markdown_terminal_source_state_v14",
            ],
        ),
        (
            11,
            ("weekly_explanations", "markdown_terminal_source_state"),
            [
                "add_weekly_explanations_v12",
                "add_chunk_stats_metadata_indexes_v13",
                "add_markdown_terminal_source_state_v14",
            ],
        ),
        (
            12,
            ("markdown_terminal_source_state",),
            [
                "add_chunk_stats_metadata_indexes_v13",
                "add_markdown_terminal_source_state_v14",
            ],
        ),
    ],
)
def test_schema_v13_migrates_recent_sources_without_future_indexes(
    tmp_path: Path,
    source_version: int,
    future_tables: tuple[str, ...],
    expected_migrations: list[str],
) -> None:
    from ai_actuarial.sqlite_schema import apply_schema, schema_plan, schema_status

    db_path = tmp_path / f"schema-v{source_version}.db"
    storage = Storage(str(db_path))
    storage.close()
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP INDEX idx_global_chunks_stats_metadata")
        conn.execute("DROP INDEX idx_chunk_embeddings_stats_metadata")
        for table in future_tables:
            conn.execute(f"DROP TABLE {table}")
        conn.execute(f"PRAGMA user_version={source_version}")

    status = schema_status(db_path)
    assert status["state"] == "needs_migration"
    assert [action["id"] for action in schema_plan(db_path)["plan"]["actions"]] == (
        expected_migrations
    )
    applied = apply_schema(db_path)
    assert applied["state"] == "current"
    assert applied["applied_migrations"] == expected_migrations


def test_schema_v13_migrates_version_zero_database_without_future_indexes(
    tmp_path: Path,
) -> None:
    from ai_actuarial.sqlite_schema import apply_schema, schema_status

    db_path = tmp_path / "schema-v0.db"
    storage = Storage(str(db_path))
    try:
        storage.insert_file(
            url="https://issue-306.test/preserved.pdf",
            sha256="preserved-sha",
            title="Preserved",
            source_site="issue-306.test",
            source_page_url="https://issue-306.test",
            original_filename="preserved.pdf",
            local_path="/preserved.pdf",
            bytes=64,
            content_type="application/pdf",
        )
    finally:
        storage.close()
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP INDEX idx_global_chunks_stats_metadata")
        conn.execute("DROP INDEX idx_chunk_embeddings_stats_metadata")
        conn.execute("PRAGMA user_version=0")

    status = schema_status(db_path)
    assert status["state"] == "needs_migration"
    assert status["can_apply"] is True
    assert status["blocked"] is False

    applied = apply_schema(db_path)
    assert applied["state"] == "current"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT sha256, title FROM files WHERE url = ?",
            ("https://issue-306.test/preserved.pdf",),
        ).fetchone() == ("preserved-sha", "Preserved")
        indexes = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'index'"
            ).fetchall()
        }
    assert "idx_global_chunks_stats_metadata" in indexes
    assert "idx_chunk_embeddings_stats_metadata" in indexes

    repeated = apply_schema(db_path)
    assert repeated["state"] == "current"
    assert repeated["applied_migrations"] == []


def test_schema_v13_adds_stats_covering_indexes_for_fresh_and_v12_databases(
    tmp_path: Path,
) -> None:
    from ai_actuarial.sqlite_schema import (
        CURRENT_SQLITE_SCHEMA_VERSION,
        apply_schema,
        schema_plan,
        schema_status,
    )

    assert CURRENT_SQLITE_SCHEMA_VERSION == 14
    db_path = tmp_path / "schema.db"
    storage = Storage(str(db_path))
    try:
        fresh_indexes = {
            str(row[1]) for row in storage._conn.execute("PRAGMA index_list(chunk_embeddings)")
        } | {str(row[1]) for row in storage._conn.execute("PRAGMA index_list(global_chunks)")}
    finally:
        storage.close()
    assert "idx_global_chunks_stats_metadata" in fresh_indexes
    assert "idx_chunk_embeddings_stats_metadata" in fresh_indexes

    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP INDEX IF EXISTS idx_global_chunks_stats_metadata")
        conn.execute("DROP INDEX IF EXISTS idx_chunk_embeddings_stats_metadata")
        conn.execute("DROP TABLE markdown_terminal_source_state")
        conn.execute("PRAGMA user_version=12")

    status = schema_status(db_path)
    assert status["state"] == "needs_migration"
    assert status["database"]["user_version"] == 12
    assert schema_plan(db_path)["plan"]["actions"] == [
        {
            "id": "add_chunk_stats_metadata_indexes_v13",
            "from_version": 12,
            "to_version": 13,
        },
        {
            "id": "add_markdown_terminal_source_state_v14",
            "from_version": 13,
            "to_version": 14,
        },
    ]
    applied = apply_schema(db_path)
    assert applied["state"] == "current"
    assert applied["applied_migrations"] == [
        "add_chunk_stats_metadata_indexes_v13",
        "add_markdown_terminal_source_state_v14",
    ]
    with sqlite3.connect(db_path) as conn:
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) == 14
        assert [
            str(row[2])
            for row in conn.execute("PRAGMA index_info(idx_global_chunks_stats_metadata)")
        ] == ["chunk_set_id", "chunk_id"]
        assert [
            str(row[2])
            for row in conn.execute("PRAGMA index_info(idx_chunk_embeddings_stats_metadata)")
        ] == [
            "embedding_identity_key",
            "chunk_id",
            "embedding_provider",
            "embedding_model",
            "dimension",
            "config_fingerprint",
            "status",
        ]
