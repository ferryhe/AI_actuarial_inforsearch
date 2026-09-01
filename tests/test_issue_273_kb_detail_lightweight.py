from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_actuarial.api.services import rag_admin
from ai_actuarial.embedding_service import EmbeddingIdentity
from ai_actuarial.storage import Storage
from tests.test_issue_256_lightweight_list_apis import (
    _identity,
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


def test_kb_detail_uses_metadata_coverage_without_deep_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "detail.db"
    identity = _identity(dimension=3)
    _seed(db_path, tmp_path, identity)
    _patch_identity(monkeypatch, identity)

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
