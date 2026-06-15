from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from ..deps import AuthContext, require_permissions
from ..services.agentic_rag import (
    AgenticRagError,
    chat_agentic_rag,
    search_ready_sections,
    search_ready_summaries,
    search_ready_titles,
    trace_ready_relations,
)


router = APIRouter()


def _db_path(request: Request) -> str:
    db_path = str(getattr(request.app.state, "db_path", "") or "")
    if not db_path:
        raise HTTPException(status_code=500, detail="Database path is unavailable")
    return db_path


def _error_response(exc: AgenticRagError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.message})


@router.post("/agentic-rag/search/summaries")
def api_search_agentic_summaries(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("catalog.read")),
):
    try:
        return search_ready_summaries(db_path=_db_path(request), payload=payload)
    except AgenticRagError as exc:
        return _error_response(exc)


@router.post("/agentic-rag/search/titles")
def api_search_agentic_titles(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("catalog.read")),
):
    try:
        return search_ready_titles(db_path=_db_path(request), payload=payload)
    except AgenticRagError as exc:
        return _error_response(exc)


@router.post("/agentic-rag/search/sections")
def api_search_agentic_sections(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("catalog.read")),
):
    try:
        return search_ready_sections(db_path=_db_path(request), payload=payload)
    except AgenticRagError as exc:
        return _error_response(exc)


@router.post("/agentic-rag/trace/relations")
def api_trace_agentic_relations(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("catalog.read")),
):
    try:
        return trace_ready_relations(db_path=_db_path(request), payload=payload)
    except AgenticRagError as exc:
        return _error_response(exc)


@router.post("/agentic-rag/chat")
def api_agentic_rag_chat(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("catalog.read")),
):
    try:
        return chat_agentic_rag(db_path=_db_path(request), payload=payload)
    except AgenticRagError as exc:
        return _error_response(exc)
