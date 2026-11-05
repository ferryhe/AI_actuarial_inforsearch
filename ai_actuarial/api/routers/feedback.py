from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, ValidationError

from ai_actuarial.feedback.store import (
    FeedbackConflict,
    FeedbackRequest,
    FeedbackStatus,
    list_feedback,
    submit_feedback,
    update_feedback_status,
)

from ..deps import AuthContext, get_auth_context, require_authenticated_permissions

router = APIRouter()
logger = logging.getLogger(__name__)


def _error(status: int, code: str, message: str):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def feedback_disabled_response():
    return _error(404, "FEATURE_DISABLED", "Feedback is disabled")


@router.post("/feedback", status_code=201)
def api_submit_feedback(request: Request, payload: object = Body(...)):
    if not getattr(request.app.state, "feedback_enabled", False):
        return feedback_disabled_response()
    try:
        submission = FeedbackRequest.model_validate(payload)
    except ValidationError:
        return _error(422, "INVALID_REQUEST", "Invalid feedback request")
    try:
        context = get_auth_context(request)
        user_id = (context.token or {}).get("_email_user_id")
        return submit_feedback(
            request.app.state.database,
            submission,
            site_key=request.app.state.feedback_site_key,
            user_id=user_id,
        )
    except FeedbackConflict as exc:
        return _error(409, "IDEMPOTENCY_CONFLICT", str(exc))
    except Exception:
        logger.exception("Feedback submission failed")
        return _error(503, "FEEDBACK_UNAVAILABLE", "Feedback could not be recorded; retry later")


@router.get("/admin/feedback")
def api_list_feedback(
    request: Request,
    status: FeedbackStatus | None = None,
    site_key: Annotated[str | None, Query(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")] = None,
    cursor: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    _auth: AuthContext = Depends(require_authenticated_permissions("feedback.read")),
):
    return list_feedback(
        request.app.state.database, status=status, site_key=site_key, cursor=cursor, limit=limit
    )


class StatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: FeedbackStatus


@router.patch("/admin/feedback/{feedback_id}")
def api_update_feedback(
    feedback_id: UUID,
    payload: StatusUpdate,
    request: Request,
    _auth: AuthContext = Depends(require_authenticated_permissions("feedback.manage")),
):
    item = update_feedback_status(request.app.state.database, feedback_id, payload.status)
    if item is None:
        return _error(404, "FEEDBACK_NOT_FOUND", "Feedback was not found")
    return item
