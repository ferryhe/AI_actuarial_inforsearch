from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from ai_actuarial.api.services.ops_write import (
    BridgeState,
    OpsWriteError,
    start_collection,
)
from ai_actuarial.embedding_service import (
    EmbeddingSelectionError,
    compute_embedding_identity,
    resolve_embedding_selection,
)
from ai_actuarial.pipeline_baton import PipelineBaton
from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.storage import Storage
from ai_actuarial.task_runtime import NativeTaskRuntime


class _Tasks:
    def __init__(self) -> None:
        self.statuses: dict[str, str] = {}
        self.tasks: dict[str, dict[str, Any]] = {}
        self.started: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

    def start(
        self,
        task_type: str,
        payload: dict[str, Any],
        *,
        task_name: str,
        extra_fields: dict[str, Any],
    ) -> str:
        task_id = f"started-{len(self.started) + 1}"
        self.started.append((task_type, dict(payload), dict(extra_fields)))
        self.statuses[task_id] = "pending"
        self.tasks[task_id] = {"id": task_id, "status": "pending", "items_downloaded": 0}
        return task_id

    def status(self, task_id: str) -> str | None:
        return self.statuses.get(task_id)

    def result(self, task_id: str) -> dict[str, Any] | None:
        task = self.tasks.get(task_id)
        return deepcopy(task) if task is not None else None


def _baton(tmp_path: Path, tasks: _Tasks, *, kbs: list[str] | None = None) -> PipelineBaton:
    return PipelineBaton(
        state_path=tmp_path / "pipeline-baton.json",
        start_task=tasks.start,
        task_status=tasks.status,
        task_result=tasks.result,
        indexable_kb_ids=lambda: list(kbs or []),
        now=lambda: "2026-09-02T12:00:00+00:00",
    )


def _seed_phase(
    tmp_path: Path,
    tasks: _Tasks,
    logical_phase: str,
    *,
    status: str,
    items_downloaded: int,
) -> PipelineBaton:
    baton = _baton(tmp_path, tasks)
    document = PipelineBaton._empty_document()
    current_step = "chunk_generation" if logical_phase == "embedding_generation" else logical_phase
    task_id = "source-task" if logical_phase == "scheduled" else "current-task"
    document["state"].update(
        current_step=current_step,
        current_task_id=task_id,
        consumed_scheduled_task_id="source-task",
        round_status="running",
        chunk_embedding_phase=(
            "embedding"
            if logical_phase == "embedding_generation"
            else ("chunk" if logical_phase == "chunk_generation" else None)
        ),
        chunk_task_id=(task_id if logical_phase == "chunk_generation" else None),
        embedding_task_id=(task_id if logical_phase == "embedding_generation" else None),
    )
    baton._state_path.parent.mkdir(parents=True, exist_ok=True)
    Path(baton._state_path).write_text(json.dumps(document), encoding="utf-8")
    tasks.statuses[task_id] = status
    tasks.tasks[task_id] = {
        "id": task_id,
        "status": status,
        "items_found": items_downloaded + (1 if status == "error" else 0),
        "items_downloaded": items_downloaded,
        "items_skipped": 3,
        "errors": ["source failure"] if status == "error" else [],
        "result": {"production_shape": True},
        "log_file": "source.log",
    }
    return baton


@pytest.mark.parametrize(
    ("logical_phase", "next_task_type"),
    [
        ("scheduled", "markdown_conversion"),
        ("markdown_conversion", "catalog"),
        ("catalog", "chunk_generation"),
        ("chunk_generation", "embedding_generation"),
        ("embedding_generation", None),
    ],
)
@pytest.mark.parametrize(
    ("terminal_status", "items_downloaded", "expected_round"),
    [
        ("completed", 2, "advance"),
        ("error", 2, "advance"),
        ("completed", 0, "completed"),
        ("error", 0, "error"),
        ("stopped", 2, "stopped"),
    ],
)
def test_all_non_kb_phases_use_one_partial_success_matrix(
    tmp_path: Path,
    logical_phase: str,
    next_task_type: str | None,
    terminal_status: str,
    items_downloaded: int,
    expected_round: str,
) -> None:
    tasks = _Tasks()
    baton = _seed_phase(
        tmp_path,
        tasks,
        logical_phase,
        status=terminal_status,
        items_downloaded=items_downloaded,
    )
    source_task_id = "source-task" if logical_phase == "scheduled" else "current-task"
    source_before = deepcopy(tasks.tasks[source_task_id])

    state = baton.tick()["state"]

    if expected_round == "advance" and next_task_type is not None:
        assert state["round_status"] == "running"
        assert [kind for kind, _payload, _extra in tasks.started] == [next_task_type]
    elif expected_round == "advance":
        assert state["round_status"] == "completed"
        assert tasks.started == []
    else:
        assert state["round_status"] == expected_round
        assert tasks.started == []
    assert tasks.tasks[source_task_id] == source_before


def test_production_markdown_partial_error_advances_once_without_selector_handoff(
    tmp_path: Path,
) -> None:
    tasks = _Tasks()
    baton = _seed_phase(
        tmp_path,
        tasks,
        "markdown_conversion",
        status="error",
        items_downloaded=2,
    )
    canonical_result = {
        "contract_version": 1,
        "files": [
            {
                "file_url": "https://example.test/converted-a.pdf",
                "markdown_hash": "markdown-hash-a",
                "markdown_version": "markdown-hash-a",
                "status": "ready",
            },
            {
                "file_url": "https://example.test/converted-b.pdf",
                "markdown_hash": "markdown-hash-b",
                "markdown_version": "markdown-hash-b",
                "status": "ready",
            },
        ],
    }
    tasks.tasks["current-task"] = {
        "id": "current-task",
        "type": "markdown_conversion",
        "name": "Pipeline: Markdown Conversion",
        "status": "error",
        "progress": 100,
        "started_at": "2026-09-02T11:59:00+00:00",
        "completed_at": "2026-09-02T12:00:00+00:00",
        "current_activity": "Completed with errors",
        "items_processed": 3,
        "items_total": 3,
        "items_downloaded": 2,
        "items_skipped": 0,
        "errors": ["https://example.test/failed.pdf: local file not found"],
        "metadata": {
            "source_type": "markdown_conversion",
            "conversion_tool": "auto",
            "resolved_engine": "docling",
            "provider": "local",
            "stopped": False,
            "result": deepcopy(canonical_result),
        },
        "result": canonical_result,
        "log_file": "logs/task_current-task.log",
    }
    source_before = deepcopy(tasks.tasks["current-task"])

    first = baton.tick()["state"]
    second = baton.tick()["state"]

    assert first["current_step"] == "catalog"
    assert second["current_task_id"] == first["current_task_id"]
    assert tasks.started == [
        (
            "catalog",
            {},
            {
                "pipeline_baton_step": "catalog",
                "pipeline_baton_source_task_id": "source-task",
            },
        )
    ]
    assert tasks.tasks["current-task"] == source_before


def test_catalog_chunk_and_embedding_use_normal_incremental_backlogs(tmp_path: Path) -> None:
    expected = {
        "markdown_conversion": ("catalog", {}),
        "catalog": ("chunk_generation", {}),
        "chunk_generation": ("embedding_generation", {"incremental": True}),
    }
    for current_phase, expected_start in expected.items():
        phase_path = tmp_path / current_phase
        tasks = _Tasks()
        baton = _seed_phase(
            phase_path,
            tasks,
            current_phase,
            status="completed",
            items_downloaded=1,
        )

        baton.tick()

        assert tasks.started[-1][:2] == expected_start
        payload = tasks.started[-1][1]
        assert "file_urls" not in payload
        assert "files" not in payload
        assert "chunk_set_ids" not in payload


def test_missing_task_and_status_exception_end_round_as_error(tmp_path: Path) -> None:
    missing = _Tasks()
    missing_baton = _seed_phase(
        tmp_path / "missing",
        missing,
        "catalog",
        status="completed",
        items_downloaded=1,
    )
    missing.statuses.pop("current-task")
    assert missing_baton.tick()["state"]["round_status"] == "error"

    exploding = _Tasks()
    exploding_baton = _seed_phase(
        tmp_path / "exception",
        exploding,
        "catalog",
        status="completed",
        items_downloaded=1,
    )

    def fail_status(_task_id: str) -> str:
        raise RuntimeError("status storage unavailable")

    exploding_baton._task_status = fail_status
    assert exploding_baton.tick()["state"]["round_status"] == "error"

    result_exploding = _Tasks()
    result_baton = _seed_phase(
        tmp_path / "result-exception",
        result_exploding,
        "catalog",
        status="completed",
        items_downloaded=1,
    )

    def fail_result(_task_id: str) -> dict[str, Any]:
        raise RuntimeError("task storage unavailable")

    result_baton._task_result = fail_result
    assert result_baton.tick()["state"]["round_status"] == "error"


@pytest.mark.parametrize("phase", ["kb_index", "ready_data"])
def test_kb_error_continues_but_stopped_halts_round(tmp_path: Path, phase: str) -> None:
    for terminal in ("error", "stopped"):
        tasks = _Tasks()
        baton = _baton(tmp_path / f"{phase}-{terminal}", tasks, kbs=["kb-a", "kb-b"])
        document = PipelineBaton._empty_document()
        document["state"].update(
            current_step="rag_indexing",
            current_task_id="kb-a-task",
            consumed_scheduled_task_id="source-task",
            current_rag_kb="kb-a",
            round_status="running",
            kb_index_ready_phase=phase,
            kb_index_task_id="kb-a-index",
            ready_data_task_id=("kb-a-task" if phase == "ready_data" else None),
            summary={"attempted": 1, "succeeded": 0, "failed": 0, "failed_kbs": []},
        )
        baton._state_path.parent.mkdir(parents=True, exist_ok=True)
        baton._state_path.write_text(json.dumps(document), encoding="utf-8")
        tasks.statuses["kb-a-task"] = terminal
        tasks.tasks["kb-a-task"] = {
            "id": "kb-a-task",
            "status": terminal,
            "items_downloaded": 0,
        }

        state = baton.tick()["state"]

        if terminal == "error":
            assert state["round_status"] == "running"
            assert state["current_rag_kb"] == "kb-b"
            assert state["summary"]["failed_kbs"] == ["kb-a"]
            assert [kind for kind, _payload, _extra in tasks.started] == ["rag_indexing"]
            tasks.statuses["started-1"] = "completed"
            tasks.tasks["started-1"].update(status="completed")
            completed = baton.tick()["state"]
            assert completed["round_status"] == "completed"
            assert completed["summary"] == {
                "attempted": 2,
                "succeeded": 1,
                "failed": 1,
                "failed_kbs": ["kb-a"],
            }
        else:
            assert state["round_status"] == "stopped"
            assert tasks.started == []


def _seed_ready_chunk_set(
    storage: Storage,
    *,
    file_url: str,
    profile_id: str,
    profile_hash: str,
    markdown_hash: str,
) -> str:
    storage.insert_file(
        file_url,
        f"file-hash-{markdown_hash}",
        file_url,
        "test",
        None,
        file_url.rsplit("/", 1)[-1],
        file_url.rsplit("/", 1)[-1],
        10,
        "application/pdf",
    )
    chunk_set = storage.get_or_create_file_chunk_set(
        file_url=file_url,
        profile_id=profile_id,
        markdown_hash=markdown_hash,
        profile_config_hash=profile_hash,
    )
    storage.replace_global_chunks(
        chunk_set_id=str(chunk_set["chunk_set_id"]),
        chunks=[{"chunk_index": 0, "content": f"content-{markdown_hash}", "token_count": 2}],
    )
    return str(chunk_set["chunk_set_id"])


def test_selector_free_embedding_backlog_uses_real_storage_eligibility_and_is_idempotent(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "embedding-backlog.db"))
    try:
        profile = storage.create_chunk_profile(
            name="issue-319",
            chunk_size=100,
            chunk_overlap=10,
            splitter="semantic",
            tokenizer="cl100k_base",
            version="v1",
        )
        ready_done = _seed_ready_chunk_set(
            storage,
            file_url="https://example.test/done.pdf",
            profile_id=str(profile["profile_id"]),
            profile_hash=str(profile["config_hash"]),
            markdown_hash="done-hash",
        )
        ready_missing = _seed_ready_chunk_set(
            storage,
            file_url="https://example.test/missing.pdf",
            profile_id=str(profile["profile_id"]),
            profile_hash=str(profile["config_hash"]),
            markdown_hash="missing-hash",
        )
        building = _seed_ready_chunk_set(
            storage,
            file_url="https://example.test/building.pdf",
            profile_id=str(profile["profile_id"]),
            profile_hash=str(profile["config_hash"]),
            markdown_hash="building-hash",
        )
        storage._conn.execute(
            "UPDATE file_chunk_sets SET status = 'building' WHERE chunk_set_id = ?", (building,)
        )
        storage._conn.commit()
        identity = compute_embedding_identity(
            RAGConfig(embedding_provider="local", embedding_model="issue-319-model"),
            dimension=3,
        )
        done_chunk = storage.list_chunks_for_embedding([ready_done])[0]
        storage.batch_upsert_chunk_embeddings(
            [{"chunk_id": done_chunk["chunk_id"], "vector": [1.0, 0.0, 0.0]}],
            identity=identity.as_dict(),
        )

        selection = resolve_embedding_selection(
            storage,
            incremental=True,
            identity=identity,
        )

        assert selection["requested_chunk_set_ids"] == []
        assert selection["requested_file_urls"] == []
        assert selection["chunk_set_ids"] == [ready_missing]

        missing_chunk = storage.list_chunks_for_embedding([ready_missing])[0]
        storage.batch_upsert_chunk_embeddings(
            [{"chunk_id": missing_chunk["chunk_id"], "vector": [0.0, 1.0, 0.0]}],
            identity=identity.as_dict(),
        )
        repeated = resolve_embedding_selection(
            storage,
            incremental=True,
            identity=identity,
        )
        assert repeated["chunk_set_ids"] == []

        storage._conn.execute(
            "UPDATE chunk_embeddings SET vector_json = '[1]' WHERE chunk_id = ?",
            (done_chunk["chunk_id"],),
        )
        storage._conn.commit()
        repair = resolve_embedding_selection(
            storage,
            incremental=True,
            identity=identity,
        )
        assert repair["chunk_set_ids"] == [ready_done]
    finally:
        storage.close()


def test_selector_free_embedding_rejects_profile_filter_at_selection_boundary(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "embedding-profile-filter.db"))
    try:
        identity = compute_embedding_identity(
            RAGConfig(embedding_provider="local", embedding_model="issue-319-model"),
            dimension=3,
        )

        with pytest.raises(
            EmbeddingSelectionError,
            match="profile_id cannot be combined with incremental embedding selection",
        ):
            resolve_embedding_selection(
                storage,
                profile_id="profile-1",
                incremental=True,
                identity=identity,
            )
    finally:
        storage.close()


class _Bridge:
    def __init__(self) -> None:
        self.active_tasks_ref: dict[str, dict[str, Any]] = {}
        self.task_history_ref: list[dict[str, Any]] = []
        self.task_lock = None
        self.started: list[tuple[str, dict[str, Any]]] = []
        self.start_background_task = self.start

    def start(self, task_type: str, payload: dict[str, Any], **_kwargs: Any) -> str:
        self.started.append((task_type, dict(payload)))
        return "embedding-job"


def test_manual_api_rejects_profile_filter_with_selector_free_embedding() -> None:
    bridge = _Bridge()

    with pytest.raises(
        OpsWriteError,
        match="profile_id cannot be combined with incremental embedding selection",
    ):
        start_collection(
            {
                "type": "embedding_generation",
                "incremental": True,
                "profile_id": "profile-1",
            },
            bridge=BridgeState(bridge),
        )

    assert bridge.started == []


def test_manual_api_and_baton_use_the_same_selector_free_embedding_mode(tmp_path: Path) -> None:
    bridge = _Bridge()
    started = start_collection(
        {"type": "embedding_generation", "incremental": True},
        bridge=BridgeState(bridge),
    )
    assert started["job_id"] == "embedding-job"
    assert bridge.started == [
        ("embedding_generation", {"type": "embedding_generation", "incremental": True})
    ]

    tasks = _Tasks()
    baton = _seed_phase(
        tmp_path,
        tasks,
        "chunk_generation",
        status="completed",
        items_downloaded=1,
    )
    baton.tick()
    assert tasks.started[-1][:2] == ("embedding_generation", {"incremental": True})

    storage = Storage(str(tmp_path / "selection-parity.db"))
    try:
        profile = storage.create_chunk_profile(
            name="issue-319-parity",
            chunk_size=100,
            chunk_overlap=10,
            splitter="semantic",
            tokenizer="cl100k_base",
            version="v1",
        )
        expected_chunk_set_id = _seed_ready_chunk_set(
            storage,
            file_url="https://example.test/parity.pdf",
            profile_id=str(profile["profile_id"]),
            profile_hash=str(profile["config_hash"]),
            markdown_hash="parity-hash",
        )
        identity = compute_embedding_identity(
            RAGConfig(embedding_provider="local", embedding_model="issue-319-model"),
            dimension=3,
        )
        manual_payload = bridge.started[0][1]
        baton_payload = tasks.started[-1][1]
        manual_selection = resolve_embedding_selection(
            storage,
            incremental=bool(manual_payload["incremental"]),
            identity=identity,
        )
        baton_selection = resolve_embedding_selection(
            storage,
            incremental=bool(baton_payload["incremental"]),
            identity=identity,
        )
        assert (
            manual_selection["chunk_set_ids"]
            == baton_selection["chunk_set_ids"]
            == [expected_chunk_set_id]
        )
    finally:
        storage.close()


def test_tasks_backlog_and_scheduled_composition_use_selector_free_embedding_but_file_detail_stays_scoped(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[1]
    tasks_source = (root / "client/src/pages/Tasks.tsx").read_text(encoding="utf-8")
    file_detail_source = (root / "client/src/pages/FileDetail.tsx").read_text(encoding="utf-8")
    assert 'type: "embedding_generation"' in tasks_source
    assert "chunk_sets?: Array<{ chunk_set_id?: string }>;" in tasks_source
    assert '.map((item) => String(item.chunk_set_id || "").trim())' in tasks_source
    empty_guard = 'if (chunk_set_ids.length === 0) throw new Error("Chunk task returned no stable chunk_set_ids");'
    embedding_request = "const embedding = await apiPost<{ job_id?: string; error?: string }>"
    assert tasks_source.index(empty_guard) < tasks_source.index(embedding_request)
    embedding_payload = tasks_source[
        tasks_source.index(embedding_request) : tasks_source.index(
            "});", tasks_source.index(embedding_request)
        )
    ]
    assert "incremental: true" in embedding_payload
    assert "chunk_set_ids" not in embedding_payload
    assert "chunk_set_ids" in file_detail_source

    class Runtime:
        started: list[tuple[str, dict[str, Any]]] = []

        def _pipeline_task_status(self, _task_id: str) -> str:
            return "completed"

        def _pipeline_task_result(self, _task_id: str) -> dict[str, Any]:
            return {
                "items_downloaded": 1,
                "result": {
                    "contract_version": 1,
                    "chunk_sets": [{"chunk_set_id": "cs-scheduled"}],
                },
            }

        def start_background_task(
            self, task_type: str, payload: dict[str, Any], **_kwargs: Any
        ) -> str:
            self.started.append((task_type, dict(payload)))
            return "embedding-task"

    runtime = Runtime()
    assert (
        NativeTaskRuntime._complete_scheduled_chunk_embedding(
            runtime, "chunk-task", "Nightly Chunk"
        )
        == "embedding-task"
    )
    assert runtime.started == [("embedding_generation", {"incremental": True})]
