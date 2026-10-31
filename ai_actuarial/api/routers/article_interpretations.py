from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ai_actuarial.article_interpretations import read_interpretations

from ..deps import AuthContext, require_permissions
from .read import _get_db_path

router = APIRouter()


@router.get("/article-interpretations")
def api_article_interpretations(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("files.read")),
):
    return {
        "interpretations": read_interpretations(
            _get_db_path(request),
            file_url=request.query_params.get("file_url", ""),
            interpretation_id=request.query_params.get("interpretation_id", ""),
        )
    }
