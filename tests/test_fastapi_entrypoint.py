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
    assert "/api/health" in body["native_paths"]
    assert "/api/migration/status" in body["native_paths"]
