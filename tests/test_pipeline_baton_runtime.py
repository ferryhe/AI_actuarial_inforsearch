from __future__ import annotations

import sqlite3
from typing import Any
from unittest.mock import patch

import pytest

from ai_actuarial.task_runtime import NativeTaskRuntime, _FallbackScheduler


def _runtime(monkeypatch, tmp_path):
    monkeypatch.setattr("ai_actuarial.task_runtime._new_scheduler", lambda: _FallbackScheduler())
    runtime = NativeTaskRuntime(
        ready_data_db_path=str(tmp_path / "index.db"),
        pipeline_baton_state_path=str(tmp_path / "pipeline-baton.json"),
    )
    runtime._scheduler_loop_started = True
    monkeypatch.setattr(
        runtime,
        "_load_site_config",
        lambda: {
            "paths": {"db": str(tmp_path / "index.db")},
            "scheduled_tasks": [
                {
                    "name": "Scheduled Collection",
                    "type": "scheduled",
                    "interval": "daily",
                    "enabled": True,
                    "params": {"site": None},
                },
                {
                    "name": "Nightly Catalog",
                    "type": "catalog",
                    "interval": "daily",
                    "enabled": True,
                    "params": {},
                },
            ],
        },
    )
    started: list[tuple[str, dict[str, Any], str | None]] = []

    def start_task(collection_type, payload, *, task_name=None, **kwargs):
        task_id = f"runtime-task-{len(started) + 1}"
        started.append((collection_type, dict(payload), task_name))
        runtime.active_tasks[task_id] = {
            "id": task_id,
            "status": "pending",
            "type": collection_type,
        }
        return task_id

    monkeypatch.setattr(runtime, "start_background_task", start_task)
    return runtime, started


def test_scheduled_collection_job_begins_baton_and_registers_30_minute_tick(
    monkeypatch, tmp_path
) -> None:
    runtime, started = _runtime(monkeypatch, tmp_path)

    runtime.init_scheduler()
    scheduled_job = next(
        job for job in runtime.scheduler.jobs if job.unit == "days" and job.interval == 1
    )
    scheduled_job.job_func()
    scheduled_job.job_func()

    assert started == [
        (
            "scheduled",
            {"site": None, "name": "Scheduled: Scheduled Collection"},
            "Scheduled: Scheduled Collection",
        )
    ]
    assert (
        runtime.pipeline_baton_status()["state"]["consumed_scheduled_task_id"] == "runtime-task-1"
    )
    assert any(job.unit == "minutes" and job.interval == 30 for job in runtime.scheduler.jobs)


def test_scheduled_tick_logs_errors_without_hiding_direct_api_failure(
    monkeypatch, tmp_path
) -> None:
    runtime, _started = _runtime(monkeypatch, tmp_path)

    def fail_tick():
        raise sqlite3.OperationalError("temporary KB lookup failure")

    monkeypatch.setattr(runtime, "tick_pipeline_baton", fail_tick)
    runtime.init_scheduler()
    tick_job = next(
        job for job in runtime.scheduler.jobs if job.unit == "minutes" and job.interval == 30
    )

    tick_job.job_func()
    with pytest.raises(sqlite3.OperationalError, match="temporary KB lookup failure"):
        runtime.tick_pipeline_baton()


def test_manual_start_uses_same_configured_scheduled_collection_and_is_idempotent(
    monkeypatch, tmp_path
) -> None:
    runtime, started = _runtime(monkeypatch, tmp_path)

    first = runtime.start_pipeline_baton()
    second = runtime.start_pipeline_baton()

    assert first == second
    assert len(started) == 1
    assert started[0][0] == "scheduled"


def test_runtime_rejects_old_full_pipeline_dispatch(monkeypatch, tmp_path) -> None:
    runtime, _started = _runtime(monkeypatch, tmp_path)

    try:
        runtime._run_collection("old-full", "full_pipeline", {})
    except RuntimeError as exc:
        assert "does not yet support collection type 'full_pipeline'" in str(exc)
    else:
        raise AssertionError("full_pipeline must be rejected")


def test_runtime_sequences_all_supported_kb_modes_in_stable_order(monkeypatch, tmp_path) -> None:
    runtime, started = _runtime(monkeypatch, tmp_path)
    with sqlite3.connect(tmp_path / "index.db") as conn:
        conn.execute("CREATE TABLE rag_knowledge_bases (kb_id TEXT, kb_mode TEXT)")
        conn.executemany(
            "INSERT INTO rag_knowledge_bases (kb_id, kb_mode) VALUES (?, ?)",
            [
                ("kb-z-category", "category"),
                ("kb-m-manual", "manual"),
                ("kb-a-all", "all"),
                ("kb-unsupported", "external"),
            ],
        )

    assert runtime._indexable_kb_ids() == [
        "kb-a-all",
        "kb-m-manual",
        "kb-z-category",
    ]
    runtime._pipeline_baton._kb_index_input = lambda kb_id: {
        "contract_version": 1,
        "kb_id": kb_id,
        "expected_binding_snapshot_fingerprint": f"binding-{kb_id}",
        "embedding_identity_key": "identity-1",
        "force_rebuild": False,
    }
    runtime._pipeline_baton._ready_data_input = lambda kb_id, result: {
        "contract_version": 1,
        "kb_id": kb_id,
        "index_version_id": result["index_version_id"],
        "expected_source_snapshot_fingerprint": f"source-{kb_id}",
    }
    runtime.active_tasks["scheduled-source"] = {
        "id": "scheduled-source",
        "status": "completed",
        "type": "scheduled",
    }
    runtime._pipeline_baton.start("scheduled-source")

    runtime._pipeline_baton.tick()
    runtime.active_tasks["runtime-task-1"].update(
        status="completed",
        result={
            "contract_version": 1,
            "files": [
                {
                    "file_url": "https://example.test/a.pdf",
                    "markdown_hash": "hash-a",
                    "markdown_version": "hash-a",
                    "status": "ready",
                }
            ],
        },
    )
    runtime._pipeline_baton.tick()
    runtime.active_tasks["runtime-task-2"]["status"] = "completed"
    runtime._pipeline_baton.tick()
    runtime.active_tasks["runtime-task-3"].update(
        status="completed",
        result={"chunk_sets": [{"chunk_set_id": "cs-a"}]},
    )
    runtime._pipeline_baton.tick()
    runtime.active_tasks["runtime-task-4"]["status"] = "completed"
    runtime._pipeline_baton.tick()

    for offset, kb_id in enumerate(
        ["kb-a-all", "kb-m-manual", "kb-z-category"],
        start=5,
    ):
        index_task_id = f"runtime-task-{offset * 2 - 5}"
        ready_task_id = f"runtime-task-{offset * 2 - 4}"
        runtime.active_tasks[index_task_id].update(
            status="completed",
            result={"index_version_id": f"idx-{kb_id}"},
        )
        runtime._pipeline_baton.tick()
        runtime.active_tasks[ready_task_id]["status"] = "completed"
        view = runtime._pipeline_baton.tick()

    assert [
        payload["kb_id"]
        for task_type, payload, _task_name in started
        if task_type == "rag_indexing"
    ] == ["kb-a-all", "kb-m-manual", "kb-z-category"]
    assert view["state"]["summary"] == {
        "attempted": 3,
        "succeeded": 3,
        "failed": 0,
        "failed_kbs": [],
    }


def test_runtime_does_not_treat_kb_discovery_errors_as_zero_kbs(monkeypatch, tmp_path) -> None:
    runtime, _started = _runtime(monkeypatch, tmp_path)

    with pytest.raises(sqlite3.OperationalError, match="rag_knowledge_bases"):
        runtime._indexable_kb_ids()


def test_runtime_catalog_resolves_untouched_form_defaults(monkeypatch, tmp_path) -> None:
    runtime, _started = _runtime(monkeypatch, tmp_path)
    stats = {"scanned": 0, "processed": 0, "skipped_ai": 0, "errors": 0, "stopped": False}

    with patch(
        "ai_actuarial.task_runtime.run_incremental_catalog", return_value=stats
    ) as run_catalog:
        runtime._run_collection("catalog-defaults", "catalog", {})

    assert run_catalog.call_args.kwargs["input_source"] == "markdown"
    assert run_catalog.call_args.kwargs["limit"] == 100


def test_runtime_status_exposes_each_independent_task_log(monkeypatch, tmp_path) -> None:
    runtime, _started = _runtime(monkeypatch, tmp_path)
    runtime.active_tasks["scheduled-1"] = {
        "id": "scheduled-1",
        "status": "completed",
        "type": "scheduled",
    }
    runtime._pipeline_baton.start("scheduled-1")
    runtime.task_history.append(
        {
            "id": "markdown-1",
            "status": "completed",
            "pipeline_baton_step": "markdown_conversion",
            "pipeline_baton_source_task_id": "scheduled-1",
        }
    )
    runtime.task_history.extend(
        [
            {
                "id": "index-1",
                "status": "completed",
                "pipeline_baton_step": "rag_indexing",
                "pipeline_baton_subtask": "kb_index",
                "pipeline_baton_source_task_id": "scheduled-1",
                "pipeline_baton_kb_id": "kb-a",
            },
            {
                "id": "ready-1",
                "status": "completed",
                "pipeline_baton_step": "rag_indexing",
                "pipeline_baton_subtask": "ready_data_build",
                "pipeline_baton_source_task_id": "scheduled-1",
                "pipeline_baton_kb_id": "kb-a",
            },
        ]
    )

    stages = {stage["step"]: stage for stage in runtime.pipeline_baton_status()["stages"]}

    assert stages["scheduled"]["tasks"][0]["log_url"] == "/api/tasks/log/scheduled-1"
    assert stages["markdown_conversion"]["tasks"][0]["log_url"] == "/api/tasks/log/markdown-1"
    assert [
        (task["subtask"], task["label"], task["log_url"])
        for task in stages["rag_indexing"]["tasks"]
    ] == [
        ("kb_index", "KB Index", "/api/tasks/log/index-1"),
        ("ready_data_build", "Ready Data Build/Publish", "/api/tasks/log/ready-1"),
    ]
