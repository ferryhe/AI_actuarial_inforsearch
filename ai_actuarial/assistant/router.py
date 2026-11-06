from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, Request, Response

from ai_actuarial.api.deps import AuthContext, require_permissions
from ai_actuarial.api.routers.assistant_help import _require_enabled
from ai_actuarial.api.services.chat import apply_session_update
from ai_actuarial.assistant.query import (
    REQUEST_SECONDS,
    QueryRequest,
    QueryResponse,
    query_assistant,
    unavailable,
)

router = APIRouter()


@router.post("/assistant/query", response_model=QueryResponse)
async def api_assistant_query(
    payload: QueryRequest,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(require_permissions("chat.query")),
) -> QueryResponse:
    _require_enabled(request)
    request.state.assistant_attempts = 0
    try:
        result, session_update = await asyncio.wait_for(
            asyncio.to_thread(
                query_assistant,
                payload=payload,
                request=request,
                auth=auth,
                deadline=time.monotonic() + REQUEST_SECONDS,
            ),
            timeout=REQUEST_SECONDS,
        )
        apply_session_update(response, request, session_update)
        return result
    except asyncio.TimeoutError:
        return unavailable(
            "usage" if payload.mode == "usage" else "clarify",
            "ASSISTANT_TIMEOUT",
            zh=payload.locale.startswith("zh"),
            attempts=request.state.assistant_attempts,
        )
