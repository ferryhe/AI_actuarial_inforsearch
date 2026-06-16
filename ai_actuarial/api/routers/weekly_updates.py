from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..deps import AuthContext, require_permissions
from ..services.weekly_updates import (
    get_latest_weekly_update_summary,
    list_weekly_update_summaries,
    parse_weekly_update_list_query,
)
from .read import _get_db_path

router = APIRouter()


@router.get("/weekly-updates")
def api_weekly_updates(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("files.read")),
) -> dict[str, object]:
    query = parse_weekly_update_list_query(request.query_params)
    return list_weekly_update_summaries(db_path=_get_db_path(request), **query)


@router.get("/weekly-updates/latest")
def api_weekly_updates_latest(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("files.read")),
) -> dict[str, object]:
    return get_latest_weekly_update_summary(db_path=_get_db_path(request))
