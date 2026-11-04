from __future__ import annotations

from urllib.parse import urlsplit

import requests
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from ai_actuarial.article_interpretation_english import (
    read_current_article_identity,
    read_english_interpretations,
)
from ai_actuarial.article_interpretations import (
    article_content_warning_codes,
    InterpretationBodyEditError,
    read_interpretations,
    update_interpretation_body,
)

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
    "body_sha256",
    "china_article_url",
    "references",
    "status",
    "content_warnings",
    "content_warning_acceptance_available",
    "manual_content_accepted_at_utc",
)

_ENGLISH_READER_FIELDS = (
    "interpretation_id",
    "title_en",
    "body_markdown_en",
    "generated_at",
    "file_url",
    "raw_sha256",
    "markdown_sha256",
    "china_article_url",
    "references",
)


def _china_reader_origin(config: dict) -> str | None:
    setting = (config.get("article_interpretation") or {}).get("english_proxy") or {}
    if setting.get("enabled") is not True:
        return None
    origin = str(setting.get("china_origin") or "").rstrip("/")
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        return None
    return origin


def _china_proxy_enabled(config: dict) -> bool:
    setting = (config.get("article_interpretation") or {}).get("english_proxy") or {}
    return setting.get("enabled") is True


def _public_english_item(item: dict) -> dict:
    result = {
        key: item[key] for key in _ENGLISH_READER_FIELDS if key in item and key != "references"
    }
    references = item.get("references")
    if isinstance(references, dict):
        public_references = {
            key: references[key]
            for key in (
                "original_url",
                "original_title",
                "published_time",
                "china_article_url",
                "author",
                "authors",
            )
            if key in references
        }
        source = references.get("source")
        if isinstance(source, dict):
            public_references["source"] = {
                key: source[key] for key in ("name_zh", "name_en") if key in source
            }
        result["references"] = public_references
    return result


def _has_local_manual_edit(request: Request, file_url: str) -> bool:
    return any(
        draft.get("reader_eligible") and draft.get("manual_edit_revision")
        for draft in read_interpretations(_get_db_path(request), file_url=file_url)
    )


def _read_overseas_english(request: Request, file_url: str) -> list[dict]:
    if not file_url:
        return []
    origin = _china_reader_origin(getattr(request.app.state, "site_config", {}))
    if not origin:
        return []
    local_identity = read_current_article_identity(request.app.state.database, file_url)
    if not local_identity:
        return []
    try:
        response = requests.get(
            origin + "/api/article-interpretations",
            params={"file_url": file_url, "locale": "en"},
            timeout=(2.0, 2.0),
            allow_redirects=False,
        )
        if response.status_code != 200:
            return []
        remote = response.json()
    except (requests.RequestException, ValueError):
        return []
    if not isinstance(remote, dict) or not isinstance(remote.get("interpretations"), list):
        return []
    for item in remote["interpretations"]:
        if not isinstance(item, dict) or any(
            item.get(key) != local_identity[key]
            for key in ("file_url", "raw_sha256", "markdown_sha256")
        ):
            continue
        if not all(
            isinstance(item.get(key), str) and item[key] for key in ("title_en", "body_markdown_en")
        ):
            continue
        return [_public_english_item(item)]
    return []


@router.get("/article-interpretations")
def api_article_interpretations(
    request: Request,
    auth: AuthContext = Depends(require_permissions("files.read")),
):
    locale = request.query_params.get("locale", "zh")
    file_url = request.query_params.get("file_url", "")
    if locale == "en":
        config = getattr(request.app.state, "site_config", {})
        if _china_proxy_enabled(config):
            drafts = (
                []
                if _has_local_manual_edit(request, file_url)
                else _read_overseas_english(request, file_url)
            )
        else:
            drafts = read_english_interpretations(_get_db_path(request), file_url=file_url)
        return {"interpretations": [_public_english_item(draft) for draft in drafts]}
    if locale != "zh":
        return {"interpretations": []}
    drafts = read_interpretations(
        _get_db_path(request),
        file_url=file_url,
        interpretation_id=request.query_params.get("interpretation_id", ""),
    )
    current = [draft for draft in drafts if draft.get("reader_eligible")]
    latest = {}
    for draft in current:
        latest.setdefault(draft["file_url"], draft)
    if "markdown.write" in auth.permissions:
        for draft in drafts:
            if (
                draft.get("file_url") not in latest
                and draft.get("is_current")
                and (warning_codes := article_content_warning_codes(draft))
            ):
                latest[draft["file_url"]] = {
                    "interpretation_id": draft["interpretation_id"],
                    "title_zh": "",
                    "body_markdown_zh": "",
                    "generated_at": draft.get("generated_at", ""),
                    "file_url": draft["file_url"],
                    "raw_sha256": draft["raw_sha256"],
                    "markdown_sha256": draft["markdown_sha256"],
                    "body_sha256": draft["body_sha256"],
                    "status": "failed",
                    "content_warnings": warning_codes,
                    "content_warning_acceptance_available": True,
                }
    public_drafts = []
    for draft in latest.values():
        public = {key: draft[key] for key in _READER_FIELDS if key in draft}
        if "content_warnings" in public and not public.get("content_warning_acceptance_available"):
            public["content_warnings"] = article_content_warning_codes(draft)
        public_drafts.append(public)
    return {"interpretations": public_drafts}


@router.post("/article-interpretations/{interpretation_id}/body")
def api_update_article_interpretation_body(
    interpretation_id: str,
    payload: dict,
    request: Request,
    auth: AuthContext = Depends(require_permissions("markdown.write")),
):
    try:
        config = getattr(request.app.state, "site_config", {})
        interpretation_config = config.get("article_interpretation") or {}
        return update_interpretation_body(
            _get_db_path(request),
            interpretation_id=interpretation_id,
            payload=payload,
            actor=str((auth.token or {}).get("subject") or "authenticated-user"),
            environment=interpretation_config.get("environment", "local"),
            china_base_url=interpretation_config.get("china_base_url", "https://aiactuary.cn"),
        )
    except InterpretationBodyEditError as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.code})
