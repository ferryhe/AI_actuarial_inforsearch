from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_actuarial.pipeline_baton import PipelineBaton


class FakeTasks:
    def __init__(self) -> None:
        self.statuses: dict[str, str] = {}
        self.started: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

    def start(
        self,
        task_type: str,
        payload: dict[str, Any],
        *,
        task_name: str,
        extra_fields: dict[str, Any],
    ) -> str:
        task_id = f"task-{len(self.started) + 1}"
        self.started.append((task_type, dict(payload), dict(extra_fields)))
        self.statuses[task_id] = "pending"
        return task_id

    def status(self, task_id: str) -> str | None:
        return self.statuses.get(task_id)


def _service(tmp_path: Path, tasks: FakeTasks, kbs: list[str]) -> PipelineBaton:
    ticks = iter(
        [
            "2026-08-25T12:00:00+00:00",
            "2026-08-25T12:30:00+00:00",
            "2026-08-25T13:00:00+00:00",
            "2026-08-25T13:30:00+00:00",
            "2026-08-25T14:00:00+00:00",
            "2026-08-25T14:30:00+00:00",
            "2026-08-25T15:00:00+00:00",
            "2026-08-25T15:30:00+00:00",
            "2026-08-25T16:00:00+00:00",
            "2026-08-25T16:30:00+00:00",
        ]
    )
    return PipelineBaton(
        state_path=tmp_path / "pipeline-baton.json",
        start_task=tasks.start,
        task_status=tasks.status,
        category_kb_ids=lambda: list(kbs),
        now=lambda: next(ticks),
    )


def test_fixed_baton_waits_and_starts_each_independent_task_without_output_handoff(tmp_path: Path) -> None:
    tasks = FakeTasks()
    tasks.statuses["scheduled-1"] = "pending"
    baton = _service(tmp_path, tasks, ["kb-z", "kb-a"])
    baton.configure(
        {
            "markdown_conversion": {"scan_count": 17},
            "catalog": {"scan_count": 23},
            "chunk_generation": {"chunk_size": 700},
            "rag_indexing": {"batch_size": 8},
        }
    )

    started = baton.start("scheduled-1")
    assert started["state"]["current_step"] == "scheduled"
    assert baton.tick()["state"]["current_task_id"] == "scheduled-1"
    assert tasks.started == []

    tasks.statuses["scheduled-1"] = "completed"
    assert baton.tick()["state"]["current_step"] == "markdown_conversion"
    assert tasks.started[-1][:2] == ("markdown_conversion", {"scan_count": 17})

    # pending/running ticks do not duplicate the current stage.
    assert baton.tick()["state"]["current_task_id"] == "task-1"
    tasks.statuses["task-1"] = "running"
    assert baton.tick()["state"]["current_task_id"] == "task-1"
    assert len(tasks.started) == 1

    tasks.statuses["task-1"] = "completed"
    baton.tick()
    assert tasks.started[-1][:2] == ("catalog", {"scan_count": 23})
    tasks.statuses["task-2"] = "completed"
    baton.tick()
    assert tasks.started[-1][:2] == ("chunk_generation", {"chunk_size": 700})
    tasks.statuses["task-3"] = "completed"
    baton.tick()
    assert tasks.started[-1][:2] == (
        "rag_indexing",
        {"batch_size": 8, "kb_id": "kb-a", "force_reindex": False, "incremental": True},
    )
    tasks.statuses["task-4"] = "completed"
    baton.tick()
    assert tasks.started[-1][:2] == (
        "rag_indexing",
        {"batch_size": 8, "kb_id": "kb-z", "force_reindex": False, "incremental": True},
    )
    tasks.statuses["task-5"] = "completed"
    completed = baton.tick()

    assert completed["state"]["round_status"] == "completed"
    assert [task_type for task_type, _, _ in tasks.started] == [
        "markdown_conversion",
        "catalog",
        "chunk_generation",
        "rag_indexing",
        "rag_indexing",
    ]
    assert all("file_urls" not in payload for _, payload, _ in tasks.started)
    assert baton.tick()["state"]["round_status"] == "completed"
    assert len(tasks.started) == 5


def test_untouched_catalog_leaves_defaults_to_the_catalog_module(tmp_path: Path) -> None:
    tasks = FakeTasks()
    tasks.statuses["scheduled-1"] = "completed"
    baton = _service(tmp_path, tasks, [])
    baton.start("scheduled-1")
    baton.tick()
    tasks.statuses["task-1"] = "completed"

    baton.tick()

    assert tasks.started[-1][:2] == ("catalog", {})


@pytest.mark.parametrize("field", ["kb_id", "force_reindex", "incremental"])
def test_rag_baton_configuration_rejects_fixed_fields(tmp_path: Path, field: str) -> None:
    baton = _service(tmp_path, FakeTasks(), [])

    with pytest.raises(ValueError, match=field):
        baton.configure({"rag_indexing": {field: False}})


@pytest.mark.parametrize("field", ["kb_id", "binding_mode", "full_reindex"])
def test_chunk_baton_configuration_rejects_kb_binding_fields(tmp_path: Path, field: str) -> None:
    baton = _service(tmp_path, FakeTasks(), [])

    with pytest.raises(ValueError, match=field):
        baton.configure({"chunk_generation": {field: False}})


def test_unknown_current_step_persists_error_terminal_state(tmp_path: Path) -> None:
    tasks = FakeTasks()
    tasks.statuses["scheduled-1"] = "running"
    state_path = tmp_path / "pipeline-baton.json"
    baton = _service(tmp_path, tasks, [])
    baton.start("scheduled-1")
    document = json.loads(state_path.read_text(encoding="utf-8"))
    document["state"]["current_step"] = "corrupt-step"
    state_path.write_text(json.dumps(document), encoding="utf-8")

    state = baton.tick()["state"]

    assert state["round_status"] == "error"
    assert _service(tmp_path, tasks, []).status()["state"]["round_status"] == "error"
    assert tasks.started == []


def test_baton_terminal_task_status_stops_round_without_starting_next(tmp_path: Path) -> None:
    for terminal in ("error", "stopped"):
        tasks = FakeTasks()
        source_id = f"scheduled-{terminal}"
        tasks.statuses[source_id] = terminal
        baton = _service(tmp_path / terminal, tasks, ["kb-a"])
        baton.start(source_id)

        state = baton.tick()["state"]

        assert state["round_status"] == terminal
        assert tasks.started == []


def test_zero_category_kbs_completes_after_chunk(tmp_path: Path) -> None:
    tasks = FakeTasks()
    tasks.statuses["scheduled-1"] = "completed"
    baton = _service(tmp_path, tasks, [])
    baton.start("scheduled-1")
    baton.tick()
    tasks.statuses["task-1"] = "completed"
    baton.tick()
    tasks.statuses["task-2"] = "completed"
    baton.tick()
    tasks.statuses["task-3"] = "completed"

    state = baton.tick()["state"]

    assert state["round_status"] == "completed"
    assert [kind for kind, _, _ in tasks.started] == [
        "markdown_conversion",
        "catalog",
        "chunk_generation",
    ]


def test_same_scheduled_task_is_consumed_once_and_active_round_is_not_replaced(tmp_path: Path) -> None:
    tasks = FakeTasks()
    tasks.statuses.update({"scheduled-1": "running", "scheduled-2": "running"})
    baton = _service(tmp_path, tasks, [])

    first = baton.start("scheduled-1")
    duplicate = baton.start("scheduled-1")
    competing = baton.start("scheduled-2")

    assert duplicate == first
    assert competing == first
    assert competing["state"]["consumed_scheduled_task_id"] == "scheduled-1"


def test_persisted_document_contains_only_config_and_minimal_baton_state(tmp_path: Path) -> None:
    tasks = FakeTasks()
    tasks.statuses["scheduled-1"] = "running"
    state_path = tmp_path / "pipeline-baton.json"
    baton = _service(tmp_path, tasks, [])
    baton.configure({"catalog": {"scan_count": 9}})
    baton.start("scheduled-1")

    import json

    document = json.loads(state_path.read_text(encoding="utf-8"))
    assert set(document) == {"config", "state"}
    assert document["config"] == {"overrides": {"catalog": {"scan_count": 9}}}
    assert set(document["state"]) == {
        "current_step",
        "current_task_id",
        "current_rag_kb",
        "round_status",
        "last_check",
        "consumed_scheduled_task_id",
    }
