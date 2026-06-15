from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .tools import QuestionCategory, classify_question


ToolName = Literal[
    "search_summaries",
    "search_titles",
    "search_sections",
    "trace_relations",
    "search_formula_cards",
    "search_structured_tables",
    "search_calculation_terms",
]

_KNOWN_CATEGORIES: set[str] = {"catalog", "locate", "summary", "document_qa"}
_L1_ARTIFACTS = {"title_aliases.jsonl", "sections_structured.jsonl", "relations_graph.json"}
_L2_ARTIFACTS = {"formula_cards.jsonl", "tables_structured.jsonl", "calculation_terms.jsonl"}


@dataclass(frozen=True)
class ToolStep:
    tool_name: ToolName
    category: QuestionCategory
    limit: int = 10


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _bounded_limit(value: int | None) -> int:
    try:
        parsed = int(value if value is not None else 10)
    except (TypeError, ValueError):
        parsed = 10
    return max(1, min(parsed, 100))


def _read_manifest(output_dir: str | Path | None) -> dict[str, Any]:
    if not output_dir:
        return {}
    try:
        with (Path(output_dir) / "ready_data_manifest.json").open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _artifact_names(manifest: dict[str, Any]) -> set[str]:
    artifact_files = manifest.get("artifact_files") or []
    names: set[str] = set()
    if isinstance(artifact_files, dict):
        for key, value in artifact_files.items():
            names.add(Path(str(key)).name)
            names.add(Path(str(value)).name)
    elif isinstance(artifact_files, list):
        names.update(Path(str(item)).name for item in artifact_files if _norm(item))
    return {name for name in names if name}


def _has_l1_artifacts(output_dir: str | Path | None, manifest: dict[str, Any]) -> bool:
    if _artifact_names(manifest) & _L1_ARTIFACTS:
        return True
    if not output_dir:
        return False
    root = Path(output_dir)
    return any((root / artifact).is_file() for artifact in _L1_ARTIFACTS)


def _has_l2_artifacts(output_dir: str | Path | None, manifest: dict[str, Any]) -> bool:
    if _artifact_names(manifest) & _L2_ARTIFACTS:
        return True
    if not output_dir:
        return False
    root = Path(output_dir)
    return any((root / artifact).is_file() for artifact in _L2_ARTIFACTS)


def _resolve_category(query: str, category: str | None) -> QuestionCategory:
    requested = _norm(category).lower()
    if requested in _KNOWN_CATEGORIES:
        return requested  # type: ignore[return-value]
    return classify_question(query)


def _base_tool_names(category: QuestionCategory) -> list[ToolName]:
    if category == "locate":
        return ["search_titles", "search_summaries"]
    if category == "summary":
        return ["search_summaries", "search_titles"]
    if category == "catalog":
        return ["search_titles", "search_summaries"]
    return ["search_summaries", "search_titles"]


def _add_regulation_tools(tool_names: list[ToolName], category: QuestionCategory) -> list[ToolName]:
    if category == "document_qa":
        ordered = ["search_sections", *tool_names, "trace_relations"]
    else:
        ordered = [tool_names[0], "search_sections", *tool_names[1:], "trace_relations"] if tool_names else [
            "search_sections",
            "trace_relations",
        ]
    deduped: list[ToolName] = []
    for tool_name in ordered:
        if tool_name not in deduped:
            deduped.append(tool_name)
    return deduped


def _add_formula_tools(tool_names: list[ToolName]) -> list[ToolName]:
    ordered: list[ToolName] = [
        "search_formula_cards",
        "search_calculation_terms",
        "search_structured_tables",
        *tool_names,
    ]
    deduped: list[ToolName] = []
    for tool_name in ordered:
        if tool_name not in deduped:
            deduped.append(tool_name)
    return deduped


def plan_tool_steps(
    query: str,
    *,
    category: str | None = None,
    profile: str | None = None,
    output_dir: str | Path | None = None,
    limit: int | None = None,
) -> list[ToolStep]:
    """Plan deterministic ready-data tool calls for an Agentic RAG query."""
    query_text = _norm(query)
    resolved_category = _resolve_category(query_text, category)
    manifest = _read_manifest(output_dir)
    resolved_profile = (_norm(profile) or _norm(manifest.get("profile")) or "general").lower()
    formula_ready = resolved_profile == "formula" or _has_l2_artifacts(output_dir, manifest)
    regulation_ready = resolved_profile in {"regulation", "formula"} or _has_l1_artifacts(output_dir, manifest) or formula_ready
    tool_names = _base_tool_names(resolved_category)
    if regulation_ready:
        tool_names = _add_regulation_tools(tool_names, resolved_category)
    if formula_ready:
        tool_names = _add_formula_tools(tool_names)
    step_limit = _bounded_limit(limit)
    return [ToolStep(tool_name=tool_name, category=resolved_category, limit=step_limit) for tool_name in tool_names]


__all__ = ["ToolName", "ToolStep", "plan_tool_steps"]
