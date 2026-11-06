from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from ai_actuarial.assistant.help import HELP_ID_PATTERN, load_help_sections, search_help

router = APIRouter()
_DOC_ID = rf"^{HELP_ID_PATTERN}$"
_SECTION_ID = rf"^{HELP_ID_PATTERN}$"
_HASH = r"^[a-f0-9]{64}$"


def _require_enabled(request: Request) -> None:
    if not getattr(request.app.state, "assistant_enabled", False):
        raise HTTPException(
            status_code=404, detail={"code": "FEATURE_DISABLED", "message": "Assistant is disabled"}
        )


@router.get("/assistant/help")
def api_search_help(
    request: Request,
    q: str = Query(min_length=1, max_length=500),
    language: str | None = Query(default=None, pattern=r"^(en|zh)$"),
    limit: int = Query(default=5, ge=1, le=10),
) -> dict[str, object]:
    _require_enabled(request)
    results = search_help(q, language=language, limit=limit)
    return {"results": results, "count": len(results)}


@router.get("/assistant/help/section")
def api_get_help_section(
    request: Request,
    doc_id: str = Query(pattern=_DOC_ID),
    section_id: str = Query(pattern=_SECTION_ID),
    language: str = Query(pattern=r"^(en|zh)$"),
    title: str = Query(min_length=1, max_length=160),
    source_version: str = Query(min_length=1, max_length=40),
    content_hash: str = Query(pattern=_HASH),
) -> dict[str, str]:
    _require_enabled(request)
    sections = load_help_sections()
    existing = next(
        (item for item in sections if item.doc_id == doc_id and item.section_id == section_id),
        None,
    )
    if existing is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "HELP_NOT_FOUND", "message": "Help section was not found"},
        )
    reference = {
        "doc_id": doc_id,
        "section_id": section_id,
        "language": language,
        "title": title,
        "source_version": source_version,
        "content_hash": content_hash,
    }
    if any(existing.reference()[field] != reference[field] for field in reference):
        raise HTTPException(
            status_code=410,
            detail={
                "code": "HELP_REFERENCE_EXPIRED",
                "message": "Help reference expired; search again",
            },
        )
    return {**existing.reference(), "content": existing.content}
