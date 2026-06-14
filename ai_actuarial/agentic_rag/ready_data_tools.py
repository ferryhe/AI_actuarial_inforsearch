from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _tokens(query: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for token in _WORD_RE.findall(query.lower()):
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return out


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
    except OSError:
        return []
    return rows


def _safe_child_path(root: Path, value: Any, default_name: str) -> Path:
    root_resolved = root.resolve()
    raw = str(value or default_name).strip()
    candidate = Path(raw)
    if candidate.is_absolute():
        return root_resolved / default_name
    resolved = (root_resolved / candidate).resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        return root_resolved / default_name
    return resolved


def _artifact_path(output_dir: Path, manifest: dict[str, Any], default_name: str) -> Path:
    artifact_files = manifest.get("artifact_files") or []
    if isinstance(artifact_files, dict):
        value = artifact_files.get(default_name) or artifact_files.get(default_name.replace(".jsonl", ""))
        if value:
            return _safe_child_path(output_dir, value, default_name)
    if isinstance(artifact_files, list):
        for item in artifact_files:
            if isinstance(item, str) and Path(item).name == default_name:
                return _safe_child_path(output_dir, item, default_name)
    return _safe_child_path(output_dir, default_name, default_name)


def _load_ready_data(output_dir: str | Path) -> dict[str, Any] | None:
    root = Path(output_dir)
    manifest = _read_json(root / "ready_data_manifest.json")
    if not manifest:
        return None
    catalog = _read_jsonl(_artifact_path(root, manifest, "doc_catalog.jsonl"))
    if not catalog:
        return None
    summaries_path = _artifact_path(root, manifest, "doc_summaries.jsonl")
    summary_rows = _read_jsonl(summaries_path)
    source = "doc_summaries" if summary_rows else "doc_catalog"
    sections = _read_jsonl(_artifact_path(root, manifest, "sections.jsonl"))
    return {
        "manifest": manifest,
        "catalog": catalog,
        "summaries": summary_rows,
        "summary_source": source,
        "sections": sections,
    }


def _doc_key(row: dict[str, Any]) -> str:
    return _norm(row.get("doc_id")) or _norm(row.get("file_url"))


def _merge_summary_docs(
    catalog: list[dict[str, Any]], summaries: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    by_key = {_doc_key(row): row for row in catalog if _doc_key(row)}
    if not summaries:
        return [dict(row) for row in catalog], set(by_key), set()

    summary_by_key = {_doc_key(row): row for row in summaries if _doc_key(row)}
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    summary_keys: set[str] = set()
    for key, catalog_row in by_key.items():
        base = dict(catalog_row)
        summary = summary_by_key.get(key)
        if summary:
            base.update({k: v for k, v in summary.items() if v not in (None, "")})
            summary_keys.add(key)
        merged.append(base)
        seen.add(key)

    for summary in summaries:
        key = _doc_key(summary)
        if key and key not in seen:
            merged.append({k: v for k, v in summary.items() if v not in (None, "")})
            seen.add(key)
            summary_keys.add(key)
    return merged, set(by_key), summary_keys


def _sections_by_doc(sections: list[dict[str, Any]]) -> dict[str, str]:
    by_doc: dict[str, list[str]] = {}
    for section in sections:
        doc_id = _norm(section.get("doc_id"))
        if not doc_id:
            continue
        heading_path = section.get("heading_path") or []
        heading_text = " ".join(_norm(item) for item in heading_path) if isinstance(heading_path, list) else _norm(heading_path)
        text = f"{heading_text} {_norm(section.get('text'))}".strip()
        if text:
            by_doc.setdefault(doc_id, []).append(text)
    return {doc_id: " ".join(parts) for doc_id, parts in by_doc.items()}


def _field_score(query_tokens: list[str], text: str, weight: float) -> float:
    haystack = text.lower()
    return sum(weight for token in query_tokens if token in haystack)


def _format_result(row: dict[str, Any], *, score: float, source: str) -> dict[str, Any]:
    file_url = _norm(row.get("file_url")) or _norm(row.get("doc_id"))
    return {
        "file_url": file_url,
        "doc_id": _norm(row.get("doc_id")) or file_url,
        "title": _norm(row.get("title")) or file_url,
        "summary": _norm(row.get("summary")),
        "category": _norm(row.get("category")),
        "score": round(float(score), 4),
        "source": source,
    }


def _limit(value: int | None) -> int:
    try:
        parsed = int(value if value is not None else 10)
    except (TypeError, ValueError):
        parsed = 10
    return max(1, min(parsed, 100))


def search_summaries(query: str, *, output_dir: str | Path, limit: int = 10) -> list[dict[str, Any]]:
    """Search L0 ready-data summaries and return stable result dictionaries."""
    query_text = _norm(query)
    query_tokens = _tokens(query_text)
    if not query_tokens:
        return []
    ready_data = _load_ready_data(output_dir)
    if not ready_data:
        return []

    docs, catalog_keys, summary_keys = _merge_summary_docs(ready_data["catalog"], ready_data["summaries"])
    section_text = _sections_by_doc(ready_data["sections"])
    scored: list[dict[str, Any]] = []
    for row in docs:
        doc_id = _doc_key(row)
        headings = row.get("headings") or []
        heading_text = " ".join(_norm(item) for item in headings) if isinstance(headings, list) else _norm(headings)
        summary_score = _field_score(query_tokens, _norm(row.get("summary")), 4.0)
        title_score = _field_score(query_tokens, _norm(row.get("title")), 2.0)
        category_score = _field_score(query_tokens, _norm(row.get("category")), 1.0)
        heading_score = _field_score(query_tokens, heading_text, 1.0)
        section_score = _field_score(query_tokens, section_text.get(doc_id, ""), 0.75)
        score = summary_score + title_score + category_score + heading_score + section_score
        if query_text.lower() and query_text.lower() in _norm(row.get("summary")).lower():
            score += 3.0
        if score <= 0:
            continue
        if doc_id in summary_keys and (summary_score > 0 or doc_id not in catalog_keys):
            source = "doc_summaries"
        elif summary_score > 0 or title_score > 0 or category_score > 0 or heading_score > 0:
            source = "doc_catalog"
        else:
            source = "sections"
        scored.append(_format_result(row, score=score, source=source))

    scored.sort(key=lambda item: (-float(item["score"]), item["title"].lower(), item["file_url"]))
    return scored[: _limit(limit)]


def search_titles(query: str, *, output_dir: str | Path, limit: int = 10) -> list[dict[str, Any]]:
    """Search L0 ready-data document titles with lightweight keyword scoring."""
    query_text = _norm(query)
    query_tokens = _tokens(query_text)
    if not query_tokens:
        return []
    ready_data = _load_ready_data(output_dir)
    if not ready_data:
        return []

    scored: list[dict[str, Any]] = []
    for row in ready_data["catalog"]:
        headings = row.get("headings") or []
        heading_text = " ".join(_norm(item) for item in headings) if isinstance(headings, list) else _norm(headings)
        title = _norm(row.get("title"))
        score = (
            _field_score(query_tokens, title, 5.0)
            + _field_score(query_tokens, _norm(row.get("file_url")), 1.0)
            + _field_score(query_tokens, _norm(row.get("category")), 0.5)
            + _field_score(query_tokens, _norm(row.get("summary")), 0.5)
            + _field_score(query_tokens, heading_text, 0.75)
        )
        if query_text.lower() and query_text.lower() in title.lower():
            score += 4.0
        if score <= 0:
            continue
        scored.append(_format_result(row, score=score, source="doc_catalog"))

    scored.sort(key=lambda item: (-float(item["score"]), item["title"].lower(), item["file_url"]))
    return scored[: _limit(limit)]
