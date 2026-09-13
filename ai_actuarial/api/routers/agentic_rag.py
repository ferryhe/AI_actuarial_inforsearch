from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from ..deps import AuthContext, require_permissions
from ..services.agentic_rag import (
    AgenticRagError,
    chat_agentic_rag,
    search_ready_calculation_terms,
    search_ready_formula_cards,
    search_ready_sections,
    search_ready_structured_tables,
    search_ready_summaries,
    search_ready_titles,
    trace_ready_relations,
)
from ..services.chat import ChatApiError, apply_session_update, query_chat

router = APIRouter()


def _db_path(request: Request) -> str:
    db_path = str(getattr(request.app.state, "db_path", "") or "")
    if not db_path:
        raise HTTPException(status_code=500, detail="Database path is unavailable")
    return db_path


DEPRECATED_AGENTIC_CHAT_PATH = "/api/agentic-rag/chat"


def _error_response(exc: AgenticRagError | ChatApiError) -> JSONResponse:
    content = exc.payload if isinstance(exc, ChatApiError) else {"error": exc.message}
    return JSONResponse(status_code=exc.status_code, content=content)


def _legacy_agentic_chat_payload(payload: dict[str, object]) -> dict[str, object]:
    """Map the retired Agentic Chat shape to the canonical Chat command.

    ``output_dir`` was a diagnostics-only escape hatch in the old endpoint.
    It has no equivalent in product Chat because Agentic Chat validates a
    selected, registered KB before it creates a conversation or consumes quota.
    """
    if "output_dir" in payload:
        raise ChatApiError(
            "output_dir is not supported by deprecated Agentic Chat; use a registered kb_id "
            "with /api/chat/query",
            status_code=400,
        )

    mapped: dict[str, object] = {
        "message": payload.get("query"),
        "kb_ids": [payload.get("kb_id")] if payload.get("kb_id") else [],
        "rag_mode": "agentic",
    }
    for old_key, new_key in (
        ("profile", "manifest_profile"),
        ("manifest_profile", "manifest_profile"),
        ("limit", "limit"),
        ("mode", "mode"),
        ("conversation_id", "conversation_id"),
    ):
        if old_key in payload:
            mapped[new_key] = payload[old_key]
    return mapped


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


@router.post("/agentic-rag/search/formula-cards")
def api_search_agentic_formula_cards(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("catalog.read")),
):
    try:
        return search_ready_formula_cards(db_path=_db_path(request), payload=payload)
    except AgenticRagError as exc:
        return _error_response(exc)


@router.post("/agentic-rag/search/tables")
def api_search_agentic_tables(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("catalog.read")),
):
    try:
        return search_ready_structured_tables(db_path=_db_path(request), payload=payload)
    except AgenticRagError as exc:
        return _error_response(exc)


@router.post("/agentic-rag/search/calculation-terms")
def api_search_agentic_calculation_terms(
    payload: dict[str, object],
    request: Request,
    _auth: AuthContext = Depends(require_permissions("catalog.read")),
):
    try:
        return search_ready_calculation_terms(db_path=_db_path(request), payload=payload)
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


@router.post("/agentic-rag/chat", deprecated=True)
def api_agentic_rag_chat(
    payload: dict[str, object],
    request: Request,
    response: Response,
    auth: AuthContext = Depends(require_permissions("chat.query")),
):
    """Temporary compatibility shim; new clients must use ``/api/chat/query``."""
    try:
        result, session_update = query_chat(
            db_path=_db_path(request),
            request=request,
            auth=auth,
            payload=_legacy_agentic_chat_payload(payload),
        )
        apply_session_update(response, request, session_update)
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = "Wed, 14 Oct 2026 00:00:00 GMT"
        response.headers["Link"] = '</api/chat/query>; rel="successor-version"'
        return result
    except (AgenticRagError, ChatApiError) as exc:
        return _error_response(exc)
