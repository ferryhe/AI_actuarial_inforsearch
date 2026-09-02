from __future__ import annotations

import math
from typing import Any

RETRIEVAL_METHODS = {
    "vector",
    "summaries",
    "titles",
    "sections",
    "relations",
    "formulas",
    "tables",
    "calculation_terms",
    "other",
}

_TOOL_METHODS = {
    "search_summaries": "summaries",
    "search_titles": "titles",
    "search_sections": "sections",
    "trace_relations": "relations",
    "search_formula_cards": "formulas",
    "search_structured_tables": "tables",
    "search_calculation_terms": "calculation_terms",
}

_SOURCE_METHODS = {
    "vector": "vector",
    "similarity": "vector",
    "doc_summaries": "summaries",
    "doc_catalog_summary": "summaries",
    "summary": "summaries",
    "title_aliases": "titles",
    "title_catalog": "titles",
    "doc_catalog_title": "titles",
    "sections": "sections",
    "sections_structured": "sections",
    "relations_graph": "relations",
    "formula_cards": "formulas",
    "tables_structured": "tables",
    "calculation_terms": "calculation_terms",
}


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_semantic_relevance(value: Any) -> int | None:
    score = _finite_number(value)
    if score is None:
        return None
    return int(round(max(0.0, min(score, 1.0)) * 100))


def normalize_keyword_relevance(value: Any, theoretical_max: Any) -> int | None:
    score = _finite_number(value)
    maximum = _finite_number(theoretical_max)
    if score is None or maximum is None or maximum <= 0:
        return None
    return int(round(max(0.0, min(score / maximum, 1.0)) * 100))


def normalize_percentage(value: Any) -> int | None:
    score = _finite_number(value)
    if score is None:
        return None
    return int(round(max(0.0, min(score, 100.0))))


def normalize_retrieval_method(*, source: Any = None, tool: Any = None, method: Any = None) -> str:
    method_text = str(method or "").strip().lower()
    if method_text:
        return method_text if method_text in RETRIEVAL_METHODS else "other"
    source_text = str(source or "").strip().lower().replace(" ", "_")
    source_method = _SOURCE_METHODS.get(source_text)
    if source_method:
        return source_method
    tool_text = str(tool or "").strip().lower()
    if tool_text in _TOOL_METHODS:
        return _TOOL_METHODS[tool_text]
    return "other"


def build_retrieval_indicators(
    *,
    similarity_score: Any = None,
    semantic_relevance_100: Any = None,
    keyword_score: Any = None,
    keyword_max: Any = None,
    keyword_relevance_100: Any = None,
    source: Any = None,
    tool: Any = None,
    retrieval_method: Any = None,
) -> dict[str, int | str | None]:
    semantic_relevance = normalize_percentage(semantic_relevance_100)
    if semantic_relevance_100 is None:
        semantic_relevance = normalize_semantic_relevance(similarity_score)
    keyword_relevance = normalize_percentage(keyword_relevance_100)
    if keyword_relevance is None and keyword_relevance_100 is None:
        keyword_relevance = normalize_keyword_relevance(keyword_score, keyword_max)
    return {
        "semantic_relevance_100": semantic_relevance,
        "keyword_relevance_100": keyword_relevance,
        "retrieval_method": normalize_retrieval_method(
            source=source,
            tool=tool,
            method=retrieval_method,
        ),
    }


__all__ = [
    "RETRIEVAL_METHODS",
    "build_retrieval_indicators",
    "normalize_keyword_relevance",
    "normalize_percentage",
    "normalize_retrieval_method",
    "normalize_semantic_relevance",
]
