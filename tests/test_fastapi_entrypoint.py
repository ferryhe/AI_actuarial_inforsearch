from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from ai_actuarial.api.app import create_app


def test_fastapi_health_endpoint_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["backend"] == "fastapi"


def test_fastapi_migration_status_reports_gateway_state() -> None:
    client = TestClient(create_app())

    response = client.get("/api/migration/status")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["backend"] == "fastapi"
    assert body["api_authority"] == "fastapi"
    assert body["legacy_api_route_count"] >= body["legacy_api_routes_remaining"] > 0
    assert body["migration_inventory_enabled"] is False
    assert body["legacy_flask_only_sample_signatures"] == []
    assert body["legacy_api_fallback_allowed"] is False
    assert "/api/health" in body["native_paths"]
    assert "/api/migration/status" in body["native_paths"]


def test_fastapi_migration_inventory_is_disabled_by_default() -> None:
    client = TestClient(create_app())

    response = client.get("/api/migration/inventory")

    assert response.status_code == 404
    assert response.json()["detail"] == "Migration inventory is disabled"


def test_fastapi_migration_inventory_exposes_native_and_legacy_routes_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("FASTAPI_ENABLE_MIGRATION_INVENTORY", "1")
    client = TestClient(create_app())

    response = client.get("/api/migration/inventory")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["api_authority"] == "fastapi"
    assert body["legacy_mount_failed"] is False
    assert body["legacy_api_fallback_allowed"] is False
    assert "/api/health" in body["native_paths"]
    assert "/api/stats" in body["legacy_api_paths"]
    assert "GET /api/stats" in body["native_override_signatures"]
    assert body["legacy_flask_only_route_count"] > 0
    assert body["legacy_api_route_count"] >= len(body["legacy_api_paths"])


def test_unported_legacy_api_fallback_is_blocked_by_default() -> None:
    client = TestClient(create_app())

    response = client.get("/api/logs/global")
    head_response = client.head("/api/logs/global")

    assert response.status_code == 410
    assert "Legacy Flask /api fallback is disabled" in response.json()["detail"]
    assert head_response.status_code == 410


def test_legacy_api_fallback_can_be_reenabled_for_debugging(monkeypatch) -> None:
    monkeypatch.setenv("FASTAPI_ALLOW_LEGACY_API_FALLBACK", "1")
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    client = TestClient(create_app())

    response = client.get("/api/files/example/indexes")

    assert response.status_code != 410


def test_fastapi_uses_rebound_legacy_task_history_reference(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "sites.yaml"
    categories_path = tmp_path / "categories.yaml"
    db_path = tmp_path / "index.db"
    config_path.write_text(
        "paths:\n  db: {}\n  download_dir: {}\n  updates_dir: {}\nsites: []\nscheduled_tasks: []\n".format(
            db_path,
            tmp_path / "files",
            tmp_path / "updates",
        ),
        encoding="utf-8",
    )
    categories_path.write_text("categories: {}\n", encoding="utf-8")
    history_dir = tmp_path / "data"
    history_dir.mkdir(parents=True, exist_ok=True)
    (history_dir / "job_history.jsonl").write_text(
        json.dumps(
            {
                "id": "task-history-from-disk",
                "name": "Loaded History",
                "type": "markdown_conversion",
                "status": "completed",
                "started_at": "2026-04-15T12:43:39.212434",
                "completed_at": "2026-04-15T12:43:40.097561",
                "items_processed": 1,
                "items_total": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("CATEGORIES_CONFIG_PATH", str(categories_path))
    monkeypatch.setenv("FLASK_SECRET_KEY", "fastapi-entrypoint-test-secret")

    client = TestClient(create_app())
    response = client.get("/api/tasks/history?limit=5")

    assert response.status_code == 200
    body = response.json()
    assert any(task.get("id") == "task-history-from-disk" for task in body["tasks"])
