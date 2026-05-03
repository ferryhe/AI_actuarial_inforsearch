from __future__ import annotations

import os
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from ai_actuarial.config import settings
from ..deps import AuthContext, require_permissions
from ..services.files_write import (
    FileWriteError,
    delete_file_record,
    export_catalog,
    generate_file_chunk_sets,
    get_downloadable_file,
    get_file_chunk_sets,
    get_rag_file_preview,
    update_file_markdown_content,
    update_file_record,
)

router = APIRouter()


def _db_path(request: Request) -> str:
    db_path = str(getattr(request.app.state, "db_path", "") or "")
    if not db_path:
        raise HTTPException(status_code=500, detail="Database path is unavailable")
    return db_path


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
    return raw_text[len(prefix):-len(suffix)]


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


def _require_config_write_token(request: Request) -> JSONResponse | None:
    expected_token = os.getenv("CONFIG_WRITE_AUTH_TOKEN") or settings.CONFIG_WRITE_AUTH_TOKEN
    if not expected_token:
        return None
    provided_token = request.headers.get("X-Auth-Token")
    if not provided_token or provided_token != expected_token:
        return JSONResponse(status_code=403, content={"error": "Forbidden"})
    return None


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
        return delete_file_record(db_path=_db_path(request), payload=payload, headers=dict(request.headers))
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
        return update_file_markdown_content(db_path=_db_path(request), url=decoded_url, payload=payload)
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
    _auth: AuthContext = Depends(require_permissions("export.read")),
):
    format_type = str(request.query_params.get("format", "csv") or "csv")
    try:
        content, media_type, filename = export_catalog(db_path=_db_path(request), format_type=format_type)
        return Response(content=content, media_type=media_type, headers={"Content-Disposition": f"attachment; filename={filename}"})
    except FileWriteError as exc:
        return _json_error(exc)


@router.get("/rag/files/preview")
def api_rag_files_preview(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("files.read")),
):
    file_url = str(request.query_params.get("file_url", "") or "").strip()
    chunk_set_id = str(request.query_params.get("chunk_set_id", "") or "").strip() or None
    try:
        return get_rag_file_preview(db_path=_db_path(request), file_url=file_url, chunk_set_id=chunk_set_id)
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
    if (auth_error := _require_config_write_token(request)) is not None:
        return auth_error
    decoded_url = _decode_file_url_path(request, file_url, suffix="/chunk-sets/generate")
    try:
        result = generate_file_chunk_sets(db_path=_db_path(request), file_url=decoded_url, payload=payload)
        status_code = 201 if not result.get("reused_existing") else 200
        return JSONResponse(status_code=status_code, content=result)
    except FileWriteError as exc:
        return _json_error(exc)
