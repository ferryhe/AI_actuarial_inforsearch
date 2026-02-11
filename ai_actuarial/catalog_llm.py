from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from config.settings import get_settings

from .catalog import CATEGORY_RULES

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LlmCatalogResult:
    summary: str
    keywords: list[str]
    category: str
    model: str | None = None


def _clean_keywords(items: Any, *, max_items: int = 12) -> list[str]:
    out: list[str] = []
    if isinstance(items, str):
        # Allow comma/semicolon/newline delimited strings.
        parts = re.split(r"[,\n;]+", items)
        items = [p.strip() for p in parts if p.strip()]
    if not isinstance(items, list):
        return out
    for v in items:
        if not isinstance(v, str):
            continue
        s = v.strip()
        if not s:
            continue
        s = re.sub(r"\s+", " ", s)
        if s.lower() not in {k.lower() for k in out}:
            out.append(s)
        if len(out) >= max_items:
            break
    return out


def _parse_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        # Best-effort: extract the first {...} block.
        m = re.search(r"\{.*\}", text, flags=re.S)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}


def catalog_with_openai(*, title: str | None, content: str) -> LlmCatalogResult:
    """Use OpenAI Chat Completions to generate summary/keywords/category.

    Requires `OPENAI_API_KEY` in `.env` (read via `config.settings`).
    """
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY missing")

    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("OpenAI catalog provider requires `openai` package") from exc

    categories = sorted({*(CATEGORY_RULES or {}).keys(), "Other"})
    model = settings.openai_default_model
    client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)

    safe_title = (title or "").strip()
    safe_content = (content or "").strip()
    # Keep inputs bounded. The caller also bounds extraction, but markdown can still be large.
    if len(safe_content) > 20000:
        safe_content = safe_content[:20000]

    system_prompt = (
        "You are a careful document cataloging assistant for an actuarial/insurance knowledge base. "
        "Your job: read the document content and output a STRICT JSON object with:\n"
        "- summary: concise, factual, 3-5 bullet points or a short paragraph (<= 120 words)\n"
        "- keywords: 8-12 keyphrases (strings), no duplicates\n"
        "- category: pick exactly one category from the provided list\n"
        "Rules: do not invent facts. If content is insufficient, use category=\"Other\" and keep summary short."
    )

    cat_lines: list[str] = []
    for c in categories:
        if c == "Other":
            cat_lines.append("- Other")
            continue
        terms = list((CATEGORY_RULES or {}).get(c) or [])
        hint = ", ".join(str(t) for t in terms[:8] if t)
        if hint:
            cat_lines.append(f"- {c} (examples: {hint})")
        else:
            cat_lines.append(f"- {c}")

    user_prompt = (
        "Categories (choose exactly one):\n"
        + "\n".join(cat_lines)
        + "\n\n"
        + f"Title:\n{safe_title}\n\n"
        + "Content:\n"
        + safe_content
        + "\n\n"
        + "Return JSON only."
    )

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
        timeout=settings.openai_timeout_seconds,
    )

    content_text = ""
    try:
        content_text = (completion.choices[0].message.content or "").strip()
    except Exception:
        content_text = ""

    payload = _parse_json_object(content_text)
    summary = str(payload.get("summary") or "").strip()
    keywords = _clean_keywords(payload.get("keywords"), max_items=12)
    category = str(payload.get("category") or "Other").strip() or "Other"
    if category not in categories:
        category = "Other"

    return LlmCatalogResult(summary=summary, keywords=keywords, category=category, model=model)
