from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from ai_actuarial.embedding_service import EmbeddingIdentity
from ai_actuarial.collectors.base import CollectionResult
from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.rag.kb_index import (
    KBIndexContractError,
    build_kb_index,
    resolve_kb_bound_chunks,
)
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.storage import Storage
from ai_actuarial.task_runtime import NativeTaskRuntime


def _identity() -> EmbeddingIdentity:
    return EmbeddingIdentity(
        embedding_identity_key="emb_test_identity",
        provider="local",
        model="test-embedding",
        dimension=3,
        config_fingerprint="test-config",
        config=RAGConfig(
            embedding_provider="local",
            embedding_model="test-embedding",
            data_dir="unused",
        ),
    )


def _seed_bound_kb(
    storage: Storage,
    *,
    tmp_path: Path,
    kb_id: str = "kb-238",
    chunk_count: int = 3,
    persist_embeddings: bool = True,
) -> tuple[KnowledgeBaseManager, dict, EmbeddingIdentity]:
    file_url = "https://example.test/issue-238.pdf"
    storage.insert_file(
        file_url,
        "file-hash",
        "Issue 238",
        "test",
        None,
        "issue-238.pdf",
        "issue-238.pdf",
        10,
        "application/pdf",
    )
    storage.update_file_markdown(file_url, "# Legacy markdown must not be read", "manual")
    storage._conn.execute(
        "UPDATE catalog_items SET status = 'ok', category = 'Test' WHERE file_url = ?",
        (file_url,),
    )
    profile = storage.create_chunk_profile(
        name=f"profile-{kb_id}",
        chunk_size=100,
        chunk_overlap=10,
        splitter="semantic",
        tokenizer="cl100k_base",
        version="v1",
    )
    chunk_set = storage.get_or_create_file_chunk_set(
        file_url=file_url,
        profile_id=str(profile["profile_id"]),
        markdown_hash="markdown-v1",
        profile_config_hash=str(profile["config_hash"]),
    )
    storage.replace_global_chunks(
        chunk_set_id=str(chunk_set["chunk_set_id"]),
        chunks=[
            {
                "chunk_index": index,
                "content": f"persisted chunk {index}",
                "token_count": 3,
                "section_hierarchy": "Issue 238",
            }
            for index in range(chunk_count)
        ],
    )
    manager = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    manager.storage = storage
    manager.config = RAGConfig(
        embedding_provider="local",
        embedding_model="test-embedding",
        data_dir=str(tmp_path / "rag"),
    )
    manager.embedding_generator = None
    manager._ensure_rag_tables()
    identity = _identity()
    manager.create_kb(
        kb_id=kb_id,
        name="Issue 238",
        kb_mode="manual",
        chunk_profile_id=str(profile["profile_id"]),
        embedding_provider=identity.provider,
        embedding_model=identity.model,
        embedding_dimension=identity.dimension,
        embedding_identity_key=identity.embedding_identity_key,
    )
    manager.add_files_to_kb(kb_id, [file_url])
    storage.bind_chunk_set_to_kb(
        kb_id=kb_id,
        file_url=file_url,
        chunk_set_id=str(chunk_set["chunk_set_id"]),
        binding_mode="pin",
    )
    chunks = storage.list_chunks_for_embedding([str(chunk_set["chunk_set_id"])])
    if persist_embeddings:
        storage.batch_upsert_chunk_embeddings(
            [
                {
                    "chunk_id": chunk["chunk_id"],
                    "vector": [float(index + 1), 0.5, -0.5],
                }
                for index, chunk in enumerate(chunks)
            ],
            identity=identity.as_dict(),
        )
    storage._conn.commit()
    return manager, chunk_set, identity


def test_create_kb_defaults_to_current_server_embedding_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = Storage(str(tmp_path / "identity.db"))
    try:
        manager = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
        manager.storage = storage
        manager.config = RAGConfig(
            embedding_provider="local",
            embedding_model="test-embedding",
            data_dir=str(tmp_path / "rag"),
        )
        manager.embedding_generator = None
        manager._ensure_rag_tables()
        identity = _identity()
        monkeypatch.setattr(
            "ai_actuarial.rag.knowledge_base.resolve_server_embedding_identity",
            lambda _storage: identity,
            raising=False,
        )

        created = manager.create_kb(
            kb_id="kb-default-identity",
            name="Default Identity",
            kb_mode="manual",
        )

        assert created.embedding_identity_key == identity.embedding_identity_key
        assert created.embedding_provider == identity.provider
        assert created.embedding_model == identity.model
        assert created.embedding_dimension == identity.dimension
        runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
        runtime._ready_data_db_path = storage.db_path
        runtime._load_site_config = lambda: {}
        monkeypatch.setattr(
            "ai_actuarial.task_runtime.resolve_kb_bound_chunks",
            lambda _storage, _kb_id: {
                "binding_snapshot_fingerprint": "bind-default-identity"
            },
        )
        payload = runtime._pipeline_kb_index_input("kb-default-identity")
        assert payload["embedding_identity_key"] == identity.embedding_identity_key
    finally:
        storage.close()


def test_binding_resolver_is_deterministic_complete_and_read_only(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _manager, _chunk_set, _identity_value = _seed_bound_kb(storage, tmp_path=tmp_path)
        before = storage._conn.total_changes
        first = resolve_kb_bound_chunks(storage, "kb-238")
        second = resolve_kb_bound_chunks(storage, "kb-238")

        assert first["contract_version"] == 1
        assert first["binding_snapshot_fingerprint"] == second["binding_snapshot_fingerprint"]
        assert first["bound_file_count"] == 1
        assert first["bound_chunk_set_count"] == 1
        assert first["bound_chunk_count"] == 3
        assert [row["chunk_index"] for row in first["chunks"]] == [0, 1, 2]
        assert storage._conn.total_changes == before
    finally:
        storage.close()


def test_binding_resolver_rejects_partial_binding_and_partial_file_selector(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        manager, _chunk_set, _identity_value = _seed_bound_kb(storage, tmp_path=tmp_path)
        second_url = "https://example.test/unbound.pdf"
        storage.insert_file(
            second_url,
            "second-hash",
            "Unbound",
            "test",
            None,
            "unbound.pdf",
            "unbound.pdf",
            10,
            "application/pdf",
        )
        manager.add_files_to_kb("kb-238", [second_url])

        with pytest.raises(KBIndexContractError) as partial:
            resolve_kb_bound_chunks(storage, "kb-238")
        assert partial.value.code == "invalid_selector"

        manager.remove_files_from_kb("kb-238", [second_url])
        with pytest.raises(KBIndexContractError) as subset:
            resolve_kb_bound_chunks(storage, "kb-238", file_urls=[])
        assert subset.value.code == "invalid_selector"
    finally:
        storage.close()


def test_kb_index_uses_persisted_embeddings_and_commits_ordinal_mapping(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        manager, _chunk_set, identity = _seed_bound_kb(
            storage,
            tmp_path=tmp_path,
            chunk_count=65,
        )
        snapshot = resolve_kb_bound_chunks(storage, "kb-238")

        class MustNotGenerate:
            def generate_embeddings(self, _texts):  # pragma: no cover - failure path
                raise AssertionError("valid persisted embeddings must be reused")

        result = build_kb_index(
            storage=storage,
            kb_id="kb-238",
            expected_binding_snapshot_fingerprint=snapshot["binding_snapshot_fingerprint"],
            embedding_identity_key=identity.embedding_identity_key,
            identity=identity,
            generator=MustNotGenerate(),
            config=manager.config,
        )

        assert result == {
            "contract_version": 1,
            "index_version_id": result["index_version_id"],
            "binding_snapshot_fingerprint": snapshot["binding_snapshot_fingerprint"],
            "embedding_identity_key": identity.embedding_identity_key,
            "chunk_count": 65,
            "vector_dimension": 3,
            "artifact_digest": result["artifact_digest"],
        }
        rows = storage._conn.execute(
            """
            SELECT vector_ordinal, chunk_id
            FROM kb_index_items
            WHERE index_version_id = ?
            ORDER BY vector_ordinal
            """,
            (result["index_version_id"],),
        ).fetchall()
        assert len(rows) == 65
        assert [row[0] for row in rows] == list(range(65))
        ready = storage._conn.execute(
            "SELECT index_version_id, artifact_digest FROM kb_ready_index_state WHERE kb_id = ?",
            ("kb-238",),
        ).fetchone()
        assert ready == (result["index_version_id"], result["artifact_digest"])
        assert Path(
            storage._conn.execute(
                "SELECT artifact_path FROM kb_index_versions WHERE index_version_id = ?",
                (result["index_version_id"],),
            ).fetchone()[0]
        ).is_file()
    finally:
        storage.close()


def test_stale_snapshot_and_stop_preserve_previous_ready_pointer(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        manager, _chunk_set, identity = _seed_bound_kb(storage, tmp_path=tmp_path)
        snapshot = resolve_kb_bound_chunks(storage, "kb-238")
        first = build_kb_index(
            storage=storage,
            kb_id="kb-238",
            expected_binding_snapshot_fingerprint=snapshot["binding_snapshot_fingerprint"],
            embedding_identity_key=identity.embedding_identity_key,
            identity=identity,
            config=manager.config,
        )

        with pytest.raises(KBIndexContractError) as stale:
            build_kb_index(
                storage=storage,
                kb_id="kb-238",
                expected_binding_snapshot_fingerprint="bind_stale",
                embedding_identity_key=identity.embedding_identity_key,
                identity=identity,
                config=manager.config,
            )
        assert stale.value.code == "stale_snapshot"

        with pytest.raises(KBIndexContractError) as stopped:
            build_kb_index(
                storage=storage,
                kb_id="kb-238",
                expected_binding_snapshot_fingerprint=snapshot["binding_snapshot_fingerprint"],
                embedding_identity_key=identity.embedding_identity_key,
                identity=identity,
                config=manager.config,
                stop_check=lambda: True,
            )
        assert stopped.value.code == "build_failure"
        assert storage._conn.execute(
            "SELECT index_version_id FROM kb_ready_index_state WHERE kb_id = ?",
            ("kb-238",),
        ).fetchone()[0] == first["index_version_id"]
    finally:
        storage.close()


def test_cleanup_retains_removed_file_chunks_referenced_by_immutable_index(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        manager, chunk_set, identity = _seed_bound_kb(storage, tmp_path=tmp_path)
        snapshot = resolve_kb_bound_chunks(storage, "kb-238")
        indexed = build_kb_index(
            storage=storage,
            kb_id="kb-238",
            expected_binding_snapshot_fingerprint=snapshot[
                "binding_snapshot_fingerprint"
            ],
            embedding_identity_key=identity.embedding_identity_key,
            identity=identity,
            config=manager.config,
        )
        file_url = str(snapshot["files"][0]["file_url"])
        assert manager.remove_files_from_kb("kb-238", [file_url]) == 1
        storage._conn.execute(
            "UPDATE file_chunk_sets SET created_at = ?, updated_at = ? WHERE chunk_set_id = ?",
            ("2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00", chunk_set["chunk_set_id"]),
        )
        storage._conn.commit()

        cleanup = storage.cleanup_orphan_chunk_sets(
            older_than_days=1,
            dry_run=False,
        )

        assert cleanup["deleted_chunk_sets"] == 0
        assert storage._conn.execute(
            "SELECT index_version_id FROM kb_ready_index_state WHERE kb_id = ?",
            ("kb-238",),
        ).fetchone()[0] == indexed["index_version_id"]
        assert storage._conn.execute(
            "SELECT status FROM kb_index_versions WHERE index_version_id = ?",
            (indexed["index_version_id"],),
        ).fetchone()[0] == "ready"
        assert storage._conn.execute(
            "SELECT COUNT(*) FROM kb_index_items WHERE index_version_id = ?",
            (indexed["index_version_id"],),
        ).fetchone()[0] == 3
        assert storage._conn.execute(
            "SELECT COUNT(*) FROM global_chunks WHERE chunk_set_id = ?",
            (chunk_set["chunk_set_id"],),
        ).fetchone()[0] == 3
        assert storage._conn.execute(
            "SELECT COUNT(*) FROM chunk_embeddings WHERE chunk_id LIKE ?",
            (f"{chunk_set['chunk_set_id']}:%",),
        ).fetchone()[0] == 3
    finally:
        storage.close()


def test_queued_ready_input_for_replaced_index_is_stale_snapshot(tmp_path: Path) -> None:
    from ai_actuarial.agentic_rag.ready_data_builder import (
        get_builder_source_fingerprint,
    )

    storage = Storage(str(tmp_path / "index.db"))
    try:
        manager, _chunk_set, identity = _seed_bound_kb(storage, tmp_path=tmp_path)
        snapshot = resolve_kb_bound_chunks(storage, "kb-238")
        first = build_kb_index(
            storage=storage,
            kb_id="kb-238",
            expected_binding_snapshot_fingerprint=snapshot[
                "binding_snapshot_fingerprint"
            ],
            embedding_identity_key=identity.embedding_identity_key,
            identity=identity,
            config=manager.config,
        )
        old_source = get_builder_source_fingerprint(
            db_path=storage.db_path,
            kb_id="kb-238",
            index_version_id=first["index_version_id"],
        )
        second = build_kb_index(
            storage=storage,
            kb_id="kb-238",
            expected_binding_snapshot_fingerprint=snapshot[
                "binding_snapshot_fingerprint"
            ],
            embedding_identity_key=identity.embedding_identity_key,
            identity=identity,
            config=manager.config,
        )
        runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
        runtime._progress_callback = lambda _task_id: lambda *_args: None
        runtime._stop_requested = lambda _task_id: False

        with pytest.raises(RuntimeError, match="^stale_snapshot:"):
            runtime._run_ready_data_build(
                "queued-ready",
                storage,
                storage.db_path,
                {
                    "contract_version": 1,
                    "kb_id": "kb-238",
                    "profile": "general",
                    "index_version_id": first["index_version_id"],
                    "expected_source_snapshot_fingerprint": old_source[
                        "source_snapshot_fingerprint"
                    ],
                },
            )
        assert storage._conn.execute(
            "SELECT index_version_id FROM kb_ready_index_state WHERE kb_id = ?",
            ("kb-238",),
        ).fetchone()[0] == second["index_version_id"]
    finally:
        storage.close()


def test_runtime_index_stop_finishes_stopped_and_preserves_ready_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        manager, _chunk_set, identity = _seed_bound_kb(storage, tmp_path=tmp_path)
        snapshot = resolve_kb_bound_chunks(storage, "kb-238")
        first = build_kb_index(
            storage=storage,
            kb_id="kb-238",
            expected_binding_snapshot_fingerprint=snapshot[
                "binding_snapshot_fingerprint"
            ],
            embedding_identity_key=identity.embedding_identity_key,
            identity=identity,
            config=manager.config,
        )
        runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
        runtime.task_lock = threading.RLock()
        runtime.active_tasks = {
            "index-stop": {"id": "index-stop", "status": "running", "kb_id": "kb-238"}
        }
        runtime.task_history = []
        runtime._append_history_to_disk = lambda _task: None
        runtime._progress_callback = lambda _task_id: lambda *_args: None
        runtime._stop_requested = lambda _task_id: True
        monkeypatch.setattr(
            "ai_actuarial.rag.kb_index.resolve_server_embedding_identity",
            lambda *_args, **_kwargs: identity,
        )
        monkeypatch.setattr("ai_actuarial.task_runtime.append_task_log", lambda *_args: None)

        result = runtime._run_rag_indexing(
            "index-stop",
            storage,
            {
                "contract_version": 1,
                "kb_id": "kb-238",
                "expected_binding_snapshot_fingerprint": snapshot[
                    "binding_snapshot_fingerprint"
                ],
                "embedding_identity_key": identity.embedding_identity_key,
            },
        )
        runtime._finalize_task_success("index-stop", "rag_indexing", result)

        assert result.success is False
        assert result.metadata == {"kb_id": "kb-238", "stopped": True}
        assert runtime.task_history[-1]["status"] == "stopped"
        assert storage._conn.execute(
            "SELECT index_version_id FROM kb_ready_index_state WHERE kb_id = ?",
            ("kb-238",),
        ).fetchone()[0] == first["index_version_id"]
        assert storage._conn.execute(
            "SELECT COUNT(*) FROM kb_index_versions WHERE kb_id = ?",
            ("kb-238",),
        ).fetchone()[0] == 1
    finally:
        storage.close()


def test_ready_data_requires_complete_bindings_and_exact_committed_index(tmp_path: Path) -> None:
    from ai_actuarial.agentic_rag import ready_data_builder

    storage = Storage(str(tmp_path / "index.db"))
    try:
        manager, _chunk_set, identity = _seed_bound_kb(storage, tmp_path=tmp_path)
        snapshot = resolve_kb_bound_chunks(storage, "kb-238")
        index_result = build_kb_index(
            storage=storage,
            kb_id="kb-238",
            expected_binding_snapshot_fingerprint=snapshot["binding_snapshot_fingerprint"],
            embedding_identity_key=identity.embedding_identity_key,
            identity=identity,
            config=manager.config,
        )
        source = ready_data_builder.get_builder_source_fingerprint(
            db_path=str(tmp_path / "index.db"),
            kb_id="kb-238",
            profile="general",
            index_version_id=index_result["index_version_id"],
        )
        output_dir = tmp_path / "ready"
        manifest = ready_data_builder.build_l0(
            db_path=str(tmp_path / "index.db"),
            output_dir=str(output_dir),
            profile="general",
            kb_id="kb-238",
            index_version_id=index_result["index_version_id"],
            expected_source_snapshot_fingerprint=source["source_snapshot_fingerprint"],
        )
        written = json.loads((output_dir / "ready_data_manifest.json").read_text(encoding="utf-8"))

        assert manifest["source_snapshot_fingerprint"] == source["source_snapshot_fingerprint"]
        assert manifest["index_version_id"] == index_result["index_version_id"]
        assert manifest["artifact_digest"] == written["artifact_digest"]
        assert manifest["doc_count"] == 1
        assert manifest["section_count"] == 3

        storage._conn.execute("DELETE FROM kb_chunk_bindings WHERE kb_id = ?", ("kb-238",))
        storage._conn.commit()
        with pytest.raises(ValueError, match="binding"):
            ready_data_builder.get_builder_source_fingerprint(
                db_path=str(tmp_path / "index.db"),
                kb_id="kb-238",
                profile="general",
                index_version_id=index_result["index_version_id"],
            )
    finally:
        storage.close()


def test_ready_data_doc_chunk_count_tracks_exact_pinned_rebinding(tmp_path: Path) -> None:
    from ai_actuarial.agentic_rag import ready_data_builder

    storage = Storage(str(tmp_path / "ready-count.db"))
    try:
        manager, first_set, identity = _seed_bound_kb(storage, tmp_path=tmp_path)
        file_url = "https://example.test/issue-238.pdf"
        storage._conn.execute(
            "UPDATE catalog_items SET rag_chunk_count = 99 WHERE file_url = ?",
            (file_url,),
        )
        storage._conn.commit()
        first_snapshot = resolve_kb_bound_chunks(storage, "kb-238")
        first_index = build_kb_index(
            storage=storage,
            kb_id="kb-238",
            expected_binding_snapshot_fingerprint=first_snapshot[
                "binding_snapshot_fingerprint"
            ],
            embedding_identity_key=identity.embedding_identity_key,
            identity=identity,
            config=manager.config,
        )
        first_source = ready_data_builder.get_builder_source_fingerprint(
            db_path=storage.db_path,
            kb_id="kb-238",
            profile="general",
            index_version_id=first_index["index_version_id"],
        )
        first_output = tmp_path / "ready-count-first"
        first_manifest = ready_data_builder.build_l0(
            db_path=storage.db_path,
            output_dir=str(first_output),
            profile="general",
            kb_id="kb-238",
            index_version_id=first_index["index_version_id"],
            expected_source_snapshot_fingerprint=first_source[
                "source_snapshot_fingerprint"
            ],
        )
        first_doc = json.loads(
            (first_output / "doc_catalog.jsonl").read_text(encoding="utf-8").strip()
        )

        second_set = storage.get_or_create_file_chunk_set(
            file_url=file_url,
            profile_id=str(first_snapshot["files"][0]["profile_id"]),
            markdown_hash="ready-count-rebind",
            profile_config_hash=str(
                first_snapshot["files"][0]["profile_config_hash"]
            ),
        )
        storage.replace_global_chunks(
            chunk_set_id=str(second_set["chunk_set_id"]),
            chunks=[
                {
                    "chunk_index": 0,
                    "content": "rebound exact chunk",
                    "token_count": 3,
                }
            ],
        )
        rebound_chunk = storage.list_chunks_for_embedding(
            [str(second_set["chunk_set_id"])]
        )[0]
        storage.batch_upsert_chunk_embeddings(
            [{"chunk_id": rebound_chunk["chunk_id"], "vector": [1.0, 0.5, -0.5]}],
            identity=identity.as_dict(),
        )
        storage.bind_chunk_set_to_kb(
            kb_id="kb-238",
            file_url=file_url,
            chunk_set_id=str(second_set["chunk_set_id"]),
            binding_mode="pin",
        )
        second_snapshot = resolve_kb_bound_chunks(storage, "kb-238")
        second_index = build_kb_index(
            storage=storage,
            kb_id="kb-238",
            expected_binding_snapshot_fingerprint=second_snapshot[
                "binding_snapshot_fingerprint"
            ],
            embedding_identity_key=identity.embedding_identity_key,
            identity=identity,
            config=manager.config,
        )
        second_source = ready_data_builder.get_builder_source_fingerprint(
            db_path=storage.db_path,
            kb_id="kb-238",
            profile="general",
            index_version_id=second_index["index_version_id"],
        )
        second_output = tmp_path / "ready-count-second"
        second_manifest = ready_data_builder.build_l0(
            db_path=storage.db_path,
            output_dir=str(second_output),
            profile="general",
            kb_id="kb-238",
            index_version_id=second_index["index_version_id"],
            expected_source_snapshot_fingerprint=second_source[
                "source_snapshot_fingerprint"
            ],
        )
        second_doc = json.loads(
            (second_output / "doc_catalog.jsonl").read_text(encoding="utf-8").strip()
        )

        assert first_doc["rag_chunk_count"] == 3
        assert first_manifest["section_count"] == first_index["chunk_count"] == 3
        assert second_doc["rag_chunk_count"] == 1
        assert second_manifest["section_count"] == second_index["chunk_count"] == 1
        assert storage._conn.execute(
            "SELECT COUNT(*) FROM global_chunks WHERE chunk_set_id = ?",
            (first_set["chunk_set_id"],),
        ).fetchone()[0] == 3
    finally:
        storage.close()


def test_rebind_switches_effective_snapshot_without_mutating_old_chunk_set(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _manager, first_set, _identity_value = _seed_bound_kb(storage, tmp_path=tmp_path)
        first = resolve_kb_bound_chunks(storage, "kb-238")
        profile_id = str(first["files"][0]["profile_id"])
        second_set = storage.get_or_create_file_chunk_set(
            file_url=first["files"][0]["file_url"],
            profile_id=profile_id,
            markdown_hash="markdown-v2",
            profile_config_hash=str(first["files"][0]["profile_config_hash"]),
        )
        storage.replace_global_chunks(
            chunk_set_id=str(second_set["chunk_set_id"]),
            chunks=[{"chunk_index": 0, "content": "replacement", "token_count": 1}],
        )
        storage.bind_chunk_set_to_kb(
            kb_id="kb-238",
            file_url=first["files"][0]["file_url"],
            chunk_set_id=str(second_set["chunk_set_id"]),
            binding_mode="pin",
        )

        second = resolve_kb_bound_chunks(storage, "kb-238")
        assert second["binding_snapshot_fingerprint"] != first["binding_snapshot_fingerprint"]
        assert second["bound_chunk_count"] == 1
        assert second["files"][0]["chunk_set_id"] == second_set["chunk_set_id"]
        assert storage._conn.execute(
            "SELECT COUNT(*) FROM global_chunks WHERE chunk_set_id = ?",
            (first_set["chunk_set_id"],),
        ).fetchone()[0] == 3
    finally:
        storage.close()


def test_cross_kb_reuses_same_identity_embeddings(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        manager, chunk_set, identity = _seed_bound_kb(
            storage, tmp_path=tmp_path, persist_embeddings=False
        )

        class CountingGenerator:
            def __init__(self) -> None:
                self.generated = 0

            def generate_embeddings(self, texts):
                self.generated += len(texts)
                return [[float(index + 1), 0.5, -0.5] for index, _ in enumerate(texts)]

        generator = CountingGenerator()
        first_snapshot = resolve_kb_bound_chunks(storage, "kb-238")
        build_kb_index(
            storage=storage,
            kb_id="kb-238",
            expected_binding_snapshot_fingerprint=first_snapshot["binding_snapshot_fingerprint"],
            embedding_identity_key=identity.embedding_identity_key,
            identity=identity,
            generator=generator,
            config=manager.config,
        )
        manager.create_kb(
            kb_id="kb-238-b",
            name="Issue 238 B",
            kb_mode="manual",
            chunk_profile_id=str(first_snapshot["files"][0]["profile_id"]),
            embedding_provider=identity.provider,
            embedding_model=identity.model,
            embedding_dimension=identity.dimension,
            embedding_identity_key=identity.embedding_identity_key,
        )
        file_url = first_snapshot["files"][0]["file_url"]
        manager.add_files_to_kb("kb-238-b", [file_url])
        storage.bind_chunk_set_to_kb(
            kb_id="kb-238-b",
            file_url=file_url,
            chunk_set_id=str(chunk_set["chunk_set_id"]),
            binding_mode="follow_latest",
        )
        second_snapshot = resolve_kb_bound_chunks(storage, "kb-238-b")
        build_kb_index(
            storage=storage,
            kb_id="kb-238-b",
            expected_binding_snapshot_fingerprint=second_snapshot["binding_snapshot_fingerprint"],
            embedding_identity_key=identity.embedding_identity_key,
            identity=identity,
            generator=generator,
            config=manager.config,
        )

        assert generator.generated == 3
        assert storage._conn.execute(
            "SELECT COUNT(*) FROM chunk_embeddings WHERE embedding_identity_key = ?",
            (identity.embedding_identity_key,),
        ).fetchone()[0] == 3
    finally:
        storage.close()


def test_identity_race_and_commit_failure_preserve_ready_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        manager, _chunk_set, identity = _seed_bound_kb(storage, tmp_path=tmp_path)
        snapshot = resolve_kb_bound_chunks(storage, "kb-238")
        first = build_kb_index(
            storage=storage,
            kb_id="kb-238",
            expected_binding_snapshot_fingerprint=snapshot["binding_snapshot_fingerprint"],
            embedding_identity_key=identity.embedding_identity_key,
            identity=identity,
            config=manager.config,
        )

        def change_identity(message: str, _current: int, _total: int) -> None:
            if message == "Commit":
                storage._conn.execute(
                    "UPDATE rag_knowledge_bases SET embedding_identity_key = 'changed' WHERE kb_id = ?",
                    ("kb-238",),
                )
                storage._conn.commit()

        with pytest.raises(KBIndexContractError) as raced:
            build_kb_index(
                storage=storage,
                kb_id="kb-238",
                expected_binding_snapshot_fingerprint=snapshot["binding_snapshot_fingerprint"],
                embedding_identity_key=identity.embedding_identity_key,
                identity=identity,
                config=manager.config,
                progress_callback=change_identity,
            )
        assert raced.value.code == "stale_snapshot"
        storage._conn.execute(
            "UPDATE rag_knowledge_bases SET embedding_identity_key = ? WHERE kb_id = ?",
            (identity.embedding_identity_key, "kb-238"),
        )
        storage._conn.commit()

        @contextmanager
        def failed_transaction(*_args, **_kwargs):
            raise RuntimeError("synthetic commit failure")
            yield

        monkeypatch.setattr(storage, "transaction", failed_transaction)
        with pytest.raises(KBIndexContractError) as failed:
            build_kb_index(
                storage=storage,
                kb_id="kb-238",
                expected_binding_snapshot_fingerprint=snapshot["binding_snapshot_fingerprint"],
                embedding_identity_key=identity.embedding_identity_key,
                identity=identity,
                config=manager.config,
            )
        assert failed.value.code == "build_failure"
        assert storage._conn.execute(
            "SELECT index_version_id FROM kb_ready_index_state WHERE kb_id = ?",
            ("kb-238",),
        ).fetchone()[0] == first["index_version_id"]
    finally:
        storage.close()


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        ("embedding", "missing_or_failed_embedding"),
        ("faiss", "build_failure"),
    ],
)
def test_embedding_and_faiss_failure_preserve_ready_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    expected_code: str,
) -> None:
    storage = Storage(str(tmp_path / f"{failure}.db"))
    try:
        manager, _chunk_set, identity = _seed_bound_kb(storage, tmp_path=tmp_path)
        snapshot = resolve_kb_bound_chunks(storage, "kb-238")
        first = build_kb_index(
            storage=storage,
            kb_id="kb-238",
            expected_binding_snapshot_fingerprint=snapshot["binding_snapshot_fingerprint"],
            embedding_identity_key=identity.embedding_identity_key,
            identity=identity,
            config=manager.config,
        )

        generator = None
        if failure == "embedding":
            storage._conn.execute(
                "DELETE FROM chunk_embeddings WHERE embedding_identity_key = ?",
                (identity.embedding_identity_key,),
            )
            storage._conn.commit()

            class FailingGenerator:
                def generate_embeddings(self, _texts):
                    raise RuntimeError("synthetic embedding failure")

            generator = FailingGenerator()
        else:
            def fail_faiss(*_args, **_kwargs):
                raise RuntimeError("synthetic FAISS failure")

            monkeypatch.setattr(
                "ai_actuarial.rag.kb_index.VectorStore.add_vectors",
                fail_faiss,
            )

        with pytest.raises(KBIndexContractError) as failed:
            build_kb_index(
                storage=storage,
                kb_id="kb-238",
                expected_binding_snapshot_fingerprint=snapshot[
                    "binding_snapshot_fingerprint"
                ],
                embedding_identity_key=identity.embedding_identity_key,
                identity=identity,
                generator=generator,
                config=manager.config,
            )
        assert failed.value.code == expected_code
        assert storage._conn.execute(
            "SELECT index_version_id FROM kb_ready_index_state WHERE kb_id = ?",
            ("kb-238",),
        ).fetchone()[0] == first["index_version_id"]
    finally:
        storage.close()


def test_embedding_provider_initialization_failure_is_canonical_and_preserves_ready_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = Storage(str(tmp_path / "provider-init.db"))
    try:
        manager, _chunk_set, identity = _seed_bound_kb(storage, tmp_path=tmp_path)
        snapshot = resolve_kb_bound_chunks(storage, "kb-238")
        first = build_kb_index(
            storage=storage,
            kb_id="kb-238",
            expected_binding_snapshot_fingerprint=snapshot[
                "binding_snapshot_fingerprint"
            ],
            embedding_identity_key=identity.embedding_identity_key,
            identity=identity,
            config=manager.config,
        )

        def fail_provider_init(**_kwargs: object) -> object:
            raise RuntimeError("provider init leaked-secret-value")

        monkeypatch.setattr(
            "ai_actuarial.rag.kb_index.ensure_chunk_embeddings",
            fail_provider_init,
        )
        with pytest.raises(KBIndexContractError) as failed:
            build_kb_index(
                storage=storage,
                kb_id="kb-238",
                expected_binding_snapshot_fingerprint=snapshot[
                    "binding_snapshot_fingerprint"
                ],
                embedding_identity_key=identity.embedding_identity_key,
                identity=identity,
                config=manager.config,
            )

        assert failed.value.code == "missing_or_failed_embedding"
        assert "leaked-secret-value" not in str(failed.value)
        assert storage._conn.execute(
            "SELECT index_version_id FROM kb_ready_index_state WHERE kb_id = ?",
            ("kb-238",),
        ).fetchone()[0] == first["index_version_id"]
        assert storage._conn.execute(
            "SELECT COUNT(*) FROM kb_index_versions WHERE kb_id = ?",
            ("kb-238",),
        ).fetchone()[0] == 1
    finally:
        storage.close()


def test_api_launch_adapters_return_real_jobs_and_small_contracts(tmp_path: Path) -> None:
    from ai_actuarial.agentic_rag.ready_data_builder import get_builder_source_fingerprint
    from ai_actuarial.api.services.rag_admin import (
        build_agentic_ready_manifest,
        create_index_task,
    )

    db_path = str(tmp_path / "index.db")
    storage = Storage(db_path)
    try:
        manager, _chunk_set, identity = _seed_bound_kb(storage, tmp_path=tmp_path)
        snapshot = resolve_kb_bound_chunks(storage, "kb-238")
        index_result = build_kb_index(
            storage=storage,
            kb_id="kb-238",
            expected_binding_snapshot_fingerprint=snapshot["binding_snapshot_fingerprint"],
            embedding_identity_key=identity.embedding_identity_key,
            identity=identity,
            config=manager.config,
        )
        source = get_builder_source_fingerprint(
            db_path=db_path,
            kb_id="kb-238",
            index_version_id=index_result["index_version_id"],
        )
    finally:
        storage.close()

    class Bridge:
        def __init__(self) -> None:
            self.started = []

        def start_background_task(self, task_type, payload, **kwargs):
            self.started.append((task_type, dict(payload), dict(kwargs)))
            return f"job-{len(self.started)}"

    bridge = Bridge()
    index_launch, index_status = create_index_task(
        db_path=db_path,
        kb_id="kb-238",
        payload={"force_rebuild": True},
        headers={},
        bridge_state=bridge,
    )
    ready_launch, ready_status = build_agentic_ready_manifest(
        db_path=db_path,
        kb_id="kb-238",
        payload={
            "index_version_id": index_result["index_version_id"],
            "expected_source_snapshot_fingerprint": source["source_snapshot_fingerprint"],
        },
        headers={},
        bridge_state=bridge,
    )

    assert (index_status, index_launch["job_id"]) == (202, "job-1")
    assert (ready_status, ready_launch["job_id"]) == (202, "job-2")
    assert bridge.started[0][1] == {
        "type": "rag_indexing",
        "contract_version": 1,
        "kb_id": "kb-238",
        "expected_binding_snapshot_fingerprint": snapshot["binding_snapshot_fingerprint"],
        "embedding_identity_key": identity.embedding_identity_key,
        "force_rebuild": True,
        "name": "KB Index: Issue 238",
    }
    assert bridge.started[1][1]["contract_version"] == 1
    assert bridge.started[1][1]["index_version_id"] == index_result["index_version_id"]
    serialized = json.dumps([index_launch, ready_launch, bridge.started])
    assert "persisted chunk" not in serialized
    assert "vector" not in serialized


def test_successful_standalone_index_launches_independent_ready_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    runtime.task_lock = threading.RLock()
    runtime.active_tasks = {
        "index-task": {
            "id": "index-task",
            "status": "running",
            "kb_id": "kb-238",
        }
    }
    runtime.task_history = []
    runtime._append_history_to_disk = lambda _task: None
    runtime._pipeline_ready_data_input = lambda kb_id, result: {
        "contract_version": 1,
        "kb_id": kb_id,
        "profile": "general",
        "index_version_id": result["index_version_id"],
        "expected_source_snapshot_fingerprint": "source-1",
    }
    launches: list[tuple[str, dict, dict]] = []

    def launch(task_type: str, payload: dict, **kwargs: object) -> str:
        launches.append((task_type, dict(payload), dict(kwargs)))
        return "ready-task"

    runtime.start_background_task = launch
    monkeypatch.setattr("ai_actuarial.task_runtime.append_task_log", lambda *_args: None)
    result = CollectionResult(
        success=True,
        items_found=3,
        items_downloaded=3,
        items_skipped=0,
        errors=[],
        metadata={
            "kb_id": "kb-238",
            "result": {
                "contract_version": 1,
                "index_version_id": "idxv-1",
                "binding_snapshot_fingerprint": "binding-1",
                "embedding_identity_key": "identity-1",
                "chunk_count": 3,
                "vector_dimension": 3,
                "artifact_digest": "digest-1",
            },
        },
    )

    runtime._finalize_task_success("index-task", "rag_indexing", result)

    assert launches == [
        (
            "ready_data_build",
            {
                "contract_version": 1,
                "kb_id": "kb-238",
                "profile": "general",
                "index_version_id": "idxv-1",
                "expected_source_snapshot_fingerprint": "source-1",
            },
            {
                "task_name": "Ready Data: kb-238",
                "extra_fields": {
                    "kb_id": "kb-238",
                    "kb_index_task_id": "index-task",
                },
            },
        )
    ]
    assert runtime.task_history[0]["ready_data_task_id"] == "ready-task"


@pytest.mark.parametrize("launch_fails", [False, True])
def test_index_terminal_history_waits_for_ready_handoff_outcome(
    monkeypatch: pytest.MonkeyPatch,
    launch_fails: bool,
) -> None:
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    runtime.task_lock = threading.RLock()
    runtime.active_tasks = {
        "index-task": {
            "id": "index-task",
            "status": "running",
            "kb_id": "kb-238",
        }
    }
    runtime.task_history = []
    runtime._append_history_to_disk = lambda _task: None
    runtime._pipeline_ready_data_input = lambda kb_id, result: {
        "kb_id": kb_id,
        "index_version_id": result["index_version_id"],
    }
    launch_entered = threading.Event()
    allow_launch_to_finish = threading.Event()

    def launch(*_args: object, **_kwargs: object) -> str:
        launch_entered.set()
        if not allow_launch_to_finish.wait(5):
            raise AssertionError("test did not release Ready Data launch")
        if launch_fails:
            raise RuntimeError("synthetic Ready Data launch failure")
        return "ready-task"

    runtime.start_background_task = launch
    monkeypatch.setattr("ai_actuarial.task_runtime.append_task_log", lambda *_args: None)
    result = CollectionResult(
        success=True,
        items_found=1,
        items_downloaded=1,
        items_skipped=0,
        errors=[],
        metadata={
            "kb_id": "kb-238",
            "result": {"index_version_id": "idxv-1"},
        },
    )
    finalize_thread = threading.Thread(
        target=runtime._finalize_task_success,
        args=("index-task", "rag_indexing", result),
    )
    reader_started = threading.Event()
    reader_finished = threading.Event()
    observed: dict[str, object] = {}

    def read_terminal_task() -> None:
        reader_started.set()
        observed["task"] = runtime._pipeline_task_result("index-task")
        reader_finished.set()

    finalize_thread.start()
    assert launch_entered.wait(5)
    reader_thread = threading.Thread(target=read_terminal_task)
    reader_thread.start()
    assert reader_started.wait(5)
    try:
        assert not reader_finished.wait(0.2)
    finally:
        allow_launch_to_finish.set()
        finalize_thread.join(5)
        reader_thread.join(5)

    assert not finalize_thread.is_alive()
    assert not reader_thread.is_alive()
    terminal = observed["task"]
    assert isinstance(terminal, dict)
    assert terminal["status"] == "completed"
    if launch_fails:
        assert terminal["ready_data_launch_error"] == "synthetic Ready Data launch failure"
        assert "ready_data_task_id" not in terminal
    else:
        assert terminal["ready_data_task_id"] == "ready-task"
        assert "ready_data_launch_error" not in terminal


def test_cli_task_status_log_stop_are_thin_json_adapters(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ai_actuarial.cli import build_parser

    calls: list[tuple[str, str]] = []

    def request(_api_url: str, path: str, *, method: str, **_kwargs: object) -> dict:
        calls.append((method, path))
        if path == "/api/tasks/active":
            return {"tasks": [{"id": "job-238", "status": "running"}]}
        if path.startswith("/api/tasks/log/"):
            return {"task_id": "job-238", "log": "Resolve"}
        if path.startswith("/api/tasks/stop/"):
            return {"success": True, "message": "Stop signal sent"}
        raise AssertionError(path)

    monkeypatch.setattr("ai_actuarial.cli._api_json_request", request)
    parser = build_parser()
    commands = [
        parser.parse_args(["task", "status", "job-238", "--json"]),
        parser.parse_args(["task", "status", "job-238", "--json"]),
        parser.parse_args(["task", "log", "job-238", "--tail", "25", "--json"]),
        parser.parse_args(["task", "stop", "job-238", "--json"]),
    ]

    assert [command.func(command) for command in commands] == [0, 0, 0, 0]
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert output[0] == output[1] == {
        "job_id": "job-238",
        "task": {"id": "job-238", "status": "running"},
    }
    assert output[2] == {"task_id": "job-238", "log": "Resolve"}
    assert output[3]["job_id"] == "job-238"
    assert calls == [
        ("GET", "/api/tasks/active"),
        ("GET", "/api/tasks/active"),
        ("GET", "/api/tasks/log/job-238?tail=25"),
        ("POST", "/api/tasks/stop/job-238"),
    ]


def test_cli_kb_binding_get_and_set_are_thin_idempotent_json_adapters(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ai_actuarial.cli import build_parser

    contract = {
        "contract_version": 1,
        "kb_id": "kb/238",
        "binding_snapshot_fingerprint": "bind-238",
        "bound_file_count": 1,
        "bound_chunk_set_count": 1,
        "bound_chunk_count": 3,
    }
    calls: list[tuple[str, str, dict | None]] = []

    def request(
        _api_url: str,
        path: str,
        *,
        method: str,
        payload: dict | None = None,
        **_kwargs: object,
    ) -> dict:
        calls.append((method, path, payload))
        return {"kb_id": "kb/238", "binding": contract}

    monkeypatch.setattr("ai_actuarial.cli._api_json_request", request)
    parser = build_parser()
    binding_payload = json.dumps(
        {
            "file_url": "https://example.test/a.pdf",
            "chunk_set_id": "cs-1",
            "binding_mode": "pin",
        }
    )
    commands = [
        parser.parse_args(["kb", "binding", "get", "kb/238", "--json"]),
        parser.parse_args(
            [
                "kb",
                "binding",
                "set",
                "kb/238",
                "--payload-json",
                binding_payload,
                "--json",
            ]
        ),
        parser.parse_args(
            [
                "kb",
                "binding",
                "set",
                "kb/238",
                "--payload-json",
                binding_payload,
                "--json",
            ]
        ),
    ]

    assert [command.func(command) for command in commands] == [0, 0, 0]
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert output[0] == output[1] == output[2] == {
        "kb_id": "kb/238",
        "binding": contract,
    }
    assert calls == [
        ("GET", "/api/rag/knowledge-bases/kb%2F238/bindings", None),
        (
            "POST",
            "/api/rag/knowledge-bases/kb%2F238/bindings",
            json.loads(binding_payload),
        ),
        (
            "POST",
            "/api/rag/knowledge-bases/kb%2F238/bindings",
            json.loads(binding_payload),
        ),
    ]
    assert "content" not in json.dumps(output)
    assert "vector" not in json.dumps(output)


def test_cli_ready_get_then_publish_is_thin_exact_json_adapter(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ai_actuarial.cli import build_parser

    calls: list[tuple[str, str, dict | None]] = []
    get_response = {
        "kb_id": "kb/238",
        "manifest": {
            "profile": "general",
            "automation_state": "awaiting_publish",
            "last_attempt_publication_id": "arp-238",
        },
        "publication_state": {"active_publication_id": "arp-active"},
    }
    publish_response = {
        "kb_id": "kb/238",
        "profile": "general",
        "publication_id": "arp-238",
        "publish_status": "published",
        "active_publication_id": "arp-238",
    }

    def request(
        _api_url: str,
        path: str,
        *,
        method: str,
        payload: dict | None = None,
        **_kwargs: object,
    ) -> dict:
        calls.append((method, path, payload))
        return get_response if method == "GET" else publish_response

    monkeypatch.setattr("ai_actuarial.cli._api_json_request", request)
    parser = build_parser()
    get_command = parser.parse_args(
        [
            "kb",
            "ready",
            "get",
            "kb/238",
            "--profile",
            "general",
            "--json",
        ]
    )
    publish_command = parser.parse_args(
        [
            "kb",
            "ready",
            "publish",
            "kb/238",
            "--profile",
            "general",
            "--publication-id",
            "arp-238",
            "--expected-active-publication-id",
            "arp-active",
            "--json",
        ]
    )

    assert get_command.func(get_command) == 0
    assert publish_command.func(publish_command) == 0
    assert [json.loads(line) for line in capsys.readouterr().out.splitlines()] == [
        get_response,
        publish_response,
    ]
    assert calls == [
        (
            "GET",
            "/api/rag/knowledge-bases/kb%2F238/agentic-ready-manifest?profile=general",
            None,
        ),
        (
            "POST",
            "/api/rag/knowledge-bases/kb%2F238/agentic-ready-manifest/publish",
            {
                "profile": "general",
                "publication_id": "arp-238",
                "expected_active_publication_id": "arp-active",
            },
        )
    ]


@pytest.mark.parametrize(
    ("auto_publish", "publication_id", "publish_status"),
    [(False, None, "awaiting_publish"), (True, "publication-238", "published")],
)
def test_ready_task_manual_and_auto_publish_are_both_successful(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    auto_publish: bool,
    publication_id: str | None,
    publish_status: str,
) -> None:
    storage = Storage(str(tmp_path / "ready-task.db"))
    try:
        manager, _chunk_set, _identity_value = _seed_bound_kb(
            storage,
            tmp_path=tmp_path,
        )
        storage.set_agentic_ready_automation(
            kb_id="kb-238",
            automatic_build_enabled=auto_publish,
            automatic_publish_enabled=auto_publish,
        )
        runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
        runtime._progress_callback = lambda _task_id: lambda *_args: None

        def build_core(**kwargs: object) -> dict:
            assert kwargs["publish"] is auto_publish
            return {
                "validation": {"valid": True, "errors": []},
                "candidate_publication": {
                    "publication_id": "publication-238",
                    "source_version_id": "source-238",
                    "artifact_digest": "digest-238",
                    "doc_count": 2,
                    "section_count": 3,
                },
                "publication_state": (
                    {"active_publication_id": "publication-238"}
                    if auto_publish
                    else {}
                ),
            }

        monkeypatch.setattr(
            "ai_actuarial.api.services.rag_admin._build_agentic_ready_manifest_core",
            build_core,
        )
        result = runtime._run_ready_data_build(
            "ready-task",
            storage,
            storage.db_path,
            {
                "contract_version": 1,
                "kb_id": "kb-238",
                "profile": "general",
                "index_version_id": "idxv-238",
                "expected_source_snapshot_fingerprint": "source-238",
            },
        )

        assert result.success is True
        assert result.metadata["result"] == {
            "contract_version": 1,
            "publication_id": publication_id,
            "publish_status": publish_status,
            "source_snapshot_fingerprint": "source-238",
            "index_version_id": "idxv-238",
            "artifact_digest": "digest-238",
            "doc_count": 2,
            "section_count": 3,
        }
        assert manager.get_kb("kb-238") is not None
    finally:
        storage.close()


def test_ready_task_rejects_idempotent_state_without_valid_active_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = Storage(str(tmp_path / "ready-uncommitted.db"))
    try:
        _seed_bound_kb(storage, tmp_path=tmp_path)
        storage.set_agentic_ready_automation(
            kb_id="kb-238",
            automatic_build_enabled=True,
            automatic_publish_enabled=True,
        )
        runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
        runtime._progress_callback = lambda _task_id: lambda *_args: None
        runtime._stop_requested = lambda _task_id: False
        monkeypatch.setattr(
            "ai_actuarial.api.services.rag_admin._build_agentic_ready_manifest_core",
            lambda **_kwargs: {
                "validation": {"valid": True, "errors": []},
                "candidate_publication": {
                    "publication_id": "duplicate-candidate",
                    "source_version_id": "source-238",
                },
                "publication_state": {
                    "active_publication_id": "not-active",
                    "idempotent": True,
                    "cas_won": True,
                    "active_publication": {
                        "publication_id": "not-active",
                        "status": "validated",
                    },
                },
            },
        )

        with pytest.raises(RuntimeError, match="publish_failure"):
            runtime._run_ready_data_build(
                "ready-uncommitted",
                storage,
                storage.db_path,
                {
                    "contract_version": 1,
                    "kb_id": "kb-238",
                    "profile": "general",
                    "index_version_id": "idxv-238",
                    "expected_source_snapshot_fingerprint": "source-238",
                },
            )
    finally:
        storage.close()
