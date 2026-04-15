from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import yaml

from ai_actuarial.storage import Storage
from test_fastapi_ops_read_endpoints import (
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
    app.state.legacy_start_background_task = recorder.start_background_task
    app.state.legacy_init_scheduler = recorder.init_scheduler
    app.state.legacy_set_site_config = recorder.set_site_config
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
    client, app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    recorder = _BridgeRecorder()
    _install_bridge(app, recorder)
    config_path = Path(os.environ["CONFIG_PATH"])

    add_response = client.post(
        "/api/config/sites/add",
        json={
            "name": "SOA AI Bulletin",
            "url": "https://www.soa.org/news-and-publications/newsletters/ai-bulletin/",
            "max_pages": 25,
            "keywords": "ai, actuarial",
        },
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
    )
    assert import_response.status_code == 200, import_response.text
    import_body = import_response.json()
    assert import_body["imported"] == 1
    assert import_body["skipped"] == 1

    export_response = client.get("/api/config/sites/export")
    assert export_response.status_code == 200
    assert "attachment; filename=sites_export_" in export_response.headers["content-disposition"]
    assert yaml.safe_load(export_response.text)["sites"]

    sample_response = client.get("/api/config/sites/sample")
    assert sample_response.status_code == 200
    assert "sites_sample.yaml" in sample_response.headers["content-disposition"]
    assert "Society of Actuaries (SOA)" in sample_response.text

    delete_site_response = client.post("/api/config/sites/delete", json={"name": "Import Site"})
    assert delete_site_response.status_code == 200, delete_site_response.text
    assert all(site["name"] != "Import Site" for site in _read_sites(config_path))

    backups_response = client.get("/api/config/backups")
    assert backups_response.status_code == 200
    backups = backups_response.json()["backups"]
    assert backups, backups_response.text
    backup_filename = backups[0]["filename"]

    delete_backup_response = client.post("/api/config/backups/delete", json={"filename": backup_filename})
    assert delete_backup_response.status_code == 200, delete_backup_response.text

    restore_source = client.get("/api/config/backups")
    restore_filename = restore_source.json()["backups"][0]["filename"]
    restore_response = client.post("/api/config/backups/restore", json={"filename": restore_filename})
    assert restore_response.status_code == 200, restore_response.text



def test_scheduled_tasks_write_and_schedule_reinit_roundtrip(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    recorder = _BridgeRecorder()
    _install_bridge(app, recorder)
    config_path = Path(os.environ["CONFIG_PATH"])

    add_response = client.post(
        "/api/scheduled-tasks/add",
        json={
            "name": "Weekly Chunk",
            "type": "chunk_generation",
            "interval": "weekly",
            "enabled": True,
            "params": {"category": "AI"},
        },
    )
    assert add_response.status_code == 200, add_response.text
    assert any(task["name"] == "Weekly Chunk" for task in _read_scheduled_tasks(config_path))

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
    )
    assert update_response.status_code == 200, update_response.text
    updated_task = next(task for task in _read_scheduled_tasks(config_path) if task["name"] == "Weekly Chunk")
    assert updated_task["interval"] == "daily"
    assert updated_task["enabled"] is False

    reinit_response = client.post("/api/schedule/reinit")
    assert reinit_response.status_code == 200, reinit_response.text
    assert reinit_response.json()["job_count"] == 2
    assert recorder.reinit_calls == 1

    delete_response = client.post("/api/scheduled-tasks/delete", json={"name": "Weekly Chunk"})
    assert delete_response.status_code == 200, delete_response.text
    assert all(task["name"] != "Weekly Chunk" for task in _read_scheduled_tasks(config_path))



def test_browse_folder_and_stats_endpoints_return_real_values(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    recorder = _BridgeRecorder()
    _install_bridge(app, recorder)
    db_path = Path(app.state.db_path)
    _seed_stats_data(db_path)

    allowed_root = tmp_path / "files"
    nested = allowed_root / "nested"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "sample.pdf").write_text("pdf", encoding="utf-8")

    browse_response = client.get(f"/api/utils/browse-folder?path={nested}")
    assert browse_response.status_code == 200, browse_response.text
    browse_body = browse_response.json()
    assert browse_body["path"] == str(nested.resolve())
    assert any(entry["name"] == "sample.pdf" for entry in browse_body["entries"])

    denied_response = client.get("/api/utils/browse-folder", params={"path": str(Path("/").resolve())})
    assert denied_response.status_code in {200, 403}

    catalog_stats = client.get("/api/catalog/stats")
    assert catalog_stats.status_code == 200, catalog_stats.text
    assert catalog_stats.json()["total_local_files"] >= 1

    markdown_stats = client.get("/api/markdown_conversion/stats")
    assert markdown_stats.status_code == 200, markdown_stats.text
    assert markdown_stats.json()["total_convertible"] >= 1
    assert markdown_stats.json()["total_with_markdown"] >= 1

    chunk_stats = client.get("/api/chunk_generation/stats")
    assert chunk_stats.status_code == 200, chunk_stats.text
    assert chunk_stats.json()["total_with_markdown"] >= 1
    assert chunk_stats.json()["total_with_chunks"] >= 1



def test_run_collection_and_stop_use_fastapi_native_endpoints(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    recorder = _BridgeRecorder()
    _install_bridge(app, recorder)

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

    stop_response = client.post("/api/tasks/stop/task-live")
    assert stop_response.status_code == 200, stop_response.text
    assert active_tasks["task-live"]["stop_requested"] is True

    invalid_response = client.post("/api/collections/run", json={"type": "file", "directory_path": "/does/not/exist"})
    assert invalid_response.status_code == 400
    assert invalid_response.json()["error"] == "Invalid directory path"

    real_dir = tmp_path / "import-me"
    real_dir.mkdir(parents=True, exist_ok=True)
    (real_dir / "bulletin.pdf").write_text("fake pdf", encoding="utf-8")
    run_response = client.post(
        "/api/collections/run",
        json={
            "type": "file",
            "name": "Import PDFs",
            "directory_path": str(real_dir),
            "extensions": ["pdf"],
            "recursive": True,
        },
    )
    assert run_response.status_code == 200, run_response.text
    run_body = run_response.json()
    assert run_body["success"] is True
    assert run_body["job_id"] == "task-fastapi-bridge"
    assert recorder.started[-1][0] == "file"
    assert recorder.started[-1][1]["directory_path"] == str(real_dir)



def test_ops_write_routes_require_operator_when_auth_enabled(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
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

    cookie_name = app.state.legacy_flask_app.config.get("SESSION_COOKIE_NAME", "session")
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
