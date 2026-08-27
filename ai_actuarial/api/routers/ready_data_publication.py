from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ..deps import AuthContext
from ..services.rag_admin import RagAdminError
from ..services.ready_data_publication import (
    publish_ready_data_publication,
    rollback_ready_data_publication,
)
from .rag_admin import require_rag_task_run


router = APIRouter()


def _db_path(request: Request) -> str:
    db_path = str(getattr(request.app.state, "db_path", "") or "")
    if not db_path:
        raise RagAdminError("Database path is unavailable", status_code=500)
    return db_path


@router.post("/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/publish")
def api_publish_ready_data_publication(
    kb_id: str,
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_rag_task_run),
):
    try:
        return publish_ready_data_publication(
            db_path=_db_path(request),
            kb_id=kb_id,
            payload=payload,
        )
    except RagAdminError as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.message})


@router.post("/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/rollback")
def api_rollback_ready_data_publication(
    kb_id: str,
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_rag_task_run),
):
    try:
        return rollback_ready_data_publication(
            db_path=_db_path(request),
            kb_id=kb_id,
            payload=payload,
        )
    except RagAdminError as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.message})
