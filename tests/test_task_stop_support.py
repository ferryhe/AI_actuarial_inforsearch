from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from ai_actuarial.catalog import CatalogItem
from ai_actuarial.catalog_incremental import run_catalog_for_urls, run_incremental_catalog
from ai_actuarial.collectors.base import CollectionResult
from ai_actuarial.crawler import Crawler, SiteConfig
from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.rag.indexing import IndexingPipeline
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.rag.semantic_chunking import Chunk
from ai_actuarial.rag.vector_store import VectorStore
from ai_actuarial.storage import Storage


def _seed_catalog_files(db_path, count: int = 2) -> list[str]:
    storage = Storage(str(db_path))
    urls = []
    try:
        for idx in range(count):
            file_url = f"https://example.com/catalog-stop-{idx}.pdf"
            urls.append(file_url)
            storage.insert_file(
                url=file_url,
                sha256=f"sha-{idx}",
                title=f"Catalog Stop {idx}",
                source_site="example.com",
                source_page_url="https://example.com",
                original_filename=f"catalog-stop-{idx}.pdf",
                local_path=f"/tmp/catalog-stop-{idx}.pdf",
                bytes=1024,
                content_type="application/pdf",
            )
    finally:
        storage.close()
    return urls


def test_run_catalog_for_urls_respects_immediate_stop(tmp_path) -> None:
    db_path = tmp_path / "catalog-stop.db"
    file_urls = _seed_catalog_files(db_path)

    stats = run_catalog_for_urls(
        db_path=str(db_path),
        file_urls=file_urls,
        out_jsonl=tmp_path / "catalog.jsonl",
        out_md=tmp_path / "catalog.md",
        max_workers=1,
        stop_check=lambda: True,
    )

    assert stats["stopped"] is True
    assert stats["processed"] == 0
    assert stats["written"] == 0


def test_run_incremental_catalog_flushes_partial_batch_before_stop(tmp_path) -> None:
    db_path = tmp_path / "catalog-incremental-stop.db"
    _seed_catalog_files(db_path)

    responses = iter([False, False, True, False])

    def stop_check() -> bool:
        return next(responses, False)

    def fake_process(row, *args, **kwargs):
        item = CatalogItem(
            source_site=row["source_site"],
            title=row["title"],
            original_filename=row["original_filename"],
            url=row["url"],
            local_path=row["local_path"],
            keywords=["ai"],
            summary="summary",
            category="AI",
        )
        return row, item, "ok", None

    with patch("ai_actuarial.catalog_incremental._process_single_row", side_effect=fake_process):
        stats = run_incremental_catalog(
            db_path=str(db_path),
            out_jsonl=tmp_path / "catalog.jsonl",
            out_md=tmp_path / "catalog.md",
            batch=10,
            limit=10,
            stop_check=stop_check,
        )

    assert stats["stopped"] is True
    assert stats["processed"] == 1
    assert stats["written"] == 1
    assert (tmp_path / "catalog.jsonl").exists()


def test_indexing_pipeline_stops_before_second_file(tmp_path) -> None:
    embedding_generator = MagicMock()
    embedding_generator.get_embedding_dimension.return_value = 3
    kb_manager = SimpleNamespace(
        storage=SimpleNamespace(),
        config=SimpleNamespace(data_dir=str(tmp_path)),
        chunker=object(),
        embedding_generator=embedding_generator,
        get_current_embedding_metadata=MagicMock(
            return_value={
                "provider": "openai",
                "model": "text-embedding-3-small",
                "dimension": 3,
            }
        ),
        sync_kb_embedding_metadata=MagicMock(
            return_value={
                "provider": "openai",
                "model": "text-embedding-3-small",
                "dimension": 3,
            }
        ),
        get_kb=MagicMock(
            return_value=SimpleNamespace(
                name="Stop Test KB",
                embedding_model="text-embedding-3-small",
                embedding_provider="openai",
                embedding_dimension=3,
                index_type="Flat",
                chunk_count=2,
            )
        ),
    )

    processed_files: list[str] = []

    def stop_check() -> bool:
        return len(processed_files) >= 1

    def fake_index_single_file(self, kb_id: str, file_url: str, vector_store) -> dict[str, object]:
        processed_files.append(file_url)
        return {"success": True, "chunk_count": 2}

    with patch("ai_actuarial.rag.indexing.VectorStore") as mock_vector_store, patch.object(
        IndexingPipeline,
        "_index_single_file",
        fake_index_single_file,
    ), patch.object(IndexingPipeline, "_update_kb_stats"):
        pipeline = IndexingPipeline(kb_manager, stop_check=stop_check)
        stats = pipeline.index_files(
            kb_id="kb-stop-test",
            file_urls=["file-1", "file-2", "file-3"],
            force_reindex=True,
        )

    assert stats["stopped"] is True
    assert stats["indexed_files"] == 1
    assert processed_files == ["file-1"]
    mock_vector_store.return_value.save_index.assert_called_once()


def test_indexing_pipeline_immediate_stop_preserves_existing_index(tmp_path) -> None:
    kb_id = "kb-stop-test"
    kb_dir = tmp_path / kb_id
    kb_dir.mkdir(parents=True, exist_ok=True)
    index_path = kb_dir / "index.faiss"
    index_path.write_text("existing-index", encoding="utf-8")

    embedding_generator = MagicMock()
    embedding_generator.get_embedding_dimension.return_value = 3
    kb_manager = SimpleNamespace(
        storage=SimpleNamespace(),
        config=SimpleNamespace(data_dir=str(tmp_path)),
        chunker=object(),
        embedding_generator=embedding_generator,
        get_current_embedding_metadata=MagicMock(
            return_value={
                "provider": "openai",
                "model": "text-embedding-3-small",
                "dimension": 3,
            }
        ),
        sync_kb_embedding_metadata=MagicMock(
            return_value={
                "provider": "openai",
                "model": "text-embedding-3-small",
                "dimension": 3,
            }
        ),
        get_kb=MagicMock(
            return_value=SimpleNamespace(
                name="Stop Test KB",
                embedding_model="text-embedding-3-small",
                embedding_provider="openai",
                embedding_dimension=3,
                index_type="Flat",
                chunk_count=0,
            )
        ),
    )

    with patch("ai_actuarial.rag.indexing.VectorStore") as mock_vector_store:
        pipeline = IndexingPipeline(kb_manager, stop_check=lambda: True)
        stats = pipeline.index_files(
            kb_id=kb_id,
            file_urls=["file-1"],
            force_reindex=True,
        )

    assert stats["stopped"] is True
    assert index_path.read_text(encoding="utf-8") == "existing-index"
    mock_vector_store.assert_not_called()


def test_crawler_records_mid_crawl_stop_diagnostic(tmp_path) -> None:
    storage = Storage(str(tmp_path / "crawler-stop.db"))
    stop_calls = 0

    def stop_check() -> bool:
        nonlocal stop_calls
        stop_calls += 1
        return stop_calls >= 2

    crawler = Crawler(
        storage=storage,
        download_dir=str(tmp_path),
        user_agent="TestAgent/1.0",
        stop_check=stop_check,
    )
    cfg = SiteConfig(name="Stop Site", url="https://example.com", max_pages=5, delay_seconds=0)

    try:
        with patch.object(crawler, "_load_sitemap", return_value=[]):
            result = crawler.crawl_site(cfg)
    finally:
        storage.close()

    assert result == []
    diagnostic = crawler.get_last_crawl_diagnostic()
    assert diagnostic["stopped"] is True
    assert diagnostic["pages_visited"] == 0


def test_indexing_pipeline_records_current_embedding_index_version(tmp_path) -> None:
    kb_id = "kb-index-version"
    storage = SimpleNamespace(create_kb_index_version=MagicMock())
    embedding_generator = MagicMock()
    embedding_generator.get_embedding_dimension.return_value = 3
    kb = SimpleNamespace(
        name="Versioned KB",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        embedding_dimension=3,
        index_type="Flat",
        chunk_count=4,
    )
    kb_manager = SimpleNamespace(
        storage=storage,
        config=SimpleNamespace(data_dir=str(tmp_path)),
        chunker=object(),
        embedding_generator=embedding_generator,
        get_current_embedding_metadata=MagicMock(
            return_value={
                "provider": "openai",
                "model": "text-embedding-3-small",
                "dimension": 3,
            }
        ),
        sync_kb_embedding_metadata=MagicMock(
            return_value={
                "provider": "openai",
                "model": "text-embedding-3-small",
                "dimension": 3,
            }
        ),
        get_kb=MagicMock(return_value=kb),
    )

    with patch("ai_actuarial.rag.indexing.VectorStore") as mock_vector_store, patch.object(
        IndexingPipeline,
        "_index_single_file",
        return_value={"success": True, "chunk_count": 4},
    ), patch.object(IndexingPipeline, "_update_kb_stats"):
        pipeline = IndexingPipeline(kb_manager)
        stats = pipeline.index_files(
            kb_id=kb_id,
            file_urls=["file-1"],
            force_reindex=True,
        )

    assert stats["indexed_files"] == 1
    mock_vector_store.return_value.save_index.assert_called_once()
    storage.create_kb_index_version.assert_called_once_with(
        kb_id=kb_id,
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        embedding_dimension=3,
        index_type="Flat",
        chunk_count=4,
        status="ready",
        artifact_path=str(tmp_path / kb_id / "index.faiss"),
    )


def test_indexing_pipeline_force_reindex_removes_chunks_for_deleted_files(tmp_path) -> None:
    kb_id = "kb-clean-removed"
    old_url = "https://example.com/removed.pdf"
    current_url = "https://example.com/current.pdf"
    storage = Storage(str(tmp_path / "clean-removed.db"))
    try:
        for file_url, title in [(old_url, "Removed"), (current_url, "Current")]:
            storage.insert_file(
                url=file_url,
                sha256=f"sha-{title}",
                title=title,
                source_site="example.com",
                source_page_url="https://example.com",
                original_filename=f"{title.lower()}.pdf",
                local_path=str(tmp_path / f"{title.lower()}.pdf"),
                bytes=1024,
                content_type="application/pdf",
            )
        manager = KnowledgeBaseManager(storage)
        manager.create_kb(kb_id, "Clean Removed KB", kb_mode="manual")
        manager.add_files_to_kb(kb_id, [current_url])
        storage._conn.execute(
            """
            INSERT INTO rag_chunks (chunk_id, kb_id, file_url, chunk_index, content, token_count, section_hierarchy, embedding_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (f"{kb_id}:removed:0", kb_id, old_url, 0, "Removed stale chunk", 3, "Removed", "hash-removed", "2026-05-24T02:00:00+00:00"),
        )
        storage._conn.execute(
            """
            INSERT INTO rag_chunks (chunk_id, kb_id, file_url, chunk_index, content, token_count, section_hierarchy, embedding_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (f"{kb_id}:current:0", kb_id, current_url, 0, "Current stale chunk", 3, "Current", "hash-current", "2026-05-24T02:00:00+00:00"),
        )
        storage._conn.commit()

        manager.embedding_generator = MagicMock()
        manager.embedding_generator.get_embedding_dimension.return_value = 3
        with patch("ai_actuarial.rag.indexing.VectorStore") as mock_vector_store, patch.object(
            IndexingPipeline,
            "_index_single_file",
            return_value={"success": True, "chunk_count": 1},
        ):
            pipeline = IndexingPipeline(manager)
            stats = pipeline.index_files(kb_id=kb_id, file_urls=[current_url], force_reindex=True)

        assert stats["indexed_files"] == 1
        mock_vector_store.return_value.save_index.assert_called_once()
        remaining_urls = [
            row[0]
            for row in storage._conn.execute(
                "SELECT DISTINCT file_url FROM rag_chunks WHERE kb_id = ?",
                (kb_id,),
            ).fetchall()
        ]
        assert old_url not in remaining_urls
    finally:
        storage.close()


def test_vector_store_soft_delete_ignores_invalid_indices_and_filters_search(tmp_path) -> None:
    index_path = tmp_path / "index.faiss"
    store = VectorStore(dimension=2, index_path=str(index_path))
    store.add_vectors(
        np.array([[1.0, 0.0], [0.0, 1.0], [0.8, 0.2]], dtype="float32"),
        [
            {"id": "active-a", "file_url": "a"},
            {"id": "deleted-b", "file_url": "b"},
            {"id": "active-c", "file_url": "c"},
        ],
    )

    removed = store.remove_vectors([-1, 1, 99, 1])

    assert removed == 1
    assert store.metadata[-1].get("_deleted") is not True
    results = store.search(np.array([0.0, 1.0], dtype="float32"), k=2)
    result_ids = [result["metadata"]["id"] for result in results]
    assert "deleted-b" not in result_ids
    assert len(result_ids) == 2


def test_indexing_pipeline_update_soft_deletes_old_file_vectors_before_append(tmp_path) -> None:
    kb_id = "kb-update-soft-delete"
    file_url = "https://example.com/update.pdf"
    storage = Storage(str(tmp_path / "update-soft-delete.db"))
    try:
        storage.insert_file(
            url=file_url,
            sha256="sha-update",
            title="Update",
            source_site="example.com",
            source_page_url="https://example.com",
            original_filename="update.pdf",
            local_path=str(tmp_path / "update.pdf"),
            bytes=1024,
            content_type="application/pdf",
        )
        storage.update_file_markdown(file_url, "# Updated\n\nNew content", "manual")
        manager = KnowledgeBaseManager(storage, config=RAGConfig(data_dir=str(tmp_path / "rag-data")))
        manager.create_kb(kb_id, "Update Soft Delete KB", kb_mode="manual")
        manager.add_files_to_kb(kb_id, [file_url])
        manager.chunker = SimpleNamespace(
            chunk_document=lambda _content, metadata: [
                Chunk(
                    content="New chunk",
                    chunk_index=0,
                    token_count=2,
                    section_hierarchy="Updated",
                    metadata=metadata,
                )
            ]
        )
        manager.embedding_generator = SimpleNamespace(
            provider="openai",
            get_embedding_dimension=lambda: 3,
            generate_embeddings=lambda texts: [[0.0, 1.0, 0.0] for _text in texts],
        )

        class FakeVectorStore:
            def __init__(self) -> None:
                self.metadata = [
                    {"kb_id": kb_id, "file_url": file_url, "content": "Old chunk"},
                    {"kb_id": kb_id, "file_url": "https://example.com/other.pdf", "content": "Other chunk"},
                ]

            def add_vectors(self, _vectors, metadata):
                self.metadata.extend(metadata)

        vector_store = FakeVectorStore()
        pipeline = IndexingPipeline(manager)

        result = pipeline._index_single_file(kb_id, file_url, vector_store)  # noqa: SLF001

        assert result == {"success": True, "chunk_count": 1}
        assert vector_store.metadata[0].get("_deleted") is True
        assert vector_store.metadata[1].get("_deleted") is not True
        assert vector_store.metadata[2]["file_url"] == file_url
        assert vector_store.metadata[2].get("_deleted") is not True
    finally:
        storage.close()


def test_remove_files_from_kb_soft_deletes_file_vectors(tmp_path) -> None:
    kb_id = "kb-remove-soft-delete"
    removed_url = "https://example.com/remove-me.pdf"
    kept_url = "https://example.com/keep-me.pdf"
    storage = Storage(str(tmp_path / "remove-soft-delete.db"))
    try:
        for file_url, title in [(removed_url, "Remove"), (kept_url, "Keep")]:
            storage.insert_file(
                url=file_url,
                sha256=f"sha-{title}",
                title=title,
                source_site="example.com",
                source_page_url="https://example.com",
                original_filename=f"{title.lower()}.pdf",
                local_path=str(tmp_path / f"{title.lower()}.pdf"),
                bytes=1024,
                content_type="application/pdf",
            )
        manager = KnowledgeBaseManager(storage, config=RAGConfig(data_dir=str(tmp_path / "rag-data")))
        manager.create_kb(kb_id, "Remove Soft Delete KB", kb_mode="manual")
        manager.add_files_to_kb(kb_id, [removed_url, kept_url])
        index_path = tmp_path / "rag-data" / kb_id / "index.faiss"
        vector_store = VectorStore(dimension=3, index_path=str(index_path))
        vector_store.add_vectors(
            np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype="float32"),
            [
                {"kb_id": kb_id, "file_url": removed_url, "content": "Remove"},
                {"kb_id": kb_id, "file_url": kept_url, "content": "Keep"},
            ],
        )
        vector_store.save_index()

        removed = manager.remove_files_from_kb(kb_id, [removed_url])

        assert removed == 1
        reloaded = VectorStore(dimension=3, index_path=str(index_path))
        assert reloaded.metadata[0].get("_deleted") is True
        assert reloaded.metadata[1].get("_deleted") is not True
    finally:
        storage.close()


def test_indexing_pipeline_keeps_index_when_version_recording_fails(tmp_path) -> None:
    kb_id = "kb-index-version-warning"
    storage = SimpleNamespace(create_kb_index_version=MagicMock(side_effect=RuntimeError("locked database")))
    embedding_generator = MagicMock()
    embedding_generator.get_embedding_dimension.return_value = 3
    kb = SimpleNamespace(
        name="Versioned KB",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        embedding_dimension=3,
        index_type="Flat",
        chunk_count=4,
    )
    kb_manager = SimpleNamespace(
        storage=storage,
        config=SimpleNamespace(data_dir=str(tmp_path)),
        chunker=object(),
        embedding_generator=embedding_generator,
        get_current_embedding_metadata=MagicMock(
            return_value={
                "provider": "openai",
                "model": "text-embedding-3-small",
                "dimension": 3,
            }
        ),
        sync_kb_embedding_metadata=MagicMock(
            return_value={
                "provider": "openai",
                "model": "text-embedding-3-small",
                "dimension": 3,
            }
        ),
        get_kb=MagicMock(return_value=kb),
    )

    with patch("ai_actuarial.rag.indexing.VectorStore") as mock_vector_store, patch.object(
        IndexingPipeline,
        "_index_single_file",
        return_value={"success": True, "chunk_count": 4},
    ), patch.object(IndexingPipeline, "_update_kb_stats"):
        pipeline = IndexingPipeline(kb_manager)
        stats = pipeline.index_files(
            kb_id=kb_id,
            file_urls=["file-1"],
            force_reindex=True,
        )

    assert stats["indexed_files"] == 1
    mock_vector_store.return_value.save_index.assert_called_once()
    storage.create_kb_index_version.assert_called_once()


def test_native_task_runtime_runs_rag_indexing_collection(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "sites.yaml"
    db_path = tmp_path / "runtime-rag.db"
    download_dir = tmp_path / "files"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {download_dir.as_posix()}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))

    from ai_actuarial.task_runtime import NativeTaskRuntime

    fake_manager = MagicMock()
    fake_manager.get_kb.return_value = SimpleNamespace(name="Runtime RAG KB")
    fake_manager.get_kb_files.return_value = [
        {"file_url": "file-1"},
        {"file_url": "file-2"},
    ]
    fake_pipeline = MagicMock()
    fake_pipeline.index_files.return_value = {
        "total_files": 2,
        "indexed_files": 2,
        "skipped_files": 0,
        "error_files": 0,
        "total_chunks": 6,
        "errors": [],
        "stopped": False,
    }

    runtime = NativeTaskRuntime()
    with patch("ai_actuarial.task_runtime.KnowledgeBaseManager", return_value=fake_manager), patch(
        "ai_actuarial.task_runtime.IndexingPipeline",
        return_value=fake_pipeline,
    ) as pipeline_cls:
        result = runtime._run_collection(
            "task-rag",
            "rag_indexing",
            {"kb_id": "kb-runtime", "force_reindex": True},
        )

    assert result.success is True
    assert result.items_found == 2
    assert result.items_downloaded == 2
    assert result.items_skipped == 0
    assert result.metadata["kb_id"] == "kb-runtime"
    assert result.metadata["total_chunks"] == 6
    pipeline_cls.assert_called_once()
    _, pipeline_kwargs = pipeline_cls.call_args
    assert callable(pipeline_kwargs["stop_check"])
    assert pipeline_kwargs["stop_check"]() is False
    fake_pipeline.index_files.assert_called_once_with(
        "kb-runtime",
        ["file-1", "file-2"],
        force_reindex=True,
    )


def test_native_task_runtime_catalog_uses_yaml_routing_for_explicit_file_urls(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "sites.yaml"
    db_path = tmp_path / "runtime-catalog.db"
    download_dir = tmp_path / "files"
    updates_dir = tmp_path / "updates"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {download_dir.as_posix()}",
                f"  updates_dir: {updates_dir.as_posix()}",
                "ai_config:",
                "  catalog:",
                "    provider: openai",
                "    model: gpt-5.4-mini",
                "    system_prompt: Custom prompt",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))

    from ai_actuarial.task_runtime import NativeTaskRuntime

    runtime = NativeTaskRuntime()
    with patch(
        "ai_actuarial.task_runtime.run_catalog_for_urls",
        return_value={"scanned": 1, "processed": 1, "skipped_ai": 0, "errors": 0, "stopped": False},
    ) as mock_for_urls, patch("ai_actuarial.task_runtime.run_incremental_catalog") as mock_incremental:
        result = runtime._run_collection(
            "task-catalog",
            "catalog",
            {
                "file_urls": ["https://example.com/a.pdf"],
                "input_source": "markdown",
                "overwrite_existing": True,
                "update_title": True,
                "output_language": "zh",
            },
        )

    assert result.success is True
    assert result.metadata["provider"] == "openai"
    assert result.metadata["catalog_version"] == "v2-keybert:openai:markdown"
    mock_incremental.assert_not_called()
    kwargs = mock_for_urls.call_args.kwargs
    assert kwargs["file_urls"] == ["https://example.com/a.pdf"]
    assert kwargs["provider"] == "openai"
    assert kwargs["input_source"] == "markdown"
    assert kwargs["skip_existing"] is False
    assert kwargs["update_title"] is True
    assert kwargs["output_language"] == "zh"
    assert kwargs["catalog_system_prompt"] == "Custom prompt"


def test_native_task_runtime_catalog_scan_uses_stats_version_and_scan_window(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "sites.yaml"
    db_path = tmp_path / "runtime-catalog-scan.db"
    download_dir = tmp_path / "files"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {download_dir.as_posix()}",
                "ai_config:",
                "  catalog:",
                "    provider: mistral",
                "    model: mistral-small-latest",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))

    from ai_actuarial.task_runtime import NativeTaskRuntime

    runtime = NativeTaskRuntime()
    with patch(
        "ai_actuarial.task_runtime.run_incremental_catalog",
        return_value={"scanned": 2, "processed": 2, "skipped_ai": 0, "errors": 0, "stopped": False},
    ) as mock_incremental, patch("ai_actuarial.task_runtime.run_catalog_for_urls") as mock_for_urls:
        result = runtime._run_collection(
            "task-catalog-scan",
            "catalog",
            {
                "scan_count": "12",
                "scan_start_index": "3",
                "input_source": "source",
                "skip_existing": False,
            },
        )

    assert result.success is True
    assert result.metadata["provider"] == "mistral"
    assert result.metadata["catalog_version"] == "v2-keybert:mistral:source"
    mock_for_urls.assert_not_called()
    kwargs = mock_incremental.call_args.kwargs
    assert kwargs["provider"] == "mistral"
    assert kwargs["limit"] == 12
    assert kwargs["candidate_offset"] == 2
    assert kwargs["skip_existing"] is False


def test_native_task_runtime_quick_check_uses_submitted_url_config(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "sites.yaml"
    db_path = tmp_path / "runtime-quick.db"
    download_dir = tmp_path / "files"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {download_dir.as_posix()}",
                "defaults:",
                "  user_agent: test-agent/1.0",
                "  max_pages: 20",
                "  max_depth: 4",
                "  file_exts: ['.pdf']",
                "sites:",
                "  - name: Configured Site",
                "    url: https://configured.example",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))

    from ai_actuarial.task_runtime import NativeTaskRuntime

    fake_crawler = MagicMock()
    fake_crawler.crawl_site.return_value = [{"local_path": str(tmp_path / "report.pdf")}]

    runtime = NativeTaskRuntime()
    with patch("ai_actuarial.task_runtime.Crawler", return_value=fake_crawler):
        result = runtime._run_collection(
            "task-quick",
            "quick_check",
            {
                "name": "Quick URL",
                "url": "https://submitted.example/start",
                "max_pages": "3",
                "max_depth": "2",
                "keywords": ["risk"],
                "file_exts": [".docx"],
                "check_database": False,
            },
        )

    assert result.success is True
    site_cfg = fake_crawler.crawl_site.call_args.args[0]
    assert site_cfg.url == "https://submitted.example/start"
    assert site_cfg.max_pages == 3
    assert site_cfg.max_depth == 2
    assert site_cfg.keywords == ["risk"]
    assert site_cfg.file_exts == [".docx"]
    assert site_cfg.check_database is False


def test_native_task_runtime_search_uses_selected_engine_and_db_credentials(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "sites.yaml"
    db_path = tmp_path / "runtime-search.db"
    download_dir = tmp_path / "files"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {download_dir.as_posix()}",
                "defaults:",
                "  user_agent: test-agent/1.0",
                "  keywords: [actuarial]",
                "  file_exts: ['.pdf']",
                "search:",
                "  max_results: 5",
                "  languages: [en]",
                "  country: us",
                "  exclude_keywords: [newsletter]",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))

    from ai_actuarial.task_runtime import NativeTaskRuntime

    fake_crawler = MagicMock()
    fake_crawler.scan_page_for_files.return_value = [{"local_path": str(tmp_path / "report.pdf")}]
    runtime = NativeTaskRuntime()
    search_result = SimpleNamespace(url="https://example.com/report", source="Search")
    with patch(
        "ai_actuarial.task_runtime.get_search_runtime_credentials",
        return_value={"brave": "brave-key", "google": "google-key", "serper": None, "tavily": None},
    ), patch("ai_actuarial.task_runtime.search_all", return_value=[search_result]) as mock_search, patch(
        "ai_actuarial.task_runtime.Crawler",
        return_value=fake_crawler,
    ):
        result = runtime._run_collection(
            "task-search",
            "search",
            {
                "query": "actuarial AI",
                "engine": "brave",
                "count": "7",
                "site": "example.com",
                "search_lang": "zh",
                "file_exts": [".pdf"],
                "use_search_defaults": True,
            },
        )

    assert result.success is True
    args = mock_search.call_args.args
    assert args[0] == ["actuarial AI site:example.com"]
    assert args[1] == 7
    assert args[2] == "brave-key"
    assert args[3] is None
    assert mock_search.call_args.kwargs["languages"] == ["zh"]
    assert mock_search.call_args.kwargs["country"] == "us"
    site_cfg = fake_crawler.scan_page_for_files.call_args.args[1]
    assert site_cfg.file_exts == [".pdf"]
    assert site_cfg.exclude_keywords == ["newsletter"]
    assert site_cfg.check_database is True


def test_native_task_runtime_search_passes_check_database_false_to_scan_config(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "sites.yaml"
    db_path = tmp_path / "runtime-search-no-db-check.db"
    download_dir = tmp_path / "files"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {download_dir.as_posix()}",
                "search:",
                "  max_results: 5",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))

    from ai_actuarial.task_runtime import NativeTaskRuntime

    fake_crawler = MagicMock()
    fake_crawler.scan_page_for_files.return_value = [{"local_path": str(tmp_path / "report.pdf")}]
    runtime = NativeTaskRuntime()
    search_result = SimpleNamespace(url="https://example.com/report", source="Search")
    with patch(
        "ai_actuarial.task_runtime.get_search_runtime_credentials",
        return_value={"brave": "brave-key", "google": None, "serper": None, "tavily": None},
    ), patch("ai_actuarial.task_runtime.search_all", return_value=[search_result]), patch(
        "ai_actuarial.task_runtime.Crawler",
        return_value=fake_crawler,
    ):
        result = runtime._run_collection(
            "task-search-no-db-check",
            "search",
            {
                "query": "actuarial AI",
                "engine": "brave",
                "check_database": False,
            },
        )

    assert result.success is True
    site_cfg = fake_crawler.scan_page_for_files.call_args.args[1]
    assert site_cfg.check_database is False


def test_native_task_runtime_missing_site_results_do_not_enqueue_search_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    from ai_actuarial.task_runtime import NativeTaskRuntime

    runtime = NativeTaskRuntime()
    runtime.start_background_task = MagicMock(return_value="child-not-used")
    result = CollectionResult(
        success=True,
        items_found=0,
        items_downloaded=0,
        items_skipped=0,
        errors=[],
        metadata=None,
    )
    site_configs = [
        SiteConfig(
            name="Configured Site",
            url="https://configured.example",
            queries=["actuarial report"],
        )
    ]

    runtime._enqueue_site_query_search_fallbacks(
        "task-missing-site-results",
        {"search": {"enabled": True}},
        result,
        site_configs,
        {},
    )

    assert result.metadata == {
        "search_fallback_enqueued": 0,
        "search_fallback_task_ids": [],
    }
    runtime.start_background_task.assert_not_called()


def test_native_task_runtime_unmatched_site_result_does_not_enqueue_search_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    from ai_actuarial.task_runtime import NativeTaskRuntime

    runtime = NativeTaskRuntime()
    runtime.start_background_task = MagicMock(return_value="child-not-used")
    result = CollectionResult(
        success=True,
        items_found=0,
        items_downloaded=0,
        items_skipped=0,
        errors=[],
        metadata={
            "site_results": [
                {
                    "name": "Different Site",
                    "url": "https://different.example",
                    "items_found": 0,
                    "success": True,
                    "fallback_reason": "zero_results",
                }
            ]
        },
    )
    site_configs = [
        SiteConfig(
            name="Configured Site",
            url="https://configured.example",
            queries=["actuarial report"],
        )
    ]

    runtime._enqueue_site_query_search_fallbacks(
        "task-unmatched-site-results",
        {"search": {"enabled": True}},
        result,
        site_configs,
        {},
    )

    assert result.metadata["search_fallback_enqueued"] == 0
    assert result.metadata["search_fallback_task_ids"] == []
    runtime.start_background_task.assert_not_called()


def test_native_task_runtime_scheduled_success_with_queries_does_not_enqueue_search_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "sites.yaml"
    db_path = tmp_path / "runtime-scheduled-success.db"
    download_dir = tmp_path / "files"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {download_dir.as_posix()}",
                "defaults:",
                "  user_agent: test-agent/1.0",
                "  keywords: [actuarial]",
                "  file_exts: ['.pdf']",
                "  exclude_keywords: [draft]",
                "search:",
                "  enabled: true",
                "  max_results: 4",
                "sites:",
                "  - name: Direct Site",
                "    url: https://direct.example",
                "    queries:",
                "      - site:direct.example actuarial report",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))

    from ai_actuarial.task_runtime import NativeTaskRuntime

    fake_crawler = MagicMock()
    fake_crawler.crawl_site.return_value = [{"local_path": str(tmp_path / "direct.pdf")}]
    runtime = NativeTaskRuntime()
    runtime.start_background_task = MagicMock(return_value="child-not-used")

    with patch.object(runtime, "_run_search_task", wraps=runtime._run_search_task) as mock_run_search_task, patch(
        "ai_actuarial.task_runtime.search_all"
    ) as mock_search, patch(
        "ai_actuarial.task_runtime.Crawler",
        return_value=fake_crawler,
    ):
        result = runtime._run_collection("task-scheduled-success", "scheduled", {"check_database": False})

    assert result.success is True
    assert result.items_found == 1
    assert result.items_downloaded == 1
    assert result.metadata["search_fallback_enqueued"] == 0
    assert result.metadata["search_fallback_task_ids"] == []
    assert result.metadata["site_results"][0]["fallback_reason"] == "success"
    runtime.start_background_task.assert_not_called()
    mock_run_search_task.assert_not_called()
    mock_search.assert_not_called()


def test_native_task_runtime_scheduled_blocked_outcome_enqueues_search_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "sites.yaml"
    db_path = tmp_path / "runtime-scheduled-blocked.db"
    download_dir = tmp_path / "files"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {download_dir.as_posix()}",
                "defaults:",
                "  user_agent: test-agent/1.0",
                "  keywords: [actuarial]",
                "  file_exts: ['.pdf']",
                "  exclude_keywords: [draft]",
                "search:",
                "  enabled: true",
                "  engine: serper",
                "  max_results: 4",
                "sites:",
                "  - name: Anti Bot Site",
                "    url: https://anti.example",
                "    queries: ['site:anti.example actuarial report']",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))

    from ai_actuarial.task_runtime import NativeTaskRuntime

    fake_crawler = MagicMock()
    fake_crawler.crawl_site.side_effect = RuntimeError("403 Forbidden by Cloudflare")
    runtime = NativeTaskRuntime()
    runtime.start_background_task = MagicMock(return_value="child-search-1")

    with patch.object(runtime, "_run_search_task", wraps=runtime._run_search_task) as mock_run_search_task, patch(
        "ai_actuarial.task_runtime.search_all"
    ) as mock_search, patch(
        "ai_actuarial.task_runtime.Crawler",
        return_value=fake_crawler,
    ):
        result = runtime._run_collection("task-scheduled-blocked", "scheduled", {})

    assert result.success is False
    assert result.items_found == 0
    assert result.metadata["search_fallback_enqueued"] == 1
    assert result.metadata["search_fallback_task_ids"] == ["child-search-1"]
    site_result = result.metadata["site_results"][0]
    assert site_result["failed"] is True
    assert site_result["blocked"] is True
    assert site_result["fallback_reason"] == "http_403"
    runtime.start_background_task.assert_called_once()
    collection_type, payload = runtime.start_background_task.call_args.args
    assert collection_type == "search"
    assert payload == {
        "name": "Anti Bot Site",
        "query": "site:anti.example actuarial report",
        "site": "anti.example",
        "engine": "serper",
        "count": 4,
        "use_search_defaults": True,
        "file_exts": [".pdf"],
        "keywords": ["actuarial"],
        "search_exclude_keywords": ["draft"],
        "check_database": True,
    }
    assert (
        runtime.start_background_task.call_args.kwargs["task_name"]
        == "Search fallback: Anti Bot Site (1/1): site:anti.example actuarial report"
    )
    assert runtime.start_background_task.call_args.kwargs["extra_fields"] == {
        "parent_task_id": "task-scheduled-blocked",
        "trigger": "crawler_fallback",
        "fallback_reason": "http_403",
    }
    mock_run_search_task.assert_not_called()
    mock_search.assert_not_called()
    log_text = (tmp_path / "data" / "task_logs" / "task-scheduled-blocked.log").read_text(encoding="utf-8")
    assert "enqueued search fallback task child-search-1" in log_text


def test_native_task_runtime_search_fallback_prefers_query_site_domain_for_www_site_config() -> None:
    from ai_actuarial.search import SearchResult
    from ai_actuarial.task_runtime import NativeTaskRuntime

    runtime = NativeTaskRuntime()
    site_config = SiteConfig(
        name="SOA",
        url="https://www.soa.org",
        file_exts=[".pdf"],
        queries=["site:soa.org actuarial report"],
    )

    payload = runtime._site_query_search_task_data(
        site_config,
        "site:soa.org actuarial report",
        {"search": {"enabled": True, "max_results": 5}},
        {},
    )

    assert payload["site"] == "soa.org"
    assert payload["query"] == "site:soa.org actuarial report"
    assert runtime._query_with_site_filter(payload["query"], payload["site"]) == "site:soa.org actuarial report"
    assert runtime._dedupe_search_results(
        [
            SearchResult(url="https://soa.org/resources/research-report.pdf", source="test"),
            SearchResult(url="https://www.soa.org/news/article", source="test"),
            SearchResult(url="https://example.com/other.pdf", source="test"),
        ],
        site_filter=payload["site"],
    ) == [
        SearchResult(url="https://soa.org/resources/research-report.pdf", source="test"),
        SearchResult(url="https://www.soa.org/news/article", source="test"),
    ]


def test_native_task_runtime_scheduled_zero_result_outcome_enqueues_brave_search_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "sites.yaml"
    db_path = tmp_path / "runtime-scheduled-zero.db"
    download_dir = tmp_path / "files"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {download_dir.as_posix()}",
                "defaults:",
                "  user_agent: test-agent/1.0",
                "  file_exts: ['.pdf']",
                "search:",
                "  enabled: true",
                "sites:",
                "  - name: Empty Site",
                "    url: https://empty.example",
                "    queries: ['actuarial report']",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))

    from ai_actuarial.task_runtime import NativeTaskRuntime

    fake_crawler = MagicMock()
    fake_crawler.crawl_site.return_value = []
    runtime = NativeTaskRuntime()
    runtime.start_background_task = MagicMock(return_value="child-search-zero")

    with patch.object(runtime, "_run_search_task", wraps=runtime._run_search_task) as mock_run_search_task, patch(
        "ai_actuarial.task_runtime.search_all"
    ) as mock_search, patch(
        "ai_actuarial.task_runtime.Crawler",
        return_value=fake_crawler,
    ):
        result = runtime._run_collection("task-scheduled-zero", "scheduled", {})

    assert result.success is True
    assert result.items_found == 0
    assert result.metadata["search_fallback_enqueued"] == 1
    assert result.metadata["site_results"][0]["fallback_reason"] == "zero_results"
    collection_type, payload = runtime.start_background_task.call_args.args
    assert collection_type == "search"
    assert payload["engine"] == "brave"
    assert payload["query"] == "actuarial report"
    assert payload["site"] == "empty.example"
    assert payload["use_search_defaults"] is True
    assert payload["check_database"] is True
    assert runtime.start_background_task.call_args.kwargs["extra_fields"] == {
        "parent_task_id": "task-scheduled-zero",
        "trigger": "crawler_fallback",
        "fallback_reason": "zero_results",
    }
    mock_run_search_task.assert_not_called()
    mock_search.assert_not_called()


def test_native_task_runtime_scheduled_search_disabled_does_not_enqueue_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "sites.yaml"
    db_path = tmp_path / "runtime-scheduled-disabled.db"
    download_dir = tmp_path / "files"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {download_dir.as_posix()}",
                "search:",
                "  enabled: false",
                "sites:",
                "  - name: Disabled Fallback Site",
                "    url: https://disabled.example",
                "    queries: ['actuarial report']",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))

    from ai_actuarial.task_runtime import NativeTaskRuntime

    fake_crawler = MagicMock()
    fake_crawler.crawl_site.return_value = []
    runtime = NativeTaskRuntime()
    runtime.start_background_task = MagicMock(return_value="child-not-used")

    with patch.object(runtime, "_run_search_task", wraps=runtime._run_search_task) as mock_run_search_task, patch(
        "ai_actuarial.task_runtime.search_all"
    ) as mock_search, patch(
        "ai_actuarial.task_runtime.Crawler",
        return_value=fake_crawler,
    ):
        result = runtime._run_collection("task-scheduled-disabled", "scheduled", {})

    assert result.success is True
    assert result.items_found == 0
    assert result.metadata["site_results"][0]["fallback_reason"] == "zero_results"
    assert result.metadata["search_fallback_enqueued"] == 0
    assert result.metadata["search_fallback_task_ids"] == []
    runtime.start_background_task.assert_not_called()
    mock_run_search_task.assert_not_called()
    mock_search.assert_not_called()


def test_native_task_runtime_scheduled_site_without_queries_does_not_enqueue_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "sites.yaml"
    db_path = tmp_path / "runtime-scheduled-no-queries.db"
    download_dir = tmp_path / "files"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {download_dir.as_posix()}",
                "search:",
                "  enabled: true",
                "sites:",
                "  - name: No Query Site",
                "    url: https://no-query.example",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))

    from ai_actuarial.task_runtime import NativeTaskRuntime

    fake_crawler = MagicMock()
    fake_crawler.crawl_site.side_effect = RuntimeError("403 Forbidden")
    runtime = NativeTaskRuntime()
    runtime.start_background_task = MagicMock(return_value="child-not-used")

    with patch.object(runtime, "_run_search_task", wraps=runtime._run_search_task) as mock_run_search_task, patch(
        "ai_actuarial.task_runtime.search_all"
    ) as mock_search, patch(
        "ai_actuarial.task_runtime.Crawler",
        return_value=fake_crawler,
    ):
        result = runtime._run_collection("task-scheduled-no-queries", "scheduled", {})

    assert result.success is False
    assert result.metadata["site_results"][0]["fallback_reason"] == "http_403"
    assert result.metadata["search_fallback_enqueued"] == 0
    assert result.metadata["search_fallback_task_ids"] == []
    runtime.start_background_task.assert_not_called()
    mock_run_search_task.assert_not_called()
    mock_search.assert_not_called()


def test_native_task_runtime_scheduled_multiple_queries_enqueue_multiple_child_tasks(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "sites.yaml"
    db_path = tmp_path / "runtime-scheduled-multi-query.db"
    download_dir = tmp_path / "files"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {download_dir.as_posix()}",
                "defaults:",
                "  keywords: [solvency]",
                "  file_exts: ['.pdf']",
                "search:",
                "  enabled: true",
                "  engine: tavily",
                "  max_results: 3",
                "sites:",
                "  - name: Multi Query Site",
                "    url: https://multi.example",
                "    queries:",
                "      - actuarial annual report",
                "      - solvency filing",
                "      - ''",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))

    from ai_actuarial.task_runtime import NativeTaskRuntime

    fake_crawler = MagicMock()
    fake_crawler.crawl_site.return_value = []
    runtime = NativeTaskRuntime()
    runtime.start_background_task = MagicMock(side_effect=["child-search-1", "child-search-2"])

    with patch.object(runtime, "_run_search_task", wraps=runtime._run_search_task) as mock_run_search_task, patch(
        "ai_actuarial.task_runtime.search_all"
    ) as mock_search, patch(
        "ai_actuarial.task_runtime.Crawler",
        return_value=fake_crawler,
    ):
        result = runtime._run_collection("task-scheduled-multi-query", "scheduled", {})

    assert result.success is True
    assert result.metadata["search_fallback_enqueued"] == 2
    assert result.metadata["search_fallback_task_ids"] == ["child-search-1", "child-search-2"]
    assert runtime.start_background_task.call_count == 2
    payloads = [call.args[1] for call in runtime.start_background_task.call_args_list]
    assert [payload["query"] for payload in payloads] == ["actuarial annual report", "solvency filing"]
    assert all(payload["site"] == "multi.example" for payload in payloads)
    assert all(payload["engine"] == "tavily" for payload in payloads)
    assert all(payload["count"] == 3 for payload in payloads)
    assert all(payload["file_exts"] == [".pdf"] for payload in payloads)
    assert all(payload["keywords"] == ["solvency"] for payload in payloads)
    task_names = [call.kwargs["task_name"] for call in runtime.start_background_task.call_args_list]
    assert task_names == [
        "Search fallback: Multi Query Site (1/2): actuarial annual report",
        "Search fallback: Multi Query Site (2/2): solvency filing",
    ]
    assert [call.kwargs["extra_fields"]["fallback_reason"] for call in runtime.start_background_task.call_args_list] == [
        "zero_results",
        "zero_results",
    ]
    mock_run_search_task.assert_not_called()
    mock_search.assert_not_called()


def test_native_task_runtime_search_task_does_not_enqueue_recursive_fallback(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "sites.yaml"
    db_path = tmp_path / "runtime-search-no-recursion.db"
    download_dir = tmp_path / "files"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {download_dir.as_posix()}",
                "search:",
                "  enabled: true",
                "  max_results: 5",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))

    from ai_actuarial.task_runtime import NativeTaskRuntime

    runtime = NativeTaskRuntime()
    runtime.start_background_task = MagicMock(return_value="child-not-used")
    with patch(
        "ai_actuarial.task_runtime.get_search_runtime_credentials",
        return_value={"brave": "brave-key", "google": None, "serper": None, "tavily": None},
    ), patch("ai_actuarial.task_runtime.search_all", return_value=[]) as mock_search, patch(
        "ai_actuarial.task_runtime.Crawler"
    ) as mock_crawler:
        result = runtime._run_collection(
            "task-search-no-recursion",
            "search",
            {"query": "actuarial report", "engine": "brave", "site": "example.com"},
        )

    assert result.success is True
    assert result.items_found == 0
    assert result.metadata["source_type"] == "search"
    assert result.metadata["search_results"] == 0
    assert "search_fallback_enqueued" not in result.metadata
    runtime.start_background_task.assert_not_called()
    mock_search.assert_called_once()
    mock_crawler.return_value.scan_page_for_files.assert_not_called()


def test_native_task_runtime_markdown_conversion_writes_db_markdown(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "sites.yaml"
    db_path = tmp_path / "runtime-markdown.db"
    download_dir = tmp_path / "files"
    source_file = tmp_path / "source.pdf"
    source_file.write_bytes(b"%PDF-1.4\n")
    file_url = "https://example.com/source.pdf"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {download_dir.as_posix()}",
                "ai_config:",
                "  ocr:",
                "    provider: local",
                "    model: docling",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    storage = Storage(str(db_path))
    try:
        storage.insert_file(
            url=file_url,
            sha256="sha-md",
            title="Source",
            source_site="example.com",
            source_page_url="https://example.com",
            original_filename="source.pdf",
            local_path=str(source_file),
            bytes=source_file.stat().st_size,
            content_type="application/pdf",
        )
    finally:
        storage.close()

    from ai_actuarial.task_runtime import NativeTaskRuntime

    runtime = NativeTaskRuntime()
    with patch(
        "ai_actuarial.task_runtime._convert_document_path",
        return_value=SimpleNamespace(markdown="# Converted", engine="docling", model="docling"),
    ) as mock_convert:
        result = runtime._run_collection(
            "task-md",
            "markdown_conversion",
            {"file_urls": [file_url], "conversion_tool": "docling", "overwrite_existing": True},
        )

    assert result.success is True
    mock_convert.assert_called_once()
    storage = Storage(str(db_path))
    try:
        markdown = storage.get_file_markdown(file_url)
    finally:
        storage.close()
    assert markdown["markdown_content"] == "# Converted"
    assert markdown["markdown_source"] == "docling:docling"


def test_native_task_runtime_chunk_generation_uses_existing_service(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "sites.yaml"
    db_path = tmp_path / "runtime-chunk.db"
    download_dir = tmp_path / "files"
    file_url = "https://example.com/source.pdf"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {download_dir.as_posix()}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    storage = Storage(str(db_path))
    try:
        storage.insert_file(
            url=file_url,
            sha256="sha-chunk",
            title="Source",
            source_site="example.com",
            source_page_url="https://example.com",
            original_filename="source.pdf",
            local_path=str(tmp_path / "source.pdf"),
            bytes=12,
            content_type="application/pdf",
        )
        storage.update_file_markdown(file_url, "# Markdown", "manual")
    finally:
        storage.close()

    from ai_actuarial.task_runtime import NativeTaskRuntime

    runtime = NativeTaskRuntime()
    with patch(
        "ai_actuarial.task_runtime.generate_file_chunk_sets",
        return_value={"chunk_set_id": "cs-test", "chunk_count": 3, "reused_existing": False},
    ) as mock_generate:
        result = runtime._run_collection(
            "task-chunk",
            "chunk_generation",
            {
                "file_urls": [file_url],
                "profile_name": "Task Profile",
                "chunk_size": "120",
                "chunk_overlap": "20",
                "overwrite_same_profile": True,
            },
        )

    assert result.success is True
    assert result.metadata["total_chunks"] == 3
    kwargs = mock_generate.call_args.kwargs
    assert Path(kwargs["db_path"]) == db_path.resolve()
    assert kwargs["file_url"] == file_url
    assert kwargs["payload"]["name"] == "Task Profile"
    assert kwargs["payload"]["chunk_size"] == 120
    assert kwargs["payload"]["chunk_overlap"] == 20


def test_native_task_runtime_chunk_generation_filters_existing_chunks_by_selected_profile(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "sites.yaml"
    db_path = tmp_path / "runtime-chunk-profile.db"
    download_dir = tmp_path / "files"
    file_url = "https://example.com/profile-source.pdf"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {download_dir.as_posix()}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    storage = Storage(str(db_path))
    try:
        storage.insert_file(
            url=file_url,
            sha256="sha-profile-chunk",
            title="Profile Source",
            source_site="example.com",
            source_page_url="https://example.com",
            original_filename="profile-source.pdf",
            local_path=str(tmp_path / "profile-source.pdf"),
            bytes=12,
            content_type="application/pdf",
        )
        storage.update_file_markdown(file_url, "# Profile Markdown", "manual")
        selected_profile = storage.create_chunk_profile(
            name="Selected Profile",
            chunk_size=300,
            chunk_overlap=40,
        )
        other_profile = storage.create_chunk_profile(
            name="Other Profile",
            chunk_size=500,
            chunk_overlap=80,
        )
        storage.get_or_create_file_chunk_set(
            file_url=file_url,
            profile_id=other_profile["profile_id"],
            markdown_hash="other-profile-hash",
            status="ready",
        )
    finally:
        storage.close()

    from ai_actuarial.task_runtime import NativeTaskRuntime

    runtime = NativeTaskRuntime()
    with patch(
        "ai_actuarial.task_runtime.generate_file_chunk_sets",
        return_value={"chunk_set_id": "cs-selected", "chunk_count": 4, "reused_existing": False},
    ) as mock_generate:
        result = runtime._run_collection(
            "task-chunk-profile",
            "chunk_generation",
            {
                "profile_id": selected_profile["profile_id"],
                "scan_count": "10",
                "overwrite_same_profile": False,
            },
        )

    assert result.success is True
    assert result.items_found == 1
    mock_generate.assert_called_once()
    assert mock_generate.call_args.kwargs["payload"]["profile_id"] == selected_profile["profile_id"]


def test_native_task_runtime_chunk_generation_resolves_custom_profile_before_filtering(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "sites.yaml"
    db_path = tmp_path / "runtime-chunk-custom-profile.db"
    download_dir = tmp_path / "files"
    file_url = "https://example.com/custom-profile-source.pdf"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {download_dir.as_posix()}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    storage = Storage(str(db_path))
    try:
        storage.insert_file(
            url=file_url,
            sha256="sha-custom-profile-chunk",
            title="Custom Profile Source",
            source_site="example.com",
            source_page_url="https://example.com",
            original_filename="custom-profile-source.pdf",
            local_path=str(tmp_path / "custom-profile-source.pdf"),
            bytes=12,
            content_type="application/pdf",
        )
        storage.update_file_markdown(file_url, "# Custom Profile Markdown", "manual")
        other_profile = storage.create_chunk_profile(
            name="Existing Other Profile",
            chunk_size=400,
            chunk_overlap=50,
        )
        storage.get_or_create_file_chunk_set(
            file_url=file_url,
            profile_id=other_profile["profile_id"],
            markdown_hash="other-profile-hash",
            status="ready",
        )
    finally:
        storage.close()

    from ai_actuarial.task_runtime import NativeTaskRuntime

    runtime = NativeTaskRuntime()
    with patch(
        "ai_actuarial.task_runtime.generate_file_chunk_sets",
        return_value={"chunk_set_id": "cs-custom", "chunk_count": 5, "reused_existing": False},
    ) as mock_generate:
        result = runtime._run_collection(
            "task-chunk-custom-profile",
            "chunk_generation",
            {
                "profile_name": "New Custom Profile",
                "chunk_size": "700",
                "chunk_overlap": "80",
                "scan_count": "10",
                "overwrite_same_profile": False,
            },
        )

    assert result.success is True
    assert result.items_found == 1
    mock_generate.assert_called_once()
    payload = mock_generate.call_args.kwargs["payload"]
    assert payload["profile_id"]
    assert payload["name"] == "New Custom Profile"


def test_native_task_runtime_chunk_generation_rejects_invalid_binding_mode(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "sites.yaml"
    db_path = tmp_path / "runtime-chunk-binding-mode.db"
    download_dir = tmp_path / "files"
    file_url = "https://example.com/binding-mode-source.pdf"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {download_dir.as_posix()}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    storage = Storage(str(db_path))
    try:
        storage.insert_file(
            url=file_url,
            sha256="sha-binding-mode-chunk",
            title="Binding Mode Source",
            source_site="example.com",
            source_page_url="https://example.com",
            original_filename="binding-mode-source.pdf",
            local_path=str(tmp_path / "binding-mode-source.pdf"),
            bytes=12,
            content_type="application/pdf",
        )
        storage.update_file_markdown(file_url, "# Binding Mode Markdown", "manual")
    finally:
        storage.close()

    from ai_actuarial.task_runtime import NativeTaskRuntime

    runtime = NativeTaskRuntime()
    with pytest.raises(RuntimeError, match="binding_mode must be one of"):
        runtime._run_collection(
            "task-chunk-binding-mode",
            "chunk_generation",
            {
                "file_urls": [file_url],
                "kb_id": "kb-binding-mode",
                "binding_mode": "invalid",
            },
        )
