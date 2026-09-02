from __future__ import annotations

import copy
import json
import logging
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest

import ai_actuarial.api.services.ops_read as ops_read_service
import ai_actuarial.task_runtime as task_runtime_module
from ai_actuarial.api.services.ops_read import get_global_logs, list_task_history
from ai_actuarial.manifest_ingest import ingest_manifest
from ai_actuarial.storage import Storage
from ai_actuarial.task_runtime import NativeTaskRuntime


def _legacy_manifest() -> dict[str, Any]:
    return {
        "schema_version": "web-listening-manifest.v1",
        "manifest_id": "manifest-320",
        "run": {"run_id": "run-320"},
        "source": {
            "source_id": "source-320",
            "site_name": "Example Source",
            "site_url": "https://example.test/",
        },
        "downloaded_assets": [
            {
                "asset_id": "asset-320",
                "url": "https://example.test/report.pdf",
                "filename": "report.pdf",
                "media_type": "application/pdf",
                "bytes": 320,
                "checksum": {"algorithm": "sha256", "value": "a" * 64},
                "local_path": "data/files/report.pdf",
            }
        ],
    }


class _StorageSpy:
    def __init__(self) -> None:
        self.transaction_calls = 0
        self.saved_manifests: list[dict[str, Any]] = []
        self.upserted_files: list[dict[str, Any]] = []

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[None]:
        assert immediate is True
        self.transaction_calls += 1
        yield

    def save_manifest_raw(self, **kwargs: Any) -> None:
        self.saved_manifests.append(kwargs)

    def upsert_file(self, **kwargs: Any) -> None:
        self.upserted_files.append(kwargs)


@contextmanager
def _capture_task_runtime_log(path: Path) -> Iterator[None]:
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger = task_runtime_module.logger
    previous_level = logger.level
    logger.setLevel(logging.ERROR)
    logger.addHandler(handler)
    try:
        yield
    finally:
        handler.flush()
        logger.removeHandler(handler)
        handler.close()
        logger.setLevel(previous_level)


def _assert_contract_error(
    manifest: Any,
    *,
    expected_code: str,
    expected_field: str,
    raw_text: str | None = None,
) -> None:
    storage = _StorageSpy()
    with pytest.raises(ValueError) as exc_info:
        ingest_manifest(storage, manifest, raw_text=raw_text)

    error = exc_info.value
    assert getattr(error, "code", None) == expected_code
    assert getattr(error, "field", None) == expected_field
    assert storage.transaction_calls == 0
    assert storage.saved_manifests == []
    assert storage.upserted_files == []


@pytest.mark.parametrize(
    ("payload", "expected_code", "expected_field"),
    [
        pytest.param(
            {
                "schema_version": "web-listening-result.v1",
                "result_id": "result-320",
                "manifest": _legacy_manifest(),
            },
            "unsupported_manifest_contract",
            "schema_version",
            id="full-result",
        ),
        pytest.param(
            {
                "schema_version": "web-listening-manifest.v1",
                "manifest": _legacy_manifest(),
                "assets": [],
            },
            "invalid_manifest_contract",
            "manifest_id",
            id="nested-manifest",
        ),
    ],
)
def test_issue_320_incompatible_producer_payloads_fail_closed(
    payload: dict[str, Any], expected_code: str, expected_field: str
) -> None:
    _assert_contract_error(
        payload,
        expected_code=expected_code,
        expected_field=expected_field,
    )


@pytest.mark.parametrize(
    ("field", "value", "delete"),
    [
        pytest.param("schema_version", None, True, id="missing-schema"),
        pytest.param("schema_version", 1, False, id="schema-type"),
        pytest.param("schema_version", "web-listening-manifest.v2", False, id="schema-value"),
        pytest.param("manifest_id", None, True, id="missing-manifest-id"),
        pytest.param("manifest_id", " ", False, id="empty-manifest-id"),
        pytest.param("manifest_id", 320, False, id="manifest-id-type"),
        pytest.param("run", None, True, id="missing-run"),
        pytest.param("run", [], False, id="run-type"),
        pytest.param("run.run_id", None, True, id="missing-run-id"),
        pytest.param("run.run_id", "", False, id="empty-run-id"),
        pytest.param("run.run_id", 320, False, id="run-id-type"),
        pytest.param("source", None, True, id="missing-source"),
        pytest.param("source", [], False, id="source-type"),
        pytest.param("source.source_id", None, True, id="missing-source-id"),
        pytest.param("source.source_id", "", False, id="empty-source-id"),
        pytest.param("source.source_id", 320, False, id="source-id-type"),
        pytest.param("source.site_name", None, True, id="missing-site-name"),
        pytest.param("source.site_name", " ", False, id="empty-site-name"),
        pytest.param("source.site_name", 320, False, id="site-name-type"),
        pytest.param("source.site_url", None, True, id="missing-site-url"),
        pytest.param("source.site_url", "relative/source", False, id="relative-site-url"),
        pytest.param("source.site_url", 320, False, id="site-url-type"),
        pytest.param("downloaded_assets", None, True, id="missing-assets"),
        pytest.param("downloaded_assets", {}, False, id="assets-type"),
    ],
)
def test_issue_320_rejects_invalid_top_level_contract(field: str, value: Any, delete: bool) -> None:
    manifest = _legacy_manifest()
    target: dict[str, Any] = manifest
    parts = field.split(".")
    for part in parts[:-1]:
        target = target[part]
    if delete:
        del target[parts[-1]]
    else:
        target[parts[-1]] = value

    expected_code = (
        "unsupported_manifest_contract"
        if field == "schema_version"
        else "invalid_manifest_contract"
    )
    _assert_contract_error(
        manifest,
        expected_code=expected_code,
        expected_field=field,
    )


@pytest.mark.parametrize(
    ("field", "value", "delete"),
    [
        pytest.param("asset_id", None, True, id="missing-asset-id"),
        pytest.param("asset_id", "", False, id="empty-asset-id"),
        pytest.param("asset_id", 320, False, id="asset-id-type"),
        pytest.param("url", None, True, id="missing-url"),
        pytest.param("url", "/relative.pdf", False, id="relative-url"),
        pytest.param("url", "ftp://example.test/report.pdf", False, id="unsupported-url"),
        pytest.param("url", 320, False, id="url-type"),
        pytest.param("checksum", None, True, id="missing-checksum"),
        pytest.param("checksum", "sha256:a", False, id="checksum-type"),
        pytest.param("checksum.algorithm", None, True, id="missing-algorithm"),
        pytest.param("checksum.algorithm", "md5", False, id="checksum-algorithm"),
        pytest.param("checksum.algorithm", 320, False, id="algorithm-type"),
        pytest.param("checksum.value", None, True, id="missing-digest"),
        pytest.param("checksum.value", "a" * 63, False, id="short-digest"),
        pytest.param("checksum.value", "z" * 64, False, id="nonhex-digest"),
        pytest.param("checksum.value", 320, False, id="digest-type"),
        pytest.param("media_type", None, True, id="missing-media-type"),
        pytest.param("media_type", 1, False, id="media-type-type"),
        pytest.param("media_type", " ", False, id="empty-media-type"),
        pytest.param("bytes", None, True, id="missing-bytes"),
        pytest.param("bytes", True, False, id="boolean-bytes"),
        pytest.param("bytes", -1, False, id="negative-bytes"),
        pytest.param("bytes", "320", False, id="string-bytes"),
        pytest.param("filename", None, True, id="missing-filename"),
        pytest.param("filename", "", False, id="empty-filename"),
        pytest.param("filename", 320, False, id="filename-type"),
        pytest.param("local_path", None, True, id="missing-path"),
        pytest.param("local_path", 320, False, id="path-type"),
        pytest.param("local_path", " ", False, id="empty-path"),
    ],
)
def test_issue_320_rejects_invalid_asset_before_transaction(
    field: str, value: Any, delete: bool
) -> None:
    manifest = _legacy_manifest()
    asset = manifest["downloaded_assets"][0]
    target = asset
    parts = field.split(".")
    for part in parts[:-1]:
        target = target[part]
    if delete:
        del target[parts[-1]]
    else:
        target[parts[-1]] = value

    _assert_contract_error(
        manifest,
        expected_code="invalid_manifest_contract",
        expected_field=f"downloaded_assets[0].{field}",
    )


def test_issue_320_rejects_malformed_late_asset_before_any_write() -> None:
    manifest = _legacy_manifest()
    malformed = copy.deepcopy(manifest["downloaded_assets"][0])
    malformed["asset_id"] = "asset-late"
    malformed["url"] = "https://example.test/late.pdf"
    malformed["bytes"] = -1
    manifest["downloaded_assets"].append(malformed)

    _assert_contract_error(
        manifest,
        expected_code="invalid_manifest_contract",
        expected_field="downloaded_assets[1].bytes",
    )


def test_issue_320_rejects_non_object_asset_before_transaction() -> None:
    manifest = _legacy_manifest()
    manifest["downloaded_assets"] = ["not-an-object"]

    _assert_contract_error(
        manifest,
        expected_code="invalid_manifest_contract",
        expected_field="downloaded_assets[0]",
    )


def test_issue_320_rejects_invalid_optional_path_even_with_valid_fallback() -> None:
    manifest = _legacy_manifest()
    manifest["downloaded_assets"][0]["canonical_blob_path"] = ""

    _assert_contract_error(
        manifest,
        expected_code="invalid_manifest_contract",
        expected_field="downloaded_assets[0].canonical_blob_path",
    )


@pytest.mark.parametrize(
    ("field", "expected_field"),
    [
        pytest.param("asset", "downloaded_assets[0].url", id="asset-url"),
        pytest.param("source", "source.site_url", id="source-url"),
    ],
)
def test_issue_320_rejects_backslash_url_before_transaction(
    field: str, expected_field: str
) -> None:
    manifest = _legacy_manifest()
    if field == "asset":
        manifest["downloaded_assets"][0]["url"] = "https://example.test\\report.pdf"
    else:
        manifest["source"]["site_url"] = "https://example.test\\source"

    _assert_contract_error(
        manifest,
        expected_code="invalid_manifest_contract",
        expected_field=expected_field,
    )


def test_issue_320_backslash_asset_url_leaves_real_database_unchanged(
    tmp_path: Path,
) -> None:
    manifest = _legacy_manifest()
    manifest["downloaded_assets"][0]["url"] = "https://example.test\\report.pdf"
    raw_text = json.dumps(manifest)
    storage = Storage(str(tmp_path / "backslash.db"))
    try:
        with pytest.raises(ValueError) as exc_info:
            ingest_manifest(storage, json.loads(raw_text), raw_text=raw_text)

        assert getattr(exc_info.value, "code", None) == "invalid_manifest_contract"
        assert getattr(exc_info.value, "field", None) == "downloaded_assets[0].url"
        assert storage._conn.execute("SELECT COUNT(*) FROM manifest_raw").fetchone()[0] == 0
        assert storage._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
    finally:
        storage.close()


@pytest.mark.parametrize(
    ("raw_text", "expected_code"),
    [
        pytest.param(
            '{"schema_version":"web-listening-manifest.v1",'
            '"schema_version":"web-listening-manifest.v1"}',
            "manifest_json_duplicate_key",
            id="top-level",
        ),
        pytest.param(
            '{"schema_version":"web-listening-manifest.v1","manifest_id":"m",'
            '"run":{"run_id":"r","run_id":"duplicate"},"source":{},'
            '"downloaded_assets":[]}',
            "manifest_json_duplicate_key",
            id="nested-run",
        ),
        pytest.param(
            '{"schema_version":"web-listening-manifest.v1","manifest_id":"m",'
            '"run":{"run_id":"r"},"source":{"source_id":"s",'
            '"site_name":"S","site_url":"https://example.test"},'
            '"downloaded_assets":[{"asset_id":"a","asset_id":"duplicate"}]}',
            "manifest_json_duplicate_key",
            id="nested-asset",
        ),
    ],
)
def test_issue_320_rejects_duplicate_json_keys_at_any_depth(
    raw_text: str, expected_code: str
) -> None:
    manifest = json.loads(raw_text)
    _assert_contract_error(
        manifest,
        raw_text=raw_text,
        expected_code=expected_code,
        expected_field="json",
    )


@pytest.mark.parametrize(
    ("raw_text", "expected_code", "expected_field"),
    [
        pytest.param("{", "manifest_json_invalid", "json", id="malformed-json"),
        pytest.param(
            '{"unexpected":NaN}',
            "manifest_json_invalid",
            "json",
            id="non-json-constant",
        ),
        pytest.param("[]", "invalid_manifest_contract", "manifest", id="non-object"),
    ],
)
def test_issue_320_rejects_invalid_raw_json_before_transaction(
    raw_text: str, expected_code: str, expected_field: str
) -> None:
    _assert_contract_error(
        {},
        raw_text=raw_text,
        expected_code=expected_code,
        expected_field=expected_field,
    )


def test_issue_320_rejects_non_object_mapping_before_transaction() -> None:
    _assert_contract_error(
        [],
        expected_code="invalid_manifest_contract",
        expected_field="manifest",
    )


def test_issue_320_rejects_mapping_and_raw_text_mismatch_type_sensitively() -> None:
    manifest = _legacy_manifest()
    raw_manifest = copy.deepcopy(manifest)
    raw_manifest["downloaded_assets"][0]["bytes"] = 1
    manifest["downloaded_assets"][0]["bytes"] = True
    raw_text = json.dumps(raw_manifest)

    _assert_contract_error(
        manifest,
        raw_text=raw_text,
        expected_code="invalid_manifest_contract",
        expected_field="raw_text",
    )


def test_issue_320_valid_empty_manifest_opens_one_transaction_and_archives_raw() -> None:
    manifest = _legacy_manifest()
    manifest["downloaded_assets"] = []
    raw_text = json.dumps(manifest, separators=(",", ":"))
    storage = _StorageSpy()

    result = ingest_manifest(storage, manifest, raw_text=raw_text)

    assert result["imported"] == 0
    assert storage.transaction_calls == 1
    assert storage.saved_manifests[0]["manifest_json"] == raw_text
    assert storage.upserted_files == []


def test_issue_320_valid_asset_preserves_legacy_mapping_and_path_precedence() -> None:
    manifest = _legacy_manifest()
    asset = manifest["downloaded_assets"][0]
    asset.update(
        {
            "checksum": {"algorithm": "SHA-256", "value": "A" * 64},
            "media_type": "text/html; charset=utf-8",
            "bytes": 0,
            "canonical_blob_path": "data/blobs/report.html",
            "tracked_path": "data/tracked/report.html",
            "local_path": "data/local/report.html",
        }
    )
    storage = _StorageSpy()

    result = ingest_manifest(storage, manifest)

    assert result["imported"] == 1
    assert storage.upserted_files == [
        {
            "url": "https://example.test/report.pdf",
            "sha256": "A" * 64,
            "title": "report.pdf",
            "source_site": "Example Source",
            "source_page_url": "https://example.test/",
            "original_filename": "report.pdf",
            "local_path": "data/blobs/report.html",
            "bytes_size": 0,
            "content_type": "text/html; charset=utf-8",
            "last_modified": None,
            "etag": None,
            "published_time": None,
            "content_kind": "web_page",
        }
    ]


def test_issue_320_valid_manifest_remains_byte_exact_and_idempotent(tmp_path: Path) -> None:
    manifest = _legacy_manifest()
    raw_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    storage = Storage(str(tmp_path / "manifest.db"))
    try:
        first = ingest_manifest(storage, manifest, raw_text=raw_text)
        second = ingest_manifest(storage, manifest, raw_text=raw_text)

        assert first["imported"] == second["imported"] == 1
        assert storage._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 1
        archived = storage._conn.execute(
            "SELECT manifest_json, source_id, run_id FROM manifest_raw WHERE manifest_id = ?",
            ("manifest-320",),
        ).fetchone()
        assert tuple(archived) == (raw_text, "source-320", "run-320")
        stored = storage._conn.execute(
            "SELECT url, sha256, content_kind, local_path FROM files"
        ).fetchone()
        assert tuple(stored) == (
            "https://example.test/report.pdf",
            "a" * 64,
            "file",
            "data/files/report.pdf",
        )
    finally:
        storage.close()


def test_issue_320_unsupported_manifest_with_identity_leaves_database_unchanged(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "manifest.db"))
    payload = {
        "schema_version": "web-listening-result.v1",
        "manifest_id": "must-not-archive",
        "run": {"run_id": "must-not-run"},
        "source": {
            "source_id": "must-not-source",
            "site_name": "Must Not Write",
            "site_url": "https://example.test/",
        },
        "downloaded_assets": [],
    }
    try:
        with pytest.raises(ValueError) as exc_info:
            ingest_manifest(storage, payload)

        assert getattr(exc_info.value, "code", None) == "unsupported_manifest_contract"
        assert storage._conn.execute("SELECT COUNT(*) FROM manifest_raw").fetchone()[0] == 0
        assert storage._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
    finally:
        storage.close()


def test_issue_320_task_preflight_runs_before_storage_is_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "duplicate-secret-name.json"
    path.write_text(
        '{"schema_version":"web-listening-manifest.v1",'
        '"schema_version":"web-listening-manifest.v1"}',
        encoding="utf-8",
    )
    runtime = NativeTaskRuntime()
    runtime.set_site_config({"paths": {"db": str(tmp_path / "must-not-open.db")}})
    storage_opened = False

    def fail_if_storage_opens(_db_path: str) -> Any:
        nonlocal storage_opened
        storage_opened = True
        raise AssertionError("Storage opened before manifest preflight")

    monkeypatch.setattr("ai_actuarial.task_runtime.Storage", fail_if_storage_opens)

    with pytest.raises(ValueError) as exc_info:
        runtime._run_collection(
            "task-320-preflight",
            "manifest_ingestion",
            {"manifest_path": str(path)},
        )

    assert getattr(exc_info.value, "code", None) == "manifest_json_duplicate_key"
    assert storage_opened is False


def test_issue_320_task_valid_file_archives_original_bytes(tmp_path: Path) -> None:
    manifest = _legacy_manifest()
    manifest["downloaded_assets"] = []
    raw_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2).replace("\n", "\r\n").encode("utf-8")
        + b"\r\n"
    )
    manifest_path = tmp_path / "valid-manifest.json"
    manifest_path.write_bytes(raw_bytes)
    db_path = tmp_path / "task.db"
    runtime = NativeTaskRuntime()
    runtime.set_site_config({"paths": {"db": str(db_path)}})

    result = runtime._run_collection(
        "task-320-valid",
        "manifest_ingestion",
        {"manifest_path": str(manifest_path)},
    )

    storage = Storage(str(db_path))
    try:
        archived = storage._conn.execute(
            "SELECT manifest_json FROM manifest_raw WHERE manifest_id = ?",
            ("manifest-320",),
        ).fetchone()[0]
    finally:
        storage.close()
    assert result.success is True
    assert result.metadata["imported"] == 0
    assert archived.encode("utf-8") == raw_bytes


def test_issue_320_task_and_history_api_expose_safe_machine_readable_error(
    tmp_path: Path,
) -> None:
    secret_path = tmp_path / "signed-query-secret-cookie.json"
    secret_path.write_text(
        json.dumps(
            {
                "schema_version": "web-listening-result.v1",
                "authorization": "Bearer secret-value",
                "url": "https://example.test/?X-Amz-Signature=secret-value",
                "cookie": "session=secret-value",
            }
        ),
        encoding="utf-8",
    )
    runtime = NativeTaskRuntime()
    runtime.set_site_config({"paths": {"db": str(tmp_path / "task.db")}})
    task_id = f"task-320-error-{tmp_path.name}"
    runtime.active_tasks[task_id] = {
        "id": task_id,
        "name": "Manifest contract",
        "type": "manifest_ingestion",
        "status": "pending",
        "started_at": "2026-09-02T00:00:00",
        "errors": [],
    }

    runtime._execute_collection_task(
        task_id,
        "manifest_ingestion",
        {"manifest_path": str(secret_path)},
    )

    response = list_task_history(runtime.task_history, limit=1000)
    task = next(row for row in response["tasks"] if row["id"] == task_id)
    assert task["status"] == "error"
    assert task["error_code"] == "unsupported_manifest_contract"
    assert task["error_details"] == {"field": "schema_version"}
    rendered = json.dumps(task)
    assert "secret-value" not in rendered
    assert str(secret_path) not in rendered
    assert task["errors"] == ["unsupported_manifest_contract: schema_version"]


def test_issue_320_invalid_port_traceback_and_task_surfaces_hide_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = "credential-secret-320"
    manifest = _legacy_manifest()
    manifest["downloaded_assets"][0]["url"] = f"https://example.test:{sentinel}/report.pdf"
    storage = _StorageSpy()

    with pytest.raises(ValueError) as exc_info:
        ingest_manifest(storage, manifest)

    formatted = "".join(traceback.format_exception(exc_info.value))
    assert getattr(exc_info.value, "code", None) == "invalid_manifest_contract"
    assert getattr(exc_info.value, "field", None) == "downloaded_assets[0].url"
    assert sentinel not in formatted
    assert storage.transaction_calls == 0

    manifest_path = tmp_path / "invalid-port.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    log_path = tmp_path / "task.log"
    monkeypatch.setattr(ops_read_service.settings, "LOG_FILE", log_path)
    runtime = NativeTaskRuntime()
    runtime.task_history = []
    runtime.set_site_config({"paths": {"db": str(tmp_path / "must-not-open.db")}})
    task_id = f"task-invalid-port-{tmp_path.name}"
    runtime.active_tasks[task_id] = {
        "id": task_id,
        "name": "Invalid port manifest",
        "type": "manifest_ingestion",
        "status": "pending",
        "started_at": "2026-09-02T00:00:00",
        "errors": [],
    }

    with _capture_task_runtime_log(log_path):
        runtime._execute_collection_task(
            task_id,
            "manifest_ingestion",
            {"manifest_path": str(manifest_path)},
        )

    task = runtime.task_history[-1]
    rendered_history = json.dumps(task)
    rendered_global_log = get_global_logs(enabled=True)["logs"]
    assert task["error_code"] == "invalid_manifest_contract"
    assert task["error_details"] == {"field": "downloaded_assets[0].url"}
    assert sentinel not in rendered_history
    assert sentinel not in rendered_global_log
    assert task["errors"] == ["invalid_manifest_contract: downloaded_assets[0].url"]


def test_issue_320_read_race_traceback_and_task_surfaces_hide_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = tmp_path / "local-secret-path-320.json"
    manifest_path.write_text("{}", encoding="utf-8")
    secret_path = str(manifest_path)
    original_read_bytes = Path.read_bytes

    def fail_manifest_read(path: Path) -> bytes:
        if path == manifest_path:
            raise OSError(f"cannot read {secret_path}")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_manifest_read)
    runtime = NativeTaskRuntime()
    runtime.task_history = []
    runtime.set_site_config({"paths": {"db": str(tmp_path / "must-not-open.db")}})

    with pytest.raises(ValueError) as exc_info:
        runtime._run_collection(
            "task-read-race-direct",
            "manifest_ingestion",
            {"manifest_path": secret_path},
        )

    formatted = "".join(traceback.format_exception(exc_info.value))
    assert getattr(exc_info.value, "code", None) == "manifest_file_unavailable"
    assert secret_path not in formatted

    log_path = tmp_path / "read-race.log"
    monkeypatch.setattr(ops_read_service.settings, "LOG_FILE", log_path)
    task_id = f"task-read-race-{tmp_path.name}"
    runtime.active_tasks[task_id] = {
        "id": task_id,
        "name": "Read race manifest",
        "type": "manifest_ingestion",
        "status": "pending",
        "started_at": "2026-09-02T00:00:00",
        "errors": [],
    }

    with _capture_task_runtime_log(log_path):
        runtime._execute_collection_task(
            task_id,
            "manifest_ingestion",
            {"manifest_path": secret_path},
        )

    task = runtime.task_history[-1]
    rendered_history = json.dumps(task)
    rendered_global_log = get_global_logs(enabled=True)["logs"]
    assert task["error_code"] == "manifest_file_unavailable"
    assert task["error_details"] == {"field": "manifest_path"}
    assert secret_path not in rendered_history
    assert secret_path not in rendered_global_log


def test_issue_320_non_manifest_task_keeps_existing_exception_logging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = "ordinary-task-error-320"
    log_path = tmp_path / "ordinary-task.log"
    monkeypatch.setattr(ops_read_service.settings, "LOG_FILE", log_path)
    runtime = NativeTaskRuntime()
    runtime.task_history = []
    task_id = f"ordinary-error-{tmp_path.name}"
    runtime.active_tasks[task_id] = {
        "id": task_id,
        "name": "Ordinary task",
        "type": "file",
        "status": "pending",
        "started_at": "2026-09-02T00:00:00",
        "errors": [],
    }

    def fail_collection(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError(sentinel)

    monkeypatch.setattr(runtime, "_run_collection", fail_collection)
    with _capture_task_runtime_log(log_path):
        runtime._execute_collection_task(task_id, "file", {})

    task = runtime.task_history[-1]
    rendered_global_log = get_global_logs(enabled=True)["logs"]
    assert task["errors"] == [sentinel]
    assert "error_code" not in task
    assert sentinel in rendered_global_log
    assert "Traceback" in rendered_global_log


@pytest.mark.parametrize(
    ("manifest_path", "file_contents", "expected_code"),
    [
        pytest.param("", None, "manifest_path_required", id="missing-path"),
        pytest.param("not-present.json", None, "manifest_file_unavailable", id="missing-file"),
        pytest.param("malformed-secret.json", b"{", "manifest_json_invalid", id="malformed-json"),
    ],
)
def test_issue_320_task_file_errors_are_stable_and_do_not_echo_paths(
    tmp_path: Path,
    manifest_path: str,
    file_contents: bytes | None,
    expected_code: str,
) -> None:
    if file_contents is not None:
        (tmp_path / manifest_path).write_bytes(file_contents)
        manifest_path = str(tmp_path / manifest_path)
    runtime = NativeTaskRuntime()
    runtime.set_site_config({"paths": {"db": str(tmp_path / "task.db")}})

    with pytest.raises(ValueError) as exc_info:
        runtime._run_collection(
            "task-320-file-error",
            "manifest_ingestion",
            {"manifest_path": manifest_path},
        )

    error = exc_info.value
    assert getattr(error, "code", None) == expected_code
    if manifest_path:
        assert manifest_path not in str(error)
