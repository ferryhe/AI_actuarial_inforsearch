from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import schedule
import yaml

from ai_actuarial.api.services.ops_read import get_schedule_status
from ai_actuarial.api.services.weekly_updates import previous_utc_iso_week_period
from ai_actuarial.schedule_presets import (
    SchedulePresetError,
    effective_task_timezone,
    parse_runtime_schedule,
    parse_structured_schedule,
)
from ai_actuarial.task_runtime import NativeTaskRuntime, _FallbackScheduler
from tests.test_fastapi_ops_read_endpoints import _build_test_client, _patch_available_models

ROOT = Path(__file__).resolve().parents[1]
NPM_COMMAND = "npm.cmd" if os.name == "nt" else "npm"


@pytest.mark.parametrize(
    ("interval", "timezone_name", "frequency", "quantity", "at_time"),
    [
        ("every 1 minutes", None, "minutes", 1, None),
        ("every 90 minutes", None, "minutes", 90, None),
        ("every 1 hours", None, "hours", 1, None),
        ("every 12 hours", None, "hours", 12, None),
        ("daily at 00:00", "UTC", "daily", 1, "00:00"),
        ("daily at 23:59", "Asia/Shanghai", "daily", 1, "23:59"),
        ("weekly at 00:30", "UTC", "weekly", 1, "00:30"),
        ("weekly at 23:45", "Asia/Shanghai", "weekly", 1, "23:45"),
    ],
)
def test_structured_schedule_parser_accepts_only_canonical_forms(
    interval: str,
    timezone_name: str | None,
    frequency: str,
    quantity: int,
    at_time: str | None,
) -> None:
    parsed = parse_structured_schedule(interval, timezone_name)

    assert parsed.interval == interval
    assert parsed.timezone == timezone_name
    assert parsed.frequency == frequency
    assert parsed.quantity == quantity
    assert parsed.at_time == at_time


@pytest.mark.parametrize(
    ("interval", "timezone_name"),
    [
        ("daily", "UTC"),
        ("weekly", "UTC"),
        ("every 0 hours", None),
        ("every -1 minutes", None),
        ("every 1.5 hours", None),
        ("every 1 hour", None),
        ("every 06 hours", None),
        ("every  6 hours", None),
        ("every 1 HOURS", None),
        ("every 1 hours extra", None),
        ("daily at 2:03", "UTC"),
        ("daily at  2:03", "UTC"),
        ("daily at 02:3", "UTC"),
        ("daily at 24:00", "UTC"),
        ("weekly on monday at 02:00", "UTC"),
        ("weekly at 02:00 extra", "UTC"),
        ("daily at 02:00", None),
        ("daily at 02:00", "America/New_York"),
        ("every 5 minutes", "UTC"),
        ("every 5 minutes", ""),
    ],
)
def test_structured_schedule_parser_rejects_legacy_or_invalid_forms(
    interval: str, timezone_name: str | None
) -> None:
    with pytest.raises(SchedulePresetError):
        parse_structured_schedule(interval, timezone_name)


@pytest.mark.parametrize(
    ("interval", "frequency", "at_time"),
    [
        ("daily", "daily", "00:30"),
        ("weekly", "weekly", "00:30"),
        ("daily at 2:03", "daily", "02:03"),
        ("every 1 hour", "hours", None),
    ],
)
def test_runtime_parser_preserves_preexisting_schedule_forms(
    interval: str, frequency: str, at_time: str | None
) -> None:
    parsed = parse_runtime_schedule(interval)

    assert parsed.frequency == frequency
    assert parsed.at_time == at_time
    assert parsed.timezone is None


@pytest.mark.parametrize(
    ("interval", "expected_interval", "frequency", "quantity", "at_time"),
    [
        ("every 06 hours", "every 6 hours", "hours", 6, None),
        ("every  6 hours", "every 6 hours", "hours", 6, None),
        ("every 6\thours", "every 6 hours", "hours", 6, None),
        ("every 01 minute", "every 1 minutes", "minutes", 1, None),
        ("daily at  2:03", "daily at 02:03", "daily", 1, "02:03"),
    ],
)
def test_runtime_parser_accepts_only_preexisting_free_text_variants(
    interval: str,
    expected_interval: str,
    frequency: str,
    quantity: int,
    at_time: str | None,
) -> None:
    parsed = parse_runtime_schedule(interval)

    assert parsed.interval == expected_interval
    assert parsed.frequency == frequency
    assert parsed.quantity == quantity
    assert parsed.at_time == at_time
    assert parsed.timezone is None
    assert parsed.legacy is True


@pytest.mark.parametrize(
    "interval",
    [
        "every 0 hours",
        "every -1 hours",
        "every 6 days",
        "every 6 hours extra",
        "daily  at 2:03",
        "daily at 2 :03",
        "weekly at  2:03",
    ],
)
def test_runtime_parser_does_not_expand_beyond_preexisting_free_text_grammar(
    interval: str,
) -> None:
    with pytest.raises(SchedulePresetError):
        parse_runtime_schedule(interval)


@pytest.mark.parametrize(
    ("task_type", "interval", "stored_timezone", "expected_timezone"),
    [
        ("weekly_summary", "weekly", None, "UTC"),
        ("weekly_summary", " WEEKLY ", None, "UTC"),
        ("weekly_summary", "daily", None, None),
        ("weekly_summary", "daily at 02:03", None, None),
        ("weekly_summary", "weekly at 02:03", None, None),
        ("weekly_summary", "every 6 hours", None, None),
        ("catalog", "weekly", None, None),
        ("weekly_summary", "weekly", "Asia/Shanghai", "Asia/Shanghai"),
    ],
)
def test_effective_task_timezone_preserves_only_the_historical_weekly_summary_default(
    task_type: str,
    interval: str,
    stored_timezone: str | None,
    expected_timezone: str | None,
) -> None:
    assert effective_task_timezone(task_type, interval, stored_timezone) == expected_timezone


def test_scheduled_task_api_persists_and_reconciles_structured_presets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    headers = {"Authorization": f"Bearer {seed['operator_token']}"}
    config_path = Path(os.environ["CONFIG_PATH"])

    accepted = [
        ("Minute Rollup", "every 15 minutes", None),
        ("Hourly Rollup", "every 6 hours", None),
        ("UTC Daily", "daily at 02:05", "UTC"),
        ("Shanghai Weekly", "weekly at 00:30", "Asia/Shanghai"),
        ("Weekly Update Summary", "weekly at 00:30", "UTC"),
    ]
    for name, interval, timezone_name in accepted:
        payload: dict[str, object] = {
            "name": name,
            "type": "weekly_summary" if name == "Weekly Update Summary" else "catalog",
            "interval": interval,
            "enabled": True,
            "params": (
                {
                    "relative_period": "custom",
                    "period_start": "2026-08-01T00:00:00+00:00",
                    "period_end": "2026-08-08T00:00:00+00:00",
                }
                if name == "Weekly Update Summary"
                else {}
            ),
        }
        if timezone_name is not None:
            payload["timezone"] = timezone_name
        response = client.post("/api/scheduled-tasks/add", json=payload, headers=headers)
        assert response.status_code == 200, response.text

    read_tasks = client.get("/api/scheduled-tasks", headers=headers).json()["tasks"]
    persisted_tasks = (yaml.safe_load(config_path.read_text(encoding="utf-8")) or {})[
        "scheduled_tasks"
    ]
    for name, interval, timezone_name in accepted:
        expected = {"interval": interval}
        if timezone_name is not None:
            expected["timezone"] = timezone_name
        for collection in (read_tasks, persisted_tasks):
            task = next(item for item in collection if item["name"] == name)
            assert {key: task[key] for key in expected} == expected
            if timezone_name is None:
                assert "timezone" not in task

    summary_task = next(task for task in persisted_tasks if task["name"] == "Weekly Update Summary")
    assert summary_task["params"] == {"relative_period": "previous_week"}

    status = client.get("/api/schedule/status", headers=headers).json()
    weekly_job = next(job for job in status["jobs"] if job["source"] == "Shanghai Weekly")
    assert weekly_job["interval"] == "weekly on monday at 00:30"
    assert weekly_job["timezone"] == "Asia/Shanghai"
    assert weekly_job["utc_offset"] == "+08:00"
    assert datetime.fromisoformat(weekly_job["next_run"]).utcoffset() is not None
    runtime_job = next(
        job
        for job in app.state.native_task_runtime.scheduler.jobs
        if getattr(job, "_ops_metadata", {}).get("source") == "Shanghai Weekly"
    )
    assert runtime_job.start_day == "monday"
    assert str(runtime_job.at_time_zone) == "Asia/Shanghai"

    fixed_update = client.post(
        "/api/scheduled-tasks/update",
        json={
            "original_name": "UTC Daily",
            "name": "UTC Daily",
            "interval": "daily at 03:15",
            "timezone": "Asia/Shanghai",
        },
        headers=headers,
    )
    assert fixed_update.status_code == 200, fixed_update.text
    rolling_update = client.post(
        "/api/scheduled-tasks/update",
        json={
            "original_name": "UTC Daily",
            "name": "UTC Daily",
            "interval": "every 2 hours",
        },
        headers=headers,
    )
    assert rolling_update.status_code == 200, rolling_update.text
    updated_task = next(
        task
        for task in client.get("/api/scheduled-tasks", headers=headers).json()["tasks"]
        if task["name"] == "UTC Daily"
    )
    assert updated_task["interval"] == "every 2 hours"
    assert "timezone" not in updated_task


def test_invalid_add_and_update_leave_yaml_and_effective_scheduler_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_available_models(monkeypatch)
    client, _app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    headers = {"Authorization": f"Bearer {seed['operator_token']}"}
    config_path = Path(os.environ["CONFIG_PATH"])
    before_yaml = config_path.read_text(encoding="utf-8")
    before_status = client.get("/api/schedule/status", headers=headers).json()

    invalid = [
        ("every 0 hours", None, "catalog"),
        ("every -1 minutes", None, "catalog"),
        ("every 1 hour", None, "catalog"),
        ("every 06 hours", None, "catalog"),
        ("every  6 hours", None, "catalog"),
        ("daily at 2:03", "UTC", "catalog"),
        ("daily at  2:03", "UTC", "catalog"),
        ("weekly at 24:00", "UTC", "catalog"),
        ("weekly at 02:00 extra", "UTC", "catalog"),
        ("daily at 02:00", None, "catalog"),
        ("daily at 02:00", "America/New_York", "catalog"),
        ("every 15 minutes", "UTC", "catalog"),
        ("every 15 minutes", "", "catalog"),
        ("daily at 02:00", "Asia/Shanghai", "weekly_summary"),
        ("weekly at 02:00", "Asia/Shanghai", "weekly_summary"),
    ]
    for index, (interval, timezone_name, task_type) in enumerate(invalid):
        payload: dict[str, object] = {
            "name": f"Invalid {index}",
            "type": task_type,
            "interval": interval,
            "enabled": True,
            "params": {},
        }
        if timezone_name is not None:
            payload["timezone"] = timezone_name
        response = client.post("/api/scheduled-tasks/add", json=payload, headers=headers)
        assert response.status_code == 400, (payload, response.text)
        assert config_path.read_text(encoding="utf-8") == before_yaml
        assert client.get("/api/schedule/status", headers=headers).json() == before_status

    null_timezone = client.post(
        "/api/scheduled-tasks/add",
        json={
            "name": "Invalid null timezone",
            "type": "catalog",
            "interval": "every 15 minutes",
            "timezone": None,
            "enabled": True,
            "params": {},
        },
        headers=headers,
    )
    assert null_timezone.status_code == 400, null_timezone.text
    assert config_path.read_text(encoding="utf-8") == before_yaml
    assert client.get("/api/schedule/status", headers=headers).json() == before_status

    for interval, timezone_name in (
        ("every 06 hours", None),
        ("every  6 hours", None),
        ("daily at  2:03", "UTC"),
    ):
        payload: dict[str, object] = {
            "original_name": "Nightly Catalog",
            "name": "Nightly Catalog",
            "interval": interval,
        }
        if timezone_name is not None:
            payload["timezone"] = timezone_name
        legacy_update = client.post("/api/scheduled-tasks/update", json=payload, headers=headers)
        assert legacy_update.status_code == 400, legacy_update.text
        assert config_path.read_text(encoding="utf-8") == before_yaml
        assert client.get("/api/schedule/status", headers=headers).json() == before_status

    update = client.post(
        "/api/scheduled-tasks/update",
        json={
            "original_name": "Nightly Catalog",
            "name": "Nightly Catalog",
            "interval": "weekly at 2:00",
            "timezone": "UTC",
        },
        headers=headers,
    )
    assert update.status_code == 400, update.text
    assert config_path.read_text(encoding="utf-8") == before_yaml
    assert client.get("/api/schedule/status", headers=headers).json() == before_status

    timezone_only_update = client.post(
        "/api/scheduled-tasks/update",
        json={
            "original_name": "Nightly Catalog",
            "name": "Nightly Catalog",
            "timezone": "UTC",
        },
        headers=headers,
    )
    assert timezone_only_update.status_code == 400, timezone_only_update.text
    assert config_path.read_text(encoding="utf-8") == before_yaml
    assert client.get("/api/schedule/status", headers=headers).json() == before_status


def test_legacy_edit_without_schedule_fields_preserves_shape_and_local_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    headers = {"Authorization": f"Bearer {seed['operator_token']}"}
    config_path = Path(os.environ["CONFIG_PATH"])

    response = client.post(
        "/api/scheduled-tasks/update",
        json={
            "original_name": "Nightly Catalog",
            "name": "Nightly Catalog",
            "enabled": False,
            "params": {"category": "Pricing"},
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    task = next(
        item
        for item in (yaml.safe_load(config_path.read_text(encoding="utf-8")) or {})[
            "scheduled_tasks"
        ]
        if item["name"] == "Nightly Catalog"
    )
    assert task["interval"] == "daily"
    assert "timezone" not in task

    runtime = app.state.native_task_runtime
    restarted = NativeTaskRuntime(pipeline_baton_state_path=str(tmp_path / "restart.json"))
    restarted._scheduler_loop_started = True
    for legacy_interval, expected_time, expected_day in (
        ("daily", "00:30", None),
        ("weekly", "00:30", "monday"),
        ("daily at 2:03", "02:03", None),
        ("weekly at 22:15", "22:15", "monday"),
    ):
        legacy_task = {**task, "interval": legacy_interval, "enabled": True}
        config = {"scheduled_tasks": [legacy_task]}
        runtime.set_site_config(config)
        runtime.init_scheduler()
        first_job = next(
            job
            for job in runtime.scheduler.jobs
            if getattr(job, "_ops_metadata", {}).get("kind") == "configured_task"
        )
        assert first_job.at_time.strftime("%H:%M") == expected_time
        assert first_job.start_day == expected_day
        assert first_job.at_time_zone is None

        restarted.set_site_config(config)
        restarted.init_scheduler()
        restarted_job = next(
            job
            for job in restarted.scheduler.jobs
            if getattr(job, "_ops_metadata", {}).get("kind") == "configured_task"
        )
        assert restarted_job.at_time.strftime("%H:%M") == expected_time
        assert restarted_job.start_day == expected_day
        assert restarted_job.at_time_zone is None
        assert legacy_task["interval"] == legacy_interval
        assert "timezone" not in legacy_task


def test_free_text_legacy_schedules_survive_edit_reinit_and_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    headers = {"Authorization": f"Bearer {seed['operator_token']}"}
    config_path = Path(os.environ["CONFIG_PATH"])
    legacy_cases = [
        ("Leading Zero Hours", "every 06 hours", "hours", 6, None),
        ("Whitespace Hours", "every  6 hours", "hours", 6, None),
        ("Whitespace Daily", "daily at  2:03", "days", 1, "02:03"),
    ]
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config["scheduled_tasks"] = [
        {
            "name": name,
            "type": "catalog",
            "interval": interval,
            "enabled": True,
            "params": {"category": "AI"},
        }
        for name, interval, _unit, _quantity, _at_time in legacy_cases
    ]
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    app.state.set_site_config(config)
    app.state.init_scheduler()

    for name, _interval, _unit, _quantity, _at_time in legacy_cases:
        response = client.post(
            "/api/scheduled-tasks/update",
            json={
                "original_name": name,
                "name": name,
                "enabled": True,
                "params": {"category": "Pricing"},
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text

    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    for name, interval, _unit, _quantity, _at_time in legacy_cases:
        task = next(task for task in persisted["scheduled_tasks"] if task["name"] == name)
        assert task["interval"] == interval
        assert "timezone" not in task
        assert task["params"] == {"category": "Pricing"}

    app.state.init_scheduler()
    restarted = NativeTaskRuntime(
        pipeline_baton_state_path=str(tmp_path / "restart-free-text.json")
    )
    restarted._scheduler_loop_started = True
    restarted.set_site_config(persisted)
    restarted.init_scheduler()

    for scheduler in (app.state.native_task_runtime.scheduler, restarted.scheduler):
        for name, _interval, unit, quantity, at_time in legacy_cases:
            job = next(
                job
                for job in scheduler.jobs
                if getattr(job, "_ops_metadata", {}).get("source") == name
            )
            assert job.unit == unit
            assert job.interval == quantity
            assert (job.at_time.strftime("%H:%M") if job.at_time is not None else None) == at_time
            assert job.at_time_zone is None

    after_restart = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    assert after_restart["scheduled_tasks"] == persisted["scheduled_tasks"]


def test_legacy_task_type_can_be_edited_only_while_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    headers = {"Authorization": f"Bearer {seed['operator_token']}"}
    config_path = Path(os.environ["CONFIG_PATH"])
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config["scheduled_tasks"].append(
        {
            "name": "Weekly Update Explanation",
            "type": "weekly_explanation",
            "interval": "weekly",
            "enabled": False,
            "params": {"relative_period": "previous_week"},
        }
    )
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    app.state.set_site_config(config)
    app.state.init_scheduler()

    response = client.post(
        "/api/scheduled-tasks/update",
        json={
            "original_name": "Weekly Update Explanation",
            "name": "Renamed Weekly Explanation",
            "type": "weekly_explanation",
            "enabled": True,
            "params": {"relative_period": "previous_week", "max_files": 250},
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    saved_config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    saved_task = next(
        task
        for task in saved_config["scheduled_tasks"]
        if task["name"] == "Renamed Weekly Explanation"
    )
    assert saved_task == {
        "name": "Renamed Weekly Explanation",
        "type": "weekly_explanation",
        "interval": "weekly",
        "enabled": True,
        "params": {"relative_period": "previous_week", "max_files": 250},
    }

    runtime_job = next(
        job
        for job in app.state.native_task_runtime.scheduler.jobs
        if getattr(job, "_ops_metadata", {}).get("source") == "Renamed Weekly Explanation"
    )
    assert runtime_job.start_day == "monday"
    assert runtime_job.at_time.strftime("%H:%M") == "00:30"
    assert runtime_job.at_time_zone is None
    status_job = next(
        job
        for job in client.get("/api/schedule/status", headers=headers).json()["jobs"]
        if job["source"] == "Renamed Weekly Explanation"
    )
    assert status_job["interval"] == "weekly on monday at 00:30"
    assert status_job["timezone"] == "process-local"

    before_rejected_yaml = config_path.read_text(encoding="utf-8")
    before_rejected_status = client.get("/api/schedule/status", headers=headers).json()
    unsupported_create = client.post(
        "/api/scheduled-tasks/add",
        json={
            "name": "New Weekly Explanation",
            "type": "weekly_explanation",
            "interval": "weekly at 00:30",
            "timezone": "UTC",
            "enabled": True,
            "params": {},
        },
        headers=headers,
    )
    unsupported_change = client.post(
        "/api/scheduled-tasks/update",
        json={
            "original_name": "Nightly Catalog",
            "name": "Nightly Catalog",
            "type": "weekly_explanation",
        },
        headers=headers,
    )

    assert unsupported_create.status_code == 400, unsupported_create.text
    assert unsupported_change.status_code == 400, unsupported_change.text
    assert config_path.read_text(encoding="utf-8") == before_rejected_yaml
    assert client.get("/api/schedule/status", headers=headers).json() == before_rejected_status


def test_weekly_summary_type_boundary_requires_an_explicit_structured_schedule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    headers = {"Authorization": f"Bearer {seed['operator_token']}"}
    config_path = Path(os.environ["CONFIG_PATH"])
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config["scheduled_tasks"] = [
        {
            "name": "Legacy Summary",
            "type": "weekly_summary",
            "interval": "weekly",
            "enabled": True,
            "params": {"relative_period": "previous_week"},
        },
        {
            "name": "Weekly Catalog",
            "type": "catalog",
            "interval": "weekly",
            "enabled": True,
            "params": {"category": "AI"},
        },
    ]
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    app.state.set_site_config(config)
    app.state.init_scheduler()
    before_yaml = config_path.read_text(encoding="utf-8")
    before_status = client.get("/api/schedule/status", headers=headers).json()

    for original_name, new_type in (
        ("Legacy Summary", "catalog"),
        ("Weekly Catalog", "weekly_summary"),
    ):
        response = client.post(
            "/api/scheduled-tasks/update",
            json={
                "original_name": original_name,
                "name": original_name,
                "type": new_type,
            },
            headers=headers,
        )
        assert response.status_code == 400, response.text
        assert config_path.read_text(encoding="utf-8") == before_yaml
        assert client.get("/api/schedule/status", headers=headers).json() == before_status

    leave_summary = client.post(
        "/api/scheduled-tasks/update",
        json={
            "original_name": "Legacy Summary",
            "name": "Legacy Summary",
            "type": "catalog",
            "interval": "weekly at 00:30",
            "timezone": "UTC",
        },
        headers=headers,
    )
    enter_summary = client.post(
        "/api/scheduled-tasks/update",
        json={
            "original_name": "Weekly Catalog",
            "name": "Weekly Catalog",
            "type": "weekly_summary",
            "interval": "weekly at 01:15",
            "timezone": "UTC",
        },
        headers=headers,
    )
    assert leave_summary.status_code == 200, leave_summary.text
    assert enter_summary.status_code == 200, enter_summary.text
    saved_tasks = (yaml.safe_load(config_path.read_text(encoding="utf-8")) or {})["scheduled_tasks"]
    saved_by_name = {task["name"]: task for task in saved_tasks}
    assert saved_by_name["Legacy Summary"]["type"] == "catalog"
    assert saved_by_name["Legacy Summary"]["interval"] == "weekly at 00:30"
    assert saved_by_name["Legacy Summary"]["timezone"] == "UTC"
    assert saved_by_name["Weekly Catalog"]["type"] == "weekly_summary"
    assert saved_by_name["Weekly Catalog"]["interval"] == "weekly at 01:15"
    assert saved_by_name["Weekly Catalog"]["timezone"] == "UTC"
    assert saved_by_name["Weekly Catalog"]["params"] == {
        "category": "AI",
        "relative_period": "previous_week",
    }


@pytest.mark.parametrize("scheduler_cls", [schedule.Scheduler, _FallbackScheduler])
@pytest.mark.parametrize("timezone_name", ["UTC", "Asia/Shanghai"])
def test_fixed_time_registration_uses_requested_wall_clock_and_monday(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scheduler_cls: type[object],
    timezone_name: str,
) -> None:
    frozen_utc = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[no-untyped-def]
            if tz is None:
                return frozen_utc.replace(tzinfo=None)
            return frozen_utc.astimezone(tz)

    monkeypatch.setattr(schedule.datetime, "datetime", FrozenDateTime)
    runtime = NativeTaskRuntime(pipeline_baton_state_path=str(tmp_path / "pipeline.json"))
    runtime.scheduler = scheduler_cls()

    daily = runtime._register_schedule("daily at 00:30", lambda: None, at_timezone=timezone_name)
    weekly = runtime._register_schedule("weekly at 00:30", lambda: None, at_timezone=timezone_name)

    assert str(daily.at_time_zone) == timezone_name
    assert str(weekly.at_time_zone) == timezone_name
    assert weekly.start_day == "monday"
    if daily.next_run is not None:
        next_in_timezone = daily.next_run.astimezone().astimezone(ZoneInfo(timezone_name))
        assert (next_in_timezone.hour, next_in_timezone.minute) == (0, 30)
        assert next_in_timezone.date().isoformat() == "2026-08-31"
    if weekly.next_run is not None:
        next_in_timezone = weekly.next_run.astimezone().astimezone(ZoneInfo(timezone_name))
        assert (next_in_timezone.weekday(), next_in_timezone.hour, next_in_timezone.minute) == (
            0,
            0,
            30,
        )


def test_status_attaches_process_local_offset_without_claiming_utc() -> None:
    naive_next = datetime(2026, 9, 1, 2, 0)
    job = SimpleNamespace(
        next_run=naive_next,
        last_run=datetime(2026, 8, 31, 2, 0),
        unit="days",
        interval=1,
        at_time=naive_next.time(),
        start_day=None,
        _ops_metadata={
            "job_key": "legacy-local",
            "kind": "configured_task",
            "source": "Legacy Local",
            "display_name": "Legacy Local",
            "managed": True,
            "deletable": True,
        },
    )

    status = get_schedule_status(SimpleNamespace(jobs=[job]))["jobs"][0]

    assert status["timezone"] == "process-local"
    assert status["utc_offset"].startswith(("+", "-"))
    assert datetime.fromisoformat(status["next_run"]).utcoffset() is not None
    assert datetime.fromisoformat(status["last_run"]).utcoffset() is not None


def test_weekly_summary_period_stays_on_utc_week_at_shanghai_monday_boundary() -> None:
    shanghai_monday = datetime(2026, 8, 31, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert previous_utc_iso_week_period(shanghai_monday) == (
        "2026-08-17T00:00:00+00:00",
        "2026-08-24T00:00:00+00:00",
    )
    assert shanghai_monday.astimezone(timezone.utc).isoformat() == "2026-08-30T16:30:00+00:00"


@pytest.mark.parametrize(
    ("interval", "expected_timezone", "expected_unit", "expected_time"),
    [
        ("weekly", "UTC", "weeks", "00:30"),
        ("daily", None, "days", "00:30"),
        ("daily at 2:03", None, "days", "02:03"),
        ("every 6 hours", None, "hours", None),
        ("weekly at 02:03", None, "weeks", "02:03"),
    ],
)
def test_legacy_weekly_summary_uses_utc_only_for_the_exact_weekly_interval(
    tmp_path: Path,
    interval: str,
    expected_timezone: str | None,
    expected_unit: str,
    expected_time: str | None,
) -> None:
    runtime = NativeTaskRuntime(
        pipeline_baton_state_path=str(tmp_path / f"summary-{expected_unit}.json")
    )
    runtime._scheduler_loop_started = True
    runtime.set_site_config(
        {
            "scheduled_tasks": [
                {
                    "name": "Legacy Weekly Summary",
                    "type": "weekly_summary",
                    "interval": interval,
                    "enabled": True,
                    "params": {"relative_period": "previous_week"},
                }
            ]
        }
    )

    runtime.init_scheduler()

    job = runtime.scheduler.jobs[0]
    assert (str(job.at_time_zone) if job.at_time_zone is not None else None) == expected_timezone
    assert job.unit == expected_unit
    assert (job.at_time.strftime("%H:%M") if job.at_time is not None else None) == expected_time
    assert getattr(job, "_ops_metadata", {}).get("timezone") == expected_timezone


def test_legacy_weekly_summary_schedules_survive_edit_reinit_and_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    headers = {"Authorization": f"Bearer {seed['operator_token']}"}
    config_path = Path(os.environ["CONFIG_PATH"])
    legacy_cases = [
        ("Exact Weekly Summary", "weekly", "UTC"),
        ("Daily Summary", "daily", None),
        ("Daily At Summary", "daily at 2:03", None),
        ("Rolling Summary", "every 6 hours", None),
    ]
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config["scheduled_tasks"] = [
        {
            "name": name,
            "type": "weekly_summary",
            "interval": interval,
            "enabled": True,
            "params": {"period_start": "legacy"},
        }
        for name, interval, _timezone_name in legacy_cases
    ]
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    app.state.set_site_config(config)
    app.state.init_scheduler()

    for name, _interval, _timezone_name in legacy_cases:
        response = client.post(
            "/api/scheduled-tasks/update",
            json={
                "original_name": name,
                "name": name,
                "type": "weekly_summary",
                "enabled": True,
                "params": {"max_files": 250},
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text

    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    for name, interval, _timezone_name in legacy_cases:
        task = next(task for task in persisted["scheduled_tasks"] if task["name"] == name)
        assert task["interval"] == interval
        assert "timezone" not in task
        assert task["params"] == {"max_files": 250, "relative_period": "previous_week"}

    app.state.init_scheduler()
    restarted = NativeTaskRuntime(pipeline_baton_state_path=str(tmp_path / "summary-restart.json"))
    restarted._scheduler_loop_started = True
    restarted.set_site_config(persisted)
    restarted.init_scheduler()

    for scheduler in (app.state.native_task_runtime.scheduler, restarted.scheduler):
        for name, _interval, expected_timezone in legacy_cases:
            job = next(
                job
                for job in scheduler.jobs
                if getattr(job, "_ops_metadata", {}).get("source") == name
            )
            actual_timezone = str(job.at_time_zone) if job.at_time_zone is not None else None
            assert actual_timezone == expected_timezone
            assert getattr(job, "_ops_metadata", {}).get("timezone") == expected_timezone

    after_restart = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    assert after_restart["scheduled_tasks"] == persisted["scheduled_tasks"]


def test_legacy_weekly_summary_runtime_stays_utc_and_forces_previous_week(
    tmp_path: Path,
) -> None:
    runtime = NativeTaskRuntime(pipeline_baton_state_path=str(tmp_path / "summary.json"))
    runtime._scheduler_loop_started = True
    started: list[tuple[str, dict[str, object]]] = []

    def record_start(
        task_type: str,
        params: dict[str, object],
        *,
        task_name: str | None = None,
    ) -> str:
        del task_name
        started.append((task_type, params))
        return "weekly-summary-task"

    runtime.start_background_task = record_start  # type: ignore[method-assign]
    runtime.set_site_config(
        {
            "scheduled_tasks": [
                {
                    "name": "Weekly Update Summary",
                    "type": "weekly_summary",
                    "interval": "weekly",
                    "enabled": True,
                    "params": {
                        "period_start": "2026-08-01T00:00:00+00:00",
                        "period_end": "2026-08-08T00:00:00+00:00",
                    },
                }
            ]
        }
    )

    runtime.init_scheduler()
    job = runtime.scheduler.jobs[0]
    job.job_func()

    assert str(job.at_time_zone) == "UTC"
    assert job.start_day == "monday"
    assert started == [
        (
            "weekly_summary",
            {"relative_period": "previous_week", "name": "Scheduled: Weekly Update Summary"},
        )
    ]


def test_schedule_preset_copy_is_complete_in_english_and_chinese() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "client" / "src" / "hooks" / "use-i18n.ts"
    ).read_text(encoding="utf-8")

    for value in (
        '"tasks.sched.frequency.minutes": "Every N minutes"',
        '"tasks.sched.frequency.weekly": "Weekly on Monday at a set time"',
        '"tasks.sched.timezone.shanghai": "China Standard Time (Asia/Shanghai)"',
        '"tasks.sched.frequency.minutes": "每 N 分钟"',
        '"tasks.sched.frequency.weekly": "每周一在指定时间"',
        '"tasks.sched.timezone.shanghai": "中国标准时间（Asia/Shanghai）"',
        '"tasks.sched.legacy_schedule_hint": "This legacy schedule remains unchanged until you explicitly save a structured schedule."',
        '"tasks.sched.legacy_weekly_summary_migration": "This legacy Weekly Summary keeps the cadence shown until you explicitly convert it."',
        '"tasks.sched.convert_weekly_summary_utc": "Convert to Weekly UTC"',
        '"tasks.sched.legacy_schedule_hint": "此旧版计划会保持原样，直到您明确保存结构化计划。"',
        '"tasks.sched.legacy_weekly_summary_migration": "此旧版每周摘要会保持当前显示的频率，直到您明确转换。"',
        '"tasks.sched.convert_weekly_summary_utc": "转换为每周 UTC"',
    ):
        assert value in source


def test_schedule_preset_rendered_component_contract() -> None:
    completed = subprocess.run(
        [
            NPM_COMMAND,
            "exec",
            "--",
            "tsx",
            "client/src/pages/tasks/SchedulePresetFields.test.tsx",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Issue 312 schedule preset component assertions passed" in completed.stdout
