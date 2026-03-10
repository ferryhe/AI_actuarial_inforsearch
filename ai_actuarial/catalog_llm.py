from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from ai_actuarial.ai_runtime import (
    get_provider_api_key_env_var,
    is_catalog_provider_supported,
    resolve_ai_function_runtime,
)

from .catalog import CATEGORY_RULES

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LlmCatalogResult:
    summary: str
    keywords: list[str]
    category: str
    model: str | None = None
    suggested_title: str | None = None


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


def _clean_categories(items: Any, *, allowed: list[str], max_items: int = 3) -> list[str]:
    out: list[str] = []
    if isinstance(items, str):
        parts = re.split(r"[,\n;|]+", items)
        items = [p.strip() for p in parts if p.strip()]
    if not isinstance(items, list):
        return out
    allowed_lut = {a.lower(): a for a in allowed}
    for raw in items:
        if not isinstance(raw, str):
            continue
        key = raw.strip().lower()
        if not key:
            continue
        canonical = allowed_lut.get(key)
        if not canonical:
            continue
        if canonical not in out:
            out.append(canonical)
        if len(out) >= max_items:
            break
    return out


def catalog_with_openai(
    *,
    title: str | None,
    content: str,
    custom_system_prompt: str | None = None,
    output_language: str = "auto",
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    storage: Any | None = None,
) -> LlmCatalogResult:
    """Use an OpenAI-compatible chat completion API for catalog generation.

    Args:
        title: Optional existing document title used as a context hint.
        content: Document text to catalog.
        custom_system_prompt: Optional system prompt override stored in ai_config.catalog
            in sites.yaml. When provided, replaces the built-in default prompt entirely
            (output_language is still appended to custom prompts).
        output_language: Language for summary/keywords/suggested_title output.
            ``"auto"`` (default) lets the LLM match the document language.
            ``"en"`` forces English output.
            ``"zh"`` forces Chinese output.
            Categories are always returned as the fixed English identifiers regardless
            of this setting, so no category-matching issues arise.

    Notes:
        The default prompt instructs the model to:
        - Write the summary and suggested_title in the same language as the document content
          (unless output_language overrides this).
        - Generate a self-contained title that reflects the document's subject matter, not the
          source website name or publication series header.
        - Use specific domain keyphrases for keywords, avoiding generic words like 'report'.
    """
    runtime = resolve_ai_function_runtime(
        "catalog",
        storage=storage,
        provider_override=provider,
        model_override=model,
    )
    resolved_provider = runtime.provider
    resolved_model = model or runtime.model
    resolved_api_key = api_key or runtime.api_key
    resolved_base_url = base_url or runtime.base_url
    raw_timeout = runtime.raw_config.get("timeout_seconds")
    try:
        timeout_seconds = (
            float(raw_timeout)
            if raw_timeout not in (None, "")
            else float(str(os.getenv("OPENAI_TIMEOUT_SECONDS") or "60").strip())
        )
    except (TypeError, ValueError):
        timeout_seconds = 60.0

    if not is_catalog_provider_supported(resolved_provider):
        raise RuntimeError(
            f"Catalog provider '{resolved_provider}' is not supported by the runtime"
        )
    if not resolved_api_key:
        env_var = get_provider_api_key_env_var(resolved_provider) or "API_KEY"
        raise RuntimeError(
            f"{env_var} missing for catalog provider '{resolved_provider}'"
        )

    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Catalog provider requires `openai` package") from exc

    categories = sorted({*(CATEGORY_RULES or {}).keys(), "Other"})
    client_kwargs = {"api_key": resolved_api_key}
    if resolved_base_url:
        client_kwargs["base_url"] = resolved_base_url
    client = OpenAI(**client_kwargs)

    safe_title = (title or "").strip()
    safe_content = (content or "").strip()
    # Keep inputs bounded. The caller also bounds extraction, but markdown can still be large.
    if len(safe_content) > 20000:
        safe_content = safe_content[:20000]

    if custom_system_prompt and custom_system_prompt.strip():
        system_prompt = custom_system_prompt.strip()
    else:
        system_prompt = (
            "You are a precise document cataloging assistant for an actuarial/insurance knowledge base. "
            "Read the document and return a STRICT JSON object with exactly these keys:\n"
            "- summary: factual summary in 3-5 concise bullet points or a short paragraph (≤300 words). "
            "Write the summary in the same language as the document content.\n"
            "- keywords: 8-12 specific keyphrases (strings), no generic words like 'report' or 'document', "
            "no duplicates, focused on the core topics covered.\n"
            "- categories: array of 1-3 most relevant categories from the provided list, "
            "ordered by relevance (most relevant first). "
            "Always return category names exactly as given — do NOT translate them.\n"
            "- suggested_title: a concise, self-contained descriptive title for the document (≤15 words, "
            "plain text, no markdown, no source-site name). "
            "The title must reflect the document's actual subject matter — not the website name, "
            "publication series, or section header. "
            "If the document is primarily in Chinese, write the title in Chinese. "
            "If the document is primarily in English, write the title in English.\n"
            "Rules: do not invent facts. "
            "If content is insufficient, return categories=[\"Other\"] and keep summary short. "
            "Output valid JSON only — no code fences, no extra text."
        )

    # Append a language-override instruction when the caller requests a specific language.
    # This supplements both the default prompt and any custom prompt so the user's
    # language choice is always honoured.
    lang_norm = (output_language or "auto").strip().lower()
    if lang_norm == "en":
        system_prompt += (
            "\n\nOUTPUT LANGUAGE OVERRIDE: Write the summary, keywords, and suggested_title "
            "in English, regardless of the document's original language."
        )
    elif lang_norm == "zh":
        system_prompt += (
            "\n\n输出语言要求：无论文档原始语言是什么，summary（摘要）、keywords（关键词）和 "
            "suggested_title（建议标题）均必须使用中文输出。"
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
        "Categories (choose 1-3 and order by relevance):\n"
        + "\n".join(cat_lines)
        + "\n\n"
        + f"Title:\n{safe_title}\n\n"
        + "Content:\n"
        + safe_content
        + "\n\n"
        + "Return JSON only, with keys: summary, keywords, categories, suggested_title."
    )

    completion = client.chat.completions.create(
        model=resolved_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
        timeout=timeout_seconds,
    )

    content_text = ""
    try:
        content_text = (completion.choices[0].message.content or "").strip()
    except Exception:
        content_text = ""

    payload = _parse_json_object(content_text)
    summary = str(payload.get("summary") or "").strip()
    keywords = _clean_keywords(payload.get("keywords"), max_items=12)
    raw_categories = payload.get("categories")
    if raw_categories is None:
        raw_categories = payload.get("category")
    selected = _clean_categories(raw_categories, allowed=categories, max_items=3)
    if not selected:
        selected = ["Other"]
    category = "; ".join(selected[:3])
    suggested_title = str(payload.get("suggested_title") or "").strip() or None

    return LlmCatalogResult(
        summary=summary,
        keywords=keywords,
        category=category,
        model=resolved_model,
        suggested_title=suggested_title,
    )
