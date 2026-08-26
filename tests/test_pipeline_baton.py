from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_actuarial.pipeline_baton import PipelineBaton


MARKDOWN_FILES = [
    {
        "file_url": "https://example.test/a.pdf",
        "markdown_hash": "markdown-hash-a",
        "markdown_version": "markdown-hash-a",
        "status": "ready",
    }
]


class FakeTasks:
    def __init__(self) -> None:
        self.statuses: dict[str, str] = {}
        self.results: dict[str, dict[str, Any]] = {}
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

    def result(self, task_id: str) -> dict[str, Any] | None:
        return self.results.get(task_id)


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
            "2026-08-25T17:00:00+00:00",
            "2026-08-25T17:30:00+00:00",
        ]
    )
    return PipelineBaton(
        state_path=tmp_path / "pipeline-baton.json",
        start_task=tasks.start,
        task_status=tasks.status,
        task_result=tasks.result,
        category_kb_ids=lambda: list(kbs),
        now=lambda: next(ticks),
    )


def test_fixed_baton_runs_embedding_for_exact_chunk_result_before_rag(tmp_path: Path) -> None:
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
    tasks.results["task-1"] = {"result": {"contract_version": 1, "files": MARKDOWN_FILES}}
    baton.tick()
    assert tasks.started[-1][:2] == (
        "catalog",
        {"scan_count": 23, "file_urls": ["https://example.test/a.pdf"]},
    )
    tasks.statuses["task-2"] = "completed"
    baton.tick()
    assert tasks.started[-1][:2] == (
        "chunk_generation",
        {"chunk_size": 700, "files": MARKDOWN_FILES},
    )
    tasks.results["task-3"] = {
        "result": {"chunk_sets": [{"chunk_set_id": "cs-a"}, {"chunk_set_id": "cs-z"}]}
    }
    tasks.statuses["task-3"] = "completed"
    baton.tick()
    assert tasks.started[-1][:2] == (
        "embedding_generation",
        {"chunk_set_ids": ["cs-a", "cs-z"]},
    )
    tasks.statuses["task-4"] = "completed"
    baton.tick()
    assert tasks.started[-1][:2] == (
        "rag_indexing",
        {"batch_size": 8, "kb_id": "kb-a", "force_reindex": False, "incremental": True},
    )
    tasks.statuses["task-5"] = "completed"
    baton.tick()
    assert tasks.started[-1][:2] == (
        "rag_indexing",
        {"batch_size": 8, "kb_id": "kb-z", "force_reindex": False, "incremental": True},
    )
    tasks.statuses["task-6"] = "completed"
    completed = baton.tick()

    assert completed["state"]["round_status"] == "completed"
    assert [task_type for task_type, _, _ in tasks.started] == [
        "markdown_conversion",
        "catalog",
        "chunk_generation",
        "embedding_generation",
        "rag_indexing",
        "rag_indexing",
    ]
    assert all("markdown_content" not in json.dumps(payload) for _, payload, _ in tasks.started)
    assert baton.tick()["state"]["round_status"] == "completed"
    assert len(tasks.started) == 6


def test_untouched_catalog_only_adds_exact_markdown_selector(tmp_path: Path) -> None:
    tasks = FakeTasks()
    tasks.statuses["scheduled-1"] = "completed"
    baton = _service(tmp_path, tasks, [])
    baton.start("scheduled-1")
    baton.tick()
    tasks.statuses["task-1"] = "completed"
    tasks.results["task-1"] = {"result": {"contract_version": 1, "files": MARKDOWN_FILES}}

    baton.tick()

    assert tasks.started[-1][:2] == (
        "catalog",
        {"file_urls": ["https://example.test/a.pdf"]},
    )


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
    tasks.results["task-1"] = {"result": {"contract_version": 1, "files": MARKDOWN_FILES}}
    baton.tick()
    tasks.statuses["task-2"] = "completed"
    baton.tick()
    tasks.statuses["task-3"] = "completed"
    tasks.results["task-3"] = {"result": {"chunk_sets": [{"chunk_set_id": "cs-1"}]}}

    state = baton.tick()["state"]
    assert state["chunk_embedding_phase"] == "embedding"
    tasks.statuses["task-4"] = "completed"
    state = baton.tick()["state"]

    assert state["round_status"] == "completed"
    assert [kind for kind, _, _ in tasks.started] == [
        "markdown_conversion",
        "catalog",
        "chunk_generation",
        "embedding_generation",
    ]


def test_chunk_failure_never_launches_embedding(tmp_path: Path) -> None:
    tasks = FakeTasks()
    tasks.statuses["scheduled-1"] = "completed"
    baton = _service(tmp_path, tasks, [])
    baton.start("scheduled-1")
    baton.tick()
    tasks.statuses["task-1"] = "completed"
    tasks.results["task-1"] = {"result": {"contract_version": 1, "files": MARKDOWN_FILES}}
    baton.tick()
    tasks.statuses["task-2"] = "completed"
    baton.tick()
    tasks.statuses["task-3"] = "error"

    state = baton.tick()["state"]

    assert state["round_status"] == "error"
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
        "chunk_embedding_phase",
        "chunk_task_id",
        "embedding_task_id",
        "markdown_files",
    }
    assert "markdown_content" not in json.dumps(document)


def test_baton_fails_closed_when_markdown_task_has_no_canonical_files(tmp_path: Path) -> None:
    tasks = FakeTasks()
    tasks.statuses["scheduled-1"] = "completed"
    baton = _service(tmp_path, tasks, [])
    baton.start("scheduled-1")
    baton.tick()
    tasks.statuses["task-1"] = "completed"
    tasks.results["task-1"] = {"result": {"contract_version": 1, "files": []}}

    state = baton.tick()["state"]

    assert state["round_status"] == "error"
    assert [kind for kind, _, _ in tasks.started] == ["markdown_conversion"]


def test_legacy_chunk_override_is_sanitized_when_persisted_baton_executes(tmp_path: Path) -> None:
    tasks = FakeTasks()
    tasks.statuses["scheduled-1"] = "completed"
    state_path = tmp_path / "pipeline-baton.json"
    state_path.write_text(
        json.dumps(
            {
                "config": {
                    "overrides": {
                        "chunk_generation": {
                            "chunk_size": 456,
                            "kb_id": "legacy-kb",
                            "knowledge_base_id": "legacy-kb-2",
                            "bind_to_kb": True,
                            "binding_mode": "pin",
                            "full_reindex": True,
                            "full_rebuild": True,
                            "force_reindex": True,
                            "overwrite_same_profile": True,
                        }
                    }
                },
                "state": PipelineBaton._empty_document()["state"],
            }
        ),
        encoding="utf-8",
    )
    baton = _service(tmp_path, tasks, [])
    baton.start("scheduled-1")
    baton.tick()
    tasks.statuses["task-1"] = "completed"
    tasks.results["task-1"] = {"result": {"contract_version": 1, "files": MARKDOWN_FILES}}
    baton.tick()
    tasks.statuses["task-2"] = "completed"

    baton.tick()

    assert tasks.started[-1][:2] == (
        "chunk_generation",
        {"chunk_size": 456, "files": MARKDOWN_FILES},
    )
    assert baton.status()["config"]["overrides"]["chunk_generation"] == {
        "chunk_size": 456
    }
