from __future__ import annotations

from tests.test_fastapi_ops_read_endpoints import _build_test_client, _patch_available_models


def test_pipeline_baton_api_uses_runtime_bridge_and_existing_permissions(tmp_path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    calls: list[tuple[str, object]] = []
    view = {
        "config": {"overrides": {}},
        "state": {"round_status": "idle"},
        "stages": [],
    }
    app.state.pipeline_baton_status = lambda: view
    app.state.pipeline_baton_start = lambda: calls.append(("start", None)) or view
    app.state.pipeline_baton_tick = lambda: calls.append(("tick", None)) or view
    app.state.pipeline_baton_configure = lambda overrides: calls.append(("config", overrides)) or view
    reader_headers = {"Authorization": f"Bearer {seed['reader_token']}"}
    operator_headers = {"Authorization": f"Bearer {seed['operator_token']}"}

    assert client.get("/api/pipeline/status", headers=reader_headers).json() == view
    assert client.get("/api/pipeline/config", headers=reader_headers).json() == view["config"]
    assert client.post("/api/pipeline/start", headers=reader_headers).status_code == 403
    assert client.post("/api/pipeline/tick", headers=operator_headers).json() == view
    assert client.post(
        "/api/pipeline/config",
        json={"overrides": {"catalog": {"scan_count": 12}}},
        headers=operator_headers,
    ).json() == view
    assert client.post("/api/pipeline/start", headers=operator_headers).json() == view
    assert calls == [
        ("tick", None),
        ("config", {"catalog": {"scan_count": 12}}),
        ("start", None),
    ]


def test_old_full_pipeline_is_rejected_by_run_and_schedule_apis(tmp_path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, _app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    headers = {"X-Auth-Token": seed["admin_token"]}

    run = client.post(
        "/api/collections/run",
        json={"type": "full_pipeline", "name": "Old Full Pipeline"},
        headers=headers,
    )
    scheduled = client.post(
        "/api/scheduled-tasks/add",
        json={"name": "Old Full Pipeline", "type": "full_pipeline", "interval": "daily", "params": {}},
        headers=headers,
    )

    assert run.status_code == 400
    assert scheduled.status_code == 400
    assert client.get("/api/pipeline/runs", headers=headers).status_code == 410
