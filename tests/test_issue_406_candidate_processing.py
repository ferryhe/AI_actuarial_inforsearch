from __future__ import annotations

import threading
from collections import Counter
from pathlib import Path
from typing import Any

from ai_actuarial.api.services.ops_write import (
    get_catalog_stats,
    get_markdown_conversion_stats,
)
from ai_actuarial.catalog import CATALOG_VERSION, CatalogItem
from ai_actuarial.catalog_incremental import run_incremental_catalog
from ai_actuarial.collectors.base import CollectionResult
from ai_actuarial.storage import Storage
from ai_actuarial.task_runtime import NativeTaskRuntime


def _seed_files(db_path: Path, count: int, *, suffix: str = "pdf") -> list[str]:
    storage = Storage(str(db_path))
    urls: list[str] = []
    try:
        for index in range(count):
            url = f"https://example.test/{index}.{suffix}"
            urls.append(url)
            storage.insert_file(
                url=url,
                sha256=f"sha-{index}",
                title=f"Document {index}",
                source_site="example.test",
                source_page_url="https://example.test",
                original_filename=f"{index}.{suffix}",
                local_path=f"/tmp/{index}.{suffix}",
                bytes=10,
                content_type="application/pdf",
            )
    finally:
        storage.close()
    return urls


def _catalog_item(row: dict[str, Any]) -> CatalogItem:
    return CatalogItem(
        source_site=str(row["source_site"]),
        title=str(row["title"]),
        original_filename=str(row["original_filename"]),
        url=str(row["url"]),
        local_path=str(row["local_path"]),
        keywords=[],
        summary="summary",
        category="Other",
    )


def _run_mock_catalog(
    db_path: Path,
    tmp_path: Path,
    monkeypatch,
    urls: list[str],
    outcome,
    *,
    limit: int,
    batch: int = 50,
    candidate_offset: int = 0,
    progress: list[tuple[int, int, str]] | None = None,
) -> dict[str, Any]:
    by_url = {url: index for index, url in enumerate(urls)}
    calls: Counter[str] = Counter()

    def process(row: dict[str, Any], *_args: Any, **_kwargs: Any) -> tuple[Any, ...]:
        url = str(row["url"])
        calls[url] += 1
        result = outcome(by_url[url])
        return row, _catalog_item(row), result, None

    monkeypatch.setattr("ai_actuarial.catalog_incremental._process_single_row", process)
    stats = run_incremental_catalog(
        db_path=str(db_path),
        out_jsonl=tmp_path / "catalog.jsonl",
        out_md=tmp_path / "catalog.md",
        batch=batch,
        limit=limit,
        candidate_offset=candidate_offset,
        skip_existing=False,
        max_workers=1,
        progress_callback=(lambda current, total, message: progress.append(
            (current, total, message)
        ))
        if progress is not None
        else None,
    )
    stats["calls"] = calls
    return stats


def test_catalog_batches_continue_after_seen_rows_and_stop_at_success_target(
    tmp_path: Path, monkeypatch
) -> None:
    for target in (100, 75):
        db_path = tmp_path / f"catalog-{target}.db"
        urls = _seed_files(db_path, 130)
        stats = _run_mock_catalog(
            db_path,
            tmp_path / str(target),
            monkeypatch,
            urls,
            lambda _index: "ok",
            limit=target,
        )

        assert stats["processed"] == target
        assert stats["scanned"] == target
        assert sum(stats["calls"].values()) == target
        assert max(stats["calls"].values()) == 1
        assert stats["candidate_exhausted"] is False


def test_catalog_failures_are_seen_once_and_do_not_consume_success_target(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "catalog-failures.db"
    urls = _seed_files(db_path, 150)
    stats = _run_mock_catalog(
        db_path,
        tmp_path,
        monkeypatch,
        urls,
        lambda index: "error:catalog_failed" if index >= 100 else "ok",
        limit=100,
    )

    assert stats["processed"] == 100
    assert stats["errors"] == 50
    assert stats["scanned"] == 150
    assert all(stats["calls"][url] == 1 for url in urls)
    assert stats["candidate_exhausted"] is False


def test_catalog_exhaustion_reports_actual_checked_success_failed_and_skipped_counts(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "catalog-exhausted.db"
    urls = _seed_files(db_path, 80)
    progress: list[tuple[int, int, str]] = []
    stats = _run_mock_catalog(
        db_path,
        tmp_path,
        monkeypatch,
        urls,
        lambda index: (
            "skipped"
            if index >= 70
            else ("error:catalog_failed" if index >= 50 else "ok")
        ),
        limit=100,
        progress=progress,
    )

    assert stats["scanned"] == 80
    assert stats["processed"] == 50
    assert stats["errors"] == 20
    assert stats["skipped_ai"] == 10
    assert stats["scanned"] == stats["processed"] + stats["errors"] + stats["skipped_ai"]
    assert stats["candidate_exhausted"] is True
    assert progress[-1][0:2] == (50, 100)
    assert "candidates exhausted" in progress[-1][2]


def test_catalog_candidate_start_is_relative_to_candidate_list(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "catalog-offset.db"
    urls = _seed_files(db_path, 30)
    stats = _run_mock_catalog(
        db_path,
        tmp_path,
        monkeypatch,
        urls,
        lambda _index: "ok",
        limit=100,
        candidate_offset=10,
    )

    assert stats["scanned"] == 20
    assert set(stats["calls"]) == set(urls[:20])
    assert stats["candidate_exhausted"] is True


def test_catalog_empty_candidate_range_finishes_without_processing(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "catalog-empty-range.db"
    urls = _seed_files(db_path, 3)
    stats = _run_mock_catalog(
        db_path,
        tmp_path,
        monkeypatch,
        urls,
        lambda _index: "ok",
        limit=100,
        candidate_offset=99,
    )

    assert stats["scanned"] == 0
    assert stats["processed"] == 0
    assert stats["candidate_exhausted"] is True
    assert stats["calls"] == Counter()


def test_catalog_stats_first_candidate_index_uses_candidate_coordinates(tmp_path: Path) -> None:
    db_path = tmp_path / "catalog-stats.db"
    urls = _seed_files(db_path, 3)
    storage = Storage(str(db_path))
    try:
        storage._conn.execute(
            """
            INSERT INTO catalog_items (
                file_url, file_sha256, sha256, catalog_version, pipeline_version,
                summary, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                urls[-1],
                "sha-2",
                "sha-2",
                f"{CATALOG_VERSION}:local:source",
                f"{CATALOG_VERSION}:local:source",
                "cataloged",
                "ok",
            ),
        )
        storage._conn.commit()
    finally:
        storage.close()

    stats = get_catalog_stats(db_path=str(db_path), provider="local", input_source="source")
    overwrite_stats = get_catalog_stats(
        db_path=str(db_path),
        provider="local",
        input_source="source",
        overwrite_existing=True,
    )

    assert stats["candidate_total"] == 2
    assert stats["first_candidate_index"] == 1
    assert overwrite_stats["candidate_total"] == 3


def test_markdown_stats_and_execution_use_filtered_candidate_positions(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "markdown-candidates.db"
    urls = _seed_files(db_path, 2)
    storage = Storage(str(db_path))
    try:
        assert storage.update_file_markdown(urls[-1], "# Existing Markdown")[0] is True
        stats = get_markdown_conversion_stats(db_path=str(db_path))
        runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
        monkeypatch.setattr(
            "ai_actuarial.task_runtime.load_markdown_conversion_config",
            lambda: {"limits": {"default_scan_count": 50, "max_scan_count": 100}},
        )
        candidates = runtime._markdown_candidate_files(storage, {"scan_start_index": 1})
        past_candidates = runtime._markdown_candidate_files(
            storage, {"scan_start_index": 2}
        )
    finally:
        storage.close()

    assert stats["first_without_markdown_index"] == 1
    assert [row["url"] for row in candidates] == [urls[0]]
    assert past_candidates == []


def test_catalog_final_task_preserves_success_progress_and_safe_parameters(
    monkeypatch,
) -> None:
    class _UnstartedThread:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def start(self) -> None:
            pass

    monkeypatch.setattr("ai_actuarial.task_runtime.threading.Thread", _UnstartedThread)
    monkeypatch.setattr("ai_actuarial.task_runtime.append_task_log", lambda *_args: None)
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    runtime.task_lock = threading.RLock()
    runtime.active_tasks = {}
    runtime.task_history = []
    runtime._append_history_to_disk = lambda _task: None
    task_id = runtime.start_background_task(
        "catalog",
        {
            "scope_mode": "category",
            "category": "Insurance",
            "scan_start_index": 4,
            "scan_count": 100,
            "skip_existing": False,
            "overwrite_existing": True,
            "api_key": "must-not-be-persisted",
        },
    )

    runtime._finalize_task_success(
        task_id,
        "catalog",
        CollectionResult(
            success=False,
            items_found=80,
            items_downloaded=50,
            items_skipped=10,
            metadata={
                "catalog_scanned": 80,
                "catalog_ok": 50,
                "catalog_errors": 20,
                "catalog_skipped": 10,
                "catalog_target": 100,
                "catalog_candidate_exhausted": True,
                "failed_items": 20,
            },
        ),
    )
    task = runtime.task_history[-1]

    assert task["items_processed"] == 50
    assert task["items_total"] == 100
    assert task["progress"] == 50
    assert task["catalog_scanned"] == 80
    assert task["catalog_ok"] == 50
    assert task["catalog_errors"] == 20
    assert task["catalog_skipped"] == 10
    assert task["catalog_candidate_exhausted"] is True
    assert task["parameters"] == {
        "scope_mode": "category",
        "scan_start_index": 4,
        "scan_count": 100,
        "skip_existing": False,
        "overwrite_existing": True,
        "category": "Insurance",
        "target_successes": 100,
        "input_source": "markdown",
        "retry_errors": False,
    }
    assert "must-not-be-persisted" not in str(task)
