from __future__ import annotations

from pathlib import Path
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
