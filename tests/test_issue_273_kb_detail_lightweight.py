from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from ai_actuarial.api.services import rag_admin
from ai_actuarial.embedding_service import EmbeddingIdentity
from ai_actuarial.storage import Storage
from tests.test_issue_256_lightweight_list_apis import (
    _identity,
    _manager,
    _patch_identity,
    _seed_shared_kbs,
)


def _seed(
    db_path: Path,
    tmp_path: Path,
    identity: EmbeddingIdentity,
    *,
    kb_id: str = "kb-273",
) -> None:
    _seed_shared_kbs(
        db_path,
        tmp_path,
        identity=identity,
        kb_ids=(kb_id,),
        chunk_count=3,
        embedding_kinds=("ready", "wrong-config", "missing"),
        create_ready_index=True,
    )


def _patch_lightweight_manager(
    monkeypatch: pytest.MonkeyPatch, db_path: Path, tmp_path: Path
) -> None:
    def manager_and_storage(_path: str) -> Any:
        storage = Storage(str(db_path))
        return None, _manager(storage, tmp_path), storage

    monkeypatch.setattr(rag_admin, "_manager_and_storage", manager_and_storage)


def test_kb_detail_uses_metadata_coverage_without_deep_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "detail.db"
    identity = _identity(dimension=3)
    _seed(db_path, tmp_path, identity)
    _patch_identity(monkeypatch, identity)
    _patch_lightweight_manager(monkeypatch, db_path, tmp_path)

    def fail(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("KB detail performed a forbidden deep read")

    monkeypatch.setattr(rag_admin, "resolve_kb_bound_chunks", fail)
    monkeypatch.setattr(Storage, "read_valid_chunk_embeddings", fail)
    monkeypatch.setattr(
        "ai_actuarial.agentic_rag.ready_data_builder.get_builder_source_fingerprint",
        fail,
    )

    payload = rag_admin.get_knowledge_base(db_path=str(db_path), kb_id="kb-273")

    kb = payload["knowledge_base"]
    assert kb["index_coverage"] == {
        "bound_file_count": 1,
        "bound_chunk_count": 3,
        "ready_embeddings": 1,
        "missing_embeddings": 2,
        "invalid_bindings": 0,
        "binding_error": "",
    }
    # Ordinary detail must not eagerly compute the Ready Data build selector.
    assert kb["agentic_ready_manifest"].get("ready_build_input") is None


def test_kb_detail_deep_path_preserves_vector_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "deep.db"
    identity = _identity(dimension=3)
    _seed(db_path, tmp_path, identity)
    _patch_identity(monkeypatch, identity)
    _patch_lightweight_manager(monkeypatch, db_path, tmp_path)

    original = Storage.read_valid_chunk_embeddings
    calls: list[Any] = []

    def spy(self: Storage, chunk_ids: Any, *, identity: Any) -> dict[str, Any]:
        calls.append(list(chunk_ids))
        return original(self, chunk_ids, identity=identity)

    monkeypatch.setattr(Storage, "read_valid_chunk_embeddings", spy)

    payload = rag_admin.get_knowledge_base(
        db_path=str(db_path),
        kb_id="kb-273",
        deep=True,
    )

    assert calls, "deep=True must still invoke read_valid_chunk_embeddings"
    kb = payload["knowledge_base"]
    # Deep validation on valid data agrees with the metadata aggregate.
    assert kb["index_coverage"]["ready_embeddings"] == 1
    assert kb["index_coverage"]["missing_embeddings"] == 2


def test_manifest_endpoint_default_skips_ready_build_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "manifest.db"
    identity = _identity(dimension=3)
    _seed(db_path, tmp_path, identity)
    _patch_identity(monkeypatch, identity)
    _patch_lightweight_manager(monkeypatch, db_path, tmp_path)

    def fail(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("manifest polling computed the build selector eagerly")

    monkeypatch.setattr(
        "ai_actuarial.agentic_rag.ready_data_builder.get_builder_source_fingerprint",
        fail,
    )

    payload = rag_admin.get_agentic_ready_manifest(
        db_path=str(db_path),
        kb_id="kb-273",
        query={},
    )

    assert payload["manifest"].get("ready_build_input") is None


def test_kb_detail_build_fetches_fresh_selector_before_posting() -> None:
    source = Path("client/src/pages/KBDetail.tsx").read_text(encoding="utf-8")
    start = source.index("const handleBuildAgenticManifest")
    end = source.index("const updateReadyDataAutomation", start)
    handler = source[start:end]

    manifest_path = (
        "`/api/rag/knowledge-bases/${encodeURIComponent(mutationKbId)}"
        "/agentic-ready-manifest?include_ready_build_input=true`"
    )
    build_path = (
        "`/api/rag/knowledge-bases/${encodeURIComponent(mutationKbId)}"
        "/agentic-ready-manifest/build`"
    )
    assert manifest_path in handler
    assert build_path in handler
    assert "await apiGet" in handler
    # Detail no longer trusts a stale cached selector for the Build POST.
    assert "effectiveManifest?.ready_build_input" not in handler
    assert handler.index(manifest_path) < handler.index(build_path)


@pytest.mark.parametrize("empty", (False, True), ids=("populated", "empty"))
def test_kb_detail_coverage_uses_covering_index_hint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    empty: bool,
) -> None:
    db_path = tmp_path / "detail-index-hint.db"
    identity = _identity(dimension=3)
    _seed(db_path, tmp_path, identity, kb_id="kb-issue-407")
    _patch_identity(monkeypatch, identity)

    storage = Storage(str(db_path))
    manager = _manager(storage, tmp_path)
    kb_id = "kb-empty" if empty else "kb-issue-407"
    if empty:
        manager.create_kb(
            kb_id=kb_id,
            name=kb_id,
            kb_mode="manual",
            embedding_provider=identity.provider,
            embedding_model=identity.model,
            embedding_dimension=identity.dimension,
            embedding_identity_key=identity.embedding_identity_key,
        )
    close = storage.close
    statements: list[str] = []
    monkeypatch.setattr(manager, "get_kb_categories", lambda _kb_id: [])

    def traced_manager_and_storage(_path: str) -> Any:
        storage._conn.set_trace_callback(statements.append)
        return None, manager, storage

    monkeypatch.setattr(storage, "close", lambda: None)
    monkeypatch.setattr(rag_admin, "_manager_and_storage", traced_manager_and_storage)

    try:
        hinted = rag_admin.get_knowledge_base(db_path=str(db_path), kb_id=kb_id)
        coverage = hinted["knowledge_base"]["index_coverage"]
        if empty:
            assert coverage == {
                "bound_file_count": 0,
                "bound_chunk_count": 0,
                "ready_embeddings": 0,
                "missing_embeddings": 0,
                "invalid_bindings": 1,
                "binding_error": "KB chunk binding metadata is invalid",
            }
        else:
            assert coverage["ready_embeddings"] == 1
        hinted_sql = next(
            statement for statement in statements if "chunk_embeddings e INDEXED BY" in statement
        )
        plan = "\n".join(
            str(row[3]) for row in storage._conn.execute(f"EXPLAIN QUERY PLAN {hinted_sql}")
        )
        assert "USING COVERING INDEX idx_chunk_embeddings_stats_metadata" in plan

        # Drop after Storage initialization on this exact connection: a detail
        # request cannot recreate it through schema initialization.
        storage._conn.execute("DROP INDEX idx_chunk_embeddings_stats_metadata")
        storage._conn.commit()
        assert not rag_admin._sqlite_index_exists(storage, "idx_chunk_embeddings_stats_metadata")

        statements.clear()
        unhinted = rag_admin.get_knowledge_base(db_path=str(db_path), kb_id=kb_id)
        assert unhinted == hinted
        fallback_sql = next(
            statement for statement in statements if "JOIN chunk_embeddings" in statement
        )
        assert "INDEXED BY" not in fallback_sql
        migrations = [statement for statement in statements if "CREATE INDEX" in statement]
        assert not migrations, migrations
    finally:
        close()


@pytest.mark.parametrize(
    ("mutation", "expected_coverage"),
    (
        (
            "",
            {"ready_embeddings": 1, "missing_embeddings": 2, "invalid_bindings": 0},
        ),
        (
            "UPDATE chunk_embeddings SET embedding_identity_key = 'other-identity'",
            {"ready_embeddings": 0, "missing_embeddings": 3, "invalid_bindings": 0},
        ),
        (
            "UPDATE chunk_embeddings SET status = 'building'",
            {"ready_embeddings": 0, "missing_embeddings": 3, "invalid_bindings": 0},
        ),
        (
            "UPDATE chunk_embeddings SET dimension = dimension + 1",
            {"ready_embeddings": 0, "missing_embeddings": 3, "invalid_bindings": 0},
        ),
        (
            "UPDATE chunk_embeddings SET config_fingerprint = 'other-fingerprint'",
            {"ready_embeddings": 0, "missing_embeddings": 3, "invalid_bindings": 0},
        ),
        (
            "UPDATE chunk_embeddings SET embedding_provider = 'other-provider'",
            {"ready_embeddings": 0, "missing_embeddings": 3, "invalid_bindings": 0},
        ),
        (
            "UPDATE file_chunk_sets SET status = 'building'",
            {"ready_embeddings": 0, "missing_embeddings": 0, "invalid_bindings": 1},
        ),
    ),
)
def test_kb_detail_coverage_hint_preserves_metadata_edge_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_coverage: dict[str, int],
) -> None:
    db_path = tmp_path / "detail-index-hint-edge.db"
    identity = _identity(dimension=3)
    _seed(db_path, tmp_path, identity, kb_id="kb-issue-407")
    _patch_identity(monkeypatch, identity)
    storage = Storage(str(db_path))
    manager = _manager(storage, tmp_path)
    close = storage.close
    statements: list[str] = []
    monkeypatch.setattr(manager, "get_kb_categories", lambda _kb_id: [])

    if mutation:
        storage._conn.execute(mutation)
        storage._conn.commit()

    def traced_manager_and_storage(_path: str) -> Any:
        storage._conn.set_trace_callback(statements.append)
        return None, manager, storage

    monkeypatch.setattr(storage, "close", lambda: None)
    monkeypatch.setattr(rag_admin, "_manager_and_storage", traced_manager_and_storage)
    try:
        hinted = rag_admin.get_knowledge_base(db_path=str(db_path), kb_id="kb-issue-407")
        coverage = hinted["knowledge_base"]["index_coverage"]
        for key, expected in expected_coverage.items():
            assert coverage[key] == expected
        assert any("chunk_embeddings e INDEXED BY" in statement for statement in statements)

        storage._conn.execute("DROP INDEX idx_chunk_embeddings_stats_metadata")
        storage._conn.commit()
        assert not rag_admin._sqlite_index_exists(storage, "idx_chunk_embeddings_stats_metadata")
        statements.clear()

        assert rag_admin.get_knowledge_base(db_path=str(db_path), kb_id="kb-issue-407") == hinted
        assert not any("INDEXED BY" in statement for statement in statements)
    finally:
        close()
