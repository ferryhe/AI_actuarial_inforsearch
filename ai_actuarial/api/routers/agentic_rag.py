from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Mapping

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from ..deps import AuthContext, require_permissions
from ..services.agentic_rag import (
    AgenticRagError,
    _resolve_ready_output_dir,
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


_AGENTIC_CHAT_SUNSET_HEADER = "Wed, 14 Oct 2026 00:00:00 GMT"
_AGENTIC_CHAT_RETIRED_MESSAGE = (
    "Endpoint retired; use /api/chat/query"
)


def _parse_sunset(value: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _validate_chat_message(payload: Mapping[str, object]) -> None:
    """Reject an empty/whitespace ``message`` before any KB or storage work.

    Mirrors the early check inside ``query_chat`` so the compatibility shim
    preserves the legacy 400 contract for empty queries instead of leaking a
    503 from the readiness gate below.
    """
    message = str(payload.get("message") or "").strip()
    if not message:
        raise ChatApiError("Message is required", status_code=400)


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
    sunset = _parse_sunset(_AGENTIC_CHAT_SUNSET_HEADER)
    if sunset is not None and datetime.now(timezone.utc) >= sunset:
        return JSONResponse(
            status_code=410,
            content={"success": False, "error": _AGENTIC_CHAT_RETIRED_MESSAGE},
        )
    try:
        mapped_payload = _legacy_agentic_chat_payload(payload)
        # Surface empty-message rejections (400) before the KB readiness gate
        # so callers that never had a chance to succeed don't get a 503.
        # The mapped payload exposes the canonical ``message`` field that
        # query_chat itself validates later; we mirror that validation here
        # so it runs ahead of any storage or embedding work.
        _validate_chat_message(mapped_payload)
        # Validate KB readiness (manifest present + status == "ready") before
        # delegating to query_chat; otherwise the canonical service would
        # silently fall back to standard RAG and crash inside the embedding
        # generator with an EmbeddingException -> 500 + leaked internals.
        # The original payload (not mapped_payload) is passed because
        # _resolve_ready_output_dir reads legacy fields like ``kb_id`` and
        # ``manifest_profile`` directly, while mapped_payload carries the
        # canonical ``kb_ids`` list and ``rag_mode``.
        try:
            _resolve_ready_output_dir(db_path=_db_path(request), payload=payload)
        except AgenticRagError as exc:
            raise ChatApiError(exc.message, status_code=503) from exc
        result, session_update = query_chat(
            db_path=_db_path(request),
            request=request,
            auth=auth,
            payload=mapped_payload,
        )
        apply_session_update(response, request, session_update)
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = _AGENTIC_CHAT_SUNSET_HEADER
        response.headers["Link"] = '</api/chat/query>; rel="successor-version"'
        return result
    except (AgenticRagError, ChatApiError) as exc:
        return _error_response(exc)
