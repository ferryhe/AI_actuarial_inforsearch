from __future__ import annotations

from typing import Any

from ai_actuarial.collectors.base import CollectionResult
from ai_actuarial.task_runtime import NativeTaskRuntime


def _result(stage: str, *, success: bool = True, errors: list[str] | None = None, stopped: bool = False) -> CollectionResult:
    return CollectionResult(
        success=success and not stopped and not errors,
        items_found=2,
        items_downloaded=1,
        items_skipped=0,
        errors=errors or ([] if not stopped else ["Task stopped by user"]),
        metadata={"stage_marker": stage, "stopped": stopped},
    )


def test_full_pipeline_chains_source_markdown_catalog_chunk_and_rag(monkeypatch) -> None:
    runtime = NativeTaskRuntime()
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_run_collection(task_id: str, collection_type: str, data: dict[str, Any]) -> CollectionResult:
        calls.append((collection_type, dict(data)))
        return _result(collection_type)

    monkeypatch.setattr(runtime, "_run_collection", fake_run_collection)
    monkeypatch.setattr(runtime, "_stop_requested", lambda task_id: False)
    monkeypatch.setattr(runtime, "_update_task", lambda task_id, **fields: None)

    result = runtime._run_full_pipeline(
        "task-full",
        {
            "name": "Nightly Full",
            "source_collection_type": "quick_check",
            "url": "https://example.com/reports",
            "urls": ["https://example.com/a.pdf", "https://example.com/b.pdf", "https://example.com/a.pdf"],
            "category": "AI",
            "scan_count": 7,
            "kb_id": "kb-1",
            "run_rag_indexing": True,
        },
    )

    assert result.success is True
    assert [call[0] for call in calls] == [
        "quick_check",
        "markdown_conversion",
        "catalog",
        "chunk_generation",
        "rag_indexing",
    ]
    assert calls[0][1]["type"] == "quick_check"
    assert calls[-1][1]["kb_id"] == "kb-1"
    assert result.metadata["source_collection_type"] == "quick_check"
    assert result.metadata["run_rag_indexing"] is True
    for collection_type, payload in calls[1:]:
        assert payload["file_urls"] == [
            "https://example.com/a.pdf",
            "https://example.com/b.pdf",
            "https://example.com/reports",
        ]
    assert [stage["stage"] for stage in result.metadata["stages"]] == [
        "source_collection",
        "markdown_conversion",
        "catalog",
        "chunk_generation",
        "rag_indexing",
    ]


def test_full_pipeline_uses_recently_collected_file_urls_for_downstream_stages(monkeypatch) -> None:
    runtime = NativeTaskRuntime()
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_run_collection(task_id: str, collection_type: str, data: dict[str, Any]) -> CollectionResult:
        calls.append((collection_type, dict(data)))
        return _result(collection_type)

    monkeypatch.setattr(runtime, "_run_collection", fake_run_collection)
    monkeypatch.setattr(runtime, "_stop_requested", lambda task_id: False)
    monkeypatch.setattr(runtime, "_update_task", lambda task_id, **fields: None)
    monkeypatch.setattr(runtime, "_full_pipeline_storage_now", lambda db_path: "2026-06-18T00:00:00+00:00")
    monkeypatch.setattr(
        runtime,
        "_full_pipeline_recent_file_urls",
        lambda db_path, started_at, data: ["https://example.com/downloaded.pdf"],
    )

    result = runtime._run_full_pipeline(
        "task-full",
        {"source_collection_type": "quick_check", "url": "https://example.com/page"},
        "data/test.db",
    )

    assert result.success is True
    assert calls[0][1]["url"] == "https://example.com/page"
    for _collection_type, payload in calls[1:]:
        assert payload["file_urls"] == ["https://example.com/downloaded.pdf"]


def test_full_pipeline_omits_rag_when_not_requested(monkeypatch) -> None:
    runtime = NativeTaskRuntime()
    calls: list[str] = []

    def fake_run_collection(task_id: str, collection_type: str, data: dict[str, Any]) -> CollectionResult:
        calls.append(collection_type)
        return _result(collection_type)

    monkeypatch.setattr(runtime, "_run_collection", fake_run_collection)
    monkeypatch.setattr(runtime, "_stop_requested", lambda task_id: False)
    monkeypatch.setattr(runtime, "_update_task", lambda task_id, **fields: None)

    result = runtime._run_full_pipeline("task-full", {"run_rag_indexing": False})

    assert result.success is True
    assert calls == ["scheduled", "markdown_conversion", "catalog", "chunk_generation"]
    assert result.metadata["run_rag_indexing"] is False


def test_full_pipeline_surfaces_stage_error_and_stops_chaining(monkeypatch) -> None:
    runtime = NativeTaskRuntime()
    calls: list[str] = []

    def fake_run_collection(task_id: str, collection_type: str, data: dict[str, Any]) -> CollectionResult:
        calls.append(collection_type)
        if collection_type == "catalog":
            return _result(collection_type, success=False, errors=["catalog boom"])
        return _result(collection_type)

    monkeypatch.setattr(runtime, "_run_collection", fake_run_collection)
    monkeypatch.setattr(runtime, "_stop_requested", lambda task_id: False)
    monkeypatch.setattr(runtime, "_update_task", lambda task_id, **fields: None)

    result = runtime._run_full_pipeline("task-full", {"kb_id": "kb-1"})

    assert result.success is False
    assert calls == ["scheduled", "markdown_conversion", "catalog"]
    assert result.errors == ["catalog: catalog boom"]
    assert result.metadata["stages"][-1]["success"] is False


def test_full_pipeline_treats_unsuccessful_stage_without_errors_as_failure(monkeypatch) -> None:
    runtime = NativeTaskRuntime()
    calls: list[str] = []

    def fake_run_collection(task_id: str, collection_type: str, data: dict[str, Any]) -> CollectionResult:
        calls.append(collection_type)
        if collection_type == "catalog":
            return _result(collection_type, success=False)
        return _result(collection_type)

    monkeypatch.setattr(runtime, "_run_collection", fake_run_collection)
    monkeypatch.setattr(runtime, "_stop_requested", lambda task_id: False)
    monkeypatch.setattr(runtime, "_update_task", lambda task_id, **fields: None)

    result = runtime._run_full_pipeline("task-full", {"kb_id": "kb-1"})

    assert result.success is False
    assert calls == ["scheduled", "markdown_conversion", "catalog"]
    assert result.errors == ["catalog: stage returned unsuccessful result"]
    assert result.metadata["stages"][-1]["success"] is False


def test_full_pipeline_surfaces_stopped_state(monkeypatch) -> None:
    runtime = NativeTaskRuntime()
    calls: list[str] = []

    def fake_run_collection(task_id: str, collection_type: str, data: dict[str, Any]) -> CollectionResult:
        calls.append(collection_type)
        if collection_type == "markdown_conversion":
            return _result(collection_type, stopped=True)
        return _result(collection_type)

    monkeypatch.setattr(runtime, "_run_collection", fake_run_collection)
    monkeypatch.setattr(runtime, "_stop_requested", lambda task_id: False)
    monkeypatch.setattr(runtime, "_update_task", lambda task_id, **fields: None)

    result = runtime._run_full_pipeline("task-full", {})

    assert result.success is False
    assert calls == ["scheduled", "markdown_conversion"]
    assert result.metadata["stopped"] is True
    assert result.metadata["stages"][-1]["stopped"] is True
    assert result.errors == ["markdown_conversion: Task stopped by user"]
