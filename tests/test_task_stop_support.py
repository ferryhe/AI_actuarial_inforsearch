from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ai_actuarial.catalog_incremental import run_catalog_for_urls
from ai_actuarial.rag.indexing import IndexingPipeline
from ai_actuarial.storage import Storage


def test_run_catalog_for_urls_respects_immediate_stop(tmp_path) -> None:
    db_path = tmp_path / "catalog-stop.db"
    storage = Storage(str(db_path))
    file_urls = []
    try:
        for idx in range(2):
            file_url = f"https://example.com/catalog-stop-{idx}.pdf"
            file_urls.append(file_url)
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


def test_indexing_pipeline_stops_before_second_file(tmp_path) -> None:
    embedding_generator = MagicMock()
    embedding_generator.get_embedding_dimension.return_value = 3
    kb_manager = SimpleNamespace(
        storage=SimpleNamespace(),
        config=SimpleNamespace(data_dir=str(tmp_path)),
        chunker=object(),
        embedding_generator=embedding_generator,
        get_kb=MagicMock(
            return_value=SimpleNamespace(
                name="Stop Test KB",
                embedding_model="text-embedding-3-small",
                index_type="Flat",
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
