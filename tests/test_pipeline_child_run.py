from __future__ import annotations

from typing import Any

import pytest

from ai_actuarial.collectors.base import CollectionResult
from ai_actuarial.crawler import SiteConfig
from ai_actuarial.storage import Storage
from ai_actuarial.task_runtime import NativeTaskRuntime


def _make_runtime(monkeypatch: pytest.MonkeyPatch, db: str) -> NativeTaskRuntime:
    runtime = NativeTaskRuntime()
    monkeypatch.setattr(
        runtime,
        "_load_site_config",
        lambda: {"paths": {"db": db, "download_dir": db + ".files"}, "search": {"enabled": True}},
    )
    return runtime


def _result(**kwargs: Any) -> CollectionResult:
    defaults: dict[str, Any] = {
        "success": True,
        "items_found": 0,
        "items_downloaded": 0,
        "items_skipped": 0,
        "errors": [],
        "metadata": {},
    }
    defaults.update(kwargs)
    return CollectionResult(**defaults)


def test_enqueue_search_fallback_creates_child_run_linked_to_parent(monkeypatch, tmp_path) -> None:
    db = str(tmp_path / "pipeline.db")
    runtime = _make_runtime(monkeypatch, db)
    monkeypatch.setattr(runtime, "_site_search_fallback_reason", lambda site_config, outcomes: "blocked")

    seen_task_id: dict[str, str] = {}

    def fake_start_background_task(collection_type, data, **kwargs):
        seen_task_id["task_id"] = kwargs.get("task_id", "")
        seen_task_id["child_run_id"] = data.get("child_run_id", "")
        seen_task_id["parent_run_id"] = data.get("parent_run_id", "")
        return kwargs.get("task_id") or "generated"

    monkeypatch.setattr(runtime, "start_background_task", fake_start_background_task)

    site_configs = [SiteConfig(name="Anti Bot", url="https://anti.example", queries=["site:anti.example report"])]
    result = _result(success=False, metadata={"site_results": []})

    # child_run.parent_run_id is a FK to pipeline_run; create the parent run first.
    storage = Storage(db)
    storage.create_pipeline_run("run-1", correlation_id="corr")
    storage.close()

    runtime._enqueue_site_query_search_fallbacks(
        "task-parent", {"paths": {"db": db}, "search": {"enabled": True}}, result, site_configs,
        {"_pipeline_run_id": "run-1"},
    )

    assert result.metadata["search_fallback_enqueued"] == 1
    assert seen_task_id["parent_run_id"] == "run-1"
    assert seen_task_id["child_run_id"] == seen_task_id["task_id"]
    assert seen_task_id["child_run_id"]

    storage = Storage(db)
    try:
        children = storage.get_child_runs("run-1")
        assert len(children) == 1
        assert children[0]["child_run_id"] == seen_task_id["child_run_id"]
        assert children[0]["parent_run_id"] == "run-1"
        assert children[0]["status"] == "pending"
    finally:
        storage.close()


def test_enqueue_search_fallback_without_parent_run_skips_child_run(monkeypatch, tmp_path) -> None:
    db = str(tmp_path / "pipeline.db")
    runtime = _make_runtime(monkeypatch, db)
    monkeypatch.setattr(runtime, "_site_search_fallback_reason", lambda site_config, outcomes: "blocked")
    monkeypatch.setattr(runtime, "start_background_task", lambda *a, **k: "child-1")

    site_configs = [SiteConfig(name="Anti Bot", url="https://anti.example", queries=["q"])]
    result = _result(success=False, metadata={"site_results": []})
    # No _pipeline_run_id -> standalone task, no child_run tracking.
    runtime._enqueue_site_query_search_fallbacks(
        "task-parent", {"paths": {"db": db}, "search": {"enabled": True}}, result, site_configs, {}
    )
    assert result.metadata["search_fallback_enqueued"] == 1


def test_finalize_child_run_success(monkeypatch, tmp_path) -> None:
    db = str(tmp_path / "pipeline.db")
    runtime = _make_runtime(monkeypatch, db)
    storage = Storage(db)
    storage.create_pipeline_run("run-1")
    storage.create_child_run("child-1", "run-1")
    storage.close()

    runtime._finalize_child_run(
        {"child_run_id": "child-1", "parent_run_id": "run-1"}, result=_result(success=True)
    )

    storage = Storage(db)
    try:
        child = storage.get_child_runs("run-1")[0]
        assert child["status"] == "succeeded"
        assert child["partial"] == 0
    finally:
        storage.close()


def test_finalize_child_run_unsuccessful_marks_partial(monkeypatch, tmp_path) -> None:
    db = str(tmp_path / "pipeline.db")
    runtime = _make_runtime(monkeypatch, db)
    storage = Storage(db)
    storage.create_pipeline_run("run-1")
    storage.create_child_run("child-1", "run-1")
    storage.close()

    runtime._finalize_child_run(
        {"child_run_id": "child-1", "parent_run_id": "run-1"},
        result=_result(success=False, errors=["no results"]),
    )

    storage = Storage(db)
    try:
        child = storage.get_child_runs("run-1")[0]
        assert child["status"] == "failed"
        assert child["partial"] == 1
        assert "no results" in child["error"]
    finally:
        storage.close()


def test_finalize_child_run_exception_marks_hard_fail(monkeypatch, tmp_path) -> None:
    db = str(tmp_path / "pipeline.db")
    runtime = _make_runtime(monkeypatch, db)
    storage = Storage(db)
    storage.create_pipeline_run("run-1")
    storage.create_child_run("child-1", "run-1")
    storage.close()

    runtime._finalize_child_run(
        {"child_run_id": "child-1", "parent_run_id": "run-1"}, error="boom"
    )

    storage = Storage(db)
    try:
        child = storage.get_child_runs("run-1")[0]
        assert child["status"] == "failed"
        assert child["partial"] == 0
        assert child["error"] == "boom"
    finally:
        storage.close()


def test_wait_and_summarize_buckets_terminal_children(monkeypatch, tmp_path) -> None:
    db = str(tmp_path / "pipeline.db")
    runtime = _make_runtime(monkeypatch, db)
    storage = Storage(db)
    try:
        storage.create_pipeline_run("run-1", correlation_id="corr")
        storage.create_child_run("c-ok", "run-1")
        storage.create_child_run("c-fail", "run-1")
        storage.create_child_run("c-partial", "run-1")
        storage.create_child_run("c-pending", "run-1")
        storage.update_child_run("c-ok", status="succeeded")
        storage.update_child_run("c-fail", status="failed", error="boom")
        storage.update_child_run("c-partial", status="failed", partial=1, error="partial")

        # Break the poll immediately: pending child + stop requested.
        monkeypatch.setattr(runtime, "_stop_requested", lambda task_id: True)
        summary = runtime._wait_and_summarize_child_runs(storage, "run-1", "task-1")

        assert [c["child_run_id"] for c in summary["failed"]] == ["c-fail"]
        assert [c["child_run_id"] for c in summary["partial"]] == ["c-partial"]
        assert [c["child_run_id"] for c in summary["pending"]] == ["c-pending"]
    finally:
        storage.close()


def test_wait_and_summarize_no_children(monkeypatch, tmp_path) -> None:
    db = str(tmp_path / "pipeline.db")
    runtime = _make_runtime(monkeypatch, db)
    storage = Storage(db)
    try:
        summary = runtime._wait_and_summarize_child_runs(storage, "run-missing", "task-1")
        assert summary == {"children": [], "failed": [], "partial": [], "pending": []}
    finally:
        storage.close()
