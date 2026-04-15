from __future__ import annotations

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
    assert body["legacy_api_routes_remaining"] > 0
    assert body["migration_inventory_enabled"] is False
    assert body["legacy_api_sample_paths"] == []
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
    assert "/api/health" in body["native_paths"]
    assert "/api/stats" in body["legacy_api_paths"]
    assert "GET /api/stats" in body["native_overrides_legacy_signatures"]
    assert body["legacy_api_route_count"] >= len(body["legacy_api_paths"])
