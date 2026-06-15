from __future__ import annotations

from typing import Literal

from .ready_data_tools import search_sections, search_summaries, search_titles, trace_relations


QuestionCategory = Literal["catalog", "locate", "summary", "document_qa"]


def classify_question(question: str) -> QuestionCategory:
    """Classify a user question into the PR3 L0 tool categories."""
    text = str(question or "").strip().lower()
    if not text:
        return "document_qa"

    summary_terms = ("summarize", "summary", "overview", "brief", "概述", "总结", "摘要")
    locate_terms = ("find", "locate", "which document", "titled", "title", "url", "file", "where is", "查找", "定位", "标题")
    catalog_terms = ("catalog", "list all", "all documents", "categories", "show documents", "目录", "清单", "全部文档")

    if any(term in text for term in summary_terms):
        return "summary"
    if any(term in text for term in locate_terms):
        return "locate"
    if any(term in text for term in catalog_terms):
        return "catalog"
    return "document_qa"


__all__ = [
    "QuestionCategory",
    "classify_question",
    "search_sections",
    "search_summaries",
    "search_titles",
    "trace_relations",
]
