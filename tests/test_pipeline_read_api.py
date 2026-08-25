from __future__ import annotations

from pathlib import Path

from ai_actuarial.api.services.ops_read import (
    get_pipeline_run_detail,
    list_pipeline_runs,
    parse_pipeline_runs_limit,
)
from ai_actuarial.storage import Storage
from tests.test_fastapi_ops_read_endpoints import _build_test_client, _patch_available_models


def _seed_pipeline(db_path: str) -> None:
    storage = Storage(db_path)
    try:
        storage.create_pipeline_run("run-1", correlation_id="corr-1", source_type="scheduled")
        storage.start_pipeline_run("run-1")
        storage.upsert_pipeline_stage("run-1", "acquisition", stage_order=1, options_json='{"sites": 2}')
        storage.update_pipeline_stage(
            "run-1", "acquisition", status="succeeded", finished_at="2026-08-25T00:01:00+00:00"
        )
        storage.upsert_pipeline_stage("run-1", "catalog", stage_order=2, options_json='{"model": "gpt-4o-mini"}')
        storage.update_pipeline_stage("run-1", "catalog", status="running", checkpoint_json='{"cursor": 3}')
        storage.create_pipeline_run("run-2", correlation_id="corr-2", source_type="scheduled")
        storage.update_pipeline_run("run-2", status="failed", error="boom", finished_at="2026-08-24T00:00:00+00:00")
        storage.create_child_run("child-1", "run-1", correlation_id="corr-1")
        storage.update_child_run("child-1", status="succeeded")
    finally:
        storage.close()


# --- service functions ------------------------------------------------------


def test_list_pipeline_runs_service(tmp_path: Path) -> None:
    db_path = str(tmp_path / "svc.db")
    _seed_pipeline(db_path)

    result = list_pipeline_runs(db_path=db_path, limit=10)
    assert result["count"] == 2
    assert {r["run_id"] for r in result["runs"]} == {"run-1", "run-2"}

    limited = list_pipeline_runs(db_path=db_path, limit=1)
    assert limited["count"] == 1


def test_get_pipeline_run_detail_service(tmp_path: Path) -> None:
    db_path = str(tmp_path / "svc.db")
    _seed_pipeline(db_path)

    detail = get_pipeline_run_detail(db_path=db_path, run_id="run-1")
    assert detail is not None
    assert detail["run"]["run_id"] == "run-1"
    assert [s["stage_name"] for s in detail["stages"]] == ["acquisition", "catalog"]

    acq = detail["stages"][0]
    assert acq["options_json"] == '{"sites": 2}'
    assert acq["status"] == "succeeded"
    assert acq["finished_at"] == "2026-08-25T00:01:00+00:00"

    catalog = detail["stages"][1]
    assert catalog["checkpoint_json"] == '{"cursor": 3}'
    assert catalog["status"] == "running"

    assert detail["child_runs"][0]["child_run_id"] == "child-1"
    assert detail["child_runs"][0]["status"] == "succeeded"

    assert get_pipeline_run_detail(db_path=db_path, run_id="missing") is None


def test_parse_pipeline_runs_limit_clamps() -> None:
    assert parse_pipeline_runs_limit(None) == 50
    assert parse_pipeline_runs_limit("25") == 25
    assert parse_pipeline_runs_limit("0") == 1
    assert parse_pipeline_runs_limit("99999") == 500
    assert parse_pipeline_runs_limit("not-a-number") == 50


# --- API endpoints ----------------------------------------------------------


def test_pipeline_runs_endpoint_lists_runs(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    _seed_pipeline(str(app.state.db_path))
    headers = {"X-Auth-Token": seed["admin_token"]}

    resp = client.get("/api/pipeline/runs", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert {r["run_id"] for r in body["runs"]} == {"run-1", "run-2"}

    limited = client.get("/api/pipeline/runs?limit=1", headers=headers)
    assert limited.status_code == 200
    assert limited.json()["count"] == 1


def test_pipeline_run_detail_endpoint(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    _seed_pipeline(str(app.state.db_path))
    headers = {"X-Auth-Token": seed["admin_token"]}

    resp = client.get("/api/pipeline/runs/run-1", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["run"]["run_id"] == "run-1"
    assert [s["stage_name"] for s in body["stages"]] == ["acquisition", "catalog"]
    assert body["stages"][0]["options_json"] == '{"sites": 2}'
    assert body["stages"][0]["finished_at"] == "2026-08-25T00:01:00+00:00"
    assert body["stages"][1]["checkpoint_json"] == '{"cursor": 3}'
    assert body["child_runs"][0]["child_run_id"] == "child-1"

    missing = client.get("/api/pipeline/runs/missing", headers=headers)
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Pipeline run not found"}


def test_pipeline_runs_require_tasks_view_permission(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    _seed_pipeline(str(app.state.db_path))

    unauthorized = client.get("/api/pipeline/runs")
    assert unauthorized.status_code == 401

    authorized = client.get(
        "/api/pipeline/runs",
        headers={"Authorization": f"Bearer {seed['reader_token']}"},
    )
    assert authorized.status_code == 200
