from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Callable, Mapping

from ai_actuarial.agentic_rag.agentic_loop import run_agentic_rag_loop
from ai_actuarial.agentic_rag.ready_data_tools import (
    search_calculation_terms,
    search_formula_cards,
    search_sections,
    search_structured_tables,
    search_summaries,
    search_titles,
    trace_relations,
)
from ai_actuarial.shared_runtime import parse_int_clamped
from ai_actuarial.storage import Storage


class AgenticRagError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _payload_value(payload: Mapping[str, Any], key: str, fallback: Any = None) -> Any:
    value = payload.get(key)
    return fallback if value in (None, "") else value


def _validate_ready_output_dir(output_dir: str) -> str:
    normalized = _norm(output_dir)
    if not normalized:
        raise AgenticRagError("output_dir or kb_id is required", status_code=400)
    path = Path(normalized)
    if not path.is_dir():
        raise AgenticRagError("output_dir does not exist or is not a directory", status_code=400)
    if not (path / "ready_data_manifest.json").is_file():
        raise AgenticRagError("ready_data manifest not found in output_dir", status_code=400)
    return str(path)


def _validate_agentic_ready_output_dir(*, db_path: str, output_dir: str) -> str:
    candidate = Path(_validate_ready_output_dir(output_dir)).resolve()
    root = (Path(db_path).resolve().parent / "agentic_ready_data").resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AgenticRagError(
            "output_dir must stay under the database agentic_ready_data directory",
            status_code=400,
        ) from exc
    return str(candidate)


def _manifest_profile_from_output_dir(output_dir: str) -> str:
    try:
        with (Path(output_dir) / "ready_data_manifest.json").open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return _norm(data.get("profile")).lower()


def _is_missing_profile_schema_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "no such table: rag_knowledge_bases" in message or "no such column: manifest_profile" in message


def _resolve_ready_output_dir(
    *,
    db_path: str,
    payload: Mapping[str, Any],
) -> tuple[str, str, str]:
    explicit_output_dir = _norm(payload.get("output_dir"))
    kb_id = _norm(payload.get("kb_id"))
    requested_profile = _norm(payload.get("profile") or payload.get("manifest_profile")).lower()
    profile = requested_profile or "general"
    if explicit_output_dir:
        if kb_id:
            raise AgenticRagError("output_dir cannot be combined with kb_id/profile registry lookup", status_code=400)
        resolved_output_dir = _validate_agentic_ready_output_dir(db_path=db_path, output_dir=explicit_output_dir)
        if not requested_profile:
            profile = _manifest_profile_from_output_dir(resolved_output_dir) or profile
        return resolved_output_dir, "", profile
    if not kb_id:
        raise AgenticRagError("output_dir or kb_id is required", status_code=400)

    storage = Storage(db_path)
    try:
        if not requested_profile:
            try:
                row = storage._conn.execute(
                    "SELECT manifest_profile FROM rag_knowledge_bases WHERE kb_id = ?",
                    (kb_id,),
                ).fetchone()
            except sqlite3.OperationalError as exc:
                if not _is_missing_profile_schema_error(exc):
                    raise
                row = None
            if row and _norm(row[0]):
                profile = _norm(row[0]).lower()
        manifest = storage.get_agentic_ready_manifest(kb_id=kb_id, profile=profile)
    finally:
        storage.close()
    if not manifest:
        raise AgenticRagError("ready_data manifest not found for kb_id/profile", status_code=404)
    status = _norm(manifest.get("status")).lower()
    output_dir = _norm(manifest.get("output_dir"))
    if status != "ready" or not output_dir:
        raise AgenticRagError("ready_data manifest is not ready for kb_id/profile", status_code=409)
    return _validate_agentic_ready_output_dir(db_path=db_path, output_dir=output_dir), kb_id, profile


def _search_response(
    *,
    db_path: str,
    payload: Mapping[str, Any],
    search_fn: Callable[..., list[dict[str, Any]]],
    search_type: str,
) -> dict[str, Any]:
    query = _norm(_payload_value(payload, "query", ""))
    limit = parse_int_clamped(_payload_value(payload, "limit", 10), default=10, min_value=1, max_value=100)
    output_dir, kb_id, profile = _resolve_ready_output_dir(db_path=db_path, payload=payload)
    results = search_fn(query, output_dir=output_dir, limit=limit) if query else []
    return {
        "query": query,
        "search_type": search_type,
        "limit": limit,
        "count": len(results),
        "results": results,
        "output_dir": output_dir,
        "kb_id": kb_id or None,
        "profile": profile,
    }


def search_ready_summaries(*, db_path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return _search_response(
        db_path=db_path,
        payload=payload,
        search_fn=search_summaries,
        search_type="summaries",
    )


def search_ready_titles(*, db_path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return _search_response(
        db_path=db_path,
        payload=payload,
        search_fn=search_titles,
        search_type="titles",
    )


def search_ready_sections(*, db_path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return _search_response(
        db_path=db_path,
        payload=payload,
        search_fn=search_sections,
        search_type="sections",
    )


def search_ready_formula_cards(*, db_path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return _search_response(
        db_path=db_path,
        payload=payload,
        search_fn=search_formula_cards,
        search_type="formula_cards",
    )


def search_ready_structured_tables(*, db_path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return _search_response(
        db_path=db_path,
        payload=payload,
        search_fn=search_structured_tables,
        search_type="tables",
    )


def search_ready_calculation_terms(*, db_path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return _search_response(
        db_path=db_path,
        payload=payload,
        search_fn=search_calculation_terms,
        search_type="calculation_terms",
    )


def trace_ready_relations(*, db_path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return _search_response(
        db_path=db_path,
        payload=payload,
        search_fn=trace_relations,
        search_type="relations",
    )


def chat_agentic_rag(*, db_path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    query = _norm(_payload_value(payload, "query", ""))
    if not query:
        raise AgenticRagError("query is required", status_code=400)
    limit = parse_int_clamped(_payload_value(payload, "limit", 10), default=10, min_value=1, max_value=100)
    output_dir, kb_id, profile = _resolve_ready_output_dir(db_path=db_path, payload=payload)
    return run_agentic_rag_loop(
        query=query,
        output_dir=output_dir,
        profile=profile,
        kb_id=kb_id or None,
        limit=limit,
    )
