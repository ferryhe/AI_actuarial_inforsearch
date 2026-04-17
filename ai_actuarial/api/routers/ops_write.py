from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from ..deps import AuthContext, require_permissions
from ..services.ops_write import (
    BridgeState,
    OpsWriteError,
    add_scheduled_task,
    add_site,
    browse_folder,
    delete_backup,
    delete_provider_credential,
    delete_scheduled_task,
    delete_site,
    export_sites_yaml,
    get_catalog_stats,
    get_chunk_generation_stats,
    get_markdown_conversion_stats,
    import_sites,
    list_backups,
    request_task_stop,
    reinitialize_scheduler,
    restore_backup,
    sample_sites_yaml,
    start_collection,
    update_ai_routing,
    update_backend_settings,
    update_scheduled_task,
    update_site,
    upsert_provider_credential,
)

router = APIRouter()


def _bridge(request: Request) -> BridgeState:
    return BridgeState(request.app.state)


def _db_path(request: Request) -> str:
    db_path = str(getattr(request.app.state, "db_path", "") or "")
    if not db_path:
        raise OpsWriteError("Database path is unavailable", status_code=500)
    return db_path


def _handle_ops_error(exc: OpsWriteError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.message})


@router.post("/config/sites/add")
def api_config_sites_add(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("schedule.write")),
):
    try:
        return add_site(payload, bridge=_bridge(request))
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.post("/config/sites/update")
def api_config_sites_update(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("schedule.write")),
):
    try:
        return update_site(payload, bridge=_bridge(request))
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.post("/config/sites/delete")
def api_config_sites_delete(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("schedule.write")),
):
    try:
        return delete_site(str(payload.get("name") or ""), bridge=_bridge(request))
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.post("/config/sites/import")
def api_config_sites_import(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("schedule.write")),
):
    try:
        return import_sites(payload, bridge=_bridge(request))
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.get("/config/sites/export")
def api_config_sites_export(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("schedule.write")),
):
    try:
        content, filename = export_sites_yaml()
        return Response(
            content=content,
            media_type="application/x-yaml",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.get("/config/sites/sample")
def api_config_sites_sample(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("schedule.write")),
):
    try:
        content, filename = sample_sites_yaml()
        return Response(
            content=content,
            media_type="application/x-yaml",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.get("/config/backups")
def api_config_backups(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("schedule.write")),
):
    try:
        return list_backups()
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.post("/config/backups/restore")
def api_config_backups_restore(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("schedule.write")),
):
    try:
        return restore_backup(str(payload.get("filename") or ""), bridge=_bridge(request))
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.post("/config/backups/delete")
def api_config_backups_delete(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("schedule.write")),
):
    try:
        return delete_backup(str(payload.get("filename") or ""))
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.post("/config/backend-settings")
def api_config_backend_settings_update(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("config.write")),
):
    try:
        expected_token = os.getenv("CONFIG_WRITE_AUTH_TOKEN")
        if expected_token:
            provided_token = request.headers.get("X-Auth-Token")
            if not provided_token or provided_token != expected_token:
                return JSONResponse(status_code=403, content={"error": "Forbidden"})
        return update_backend_settings(payload, bridge=_bridge(request))
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.post("/config/provider-credentials")
def api_config_provider_credentials_upsert(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("config.write")),
):
    try:
        expected_token = os.getenv("CONFIG_WRITE_AUTH_TOKEN")
        if expected_token:
            provided_token = request.headers.get("X-Auth-Token")
            if not provided_token or provided_token != expected_token:
                return JSONResponse(status_code=403, content={"error": "Forbidden"})
        return upsert_provider_credential(payload, db_path=_db_path(request))
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.delete("/config/provider-credentials/{provider_id}")
def api_config_provider_credentials_delete(
    provider_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_permissions("config.write")),
):
    try:
        expected_token = os.getenv("CONFIG_WRITE_AUTH_TOKEN")
        if expected_token:
            provided_token = request.headers.get("X-Auth-Token")
            if not provided_token or provided_token != expected_token:
                return JSONResponse(status_code=403, content={"error": "Forbidden"})
        category = str(request.query_params.get("category") or "llm").strip().lower() or "llm"
        return delete_provider_credential(provider_id, db_path=_db_path(request), category=category)
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.post("/config/ai-routing")
def api_config_ai_routing_update(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("config.write")),
):
    try:
        expected_token = os.getenv("CONFIG_WRITE_AUTH_TOKEN")
        if expected_token:
            provided_token = request.headers.get("X-Auth-Token")
            if not provided_token or provided_token != expected_token:
                return JSONResponse(status_code=403, content={"error": "Forbidden"})
        return update_ai_routing(payload, db_path=_db_path(request), bridge=_bridge(request))
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.post("/scheduled-tasks/add")
def api_scheduled_tasks_add(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("schedule.write")),
):
    try:
        return add_scheduled_task(payload, bridge=_bridge(request))
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.post("/scheduled-tasks/update")
def api_scheduled_tasks_update(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("schedule.write")),
):
    try:
        return update_scheduled_task(payload, bridge=_bridge(request))
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.post("/scheduled-tasks/delete")
def api_scheduled_tasks_delete(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("schedule.write")),
):
    try:
        return delete_scheduled_task(str(payload.get("name") or ""), bridge=_bridge(request))
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.post("/schedule/reinit")
def api_schedule_reinit(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("schedule.write")),
):
    try:
        return reinitialize_scheduler(_bridge(request))
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.post("/tasks/stop/{task_id}")
def api_tasks_stop(
    task_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_permissions("tasks.stop")),
):
    try:
        return request_task_stop(task_id, bridge=_bridge(request))
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.post("/collections/run")
def api_collections_run(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("tasks.run")),
):
    try:
        return start_collection(payload, bridge=_bridge(request))
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.get("/utils/browse-folder")
def api_utils_browse_folder(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("tasks.run")),
):
    try:
        return browse_folder(request.query_params.get("path"))
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.get("/catalog/stats")
def api_catalog_stats(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("tasks.view")),
):
    try:
        return get_catalog_stats(
            db_path=_db_path(request),
            provider=request.query_params.get("provider"),
            input_source=request.query_params.get("input_source"),
            category=request.query_params.get("category"),
        )
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.get("/markdown_conversion/stats")
def api_markdown_conversion_stats(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("tasks.view")),
):
    try:
        return get_markdown_conversion_stats(db_path=_db_path(request), category=request.query_params.get("category"))
    except OpsWriteError as exc:
        return _handle_ops_error(exc)


@router.get("/chunk_generation/stats")
def api_chunk_generation_stats(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("tasks.view")),
):
    try:
        return get_chunk_generation_stats(db_path=_db_path(request), category=request.query_params.get("category"))
    except OpsWriteError as exc:
        return _handle_ops_error(exc)
