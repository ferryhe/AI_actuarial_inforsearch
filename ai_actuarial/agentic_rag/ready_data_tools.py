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
    aliases = _read_jsonl(_artifact_path(root, manifest, "title_aliases.jsonl"))
    sections_structured = _read_jsonl(_artifact_path(root, manifest, "sections_structured.jsonl"))
    formula_cards = _read_jsonl(_artifact_path(root, manifest, "formula_cards.jsonl"))
    tables_structured = _read_jsonl(_artifact_path(root, manifest, "tables_structured.jsonl"))
    calculation_terms = _read_jsonl(_artifact_path(root, manifest, "calculation_terms.jsonl"))
    relations_graph = _read_json(_artifact_path(root, manifest, "relations_graph.json")) or {}
    return {
        "manifest": manifest,
        "catalog": catalog,
        "summaries": summary_rows,
        "summary_source": source,
        "sections": sections,
        "aliases": aliases,
        "sections_structured": sections_structured,
        "formula_cards": formula_cards,
        "tables_structured": tables_structured,
        "calculation_terms": calculation_terms,
        "relations_graph": relations_graph,
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


def _catalog_by_doc(catalog: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {_doc_key(row): row for row in catalog if _doc_key(row)}


def _list_text(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_norm(item) for item in value if _norm(item)]
    text = _norm(value)
    return [text] if text else []


def _first_text(value: Any) -> str:
    parts = _list_text(value)
    return parts[-1] if parts else ""


def _text_snippet(value: Any, max_chars: int = 240) -> str:
    text = " ".join(_norm(value).split())
    if len(text) <= max_chars:
        return text
    if max_chars <= 0:
        return ""
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3].rstrip() + "..."


def _normalized_phrase(value: Any) -> str:
    return " ".join(_norm(value).lower().split())


def _bounded_phrase_contains(text: str, phrase: str) -> bool:
    if not text or not phrase:
        return False
    pattern = r"(?<![\w])" + r"\s+".join(re.escape(part) for part in phrase.split()) + r"(?![\w])"
    return bool(re.search(pattern, text, flags=re.IGNORECASE | re.UNICODE))


def _number_alias_in_query(query_text: str, number: str) -> bool:
    if not number:
        return False
    escaped = re.escape(number)
    patterns = (
        rf"(?<![A-Za-z0-9])(?:第\s*)?{escaped}\s*(?:号)?(?![A-Za-z0-9])",
        rf"(?<![A-Za-z0-9])(?:rule|article)\s*[-#: ]\s*{escaped}(?![A-Za-z0-9])",
    )
    return any(re.search(pattern, query_text, flags=re.IGNORECASE) for pattern in patterns)


def _alias_match_score(query_text: str, alias_row: dict[str, Any]) -> tuple[float, str]:
    query_lower = _normalized_phrase(query_text)
    candidates: list[tuple[str, str]] = []
    candidates.extend(("alias", item) for item in _list_text(alias_row.get("aliases")))
    candidates.extend(("identifier", item) for item in _list_text(alias_row.get("identifiers")))
    candidates.extend(("document_number", item) for item in _list_text(alias_row.get("document_numbers")))
    candidates.extend(("rule_number", item) for item in _list_text(alias_row.get("rule_numbers")))
    candidates.append(("title", _norm(alias_row.get("title"))))
    best_score = 0.0
    best_match = ""
    for kind, candidate in candidates:
        candidate_lower = _normalized_phrase(candidate)
        if not candidate_lower:
            continue
        if query_lower == candidate_lower:
            return 100.0, candidate
        if kind in {"document_number", "rule_number"} or re.fullmatch(r"[0-9]+", candidate_lower):
            if _number_alias_in_query(query_text, candidate_lower):
                score = 92.0
            else:
                continue
        elif _bounded_phrase_contains(query_lower, candidate_lower):
            score = 88.0 + min(len(candidate_lower), len(query_lower)) / max(len(candidate_lower), len(query_lower))
        elif len(_tokens(query_lower)) >= 2 and _bounded_phrase_contains(candidate_lower, query_lower):
            score = 80.0 + min(len(candidate_lower), len(query_lower)) / max(len(candidate_lower), len(query_lower))
        else:
            continue
        if score > best_score:
            best_score = score
            best_match = candidate
    return best_score, best_match


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
    """Search ready-data document titles, preferring L1 aliases before scoring."""
    query_text = _norm(query)
    query_tokens = _tokens(query_text)
    if not query_tokens:
        return []
    ready_data = _load_ready_data(output_dir)
    if not ready_data:
        return []

    by_doc = _catalog_by_doc(ready_data["catalog"])
    alias_hits: list[dict[str, Any]] = []
    seen_alias_docs: set[str] = set()
    for alias_row in ready_data["aliases"]:
        score, matched_alias = _alias_match_score(query_text, alias_row)
        if score <= 0:
            continue
        doc_id = _doc_key(alias_row)
        row = dict(by_doc.get(doc_id, {}))
        row.update({k: v for k, v in alias_row.items() if v not in (None, "")})
        result = _format_result(row, score=score, source="title_aliases")
        result["matched_alias"] = matched_alias
        alias_hits.append(result)
        seen_alias_docs.add(result["doc_id"])
    if alias_hits:
        alias_hits.sort(key=lambda item: (-float(item["score"]), item["title"].lower(), item["file_url"]))
        if len(alias_hits) >= _limit(limit):
            return alias_hits[: _limit(limit)]

    scored: list[dict[str, Any]] = []
    for row in ready_data["catalog"]:
        doc_id = _doc_key(row)
        if doc_id in seen_alias_docs:
            continue
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
    return (alias_hits + scored)[: _limit(limit)]


def search_sections(query: str, *, output_dir: str | Path, limit: int = 10) -> list[dict[str, Any]]:
    """Search L1 structured sections, falling back to L0 sections when needed."""
    query_text = _norm(query)
    query_tokens = _tokens(query_text)
    if not query_tokens:
        return []
    ready_data = _load_ready_data(output_dir)
    if not ready_data:
        return []

    catalog = _catalog_by_doc(ready_data["catalog"])
    source = "sections_structured" if ready_data["sections_structured"] else "sections"
    section_rows = ready_data["sections_structured"] or ready_data["sections"]
    scored: list[dict[str, Any]] = []
    for section in section_rows:
        doc_id = _norm(section.get("doc_id"))
        if not doc_id:
            continue
        doc = catalog.get(doc_id, {})
        heading_path = _list_text(section.get("heading_path"))
        heading = _norm(section.get("heading")) or _first_text(heading_path)
        text = _norm(section.get("text"))
        alias_text = " ".join(_list_text(section.get("aliases")) + _list_text(section.get("document_aliases")))
        score = (
            _field_score(query_tokens, heading, 4.0)
            + _field_score(query_tokens, " ".join(heading_path), 3.0)
            + _field_score(query_tokens, text, 1.0)
            + _field_score(query_tokens, _norm(doc.get("title")) or _norm(section.get("title")), 1.0)
            + _field_score(query_tokens, alias_text, 4.0)
        )
        if query_text.lower() and query_text.lower() in f"{heading} {text}".lower():
            score += 3.0
        if score <= 0:
            continue
        file_url = _norm(section.get("file_url")) or _norm(doc.get("file_url")) or doc_id
        scored.append(
            {
                "doc_id": doc_id,
                "file_url": file_url,
                "title": _norm(section.get("title")) or _norm(doc.get("title")) or file_url,
                "section_id": _norm(section.get("section_id")),
                "heading_path": heading_path,
                "heading": heading,
                "text_snippet": _text_snippet(text),
                "score": round(float(score), 4),
                "source": source,
            }
        )

    scored.sort(key=lambda item: (-float(item["score"]), item["title"].lower(), item["section_id"]))
    return scored[: _limit(limit)]


def search_formula_cards(query: str, *, output_dir: str | Path, limit: int = 10) -> list[dict[str, Any]]:
    """Search L2 formula cards and return stable formula result dictionaries."""
    query_text = _norm(query)
    query_tokens = _tokens(query_text)
    if not query_tokens:
        return []
    ready_data = _load_ready_data(output_dir)
    if not ready_data:
        return []

    scored: list[dict[str, Any]] = []
    for row in ready_data["formula_cards"]:
        formula_text = _norm(row.get("formula_text"))
        context = _norm(row.get("context"))
        terms = _list_text(row.get("terms"))
        heading_path = _list_text(row.get("heading_path"))
        heading = _norm(row.get("heading")) or _first_text(heading_path)
        title = _norm(row.get("title"))
        score = (
            _field_score(query_tokens, formula_text, 6.0)
            + _field_score(query_tokens, " ".join(terms), 5.0)
            + _field_score(query_tokens, heading, 3.0)
            + _field_score(query_tokens, context, 1.5)
            + _field_score(query_tokens, title, 1.0)
        )
        if query_text.lower() and query_text.lower() in f"{formula_text} {context}".lower():
            score += 4.0
        if score <= 0:
            continue
        file_url = _norm(row.get("file_url")) or _norm(row.get("doc_id"))
        scored.append(
            {
                "doc_id": _norm(row.get("doc_id")) or file_url,
                "file_url": file_url,
                "title": title or file_url,
                "formula_id": _norm(row.get("formula_id")),
                "section_id": _norm(row.get("section_id")),
                "heading_path": heading_path,
                "heading": heading,
                "formula_text": formula_text,
                "context_snippet": _text_snippet(context),
                "terms": terms,
                "score": round(float(score), 4),
                "source": "formula_cards",
            }
        )

    scored.sort(key=lambda item: (-float(item["score"]), item["title"].lower(), item["formula_id"]))
    return scored[: _limit(limit)]


def _table_rows_text(rows: Any) -> str:
    if not isinstance(rows, list):
        return ""
    parts: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            parts.extend(_norm(value) for value in row.values() if _norm(value))
        elif isinstance(row, list):
            parts.extend(_norm(value) for value in row if _norm(value))
        else:
            text = _norm(row)
            if text:
                parts.append(text)
    return " ".join(parts)


def search_structured_tables(query: str, *, output_dir: str | Path, limit: int = 10) -> list[dict[str, Any]]:
    """Search L2 structured table artifacts."""
    query_text = _norm(query)
    query_tokens = _tokens(query_text)
    if not query_tokens:
        return []
    ready_data = _load_ready_data(output_dir)
    if not ready_data:
        return []

    scored: list[dict[str, Any]] = []
    for row in ready_data["tables_structured"]:
        headers = _list_text(row.get("headers"))
        rows = row.get("rows") if isinstance(row.get("rows"), list) else []
        heading_path = _list_text(row.get("heading_path"))
        heading = _norm(row.get("heading")) or _first_text(heading_path)
        caption = _norm(row.get("caption"))
        table_text = " ".join(
            part
            for part in [
                caption,
                heading,
                " ".join(headers),
                _table_rows_text(rows),
                _norm(row.get("text")),
            ]
            if part
        )
        score = (
            _field_score(query_tokens, " ".join(headers), 4.0)
            + _field_score(query_tokens, _table_rows_text(rows), 4.0)
            + _field_score(query_tokens, caption, 2.0)
            + _field_score(query_tokens, heading, 2.0)
            + _field_score(query_tokens, _norm(row.get("text")), 1.0)
        )
        if query_text.lower() and query_text.lower() in table_text.lower():
            score += 4.0
        if score <= 0:
            continue
        file_url = _norm(row.get("file_url")) or _norm(row.get("doc_id"))
        scored.append(
            {
                "doc_id": _norm(row.get("doc_id")) or file_url,
                "file_url": file_url,
                "title": _norm(row.get("title")) or file_url,
                "table_id": _norm(row.get("table_id")),
                "section_id": _norm(row.get("section_id")),
                "heading_path": heading_path,
                "heading": heading,
                "caption": caption,
                "headers": headers,
                "rows": rows,
                "text_snippet": _text_snippet(table_text),
                "score": round(float(score), 4),
                "source": "tables_structured",
            }
        )

    scored.sort(key=lambda item: (-float(item["score"]), item["title"].lower(), item["table_id"]))
    return scored[: _limit(limit)]


def search_calculation_terms(query: str, *, output_dir: str | Path, limit: int = 10) -> list[dict[str, Any]]:
    """Search L2 calculation term artifacts."""
    query_text = _norm(query)
    query_tokens = _tokens(query_text)
    if not query_tokens:
        return []
    ready_data = _load_ready_data(output_dir)
    if not ready_data:
        return []

    scored: list[dict[str, Any]] = []
    for row in ready_data["calculation_terms"]:
        term = _norm(row.get("term"))
        normalized_term = _norm(row.get("normalized_term")) or term.lower()
        context = _norm(row.get("context"))
        heading_path = _list_text(row.get("heading_path"))
        term_text = f"{term} {normalized_term}"
        score = (
            _field_score(query_tokens, term_text, 8.0)
            + _field_score(query_tokens, context, 2.0)
            + _field_score(query_tokens, " ".join(heading_path), 1.0)
            + _field_score(query_tokens, _norm(row.get("title")), 0.5)
        )
        if query_text.lower() and query_text.lower() in term_text.lower():
            score += 6.0
        elif query_text.lower() and query_text.lower() in context.lower():
            score += 2.0
        if score <= 0:
            continue
        file_url = _norm(row.get("file_url")) or _norm(row.get("doc_id"))
        scored.append(
            {
                "doc_id": _norm(row.get("doc_id")) or file_url,
                "file_url": file_url,
                "title": _norm(row.get("title")) or file_url,
                "term_id": _norm(row.get("term_id")),
                "term": term,
                "normalized_term": normalized_term,
                "section_id": _norm(row.get("section_id")),
                "heading_path": heading_path,
                "context_snippet": _text_snippet(context),
                "score": round(float(score), 4),
                "source": "calculation_terms",
            }
        )

    scored.sort(key=lambda item: (-float(item["score"]), item["term"].lower(), item["term_id"]))
    return scored[: _limit(limit)]


def trace_relations(query_or_doc: str, *, output_dir: str | Path, limit: int = 10) -> list[dict[str, Any]]:
    """Trace L1 relation rows for an alias, document, or section query."""
    query_text = _norm(query_or_doc)
    query_tokens = _tokens(query_text)
    if not query_tokens:
        return []
    ready_data = _load_ready_data(output_dir)
    if not ready_data:
        return []
    graph = ready_data.get("relations_graph") or {}
    relations = graph.get("relations") if isinstance(graph, dict) else None
    if not isinstance(relations, list):
        return []

    scored: list[dict[str, Any]] = []
    matched_doc_ids: set[str] = set()
    seen_relation_keys: set[tuple[str, str]] = set()
    for row in relations:
        if not isinstance(row, dict):
            continue
        haystack = " ".join(
            _norm(row.get(key))
            for key in (
                "doc_id",
                "file_url",
                "title",
                "alias",
                "section_id",
                "section_heading",
                "target_id",
                "target_type",
                "relation_type",
            )
        )
        score = _field_score(query_tokens, haystack, 2.0)
        if query_text.lower() and query_text.lower() in haystack.lower():
            score += 5.0
        if score > 0:
            matched_doc_ids.add(_norm(row.get("doc_id")))
            result = dict(row)
            result["score"] = round(float(score), 4)
            result["source"] = "relations_graph"
            scored.append(result)
            seen_relation_keys.add((_norm(row.get("relation_type")), _norm(row.get("target_id"))))

    if matched_doc_ids:
        for row in relations:
            if not isinstance(row, dict):
                continue
            doc_id = _norm(row.get("doc_id"))
            if not doc_id or doc_id not in matched_doc_ids:
                continue
            relation_key = (_norm(row.get("relation_type")), _norm(row.get("target_id")))
            if relation_key in seen_relation_keys:
                continue
            result = dict(row)
            result["score"] = 0.5
            result["source"] = "relations_graph"
            scored.append(result)
            seen_relation_keys.add(relation_key)

    scored.sort(
        key=lambda item: (
            -float(item.get("score") or 0),
            _norm(item.get("relation_type")),
            _norm(item.get("target_id")),
        )
    )
    return scored[: _limit(limit)]
