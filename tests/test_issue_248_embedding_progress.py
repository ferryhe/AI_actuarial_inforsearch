from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ai_actuarial.api.services.ops_read import list_active_tasks
from ai_actuarial.collectors.base import CollectionResult
from ai_actuarial.embedding_service import (
    compute_embedding_identity,
    ensure_chunk_embeddings,
)
from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.storage import Storage
from ai_actuarial.task_runtime import NativeTaskRuntime


def _seed_chunks(storage: Storage) -> tuple[str, list[dict[str, Any]]]:
    file_url = "https://example.test/issue-248.pdf"
    storage.insert_file(
        file_url,
        "file-hash",
        "Issue 248",
        "test",
        None,
        "issue-248.pdf",
        "issue-248.pdf",
        10,
        "application/pdf",
    )
    profile = storage.create_chunk_profile(
        name="issue-248",
        chunk_size=100,
        chunk_overlap=10,
        splitter="semantic",
        tokenizer="cl100k_base",
        version="v1",
    )
    chunk_set = storage.get_or_create_file_chunk_set(
        file_url=file_url,
        profile_id=str(profile["profile_id"]),
        markdown_hash="markdown-v1",
        profile_config_hash=str(profile["config_hash"]),
    )
    chunk_set_id = str(chunk_set["chunk_set_id"])
    storage.replace_global_chunks(
        chunk_set_id=chunk_set_id,
        chunks=[
            {"chunk_index": 0, "content": "alpha", "token_count": 1},
            {"chunk_index": 1, "content": "beta", "token_count": 1},
            {"chunk_index": 2, "content": "gamma", "token_count": 1},
        ],
    )
    return chunk_set_id, storage.list_chunks_for_embedding([chunk_set_id])


def _identity():
    return compute_embedding_identity(
        RAGConfig(embedding_provider="local", embedding_model="test-model"),
        dimension=3,
    )


class _SequenceGenerator:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[list[str]] = []

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def test_service_reports_initial_reuse_then_each_provider_batch_once(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _, chunks = _seed_chunks(storage)
        identity = _identity()
        storage.batch_upsert_chunk_embeddings(
            [{"chunk_id": chunks[0]["chunk_id"], "vector": [1.0, 0.0, 0.0]}],
            identity=identity.as_dict(),
        )
        storage.batch_upsert_chunk_embeddings(
            [{"chunk_id": chunks[1]["chunk_id"], "vector": [0.0, 1.0, 0.0]}],
            identity=identity.as_dict(),
        )
        storage._conn.execute(
            "UPDATE chunk_embeddings SET vector_json = ? WHERE chunk_id = ? AND embedding_identity_key = ?",
            (
                json.dumps([[0.0, 1.0, 0.0]]),
                chunks[1]["chunk_id"],
                identity.embedding_identity_key,
            ),
        )
        storage._conn.commit()
        generator = _SequenceGenerator(
            [
                [[0.25, 0.5, 0.75]],
                [[0.75, 0.5, 0.25]],
            ]
        )
        progress_events: list[tuple[int, int, str]] = []

        result = ensure_chunk_embeddings(
            storage=storage,
            chunks=chunks,
            identity=identity,
            generator=generator,
            batch_size=1,
            progress_callback=lambda current, total, activity: progress_events.append(
                (current, total, activity)
            ),
        )

        assert [(current, total) for current, total, _ in progress_events] == [
            (1, 3),
            (2, 3),
            (3, 3),
        ]
        assert generator.calls == [["beta"], ["gamma"]]
        assert result.reused == 1
        assert result.invalid_regenerated == 1
        assert result.generated == 1
        assert result.failed == 0
        assert all(
            text not in activity
            for _, _, activity in progress_events
            for text in ("alpha", "beta", "gamma")
        )
    finally:
        storage.close()


def test_service_failed_batches_advance_with_safe_summary_messages(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _, chunks = _seed_chunks(storage)
        generator = _SequenceGenerator(
            [
                RuntimeError("credential=secret-key content=alpha vector=[9, 9, 9]"),
                [],
                [[float("nan"), 0.0, 0.0]],
            ]
        )
        progress_events: list[tuple[int, int, str]] = []

        result = ensure_chunk_embeddings(
            storage=storage,
            chunks=chunks,
            identity=_identity(),
            generator=generator,
            batch_size=1,
            progress_callback=lambda current, total, activity: progress_events.append(
                (current, total, activity)
            ),
        )

        assert [(current, total) for current, total, _ in progress_events] == [
            (0, 3),
            (1, 3),
            (2, 3),
            (3, 3),
        ]
        assert result.failed == 3
        assert {error["code"] for error in result.errors} == {
            "provider_error",
            "provider_count_mismatch",
            "invalid_embedding_vector",
        }
        assert all(
            unsafe not in activity
            for _, _, activity in progress_events
            for unsafe in ("secret-key", "credential", "alpha", "[9", "nan")
        )
    finally:
        storage.close()


def test_service_stop_after_completed_batch_preserves_attempted_progress(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _, chunks = _seed_chunks(storage)
        identity = _identity()
        storage.batch_upsert_chunk_embeddings(
            [{"chunk_id": chunks[0]["chunk_id"], "vector": [1.0, 0.0, 0.0]}],
            identity=identity.as_dict(),
        )
        stopped = False
        progress_events: list[tuple[int, int, str]] = []

        class StopAfterFirstBatch:
            calls: list[list[str]] = []

            def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
                nonlocal stopped
                self.calls.append(list(texts))
                stopped = True
                return [[1.0, 0.0, 0.0]]

        generator = StopAfterFirstBatch()
        result = ensure_chunk_embeddings(
            storage=storage,
            chunks=chunks,
            identity=identity,
            generator=generator,
            batch_size=1,
            stop_check=lambda: stopped,
            progress_callback=lambda current, total, activity: progress_events.append(
                (current, total, activity)
            ),
        )

        assert generator.calls == [["beta"]]
        assert result.stopped is True
        assert result.generated == 1
        assert result.reused == 1
        assert result.failed == 0
        assert [(current, total) for current, total, _ in progress_events] == [
            (1, 3),
            (2, 3),
        ]
    finally:
        storage.close()


def _patch_embedding_runtime_inputs(
    monkeypatch: pytest.MonkeyPatch,
    ensured: SimpleNamespace,
    progress_steps: list[int],
    snapshots: list[dict[str, Any]],
    runtime: NativeTaskRuntime,
) -> None:
    identity = SimpleNamespace(
        config=SimpleNamespace(embedding_batch_size=1),
        as_dict=lambda: {"provider": "test", "model": "test", "dimension": 3},
    )
    selection = {
        "chunks": [
            {"chunk_id": "chunk-1"},
            {"chunk_id": "chunk-2"},
            {"chunk_id": "chunk-3"},
        ],
        "chunk_sets": [{"file_url": "https://example.test/a"}],
        "requested_file_urls": [],
        "requested_chunk_set_ids": ["cs-1"],
        "chunk_set_ids": ["cs-1"],
    }

    def fake_ensure(**kwargs: Any) -> SimpleNamespace:
        callback = kwargs["progress_callback"]
        for current in progress_steps:
            callback(current, 3, f"Embedding progress: {current}/3 processed")
            snapshots.append(list_active_tasks(runtime.active_tasks, runtime.task_lock))
        return ensured

    monkeypatch.setattr(
        "ai_actuarial.task_runtime.resolve_embedding_selection",
        lambda *_args, **_kwargs: selection,
    )
    monkeypatch.setattr(
        "ai_actuarial.task_runtime.resolve_server_embedding_identity",
        lambda *_args, **_kwargs: identity,
    )
    monkeypatch.setattr(
        "ai_actuarial.task_runtime.ensure_chunk_embeddings",
        fake_ensure,
    )
    monkeypatch.setattr(
        "ai_actuarial.task_runtime.embedding_coverage_for_selection",
        lambda **_kwargs: {"per_file": []},
    )
    monkeypatch.setattr("ai_actuarial.task_runtime.append_task_log", lambda *_args: None)


def _runtime_with_active_task() -> NativeTaskRuntime:
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    runtime.task_lock = threading.RLock()
    runtime.active_tasks = {
        "embedding-task": {
            "id": "embedding-task",
            "name": "Embedding",
            "type": "embedding_generation",
            "status": "running",
            "progress": 0,
            "items_processed": 0,
            "items_total": 0,
            "started_at": "2026-08-27T00:00:00+00:00",
        }
    }
    runtime.task_history = []
    runtime._append_history_to_disk = lambda _task: None
    runtime._stop_requested = lambda _task_id: False
    return runtime


def test_runtime_api_and_task_card_observe_multibatch_intermediate_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime_with_active_task()
    snapshots: list[dict[str, Any]] = []
    ensured = SimpleNamespace(
        ready_count=3,
        stopped=False,
        failed=0,
        expected_count=3,
        generated=3,
        reused=0,
        invalid_regenerated=0,
        persisted_record_count=3,
        errors=[],
        started_at="2026-08-27T00:00:00+00:00",
        completed_at="2026-08-27T00:00:01+00:00",
    )
    _patch_embedding_runtime_inputs(
        monkeypatch,
        ensured,
        [0, 1, 2, 3],
        snapshots,
        runtime,
    )

    result = runtime._run_embedding_generation(
        "embedding-task",
        SimpleNamespace(),
        {"chunk_set_ids": ["cs-1"]},
    )

    observed = [snapshot["tasks"][0] for snapshot in snapshots]
    assert any(
        0 < task["progress"] < 100 and 0 < task["items_processed"] < task["items_total"]
        for task in observed
    )
    card = (Path(__file__).resolve().parents[1] / "client/src/pages/tasks/TaskCard.tsx").read_text(
        encoding="utf-8"
    )
    assert "task.items_processed" in card
    assert "task.items_total" in card
    assert "task.progress" in card

    runtime._finalize_task_success("embedding-task", "embedding_generation", result)
    terminal = runtime.task_history[0]
    assert terminal["status"] == "completed"
    assert terminal["progress"] == 100
    assert terminal["items_processed"] == terminal["items_total"] == 3


def test_stopped_embedding_terminal_state_keeps_actual_attempted_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime_with_active_task()
    snapshots: list[dict[str, Any]] = []
    ensured = SimpleNamespace(
        ready_count=2,
        stopped=True,
        failed=0,
        expected_count=3,
        generated=1,
        reused=1,
        invalid_regenerated=0,
        persisted_record_count=1,
        errors=[],
        started_at="2026-08-27T00:00:00+00:00",
        completed_at="2026-08-27T00:00:01+00:00",
    )
    _patch_embedding_runtime_inputs(
        monkeypatch,
        ensured,
        [1, 2],
        snapshots,
        runtime,
    )

    result = runtime._run_embedding_generation(
        "embedding-task",
        SimpleNamespace(),
        {"chunk_set_ids": ["cs-1"]},
    )
    runtime._finalize_task_success("embedding-task", "embedding_generation", result)

    terminal = runtime.task_history[0]
    assert terminal["status"] == "stopped"
    assert terminal["progress"] == 66
    assert terminal["items_processed"] == 2
    assert terminal["items_total"] == 3
    assert terminal["result"]["generated"] == 1
    assert terminal["result"]["failed"] == 0


def test_non_embedding_stopped_finalizer_contract_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime_with_active_task()
    runtime.active_tasks["embedding-task"]["type"] = "chunk_generation"
    monkeypatch.setattr("ai_actuarial.task_runtime.append_task_log", lambda *_args: None)
    result = CollectionResult(
        success=False,
        items_found=3,
        items_downloaded=1,
        items_skipped=0,
        errors=[],
        metadata={"stopped": True},
    )

    runtime._finalize_task_success("embedding-task", "chunk_generation", result)

    terminal = runtime.task_history[0]
    assert terminal["status"] == "stopped"
    assert terminal["progress"] == 100
    assert terminal["items_processed"] == terminal["items_total"] == 3
