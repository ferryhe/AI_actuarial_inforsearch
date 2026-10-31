from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ai_actuarial.article_interpretations import read_interpretations

from ..deps import AuthContext, require_permissions
from .read import _get_db_path

router = APIRouter()

_READER_FIELDS = (
    "interpretation_id",
    "title_zh",
    "body_markdown_zh",
    "generated_at",
    "file_url",
    "raw_sha256",
    "markdown_sha256",
    "china_article_url",
    "references",
)


@router.get("/article-interpretations")
def api_article_interpretations(
    request: Request,
    _auth: AuthContext = Depends(require_permissions("files.read")),
):
    drafts = read_interpretations(
        _get_db_path(request),
        file_url=request.query_params.get("file_url", ""),
        interpretation_id=request.query_params.get("interpretation_id", ""),
    )
    current = [draft for draft in drafts if draft.get("reader_eligible")]
    latest = {}
    for draft in current:
        latest.setdefault(draft["file_url"], draft)
    return {
        "interpretations": [
            {key: draft[key] for key in _READER_FIELDS if key in draft}
            for draft in latest.values()
        ]
    }
