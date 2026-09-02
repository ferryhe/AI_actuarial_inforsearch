from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_actuarial.api.services import ops_read, task_service
from ai_actuarial.collectors.base import CollectionResult
from ai_actuarial.sqlite_schema import apply_schema, schema_status
from ai_actuarial.storage import Storage
from ai_actuarial.task_runtime import NativeTaskRuntime

OLE_HEADER = bytes.fromhex("d0cf11e0a1b11ae1")


def _configure_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    db_path = tmp_path / "index.db"
    download_dir = tmp_path / "files"
    config_path = tmp_path / "sites.yaml"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {download_dir.as_posix()}",
                "ai_config:",
                "  ocr:",
                "    provider: local",
                "    model: docling",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.delenv("MARKDOWN_CONVERSION_CONFIG_PATH", raising=False)
    return db_path, download_dir


def _seed_file(
    storage: Storage,
    *,
    url: str,
    path: Path,
    content_type: str,
    content_kind: str = "file",
) -> None:
    storage.upsert_file(
        url=url,
        sha256=f"sha-{path.name}",
        title=path.name,
        source_site="example.test",
        source_page_url="https://example.test",
        original_filename=path.name,
        local_path=str(path),
        bytes_size=path.stat().st_size if path.exists() else None,
        content_type=content_type,
        last_modified=None,
        etag=None,
        published_time=None,
        content_kind=content_kind,
    )
    storage.upsert_catalog_item(
        {"url": url, "sha256": f"sha-{path.name}", "category": "Issue 322"},
        pipeline_version="issue-322",
    )


def _outcomes(result: CollectionResult) -> dict[str, dict[str, object]]:
    return {str(row["file_url"]): row for row in result.metadata["result"]["outcomes"]}


def test_terminal_preflight_classifies_before_conversion_and_persists_exclusion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, _download_dir = _configure_runtime(tmp_path, monkeypatch)
    legacy_path = tmp_path / "legacy.ppt"
    missing_path = tmp_path / "missing.pdf"
    html_path = tmp_path / "html.pdf"
    html_magic_path = tmp_path / "html-magic.pdf"
    valid_path = tmp_path / "valid.pdf"
    legacy_path.write_bytes(OLE_HEADER + b"legacy-ppt")
    html_path.write_bytes(b"%PDF-1.7\ndeclared HTML response")
    html_magic_path.write_bytes(b"  <!DOCTYPE html><html><body>not a PDF</body></html>")
    valid_path.write_bytes(b"%PDF-1.7\nvalid")
    urls = {
        "legacy": "https://example.test/legacy.ppt",
        "missing": "https://example.test/missing.pdf",
        "html": "https://example.test/html.pdf",
        "html_magic": "https://example.test/html-magic.pdf",
        "valid": "https://example.test/valid.pdf",
    }
    storage = Storage(str(db_path))
    try:
        _seed_file(
            storage,
            url=urls["legacy"],
            path=legacy_path,
            content_type="application/vnd.ms-powerpoint",
        )
        _seed_file(
            storage,
            url=urls["missing"],
            path=missing_path,
            content_type="application/pdf",
        )
        _seed_file(
            storage,
            url=urls["html"],
            path=html_path,
            content_type="text/html; charset=utf-8",
            content_kind="web_page",
        )
        _seed_file(
            storage,
            url=urls["html_magic"],
            path=html_magic_path,
            content_type="application/pdf",
        )
        _seed_file(
            storage,
            url=urls["valid"],
            path=valid_path,
            content_type="application/pdf",
        )
    finally:
        storage.close()

    calls: list[str] = []

    def convert(path: Path, **_kwargs: object) -> SimpleNamespace:
        calls.append(path.name)
        return SimpleNamespace(markdown=f"# {path.stem}", engine="docling", model="docling")

    monkeypatch.setattr("ai_actuarial.task_runtime._convert_document_path", convert)
    runtime = NativeTaskRuntime()
    first = runtime._run_collection(
        "markdown-first",
        "markdown_conversion",
        {"conversion_tool": "docling", "overwrite_existing": True, "scan_count": 20},
    )

    assert calls == ["valid.pdf"]
    assert first.success is False
    assert first.items_downloaded == 1
    assert first.items_skipped == 0
    assert first.errors == []
    assert first.metadata["items_terminal_skipped"] == 4
    outcomes = _outcomes(first)
    assert outcomes[urls["legacy"]]["terminal_code"] == "unsupported_legacy_ppt"
    assert outcomes[urls["missing"]]["terminal_code"] == "repair_required"
    assert outcomes[urls["html"]]["terminal_code"] == "invalid_source"
    assert outcomes[urls["html_magic"]]["terminal_code"] == "invalid_source"
    assert outcomes[urls["valid"]]["outcome"] == "converted"
    assert {str(row["outcome"]) for row in outcomes.values()} == {
        "converted",
        "terminal_skipped",
    }
    assert [row["file_url"] for row in first.metadata["result"]["files"]] == [urls["valid"]]

    calls.clear()
    second = runtime._run_collection(
        "markdown-second",
        "markdown_conversion",
        {"conversion_tool": "docling", "scan_count": 20},
    )
    assert second.success is True
    assert second.items_found == 0
    assert second.metadata["result"]["files"] == []
    assert second.metadata["result"]["outcomes"] == []
    assert calls == []

    with sqlite3.connect(db_path) as conn:
        states = dict(
            conn.execute(
                "SELECT file_url, terminal_code FROM markdown_terminal_source_state"
            ).fetchall()
        )
    assert states == {
        urls["legacy"]: "unsupported_legacy_ppt",
        urls["missing"]: "repair_required",
        urls["html"]: "invalid_source",
        urls["html_magic"]: "invalid_source",
    }


def test_ordinary_backlog_preflights_legacy_ppt_with_missing_or_generic_mime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, _download_dir = _configure_runtime(tmp_path, monkeypatch)
    cases = (
        ("https://example.test/missing-mime.ppt", ""),
        ("https://example.test/generic-mime.ppt", "application/octet-stream"),
    )
    storage = Storage(str(db_path))
    try:
        for file_url, content_type in cases:
            source_path = tmp_path / file_url.rsplit("/", 1)[-1]
            source_path.write_bytes(OLE_HEADER + source_path.name.encode("ascii"))
            _seed_file(
                storage,
                url=file_url,
                path=source_path,
                content_type=content_type,
            )
    finally:
        storage.close()

    converter_calls: list[str] = []

    def convert(path: Path, **_kwargs: object) -> SimpleNamespace:
        converter_calls.append(path.name)
        return SimpleNamespace(markdown="# unexpected", engine="docling", model="docling")

    monkeypatch.setattr("ai_actuarial.task_runtime._convert_document_path", convert)
    result = NativeTaskRuntime()._run_collection(
        "legacy-generic-mime",
        "markdown_conversion",
        {"conversion_tool": "docling", "scan_count": 20},
    )

    assert result.success is False
    assert result.items_found == 2
    assert result.items_downloaded == 0
    assert result.metadata["items_terminal_skipped"] == 2
    assert converter_calls == []
    outcomes = _outcomes(result)
    assert set(outcomes) == {file_url for file_url, _content_type in cases}
    assert {str(outcome["terminal_code"]) for outcome in outcomes.values()} == {
        "unsupported_legacy_ppt"
    }
    with sqlite3.connect(db_path) as conn:
        states = dict(
            conn.execute(
                "SELECT file_url, terminal_code FROM markdown_terminal_source_state"
            ).fetchall()
        )
    assert states == {file_url: "unsupported_legacy_ppt" for file_url, _content_type in cases}


def test_source_change_and_explicit_selection_reenter_under_narrow_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, _download_dir = _configure_runtime(tmp_path, monkeypatch)
    missing_path = tmp_path / "missing.pdf"
    file_url = "https://example.test/missing.pdf"
    storage = Storage(str(db_path))
    try:
        _seed_file(
            storage,
            url=file_url,
            path=missing_path,
            content_type="application/pdf",
        )
    finally:
        storage.close()

    calls: list[str] = []

    def convert(path: Path, **_kwargs: object) -> SimpleNamespace:
        calls.append(path.name)
        return SimpleNamespace(markdown="# repaired", engine="docling", model="docling")

    monkeypatch.setattr("ai_actuarial.task_runtime._convert_document_path", convert)
    runtime = NativeTaskRuntime()
    terminal = runtime._run_collection(
        "missing-first",
        "markdown_conversion",
        {"conversion_tool": "docling"},
    )
    assert terminal.metadata["items_terminal_skipped"] == 1
    assert calls == []

    explicit = runtime._run_collection(
        "missing-explicit",
        "markdown_conversion",
        {"conversion_tool": "docling", "file_urls": [file_url], "overwrite_existing": True},
    )
    assert explicit.items_found == 1
    assert explicit.metadata["items_terminal_skipped"] == 1
    assert _outcomes(explicit)[file_url]["terminal_code"] == "repair_required"
    assert calls == []

    missing_path.write_bytes(b"%PDF-1.7\nrepaired")
    repaired = runtime._run_collection(
        "missing-repaired",
        "markdown_conversion",
        {"conversion_tool": "docling"},
    )
    assert repaired.success is True
    assert repaired.items_downloaded == 1
    assert repaired.metadata["items_terminal_skipped"] == 0
    assert _outcomes(repaired)[file_url]["outcome"] == "converted"
    assert calls == ["missing.pdf"]
    with sqlite3.connect(db_path) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM markdown_terminal_source_state WHERE file_url = ?",
                (file_url,),
            ).fetchone()[0]
            == 0
        )


def test_same_path_replacement_reenters_without_database_metadata_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, _download_dir = _configure_runtime(tmp_path, monkeypatch)
    source_path = tmp_path / "replacement.ppt"
    source_path.write_bytes(OLE_HEADER + b"legacy")
    original_stat = source_path.stat()
    file_url = "https://example.test/replacement.ppt"
    storage = Storage(str(db_path))
    try:
        _seed_file(
            storage,
            url=file_url,
            path=source_path,
            content_type="application/vnd.ms-powerpoint",
        )
    finally:
        storage.close()

    calls: list[str] = []

    def convert(path: Path, **_kwargs: object) -> SimpleNamespace:
        calls.append(path.name)
        return SimpleNamespace(markdown="# replacement", engine="docling", model="docling")

    monkeypatch.setattr("ai_actuarial.task_runtime._convert_document_path", convert)
    runtime = NativeTaskRuntime()
    first = runtime._run_collection(
        "replacement-first",
        "markdown_conversion",
        {"conversion_tool": "docling"},
    )
    assert first.metadata["items_terminal_skipped"] == 1
    assert calls == []

    source_path.write_bytes(b"%PDF-1.7\nvalid")
    os.utime(
        source_path,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )
    second = runtime._run_collection(
        "replacement-second",
        "markdown_conversion",
        {"conversion_tool": "docling"},
    )
    assert second.success is True
    assert second.items_downloaded == 1
    assert second.metadata["items_terminal_skipped"] == 0
    assert calls == ["replacement.ppt"]


def test_terminal_backlog_paginates_before_applying_logical_offset_and_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, _download_dir = _configure_runtime(tmp_path, monkeypatch)
    older_valid_path = tmp_path / "older-valid.pdf"
    newer_valid_path = tmp_path / "newer-valid.pdf"
    older_valid_path.write_bytes(b"%PDF-1.7\nolder")
    newer_valid_path.write_bytes(b"%PDF-1.7\nnewer")
    storage = Storage(str(db_path))
    try:
        _seed_file(
            storage,
            url="https://example.test/older-valid.pdf",
            path=older_valid_path,
            content_type="application/pdf",
        )
        _seed_file(
            storage,
            url="https://example.test/newer-valid.pdf",
            path=newer_valid_path,
            content_type="application/pdf",
        )
        for index in range(35):
            missing_path = tmp_path / f"missing-{index:02d}.pdf"
            _seed_file(
                storage,
                url=f"https://example.test/missing-{index:02d}.pdf",
                path=missing_path,
                content_type="application/pdf",
            )
    finally:
        storage.close()

    calls: list[str] = []

    def convert(path: Path, **_kwargs: object) -> SimpleNamespace:
        calls.append(path.name)
        return SimpleNamespace(markdown="# valid", engine="docling", model="docling")

    monkeypatch.setattr("ai_actuarial.task_runtime._convert_document_path", convert)
    runtime = NativeTaskRuntime()
    terminal = runtime._run_collection(
        "terminal-page",
        "markdown_conversion",
        {"conversion_tool": "docling", "scan_count": 35},
    )
    assert terminal.metadata["items_terminal_skipped"] == 35
    assert calls == []

    next_page = runtime._run_collection(
        "valid-page",
        "markdown_conversion",
        {
            "conversion_tool": "docling",
            "scan_start_index": 2,
            "scan_count": 1,
        },
    )
    assert next_page.success is True
    assert next_page.items_found == 1
    assert next_page.items_downloaded == 1
    assert calls == ["older-valid.pdf"]


def test_retryable_converter_failure_stays_eligible_and_has_per_item_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, _download_dir = _configure_runtime(tmp_path, monkeypatch)
    source_path = tmp_path / "retry.pdf"
    source_path.write_bytes(b"%PDF-1.7\nretry")
    file_url = "https://example.test/retry.pdf"
    storage = Storage(str(db_path))
    try:
        _seed_file(
            storage,
            url=file_url,
            path=source_path,
            content_type="application/pdf",
        )
    finally:
        storage.close()

    attempts = 0

    def fail_convert(_path: Path, **_kwargs: object) -> SimpleNamespace:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("converter unavailable")

    monkeypatch.setattr("ai_actuarial.task_runtime._convert_document_path", fail_convert)
    runtime = NativeTaskRuntime()
    for task_id in ("retry-first", "retry-second"):
        result = runtime._run_collection(
            task_id,
            "markdown_conversion",
            {"conversion_tool": "docling"},
        )
        assert result.success is False
        assert result.metadata["items_terminal_skipped"] == 0
        assert _outcomes(result)[file_url]["outcome"] == "retryable_error"
    assert attempts == 2


def test_terminal_only_finalization_and_both_api_summaries_stay_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = {
        "contract_version": 1,
        "files": [],
        "outcomes": [
            {
                "file_url": "https://example.test/legacy.ppt",
                "status": "terminal_skipped",
                "outcome": "terminal_skipped",
                "terminal_code": "unsupported_legacy_ppt",
            }
        ],
    }
    result = CollectionResult(
        success=False,
        items_found=1,
        items_downloaded=0,
        items_skipped=0,
        errors=[],
        metadata={
            "stopped": False,
            "items_terminal_skipped": 1,
            "result": canonical,
        },
    )
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    runtime.task_lock = threading.RLock()
    runtime.active_tasks = {
        "terminal-task": {
            "id": "terminal-task",
            "type": "markdown_conversion",
            "status": "running",
        }
    }
    runtime.task_history = []
    runtime._append_history_to_disk = lambda _task: None
    monkeypatch.setattr("ai_actuarial.task_runtime.append_task_log", lambda *_args: None)

    runtime._finalize_task_success("terminal-task", "markdown_conversion", result)
    task = runtime.task_history[0]
    assert task["status"] == "error"
    assert task["items_terminal_skipped"] == 1
    assert task["items_downloaded"] == 0
    assert task["items_skipped"] == 0
    assert task["errors"] == []
    assert task["result"] == canonical

    for builder in (
        task_service._build_task_display_summary,
        ops_read._build_task_display_summary,
    ):
        summary = builder(task)
        assert summary["primary"]["value"] == 0
        terminal_metric = next(
            metric
            for metric in summary["secondary"]
            if metric["label_key"] == "tasks.metric_terminal_skipped"
        )
        assert terminal_metric == {
            "label_key": "tasks.metric_terminal_skipped",
            "label_fallback": "Terminal skips",
            "value": 1,
        }


def test_auto_failure_details_preserve_every_runtime_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "control.pdf"
    source_path.write_bytes(b"%PDF-1.7\n")
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    monkeypatch.setattr(
        "ai_actuarial.task_runtime.candidate_chain_for_path",
        lambda *_args, **_kwargs: ["markitdown", "mistral", "local"],
    )

    def resolve(**kwargs: object) -> SimpleNamespace:
        engine = str(kwargs["engine_override"])
        if engine == "markitdown":
            raise RuntimeError("engine unavailable")
        return SimpleNamespace(
            engine=engine,
            provider="mistral" if engine == "mistral" else "local",
            model=engine,
            api_key=None,
            base_url=None,
        )

    monkeypatch.setattr("ai_actuarial.task_runtime.resolve_ocr_runtime", resolve)
    monkeypatch.setattr("ai_actuarial.task_runtime.apply_ocr_runtime_environment", lambda *_: None)

    def fail(_path: Path, **kwargs: object) -> SimpleNamespace:
        engine = str(kwargs["engine"])
        raise RuntimeError(f"{engine} concrete failure")

    monkeypatch.setattr("ai_actuarial.task_runtime._convert_document_path", fail)

    with pytest.raises(RuntimeError) as exc_info:
        runtime._convert_markdown_candidate_chain(
            source_path,
            explicit_runtime=None,
            storage=SimpleNamespace(),
            config={},
            md_config={"tools": {}},
        )

    detail = str(exc_info.value)
    assert "markitdown: engine unavailable" in detail
    assert "mistral: provider not configured" in detail
    assert "local: local concrete failure" in detail


def test_auto_long_failure_details_preserve_all_candidates_in_public_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, _download_dir = _configure_runtime(tmp_path, monkeypatch)
    source_path = tmp_path / "control.pdf"
    source_path.write_bytes(b"%PDF-1.7\n")
    file_url = "https://example.test/control.pdf"
    storage = Storage(str(db_path))
    try:
        _seed_file(
            storage,
            url=file_url,
            path=source_path,
            content_type="application/pdf",
        )
    finally:
        storage.close()

    candidates = ["opendataloader", "markitdown", "docling", "local"]
    monkeypatch.setattr(
        "ai_actuarial.task_runtime.candidate_chain_for_path",
        lambda *_args, **_kwargs: candidates,
    )

    def resolve(**kwargs: object) -> SimpleNamespace:
        engine = str(kwargs["engine_override"])
        return SimpleNamespace(
            engine=engine,
            provider="local",
            model=engine,
            api_key=None,
            base_url=None,
        )

    monkeypatch.setattr("ai_actuarial.task_runtime.resolve_ocr_runtime", resolve)
    monkeypatch.setattr("ai_actuarial.task_runtime.apply_ocr_runtime_environment", lambda *_: None)

    def fail(path: Path, **kwargs: object) -> SimpleNamespace:
        engine = str(kwargs["engine"])
        raise RuntimeError(f"{engine} concrete reason at {path} " + (f"{engine}-detail-" * 24))

    monkeypatch.setattr("ai_actuarial.task_runtime._convert_document_path", fail)
    result = NativeTaskRuntime()._run_collection(
        "auto-long-failures",
        "markdown_conversion",
        {"conversion_tool": "auto", "scan_count": 20},
    )

    assert result.success is False
    assert result.items_found == 1
    assert result.items_downloaded == 0
    assert result.metadata["items_terminal_skipped"] == 0
    outcome = _outcomes(result)[file_url]
    assert outcome["outcome"] == "retryable_error"
    detail = str(outcome["detail"])
    assert len(detail) <= 800
    assert str(source_path) not in detail
    assert len(result.errors) == 1
    for candidate in candidates:
        expected = f"{candidate}: {candidate} concrete reason"
        assert expected in detail
        assert expected in result.errors[0]


def test_registry_auto_failure_details_preserve_every_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from doc_to_md import registry

    source_path = tmp_path / "control.pdf"
    source_path.write_bytes(b"%PDF-1.7\n")
    candidates = ["opendataloader", "markitdown", "docling", "local"]
    monkeypatch.setattr(registry, "_auto_candidates", lambda _path: candidates)

    class FailingEngine:
        def __init__(self, *, name: str = "") -> None:
            self.name = name

        def convert(self, path: Path) -> object:
            raise RuntimeError(
                f"{self.name} unavailable at {path} " + (f"{self.name}-detail-" * 24)
            )

    def engine_class(name: str):
        class NamedFailingEngine(FailingEngine):
            def __init__(self, **_kwargs: object) -> None:
                super().__init__(name=name)

        return NamedFailingEngine

    monkeypatch.setattr(registry, "_import_engine", engine_class)

    with pytest.raises(RuntimeError) as exc_info:
        registry.convert_path(source_path, engine="auto")

    detail = str(exc_info.value)
    assert len(detail) <= 800
    assert str(source_path) not in detail
    for candidate in candidates:
        assert f"{candidate}: {candidate} unavailable" in detail


def test_schema_v14_migrates_terminal_state_table_and_reopens_idempotently(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "schema-v13.db"
    storage = Storage(str(db_path))
    storage.close()
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE IF EXISTS markdown_terminal_source_state")
        conn.execute("PRAGMA user_version=13")

    assert schema_status(db_path)["state"] == "needs_migration"
    applied = apply_schema(db_path)
    assert applied["database"]["user_version"] == 14
    assert applied["applied_migrations"] == ["add_markdown_terminal_source_state_v14"]
    with sqlite3.connect(db_path) as conn:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(markdown_terminal_source_state)")
        }
    assert columns == {"file_url", "terminal_code", "source_fingerprint", "updated_at"}

    reopened = Storage(str(db_path))
    reopened.close()
    repeated = apply_schema(db_path)
    assert repeated["state"] == "current"
    assert repeated["applied_migrations"] == []
