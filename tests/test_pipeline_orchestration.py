from __future__ import annotations

import json
from typing import Any

import pytest

from ai_actuarial.collectors.base import CollectionResult
from ai_actuarial.storage import Storage
from ai_actuarial.task_runtime import NativeTaskRuntime


def _result(stage: str, *, success: bool = True, errors: list[str] | None = None) -> CollectionResult:
    return CollectionResult(
        success=success and not errors,
        items_found=2,
        items_downloaded=1,
        items_skipped=0,
        errors=errors or [],
        metadata={"stage_marker": stage},
    )


def _make_runtime(
    monkeypatch: pytest.MonkeyPatch,
    db: str,
    *,
    collector,
    ai_config: dict[str, Any] | None = None,
) -> NativeTaskRuntime:
    runtime = NativeTaskRuntime()
    cfg = {"paths": {"db": db, "download_dir": db + ".files"}}
    if ai_config:
        cfg["ai_config"] = ai_config
    monkeypatch.setattr(runtime, "_load_site_config", lambda: dict(cfg))
    monkeypatch.setattr(runtime, "_run_collection", collector)
    monkeypatch.setattr(runtime, "_stop_requested", lambda task_id: False)
    monkeypatch.setattr(runtime, "_update_task", lambda task_id, **fields: None)
    return runtime


def _ok_collector() -> Any:
    def collector(task_id: str, collection_type: str, data: dict[str, Any]) -> CollectionResult:
        return _result(collection_type)

    return collector


def test_full_pipeline_records_run_and_effective_options(monkeypatch, tmp_path) -> None:
    db = str(tmp_path / "pipeline.db")
    runtime = _make_runtime(
        monkeypatch,
        db,
        collector=_ok_collector(),
        ai_config={"catalog": {"provider": "local", "model": "base"}},
    )

    result = runtime._run_full_pipeline(
        "task-1",
        {"stage_options": {"catalog": {"model": "gpt-5.4-mini"}}},
        db,
    )

    assert result.success is True
    run_id = result.metadata["run_id"]
    assert run_id

    storage = Storage(db)
    try:
        run = storage.get_pipeline_run(run_id)
        assert run is not None
        assert run["status"] == "succeeded"
        assert run["correlation_id"] == "task-1"

        stages = {s["stage_name"]: s for s in storage.get_pipeline_stages(run_id)}
        assert set(stages) == {"acquisition", "markdown_conversion", "catalog", "chunk_generation"}
        for name in ("acquisition", "markdown_conversion", "catalog", "chunk_generation"):
            assert stages[name]["status"] == "succeeded"

        # Effective options: catalog override merged onto module defaults, recorded.
        catalog_options = json.loads(stages["catalog"]["options_json"])
        assert catalog_options["model"] == "gpt-5.4-mini"
        assert catalog_options["provider"] == "local"

        # Watermark advanced through every committed stage.
        watermark = json.loads(run["watermark"])
        assert watermark == ["acquisition", "markdown_conversion", "catalog", "chunk_generation"]
    finally:
        storage.close()


def test_full_pipeline_failure_does_not_advance_watermark(monkeypatch, tmp_path) -> None:
    db = str(tmp_path / "pipeline.db")

    def collector(task_id: str, collection_type: str, data: dict[str, Any]) -> CollectionResult:
        if collection_type == "catalog":
            return _result(collection_type, success=False, errors=["catalog boom"])
        return _result(collection_type)

    runtime = _make_runtime(monkeypatch, db, collector=collector)

    result = runtime._run_full_pipeline("task-1", {"kb_id": "kb-1"}, db)

    assert result.success is False
    run_id = result.metadata["run_id"]

    storage = Storage(db)
    try:
        run = storage.get_pipeline_run(run_id)
        assert run["status"] == "failed"
        watermark = json.loads(run["watermark"])
        # acquisition + markdown_conversion committed; catalog did not.
        assert watermark == ["acquisition", "markdown_conversion"]
        stages = {s["stage_name"]: s for s in storage.get_pipeline_stages(run_id)}
        assert stages["catalog"]["status"] == "failed"
    finally:
        storage.close()


def test_full_pipeline_resume_skips_committed_stages(monkeypatch, tmp_path) -> None:
    db = str(tmp_path / "pipeline.db")
    runtime = NativeTaskRuntime()
    cfg = {"paths": {"db": db, "download_dir": db + ".files"}}
    monkeypatch.setattr(runtime, "_load_site_config", lambda: dict(cfg))
    monkeypatch.setattr(runtime, "_stop_requested", lambda task_id: False)
    monkeypatch.setattr(runtime, "_update_task", lambda task_id, **fields: None)

    calls: list[str] = []

    def fail_at_catalog(task_id: str, collection_type: str, data: dict[str, Any]) -> CollectionResult:
        calls.append(collection_type)
        if collection_type == "catalog":
            raise RuntimeError("catalog boom")
        return _result(collection_type)

    monkeypatch.setattr(runtime, "_run_collection", fail_at_catalog)
    first = runtime._run_full_pipeline("task-1", {"kb_id": "kb-1"}, db)
    assert first.success is False
    assert calls == ["scheduled", "markdown_conversion", "catalog"]

    # Second call with the same correlation resumes: committed stages skipped.
    calls.clear()

    def succeed(task_id: str, collection_type: str, data: dict[str, Any]) -> CollectionResult:
        calls.append(collection_type)
        return _result(collection_type)

    monkeypatch.setattr(runtime, "_run_collection", succeed)
    second = runtime._run_full_pipeline("task-1", {"kb_id": "kb-1"}, db)
    assert second.success is True
    assert second.metadata["resumed"] is True
    assert calls == ["catalog", "chunk_generation", "rag_indexing"]


def test_full_pipeline_resume_reinjects_acquisition_urls(monkeypatch, tmp_path) -> None:
    db = str(tmp_path / "pipeline.db")
    runtime = NativeTaskRuntime()
    monkeypatch.setattr(runtime, "_load_site_config", lambda: {"paths": {"db": db, "download_dir": db + ".files"}})
    monkeypatch.setattr(runtime, "_stop_requested", lambda task_id: False)
    monkeypatch.setattr(runtime, "_update_task", lambda task_id, **fields: None)
    monkeypatch.setattr(runtime, "_full_pipeline_storage_now", lambda db_path: "2026-06-18T00:00:00+00:00")
    monkeypatch.setattr(
        runtime,
        "_full_pipeline_recent_file_urls",
        lambda db_path, started_at, data: ["https://example.com/discovered.pdf"],
    )

    seen: list[list[str]] = []

    def fail_at_catalog(task_id: str, collection_type: str, data: dict[str, Any]) -> CollectionResult:
        if collection_type == "catalog":
            raise RuntimeError("catalog boom")
        return _result(collection_type)

    monkeypatch.setattr(runtime, "_run_collection", fail_at_catalog)
    runtime._run_full_pipeline("task-1", {"kb_id": "kb-1"}, db)

    # Resume: downstream stages must still see the discovered URLs.
    def succeed(task_id: str, collection_type: str, data: dict[str, Any]) -> CollectionResult:
        if collection_type in ("catalog", "chunk_generation", "rag_indexing"):
            seen.append(list(data.get("file_urls") or []))
        return _result(collection_type)

    monkeypatch.setattr(runtime, "_run_collection", succeed)
    second = runtime._run_full_pipeline("task-1", {"kb_id": "kb-1"}, db)
    assert second.success is True
    assert seen and all(urls == ["https://example.com/discovered.pdf"] for urls in seen)


def test_pipeline_run_lease_fences_concurrent_claims(tmp_path) -> None:
    db = str(tmp_path / "pipeline.db")
    storage = Storage(db)
    try:
        storage.create_pipeline_run("run-1", correlation_id="corr-1", source_type="scheduled")
        assert storage.claim_pipeline_run("run-1", lease_owner="worker-a") is True
        # A second live owner cannot claim while the first lease is unexpired.
        assert storage.claim_pipeline_run("run-1", lease_owner="worker-b") is False
        # The original owner can release and a new owner can then claim.
        storage.release_pipeline_lease("run-1", lease_owner="worker-a")
        assert storage.claim_pipeline_run("run-1", lease_owner="worker-b") is True
    finally:
        storage.close()


def test_full_pipeline_immutable_config_change_fails_closed_on_resume(monkeypatch, tmp_path) -> None:
    db = str(tmp_path / "pipeline.db")
    runtime = NativeTaskRuntime()
    monkeypatch.setattr(runtime, "_load_site_config", lambda: {"paths": {"db": db, "download_dir": db + ".files"}})
    monkeypatch.setattr(runtime, "_stop_requested", lambda task_id: False)
    monkeypatch.setattr(runtime, "_update_task", lambda task_id, **fields: None)

    def fail_at_rag(task_id: str, collection_type: str, data: dict[str, Any]) -> CollectionResult:
        if collection_type == "rag_indexing":
            raise RuntimeError("rag boom")
        return _result(collection_type)

    monkeypatch.setattr(runtime, "_run_collection", fail_at_rag)
    # First run commits chunk_generation with chunk_size=800, then fails at rag.
    first = runtime._run_full_pipeline(
        "task-1", {"chunk_size": 800, "kb_id": "kb-1", "run_rag_indexing": True}, db
    )
    assert first.success is False

    # Resume with a different immutable chunk config must fail closed.
    monkeypatch.setattr(runtime, "_run_collection", _ok_collector())
    with pytest.raises(RuntimeError, match="immutable stage chunk_generation"):
        runtime._run_full_pipeline(
            "task-1", {"chunk_size": 400, "kb_id": "kb-1", "run_rag_indexing": True}, db
        )


def test_full_pipeline_resume_same_effective_chunk_config_does_not_fail_closed(monkeypatch, tmp_path) -> None:
    db = str(tmp_path / "pipeline.db")
    runtime = NativeTaskRuntime()
    monkeypatch.setattr(runtime, "_load_site_config", lambda: {"paths": {"db": db, "download_dir": db + ".files"}})
    monkeypatch.setattr(runtime, "_stop_requested", lambda task_id: False)
    monkeypatch.setattr(runtime, "_update_task", lambda task_id, **fields: None)

    def fail_at_rag(task_id: str, collection_type: str, data: dict[str, Any]) -> CollectionResult:
        if collection_type == "rag_indexing":
            raise RuntimeError("rag boom")
        return _result(collection_type)

    monkeypatch.setattr(runtime, "_run_collection", fail_at_rag)
    # First run omits chunk_size -> effective default is 800.
    first = runtime._run_full_pipeline("task-1", {"kb_id": "kb-1", "run_rag_indexing": True}, db)
    assert first.success is False

    # Resume with the explicit default (800) is the SAME effective config, so it
    # must NOT fail closed; it should resume and finish.
    monkeypatch.setattr(runtime, "_run_collection", _ok_collector())
    second = runtime._run_full_pipeline(
        "task-1", {"chunk_size": 800, "kb_id": "kb-1", "run_rag_indexing": True}, db
    )
    assert second.success is True
    assert second.metadata["resumed"] is True

