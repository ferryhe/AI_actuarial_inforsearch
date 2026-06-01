from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import yaml
from cryptography.fernet import Fernet

from ai_actuarial.services.token_encryption import TokenEncryption
from ai_actuarial.storage import Storage
from ai_actuarial.task_runtime import NativeTaskRuntime
from tests.test_fastapi_ops_read_endpoints import (
    _build_test_client,
    _make_session_cookie,
    _patch_available_models,
)


def _read_sites(config_path: Path) -> list[dict[str, object]]:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return list(data.get("sites") or [])


def _read_scheduled_tasks(config_path: Path) -> list[dict[str, object]]:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return list(data.get("scheduled_tasks") or [])


def _seed_stats_data(db_path: Path) -> None:
    storage = Storage(str(db_path))
    try:
        conn = storage._conn
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE catalog_items SET markdown_content = ? WHERE file_url = ?",
            ("# markdown", "https://alpha.example/doc-a.pdf"),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO chunk_profiles (
                profile_id, name, config_hash, config_json, chunk_size, chunk_overlap,
                splitter, tokenizer, version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "profile-default",
                "Default",
                "cfg-hash",
                json.dumps({"chunk_size": 800, "chunk_overlap": 100}),
                800,
                100,
                "markdown",
                "cl100k_base",
                "v1",
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO file_chunk_sets (
                chunk_set_id, file_url, profile_id, markdown_hash, status, chunk_count,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "chunkset-1",
                "https://alpha.example/doc-a.pdf",
                "profile-default",
                "md-hash-1",
                "ready",
                2,
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        storage.close()



def _install_public_dns_resolver(monkeypatch, *hosts: str) -> None:
    def fake_getaddrinfo(host, port, type=0, proto=0, *args, **kwargs):
        if host in set(hosts):
            return [(2, type, proto, "", ("93.184.216.34", 0))]
        raise AssertionError(f"Unexpected DNS lookup in test: {host}")

    monkeypatch.setattr("ai_actuarial.security.url_safety.socket.getaddrinfo", fake_getaddrinfo)



class _BridgeRecorder:
    def __init__(self) -> None:
        self.started: list[tuple[str, dict[str, object], str | None, dict[str, object] | None]] = []
        self.reinit_calls = 0
        self.last_site_config: dict[str, object] | None = None

    def start_background_task(
        self,
        collection_type: str,
        data: dict[str, object],
        *,
        task_name: str | None = None,
        extra_fields: dict[str, object] | None = None,
    ) -> str:
        self.started.append((collection_type, dict(data), task_name, extra_fields))
        return "task-fastapi-bridge"

    def init_scheduler(self) -> None:
        self.reinit_calls += 1

    def set_site_config(self, config_data: dict[str, object]) -> None:
        self.last_site_config = dict(config_data)



def _install_bridge(app, recorder: _BridgeRecorder) -> None:
    app.state.start_background_task = recorder.start_background_task
    app.state.init_scheduler = recorder.init_scheduler
    app.state.set_site_config = recorder.set_site_config
    app.state.schedule_ref = SimpleNamespace(jobs=[object(), object()])



def test_ops_write_routes_are_listed_in_native_inventory(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    migration = client.get("/api/migration/status")
    body = migration.json()
    assert "/api/config/sites/add" in body["native_paths"]
    assert "/api/schedule/reinit" in body["native_paths"]
    assert "/api/collections/run" in body["native_paths"]



def test_config_sites_crud_import_export_and_backups_roundtrip(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    _install_public_dns_resolver(
        monkeypatch,
        "www.soa.org",
        "preview.example",
        "import.example",
        "duplicate.example",
    )
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    recorder = _BridgeRecorder()
    _install_bridge(app, recorder)
    config_path = Path(os.environ["CONFIG_PATH"])
    headers = {"X-Auth-Token": seed["operator_token"]}

    add_response = client.post(
        "/api/config/sites/add",
        json={
            "name": "SOA AI Bulletin",
            "url": "https://www.soa.org/news-and-publications/newsletters/ai-bulletin/",
            "max_pages": 25,
            "keywords": "ai, actuarial",
        },
        headers=headers,
    )
    assert add_response.status_code == 200, add_response.text
    assert any(site["name"] == "SOA AI Bulletin" for site in _read_sites(config_path))
    assert recorder.last_site_config is not None

    update_response = client.post(
        "/api/config/sites/update",
        json={
            "original_name": "SOA AI Bulletin",
            "name": "SOA AI Bulletin",
            "url": "https://www.soa.org/resources/research-reports/",
            "max_pages": 30,
            "exclude_keywords": "archive, curriculum",
        },
        headers=headers,
    )
    assert update_response.status_code == 200, update_response.text
    updated_site = next(site for site in _read_sites(config_path) if site["name"] == "SOA AI Bulletin")
    assert updated_site["url"] == "https://www.soa.org/resources/research-reports/"
    assert updated_site["exclude_keywords"] == ["archive", "curriculum"]

    preview_response = client.post(
        "/api/config/sites/import",
        json={
            "preview": True,
            "yaml_text": "sites:\n  - name: Preview Site\n    url: https://preview.example\n",
        },
        headers=headers,
    )
    assert preview_response.status_code == 200, preview_response.text
    assert preview_response.json()["count"] == 1

    import_response = client.post(
        "/api/config/sites/import",
        json={
            "mode": "merge",
            "yaml_text": (
                "sites:\n"
                "  - name: Import Site\n"
                "    url: https://import.example\n"
                "  - name: SOA AI Bulletin\n"
                "    url: https://duplicate.example\n"
            ),
        },
        headers=headers,
    )
    assert import_response.status_code == 200, import_response.text
    import_body = import_response.json()
    assert import_body["imported"] == 1
    assert import_body["skipped"] == 1

    export_response = client.get("/api/config/sites/export", headers=headers)
    assert export_response.status_code == 200
    assert "attachment; filename=sites_export_" in export_response.headers["content-disposition"]
    assert yaml.safe_load(export_response.text)["sites"]

    sample_response = client.get("/api/config/sites/sample", headers=headers)
    assert sample_response.status_code == 200
    assert "sites_sample.yaml" in sample_response.headers["content-disposition"]
    assert "Society of Actuaries (SOA)" in sample_response.text

    delete_site_response = client.post("/api/config/sites/delete", json={"name": "Import Site"}, headers=headers)
    assert delete_site_response.status_code == 200, delete_site_response.text
    assert all(site["name"] != "Import Site" for site in _read_sites(config_path))

    operator_backups_response = client.get("/api/config/backups", headers=headers)
    assert operator_backups_response.status_code == 403

    admin_headers = {"X-Auth-Token": seed["admin_token"]}
    backups_response = client.get("/api/config/backups", headers=admin_headers)
    assert backups_response.status_code == 200
    backups = backups_response.json()["backups"]
    assert backups, backups_response.text
    backup_filename = backups[0]["filename"]

    delete_backup_response = client.post("/api/config/backups/delete", json={"filename": backup_filename}, headers=admin_headers)
    assert delete_backup_response.status_code == 200, delete_backup_response.text

    restore_source = client.get("/api/config/backups", headers=admin_headers)
    restore_filename = restore_source.json()["backups"][0]["filename"]
    restore_response = client.post("/api/config/backups/restore", json={"filename": restore_filename}, headers=admin_headers)
    assert restore_response.status_code == 200, restore_response.text



def test_site_config_write_rejects_unsafe_urls(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    _install_public_dns_resolver(monkeypatch, "safe.example", "preview.example", "import.example")
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    config_path = Path(os.environ["CONFIG_PATH"])
    headers = {"X-Auth-Token": seed["operator_token"]}

    add_response = client.post(
        "/api/config/sites/add",
        json={"name": "Blocked", "url": "http://127.0.0.1/internal"},
        headers=headers,
    )
    assert add_response.status_code == 400, add_response.text
    assert "Unsafe site URL" in add_response.text

    safe_add = client.post(
        "/api/config/sites/add",
        json={"name": "Safe", "url": "https://safe.example/reports"},
        headers=headers,
    )
    assert safe_add.status_code == 200, safe_add.text

    update_response = client.post(
        "/api/config/sites/update",
        json={"original_name": "Safe", "name": "Safe", "url": "http://localhost/admin"},
        headers=headers,
    )
    assert update_response.status_code == 400, update_response.text
    safe_site = next(site for site in _read_sites(config_path) if site["name"] == "Safe")
    assert safe_site["url"] == "https://safe.example/reports"

    preview_response = client.post(
        "/api/config/sites/import",
        json={
            "preview": True,
            "yaml_text": (
                "sites:\n"
                "  - name: Preview Safe\n"
                "    url: https://preview.example\n"
                "  - name: Preview Blocked\n"
                "    url: http://127.0.0.1/hidden\n"
            ),
        },
        headers=headers,
    )
    assert preview_response.status_code == 200, preview_response.text
    assert preview_response.json()["count"] == 1

    import_response = client.post(
        "/api/config/sites/import",
        json={
            "mode": "merge",
            "yaml_text": (
                "sites:\n"
                "  - name: Import Safe\n"
                "    url: https://import.example\n"
                "  - name: Import Blocked\n"
                "    url: http://127.0.0.1/secret\n"
            ),
        },
        headers=headers,
    )
    assert import_response.status_code == 200, import_response.text
    body = import_response.json()
    assert body["imported"] == 1
    assert any("Unsafe site URL" in message for message in body.get("errors", []))
    site_names = {site["name"] for site in _read_sites(config_path)}
    assert "Import Safe" in site_names
    assert "Import Blocked" not in site_names



def test_backend_settings_write_roundtrip_is_native_fastapi(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    config_path = Path(os.environ["CONFIG_PATH"])
    headers = {"X-Auth-Token": seed["admin_token"]}

    update_response = client.post(
        "/api/config/backend-settings",
        json={
            "defaults": {
                "max_pages": 42,
                "max_depth": 3,
                "delay_seconds": 1.5,
                "file_exts": [".pdf", ".md"],
                "keywords": ["pricing", "ai"],
                "exclude_keywords": ["draft"],
                "exclude_prefixes": ["/private"],
                "schedule_interval": "weekly",
            },
            "paths": {
                "download_dir": "data/native-files",
                "updates_dir": "data/native-updates",
                "last_run_new": "data/native-last-run.json",
            },
            "search": {
                "enabled": False,
                "max_results": 9,
                "delay_seconds": 2.0,
                "languages": ["en", "zh"],
                "country": "sg",
                "exclude_keywords": ["jobs", "archive"],
                "queries": ["actuarial ai", "insurance llm"],
            },
            "features": {
                "enable_file_deletion": False,
                "require_auth": True,
                "enable_global_logs_api": True,
                "enable_rate_limiting": True,
                "enable_csrf": False,
                "enable_security_headers": False,
                "expose_error_details": True,
                "rate_limit_defaults": "100 per hour, 20 per minute",
                "rate_limit_storage_uri": "memory://",
                "content_security_policy": "default-src 'self'",
            },
        },
        headers=headers,
    )
    assert update_response.status_code == 200, update_response.text
    body = update_response.json()
    assert body["success"] is True
    assert body["defaults"]["max_pages"] == 42
    assert body["search"]["enabled"] is False
    assert body["runtime"]["file_deletion_enabled"] is False
    assert body["runtime"]["require_auth"] is True
    assert body["runtime"]["enable_global_logs_api"] is True
    assert body["runtime"]["enable_rate_limiting"] is True
    assert body["runtime"]["enable_security_headers"] is False
    assert body["runtime"]["expose_error_details"] is True
    assert body["runtime"]["rate_limit_defaults"] == "100 per hour, 20 per minute"
    assert app.state.require_auth is True
    assert app.state.enable_global_logs_api is True
    assert app.state.enable_rate_limiting is True
    assert app.state.enable_security_headers is False
    assert app.state.expose_error_details is True
    assert app.state.rate_limit_defaults == "100 per hour, 20 per minute"
    assert app.state.rate_limit_storage_uri == "memory://"

    written = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    assert written["defaults"]["max_pages"] == 42
    assert written["paths"]["download_dir"] == "data/native-files"
    assert written["search"]["queries"] == ["actuarial ai", "insurance llm"]
    assert written["features"]["enable_file_deletion"] is False
    assert written["features"]["require_auth"] is True
    assert written["features"]["enable_global_logs_api"] is True
    assert written["features"]["enable_rate_limiting"] is True
    assert written["features"]["enable_security_headers"] is False
    assert written["features"]["expose_error_details"] is True
    assert written["features"]["content_security_policy"] == "default-src 'self'"
    assert "file_deletion_enabled" not in (written.get("system") or {})



def test_categories_and_ai_models_write_roundtrip_is_native_fastapi(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    nested_categories_path = tmp_path / "nested" / "config" / "categories.yaml"
    monkeypatch.setenv("CATEGORIES_CONFIG_PATH", str(nested_categories_path))
    config_path = Path(os.environ["CONFIG_PATH"])
    categories_path = nested_categories_path
    headers = {"X-Auth-Token": seed["admin_token"]}

    categories_response = client.post(
        "/api/config/categories",
        json={
            "categories": {
                "AI Governance": ["governance", "policy"],
                "Pricing": ["pricing", "reserve"],
            },
            "ai_filter_keywords": ["artificial intelligence", "large language model"],
            "ai_keywords": ["artificial intelligence", "large language model"],
        },
        headers=headers,
    )
    assert categories_response.status_code == 200, categories_response.text
    categories_body = categories_response.json()
    assert categories_body["success"] is True
    assert categories_body["categories"]["AI Governance"] == ["governance", "policy"]
    assert categories_body["ai_filter_keywords"] == ["artificial intelligence", "large language model"]
    assert categories_body["ai_keywords"] == ["artificial intelligence", "large language model"]

    written_categories = yaml.safe_load(categories_path.read_text(encoding="utf-8")) or {}
    assert written_categories["categories"]["Pricing"] == ["pricing", "reserve"]
    assert written_categories["ai_filter_keywords"] == ["artificial intelligence", "large language model"]
    assert written_categories["ai_keywords"] == ["artificial intelligence", "large language model"]

    ai_models_response = client.post(
        "/api/config/ai-models",
        json={
            "catalog": {"system_prompt": "native catalog prompt"},
            "chatbot": {
                "prompts": {"expert": "native expert prompt", "summary": "native summary prompt"},
                "summarization_prompt": "native summarize prompt",
            },
        },
        headers=headers,
    )
    assert ai_models_response.status_code == 200, ai_models_response.text
    ai_models_body = ai_models_response.json()
    assert ai_models_body["success"] is True
    assert ai_models_body["current"]["catalog"]["system_prompt"] == "native catalog prompt"
    assert ai_models_body["current"]["chatbot"]["prompts"]["expert"] == "native expert prompt"
    assert ai_models_body["current"]["chatbot"]["summarization_prompt"] == "native summarize prompt"

    written_config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    assert written_config["ai_config"]["catalog"]["system_prompt"] == "native catalog prompt"
    assert written_config["ai_config"]["chatbot"]["prompts"]["summary"] == "native summary prompt"
    assert written_config["ai_config"]["chatbot"]["summarization_prompt"] == "native summarize prompt"



def test_scheduled_tasks_write_and_schedule_reinit_roundtrip(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    recorder = _BridgeRecorder()
    _install_bridge(app, recorder)
    config_path = Path(os.environ["CONFIG_PATH"])
    headers = {"X-Auth-Token": seed["operator_token"]}

    for invalid_interval in ("every 5 hourly", "every 1 hours extra", "every 0 hours"):
        invalid_response = client.post(
            "/api/scheduled-tasks/add",
            json={
                "name": f"Invalid {invalid_interval}",
                "type": "chunk_generation",
                "interval": invalid_interval,
                "enabled": True,
                "params": {},
            },
            headers=headers,
        )
        assert invalid_response.status_code == 400, invalid_response.text
        assert "Invalid schedule interval" in invalid_response.text

    file_schedule_response = client.post(
        "/api/scheduled-tasks/add",
        json={
            "name": "Legacy File Schedule",
            "type": "file",
            "interval": "daily",
            "enabled": True,
            "params": {"directory_path": "/tmp"},
        },
        headers=headers,
    )
    assert file_schedule_response.status_code == 400, file_schedule_response.text
    assert "Invalid task type: file" in file_schedule_response.text

    add_response = client.post(
        "/api/scheduled-tasks/add",
        json={
            "name": "Weekly Chunk",
            "type": "chunk_generation",
            "interval": "daily at 02:00",
            "enabled": True,
            "params": {"category": "AI"},
        },
        headers=headers,
    )
    assert add_response.status_code == 200, add_response.text
    written_task = next(task for task in _read_scheduled_tasks(config_path) if task["name"] == "Weekly Chunk")
    assert written_task["interval"] == "daily at 02:00"

    update_response = client.post(
        "/api/scheduled-tasks/update",
        json={
            "original_name": "Weekly Chunk",
            "name": "Weekly Chunk",
            "type": "chunk_generation",
            "interval": "daily",
            "enabled": False,
            "params": {"category": "Pricing"},
        },
        headers=headers,
    )
    assert update_response.status_code == 200, update_response.text
    updated_task = next(task for task in _read_scheduled_tasks(config_path) if task["name"] == "Weekly Chunk")
    assert updated_task["interval"] == "daily"
    assert updated_task["enabled"] is False

    reinit_response = client.post("/api/schedule/reinit", headers=headers)
    assert reinit_response.status_code == 200, reinit_response.text
    assert reinit_response.json()["job_count"] == 2
    assert recorder.reinit_calls == 1

    delete_response = client.post("/api/scheduled-tasks/delete", json={"name": "Weekly Chunk"}, headers=headers)
    assert delete_response.status_code == 200, delete_response.text
    assert all(task["name"] != "Weekly Chunk" for task in _read_scheduled_tasks(config_path))



def test_browse_folder_and_stats_endpoints_return_real_values(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    recorder = _BridgeRecorder()
    _install_bridge(app, recorder)
    db_path = Path(app.state.db_path)
    _seed_stats_data(db_path)
    headers = {"X-Auth-Token": str(seed["admin_token"])}
    operator_headers = {"X-Auth-Token": str(seed["operator_token"])}

    allowed_root = tmp_path / "files"
    nested = allowed_root / "nested"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "sample.pdf").write_text("pdf", encoding="utf-8")

    browse_response = client.get(f"/api/utils/browse-folder?path={nested}", headers=headers)
    assert browse_response.status_code == 200, browse_response.text
    browse_body = browse_response.json()
    assert browse_body["path"] == str(nested.resolve())
    assert any(entry["name"] == "sample.pdf" for entry in browse_body["entries"])

    denied_response = client.get("/api/utils/browse-folder", params={"path": str(Path("/").resolve())}, headers=headers)
    assert denied_response.status_code == 403, denied_response.text

    operator_browse = client.get(f"/api/utils/browse-folder?path={nested}", headers=operator_headers)
    assert operator_browse.status_code == 403

    catalog_stats = client.get("/api/catalog/stats", headers=headers)
    assert catalog_stats.status_code == 200, catalog_stats.text
    assert catalog_stats.json()["total_local_files"] >= 1

    markdown_stats = client.get("/api/markdown_conversion/stats", headers=headers)
    assert markdown_stats.status_code == 200, markdown_stats.text
    assert markdown_stats.json()["total_convertible"] >= 1
    assert markdown_stats.json()["total_with_markdown"] >= 1

    chunk_stats = client.get("/api/chunk_generation/stats", headers=headers)
    assert chunk_stats.status_code == 200, chunk_stats.text
    assert chunk_stats.json()["total_with_markdown"] >= 1
    assert chunk_stats.json()["total_with_chunks"] >= 1



def test_upload_batch_then_run_file_collection_uses_batch_not_server_path(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    recorder = _BridgeRecorder()
    _install_bridge(app, recorder)
    headers = {"X-Auth-Token": seed["operator_token"]}

    active_tasks = {
        "task-live": {
            "id": "task-live",
            "name": "Live Task",
            "type": "file",
            "status": "running",
            "current_activity": "working",
        }
    }
    app.state.active_tasks_ref = active_tasks

    stop_response = client.post("/api/tasks/stop/task-live", headers=headers)
    assert stop_response.status_code == 200, stop_response.text
    assert active_tasks["task-live"]["stop_requested"] is True

    server_path_response = client.post("/api/collections/run", json={"type": "file", "directory_path": "/does/not/exist"}, headers=headers)
    assert server_path_response.status_code == 403

    admin_server_path_response = client.post(
        "/api/collections/run",
        json={"type": "file", "directory_path": "/does/not/exist"},
        headers={"X-Auth-Token": str(seed["admin_token"])},
    )
    assert admin_server_path_response.status_code == 400
    assert admin_server_path_response.json()["error"] == "File imports must use an upload batch"

    upload_response = client.post(
        "/api/files/import-batches",
        data={"relative_paths": ["reports/bulletin.pdf", "reports/notes.txt", "books/manual.epub"]},
        files=[
            ("files", ("bulletin.pdf", b"fake pdf", "application/pdf")),
            ("files", ("notes.txt", b"side note", "text/plain")),
            ("files", ("manual.epub", b"fake epub", "application/epub+zip")),
        ],
        headers=headers,
    )
    assert upload_response.status_code == 201, upload_response.text
    upload_body = upload_response.json()
    assert upload_body["success"] is True
    assert upload_body["file_count"] == 3
    assert upload_body["total_bytes"] == len(b"fake pdf") + len(b"side note") + len(b"fake epub")
    assert [item["relative_path"] for item in upload_body["files"]] == ["reports/bulletin.pdf", "reports/notes.txt", "books/manual.epub"]
    assert all("stored_path" not in item for item in upload_body["files"])
    batch_id = upload_body["upload_batch_id"]
    runtime_paths = NativeTaskRuntime()._collect_file_paths({"upload_batch_id": batch_id, "extensions": ["pdf"]})
    assert [Path(path).name for path in runtime_paths] == ["bulletin.pdf"]

    run_response = client.post(
        "/api/collections/run",
        json={
            "type": "file",
            "name": "Import PDFs",
            "upload_batch_id": batch_id,
            "directory_path": "/stale/legacy/path",
        },
        headers=headers,
    )
    assert run_response.status_code == 200, run_response.text
    run_body = run_response.json()
    assert run_body["success"] is True
    assert run_body["job_id"] == "task-fastapi-bridge"
    assert recorder.started[-1][0] == "file"
    assert recorder.started[-1][1]["upload_batch_id"] == batch_id
    assert "directory_path" not in recorder.started[-1][1]


def test_import_batch_rejects_readers_and_path_traversal(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, _app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)

    reader_response = client.post(
        "/api/files/import-batches",
        data={"relative_paths": ["bulletin.pdf"]},
        files={"files": ("bulletin.pdf", b"fake pdf", "application/pdf")},
        headers={"Authorization": f"Bearer {seed['reader_token']}"},
    )
    assert reader_response.status_code == 403

    traversal_response = client.post(
        "/api/files/import-batches",
        data={"relative_paths": ["../escape.pdf"]},
        files={"files": ("escape.pdf", b"fake pdf", "application/pdf")},
        headers={"X-Auth-Token": seed["operator_token"]},
    )
    assert traversal_response.status_code == 400
    assert traversal_response.json()["error"] == "Invalid relative path"

    unsupported_response = client.post(
        "/api/files/import-batches",
        data={"relative_paths": ["malware.exe"]},
        files={"files": ("malware.exe", b"fake exe", "application/octet-stream")},
        headers={"X-Auth-Token": seed["operator_token"]},
    )
    assert unsupported_response.status_code == 400
    assert unsupported_response.json()["error"] == "Unsupported file type"



def test_schedule_reinit_and_file_collection_work_with_native_bridge(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    headers = {"X-Auth-Token": seed["operator_token"]}

    reinit_response = client.post("/api/schedule/reinit", headers=headers)
    assert reinit_response.status_code == 200, reinit_response.text
    assert reinit_response.json()["job_count"] >= 1

    upload_response = client.post(
        "/api/files/import-batches",
        data={"relative_paths": ["native.pdf"]},
        files={"files": ("native.pdf", b"fake pdf", "application/pdf")},
        headers=headers,
    )
    assert upload_response.status_code == 201, upload_response.text

    run_response = client.post(
        "/api/collections/run",
        json={
            "type": "file",
            "name": "Native Import",
            "upload_batch_id": upload_response.json()["upload_batch_id"],
            "extensions": ["pdf"],
        },
        headers=headers,
    )
    assert run_response.status_code == 200, run_response.text
    run_body = run_response.json()
    assert run_body["success"] is True
    assert run_body["job_id"].startswith("task_")



def test_ops_write_routes_require_operator_when_auth_enabled(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    _install_public_dns_resolver(monkeypatch, "blocked.example", "allowed.example")
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    recorder = _BridgeRecorder()
    _install_bridge(app, recorder)

    unauthorized = client.post("/api/config/sites/add", json={"name": "Blocked", "url": "https://blocked.example"})
    assert unauthorized.status_code == 401

    reader = client.post(
        "/api/config/sites/add",
        json={"name": "Blocked", "url": "https://blocked.example"},
        headers={"Authorization": f"Bearer {seed['reader_token']}"},
    )
    assert reader.status_code == 403

    cookie_name = app.state.fastapi_session_cookie_name
    operator_cookie = _make_session_cookie(
        app,
        {"email_user_id": seed["operator_user_id"]},
    )
    client.cookies.set(cookie_name, operator_cookie)
    operator = client.post(
        "/api/config/sites/add",
        json={"name": "Allowed Site", "url": "https://allowed.example"},
    )
    assert operator.status_code == 200, operator.text

    operator_config_write = client.post("/api/config/backend-settings", json={"defaults": {"max_pages": 12}})
    assert operator_config_write.status_code == 403



def test_ai_provider_credentials_and_routing_write_endpoints_roundtrip(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    recorder = _BridgeRecorder()
    _install_bridge(app, recorder)
    headers = {"X-Auth-Token": seed["admin_token"]}

    credential_upsert = client.post(
        "/api/config/provider-credentials",
        json={
            "provider_id": "mistral",
            "instance_id": "primary",
            "label": "Mistral Primary",
            "api_key": "***",
            "api_base_url": "https://api.mistral.ai/v1",
        },
        headers=headers,
    )
    assert credential_upsert.status_code == 200, credential_upsert.text
    assert credential_upsert.json()["stable_credential_id"] == "mistral:llm:instance:primary"
    backup_upsert = client.post(
        "/api/config/provider-credentials",
        json={
            "provider_id": "mistral",
            "instance_id": "backup",
            "label": "Mistral Backup",
            "api_key": "***",
            "api_base_url": "https://backup.mistral.ai/v1",
            "is_default": False,
        },
        headers=headers,
    )
    assert backup_upsert.status_code == 200, backup_upsert.text
    backup_credential_id = backup_upsert.json()["credential_id"]
    backup_stable_credential_id = backup_upsert.json()["stable_credential_id"]
    assert backup_stable_credential_id == "mistral:llm:instance:backup"
    credentials = client.get("/api/config/provider-credentials", headers=headers)
    rows = credentials.json()["credentials"]
    assert any(row["provider_id"] == "mistral" and row["instance_id"] == "primary" and row["source"] == "db" for row in rows)
    assert any(row["provider_id"] == "mistral" and row["instance_id"] == "backup" and row["source"] == "db" for row in rows)

    routing_update = client.post(
        "/api/config/ai-routing",
        json={
            "bindings": [
                {"function_name": "chat", "provider": "openai", "model": "gpt-4o-mini"},
                {"function_name": "embeddings", "provider": "openai", "model": "text-embedding-3-small"},
                {"function_name": "catalog", "provider": "mistral", "credential_id": backup_stable_credential_id, "model": "mistral-small-latest"},
            ]
        },
        headers=headers,
    )
    assert routing_update.status_code == 200, routing_update.text
    routing_body = routing_update.json()
    assert routing_body["success"] is True
    assert routing_body["rebuild_required"] is True
    assert routing_body["affected_kb_count"] == 0
    assert routing_body["affected_kb_ids"] == []
    bindings = {item["function_name"]: item for item in routing_body["bindings"]}
    assert bindings["chat"]["model"] == "gpt-4o-mini"
    assert bindings["embeddings"]["model"] == "text-embedding-3-small"
    assert bindings["embeddings"]["embedding_fingerprint"].startswith("openai:text-embedding-3-small:")
    assert bindings["catalog"]["provider"] == "mistral"
    assert bindings["catalog"]["credential_id"] == backup_credential_id
    assert bindings["catalog"]["stable_credential_id"] == backup_stable_credential_id
    assert bindings["catalog"]["configured"] is True
    assert bindings["catalog"]["credential_error"] is None

    invalid_routing_update = client.post(
        "/api/config/ai-routing",
        json={
            "bindings": [
                {
                    "function_name": "catalog",
                    "provider": "openai",
                    "credential_id": backup_stable_credential_id,
                    "model": "gpt-4o-mini",
                },
            ]
        },
        headers=headers,
    )
    assert invalid_routing_update.status_code == 400

    credential_delete = client.delete("/api/config/provider-credentials/mistral?instance_id=backup", headers=headers)
    assert credential_delete.status_code == 200, credential_delete.text
    remaining = client.get("/api/config/provider-credentials", headers=headers).json()["credentials"]
    assert any(row["provider_id"] == "mistral" and row["instance_id"] == "primary" and row["source"] == "db" for row in remaining)
    assert not any(row["provider_id"] == "mistral" and row["instance_id"] == "backup" and row["source"] == "db" for row in remaining)


def test_ai_routing_embedding_change_marks_existing_kbs_for_chat_reindex(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    headers = {"X-Auth-Token": seed["admin_token"]}
    alpha_url = "https://alpha.example/doc-a.pdf"

    create_kb = client.post(
        "/api/rag/knowledge-bases",
        json={"kb_id": "kb-embedding-route-change", "name": "Embedding Route Change", "kb_mode": "manual"},
        headers=headers,
    )
    assert create_kb.status_code == 201, create_kb.text

    add_file = client.post(
        "/api/rag/knowledge-bases/kb-embedding-route-change/files",
        json={"file_urls": [alpha_url]},
        headers=headers,
    )
    assert add_file.status_code == 200, add_file.text

    built_at = "2026-05-01T00:00:00+00:00"
    storage = Storage(str(app.state.db_path))
    try:
        storage.create_kb_index_version(
            kb_id="kb-embedding-route-change",
            embedding_provider="openai",
            embedding_model="text-embedding-3-large",
            embedding_dimension=3072,
            index_type="Flat",
            status="ready",
            chunk_count=1,
            built_at=built_at,
        )
        storage._conn.execute(
            "UPDATE rag_kb_files SET indexed_at = ? WHERE kb_id = ? AND file_url = ?",
            (built_at, "kb-embedding-route-change", alpha_url),
        )
        storage._conn.execute(
            "UPDATE rag_knowledge_bases SET chunk_count = 1, index_dirty_at = NULL WHERE kb_id = ?",
            ("kb-embedding-route-change",),
        )
        storage._conn.commit()
    finally:
        storage.close()

    routing_update = client.post(
        "/api/config/ai-routing",
        json={
            "bindings": [
                {"function_name": "embeddings", "provider": "openai", "model": "text-embedding-3-small"},
            ]
        },
        headers=headers,
    )
    assert routing_update.status_code == 200, routing_update.text
    routing_body = routing_update.json()
    assert routing_body["rebuild_required"] is True
    assert routing_body["affected_kb_count"] == 1
    assert routing_body["affected_kb_ids"] == ["kb-embedding-route-change"]

    chat_kbs = client.get("/api/chat/knowledge-bases", headers=headers)
    assert chat_kbs.status_code == 200, chat_kbs.text
    kb = next(item for item in chat_kbs.json()["data"]["knowledge_bases"] if item["kb_id"] == "kb-embedding-route-change")
    assert kb["embedding_compatible"] is False
    assert kb["needs_reindex"] is True
    assert kb["availability"] == "needs_reindex"
    assert kb["usable"] is False


def test_ai_routing_embedding_model_selection_persists_model_defaults(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, _app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    headers = {"X-Auth-Token": seed["admin_token"]}

    routing_update = client.post(
        "/api/config/ai-routing",
        json={
            "bindings": [
                {
                    "function_name": "embeddings",
                    "provider": "qwen",
                    "model": "text-embedding-v3",
                    "batch_size": 64,
                    "similarity_threshold": 0.4,
                },
            ]
        },
        headers=headers,
    )

    assert routing_update.status_code == 200, routing_update.text
    embeddings_binding = next(item for item in routing_update.json()["bindings"] if item["function_name"] == "embeddings")
    assert embeddings_binding["embedding_batch_size_default"] == 10
    assert embeddings_binding["similarity_threshold_default"] == 0.02

    config_data = yaml.safe_load(Path(os.environ["CONFIG_PATH"]).read_text(encoding="utf-8"))
    embeddings_config = config_data["ai_config"]["embeddings"]
    assert embeddings_config["provider"] == "qwen"
    assert embeddings_config["model"] == "text-embedding-v3"
    assert embeddings_config["batch_size"] == 10
    assert embeddings_config["similarity_threshold"] == 0.02


def test_ai_routing_embedding_credential_update_preserves_existing_runtime_knobs(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, _app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    headers = {"X-Auth-Token": seed["admin_token"]}

    primary = client.post(
        "/api/config/provider-credentials",
        json={
            "provider_id": "qwen",
            "instance_id": "primary",
            "label": "Qwen Primary",
            "api_key": "***",
            "api_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        },
        headers=headers,
    )
    assert primary.status_code == 200, primary.text
    backup = client.post(
        "/api/config/provider-credentials",
        json={
            "provider_id": "qwen",
            "instance_id": "backup",
            "label": "Qwen Backup",
            "api_key": "***",
            "api_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        },
        headers=headers,
    )
    assert backup.status_code == 200, backup.text

    config_path = Path(os.environ["CONFIG_PATH"])
    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config_data.setdefault("ai_config", {})["embeddings"] = {
        "provider": "qwen",
        "credential_id": primary.json()["stable_credential_id"],
        "model": "text-embedding-v3",
        "batch_size": 7,
        "similarity_threshold": 0.03,
    }
    config_path.write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")

    routing_update = client.post(
        "/api/config/ai-routing",
        json={
            "bindings": [
                {
                    "function_name": "embeddings",
                    "provider": "qwen",
                    "credential_id": backup.json()["stable_credential_id"],
                    "model": "text-embedding-v3",
                },
            ]
        },
        headers=headers,
    )

    assert routing_update.status_code == 200, routing_update.text
    assert routing_update.json().get("rebuild_required") is not True
    embeddings_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))["ai_config"]["embeddings"]
    assert embeddings_config["credential_id"] == backup.json()["stable_credential_id"]
    assert embeddings_config["batch_size"] == 7
    assert embeddings_config["similarity_threshold"] == 0.03


def test_ai_routing_embedding_credential_only_update_preserves_runtime_knobs(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, _app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    headers = {"X-Auth-Token": seed["admin_token"]}

    backup = client.post(
        "/api/config/provider-credentials",
        json={
            "provider_id": "qwen",
            "instance_id": "backup",
            "label": "Qwen Backup",
            "api_key": "***",
            "api_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        },
        headers=headers,
    )
    assert backup.status_code == 200, backup.text

    config_path = Path(os.environ["CONFIG_PATH"])
    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config_data.setdefault("ai_config", {})["embeddings"] = {
        "provider": "qwen",
        "model": "text-embedding-v3",
        "batch_size": 7,
        "similarity_threshold": 0.03,
    }
    config_path.write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")

    routing_update = client.post(
        "/api/config/ai-routing",
        json={"bindings": [{"function_name": "embeddings", "credential_id": backup.json()["stable_credential_id"]}]},
        headers=headers,
    )

    assert routing_update.status_code == 200, routing_update.text
    assert routing_update.json().get("rebuild_required") is not True
    embeddings_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))["ai_config"]["embeddings"]
    assert embeddings_config["credential_id"] == backup.json()["stable_credential_id"]
    assert embeddings_config["batch_size"] == 7
    assert embeddings_config["similarity_threshold"] == 0.03


def test_ai_routing_embedding_same_model_payload_ignores_request_runtime_knobs(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, _app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    headers = {"X-Auth-Token": seed["admin_token"]}
    config_path = Path(os.environ["CONFIG_PATH"])
    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config_data.setdefault("ai_config", {})["embeddings"] = {
        "provider": "qwen",
        "model": "text-embedding-v3",
        "batch_size": 7,
        "similarity_threshold": 0.03,
    }
    config_path.write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")

    routing_update = client.post(
        "/api/config/ai-routing",
        json={
            "bindings": [
                {
                    "function_name": "embeddings",
                    "provider": "qwen",
                    "model": "text-embedding-v3",
                    "batch_size": 64,
                    "similarity_threshold": 0.4,
                },
            ]
        },
        headers=headers,
    )

    assert routing_update.status_code == 200, routing_update.text
    embeddings_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))["ai_config"]["embeddings"]
    assert embeddings_config["batch_size"] == 7
    assert embeddings_config["similarity_threshold"] == 0.03


def test_ai_routing_embedding_model_change_overwrites_stale_yaml_values(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, _app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    headers = {"X-Auth-Token": seed["admin_token"]}
    config_path = Path(os.environ["CONFIG_PATH"])
    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config_data.setdefault("ai_config", {})["embeddings"] = {
        "provider": "openai",
        "model": "text-embedding-3-large",
        "batch_size": 64,
        "similarity_threshold": 0.4,
    }
    config_path.write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")

    routing_update = client.post(
        "/api/config/ai-routing",
        json={
            "bindings": [
                {"function_name": "embeddings", "provider": "qwen", "model": "text-embedding-v3"},
            ]
        },
        headers=headers,
    )

    assert routing_update.status_code == 200, routing_update.text
    embeddings_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))["ai_config"]["embeddings"]
    assert embeddings_config["provider"] == "qwen"
    assert embeddings_config["model"] == "text-embedding-v3"
    assert embeddings_config["batch_size"] == 10
    assert embeddings_config["similarity_threshold"] == 0.02


def test_ai_routing_embedding_provider_change_requires_model(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, _app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    headers = {"X-Auth-Token": seed["admin_token"]}
    config_path = Path(os.environ["CONFIG_PATH"])
    config_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config_data.setdefault("ai_config", {})["embeddings"] = {
        "provider": "openai",
        "model": "text-embedding-3-large",
        "batch_size": 64,
        "similarity_threshold": 0.4,
    }
    config_path.write_text(yaml.safe_dump(config_data, sort_keys=False), encoding="utf-8")

    routing_update = client.post(
        "/api/config/ai-routing",
        json={"bindings": [{"function_name": "embeddings", "provider": "qwen"}]},
        headers=headers,
    )

    assert routing_update.status_code == 400
    assert "Model is required when changing embeddings provider" in routing_update.text
    embeddings_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))["ai_config"]["embeddings"]
    assert embeddings_config["provider"] == "openai"
    assert embeddings_config["model"] == "text-embedding-3-large"
    assert embeddings_config["batch_size"] == 64
    assert embeddings_config["similarity_threshold"] == 0.4


def test_ai_routing_provider_change_clears_stale_credential_binding(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    recorder = _BridgeRecorder()
    _install_bridge(app, recorder)
    headers = {"X-Auth-Token": seed["admin_token"]}

    mistral = client.post(
        "/api/config/provider-credentials",
        json={
            "provider_id": "mistral",
            "instance_id": "primary",
            "label": "Mistral Primary",
            "api_key": "***",
            "api_base_url": "https://api.mistral.ai/v1",
        },
        headers=headers,
    )
    assert mistral.status_code == 200, mistral.text
    mistral_credential_id = mistral.json()["stable_credential_id"]

    first_update = client.post(
        "/api/config/ai-routing",
        json={
            "bindings": [
                {"function_name": "catalog", "provider": "mistral", "credential_id": mistral_credential_id, "model": "mistral-small-latest"},
            ]
        },
        headers=headers,
    )
    assert first_update.status_code == 200, first_update.text

    second_update = client.post(
        "/api/config/ai-routing",
        json={
            "bindings": [
                {"function_name": "catalog", "provider": "openai", "model": "gpt-4o-mini"},
            ]
        },
        headers=headers,
    )
    assert second_update.status_code == 200, second_update.text
    catalog_binding = next(item for item in second_update.json()["bindings"] if item["function_name"] == "catalog")
    assert catalog_binding["provider"] == "openai"
    assert catalog_binding.get("credential_id") in (None, "openai:llm:env") or str(catalog_binding.get("credential_id", "")).startswith("openai:")


def test_ai_routing_rejects_models_for_wrong_capability(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, _app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    headers = {"X-Auth-Token": seed["admin_token"]}

    chat_with_embedding_model = client.post(
        "/api/config/ai-routing",
        json={
            "bindings": [
                {"function_name": "chat", "provider": "openai", "model": "text-embedding-3-large"},
            ]
        },
        headers=headers,
    )
    assert chat_with_embedding_model.status_code == 400
    assert "does not support chat" in chat_with_embedding_model.text

    embeddings_with_chat_model = client.post(
        "/api/config/ai-routing",
        json={
            "bindings": [
                {"function_name": "embeddings", "provider": "openai", "model": "gpt-4o-mini"},
            ]
        },
        headers=headers,
    )
    assert embeddings_with_chat_model.status_code == 400
    assert "does not support embeddings" in embeddings_with_chat_model.text


def test_provider_credentials_import_env_bootstraps_default_instance(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    TokenEncryption._instance = None
    monkeypatch.setenv("MISTRAL_API_KEY", "env-mistral-key")
    monkeypatch.setenv("MISTRAL_BASE_URL", "https://env.mistral.example/v1")
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    recorder = _BridgeRecorder()
    _install_bridge(app, recorder)
    headers = {"X-Auth-Token": seed["admin_token"]}

    response = client.post(
        "/api/config/provider-credentials/import-env",
        json={"providers": ["mistral"]},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["imported_count"] == 1
    assert body["skipped_count"] == 0
    assert body["imported"][0]["provider_id"] == "mistral"

    rows = client.get("/api/config/provider-credentials", headers=headers).json()["credentials"]
    imported = next(row for row in rows if row["provider_id"] == "mistral" and row["source"] == "db")
    assert imported["instance_id"] == "default"
    assert imported["stable_credential_id"] == "mistral:llm:instance:default"
    assert imported["is_default"] is True
    assert imported["api_base_url"] == "https://env.mistral.example/v1"
    TokenEncryption._instance = None



def test_provider_credentials_reencrypt_rotates_ciphertext(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()
    TokenEncryption._instance = None
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    recorder = _BridgeRecorder()
    _install_bridge(app, recorder)
    headers = {"X-Auth-Token": seed["admin_token"]}
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", old_key)
    TokenEncryption._instance = None

    create = client.post(
        "/api/config/provider-credentials",
        json={
            "provider_id": "mistral",
            "instance_id": "default",
            "label": "Mistral Default",
            "api_key": "rotate-me",
            "api_base_url": "https://api.mistral.ai/v1",
        },
        headers=headers,
    )
    assert create.status_code == 200, create.text

    storage = Storage(str(app.state.db_path))
    try:
        before = storage.get_llm_provider("mistral", category="llm", instance_id="default")
        before_cipher = str(before["api_key_encrypted"])
    finally:
        storage.close()

    rotate = client.post(
        "/api/config/provider-credentials/re-encrypt",
        json={"old_key": old_key, "new_key": new_key, "category": "llm", "providers": ["mistral"]},
        headers=headers,
    )
    assert rotate.status_code == 200, rotate.text
    rotate_body = rotate.json()
    assert rotate_body["success"] is True
    assert rotate_body["rotated_count"] >= 1
    assert rotate_body["failed_count"] == 0

    storage = Storage(str(app.state.db_path))
    try:
        after = storage.get_llm_provider("mistral", category="llm", instance_id="default")
        after_cipher = str(after["api_key_encrypted"])
    finally:
        storage.close()

    assert before_cipher != after_cipher
    assert Fernet(new_key.encode()).decrypt(after_cipher.encode()).decode() == "rotate-me"
    TokenEncryption._instance = None



def test_optional_api_key_provider_and_chatbot_alias_routing_write_endpoints(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    recorder = _BridgeRecorder()
    _install_bridge(app, recorder)
    headers = {"X-Auth-Token": seed["admin_token"]}

    credential_upsert = client.post(
        "/api/config/provider-credentials",
        json={
            "provider_id": "vllm",
            "api_key": "",
            "api_base_url": "http://localhost:8001/v1",
        },
        headers=headers,
    )
    assert credential_upsert.status_code == 200, credential_upsert.text
    rows = client.get("/api/config/provider-credentials", headers=headers).json()["credentials"]
    assert any(row["provider_id"] == "vllm" and row["source"] == "db" for row in rows)

    routing_update = client.post(
        "/api/config/ai-routing",
        json={
            "bindings": [
                {"function_name": "chatbot", "provider": "openai", "model": "gpt-4o-mini", "temperature": 0.2},
            ]
        },
        headers=headers,
    )
    assert routing_update.status_code == 200, routing_update.text

    config_data = yaml.safe_load((tmp_path / "sites.yaml").read_text(encoding="utf-8")) or {}
    assert config_data["ai_config"]["chatbot"]["provider"] == "openai"
    assert config_data["ai_config"]["chatbot"]["model"] == "gpt-4o-mini"
    assert config_data["ai_config"]["chatbot"]["temperature"] == 0.2
