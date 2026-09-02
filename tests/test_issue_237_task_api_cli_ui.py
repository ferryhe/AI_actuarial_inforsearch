from __future__ import annotations

import json
import threading
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_actuarial.api.services.ops_write import BridgeState, OpsWriteError, start_collection
from ai_actuarial.cli import build_parser, cmd_task_run
from ai_actuarial.collectors.base import CollectionResult
from ai_actuarial.task_runtime import NativeTaskRuntime


class _State:
    def __init__(self) -> None:
        self.active_tasks_ref = {}
        self.task_history_ref = []
        self.task_lock = None
        self.started: list[tuple[str, dict[str, object]]] = []
        self.start_background_task = self._start

    def _start(self, task_type: str, payload: dict[str, object], **_kwargs: object) -> str:
        self.started.append((task_type, dict(payload)))
        return "real-job-id"


@pytest.mark.parametrize(
    "field",
    ["kb_id", "bind_to_kb", "binding_mode", "full_reindex"],
)
def test_chunk_launch_rejects_removed_options_machine_readably(field: str) -> None:
    state = _State()
    with pytest.raises(OpsWriteError) as exc_info:
        start_collection(
            {"type": "chunk_generation", "file_urls": ["https://example.test/a"], field: False},
            bridge=BridgeState(state),
        )

    exc = exc_info.value
    assert exc.code == "unsupported_option"
    assert exc.details["unsupported_options"] == [field]
    assert "KB Binding" in exc.details["guidance"]
    assert state.started == []


def test_chunk_launch_accepts_legacy_overwrite_only_as_noop_signal() -> None:
    state = _State()
    result = start_collection(
        {
            "type": "chunk_generation",
            "file_urls": ["https://example.test/a"],
            "overwrite_same_profile": True,
        },
        bridge=BridgeState(state),
    )

    assert result["job_id"] == "real-job-id"
    assert state.started[0][1]["overwrite_same_profile"] is True


def test_chunk_launch_accepts_canonical_markdown_files_selector() -> None:
    state = _State()
    files = [
        {
            "file_url": "https://example.test/a",
            "markdown_hash": "md-hash",
            "markdown_version": "md-hash",
            "status": "ready",
        }
    ]

    result = start_collection(
        {"type": "chunk_generation", "files": files},
        bridge=BridgeState(state),
    )

    assert result["job_id"] == "real-job-id"
    assert state.started == [("chunk_generation", {"type": "chunk_generation", "files": files})]


@pytest.mark.parametrize(
    "field",
    ["api_key", "endpoint", "api_base_url", "text", "texts", "provider", "model", "dimension"],
)
def test_embedding_launch_rejects_client_injected_identity_or_text(field: str) -> None:
    state = _State()
    with pytest.raises(OpsWriteError) as exc_info:
        start_collection(
            {"type": "embedding_generation", "chunk_set_ids": ["cs-1"], field: "secret"},
            bridge=BridgeState(state),
        )
    assert exc_info.value.code == "unsupported_option"
    assert field in exc_info.value.details["unsupported_options"]
    assert state.started == []


def test_cli_exposes_thin_task_and_embedding_commands() -> None:
    parser = build_parser()
    task = parser.parse_args(
        [
            "task",
            "run",
            "--type",
            "embedding_generation",
            "--chunk-set-id",
            "cs-1",
            "--wait",
            "--timeout",
            "9",
            "--json",
        ]
    )
    coverage = parser.parse_args(["embedding", "coverage", "--chunk-set-id", "cs-1", "--json"])

    assert task.func is cmd_task_run
    assert task.wait is True
    assert task.timeout == 9
    assert coverage.embedding_cmd == "coverage"


def test_cli_wait_failure_returns_nonzero_and_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    responses = iter(
        [
            {"success": True, "job_id": "job-1"},
            {"tasks": []},
            {"tasks": [{"id": "job-1", "status": "error", "errors": ["safe"]}]},
        ]
    )
    monkeypatch.setattr(
        "ai_actuarial.cli._api_json_request", lambda *_args, **_kwargs: next(responses)
    )
    args = Namespace(
        api_url="http://api.test",
        token=None,
        task_type="embedding_generation",
        file_url=[],
        chunk_set_id=["cs-1"],
        profile_id=None,
        embedding_identity_key=None,
        payload_json=None,
        wait=True,
        timeout=2,
        json=True,
    )

    assert cmd_task_run(args) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["job_id"] == "job-1"
    assert payload["task"]["status"] == "error"


def test_cli_wait_timeout_returns_124_and_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    responses = iter(
        [
            {"success": True, "job_id": "job-1"},
            {"tasks": [{"id": "job-1", "status": "running"}]},
        ]
    )
    monkeypatch.setattr(
        "ai_actuarial.cli._api_json_request",
        lambda *_args, **_kwargs: next(responses),
    )
    args = Namespace(
        api_url="http://api.test",
        token=None,
        task_type="embedding_generation",
        file_url=[],
        chunk_set_id=["cs-1"],
        profile_id=None,
        embedding_identity_key=None,
        payload_json=None,
        wait=True,
        timeout=0,
        json=True,
    )

    assert cmd_task_run(args) == 124
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert "timed out" in payload["error"]


def test_cli_wait_success_emits_completed_contract(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    responses = iter(
        [
            {"success": True, "job_id": "job-1"},
            {"tasks": []},
            {
                "tasks": [
                    {
                        "id": "job-1",
                        "status": "completed",
                        "result": {"contract_version": 1, "reused": 2, "generated": 0},
                    }
                ]
            },
        ]
    )
    monkeypatch.setattr(
        "ai_actuarial.cli._api_json_request",
        lambda *_args, **_kwargs: next(responses),
    )
    args = Namespace(
        api_url="http://api.test",
        token=None,
        task_type="embedding_generation",
        file_url=[],
        chunk_set_id=["cs-1"],
        profile_id=None,
        embedding_identity_key=None,
        payload_json=None,
        wait=True,
        timeout=2,
        json=True,
    )

    assert cmd_task_run(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["job_id"] == "job-1"
    assert payload["task"]["result"] == {
        "contract_version": 1,
        "reused": 2,
        "generated": 0,
    }


def test_chunk_embedding_ui_removes_binding_and_overwrite_controls_and_uses_fixed_pair() -> None:
    root = Path(__file__).resolve().parents[1]
    chunk_form = (root / "client/src/pages/tasks/ChunkForm.tsx").read_text(encoding="utf-8")
    file_detail = (root / "client/src/pages/FileDetail.tsx").read_text(encoding="utf-8")
    tasks = (root / "client/src/pages/Tasks.tsx").read_text(encoding="utf-8")
    pipeline = (root / "client/src/pages/tasks/PipelineBaton.tsx").read_text(encoding="utf-8")
    schedules = (root / "client/src/pages/tasks/ScheduledTasksSection.tsx").read_text(
        encoding="utf-8"
    )

    for source in (chunk_form, file_detail, pipeline, schedules):
        assert "bind_to_kb" not in source
        assert "binding_mode" not in source
        assert "overwrite_same_profile" not in source
    assert 'type: "embedding_generation"' in tasks
    assert 'type: "embedding_generation"' in file_detail
    assert "chunk_sets?: Array<{ chunk_set_id?: string }>;" in tasks
    assert '.map((item) => String(item.chunk_set_id || "").trim())' in tasks
    empty_guard = 'if (chunk_set_ids.length === 0) throw new Error("Chunk task returned no stable chunk_set_ids");'
    embedding_request = "const embedding = await apiPost<{ job_id?: string; error?: string }>"
    assert tasks.index(empty_guard) < tasks.index(embedding_request)
    embedding_payload = tasks[
        tasks.index(embedding_request) : tasks.index("});", tasks.index(embedding_request))
    ]
    assert "incremental: true" in embedding_payload
    assert "chunk_set_ids" not in embedding_payload
    assert "chunk_set_ids" in file_detail
    assert "const identity = embeddingTask.result;" in tasks
    assert 'label: "Chunk & Embedding"' in pipeline
    assert "{task.status} · {task.task_id}" in pipeline


def test_managed_schedule_launches_incremental_embedding_for_reused_chunk_sets() -> None:
    class Runtime:
        started: list[tuple[str, dict[str, object], str]] = []

        def _pipeline_task_status(self, _task_id: str) -> str:
            return "completed"

        def _pipeline_task_result(self, _task_id: str) -> dict[str, object]:
            return {
                "items_downloaded": 0,
                "items_skipped": 2,
                "result": {
                    "chunk_sets": [
                        {"chunk_set_id": "cs-1"},
                        {"chunk_set_id": "cs-2"},
                    ]
                },
            }

        def start_background_task(
            self,
            task_type: str,
            payload: dict[str, object],
            *,
            task_name: str,
        ) -> str:
            self.started.append((task_type, payload, task_name))
            return "embedding-task"

    runtime = Runtime()
    result = NativeTaskRuntime._complete_scheduled_chunk_embedding(
        runtime, "chunk-task", "Nightly Chunk"
    )

    assert result == "embedding-task"
    assert runtime.started == [
        (
            "embedding_generation",
            {"incremental": True},
            "Scheduled: Nightly Chunk (Embedding)",
        )
    ]


def test_managed_schedule_does_not_launch_embedding_for_empty_chunk_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Runtime:
        started: list[object] = []

        def _pipeline_task_status(self, _task_id: str) -> str:
            return "completed"

        def _pipeline_task_result(self, _task_id: str) -> dict[str, object]:
            return {
                "items_downloaded": 0,
                "items_skipped": 0,
                "result": {"contract_version": 1, "chunk_sets": []},
            }

        def start_background_task(self, *_args: object, **_kwargs: object) -> str:
            self.started.append((_args, _kwargs))
            return "unexpected"

    monkeypatch.setattr("ai_actuarial.task_runtime.append_task_log", lambda *_args: None)
    runtime = Runtime()

    assert (
        NativeTaskRuntime._complete_scheduled_chunk_embedding(
            runtime, "chunk-task", "Nightly Chunk"
        )
        is None
    )
    assert runtime.started == []


@pytest.mark.parametrize("terminal", ["error", "stopped"])
def test_managed_schedule_does_not_launch_embedding_after_chunk_failure(
    terminal: str,
) -> None:
    class Runtime:
        started: list[object] = []

        def _pipeline_task_status(self, _task_id: str) -> str:
            return terminal

        def start_background_task(self, *_args: object, **_kwargs: object) -> str:
            self.started.append((_args, _kwargs))
            return "unexpected"

    runtime = Runtime()

    assert (
        NativeTaskRuntime._complete_scheduled_chunk_embedding(
            runtime, "chunk-task", "Nightly Chunk"
        )
        is None
    )
    assert runtime.started == []


def test_legacy_scheduled_chunk_params_are_sanitized_at_runtime(tmp_path: Path) -> None:
    runtime = NativeTaskRuntime(pipeline_baton_state_path=tmp_path / "pipeline.json")
    runtime._scheduler_loop_started = True
    runtime.set_site_config(
        {
            "scheduled_tasks": [
                {
                    "name": "Legacy Chunk",
                    "type": "chunk_generation",
                    "interval": "daily",
                    "enabled": True,
                    "params": {
                        "chunk_size": 321,
                        "kb_id": "kb-old",
                        "knowledge_base_id": "kb-old-2",
                        "bind_to_kb": True,
                        "binding_mode": "follow_latest",
                        "full_reindex": True,
                        "full_rebuild": True,
                        "force_reindex": True,
                        "overwrite_same_profile": True,
                    },
                }
            ]
        }
    )
    started: list[tuple[str, dict[str, object]]] = []
    runtime.start_background_task = lambda task_type, payload, **_kwargs: (
        started.append((task_type, dict(payload))) or "legacy-task"
    )

    runtime.init_scheduler()
    runtime.scheduler.jobs[0].job_func()

    assert started == [
        (
            "chunk_generation",
            {"chunk_size": 321, "name": "Scheduled: Legacy Chunk"},
        )
    ]


def test_partial_chunk_failure_is_error_and_scheduled_composition_does_not_continue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    runtime.task_lock = threading.RLock()
    runtime.active_tasks = {"chunk-task": {"id": "chunk-task", "status": "running"}}
    runtime.task_history = []
    runtime._append_history_to_disk = lambda _task: None
    runtime._chunk_candidate_file_urls = lambda _storage, _data: ["file-a", "file-b"]
    runtime._stop_requested = lambda _task_id: False
    storage = SimpleNamespace(
        create_chunk_profile=lambda **_kwargs: {
            "profile_id": "profile-1",
            "config_hash": "profile-hash",
        }
    )
    calls = 0

    def generate(**kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second failed")
        return {
            "chunk_set_id": "cs-1",
            "profile_id": "profile-1",
            "profile_config_hash": "profile-hash",
            "markdown_hash": "markdown-hash",
            "chunk_count": 1,
        }

    monkeypatch.setattr("ai_actuarial.task_runtime.generate_file_chunk_sets", generate)
    monkeypatch.setattr("ai_actuarial.task_runtime.append_task_log", lambda *_args: None)

    result = runtime._run_chunk_generation("chunk-task", storage, str(tmp_path / "db"), {})
    runtime._finalize_task_success("chunk-task", "chunk_generation", result)
    runtime.start_background_task = lambda *_args, **_kwargs: pytest.fail(
        "embedding must not launch"
    )

    assert result.success is False
    assert result.metadata["stopped"] is False
    assert len(result.metadata["result"]["chunk_sets"]) == 1
    assert runtime._pipeline_task_status("chunk-task") == "error"
    assert runtime._complete_scheduled_chunk_embedding("chunk-task", "Legacy Chunk") is None


def test_partial_chunk_stop_is_stopped_and_retains_completed_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    runtime._chunk_candidate_file_urls = lambda _storage, _data: ["file-a", "file-b"]
    stop_checks = iter([False, True])
    runtime._stop_requested = lambda _task_id: next(stop_checks)
    runtime._progress_callback = lambda _task_id: lambda *_args: None
    storage = SimpleNamespace(
        create_chunk_profile=lambda **_kwargs: {
            "profile_id": "profile-1",
            "config_hash": "profile-hash",
        }
    )
    monkeypatch.setattr(
        "ai_actuarial.task_runtime.generate_file_chunk_sets",
        lambda **_kwargs: {
            "chunk_set_id": "cs-1",
            "profile_id": "profile-1",
            "profile_config_hash": "profile-hash",
            "markdown_hash": "markdown-hash",
            "chunk_count": 1,
        },
    )

    result = runtime._run_chunk_generation("chunk-task", storage, str(tmp_path / "db"), {})

    assert result.success is False
    assert result.metadata["stopped"] is True
    assert result.items_downloaded == 1
    assert [row["chunk_set_id"] for row in result.metadata["result"]["chunk_sets"]] == ["cs-1"]


def test_chunk_stop_requested_during_only_file_is_terminal_stopped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    runtime.task_lock = threading.RLock()
    runtime.active_tasks = {"chunk-task": {"id": "chunk-task", "status": "running"}}
    runtime.task_history = []
    runtime._append_history_to_disk = lambda _task: None
    runtime._chunk_candidate_file_urls = lambda _storage, _data: ["file-a"]
    runtime._progress_callback = lambda _task_id: lambda *_args: None
    stopped = False
    runtime._stop_requested = lambda _task_id: stopped
    storage = SimpleNamespace(
        create_chunk_profile=lambda **_kwargs: {
            "profile_id": "profile-1",
            "config_hash": "profile-hash",
        }
    )

    def generate(**_kwargs: object) -> dict[str, object]:
        nonlocal stopped
        stopped = True
        return {
            "chunk_set_id": "cs-1",
            "profile_id": "profile-1",
            "profile_config_hash": "profile-hash",
            "markdown_hash": "markdown-hash",
            "chunk_count": 1,
        }

    monkeypatch.setattr("ai_actuarial.task_runtime.generate_file_chunk_sets", generate)
    monkeypatch.setattr("ai_actuarial.task_runtime.append_task_log", lambda *_args: None)

    result = runtime._run_chunk_generation("chunk-task", storage, str(tmp_path / "db"), {})
    runtime._finalize_task_success("chunk-task", "chunk_generation", result)
    runtime.start_background_task = lambda *_args, **_kwargs: pytest.fail(
        "embedding must not launch after a last-file stop"
    )

    assert result.success is False
    assert result.metadata["stopped"] is True
    assert result.items_downloaded == 1
    assert [row["chunk_set_id"] for row in result.metadata["result"]["chunk_sets"]] == ["cs-1"]
    assert runtime._pipeline_task_status("chunk-task") == "stopped"
    assert runtime._complete_scheduled_chunk_embedding("chunk-task", "Managed") is None


@pytest.mark.parametrize("stop_after_first", [False, True])
def test_markdown_partial_failure_or_stop_is_not_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stop_after_first: bool,
) -> None:
    first_path = tmp_path / "first.pdf"
    first_path.write_bytes(b"pdf")
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    runtime._markdown_candidate_files = lambda _storage, _data: [
        {"url": "file-a", "local_path": str(first_path), "markdown_content": ""},
        {"url": "file-b", "local_path": str(tmp_path / "missing.pdf"), "markdown_content": ""},
    ]
    checks = iter([False, stop_after_first, False])
    runtime._stop_requested = lambda _task_id: next(checks)
    runtime._progress_callback = lambda _task_id: lambda *_args: None
    runtime._resolve_file_path = lambda raw, _download_dir: Path(str(raw))
    runtime._convert_markdown_candidate_chain = lambda *_args, **_kwargs: (
        SimpleNamespace(engine="local", model="model", markdown="# ready"),
        "local",
    )
    storage = SimpleNamespace(
        update_file_markdown=lambda *_args, **_kwargs: (True, ""),
        record_markdown_terminal_source_state=lambda **_kwargs: None,
        clear_markdown_terminal_source_state=lambda _file_url: None,
    )
    monkeypatch.setattr(
        "ai_actuarial.task_runtime.load_markdown_conversion_config",
        lambda: {"default_tool": "auto", "tools": {}},
    )

    result = runtime._run_markdown_conversion("markdown-task", storage, {}, str(tmp_path), {})

    assert result.success is False
    assert result.metadata["stopped"] is stop_after_first
    assert result.items_downloaded == 1
    assert len(result.metadata["result"]["files"]) == 1
    assert result.metadata["items_terminal_skipped"] == (0 if stop_after_first else 1)
    assert len(result.metadata["result"]["outcomes"]) == (1 if stop_after_first else 2)


def test_markdown_stop_requested_during_only_file_preserves_output_as_stopped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "only.pdf"
    source_path.write_bytes(b"pdf")
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    runtime._markdown_candidate_files = lambda _storage, _data: [
        {"url": "file-a", "local_path": str(source_path), "markdown_content": ""}
    ]
    runtime._progress_callback = lambda _task_id: lambda *_args: None
    runtime._resolve_file_path = lambda raw, _download_dir: Path(str(raw))
    stopped = False
    runtime._stop_requested = lambda _task_id: stopped

    def convert(*_args: object, **_kwargs: object):
        nonlocal stopped
        stopped = True
        return SimpleNamespace(engine="local", model="model", markdown="# ready"), "local"

    runtime._convert_markdown_candidate_chain = convert
    storage = SimpleNamespace(update_file_markdown=lambda *_args, **_kwargs: (True, ""))
    monkeypatch.setattr(
        "ai_actuarial.task_runtime.load_markdown_conversion_config",
        lambda: {"default_tool": "auto", "tools": {}},
    )

    result = runtime._run_markdown_conversion("markdown-task", storage, {}, str(tmp_path), {})

    assert result.success is False
    assert result.metadata["stopped"] is True
    assert result.items_downloaded == 1
    assert len(result.metadata["result"]["files"]) == 1


@pytest.mark.parametrize("error", [False, True])
def test_task_finalization_has_no_active_history_visibility_gap(
    monkeypatch: pytest.MonkeyPatch,
    error: bool,
) -> None:
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    runtime.task_lock = threading.RLock()
    runtime.active_tasks = {"task-1": {"id": "task-1", "status": "running"}}
    runtime.task_history = []
    runtime._append_history_to_disk = lambda _task: None
    log_entered = threading.Event()
    release_log = threading.Event()

    def blocking_log(*_args: object) -> None:
        log_entered.set()
        assert release_log.wait(2)

    monkeypatch.setattr("ai_actuarial.task_runtime.append_task_log", blocking_log)
    if error:

        def finalize() -> None:
            runtime._finalize_task_error("task-1", "safe")

        expected = "error"
    else:
        result = CollectionResult(True, 1, 1, 0, [], {"result": {"contract_version": 1}})

        def finalize() -> None:
            runtime._finalize_task_success("task-1", "chunk_generation", result)

        expected = "completed"
    thread = threading.Thread(target=finalize)
    thread.start()
    assert log_entered.wait(2)
    try:
        assert runtime._pipeline_task_status("task-1") == expected
    finally:
        release_log.set()
        thread.join(2)
    assert not thread.is_alive()


def test_chunk_canonical_files_selector_fails_if_markdown_changed(tmp_path: Path) -> None:
    db_path = tmp_path / "index.db"
    storage = __import__("ai_actuarial.storage", fromlist=["Storage"]).Storage(str(db_path))
    try:
        storage.insert_file(
            "https://example.test/a.pdf",
            "hash",
            "A",
            "test",
            None,
            "a.pdf",
            "a.pdf",
            10,
            "application/pdf",
        )
        storage.update_file_markdown("https://example.test/a.pdf", "# changed", "manual")
        runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
        runtime._stop_requested = lambda _task_id: False
        runtime._progress_callback = lambda _task_id: lambda *_args: None

        with pytest.raises(RuntimeError, match="Markdown changed"):
            runtime._run_chunk_generation(
                "chunk-task",
                storage,
                str(db_path),
                {
                    "files": [
                        {
                            "file_url": "https://example.test/a.pdf",
                            "markdown_hash": "old-hash",
                            "markdown_version": "old-hash",
                        }
                    ]
                },
            )
    finally:
        storage.close()


def test_chunk_service_rechecks_each_expected_markdown_hash_at_generation_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_actuarial.api.services.files_write import generate_file_chunk_sets as real_generate
    from ai_actuarial.storage import Storage

    db_path = tmp_path / "toctou.db"
    file_urls = ["https://example.test/a.pdf", "https://example.test/b.pdf"]
    markdown_by_url = {file_urls[0]: "# Alpha", file_urls[1]: "# Beta"}
    storage = Storage(str(db_path))
    try:
        for file_url in file_urls:
            storage.insert_file(
                file_url,
                f"hash-{file_url[-5]}",
                file_url,
                "test",
                None,
                file_url.rsplit("/", 1)[-1],
                file_url.rsplit("/", 1)[-1],
                10,
                "application/pdf",
            )
            storage.update_file_markdown(file_url, markdown_by_url[file_url], "manual")

        runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
        runtime._stop_requested = lambda _task_id: False
        runtime._progress_callback = lambda _task_id: lambda *_args: None
        selectors = [
            {
                "file_url": file_url,
                "markdown_hash": __import__("hashlib")
                .sha256(markdown_by_url[file_url].encode("utf-8"))
                .hexdigest(),
                "markdown_version": __import__("hashlib")
                .sha256(markdown_by_url[file_url].encode("utf-8"))
                .hexdigest(),
            }
            for file_url in file_urls
        ]
        calls = 0

        def generate(**kwargs: object) -> dict[str, object]:
            nonlocal calls
            result = real_generate(**kwargs)
            calls += 1
            if calls == 1:
                mutator = Storage(str(db_path))
                try:
                    mutator.update_file_markdown(file_urls[1], "# Changed Beta", "manual")
                finally:
                    mutator.close()
            return result

        monkeypatch.setattr("ai_actuarial.task_runtime.generate_file_chunk_sets", generate)
        monkeypatch.setattr(
            "ai_actuarial.rag.semantic_chunking.SemanticChunker.chunk_document",
            lambda _chunker, text, **_kwargs: [
                SimpleNamespace(
                    chunk_index=0,
                    content=text,
                    token_count=2,
                    section_hierarchy="Root",
                )
            ],
        )

        result = runtime._run_chunk_generation(
            "chunk-task", storage, str(db_path), {"files": selectors}
        )

        assert result.success is False
        assert [row["file_url"] for row in result.metadata["result"]["chunk_sets"]] == [
            file_urls[0]
        ], result.errors
        assert any("Markdown changed" in error and file_urls[1] in error for error in result.errors)
        assert (
            storage._conn.execute(
                "SELECT COUNT(*) FROM file_chunk_sets WHERE file_url = ?",
                (file_urls[1],),
            ).fetchone()[0]
            == 0
        )
    finally:
        storage.close()


def test_tasks_ui_persistently_displays_ids_logs_and_chunk_embedding_results() -> None:
    root = Path(__file__).resolve().parents[1] / "client/src/pages"
    types = (root / "tasks/Tasks.types.ts").read_text(encoding="utf-8")
    card = (root / "tasks/TaskCard.tsx").read_text(encoding="utf-8")
    metrics = (root / "tasks/TaskMetrics.tsx").read_text(encoding="utf-8")
    table = (root / "tasks/TaskTable.tsx").read_text(encoding="utf-8")
    tasks = (root / "Tasks.tsx").read_text(encoding="utf-8")

    assert "result?: TaskContractResult" in types
    for field in (
        "chunk_sets",
        "provider",
        "model",
        "dimension",
        "generated",
        "reused",
        "invalid_regenerated",
        "failed",
    ):
        assert field in types
    assert "task.id" in card and "onViewLog" in card
    assert "TaskMetrics" in card
    assert "task.id" in table and "task.result" in table
    assert "invalid_regenerated" in metrics
    assert "provider" in metrics
    assert "TaskResultSummary" in table
    assert "onViewLog={viewTaskLog}" in tasks


def test_chunk_embedding_waiters_only_load_history_after_task_leaves_active() -> None:
    root = Path(__file__).resolve().parents[1] / "client/src/pages"

    for path, function_name in (
        (root / "Tasks.tsx", "waitForTaskResult"),
        (root / "FileDetail.tsx", "waitForChunkEmbeddingTask"),
    ):
        src = path.read_text(encoding="utf-8")
        function = src[src.index(f"async function {function_name}") :]
        function = function[: function.index("\n}") + 2]

        active_lookup = function.index("apiGet<{ tasks?:")
        active_match = function.index("activeTask")
        history_lookup = function.index('"/api/tasks/history?limit=200"')
        assert active_lookup < active_match < history_lookup
        assert "Promise.all" not in function


def test_embedding_failure_result_status_matches_terminal_task_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    runtime._progress_callback = lambda _task_id: lambda *_args: None
    runtime._stop_requested = lambda _task_id: False
    identity = SimpleNamespace(
        config=SimpleNamespace(embedding_batch_size=10),
        as_dict=lambda: {"provider": "test", "model": "test", "dimension": 2},
    )
    selection = {
        "chunks": [{"chunk_id": "chunk-1"}],
        "chunk_sets": [{"file_url": "https://example.test/a"}],
        "requested_file_urls": ["https://example.test/a"],
        "requested_chunk_set_ids": [],
        "chunk_set_ids": ["cs-1"],
    }
    ensured = SimpleNamespace(
        ready_count=0,
        stopped=False,
        failed=1,
        expected_count=1,
        generated=0,
        reused=0,
        invalid_regenerated=0,
        persisted_record_count=0,
        errors=[{"code": "embedding_failed"}],
        started_at="2026-08-26T00:00:00+00:00",
        completed_at="2026-08-26T00:00:01+00:00",
    )
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
        lambda **_kwargs: ensured,
    )
    monkeypatch.setattr(
        "ai_actuarial.task_runtime.embedding_coverage_for_selection",
        lambda **_kwargs: {"per_file": []},
    )

    result = runtime._run_embedding_generation(
        "embedding-task",
        SimpleNamespace(),
        {"chunk_set_ids": ["cs-1"]},
    )

    assert result.success is False
    assert result.metadata["result"]["status"] == "error"
