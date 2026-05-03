from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ai_actuarial.catalog import CatalogItem
from ai_actuarial.catalog_incremental import run_catalog_for_urls, run_incremental_catalog
from ai_actuarial.rag.indexing import IndexingPipeline
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
    ):
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
    fake_pipeline.index_files.assert_called_once_with(
        "kb-runtime",
        ["file-1", "file-2"],
        force_reindex=True,
    )
