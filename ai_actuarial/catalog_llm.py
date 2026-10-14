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
from ai_actuarial.openai_capabilities import is_openai_gpt6_model

from .catalog import CATEGORY_RULES

logger = logging.getLogger(__name__)


def _uses_default_temperature_only(provider: str | None, model: str | None) -> bool:
    provider_norm = str(provider or "").strip().lower()
    model_norm = str(model or "").strip().lower().split("/")[-1]
    return provider_norm in {"openai", "azure_openai"} and (
        model_norm.startswith("gpt-5") or is_openai_gpt6_model(provider, model)
    )


@dataclass(frozen=True)
class LlmCatalogResult:
    summary: str
    keywords: list[str]
    category: str
    model: str | None = None
    suggested_title: str | None = None
    bilingual_metadata: dict[str, dict[str, Any]] | None = None


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


def _legacy_language(output_language: str, content: str) -> str:
    requested = str(output_language or "").strip().lower()
    if requested in {"en", "zh"}:
        return requested
    han = sum("\u4e00" <= char <= "\u9fff" for char in content)
    latin = sum(char.isascii() and char.isalpha() for char in content)
    return "zh" if han > latin else "en"


def catalog_with_openai(
    *,
    title: str | None,
    content: str,
    custom_system_prompt: str | None = None,
    output_language: str = "bilingual",
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
            in sites.yaml. The bilingual output contract is appended to custom prompts.
        output_language: Legacy projection hint for top-level summary/keywords/title
            fields. The model always generates both Chinese and English packages.

    Notes:
        The default prompt instructs the model to:
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
        raise RuntimeError(f"{env_var} missing for catalog provider '{resolved_provider}'")

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
            "Read the document and produce factual, concise catalog metadata in Chinese and English. "
            "Titles must be self-contained, reflect the document subject, and omit website names and "
            "publication series. Do not invent facts."
        )
    system_prompt += (
        "\n\nMANDATORY BILINGUAL CATALOG CONTRACT:\n"
        'Return valid JSON with exactly one top-level key: "bilingual_metadata". '
        'Its value must have exactly "zh" and "en" objects. Each language object must have '
        'non-empty string fields "title", "summary", and "category", plus a non-empty array '
        'of string "keywords". The title, summary, and keywords must be naturally written in '
        "the named language. Use the same canonical category key in both objects, chosen exactly "
        "from the supplied category list; do not translate category keys. Category may contain "
        'up to three canonical keys separated by "; ". Missing or empty fields are invalid. '
        "Do not use the document language to omit or copy a translation. Output JSON only."
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
        "Categories (choose up to 3 canonical keys and order by relevance):\n"
        + "\n".join(cat_lines)
        + "\n\n"
        + f"Title:\n{safe_title}\n\n"
        + "Content:\n"
        + safe_content
        + "\n\n"
        + 'Return JSON only with this shape: {"bilingual_metadata":{"zh":{"title":"...",'
        '"summary":"...","category":"...","keywords":["..."]},"en":{"title":"...",'
        '"summary":"...","category":"...","keywords":["..."]}}.'
    )

    request_kwargs: dict[str, Any] = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "timeout": timeout_seconds,
    }
    if not _uses_default_temperature_only(resolved_provider, resolved_model):
        request_kwargs["temperature"] = 0.2
    completion = client.chat.completions.create(**request_kwargs)

    content_text = ""
    try:
        content_text = (completion.choices[0].message.content or "").strip()
    except Exception:
        content_text = ""

    payload = _parse_json_object(content_text)
    raw_bilingual = payload.get("bilingual_metadata")
    if not isinstance(raw_bilingual, dict):
        raise ValueError("Catalog model response is missing bilingual_metadata")

    bilingual_metadata: dict[str, dict[str, Any]] = {}
    canonical_categories: dict[str, str] = {}
    for language in ("zh", "en"):
        raw_entry = raw_bilingual.get(language)
        if not isinstance(raw_entry, dict):
            raise ValueError(f"Catalog model response is missing the {language} metadata package")
        title_value = raw_entry.get("title")
        summary_value = raw_entry.get("summary")
        if not isinstance(title_value, str) or not title_value.strip():
            raise ValueError(f"Catalog model response has an empty {language} title")
        if not isinstance(summary_value, str) or not summary_value.strip():
            raise ValueError(f"Catalog model response has an empty {language} summary")
        keywords = _clean_keywords(raw_entry.get("keywords"), max_items=12)
        if not keywords:
            raise ValueError(f"Catalog model response has no {language} keywords")
        selected = _clean_categories(raw_entry.get("category"), allowed=categories, max_items=3)
        if not selected:
            raise ValueError(f"Catalog model response has an invalid {language} category")
        category = "; ".join(selected)
        canonical_categories[language] = category
        bilingual_metadata[language] = {
            "title": re.sub(r"\s+", " ", title_value.strip()),
            "summary": summary_value.strip(),
            "category": category,
            "keywords": keywords,
        }
    if canonical_categories["zh"] != canonical_categories["en"]:
        raise ValueError("Catalog model returned different canonical categories for zh and en")

    legacy_language = _legacy_language(output_language, safe_content)
    legacy_package = bilingual_metadata[legacy_language]
    summary = legacy_package["summary"]
    keywords = legacy_package["keywords"]
    category = legacy_package["category"]
    suggested_title = legacy_package["title"]

    return LlmCatalogResult(
        summary=summary,
        keywords=keywords,
        category=category,
        model=resolved_model,
        suggested_title=suggested_title,
        bilingual_metadata=bilingual_metadata,
    )


def confirm_category_for_summary(
    *,
    summary: str,
    candidate_category: str,
    category_terms: list[str],
    storage: Any | None = None,
) -> bool:
    """Ask the catalog LLM whether a document summary belongs to a candidate category.

    Used by the recategory task's "add" phase: after keyword pre-filtering, this
    makes the final per-item decision from the summary alone. It does not re-generate
    summary/keywords. Returns True only when the model returns an explicit boolean.
    """
    runtime = resolve_ai_function_runtime("catalog", storage=storage)
    resolved_provider = runtime.provider
    resolved_model = runtime.model
    resolved_api_key = runtime.api_key
    resolved_base_url = runtime.base_url
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
        raise RuntimeError(f"{env_var} missing for catalog provider '{resolved_provider}'")

    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Catalog provider requires `openai` package") from exc

    client_kwargs = {"api_key": resolved_api_key}
    if resolved_base_url:
        client_kwargs["base_url"] = resolved_base_url
    client = OpenAI(**client_kwargs)

    terms_hint = ", ".join(str(t) for t in (category_terms or [])[:12] if t)
    system_prompt = (
        "You are a precise document-classification assistant for an actuarial/insurance "
        "knowledge base. Decide whether a document summary belongs to a single candidate "
        'category. Return strict JSON with exactly one key "belongs" (boolean true/false). '
        "Do not invent facts; when in doubt, return false."
    )
    user_prompt = (
        f"Candidate category: {candidate_category}\n"
        + (f"Category keywords: {terms_hint}\n" if terms_hint else "")
        + f"\nSummary:\n{(summary or '').strip()}\n\n"
        + 'Return JSON only: {"belongs": true|false}.'
    )

    request_kwargs: dict[str, Any] = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "timeout": timeout_seconds,
    }
    if not _uses_default_temperature_only(resolved_provider, resolved_model):
        request_kwargs["temperature"] = 0.0
    completion = client.chat.completions.create(**request_kwargs)

    content_text = ""
    try:
        content_text = (completion.choices[0].message.content or "").strip()
    except Exception:
        content_text = ""

    payload = _parse_json_object(content_text)
    belongs = payload.get("belongs")
    return isinstance(belongs, bool) and belongs
