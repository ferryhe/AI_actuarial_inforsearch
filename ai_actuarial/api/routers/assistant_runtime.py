"""Admin-only contract path for the independently installed Assistant Feature."""

from __future__ import annotations

import asyncio
import time
from threading import Event
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_actuarial.api.deps import AuthContext, require_permissions
from ai_actuarial.api.routers.assistant_help import _require_enabled
from ai_actuarial.api.services.chat import apply_session_update
from ai_actuarial.assistant.query import FeatureResponse, REQUEST_SECONDS

router = APIRouter()


class RuntimePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    message: str = Field(min_length=1, max_length=4000)
    locale: Literal["en", "zh", "zh-CN"] = "en"

    @field_validator("message")
    @classmethod
    def valid_message(cls, value: str) -> str:
        if not value.strip() or "\0" in value:
            raise ValueError("A nonempty message without NUL is required")
        return value


@router.post("/assistant/runtime/query", response_model=FeatureResponse)
async def api_assistant_runtime_query(
    payload: RuntimePayload,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(require_permissions("config.write")),
) -> FeatureResponse:
    _require_enabled(request)
    feature = getattr(request.app.state, "assistant_feature", None)
    if feature is None:
        raise HTTPException(status_code=503, detail="Assistant Feature is unavailable")
    cancelled = Event()
    try:
        outcome = await asyncio.wait_for(
            asyncio.to_thread(
                feature.query,
                request=request,
                auth=auth,
                message=payload.message,
                locale=payload.locale,
                cancelled=cancelled,
                deadline=time.monotonic() + REQUEST_SECONDS,
            ),
            timeout=REQUEST_SECONDS,
        )
    except asyncio.TimeoutError:
        cancelled.set()
        return FeatureResponse(
            intent="clarify",
            answer=(
                "助手超时，请稍后重试。"
                if payload.locale.startswith("zh")
                else "The assistant timed out. Please retry."
            ),
            availability="error",
            error_code="ASSISTANT_TIMEOUT",
            stop_reason="error",
        )
    except asyncio.CancelledError:
        cancelled.set()
        raise
    apply_session_update(response, request, outcome.session_update)
    return outcome.response
