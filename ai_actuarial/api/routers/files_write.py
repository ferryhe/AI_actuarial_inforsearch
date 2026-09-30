from __future__ import annotations

import logging
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from ai_actuarial.storage import Storage

from ..deps import AuthContext, require_permissions
from ..services.files_write import (
    FileWriteError,
    delete_file_record,
    export_catalog,
    get_downloadable_file,
    get_file_chunk_sets,
    get_previewable_file,
    get_rag_file_preview,
    update_file_markdown_content,
    update_file_record,
)
from ..services.import_batches import ImportBatchError, create_import_batch
from ..services.ops_write import BridgeState, OpsWriteError, start_collection
from ..services.read import FileListValidationError, parse_file_list_query
from .read import _can_view_sensitive_file_fields

router = APIRouter()
logger = logging.getLogger(__name__)


def _db_path(request: Request) -> str:
    db_path = str(getattr(request.app.state, "db_path", "") or "")
    if not db_path:
        raise HTTPException(status_code=500, detail="Database path is unavailable")
    return db_path


def _record_export_audit(request: Request, auth: AuthContext, *, count: int, full: bool) -> None:
    storage = Storage(_db_path(request))
    try:
        storage.log_audit_event(
            "catalog_export",
            token_id=(auth.token or {}).get("id"),
            resource="catalog",
            detail=f"records={count}; full={str(full).lower()}",
            ip=request.client.host if request.client else None,
        )
    finally:
        storage.close()


def _extract_encoded_file_url(request: Request, *, suffix: str) -> str | None:
    raw_path = request.scope.get("raw_path")
    if not isinstance(raw_path, (bytes, bytearray)):
        return None
    try:
        raw_text = bytes(raw_path).decode("ascii")
    except Exception:
        return None
    prefix = "/api/files/"
    if not raw_text.startswith(prefix) or not raw_text.endswith(suffix):
        return None
    return raw_text[len(prefix) : -len(suffix)]


def _decode_file_url_path(request: Request, file_url: str, *, suffix: str) -> str:
    encoded = _extract_encoded_file_url(request, suffix=suffix)
    if not encoded:
        return file_url
    try:
        return unquote(encoded)
    except Exception:
        return file_url


def _json_error(exc: FileWriteError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.message})


@router.post("/files/import-batches")
async def api_files_import_batches(
    files: list[UploadFile],
    request: Request,
    relative_paths: list[str] = Form(default=[]),
    auth: AuthContext = Depends(require_permissions("tasks.run")),
):
    try:
        result = await create_import_batch(
            files=files, relative_paths=relative_paths, auth_token=auth.token
        )
        return JSONResponse(status_code=201, content=result)
    except ImportBatchError as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.message})


@router.post("/files/update")
def api_files_update(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("catalog.write")),
):
    try:
        return update_file_record(db_path=_db_path(request), payload=payload)
    except FileWriteError as exc:
        return _json_error(exc)


@router.post("/files/delete")
def api_files_delete(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("files.delete")),
):
    try:
        return delete_file_record(
            db_path=_db_path(request),
            payload=payload,
            bridge_state=request.app.state,
            headers=dict(request.headers),
            auth=_auth,
        )
    except FileWriteError as exc:
        return _json_error(exc)


@router.post("/files/{file_url:path}/markdown")
def api_files_update_markdown(
    file_url: str,
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("markdown.write")),
):
    decoded_url = _decode_file_url_path(request, file_url, suffix="/markdown")
    try:
        return update_file_markdown_content(
            db_path=_db_path(request), url=decoded_url, payload=payload
        )
    except FileWriteError as exc:
        return _json_error(exc)


@router.get("/download")
def api_download(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("files.download")),
):
    url = str(request.query_params.get("url", "") or "").strip()
    try:
        path, filename = get_downloadable_file(db_path=_db_path(request), url=url)
        return FileResponse(path=path, filename=filename)
    except FileWriteError as exc:
        return _json_error(exc)


@router.get("/export")
def api_export(
    request: Request,
    auth: AuthContext = Depends(require_permissions("export.read")),
):
    format_type = str(request.query_params.get("format", "csv") or "csv")
    try:
        query = parse_file_list_query(request.query_params)
        if query.include_deleted:
            return JSONResponse(
                status_code=400,
                content={"error": "Deleted records require full export with include_deleted=true"},
            )
        content, media_type, filename, count = export_catalog(
            db_path=_db_path(request), format_type=format_type, query=query
        )
        _record_export_audit(request, auth, count=count, full=False)
        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Export-Record-Count": str(count),
            },
        )
    except FileListValidationError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except FileWriteError as exc:
        return _json_error(exc)


@router.get("/export/full")
def api_export_full(
    request: Request,
    auth: AuthContext = Depends(require_permissions("export.full")),
):
    format_type = str(request.query_params.get("format", "csv") or "csv")
    include_deleted = str(request.query_params.get("include_deleted", "false")).lower() == "true"
    include_sensitive = str(request.query_params.get("include_internal", "false")).lower() == "true"
    try:
        query = parse_file_list_query(request.query_params)
        content, media_type, filename, count = export_catalog(
            db_path=_db_path(request),
            format_type=format_type,
            query=query,
            include_deleted=include_deleted,
            include_sensitive=include_sensitive,
        )
        _record_export_audit(request, auth, count=count, full=True)
        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Export-Record-Count": str(count),
            },
        )
    except FileListValidationError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except FileWriteError as exc:
        return _json_error(exc)


@router.get("/rag/files/preview")
def api_rag_files_preview(
    request: Request,
    auth: AuthContext = Depends(require_permissions("files.read")),
):
    file_url = str(request.query_params.get("file_url", "") or "").strip()
    chunk_set_id = str(request.query_params.get("chunk_set_id", "") or "").strip() or None
    try:
        return get_rag_file_preview(
            db_path=_db_path(request),
            file_url=file_url,
            chunk_set_id=chunk_set_id,
            include_sensitive=_can_view_sensitive_file_fields(auth),
        )
    except FileWriteError as exc:
        return _json_error(exc)


@router.api_route("/rag/files/preview/raw", methods=["GET", "HEAD"])
def api_rag_files_preview_raw(
    request: Request,
    auth: AuthContext = Depends(require_permissions("files.read")),
):
    """Serve PDF/image bytes for authenticated inline preview, never as a download grant."""
    file_url = str(request.query_params.get("file_url", "") or "").strip()
    try:
        path, filename, media_type = get_previewable_file(db_path=_db_path(request), url=file_url)
        logger.info(
            "audit_event=file_preview_raw subject=%s resource=%s ip=%s",
            (auth.token or {}).get("subject", ""),
            file_url,
            request.client.host if request.client else "",
        )
        return FileResponse(
            path=path,
            filename=filename,
            media_type=media_type,
            content_disposition_type="inline",
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
    except FileWriteError as exc:
        return _json_error(exc)


@router.get("/files/{file_url:path}/chunk-sets")
def api_file_chunk_sets(
    file_url: str,
    request: Request,
    _auth: AuthContext = Depends(require_permissions("files.read")),
):
    decoded_url = _decode_file_url_path(request, file_url, suffix="/chunk-sets")
    try:
        return get_file_chunk_sets(db_path=_db_path(request), file_url=decoded_url)
    except FileWriteError as exc:
        return _json_error(exc)


@router.post("/files/{file_url:path}/chunk-sets/generate")
def api_file_chunk_sets_generate(
    file_url: str,
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("tasks.run")),
):
    decoded_url = _decode_file_url_path(request, file_url, suffix="/chunk-sets/generate")
    try:
        task_payload = dict(payload)
        task_payload.update(
            {
                "type": "chunk_generation",
                "file_urls": [decoded_url],
                "name": str(payload.get("name") or "Chunk & Embedding: file chunk step"),
            }
        )
        result = start_collection(task_payload, bridge=BridgeState(request.app.state))
        return JSONResponse(status_code=202, content=result)
    except FileWriteError as exc:
        return _json_error(exc)
    except OpsWriteError as exc:
        content: dict[str, object] = {"error": exc.message}
        if exc.code:
            content["code"] = exc.code
        content.update(exc.details)
        return JSONResponse(status_code=exc.status_code, content=content)
