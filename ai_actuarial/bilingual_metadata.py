"""Small helpers for the persisted Chinese/English catalog contract."""

from __future__ import annotations

import json
from typing import Any

BILINGUAL_LANGUAGES = ("zh", "en")


def parse_bilingual_metadata(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return {}
    return value if isinstance(value, dict) else {}


def with_shared_category(metadata: dict[str, Any], category: str) -> dict[str, Any]:
    updated = dict(metadata)
    for language in BILINGUAL_LANGUAGES:
        package = metadata.get(language)
        if isinstance(package, dict):
            updated[language] = {**package, "category": category}
    return updated


def is_complete_bilingual_metadata(value: object) -> bool:
    metadata = parse_bilingual_metadata(value)
    category_by_language: dict[str, str] = {}
    for language in BILINGUAL_LANGUAGES:
        entry = metadata.get(language)
        if not isinstance(entry, dict):
            return False
        if any(
            not isinstance(entry.get(field), str) or not entry[field].strip()
            for field in ("title", "summary", "category")
        ):
            return False
        category_by_language[language] = entry["category"].strip()
        keywords = entry.get("keywords")
        if not isinstance(keywords, list) or not any(
            isinstance(keyword, str) and keyword.strip() for keyword in keywords
        ):
            return False
    return category_by_language["zh"] == category_by_language["en"]
