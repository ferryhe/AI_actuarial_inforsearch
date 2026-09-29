from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ai_actuarial.api.services.ops_read import list_task_history
from ai_actuarial.catalog import CatalogItem
from ai_actuarial.catalog_incremental import run_catalog_for_urls, run_incremental_catalog
from ai_actuarial.collectors.base import CollectionResult
from ai_actuarial.embedding_service import ensure_chunk_embeddings
from ai_actuarial.storage import Storage
from ai_actuarial.task_item_errors import ITEM_ERROR_LIMIT, make_item_error
from ai_actuarial.task_runtime import NativeTaskRuntime

NATIVE_TASK_ID = "task_1780000000000_0123456789abcdef"
UNSAFE_PARTS = (
    "document body secret",
    "Authorization: Bearer auth-secret",
    "Cookie: session=cookie-secret",
    "api_key=provider-secret",
    "C:\\Users\\private\\report.pdf",
    "/srv/private/report.pdf",
)


def _seed_catalog_files(db_path: Path, count: int) -> list[str]:
    storage = Storage(str(db_path))
    urls: list[str] = []
    try:
        for index in range(count):
            url = f"https://user:pass@example.test/private/{index}.pdf?api_key=secret-{index}"
            urls.append(url)
            storage.insert_file(
                url=url,
                sha256=f"sha-{index}",
                title=f"Secret title {index}",
                source_site="example.test",
                source_page_url="https://example.test",
                original_filename=f"secret-{index}.pdf",
                local_path=f"C:\\private\\secret-{index}.pdf",
                bytes=10,
                content_type="application/pdf",
            )
    finally:
        storage.close()
    return urls


def _catalog_item(row: dict[str, Any]) -> CatalogItem:
    return CatalogItem(
        source_site=str(row["source_site"]),
        title=str(row["title"]),
        original_filename=str(row["original_filename"]),
        url=str(row["url"]),
        local_path=str(row["local_path"]),
        keywords=["ai"],
        summary="safe summary",
        category="Other",
    )


def test_item_error_schema_is_closed_stable_and_uses_only_native_task_context() -> None:
    first = make_item_error(
        "catalog",
        "file_not_found",
        "https://example.test/report.pdf?query=one",
        task_id=NATIVE_TASK_ID,
    )
    repeated = make_item_error(
        "catalog",
        "file_not_found",
        "https://example.test/report.pdf?query=one",
        task_id=NATIVE_TASK_ID,
    )
    changed_query = make_item_error(
        "catalog",
        "file_not_found",
        "https://example.test/report.pdf?query=two",
        task_id="external-task-id",
    )
    fallback = make_item_error("embedding", "unknown", "chunk-secret")

    assert first == repeated
    assert first["object_id"].startswith("file:")
    assert first["display_name"] == f"File {first['object_id'][5:17]}"
    assert first["context_url"] == f"/tasks?task_id={NATIVE_TASK_ID}"
    assert changed_query["object_id"] != first["object_id"]
    assert "context_url" not in changed_query
    assert fallback["code"] == "provider_error"
    assert fallback["stage"] == "embedding"
    assert fallback["summary"] == "Embedding provider failed."
    assert set(first) == {
        "object_id",
        "display_name",
        "stage",
        "code",
        "summary",
        "context_url",
    }
    assert len(first["summary"]) <= 160
    assert "report" not in json.dumps(first)


def test_catalog_url_and_incremental_producers_keep_distinct_bounded_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_urls = [
        f"https://user:pass@example.test/private/{index}.pdf?api_key=secret-{index}"
        for index in range(ITEM_ERROR_LIMIT + 1)
    ]
    missing_stats = run_catalog_for_urls(
        db_path=str(tmp_path / "missing.db"),
        file_urls=missing_urls,
        out_jsonl=tmp_path / "missing.jsonl",
        out_md=tmp_path / "missing.md",
        task_id=NATIVE_TASK_ID,
    )

    assert missing_stats["errors"] == ITEM_ERROR_LIMIT + 1
    assert missing_stats["failed_items"] == ITEM_ERROR_LIMIT + 1
    assert len(missing_stats["item_errors"]) == ITEM_ERROR_LIMIT
    assert missing_stats["item_errors_truncated"] is True
    assert {row["code"] for row in missing_stats["item_errors"]} == {"file_not_found"}
    assert not any(url in json.dumps(missing_stats["item_errors"]) for url in missing_urls)

    db_path = tmp_path / "incremental.db"
    urls = _seed_catalog_files(db_path, 2)

    def process(row: dict[str, Any], *_args: Any, **_kwargs: Any) -> tuple[Any, ...]:
        if row["url"] == urls[0]:
            return row, _catalog_item(row), "ok", None
        raw = " | ".join(UNSAFE_PARTS)
        return row, _catalog_item(row), f"error:{raw}", None

    monkeypatch.setattr("ai_actuarial.catalog_incremental._process_single_row", process)
    stats = run_incremental_catalog(
        db_path=str(db_path),
        out_jsonl=tmp_path / "incremental.jsonl",
        out_md=tmp_path / "incremental.md",
        batch=10,
        limit=10,
        task_id=NATIVE_TASK_ID,
    )

    assert stats["processed"] == 1
    assert stats["failed_items"] == 1
    assert stats["item_errors_truncated"] is False
    assert stats["item_errors"][0]["code"] == "catalog_failed"
    assert stats["item_errors"][0]["context_url"].endswith(NATIVE_TASK_ID)
    serialized = json.dumps(stats["item_errors"])
    assert all(part not in serialized for part in UNSAFE_PARTS)


@pytest.mark.parametrize("producer", ["explicit", "incremental"])
def test_catalog_missing_source_uses_file_not_found_without_leaking_identity(
    producer: str,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db_path = tmp_path / f"catalog-missing-{producer}.db"
    file_url = "https://user:pass@example.test/private/report.pdf?api_key=provider-secret"
    missing_path = tmp_path / "Authorization-Bearer-secret-report.pdf"
    storage = Storage(str(db_path))
    try:
        storage.insert_file(
            url=file_url,
            sha256="missing-source-sha",
            title="document body secret",
            source_site="example.test",
            source_page_url="https://example.test",
            original_filename="Cookie-session-cookie-secret.pdf",
            local_path=str(missing_path),
            bytes=10,
            content_type="application/pdf",
        )
    finally:
        storage.close()

    common = {
        "db_path": str(db_path),
        "out_jsonl": tmp_path / f"{producer}.jsonl",
        "out_md": tmp_path / f"{producer}.md",
        "skip_existing": False,
        "input_source": "source",
        "max_workers": 1,
    }
    caplog.set_level("WARNING", logger="ai_actuarial.catalog_incremental")
    if producer == "explicit":
        stats = run_catalog_for_urls(file_urls=[file_url], **common)
    else:
        stats = run_incremental_catalog(batch=10, limit=10, **common)

    assert stats["failed_items"] == 1
    assert stats["missing_files"] == 1
    assert stats["item_errors"][0]["code"] == "file_not_found"
    serialized = json.dumps(stats)
    for secret in (
        file_url,
        str(missing_path),
        "document body secret",
        "provider-secret",
        "Authorization-Bearer-secret",
        "Cookie-session-cookie-secret",
    ):
        assert secret not in serialized
        assert secret not in caplog.text
    if producer == "incremental":
        assert "Catalog item failed: file_not_found" in caplog.text


@pytest.mark.parametrize("producer", ["explicit", "incremental"])
def test_catalog_worker_exception_logs_only_fixed_failure_code(
    producer: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    db_path = tmp_path / f"catalog-worker-exception-{producer}.db"
    file_url = "https://judge-user:judge-pass@example.test/private.pdf?api_key=judge-api-secret"
    storage = Storage(str(db_path))
    try:
        storage.insert_file(
            url=file_url,
            sha256="worker-exception-sha",
            title="worker exception title",
            source_site="example.test",
            source_page_url="https://example.test",
            original_filename="worker-exception.pdf",
            local_path="C:\\Users\\private\\worker-exception.pdf",
            bytes=10,
            content_type="application/pdf",
        )
    finally:
        storage.close()

    sensitive_parts = (
        file_url,
        "judge-user",
        "judge-pass",
        "judge-api-secret",
        "Authorization: Bearer judge-auth-secret",
        "Cookie: session=judge-cookie-secret",
        "C:\\Users\\private\\worker-exception.pdf",
        "/srv/private/worker-exception.pdf",
    )

    def fail_worker(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError(" | ".join(sensitive_parts))

    monkeypatch.setattr("ai_actuarial.catalog_incremental._process_single_row", fail_worker)
    caplog.set_level("ERROR", logger="ai_actuarial.catalog_incremental")
    common = {
        "db_path": str(db_path),
        "out_jsonl": tmp_path / f"{producer}.jsonl",
        "out_md": tmp_path / f"{producer}.md",
        "skip_existing": False,
        "max_workers": 1,
    }
    if producer == "explicit":
        stats = run_catalog_for_urls(file_urls=[file_url], **common)
    else:
        stats = run_incremental_catalog(batch=10, limit=10, **common)

    assert stats["errors"] == 1
    assert stats["failed_items"] == 1
    assert stats["item_errors"][0]["code"] == "catalog_failed"
    assert "Catalog worker failed: catalog_failed" in caplog.text
    assert all(part not in caplog.text for part in sensitive_parts)


class _EmbeddingStorage:
    def __init__(self) -> None:
        self.valid: dict[str, list[float]] = {}

    def read_valid_chunk_embeddings(
        self, chunk_ids: list[str], *, identity: dict[str, Any]
    ) -> dict[str, Any]:
        del identity
        return {
            "valid": {
                chunk_id: self.valid[chunk_id] for chunk_id in chunk_ids if chunk_id in self.valid
            },
            "missing_chunk_ids": [chunk_id for chunk_id in chunk_ids if chunk_id not in self.valid],
            "invalid_chunk_ids": [],
        }

    def batch_upsert_chunk_embeddings(
        self, rows: list[dict[str, Any]], *, identity: dict[str, Any]
    ) -> None:
        del identity
        for row in rows:
            self.valid[str(row["chunk_id"])] = list(row["vector"])


def _embedding_identity() -> SimpleNamespace:
    return SimpleNamespace(
        provider="secret-provider",
        model="secret-model",
        dimension=3,
        config=SimpleNamespace(embedding_batch_size=1),
        as_dict=lambda: {
            "provider": "secret-provider",
            "model": "secret-model",
            "dimension": 3,
        },
    )


def test_embedding_producer_counts_all_failures_but_retains_only_first_50() -> None:
    secret_chunk_ids = [
        f"chunk-{index}-document body secret-api_key=provider-secret-C:\\private\\{index}"
        for index in range(ITEM_ERROR_LIMIT + 2)
    ]
    chunks = [
        {"chunk_id": chunk_id, "content": "document body secret"} for chunk_id in secret_chunk_ids
    ]

    class FailingGenerator:
        calls = 0

        def generate_embeddings(self, _texts: list[str]) -> list[list[float]]:
            self.calls += 1
            if self.calls == 1:
                return [[1.0, 0.0, 0.0]]
            raise RuntimeError(" | ".join(UNSAFE_PARTS))

    ensured = ensure_chunk_embeddings(
        storage=_EmbeddingStorage(),  # type: ignore[arg-type]
        chunks=chunks,
        identity=_embedding_identity(),  # type: ignore[arg-type]
        generator=FailingGenerator(),
        batch_size=1,
        task_id=NATIVE_TASK_ID,
    )

    assert ensured.generated == 1
    assert ensured.failed == ITEM_ERROR_LIMIT + 1
    assert len(ensured.errors) == ITEM_ERROR_LIMIT
    assert ensured.errors_truncated is True
    assert all(
        set(row) <= {"object_id", "display_name", "stage", "code", "summary", "context_url"}
        for row in ensured.errors
    )
    serialized = json.dumps(ensured.errors)
    assert all(
        secret not in serialized
        for secret in (*UNSAFE_PARTS, *secret_chunk_ids, "secret-provider", "secret-model")
    )


class _MarkdownStorage:
    def __init__(self) -> None:
        self.terminal: list[str] = []

    def update_file_markdown(
        self, file_url: str, markdown: str, *, markdown_source: str
    ) -> tuple[bool, str]:
        del markdown, markdown_source
        if "update" in file_url:
            return False, " | ".join(UNSAFE_PARTS)
        return True, ""

    def record_markdown_terminal_source_state(self, **kwargs: Any) -> None:
        self.terminal.append(str(kwargs["file_url"]))

    def clear_markdown_terminal_source_state(self, _file_url: str) -> None:
        return None


def test_markdown_partial_failures_are_safe_and_exclude_terminal_skip_and_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls = {
        "ok": "https://example.test/ok.pdf",
        "conversion": "https://user:pass@example.test/conversion.pdf?api_key=provider-secret",
        "update": "https://example.test/update.pdf?Cookie=cookie-secret",
        "terminal": "https://example.test/legacy.ppt",
    }
    rows = [{"url": url} for url in urls.values()]
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    runtime._markdown_candidate_files = lambda *_args: rows  # type: ignore[method-assign]
    runtime._progress_callback = lambda _task_id: lambda *_args: None  # type: ignore[method-assign]
    runtime._stop_requested = lambda _task_id: False  # type: ignore[method-assign]
    runtime._markdown_source_preflight = lambda row, _download_dir: {  # type: ignore[method-assign]
        "local_path": f"C:\\private\\{str(row['url']).rsplit('/', 1)[-1]}",
        "source_fingerprint": "fingerprint",
        "terminal_code": "unsupported_legacy_ppt" if row["url"] == urls["terminal"] else "",
    }

    def convert(path: Path, **_kwargs: Any) -> tuple[SimpleNamespace, str]:
        if "conversion" in str(path):
            raise RuntimeError(" | ".join(UNSAFE_PARTS))
        return (
            SimpleNamespace(markdown="# safe", engine="secret-engine", model="secret-model"),
            "secret-provider",
        )

    runtime._convert_markdown_candidate_chain = convert  # type: ignore[method-assign]
    monkeypatch.setattr(
        "ai_actuarial.task_runtime.load_markdown_conversion_config",
        lambda: {"default_tool": "auto", "tools": {}},
    )

    result = runtime._run_markdown_conversion(
        NATIVE_TASK_ID,
        _MarkdownStorage(),  # type: ignore[arg-type]
        {},
        "C:\\private",
        {"overwrite_existing": True},
    )

    assert result.items_downloaded == 1
    assert result.metadata["items_terminal_skipped"] == 1
    assert result.metadata["failed_items"] == 2
    assert result.metadata["item_errors_truncated"] is False
    assert {row["code"] for row in result.metadata["item_errors"]} == {
        "conversion_failed",
        "markdown_update_failed",
    }
    assert set(result.errors) == {
        "Markdown conversion failed.",
        "Converted markdown could not be saved.",
    }
    assert all(
        row.get("outcome") != "retryable_error" for row in result.metadata["result"]["outcomes"]
    )
    serialized = json.dumps(
        {
            "errors": result.errors,
            "item_errors": result.metadata["item_errors"],
            "outcomes": result.metadata["result"]["outcomes"],
        }
    )
    assert all(part not in serialized for part in UNSAFE_PARTS)
    assert urls["conversion"] not in serialized
    assert urls["update"] not in serialized

    runtime._stop_requested = lambda _task_id: True  # type: ignore[method-assign]
    stopped = runtime._run_markdown_conversion(
        NATIVE_TASK_ID,
        _MarkdownStorage(),  # type: ignore[arg-type]
        {},
        "C:\\private",
        {"overwrite_existing": True},
    )
    assert stopped.metadata["stopped"] is True
    assert stopped.metadata["failed_items"] == 0
    assert stopped.metadata["item_errors"] == []


def test_finalized_task_persists_bounded_contract_and_restart_api_reads_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    item_errors = [
        make_item_error(
            "catalog", "catalog_failed", f"https://example.test/{index}", task_id=NATIVE_TASK_ID
        )
        for index in range(ITEM_ERROR_LIMIT)
    ]
    result = CollectionResult(
        success=False,
        items_found=52,
        items_downloaded=1,
        items_skipped=0,
        errors=["Catalog processing failed."],
        metadata={
            "failed_items": 51,
            "item_errors": item_errors,
            "item_errors_truncated": True,
            "catalog_scanned": 52,
            "catalog_ok": 1,
            "catalog_skipped": 0,
            "catalog_errors": 1,
        },
    )
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    runtime.task_lock = threading.RLock()
    runtime.active_tasks = {
        NATIVE_TASK_ID: {"id": NATIVE_TASK_ID, "name": "Catalog", "type": "catalog"}
    }
    runtime.task_history = []
    monkeypatch.setattr("ai_actuarial.task_runtime.append_task_log", lambda *_args: None)

    runtime._finalize_task_success(NATIVE_TASK_ID, "catalog", result)
    restarted = NativeTaskRuntime.__new__(NativeTaskRuntime)._load_history_from_disk()
    task = list_task_history(restarted, 20)["tasks"][0]

    assert task["failed_items"] == 51
    assert len(task["item_errors"]) == ITEM_ERROR_LIMIT
    assert task["item_errors_truncated"] is True
    assert task["catalog_errors"] == 1
    assert task["catalog_errors"] != task["failed_items"]
    assert len(json.dumps(task)) < 30_000


@pytest.mark.parametrize("count", [0, 1, 50, 51])
def test_finalizer_normalizes_zero_one_and_cap_boundaries(
    count: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retained = min(count, ITEM_ERROR_LIMIT)
    result = CollectionResult(
        success=count == 0,
        items_found=count,
        items_downloaded=0,
        items_skipped=0,
        errors=[] if count == 0 else ["Catalog processing failed."],
        metadata={
            "failed_items": count,
            "item_errors": [
                make_item_error("catalog", "catalog_failed", f"file-{index}")
                for index in range(retained)
            ],
        },
    )
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    runtime.task_lock = threading.RLock()
    runtime.active_tasks = {"test": {"id": "test", "type": "catalog"}}
    runtime.task_history = []
    runtime._append_history_to_disk = lambda _task: None  # type: ignore[method-assign]
    monkeypatch.setattr("ai_actuarial.task_runtime.append_task_log", lambda *_args: None)

    runtime._finalize_task_success("test", "catalog", result)
    task = runtime.task_history[0]

    assert task["failed_items"] == count
    assert len(task["item_errors"]) == retained
    assert task["item_errors_truncated"] is (count > retained)


def test_tasks_query_selection_opens_existing_log_without_posting() -> None:
    source = (Path(__file__).resolve().parents[1] / "client/src/pages/Tasks.tsx").read_text(
        encoding="utf-8"
    )
    start = source.index("const taskId = trustedTaskIdFromSearch(window.location.search);")
    end = source.index("}, [activeTasks, historyTasks, location, viewTaskLog]);", start)
    effect = source[start:end]

    assert "[...activeTasks, ...historyTasks].find" in effect
    assert "void viewTaskLog(taskId, task.name, task);" in effect
    assert "apiPost" not in effect


@pytest.mark.parametrize(
    ("task_type", "public_error"),
    [
        ("catalog", "Catalog processing failed."),
        ("embedding_generation", "Embedding generation failed."),
        ("markdown_conversion", "Markdown conversion failed."),
    ],
)
def test_stage_level_failures_use_fixed_public_top_level_errors(
    task_type: str,
    public_error: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    runtime.task_lock = threading.RLock()
    runtime.active_tasks = {NATIVE_TASK_ID: {"id": NATIVE_TASK_ID, "type": task_type}}
    runtime.task_history = []
    runtime._run_collection = lambda *_args: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeError(" | ".join(UNSAFE_PARTS))
    )
    runtime._finalize_child_run = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
    runtime._append_history_to_disk = lambda _task: None  # type: ignore[method-assign]
    monkeypatch.setattr("ai_actuarial.task_runtime.append_task_log", lambda *_args: None)

    runtime._execute_collection_task(NATIVE_TASK_ID, task_type, {})

    assert runtime.task_history[0]["errors"] == [public_error]
    assert all(part not in json.dumps(runtime.task_history[0]) for part in UNSAFE_PARTS)
