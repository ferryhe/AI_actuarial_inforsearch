from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import MagicMock, patch

import pytest

from ai_actuarial.agentic_rag.ready_data_builder import (
    build_l0,
    get_builder_source_fingerprint,
)
from ai_actuarial.api.services.rag_admin import _ready_data_artifact_digest
from ai_actuarial.api.services.ready_data_automation import (
    _default_build_candidate,
    run_ready_data_automation_once,
)
from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.rag.exceptions import KnowledgeBaseException, RAGException
from ai_actuarial.rag.indexing import IndexingPipeline
from ai_actuarial.rag.kb_index import resolve_kb_bound_chunks
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.storage import Storage


SOURCE_KIND = "catalog_chunks_snapshot"


def _create_kb(storage: Storage, kb_id: str = "kb-index-reeval") -> None:
    KnowledgeBaseManager(storage).create_kb(
        kb_id=kb_id,
        name=f"Index re-evaluation {kb_id}",
        kb_mode="manual",
        manifest_profile="general",
    )


def _source_state(storage: Storage, kb_id: str, profile: str = "general") -> dict[str, Any]:
    return storage.get_agentic_ready_source_state(kb_id=kb_id, profile=profile)


def _settle_pending(storage: Storage, kb_id: str, source_id: str = "settled") -> None:
    state = _source_state(storage, kb_id)
    storage.record_agentic_ready_source_evaluation(
        kb_id=kb_id,
        profile="general",
        evaluated_generation=int(state["pending_evaluation_generation"]),
        source_version_kind=SOURCE_KIND,
        source_version_id=source_id,
    )


def _commit_index(
    storage: Storage,
    kb_id: str,
    *,
    provider: str = "openai",
    model: str = "text-embedding-3-small",
    dimension: int | None = 1536,
    status: str = "ready",
    embedding_identity_key: str = "",
    binding_snapshot_fingerprint: str = "",
    chunk_ids: list[str] | None = None,
    chunk_count: int = 2,
) -> dict[str, Any]:
    return storage.create_kb_index_version(
        kb_id=kb_id,
        embedding_provider=provider,
        embedding_model=model,
        embedding_dimension=dimension,
        index_type="Flat",
        chunk_count=chunk_count,
        embedding_identity_key=embedding_identity_key,
        binding_snapshot_fingerprint=binding_snapshot_fingerprint,
        chunk_ids=chunk_ids,
        status=status,
        artifact_path="index.faiss",
    )


def _valid(_: str) -> dict[str, Any]:
    return {"valid": True, "errors": [], "warnings": []}


def _invalid(_: str) -> dict[str, Any]:
    return {"valid": False, "errors": ["synthetic validation failure"], "warnings": []}


def _record_publication(
    storage: Storage,
    *,
    kb_id: str,
    source_id: str,
    label: str,
    status: str = "validated",
    index_version_id: str = "idx-test",
) -> dict[str, Any]:
    output_dir = (
        Path(storage.db_path).resolve().parent
        / "agentic_ready_data"
        / "staging"
        / label
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "ready_data_manifest.json"
    manifest_path.write_text(
        f'{{"profile":"general","profile_version":"1","label":"{label}"}}',
        encoding="utf-8",
    )
    artifacts = ["ready_data_manifest.json"]
    return storage.record_agentic_ready_publication(
        kb_id=kb_id,
        index_version_id=index_version_id,
        source_version_kind=SOURCE_KIND,
        source_version_id=source_id,
        profile="general",
        profile_version="1",
        status=status,
        output_dir=str(output_dir) if status == "validated" else "",
        artifact_files=artifacts,
        doc_count=1,
        section_count=1,
        built_at="2026-08-19T00:00:00+00:00",
        artifact_digest=_ready_data_artifact_digest(str(output_dir), artifacts),
        source_db=storage.db_path,
        smoke_result={
            "contract_version": "ready-data-staging-smoke.v1",
            "status": "passed",
            "checked_at": "2026-08-19T00:00:00+00:00",
            "elapsed_ms": 1,
            "query_source": "title",
            "query": "Synthetic index re-evaluation candidate",
            "query_sha256": "a" * 64,
            "matched_doc_id": "doc-index-reevaluation",
            "matched_file_url": "https://example.com/index-reevaluation",
            "failure_reason": "",
            "catalog_doc_count": 1,
        },
        error_message="synthetic build failure" if status == "failed" else "",
    )


def _publish_active(
    storage: Storage,
    *,
    kb_id: str,
    source_id: str,
    label: str = "active",
) -> dict[str, Any]:
    publication = _record_publication(
        storage,
        kb_id=kb_id,
        source_id=source_id,
        label=label,
    )
    current = storage.get_agentic_ready_publication_state(kb_id=kb_id, profile="general")
    state = storage.publish_agentic_ready_publication(
        str(publication["publication_id"]),
        expected_active_publication_id=current["active_publication_id"],
    )
    return dict(state["active_publication"])


def _set_automation(storage: Storage, kb_id: str, *, publish: bool) -> None:
    storage.set_agentic_ready_automation(
        kb_id=kb_id,
        profile="general",
        automatic_build_enabled=True,
        automatic_publish_enabled=publish,
    )


def _fingerprint(source_id: str) -> Callable[..., dict[str, str]]:
    def load(*, db_path: str, kb_id: str, profile: str) -> dict[str, str]:
        assert db_path
        assert kb_id
        assert profile == "general"
        return {
            "source_version_kind": SOURCE_KIND,
            "source_version_id": source_id,
            "index_version_id": "idx-test",
        }

    return load


def _builder(
    calls: list[int],
    *,
    source_id: str,
    valid: bool = True,
) -> Callable[..., dict[str, Any]]:
    def build(
        *,
        db_path: str,
        kb_id: str,
        profile: str,
        index_version_id: str,
        expected_source_snapshot_fingerprint: str,
    ) -> dict[str, Any]:
        storage = Storage(db_path)
        try:
            state = _source_state(storage, kb_id, profile)
            generation = int(state["pending_evaluation_generation"])
            calls.append(generation)
            candidate = _record_publication(
                storage,
                kb_id=kb_id,
                source_id=source_id,
                label=f"candidate-{generation}-{len(calls)}",
                index_version_id=index_version_id,
            )
        finally:
            storage.close()
        return {
            "kb_id": kb_id,
            "candidate_publication": candidate,
            "publication_state": {},
            "validation": _valid("") if valid else _invalid(""),
        }

    return build


def _setup_automation(
    tmp_path: Path,
    *,
    active_source_id: str | None,
    publish: bool,
) -> tuple[str, str, dict[str, Any] | None]:
    db_path = str(tmp_path / "index.db")
    kb_id = "kb-index-reeval"
    storage = Storage(db_path)
    try:
        _create_kb(storage, kb_id)
        active = (
            _publish_active(storage, kb_id=kb_id, source_id=active_source_id)
            if active_source_id is not None
            else None
        )
        _set_automation(storage, kb_id, publish=publish)
        _commit_index(storage, kb_id)
        assert _source_state(storage, kb_id)["pending_evaluation"] is True
    finally:
        storage.close()
    return db_path, kb_id, active


def _publication_count(storage: Storage, kb_id: str) -> int:
    row = storage._conn.execute(
        "SELECT COUNT(*) FROM agentic_ready_publications WHERE kb_id = ?",
        (kb_id,),
    ).fetchone()
    return int(row[0])


def _seed_builder_source(storage: Storage, tmp_path: Path, kb_id: str) -> str:
    file_url = "https://example.com/index-reeval.pdf"
    storage.insert_file(
        url=file_url,
        sha256="sha-index-reeval",
        title="Index re-evaluation source",
        source_site="example.com",
        source_page_url="https://example.com",
        original_filename="index-reeval.pdf",
        local_path=str(tmp_path / "index-reeval.pdf"),
        bytes=100,
        content_type="application/pdf",
        published_time="2026-08-19",
    )
    storage.upsert_catalog_item(
        {
            "url": file_url,
            "sha256": "sha-index-reeval",
            "keywords": ["index", "ready-data"],
            "summary": "Builder-visible source",
            "category": "test",
        },
        pipeline_version="test-v1",
        status="ok",
    )
    now = "2026-08-19T00:00:00+00:00"
    with storage.transaction():
        storage._conn.execute(
            "INSERT INTO rag_kb_files(kb_id, file_url, added_at) VALUES (?, ?, ?)",
            (kb_id, file_url, now),
        )
        storage._conn.execute(
            """
            INSERT INTO chunk_profiles(
                profile_id, name, config_hash, config_json, chunk_size,
                chunk_overlap, splitter, tokenizer, version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("cp-test", "Test", "cfg-test", "{}", 100, 10, "semantic", "test", "1", now, now),
        )
        storage._conn.execute(
            """
            INSERT INTO file_chunk_sets(
                chunk_set_id, file_url, profile_id, markdown_hash,
                status, chunk_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'ready', 1, ?, ?)
            """,
            ("cs-test", file_url, "cp-test", "md-test", now, now),
        )
        storage._conn.execute(
            """
            INSERT INTO global_chunks(
                chunk_id, chunk_set_id, chunk_index, content,
                token_count, section_hierarchy, content_hash, created_at
            ) VALUES (?, ?, 0, ?, 3, ?, ?, ?)
            """,
            ("chunk-test", "cs-test", "Ready data content", "Section", "content-test", now),
        )
        storage._conn.execute(
            """
            INSERT INTO kb_chunk_bindings(
                kb_id, file_url, chunk_set_id, bound_at, bound_by,
                binding_mode, target_profile_id
            ) VALUES (?, ?, ?, ?, 'test', 'pin', NULL)
            """,
            (kb_id, file_url, "cs-test", now),
        )
    return file_url


def _commit_builder_index(storage: Storage, kb_id: str) -> dict[str, Any]:
    storage._conn.execute(
        "UPDATE rag_knowledge_bases SET embedding_identity_key = ? WHERE kb_id = ?",
        ("identity-test", kb_id),
    )
    storage._conn.commit()
    snapshot = resolve_kb_bound_chunks(storage, kb_id)
    return _commit_index(
        storage,
        kb_id,
        embedding_identity_key="identity-test",
        binding_snapshot_fingerprint=snapshot["binding_snapshot_fingerprint"],
        chunk_ids=["chunk-test"],
        chunk_count=1,
    )


def test_ready_index_commit_marks_transactional_neutral_event(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        record = _commit_index(storage, "kb-index-reeval")

        state = _source_state(storage, "kb-index-reeval")
        assert record["status"] == "ready"
        assert state["event_generation"] == 1
        assert state["pending_reasons"] == ["index_committed"]
        assert state["pending_severity"] == "none"
    finally:
        storage.close()


def test_embedding_tuple_change_marks_embedding_index_committed(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        _commit_index(storage, "kb-index-reeval")
        _settle_pending(storage, "kb-index-reeval")

        _commit_index(
            storage,
            "kb-index-reeval",
            provider="azure_openai",
            model="text-embedding-3-large",
            dimension=3072,
        )

        state = _source_state(storage, "kb-index-reeval")
        assert state["event_generation"] == 2
        assert state["pending_reasons"] == ["embedding_index_committed"]
    finally:
        storage.close()


def test_unchanged_embedding_tuple_uses_index_committed(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        _commit_index(storage, "kb-index-reeval")
        _settle_pending(storage, "kb-index-reeval")

        _commit_index(storage, "kb-index-reeval")

        assert _source_state(storage, "kb-index-reeval")["pending_reasons"] == [
            "index_committed"
        ]
    finally:
        storage.close()


def test_first_ready_index_uses_index_committed(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        _commit_index(storage, "kb-index-reeval", provider="cohere", model="embed-v4", dimension=1024)
        assert _source_state(storage, "kb-index-reeval")["pending_reasons"] == [
            "index_committed"
        ]
    finally:
        storage.close()


@pytest.mark.parametrize("status", ["error", "stopped"])
def test_non_ready_index_commit_does_not_mark_source_event(tmp_path: Path, status: str) -> None:
    storage = Storage(str(tmp_path / f"{status}.db"))
    try:
        _create_kb(storage)
        _commit_index(storage, "kb-index-reeval")
        _settle_pending(storage, "kb-index-reeval")
        _commit_index(storage, "kb-index-reeval", status=status)
        state = _source_state(storage, "kb-index-reeval")
        assert state["event_generation"] == 1
        assert state["pending_evaluation"] is False
    finally:
        storage.close()


@pytest.mark.parametrize("status", ["error", "stopped"])
def test_non_ready_index_preserves_last_ready_embedding_tuple(
    tmp_path: Path,
    status: str,
) -> None:
    storage = Storage(str(tmp_path / f"preserve-{status}.db"))
    try:
        _create_kb(storage)
        _commit_index(storage, "kb-index-reeval")
        _settle_pending(storage, "kb-index-reeval")
        _commit_index(storage, "kb-index-reeval", status=status)

        _commit_index(
            storage,
            "kb-index-reeval",
            provider="azure_openai",
            model="text-embedding-3-large",
            dimension=3072,
        )

        state = _source_state(storage, "kb-index-reeval")
        assert state["event_generation"] == 2
        assert state["pending_reasons"] == ["embedding_index_committed"]
    finally:
        storage.close()


def test_deleted_and_recreated_kb_treats_next_ready_index_as_first(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "recreated.db"))
    try:
        manager = KnowledgeBaseManager(
            storage,
            config=RAGConfig(data_dir=str(tmp_path / "rag-data")),
        )
        manager.create_kb(
            kb_id="kb-index-reeval",
            name="Original KB",
            kb_mode="manual",
            manifest_profile="general",
        )
        _commit_index(storage, "kb-index-reeval")

        assert manager.delete_kb("kb-index-reeval") is True
        assert storage._conn.execute(
            "SELECT 1 FROM kb_index_versions WHERE kb_id = ?",
            ("kb-index-reeval",),
        ).fetchone() is None
        assert storage._conn.execute(
            "SELECT 1 FROM kb_ready_index_state WHERE kb_id = ?",
            ("kb-index-reeval",),
        ).fetchone() is None

        manager.create_kb(
            kb_id="kb-index-reeval",
            name="Recreated KB",
            kb_mode="manual",
            manifest_profile="general",
        )
        _commit_index(
            storage,
            "kb-index-reeval",
            provider="azure_openai",
            model="text-embedding-3-large",
            dimension=3072,
        )

        state = _source_state(storage, "kb-index-reeval")
        assert state["event_generation"] == 1
        assert state["pending_reasons"] == ["index_committed"]
    finally:
        storage.close()


def test_delete_kb_rejects_outer_transaction_before_filesystem_removal(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "nested-delete.db"))
    try:
        data_dir = tmp_path / "rag-data"
        manager = KnowledgeBaseManager(storage, config=RAGConfig(data_dir=str(data_dir)))
        manager.create_kb(
            kb_id="kb-index-reeval",
            name="Nested delete KB",
            kb_mode="manual",
            manifest_profile="general",
        )
        sentinel = data_dir / "kb-index-reeval" / "index.faiss"
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_bytes(b"must survive rollback")

        with pytest.raises(RuntimeError, match="outer rollback"):
            with storage.transaction(immediate=True):
                with pytest.raises(
                    KnowledgeBaseException,
                    match="inside an active database transaction",
                ):
                    manager.delete_kb("kb-index-reeval")
                raise RuntimeError("outer rollback")

        assert manager.get_kb("kb-index-reeval") is not None
        assert sentinel.read_bytes() == b"must survive rollback"
    finally:
        storage.close()


def test_legacy_orphan_index_state_is_not_inherited_by_recreated_kb(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "legacy-orphan.db")
    storage = Storage(db_path)
    try:
        KnowledgeBaseManager(
            storage,
            config=RAGConfig(data_dir=str(tmp_path / "rag-data")),
        )
        storage._conn.execute("PRAGMA foreign_keys=OFF")
        storage._conn.execute(
            """
            INSERT INTO kb_index_versions (
                index_version_id, kb_id, embedding_provider, embedding_model,
                embedding_dimension, index_type, status, artifact_path,
                chunk_count, built_at, created_at
            ) VALUES (?, ?, ?, ?, ?, 'Flat', 'ready', '', 1, ?, ?)
            """,
            (
                "idxv-legacy-orphan",
                "kb-index-reeval",
                "openai",
                "legacy-model",
                7,
                "2020-01-01T00:00:00+00:00",
                "2020-01-01T00:00:00+00:00",
            ),
        )
        storage._conn.execute(
            """
            INSERT INTO kb_ready_index_state (
                kb_id, index_version_id, embedding_provider, embedding_model,
                embedding_dimension, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "kb-index-reeval",
                "idxv-legacy-orphan",
                "openai",
                "legacy-model",
                7,
                "2020-01-01T00:00:00+00:00",
            ),
        )
        storage._conn.commit()
        storage._conn.execute("PRAGMA foreign_keys=ON")
    finally:
        storage.close()

    storage = Storage(db_path)
    try:
        assert storage._conn.execute(
            "SELECT 1 FROM kb_ready_index_state WHERE kb_id = ?",
            ("kb-index-reeval",),
        ).fetchone() is not None
        assert storage._conn.execute(
            "SELECT 1 FROM kb_index_versions WHERE kb_id = ?",
            ("kb-index-reeval",),
        ).fetchone() is not None
        manager = KnowledgeBaseManager(
            storage,
            config=RAGConfig(data_dir=str(tmp_path / "rag-data")),
        )
        manager.create_kb(
            kb_id="kb-index-reeval",
            name="Recreated legacy KB",
            kb_mode="manual",
            manifest_profile="general",
        )
        assert storage._conn.execute(
            "SELECT 1 FROM kb_ready_index_state WHERE kb_id = ?",
            ("kb-index-reeval",),
        ).fetchone() is None
        assert storage._conn.execute(
            "SELECT 1 FROM kb_index_versions WHERE kb_id = ?",
            ("kb-index-reeval",),
        ).fetchone() is None
    finally:
        storage.close()

    storage = Storage(db_path)
    try:
        assert storage._conn.execute(
            "SELECT 1 FROM kb_ready_index_state WHERE kb_id = ?",
            ("kb-index-reeval",),
        ).fetchone() is None
        assert storage._conn.execute(
            "SELECT 1 FROM kb_index_versions WHERE kb_id = ?",
            ("kb-index-reeval",),
        ).fetchone() is None
        _commit_index(
            storage,
            "kb-index-reeval",
            provider="azure_openai",
            model="text-embedding-3-large",
            dimension=3072,
        )
        assert _source_state(storage, "kb-index-reeval")["pending_reasons"] == [
            "index_committed"
        ]
    finally:
        storage.close()


def test_ready_index_commit_advances_each_known_profile_once(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        for profile in ("general", "regulation", "formula"):
            storage.set_agentic_ready_automation(
                kb_id="kb-index-reeval",
                profile=profile,
                automatic_build_enabled=False,
                automatic_publish_enabled=False,
            )

        _commit_index(storage, "kb-index-reeval")

        assert [
            _source_state(storage, "kb-index-reeval", profile)["event_generation"]
            for profile in ("general", "regulation", "formula")
        ] == [1, 1, 1]
    finally:
        storage.close()


def test_marker_failure_rolls_back_index_version_update(tmp_path: Path, monkeypatch) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        previous = _commit_index(storage, "kb-index-reeval")
        storage.set_agentic_ready_automation(
            kb_id="kb-index-reeval",
            profile="regulation",
            automatic_build_enabled=False,
            automatic_publish_enabled=False,
        )
        original_marker = storage.mark_agentic_ready_source_event
        marker_calls = 0

        def fail_second_profile(
            *, kb_id: str, profile: str = "general", reason: str
        ) -> dict[str, Any]:
            nonlocal marker_calls
            marker_calls += 1
            if marker_calls == 2:
                raise RuntimeError(f"marker failed for {kb_id}/{profile}: {reason}")
            return original_marker(kb_id=kb_id, profile=profile, reason=reason)

        monkeypatch.setattr(storage, "mark_agentic_ready_source_event", fail_second_profile)
        with pytest.raises(RuntimeError, match="marker failed"):
            _commit_index(storage, "kb-index-reeval", model="changed", dimension=7)

        row = storage._conn.execute(
            "SELECT index_version_id, embedding_model FROM kb_index_versions WHERE kb_id = ?",
            ("kb-index-reeval",),
        ).fetchone()
        assert tuple(row) == (previous["index_version_id"], previous["embedding_model"])
        ready_state = storage._conn.execute(
            "SELECT index_version_id, embedding_model FROM kb_ready_index_state WHERE kb_id = ?",
            ("kb-index-reeval",),
        ).fetchone()
        assert tuple(ready_state) == (
            previous["index_version_id"],
            previous["embedding_model"],
        )
        assert _source_state(storage, "kb-index-reeval")["event_generation"] == 1
        assert _source_state(storage, "kb-index-reeval", "regulation")[
            "event_generation"
        ] == 0
    finally:
        storage.close()


def test_ready_index_record_failure_fails_indexing_pipeline_without_removing_artifact(
    tmp_path: Path,
) -> None:
    kb_id = "kb-index-version-failure"
    storage = SimpleNamespace(
        create_kb_index_version=MagicMock(side_effect=RuntimeError("marker failed"))
    )
    embedding_generator = MagicMock()
    embedding_generator.get_embedding_dimension.return_value = 3
    kb = SimpleNamespace(
        name="Versioned KB",
        index_type="Flat",
        chunk_count=4,
    )
    manager = SimpleNamespace(
        storage=storage,
        config=SimpleNamespace(data_dir=str(tmp_path)),
        chunker=object(),
        embedding_generator=embedding_generator,
        get_current_embedding_metadata=MagicMock(
            return_value={"provider": "openai", "model": "embedding", "dimension": 3}
        ),
        sync_kb_embedding_metadata=MagicMock(),
        get_kb=MagicMock(return_value=kb),
    )
    index_path = tmp_path / kb_id / "index.faiss"

    with patch("ai_actuarial.rag.indexing.VectorStore") as vector_store_cls, patch.object(
        IndexingPipeline,
        "_index_single_file",
        return_value={"success": True, "chunk_count": 4},
    ), patch.object(IndexingPipeline, "_update_kb_stats"):
        vector_store_cls.return_value.save_index.side_effect = lambda: (
            index_path.parent.mkdir(parents=True, exist_ok=True),
            index_path.write_bytes(b"safe artifact"),
        )
        with pytest.raises(RAGException, match="record ready KB index version"):
            IndexingPipeline(manager).index_files(kb_id, ["file-1"], force_reindex=True)

    assert index_path.read_bytes() == b"safe artifact"


def test_ready_index_record_failure_marks_native_task_error_and_keeps_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from ai_actuarial.task_runtime import NativeTaskRuntime

    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "runtime.db"
    config_path = tmp_path / "sites.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {(tmp_path / 'files').as_posix()}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    kb_id = "kb-runtime-index-version-failure"
    index_path = tmp_path / "rag-data" / kb_id / "index.faiss"
    kb = SimpleNamespace(
        name="Runtime Versioned KB",
    )
    manager = SimpleNamespace(
        config=SimpleNamespace(data_dir=str(tmp_path / "rag-data")),
        get_kb=MagicMock(return_value=kb),
    )
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_bytes(b"safe runtime artifact")
    runtime = NativeTaskRuntime()
    task_id = "task-ready-index-marker-failure"
    runtime.active_tasks[task_id] = {
        "id": task_id,
        "name": "Ready index marker failure",
        "type": "rag_indexing",
        "status": "pending",
        "errors": [],
    }

    with patch(
        "ai_actuarial.task_runtime.KnowledgeBaseManager",
        return_value=manager,
    ), patch(
        "ai_actuarial.task_runtime.resolve_kb_bound_chunks",
        return_value={"binding_snapshot_fingerprint": "binding-runtime"},
    ), patch(
        "ai_actuarial.task_runtime.build_kb_index",
        side_effect=RuntimeError("build_failure: transactional source marker failed"),
    ):
        runtime._execute_collection_task(
            task_id,
            "rag_indexing",
            {
                "contract_version": 1,
                "kb_id": kb_id,
                "expected_binding_snapshot_fingerprint": "binding-runtime",
                "embedding_identity_key": "identity-runtime",
                "force_rebuild": True,
            },
        )

    assert task_id not in runtime.active_tasks
    task = runtime.task_history[-1]
    assert task["id"] == task_id
    assert task["status"] == "error"
    assert any("build_failure" in error for error in task["errors"])
    assert index_path.read_bytes() == b"safe runtime artifact"


def test_automation_disabled_keeps_pending_evaluation_and_does_not_build(tmp_path: Path) -> None:
    db_path = str(tmp_path / "index.db")
    storage = Storage(db_path)
    calls: list[int] = []
    try:
        _create_kb(storage)
        _commit_index(storage, "kb-index-reeval")
    finally:
        storage.close()

    result = run_ready_data_automation_once(
        db_path,
        build_candidate=_builder(calls, source_id="new-source"),
        source_fingerprint=_fingerprint("new-source"),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    storage = Storage(db_path)
    try:
        assert result["status"] == "idle"
        assert calls == []
        assert _source_state(storage, "kb-index-reeval")["pending_evaluation"] is True
    finally:
        storage.close()


def test_matching_healthy_active_settles_up_to_date_without_builder(tmp_path: Path) -> None:
    db_path, kb_id, active = _setup_automation(
        tmp_path,
        active_source_id="same-source",
        publish=True,
    )
    calls: list[int] = []
    storage = Storage(db_path)
    try:
        storage._conn.execute(
            "UPDATE agentic_ready_publications SET index_version_id = ? WHERE publication_id = ?",
            ("idx-observed-at-build", active["publication_id"]),
        )
        storage._conn.commit()
    finally:
        storage.close()

    result = run_ready_data_automation_once(
        db_path,
        build_candidate=_builder(calls, source_id="unused"),
        source_fingerprint=_fingerprint("same-source"),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    storage = Storage(db_path)
    try:
        state = storage.get_agentic_ready_publication_state(kb_id=kb_id, profile="general")
        assert result["status"] == "up_to_date"
        assert calls == []
        assert state["active_publication_id"] == active["publication_id"]
        assert state["active_publication"]["index_version_id"] == "idx-observed-at-build"
        assert state["previous_publication_id"] is None
        assert _source_state(storage, kb_id)["pending_evaluation"] is False
        assert _publication_count(storage, kb_id) == 1
    finally:
        storage.close()


@pytest.mark.parametrize(
    ("active_source_id", "publish", "expected_status"),
    [("old-source", False, "awaiting_publish"), ("old-source", True, "published")],
)
def test_changed_fingerprint_preserves_build_only_and_auto_publish_behavior(
    tmp_path: Path,
    active_source_id: str,
    publish: bool,
    expected_status: str,
) -> None:
    db_path, kb_id, _ = _setup_automation(
        tmp_path,
        active_source_id=active_source_id,
        publish=publish,
    )
    calls: list[int] = []

    first = run_ready_data_automation_once(
        db_path,
        build_candidate=_builder(calls, source_id="new-source"),
        source_fingerprint=_fingerprint("new-source"),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )
    second = run_ready_data_automation_once(
        db_path,
        build_candidate=_builder(calls, source_id="new-source"),
        source_fingerprint=_fingerprint("new-source"),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    assert first["status"] == expected_status
    assert second["status"] == "idle"
    assert calls and len(calls) == 1
    if publish:
        storage = Storage(db_path)
        try:
            assert _source_state(storage, kb_id)["pending_evaluation"] is False
        finally:
            storage.close()


def test_metadata_change_coalesced_with_index_event_builds_latest_generation_once(
    tmp_path: Path,
) -> None:
    db_path = str(tmp_path / "index.db")
    kb_id = "kb-index-reeval"
    storage = Storage(db_path)
    try:
        _create_kb(storage, kb_id)
        file_url = _seed_builder_source(storage, tmp_path, kb_id)
        _commit_builder_index(storage, kb_id)
        initial_fingerprint = get_builder_source_fingerprint(
            db_path=db_path,
            kb_id=kb_id,
        )
        _publish_active(
            storage,
            kb_id=kb_id,
            source_id=initial_fingerprint["source_version_id"],
        )
        _set_automation(storage, kb_id, publish=True)

        updated, error = storage.update_file_metadata(
            file_url,
            summary="Builder-visible source changed after publication",
        )
        assert updated is True
        assert error is None
        changed_fingerprint = get_builder_source_fingerprint(
            db_path=db_path,
            kb_id=kb_id,
        )
        assert changed_fingerprint != initial_fingerprint

        _commit_builder_index(storage, kb_id)
        pending = _source_state(storage, kb_id)
        assert set(pending["pending_reasons"]) == {
            "index_committed",
            "metadata_updated",
        }
        latest_generation = pending["event_generation"]
    finally:
        storage.close()
    calls: list[int] = []

    def tracked_build(
        *,
        db_path: str,
        kb_id: str,
        profile: str,
        index_version_id: str,
        expected_source_snapshot_fingerprint: str,
    ) -> dict[str, Any]:
        current = Storage(db_path)
        try:
            calls.append(
                int(
                    _source_state(current, kb_id, profile)[
                        "pending_evaluation_generation"
                    ]
                )
            )
        finally:
            current.close()
        return _default_build_candidate(
            db_path=db_path,
            kb_id=kb_id,
            profile=profile,
            index_version_id=index_version_id,
            expected_source_snapshot_fingerprint=(
                expected_source_snapshot_fingerprint
            ),
        )

    first = run_ready_data_automation_once(
        db_path,
        build_candidate=tracked_build,
        source_fingerprint=get_builder_source_fingerprint,
        validator=_valid,
        heartbeat_interval_seconds=0,
    )
    second = run_ready_data_automation_once(
        db_path,
        build_candidate=tracked_build,
        source_fingerprint=get_builder_source_fingerprint,
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    assert first["status"] == "published"
    assert second["status"] == "idle"
    assert calls == [latest_generation]


def test_corrupt_matching_active_does_not_take_up_to_date_fast_path(tmp_path: Path) -> None:
    db_path, _, active = _setup_automation(
        tmp_path,
        active_source_id="same-source",
        publish=False,
    )
    Path(str(active["output_dir"]), "ready_data_manifest.json").unlink()
    calls: list[int] = []

    result = run_ready_data_automation_once(
        db_path,
        build_candidate=_builder(calls, source_id="same-source"),
        source_fingerprint=_fingerprint("same-source"),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    assert result["status"] == "awaiting_publish"
    assert len(calls) == 1


def test_non_active_slot_record_does_not_take_up_to_date_fast_path(tmp_path: Path) -> None:
    db_path, _, active = _setup_automation(
        tmp_path,
        active_source_id="same-source",
        publish=False,
    )
    storage = Storage(db_path)
    try:
        storage._conn.execute(
            "UPDATE agentic_ready_publications SET status = 'validated' WHERE publication_id = ?",
            (active["publication_id"],),
        )
        storage._conn.commit()
    finally:
        storage.close()
    calls: list[int] = []

    result = run_ready_data_automation_once(
        db_path,
        build_candidate=_builder(calls, source_id="same-source"),
        source_fingerprint=_fingerprint("same-source"),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    assert result["status"] == "awaiting_publish"
    assert len(calls) == 1


@pytest.mark.parametrize("active_mode", ["none", "non_comparable", "legacy"])
def test_missing_or_non_comparable_active_enters_existing_build_flow(
    tmp_path: Path,
    active_mode: str,
) -> None:
    active_source = None if active_mode == "none" else "legacy-source"
    db_path, kb_id, active = _setup_automation(
        tmp_path,
        active_source_id=active_source,
        publish=False,
    )
    if active_mode == "non_comparable":
        storage = Storage(db_path)
        try:
            storage._conn.execute(
                "UPDATE agentic_ready_publications SET source_version_kind = '', source_version_id = '' WHERE publication_id = ?",
                (active["publication_id"],),
            )
            storage._conn.commit()
        finally:
            storage.close()
    elif active_mode == "legacy":
        storage = Storage(db_path)
        try:
            storage._conn.execute(
                "UPDATE agentic_ready_publications SET source_version_kind = 'legacy_artifact' WHERE publication_id = ?",
                (active["publication_id"],),
            )
            storage._conn.commit()
        finally:
            storage.close()
    calls: list[int] = []

    result = run_ready_data_automation_once(
        db_path,
        build_candidate=_builder(calls, source_id="current-source"),
        source_fingerprint=_fingerprint("current-source"),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    assert result["status"] == "awaiting_publish"
    assert len(calls) == 1
    assert kb_id


def test_fingerprint_matches_build_identity_and_writes_no_artifacts(tmp_path: Path) -> None:
    db_path = str(tmp_path / "source.db")
    storage = Storage(db_path)
    try:
        _create_kb(storage)
        _seed_builder_source(storage, tmp_path, "kb-index-reeval")
        committed = _commit_builder_index(storage, "kb-index-reeval")
    finally:
        storage.close()
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}

    fingerprint = get_builder_source_fingerprint(db_path=db_path, kb_id="kb-index-reeval")

    after_fingerprint = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}
    created_by_fingerprint = after_fingerprint - before
    output_dir = tmp_path / "manual-build"
    manifest = build_l0(
        db_path=db_path,
        output_dir=str(output_dir),
        profile="general",
        kb_id="kb-index-reeval",
        index_version_id=str(committed["index_version_id"]),
        expected_source_snapshot_fingerprint=str(
            fingerprint["source_snapshot_fingerprint"]
        ),
    )
    assert {path.name for path in created_by_fingerprint} <= {"source.db-wal", "source.db-shm"}
    assert not any((tmp_path / path).is_dir() for path in created_by_fingerprint)
    assert fingerprint["source_version_kind"] == manifest["source_version_kind"]
    assert fingerprint["source_version_id"] == manifest["source_version_id"]
    assert fingerprint["source_snapshot_fingerprint"] == manifest["source_version_id"]
    assert fingerprint["index_version_id"] == committed["index_version_id"]
    assert manifest["index_version_id"] == committed["index_version_id"]
    assert output_dir.is_dir()


@pytest.mark.parametrize(
    "race",
    ["generation", "claim", "lease", "flags", "expected_active"],
)
def test_prebuild_races_fail_closed_without_starting_builder(tmp_path: Path, race: str) -> None:
    db_path, kb_id, _ = _setup_automation(
        tmp_path,
        active_source_id="old-source",
        publish=True,
    )
    calls: list[int] = []

    def race_fingerprint(
        *, db_path: str, kb_id: str, profile: str
    ) -> dict[str, str]:
        assert profile == "general"
        storage = Storage(db_path)
        try:
            if race == "generation":
                storage.mark_agentic_ready_source_event(
                    kb_id=kb_id, profile="general", reason="metadata_updated"
                )
            elif race == "claim":
                storage._conn.execute(
                    "UPDATE agentic_ready_automation SET claim_token = 'stolen' WHERE kb_id = ?",
                    (kb_id,),
                )
                storage._conn.commit()
            elif race == "lease":
                expired = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
                storage._conn.execute(
                    "UPDATE agentic_ready_automation SET lease_expires_at = ? WHERE kb_id = ?",
                    (expired, kb_id),
                )
                storage._conn.execute(
                    "UPDATE agentic_ready_automation_lock SET lease_expires_at = ? WHERE lock_name = 'global'",
                    (expired,),
                )
                storage._conn.commit()
            elif race == "flags":
                storage.set_agentic_ready_automation(
                    kb_id=kb_id,
                    profile="general",
                    automatic_build_enabled=False,
                    automatic_publish_enabled=False,
                )
            else:
                _publish_active(
                    storage,
                    kb_id=kb_id,
                    source_id="racing-source",
                    label="racing-active",
                )
        finally:
            storage.close()
        return {
            "source_version_kind": SOURCE_KIND,
            "source_version_id": "new-source",
            "index_version_id": "idx-test",
        }

    result = run_ready_data_automation_once(
        db_path,
        build_candidate=_builder(calls, source_id="new-source"),
        source_fingerprint=race_fingerprint,
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    assert result["status"] in {"superseded", "claim_lost", "failed", "pending"}
    assert calls == []
    storage = Storage(db_path)
    try:
        assert _source_state(storage, kb_id)["pending_evaluation"] is True
    finally:
        storage.close()


def test_fingerprint_failure_records_automation_failure_without_slot_changes(tmp_path: Path) -> None:
    db_path, kb_id, active = _setup_automation(
        tmp_path,
        active_source_id="active-source",
        publish=True,
    )

    def fail_fingerprint(
        *, db_path: str, kb_id: str, profile: str
    ) -> dict[str, str]:
        assert profile == "general"
        raise RuntimeError(f"fingerprint failed for {kb_id} in {db_path}")

    result = run_ready_data_automation_once(
        db_path,
        source_fingerprint=fail_fingerprint,
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    storage = Storage(db_path)
    try:
        state = storage.get_agentic_ready_publication_state(kb_id=kb_id, profile="general")
        automation = storage.get_agentic_ready_automation_state(kb_id=kb_id, profile="general")
        assert result["status"] == "failed"
        assert state["active_publication_id"] == active["publication_id"]
        assert state["previous_publication_id"] is None
        assert "fingerprint failed" in automation["last_error"]
        assert _source_state(storage, kb_id)["pending_evaluation"] is True
    finally:
        storage.close()


def test_validation_failure_does_not_change_active_or_previous(tmp_path: Path) -> None:
    db_path, kb_id, active = _setup_automation(
        tmp_path,
        active_source_id="same-source",
        publish=True,
    )
    calls: list[int] = []

    result = run_ready_data_automation_once(
        db_path,
        build_candidate=_builder(calls, source_id="same-source", valid=False),
        source_fingerprint=_fingerprint("same-source"),
        validator=_invalid,
        heartbeat_interval_seconds=0,
    )

    storage = Storage(db_path)
    try:
        state = storage.get_agentic_ready_publication_state(kb_id=kb_id, profile="general")
        assert result["status"] == "failed"
        assert calls
        assert state["active_publication_id"] == active["publication_id"]
        assert state["previous_publication_id"] is None
        assert _source_state(storage, kb_id)["pending_evaluation"] is True
    finally:
        storage.close()


def test_repeated_same_index_profile_reevaluation_creates_no_publication(tmp_path: Path) -> None:
    db_path, kb_id, active = _setup_automation(
        tmp_path,
        active_source_id="same-source",
        publish=True,
    )
    calls: list[int] = []

    first = run_ready_data_automation_once(
        db_path,
        build_candidate=_builder(calls, source_id="unused"),
        source_fingerprint=_fingerprint("same-source"),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )
    storage = Storage(db_path)
    try:
        _commit_index(storage, kb_id)
    finally:
        storage.close()
    second = run_ready_data_automation_once(
        db_path,
        build_candidate=_builder(calls, source_id="unused"),
        source_fingerprint=_fingerprint("same-source"),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    storage = Storage(db_path)
    try:
        assert first["status"] == second["status"] == "up_to_date"
        assert calls == []
        assert _publication_count(storage, kb_id) == 1
        assert storage.get_agentic_ready_publication_state(
            kb_id=kb_id, profile="general"
        )["active_publication_id"] == active["publication_id"]
    finally:
        storage.close()
