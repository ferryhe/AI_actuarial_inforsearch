from __future__ import annotations

import json
import sqlite3
from typing import Any
from unittest.mock import patch

import pytest

from ai_actuarial.pipeline_baton import PipelineBaton
from ai_actuarial.task_item_errors import make_item_error
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


def test_tick_start_failure_projects_attempted_markdown(monkeypatch, tmp_path) -> None:
    runtime, _started = _runtime(monkeypatch, tmp_path)
    statuses = {"scheduled-1": "completed"}
    results = {"scheduled-1": {"items_downloaded": 1}}

    def start(kind, *_args, **_kwargs):
        if kind == "markdown_conversion":
            raise RuntimeError("launch failed")
        return "unused"

    baton = PipelineBaton(
        state_path=tmp_path / "real-baton.json",
        start_task=start,
        task_status=statuses.get,
        task_result=results.get,
        indexable_kb_ids=lambda: [],
        now=lambda: "now",
    )
    baton.start("scheduled-1")
    state = baton.tick()["state"]
    assert state["round_status"] == "error"
    assert state["current_step"] == "scheduled"
    runtime._pipeline_baton.status = lambda: {"config": {"overrides": {}}, "state": state}
    runtime.task_history.append({"id": "scheduled-1", "status": "completed", "items_downloaded": 1})
    view = runtime.pipeline_baton_status()
    stages = {stage["step"]: stage for stage in view["stages"]}
    assert stages["scheduled"]["status"] == "completed"
    assert stages["markdown_conversion"]["status"] == "failed"
    assert view["summary"]["latest_failure"]["task_id"] is None


def test_runtime_reloads_evicted_retained_round_tasks_after_restart(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    history_path = tmp_path / "data" / "job_history.jsonl"
    history_path.parent.mkdir()
    source = {
        "id": "source-1",
        "status": "error",
        "errors": ["partial failure"],
        "items_downloaded": 1,
    }
    late_child = {
        "id": "late-child",
        "status": "completed",
        "pipeline_baton_step": "markdown_conversion",
        "pipeline_baton_source_task_id": "source-1",
    }
    rows = (
        [source]
        + [{"id": f"later-{index}", "status": "completed"} for index in range(100)]
        + [late_child]
    )
    history_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    (tmp_path / "pipeline-baton.json").write_text(
        json.dumps(
            {
                "config": {"overrides": {}},
                "state": {"round_status": "completed", "consumed_scheduled_task_id": "source-1"},
            }
        ),
        encoding="utf-8",
    )
    runtime, _started = _runtime(monkeypatch, tmp_path)
    runtime.active_tasks["late-child"] = {**late_child, "status": "running"}

    assert all(task["id"] != "source-1" for task in runtime.task_history)
    assert any(task["id"] == "late-child" for task in runtime.task_history)
    view = runtime.pipeline_baton_status()

    scheduled = next(stage for stage in view["stages"] if stage["step"] == "scheduled")
    assert view["summary"]["status"] == "completed_with_errors"
    assert view["summary"]["failed_stages"] == 1
    assert view["summary"]["latest_failure"]["task_id"] == "source-1"
    assert scheduled["status"] == "failed"
    assert scheduled["tasks"][0]["log_url"] == "/api/tasks/log/source-1"
    markdown = next(stage for stage in view["stages"] if stage["step"] == "markdown_conversion")
    assert markdown["tasks"][0]["status"] == "running"


def test_tick_ready_data_oserror_projects_terminal_rag_failure(monkeypatch, tmp_path) -> None:
    runtime, _started = _runtime(monkeypatch, tmp_path)
    statuses = {"index-2": "completed"}
    results = {"index-2": {"result": {"index_version_id": "v2"}}}
    baton = PipelineBaton(
        state_path=tmp_path / "rag-baton.json",
        start_task=lambda *_args, **_kwargs: "unused",
        task_status=statuses.get,
        task_result=results.get,
        indexable_kb_ids=lambda: ["kb-a", "kb-b"],
        ready_data_input=lambda *_args: (_ for _ in ()).throw(OSError("ready data failed")),
        now=lambda: "now",
    )
    document = PipelineBaton._empty_document()
    document["state"].update(
        round_status="running",
        consumed_scheduled_task_id="source-1",
        current_step="rag_indexing",
        current_task_id="index-2",
        current_rag_kb="kb-b",
        kb_index_ready_phase="kb_index",
        kb_index_task_id="index-2",
        kb_results=[
            {
                "kb_id": "kb-a",
                "status": "failed",
                "failure_status": "error",
                "kb_index_task_id": "index-1",
                "ready_data_task_id": None,
            }
        ],
    )
    baton._save(document)
    state = baton.tick()["state"]
    assert state["round_status"] == "error"
    assert state["current_step"] == "rag_indexing"
    assert state["current_task_id"] == "index-2"
    runtime._pipeline_baton.status = baton.status
    runtime.task_history.extend(
        [
            {"id": "source-1", "status": "completed"},
            {
                "id": "index-2",
                "status": "completed",
                "pipeline_baton_step": "rag_indexing",
                "pipeline_baton_source_task_id": "source-1",
            },
        ]
    )
    view = runtime.pipeline_baton_status()
    rag = next(stage for stage in view["stages"] if stage["step"] == "rag_indexing")
    assert rag["status"] == "failed"
    assert len(rag["failures"]) == 1
    assert view["summary"]["failed_stages"] == 1
    assert view["summary"]["latest_failure"] == {
        "task_id": None,
        "stage": "rag_indexing",
        "error_count": 1,
        "first_error_code": "orchestration_error",
        "summary": "Pipeline orchestration failed.",
    }


def test_scheduled_collection_job_begins_baton_and_registers_one_hour_tick(
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
    assert any(job.unit == "hours" and job.interval == 1 for job in runtime.scheduler.jobs)


def test_scheduled_tick_logs_errors_without_hiding_direct_api_failure(
    monkeypatch, tmp_path
) -> None:
    runtime, _started = _runtime(monkeypatch, tmp_path)

    def fail_tick():
        raise sqlite3.OperationalError("temporary KB lookup failure")

    monkeypatch.setattr(runtime, "tick_pipeline_baton", fail_tick)
    runtime.init_scheduler()
    tick_job = next(
        job for job in runtime.scheduler.jobs if job.unit == "hours" and job.interval == 1
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
        "items_downloaded": 1,
    }
    runtime._pipeline_baton.start("scheduled-source")

    runtime._pipeline_baton.tick()
    runtime.active_tasks["runtime-task-1"].update(
        status="completed",
        items_downloaded=1,
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
    runtime.active_tasks["runtime-task-2"].update(status="completed", items_downloaded=1)
    runtime._pipeline_baton.tick()
    runtime.active_tasks["runtime-task-3"].update(
        status="completed",
        items_downloaded=1,
        result={"chunk_sets": [{"chunk_set_id": "cs-a"}]},
    )
    runtime._pipeline_baton.tick()
    runtime.active_tasks["runtime-task-4"].update(status="completed", items_downloaded=1)
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


def test_runtime_status_projects_completed_child_errors_without_changing_raw_status(
    monkeypatch, tmp_path
) -> None:
    runtime, _started = _runtime(monkeypatch, tmp_path)
    runtime._pipeline_baton.status = lambda: {
        "config": {"overrides": {}},
        "state": {"round_status": "completed", "consumed_scheduled_task_id": "source-1"},
    }
    runtime.task_history.extend(
        [
            {"id": "source-1", "status": "completed"},
            {
                "id": "catalog-1",
                "status": "completed",
                "pipeline_baton_step": "catalog",
                "pipeline_baton_source_task_id": "source-1",
                "catalog_errors": 1,
                "failed_items": 5,
                "item_errors": [make_item_error("catalog", "catalog_failed", "example.pdf")],
            },
            {
                "id": "chunk-1",
                "status": "stopped",
                "pipeline_baton_step": "chunk_generation",
                "pipeline_baton_source_task_id": "source-1",
            },
        ]
    )

    view = runtime.pipeline_baton_status()
    stages = {stage["step"]: stage for stage in view["stages"]}

    assert view["state"]["round_status"] == "completed"
    assert view["summary"] == {
        "status": "completed_with_errors",
        "successful_stages": 1,
        "failed_stages": 1,
        "stopped_stages": 1,
        "latest_failure": {
            "task_id": "catalog-1",
            "stage": "catalog",
            "error_count": 1,
            "first_error_code": "catalog_failed",
            "summary": "Catalog processing failed.",
        },
    }
    assert stages["catalog"]["status"] == "failed"
    assert stages["catalog"]["tasks"][0] == {
        "task_id": "catalog-1",
        "status": "completed",
        "error_count": 1,
        "first_error_code": "catalog_failed",
        "first_error_summary": "Catalog processing failed.",
        "failed_items": 5,
        "kb_id": None,
        "log_url": "/api/tasks/log/catalog-1",
    }


@pytest.mark.parametrize("round_status", ["completed", "error"])
def test_runtime_status_keeps_noop_and_hard_failure_orchestration_statuses(
    monkeypatch, tmp_path, round_status
) -> None:
    runtime, _started = _runtime(monkeypatch, tmp_path)
    runtime._pipeline_baton.status = lambda: {
        "config": {"overrides": {}},
        "state": {"round_status": round_status},
    }

    view = runtime.pipeline_baton_status()

    assert view["state"]["round_status"] == round_status
    assert view["summary"] == {
        "status": round_status,
        "successful_stages": 0,
        "failed_stages": 0,
        "stopped_stages": 0,
        "latest_failure": None,
    }


@pytest.mark.parametrize(
    ("current_task_id", "expected_task_id"),
    [("catalog-1", "catalog-1"), ("missing-task", None)],
)
def test_runtime_status_projects_hard_orchestration_error_to_current_stage(
    monkeypatch, tmp_path, current_task_id, expected_task_id
) -> None:
    runtime, _started = _runtime(monkeypatch, tmp_path)
    runtime._pipeline_baton.status = lambda: {
        "config": {"overrides": {}},
        "state": {
            "round_status": "error",
            "consumed_scheduled_task_id": "source-1",
            "current_step": "catalog",
            "current_task_id": current_task_id,
        },
    }
    runtime.task_history.extend(
        [
            {"id": "source-1", "status": "completed"},
            {
                "id": "catalog-1",
                "status": "completed",
                "pipeline_baton_step": "catalog",
                "pipeline_baton_source_task_id": "source-1",
            },
        ]
    )

    view = runtime.pipeline_baton_status()
    stage = next(stage for stage in view["stages"] if stage["step"] == "catalog")

    assert view["state"]["round_status"] == "error"
    assert stage["status"] == "failed"
    assert view["summary"] == {
        "status": "error",
        "successful_stages": 1,
        "failed_stages": 1,
        "stopped_stages": 0,
        "latest_failure": {
            "task_id": expected_task_id,
            "stage": "catalog",
            "error_count": 1,
            "first_error_code": "orchestration_error",
            "summary": "Pipeline orchestration failed.",
        },
    }


def test_runtime_status_keeps_earlier_failure_and_projects_terminal_orchestration_error(
    monkeypatch, tmp_path
) -> None:
    runtime, _started = _runtime(monkeypatch, tmp_path)
    runtime._pipeline_baton.status = lambda: {
        "config": {"overrides": {}},
        "state": {
            "round_status": "error",
            "consumed_scheduled_task_id": "source-1",
            "current_step": "chunk_generation",
            "current_task_id": None,
        },
    }
    runtime.task_history.extend(
        [
            {"id": "source-1", "status": "completed"},
            {
                "id": "catalog-1",
                "status": "error",
                "errors": ["catalog failed"],
                "pipeline_baton_step": "catalog",
                "pipeline_baton_source_task_id": "source-1",
            },
        ]
    )
    view = runtime.pipeline_baton_status()
    stages = {stage["step"]: stage for stage in view["stages"]}
    assert stages["catalog"]["status"] == "failed"
    assert stages["chunk_generation"]["status"] == "failed"
    assert view["summary"]["failed_stages"] == 2
    assert view["summary"]["latest_failure"]["stage"] == "chunk_generation"


def test_runtime_status_uses_last_rag_failure_and_advanced_current_task_error(
    monkeypatch, tmp_path
) -> None:
    runtime, _started = _runtime(monkeypatch, tmp_path)
    runtime._pipeline_baton.status = lambda: {
        "config": {"overrides": {}},
        "state": {
            "round_status": "error",
            "consumed_scheduled_task_id": "source-1",
            "current_step": "chunk_generation",
            "current_task_id": "chunk-1",
            "kb_results": [
                {
                    "kb_id": "a",
                    "status": "failed",
                    "failure_status": "error",
                    "kb_index_task_id": "index-1",
                },
                {
                    "kb_id": "b",
                    "status": "failed",
                    "failure_status": "index_launch_failed",
                    "kb_index_task_id": None,
                },
            ],
        },
    }
    runtime.task_history.extend(
        [
            {"id": "source-1", "status": "completed"},
            {
                "id": "index-1",
                "status": "error",
                "errors": ["index failed"],
                "pipeline_baton_step": "rag_indexing",
                "pipeline_baton_source_task_id": "source-1",
            },
            {
                "id": "chunk-1",
                "status": "error",
                "errors": ["advance failed"],
                "items_downloaded": 1,
                "pipeline_baton_step": "chunk_generation",
                "pipeline_baton_source_task_id": "source-1",
            },
        ]
    )
    view = runtime.pipeline_baton_status()
    assert view["summary"]["failed_stages"] == 2
    assert view["summary"]["latest_failure"]["stage"] == "chunk_generation"
    assert view["summary"]["latest_failure"]["first_error_code"] == "orchestration_error"
    rag = next(stage for stage in view["stages"] if stage["step"] == "rag_indexing")
    assert rag["failures"][-1]["task_id"] is None


@pytest.mark.parametrize(
    ("task", "expected_failed_items"),
    [
        (
            {"errors": ["Catalog errors: 5"]},
            5,
        ),
        (
            {"errors": ["Catalog errors: 5"], "failed_items": 0},
            0,
        ),
    ],
)
def test_runtime_status_uses_legacy_catalog_error_summary_only_without_failed_items(
    monkeypatch, tmp_path, task, expected_failed_items
) -> None:
    runtime, _started = _runtime(monkeypatch, tmp_path)
    runtime._pipeline_baton.status = lambda: {
        "config": {"overrides": {}},
        "state": {"round_status": "completed", "consumed_scheduled_task_id": "source-1"},
    }
    runtime.task_history.extend(
        [
            {"id": "source-1", "status": "completed"},
            {
                "id": "catalog-1",
                "status": "completed",
                "pipeline_baton_step": "catalog",
                "pipeline_baton_source_task_id": "source-1",
                **task,
            },
        ]
    )

    view = runtime.pipeline_baton_status()
    catalog = next(stage for stage in view["stages"] if stage["step"] == "catalog")

    assert catalog["tasks"][0]["error_count"] == 1
    assert catalog["tasks"][0]["failed_items"] == expected_failed_items


def test_runtime_status_keeps_persisted_stopped_task_out_of_error_aggregation(
    monkeypatch, tmp_path
) -> None:
    runtime, _started = _runtime(monkeypatch, tmp_path)
    runtime._pipeline_baton.status = lambda: {
        "config": {"overrides": {}},
        "state": {"round_status": "stopped", "consumed_scheduled_task_id": "source-1"},
    }
    runtime.task_history.append(
        {
            "id": "markdown-1",
            "status": "stopped",
            "errors": ["Task stopped by user"],
            "pipeline_baton_step": "markdown_conversion",
            "pipeline_baton_source_task_id": "source-1",
        }
    )

    view = runtime.pipeline_baton_status()
    stage = next(stage for stage in view["stages"] if stage["step"] == "markdown_conversion")

    assert stage["status"] == "stopped"
    assert stage["tasks"][0]["error_count"] == 0
    assert view["summary"]["failed_stages"] == 0
    assert view["summary"]["stopped_stages"] == 1


def test_runtime_status_marks_a_stopped_stage_failed_for_a_different_task_error(
    monkeypatch, tmp_path
) -> None:
    runtime, _started = _runtime(monkeypatch, tmp_path)
    runtime._pipeline_baton.status = lambda: {
        "config": {"overrides": {}},
        "state": {"round_status": "completed", "consumed_scheduled_task_id": "source-1"},
    }
    runtime.task_history.extend(
        [
            {
                "id": "markdown-stopped",
                "status": "stopped",
                "errors": ["Task stopped by user"],
                "pipeline_baton_step": "markdown_conversion",
                "pipeline_baton_source_task_id": "source-1",
            },
            {
                "id": "markdown-failed",
                "status": "error",
                "errors": ["conversion failed"],
                "pipeline_baton_step": "markdown_conversion",
                "pipeline_baton_source_task_id": "source-1",
            },
        ]
    )

    view = runtime.pipeline_baton_status()
    stage = next(stage for stage in view["stages"] if stage["step"] == "markdown_conversion")

    assert stage["status"] == "failed"
    assert view["summary"]["failed_stages"] == 1
    assert view["summary"]["stopped_stages"] == 0


@pytest.mark.parametrize(
    ("result", "expected_task_id"),
    [
        (
            {
                "kb_id": "kb-a",
                "status": "failed",
                "failure_status": "invalid_index_result",
                "kb_index_task_id": "index-1",
                "ready_data_task_id": None,
            },
            "index-1",
        ),
        (
            {
                "kb_id": "kb-a",
                "status": "failed",
                "failure_status": "ready_launch_failed",
                "kb_index_task_id": "index-1",
                "ready_data_task_id": None,
            },
            "index-1",
        ),
        (
            {
                "kb_id": "kb-a",
                "status": "failed",
                "failure_status": "index_launch_failed",
                "kb_index_task_id": None,
                "ready_data_task_id": None,
            },
            None,
        ),
    ],
)
def test_runtime_status_projects_completed_baton_kb_failures(
    monkeypatch, tmp_path, result, expected_task_id
) -> None:
    runtime, _started = _runtime(monkeypatch, tmp_path)
    runtime._pipeline_baton.status = lambda: {
        "config": {"overrides": {}},
        "state": {
            "round_status": "completed",
            "kb_results": [result],
            "summary": {"attempted": 1, "succeeded": 0, "failed": 1, "failed_kbs": ["kb-a"]},
        },
    }

    view = runtime.pipeline_baton_status()
    stage = next(stage for stage in view["stages"] if stage["step"] == "rag_indexing")

    assert view["state"]["round_status"] == "completed"
    assert view["summary"]["status"] == "completed_with_errors"
    assert stage["status"] == "failed"
    assert stage["failures"] == [
        {
            "task_id": expected_task_id,
            "first_error_code": result["failure_status"],
            "first_error_summary": f"Knowledge base kb-a failed: {result['failure_status']}.",
        }
    ]
