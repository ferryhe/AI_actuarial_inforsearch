from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from ai_actuarial.api.services import ops_write
from ai_actuarial.api.services.ops_read import list_task_history
from ai_actuarial.collectors.base import CollectionResult
from ai_actuarial.task_runtime import NativeTaskRuntime
from tests.test_fastapi_ops_read_endpoints import _build_test_client, _patch_available_models


def _assert_aware_utc(value: str) -> None:
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timezone.utc.utcoffset(parsed)


def test_native_task_start_success_and_failure_timestamps_are_utc(monkeypatch) -> None:
    import ai_actuarial.task_runtime as task_runtime_module

    class DeferredThread:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def start(self) -> None:
            pass

    monkeypatch.setattr(task_runtime_module.threading, "Thread", DeferredThread)
    monkeypatch.setattr(task_runtime_module, "append_task_log", lambda *args: None)
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    runtime.active_tasks = {}
    runtime.task_history = []
    runtime.task_lock = threading.RLock()
    runtime._append_history_to_disk = lambda _task: None

    runtime.start_background_task("scheduled", {}, task_id="date-start")
    _assert_aware_utc(runtime.active_tasks["date-start"]["started_at"])
    runtime._finalize_task_success(
        "date-start",
        "scheduled",
        CollectionResult(True, 0, 0, 0, []),
    )
    _assert_aware_utc(runtime.task_history[-1]["completed_at"])

    runtime.start_background_task("scheduled", {}, task_id="date-error")
    runtime._finalize_task_error("date-error", "failed")
    _assert_aware_utc(runtime.task_history[-1]["started_at"])
    _assert_aware_utc(runtime.task_history[-1]["completed_at"])


def test_rejected_task_timestamps_are_utc(monkeypatch) -> None:
    monkeypatch.setattr(ops_write, "append_task_log", lambda *args: None)
    monkeypatch.setattr(ops_write, "_append_history_to_disk", lambda _task: None)
    history: list[dict[str, object]] = []
    bridge = SimpleNamespace(task_history_ref=history, task_lock=None)

    ops_write._record_rejected_task(
        "Rejected by test",
        collection_type="scheduled",
        data={},
        bridge=bridge,
    )

    _assert_aware_utc(str(history[0]["started_at"]))
    _assert_aware_utc(str(history[0]["completed_at"]))


def test_task_history_api_normalizes_legacy_naive_values_without_mutating_history(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    legacy = {
        "id": "legacy-naive",
        "name": "Legacy task",
        "type": "scheduled",
        "status": "completed",
        "started_at": "2026-03-08T01:30:00",
        "completed_at": "2026-03-08T03:30:00",
        "errors": [],
    }
    app.state.task_history_ref = [legacy]
    app.state.task_lock = None

    response = client.get(
        "/api/tasks/history?limit=20",
        headers={"X-Auth-Token": seed["admin_token"]},
    )

    assert response.status_code == 200, response.text
    api_row = response.json()["tasks"][0]
    assert (
        api_row["started_at"]
        == datetime.fromisoformat(legacy["started_at"]).astimezone().isoformat()
    )
    assert (
        api_row["completed_at"]
        == datetime.fromisoformat(legacy["completed_at"]).astimezone().isoformat()
    )
    assert legacy["started_at"] == "2026-03-08T01:30:00"
    assert legacy["completed_at"] == "2026-03-08T03:30:00"


def test_site_backup_timestamps_are_exact_utc_instants(tmp_path: Path, monkeypatch) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    backup_path = backup_dir / "sites_existing.yaml"
    backup_path.write_text("sites: []\n", encoding="utf-8")
    timestamp = 1772955000.0
    import os

    os.utime(backup_path, (timestamp, timestamp))
    monkeypatch.setattr(ops_write, "_ensure_backup_dir", lambda: backup_dir)

    listed = ops_write.list_backups()["backups"][0]["timestamp"]
    expected = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    assert listed == expected

    def create_known_backup(_label: str) -> str:
        created_path = backup_dir / "sites_created.yaml"
        created_path.write_text("sites: []\n", encoding="utf-8")
        os.utime(created_path, (timestamp, timestamp))
        return created_path.name

    monkeypatch.setattr(ops_write, "_backup_config", create_known_backup)
    created = ops_write.create_backup()
    assert created["timestamp"] == expected


def test_task_serializer_preserves_aware_values_and_malformed_strings() -> None:
    task_history = [
        {
            "id": "aware",
            "started_at": "2026-03-08T01:30:00-05:00",
            "completed_at": "invalid",
        }
    ]

    result = list_task_history(task_history, 10)["tasks"][0]

    assert result["started_at"] == "2026-03-08T01:30:00-05:00"
    assert result["completed_at"] == "invalid"


def test_task_history_sorts_mixed_instants_before_limit_and_keeps_invalid_last() -> None:
    task_history = [
        {"id": "older-aware", "started_at": "2026-10-04T08:00:00+08:00"},
        {"id": "newer-legacy", "started_at": "2026-10-04T07:00:00"},
        {"id": "invalid", "started_at": "not-a-date"},
    ]

    result = list_task_history(task_history, 2)["tasks"]

    assert [task["id"] for task in result] == ["newer-legacy", "older-aware"]
