from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import yaml

from ai_actuarial.api.services.ops_read import get_schedule_status
from ai_actuarial.shared_runtime import append_task_log
from ai_actuarial.task_runtime import NativeTaskRuntime, _FallbackScheduler
from tests.test_fastapi_ops_read_endpoints import _build_test_client, _patch_available_models

ROOT = Path(__file__).resolve().parents[1]
NPM_COMMAND = "npm.cmd" if os.name == "nt" else "npm"


def _configured_sources(status: dict[str, object]) -> set[str]:
    return {
        str(job["source"])
        for job in status["jobs"]  # type: ignore[index,union-attr]
        if job["kind"] == "configured_task"  # type: ignore[index]
    }


def _system_job_objects(runtime: NativeTaskRuntime) -> dict[str, object]:
    jobs: dict[str, object] = {}
    for job in runtime.scheduler.jobs:
        metadata = getattr(job, "_ops_metadata", {})
        if metadata.get("kind") != "configured_task":
            jobs[str(metadata.get("job_key") or "")] = job
    return jobs


def test_scheduler_status_has_stable_sanitized_identity_for_every_job_kind(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("ai_actuarial.task_runtime._new_scheduler", _FallbackScheduler)
    runtime = NativeTaskRuntime(
        ready_data_db_path=str(tmp_path / "ready.db"),
        ready_data_poll_interval_seconds=15,
        pipeline_baton_state_path=str(tmp_path / "pipeline.json"),
    )
    runtime._scheduler_loop_started = True
    runtime.set_site_config(
        {
            "defaults": {"schedule_interval": "daily"},
            "sites": [
                {
                    "name": "Actuarial Research",
                    "schedule_interval": "weekly",
                    "url": "https://example.test",
                }
            ],
            "scheduled_tasks": [
                {
                    "name": "Pricing Catalog",
                    "type": "catalog",
                    "interval": "every 2 hours",
                    "enabled": True,
                    "params": {
                        "category": "Pricing",
                        "api_key": "must-not-leak",
                        "callback": object(),
                    },
                }
            ],
        }
    )

    runtime.init_scheduler()
    first = get_schedule_status(runtime.scheduler)
    first_keys = {str(job["kind"]): str(job["job_key"]) for job in first["jobs"]}

    assert {job["kind"] for job in first["jobs"]} == {
        "configured_task",
        "site",
        "global",
        "pipeline_baton",
        "ready_data",
    }
    assert _configured_sources(first) == {"Pricing Catalog"}
    assert all(
        set(job)
        == {
            "job_key",
            "kind",
            "source",
            "display_name",
            "interval",
            "last_run",
            "next_run",
            "timezone",
            "utc_offset",
            "managed",
            "deletable",
        }
        for job in first["jobs"]
    )
    configured = next(job for job in first["jobs"] if job["kind"] == "configured_task")
    assert configured["source"] == "Pricing Catalog"
    assert configured["display_name"] == "Pricing Catalog"
    assert configured["managed"] is True
    assert configured["deletable"] is True
    assert "must-not-leak" not in repr(first)
    assert "callback" not in repr(first)
    assert "object at 0x" not in repr(first)

    runtime.init_scheduler()
    second = get_schedule_status(runtime.scheduler)
    second_keys = {str(job["kind"]): str(job["job_key"]) for job in second["jobs"]}
    assert second_keys == first_keys


def test_unmanaged_scheduler_job_identity_survives_runtime_reordering() -> None:
    first_job = SimpleNamespace(
        next_run=None,
        last_run=None,
        unit="hours",
        interval=1,
        at_time=None,
    )
    second_job = SimpleNamespace(
        next_run=None,
        last_run=None,
        unit="hours",
        interval=1,
        at_time=None,
    )
    schedule_ref = SimpleNamespace(jobs=[first_job, second_job])

    initial = get_schedule_status(schedule_ref)
    first_job_key = initial["jobs"][0]["job_key"]
    first_display_name = initial["jobs"][0]["display_name"]

    schedule_ref.jobs = [second_job, first_job]
    reordered = get_schedule_status(schedule_ref)

    assert reordered["jobs"][1]["job_key"] == first_job_key
    assert reordered["jobs"][1]["display_name"] == first_display_name


def test_scheduler_reinitialize_is_atomic_when_registration_fails(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("ai_actuarial.task_runtime._new_scheduler", _FallbackScheduler)
    runtime = NativeTaskRuntime(pipeline_baton_state_path=str(tmp_path / "pipeline.json"))
    runtime._scheduler_loop_started = True
    runtime.active_tasks["active-307"] = {"id": "active-307", "status": "running"}
    runtime.task_history.append({"id": "history-307", "status": "completed"})
    runtime.set_site_config(
        {
            "scheduled_tasks": [
                {
                    "name": "Old Recurrence",
                    "type": "catalog",
                    "interval": "daily",
                    "enabled": True,
                    "params": {},
                }
            ]
        }
    )
    runtime.init_scheduler()
    old_jobs = list(runtime.scheduler.jobs)
    old_status = get_schedule_status(runtime.scheduler)

    original_register = runtime._register_schedule

    def fail_new_registration(interval: str, *args, **kwargs):
        if interval == "every 7 hours":
            raise RuntimeError("forced registration failure")
        return original_register(interval, *args, **kwargs)

    monkeypatch.setattr(runtime, "_register_schedule", fail_new_registration)
    runtime.set_site_config(
        {
            "scheduled_tasks": [
                {
                    "name": "New Recurrence",
                    "type": "catalog",
                    "interval": "every 7 hours",
                    "enabled": True,
                    "params": {},
                }
            ]
        }
    )

    try:
        runtime.init_scheduler()
    except RuntimeError as exc:
        assert str(exc) == "forced registration failure"
    else:
        raise AssertionError("forced registration failure was swallowed")

    assert runtime.scheduler.jobs == old_jobs
    assert get_schedule_status(runtime.scheduler) == old_status
    assert runtime.active_tasks == {"active-307": {"id": "active-307", "status": "running"}}
    assert runtime.task_history[-1] == {"id": "history-307", "status": "completed"}


def test_scheduled_task_api_reconciles_and_preserves_task_surfaces(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    runtime = app.state.native_task_runtime
    config_path = Path(os.environ["CONFIG_PATH"])
    reader_headers = {"Authorization": f"Bearer {seed['reader_token']}"}
    operator_headers = {"Authorization": f"Bearer {seed['operator_token']}"}
    admin_headers = {"Authorization": f"Bearer {seed['admin_token']}"}

    runtime.active_tasks["active-307"] = {
        "id": "active-307",
        "name": "Already Running",
        "type": "catalog",
        "status": "running",
        "started_at": "2026-09-01T10:00:00+00:00",
        "errors": [],
    }
    runtime.task_history.append(
        {
            "id": "history-307",
            "name": "Past Run",
            "type": "catalog",
            "status": "completed",
            "started_at": "2026-08-31T10:00:00+00:00",
            "completed_at": "2026-08-31T10:01:00+00:00",
            "errors": [],
        }
    )
    append_task_log("active-307", "INFO", "Issue 307 log remains readable")

    assert client.get("/api/scheduled-tasks", headers=reader_headers).status_code == 200
    assert client.get("/api/schedule/status", headers=reader_headers).status_code == 200
    reader_write = client.post(
        "/api/scheduled-tasks/add",
        json={
            "name": "Reader Cannot Add",
            "type": "catalog",
            "interval": "daily",
            "enabled": True,
            "params": {},
        },
        headers=reader_headers,
    )
    assert reader_write.status_code == 403

    before = client.get("/api/schedule/status", headers=operator_headers).json()
    system_keys = {
        job["kind"]: job["job_key"] for job in before["jobs"] if job["kind"] != "configured_task"
    }
    system_jobs_before = _system_job_objects(runtime)

    added = client.post(
        "/api/scheduled-tasks/add",
        json={
            "name": "Issue 307 Recurrence",
            "type": "catalog",
            "interval": "every 2 hours",
            "enabled": True,
            "params": {"category": "AI"},
        },
        headers=operator_headers,
    )
    assert added.status_code == 200, added.text
    after_add = client.get("/api/schedule/status", headers=reader_headers).json()
    assert "Issue 307 Recurrence" in _configured_sources(after_add)

    updated = client.post(
        "/api/scheduled-tasks/update",
        json={
            "original_name": "Issue 307 Recurrence",
            "name": "Issue 307 Recurrence",
            "type": "catalog",
            "interval": "every 3 hours",
            "enabled": True,
            "params": {"category": "Risk"},
        },
        headers=admin_headers,
    )
    assert updated.status_code == 200, updated.text
    after_update = client.get("/api/schedule/status", headers=reader_headers).json()
    configured = next(
        job for job in after_update["jobs"] if job["source"] == "Issue 307 Recurrence"
    )
    assert configured["interval"] == "every 3 hours"

    deleted = client.post(
        "/api/scheduled-tasks/delete",
        json={"name": "Issue 307 Recurrence"},
        headers=operator_headers,
    )
    assert deleted.status_code == 200, deleted.text
    after_delete = client.get("/api/schedule/status", headers=reader_headers).json()
    assert "Issue 307 Recurrence" not in _configured_sources(after_delete)
    assert {
        job["kind"]: job["job_key"]
        for job in after_delete["jobs"]
        if job["kind"] != "configured_task"
    } == system_keys
    system_jobs_after = _system_job_objects(runtime)
    assert system_jobs_after.keys() == system_jobs_before.keys()
    assert all(system_jobs_after[key] is job for key, job in system_jobs_before.items())
    assert all(job["deletable"] is False for job in after_delete["jobs"] if not job["managed"])

    assert runtime.active_tasks["active-307"]["status"] == "running"
    assert any(task["id"] == "history-307" for task in runtime.task_history)
    assert client.get("/api/tasks/active", headers=reader_headers).status_code == 200
    assert client.get("/api/tasks/history", headers=reader_headers).status_code == 200
    log_response = client.get("/api/tasks/log/active-307", headers=reader_headers)
    assert log_response.status_code == 200
    assert "Issue 307 log remains readable" in log_response.json()["log"]
    stop_response = client.post("/api/tasks/stop/active-307", headers=operator_headers)
    assert stop_response.status_code == 200
    assert runtime.active_tasks["active-307"]["stop_requested"] is True

    written = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    assert all(
        task.get("name") != "Issue 307 Recurrence" for task in written.get("scheduled_tasks") or []
    )


def test_scheduled_task_api_rolls_back_yaml_and_runtime_on_registration_failure(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    runtime = app.state.native_task_runtime
    config_path = Path(os.environ["CONFIG_PATH"])
    headers = {"Authorization": f"Bearer {seed['operator_token']}"}
    previous_yaml = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    previous_status = client.get("/api/schedule/status", headers=headers).json()
    original_register = runtime._register_schedule

    def fail_new_registration(interval: str, *args, **kwargs):
        if interval == "every 7 hours":
            raise RuntimeError("forced registration failure")
        return original_register(interval, *args, **kwargs)

    monkeypatch.setattr(runtime, "_register_schedule", fail_new_registration)
    response = client.post(
        "/api/scheduled-tasks/add",
        json={
            "name": "Must Roll Back",
            "type": "catalog",
            "interval": "every 7 hours",
            "enabled": True,
            "params": {},
        },
        headers=headers,
    )

    assert response.status_code == 503, response.text
    assert response.json()["code"] == "scheduler_reconciliation_failed"
    assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == previous_yaml
    assert client.get("/api/schedule/status", headers=headers).json() == previous_status


def test_scheduled_task_api_rejects_noncanonical_single_digit_daily_hour(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_available_models(monkeypatch)
    client, _app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    headers = {"Authorization": f"Bearer {seed['operator_token']}"}

    response = client.post(
        "/api/scheduled-tasks/add",
        json={
            "name": "Single Digit Daily Hour",
            "type": "catalog",
            "interval": "daily at 9:00",
            "enabled": True,
            "params": {},
        },
        headers=headers,
    )

    assert response.status_code == 400, response.text
    assert all(
        task["name"] != "Single Digit Daily Hour"
        for task in client.get("/api/scheduled-tasks", headers=headers).json()["tasks"]
    )


def test_scheduled_task_update_rejects_duplicate_effective_identity(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_available_models(monkeypatch)
    client, _app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    headers = {"Authorization": f"Bearer {seed['operator_token']}"}
    added = client.post(
        "/api/scheduled-tasks/add",
        json={
            "name": "Duplicate Target",
            "type": "catalog",
            "interval": "every 1 hours",
            "enabled": True,
            "params": {},
        },
        headers=headers,
    )
    assert added.status_code == 200, added.text

    response = client.post(
        "/api/scheduled-tasks/update",
        json={
            "original_name": "Nightly Catalog",
            "name": "Duplicate Target",
            "type": "catalog",
            "interval": "every 1 hours",
            "enabled": True,
            "params": {},
        },
        headers=headers,
    )

    assert response.status_code == 400, response.text
    assert "Task name already exists" in response.text


def test_scheduled_task_update_rejects_stale_effective_interval(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    runtime = app.state.native_task_runtime
    config_path = Path(os.environ["CONFIG_PATH"])
    headers = {"Authorization": f"Bearer {seed['operator_token']}"}

    added = client.post(
        "/api/scheduled-tasks/add",
        json={
            "name": "Stale Interval",
            "type": "catalog",
            "interval": "every 1 hours",
            "enabled": True,
            "params": {},
        },
        headers=headers,
    )
    assert added.status_code == 200, added.text
    previous_yaml = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    previous_status = client.get("/api/schedule/status", headers=headers).json()

    def leave_scheduler_stale() -> None:
        return None

    app.state.init_scheduler = leave_scheduler_stale
    monkeypatch.setattr(runtime, "reconcile_configured_tasks", leave_scheduler_stale, raising=False)
    response = client.post(
        "/api/scheduled-tasks/update",
        json={
            "original_name": "Stale Interval",
            "name": "Stale Interval",
            "type": "catalog",
            "interval": "every 2 hours",
            "enabled": True,
            "params": {},
        },
        headers=headers,
    )

    assert response.status_code == 503, response.text
    assert response.json()["code"] == "scheduler_reconciliation_failed"
    assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == previous_yaml
    assert client.get("/api/schedule/status", headers=headers).json() == previous_status


def test_scheduled_tasks_rendered_component_contract() -> None:
    completed = subprocess.run(
        [
            NPM_COMMAND,
            "exec",
            "--",
            "tsx",
            "client/src/pages/tasks/ScheduledTasksSection.test.tsx",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Issue 307 scheduled tasks component assertions passed" in completed.stdout
