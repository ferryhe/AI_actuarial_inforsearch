from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..deps import AuthContext, require_permissions
from ..services.weekly_updates import (
    WeeklySnapshotNotFoundError,
    get_latest_weekly_update_summary,
    get_weekly_update_summary_detail,
    get_weekly_update_summary_files,
    list_weekly_update_summaries,
    parse_weekly_update_files_query,
    parse_weekly_update_list_query,
)
from .read import _get_db_path

router = APIRouter()


class WeeklySnapshotSummaryModel(BaseModel):
    id: str
    period_start: str
    period_end: str
    generated_at: str
    status: Literal["published", "superseded", "failed"]
    file_count: int
    metadata: dict[str, Any]


class WeeklySnapshotDetailModel(WeeklySnapshotSummaryModel):
    summary_markdown: str


class WeeklySnapshotFileModel(BaseModel):
    url: str
    title: str
    original_filename: str | None
    first_seen: str


class WeeklySnapshotListModel(BaseModel):
    summaries: list[WeeklySnapshotSummaryModel]
    total: int
    limit: int
    offset: int


class WeeklySnapshotLatestModel(BaseModel):
    summary: WeeklySnapshotSummaryModel | None


class WeeklySnapshotDetailEnvelopeModel(BaseModel):
    summary: WeeklySnapshotDetailModel


class WeeklySnapshotFilesModel(BaseModel):
    snapshot_id: str
    files: list[WeeklySnapshotFileModel]
    total: int
    limit: int
    offset: int
    included_count: int
    truncated: bool


def _not_found_response() -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "Weekly snapshot not found"})


@router.get("/weekly-updates", response_model=WeeklySnapshotListModel)
def api_weekly_updates(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("files.read")),
) -> dict[str, object]:
    query = parse_weekly_update_list_query(request.query_params)
    return list_weekly_update_summaries(db_path=_get_db_path(request), **query)


@router.get("/weekly-updates/latest", response_model=WeeklySnapshotLatestModel)
def api_weekly_updates_latest(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("files.read")),
) -> dict[str, object]:
    return get_latest_weekly_update_summary(db_path=_get_db_path(request))


@router.get(
    "/weekly-updates/{snapshot_id}/files",
    response_model=WeeklySnapshotFilesModel,
)
def api_weekly_update_files(
    snapshot_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_permissions("files.read")),
):
    query = parse_weekly_update_files_query(request.query_params)
    try:
        return get_weekly_update_summary_files(
            db_path=_get_db_path(request),
            snapshot_id=snapshot_id,
            **query,
        )
    except WeeklySnapshotNotFoundError:
        return _not_found_response()


@router.get(
    "/weekly-updates/{snapshot_id}",
    response_model=WeeklySnapshotDetailEnvelopeModel,
)
def api_weekly_update_detail(
    snapshot_id: str,
    request: Request,
    _auth: AuthContext = Depends(require_permissions("files.read")),
):
    try:
        return get_weekly_update_summary_detail(
            db_path=_get_db_path(request),
            snapshot_id=snapshot_id,
        )
    except WeeklySnapshotNotFoundError:
        return _not_found_response()
