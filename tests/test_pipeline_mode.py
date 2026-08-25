from __future__ import annotations

from typing import Any

from ai_actuarial.task_runtime import (
    NativeTaskRuntime,
    _FallbackScheduler,
    pipeline_mode_for_site,
)


# --- pure decision function -------------------------------------------------


def test_pipeline_mode_defaults_to_legacy() -> None:
    assert pipeline_mode_for_site({}, {}) == "legacy"
    assert pipeline_mode_for_site({"full_pipeline": False}, {}) == "legacy"
    assert pipeline_mode_for_site({"full_pipeline": "false"}, {}) == "legacy"


def test_pipeline_mode_site_flag_opts_in() -> None:
    assert pipeline_mode_for_site({"full_pipeline": True}, {}) == "full"
    assert pipeline_mode_for_site({"full_pipeline": "true"}, {}) == "full"
    assert pipeline_mode_for_site({"full_pipeline": 1}, {}) == "full"


def test_pipeline_mode_global_fallback_overrides_site() -> None:
    site = {"full_pipeline": True}
    assert pipeline_mode_for_site(site, {"full_pipeline_fallback": True}) == "legacy"
    assert pipeline_mode_for_site(site, {"full_pipeline_fallback": "true"}) == "legacy"
    # A false fallback does not block the site opt-in.
    assert pipeline_mode_for_site(site, {"full_pipeline_fallback": False}) == "full"


def test_pipeline_mode_global_fallback_alone() -> None:
    assert pipeline_mode_for_site({}, {"full_pipeline_fallback": True}) == "legacy"
    assert pipeline_mode_for_site({"full_pipeline": False}, {"full_pipeline_fallback": True}) == "legacy"


def test_pipeline_mode_tolerates_none_global_config() -> None:
    assert pipeline_mode_for_site({"full_pipeline": True}, None) == "full"


# --- scheduler wiring -------------------------------------------------------


def _make_runtime(monkeypatch, config: dict[str, Any]) -> tuple[NativeTaskRuntime, list[tuple[str, dict[str, Any]]]]:
    monkeypatch.setattr("ai_actuarial.task_runtime._new_scheduler", lambda: _FallbackScheduler())
    runtime = NativeTaskRuntime()
    # Avoid spawning the daemon scheduler loop during the test.
    runtime._scheduler_loop_started = True
    monkeypatch.setattr(NativeTaskRuntime, "_load_site_config", lambda self: config)
    started: list[tuple[str, dict[str, Any]]] = []

    def _record(collection_type: str, data: dict[str, Any], **kwargs: Any) -> str:
        started.append((collection_type, dict(data)))
        return "task-x"

    monkeypatch.setattr(runtime, "start_background_task", _record)
    return runtime, started


def test_scheduler_dispatches_full_pipeline_for_opted_in_site(monkeypatch) -> None:
    config = {
        "defaults": {},
        "sites": [
            {"name": "Gray Site", "url": "https://gray.example", "schedule_interval": "daily", "full_pipeline": True},
            {"name": "Legacy Site", "url": "https://legacy.example", "schedule_interval": "daily"},
        ],
    }
    runtime, started = _make_runtime(monkeypatch, config)
    runtime.init_scheduler()
    assert len(runtime.scheduler.jobs) == 2
    for job in runtime.scheduler.jobs:
        job.job_func()

    by_site = {data["site"]: collection_type for collection_type, data in started}
    assert by_site["Gray Site"] == "full_pipeline"
    assert by_site["Legacy Site"] == "scheduled"

    full_data = next(data for collection_type, data in started if collection_type == "full_pipeline")
    assert full_data["source_collection_type"] == "scheduled"
    assert full_data["site"] == "Gray Site"


def test_scheduler_full_pipeline_task_data_carries_site_and_source(monkeypatch) -> None:
    config = {
        "defaults": {},
        "sites": [
            {"name": "Gray Site", "url": "https://gray.example", "schedule_interval": "daily", "full_pipeline": True, "max_pages": 30, "max_depth": 2},
        ],
    }
    runtime, started = _make_runtime(monkeypatch, config)
    runtime.init_scheduler()
    runtime.scheduler.jobs[0].job_func()

    collection_type, data = started[0]
    assert collection_type == "full_pipeline"
    assert data["source_collection_type"] == "scheduled"
    assert data["site"] == "Gray Site"
    assert data["max_pages"] == 30
    assert data["max_depth"] == 2


def test_scheduler_global_fallback_forces_legacy(monkeypatch) -> None:
    config = {
        "defaults": {"full_pipeline_fallback": True},
        "sites": [
            {"name": "Gray Site", "url": "https://gray.example", "schedule_interval": "daily", "full_pipeline": True},
        ],
    }
    runtime, started = _make_runtime(monkeypatch, config)
    runtime.init_scheduler()
    runtime.scheduler.jobs[0].job_func()
    assert started[0][0] == "scheduled"


def test_scheduler_site_without_flag_is_legacy(monkeypatch) -> None:
    config = {
        "defaults": {},
        "sites": [
            {"name": "Plain Site", "url": "https://plain.example", "schedule_interval": "daily"},
        ],
    }
    runtime, started = _make_runtime(monkeypatch, config)
    runtime.init_scheduler()
    runtime.scheduler.jobs[0].job_func()
    assert started[0][0] == "scheduled"
    assert started[0][1]["site"] == "Plain Site"
