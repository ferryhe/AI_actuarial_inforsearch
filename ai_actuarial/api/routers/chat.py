from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from ..deps import AuthContext, require_permissions
from ..services.chat import (
    ChatApiError,
    apply_session_update,
    create_conversation,
    delete_conversation,
    get_conversation_detail,
    list_available_documents,
    list_conversations,
    list_knowledge_bases,
    query_chat,
)

router = APIRouter()


def _db_path(request: Request) -> str:
    db_path = str(getattr(request.app.state, "db_path", "") or "")
    if not db_path:
        raise ChatApiError("Database path is unavailable", status_code=500)
    return db_path


def _error_response(exc: ChatApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.payload)


@router.get("/chat/conversations")
def api_list_conversations(
    request: Request,
    response: Response,
    auth: AuthContext = Depends(require_permissions("chat.conversations")),
):
    try:
        payload, session_update = list_conversations(db_path=_db_path(request), request=request, auth=auth)
        apply_session_update(response, request, session_update)
        return payload
    except ChatApiError as exc:
        return _error_response(exc)


@router.post("/chat/conversations")
def api_create_conversation(
    payload: dict[str, object],
    request: Request,
    response: Response,
    auth: AuthContext = Depends(require_permissions("chat.conversations")),
):
    try:
        result, session_update = create_conversation(db_path=_db_path(request), request=request, auth=auth, payload=payload)
        apply_session_update(response, request, session_update)
        return JSONResponse(status_code=201, content=result, headers=dict(response.headers))
    except ChatApiError as exc:
        return _error_response(exc)


@router.get("/chat/conversations/{conversation_id}")
def api_get_conversation(
    conversation_id: str,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(require_permissions("chat.conversations")),
):
    try:
        payload, session_update = get_conversation_detail(
            db_path=_db_path(request), request=request, auth=auth, conversation_id=conversation_id
        )
        apply_session_update(response, request, session_update)
        return payload
    except ChatApiError as exc:
        return _error_response(exc)


@router.delete("/chat/conversations/{conversation_id}")
def api_delete_conversation(
    conversation_id: str,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(require_permissions("chat.conversations")),
):
    try:
        payload, session_update = delete_conversation(
            db_path=_db_path(request), request=request, auth=auth, conversation_id=conversation_id
        )
        apply_session_update(response, request, session_update)
        return payload
    except ChatApiError as exc:
        return _error_response(exc)


@router.get("/chat/knowledge-bases")
def api_list_chat_knowledge_bases(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("chat.view")),
):
    try:
        return list_knowledge_bases(db_path=_db_path(request))
    except ChatApiError as exc:
        return _error_response(exc)


@router.get("/chat/available-documents")
def api_list_available_documents(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("chat.view")),
):
    try:
        return list_available_documents(db_path=_db_path(request), query=request.query_params)
    except ChatApiError as exc:
        return _error_response(exc)


@router.post("/chat/query")
def api_chat_query(
    payload: dict[str, object],
    request: Request,
    response: Response,
    auth: AuthContext = Depends(require_permissions("chat.query")),
):
    try:
        result, session_update = query_chat(db_path=_db_path(request), request=request, auth=auth, payload=payload)
        apply_session_update(response, request, session_update)
        return result
    except ChatApiError as exc:
        return _error_response(exc)
