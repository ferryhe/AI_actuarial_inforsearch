from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .planner import ToolStep, plan_tool_steps
from .ready_data_tools import search_sections, search_summaries, search_titles, trace_relations


NO_EVIDENCE_ANSWER = "No evidence found in ready_data for this query."

_TOOL_FUNCTIONS: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "search_summaries": search_summaries,
    "search_titles": search_titles,
    "search_sections": search_sections,
    "trace_relations": trace_relations,
}


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _bounded_limit(value: int | None) -> int:
    try:
        parsed = int(value if value is not None else 10)
    except (TypeError, ValueError):
        parsed = 10
    return max(1, min(parsed, 100))


def _trace_entry(step: ToolStep, *, status: str, result_count: int = 0, error: str | None = None) -> dict[str, Any]:
    return {
        "tool_name": step.tool_name,
        "status": status,
        "result_count": int(result_count),
        "error": error,
    }


def _evidence_key(item: dict[str, Any]) -> tuple[str, ...]:
    return (
        _norm(item.get("tool")),
        _norm(item.get("source")),
        _norm(item.get("doc_id")),
        _norm(item.get("section_id")),
        _norm(item.get("relation_type")),
        _norm(item.get("target_id")),
        _norm(item.get("file_url")),
        _norm(item.get("title")),
    )


def _evidence_label(item: dict[str, Any]) -> str:
    title = _norm(item.get("title"))
    heading = _norm(item.get("heading") or item.get("section_heading"))
    relation_type = _norm(item.get("relation_type"))
    if title and heading:
        return f"{title} / {heading}"
    if title:
        return title
    if heading:
        return heading
    if relation_type:
        target_id = _norm(item.get("target_id"))
        return f"{relation_type} {target_id}".strip()
    return _norm(item.get("doc_id") or item.get("file_url") or item.get("source")) or "evidence"


def _build_answer(query: str, evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return NO_EVIDENCE_ANSWER
    labels: list[str] = []
    for item in evidence:
        label = _evidence_label(item)
        if label not in labels:
            labels.append(label)
        if len(labels) >= 3:
            break
    suffix = "; ".join(labels)
    return f'Found {len(evidence)} evidence item(s) in ready_data for "{query}". Top evidence: {suffix}.'


def run_agentic_rag_loop(
    *,
    query: str,
    output_dir: str | Path,
    profile: str = "general",
    kb_id: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Run a deterministic local ready-data Agentic RAG loop without provider calls."""
    query_text = _norm(query)
    step_limit = _bounded_limit(limit)
    output_dir_text = str(Path(output_dir))
    steps = plan_tool_steps(query_text, profile=profile, output_dir=output_dir, limit=step_limit)
    evidence: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    tool_trace: list[dict[str, Any]] = []

    for step in steps:
        tool_fn = _TOOL_FUNCTIONS.get(step.tool_name)
        if tool_fn is None:
            tool_trace.append(_trace_entry(step, status="error", error="tool is not registered"))
            continue
        try:
            results = tool_fn(query_text, output_dir=output_dir, limit=step.limit)
        except Exception as exc:  # noqa: BLE001
            tool_trace.append(_trace_entry(step, status="error", error=str(exc)))
            continue
        tool_trace.append(_trace_entry(step, status="ok", result_count=len(results)))
        for result in results:
            item = dict(result)
            item["tool"] = step.tool_name
            key = _evidence_key(item)
            if key in seen:
                continue
            seen.add(key)
            evidence.append(item)

    category = steps[0].category if steps else "document_qa"
    metadata = {
        "category": category,
        "limit": step_limit,
        "step_count": len(steps),
        "evidence_count": len(evidence),
        "tool_trace": tool_trace,
    }
    return {
        "query": query_text,
        "answer": _build_answer(query_text, evidence),
        "evidence": evidence,
        "results": evidence,
        "metadata": metadata,
        "tool_trace": tool_trace,
        "kb_id": _norm(kb_id) or None,
        "profile": _norm(profile).lower() or "general",
        "output_dir": output_dir_text,
    }


__all__ = ["NO_EVIDENCE_ANSWER", "run_agentic_rag_loop"]
