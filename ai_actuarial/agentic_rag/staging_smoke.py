from __future__ import annotations

import hashlib
import json
import multiprocessing
import socket
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Iterator

from .agentic_loop import run_agentic_rag_loop


STAGING_SMOKE_CONTRACT_VERSION = "ready-data-staging-smoke.v1"
STAGING_SMOKE_QUERY_MAX_CHARS = 160
STAGING_SMOKE_IDENTIFIER_MAX_CHARS = 512


def _bounded_text(value: Any, max_chars: int) -> str:
    text = " ".join(
        unicodedata.normalize("NFKC", str(value or "")).split()
    ).strip()
    return text[:max_chars].rstrip()


def _identifier(value: Any) -> str:
    return _bounded_text(value, STAGING_SMOKE_IDENTIFIER_MAX_CHARS)


def _reference_identifier(value: Any) -> str:
    return str(value or "").strip()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            item = json.loads(text)
            if isinstance(item, dict):
                rows.append(item)
    return rows


def _stable_catalog_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _reference_identifier(row.get("doc_id") or row.get("file_url")),
        _reference_identifier(row.get("file_url")),
        _bounded_text(row.get("title"), STAGING_SMOKE_QUERY_MAX_CHARS),
    )


def _catalog_headings(row: dict[str, Any]) -> list[str]:
    headings = row.get("headings")
    if isinstance(headings, list):
        return [
            query
            for item in headings
            if (query := _bounded_text(item, STAGING_SMOKE_QUERY_MAX_CHARS))
        ]
    heading = _bounded_text(headings, STAGING_SMOKE_QUERY_MAX_CHARS)
    return [heading] if heading else []


def _section_queries(root: Path) -> dict[str, list[tuple[str, str, str]]]:
    rows: list[dict[str, Any]] = []
    for name in ("sections_structured.jsonl", "sections.jsonl"):
        path = root / name
        if path.is_file():
            rows.extend(_read_jsonl(path))
    queries: dict[str, list[tuple[str, str, str]]] = {}
    for row in rows:
        doc_id = _reference_identifier(row.get("doc_id") or row.get("file_url"))
        if not doc_id:
            continue
        heading_path = row.get("heading_path")
        headings = heading_path if isinstance(heading_path, list) else [heading_path]
        heading = _bounded_text(
            row.get("heading") or next((item for item in reversed(headings) if item), ""),
            STAGING_SMOKE_QUERY_MAX_CHARS,
        )
        text = _bounded_text(row.get("text"), STAGING_SMOKE_QUERY_MAX_CHARS)
        section_id = _reference_identifier(row.get("section_id"))
        queries.setdefault(doc_id, []).append((section_id, heading, text))
    for values in queries.values():
        values.sort(key=lambda item: item[0])
    return queries


def select_staging_smoke_query(output_dir: str | Path) -> dict[str, Any]:
    """Choose one stable catalog document and a bounded local query."""
    root = Path(output_dir)
    catalog = _read_jsonl(root / "doc_catalog.jsonl")
    catalog.sort(key=_stable_catalog_key)
    doc_ids = sorted(
        {
            value
            for row in catalog
            if (value := _reference_identifier(row.get("doc_id")))
        }
    )
    file_urls = sorted(
        {
            value
            for row in catalog
            if (value := _reference_identifier(row.get("file_url")))
        }
    )
    selection: dict[str, Any] = {
        "catalog_doc_count": len(catalog),
        "catalog_doc_ids": doc_ids,
        "catalog_file_urls": file_urls,
        "catalog_doc_id": "",
        "catalog_file_url": "",
        "query_source": "empty_catalog" if not catalog else "",
        "query": "",
    }
    if not catalog:
        return selection

    section_queries = _section_queries(root)
    for row in catalog:
        doc_id = _reference_identifier(row.get("doc_id") or row.get("file_url"))
        file_url = _reference_identifier(row.get("file_url"))
        if not doc_id and not file_url:
            continue
        candidates: list[tuple[str, str]] = []
        title = _bounded_text(row.get("title"), STAGING_SMOKE_QUERY_MAX_CHARS)
        summary = _bounded_text(row.get("summary"), STAGING_SMOKE_QUERY_MAX_CHARS)
        if title:
            candidates.append(("title", title))
        if summary:
            candidates.append(("summary", summary))
        candidates.extend(("heading", value) for value in _catalog_headings(row))
        for _section_id, heading, text in section_queries.get(doc_id, []):
            if heading:
                candidates.append(("heading", heading))
            if text:
                candidates.append(("section_text", text))
        if not candidates:
            continue
        query_source, query = candidates[0]
        selection.update(
            {
                "catalog_doc_id": doc_id,
                "catalog_file_url": file_url,
                "query_source": query_source,
                "query": query,
            }
        )
        return selection

    selection["query_source"] = "unavailable"
    return selection


def _network_disabled(*_args: Any, **_kwargs: Any) -> Any:
    raise RuntimeError("network access is disabled for ready-data staging smoke")


@contextmanager
def _offline_network_guard() -> Iterator[None]:
    original_socket = socket.socket
    original_create_connection = socket.create_connection
    original_getaddrinfo = socket.getaddrinfo
    socket.socket = _network_disabled  # type: ignore[assignment]
    socket.create_connection = _network_disabled  # type: ignore[assignment]
    socket.getaddrinfo = _network_disabled  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.socket = original_socket  # type: ignore[assignment]
        socket.create_connection = original_create_connection  # type: ignore[assignment]
        socket.getaddrinfo = original_getaddrinfo  # type: ignore[assignment]


def _run_offline_query(
    *,
    query: str,
    output_dir: str,
    profile: str,
    kb_id: str,
) -> dict[str, Any]:
    """Run only the existing local ready-data query path and return bounded metadata."""
    with _offline_network_guard():
        result = run_agentic_rag_loop(
            query=query,
            output_dir=output_dir,
            profile=profile,
            kb_id=kb_id,
            limit=10,
        )
    evidence = result.get("evidence")
    evidence_count = len(evidence) if isinstance(evidence, list) else 0
    raw_references = result.get("citations")
    if not isinstance(raw_references, list):
        raw_references = result.get("references")
    references: list[dict[str, str]] = []
    if isinstance(raw_references, list):
        for item in raw_references[:20]:
            if not isinstance(item, dict):
                continue
            references.append(
                {
                    "doc_id": _reference_identifier(item.get("doc_id")),
                    "file_url": _reference_identifier(item.get("file_url")),
                }
            )
    return {
        "status": "ok",
        "evidence_count": evidence_count,
        "references": references,
    }


def _query_process_entry(connection: Any, request: dict[str, str]) -> None:
    try:
        payload = _run_offline_query(
            query=request["query"],
            output_dir=request["output_dir"],
            profile=request["profile"],
            kb_id=request["kb_id"],
        )
    except BaseException:  # noqa: BLE001
        payload = {
            "status": "error",
            "failure_reason": "query_execution_failed",
        }
    try:
        connection.send(payload)
    finally:
        connection.close()


def _stop_process(process: multiprocessing.Process) -> None:
    if process.is_alive():
        process.terminate()
        process.join(timeout=1.0)
    if process.is_alive():
        process.kill()
        process.join()
    else:
        process.join()
    process.close()


def _execute_bounded_smoke(
    request: dict[str, str],
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_smoke_process_entry,
        args=(child_connection, request),
        name="ready-data-staging-smoke",
    )
    try:
        process.start()
        child_connection.close()
        if not parent_connection.poll(timeout_seconds):
            return {
                "status": "error",
                "failure_reason": "query_timed_out",
            }
        try:
            payload = parent_connection.recv()
        except (EOFError, OSError):
            return {
                "status": "error",
                "failure_reason": "query_process_failed",
            }
        return payload if isinstance(payload, dict) else {
            "status": "error",
            "failure_reason": "query_process_failed",
        }
    except (OSError, RuntimeError):
        return {
            "status": "error",
            "failure_reason": "query_process_failed",
        }
    finally:
        child_connection.close()
        parent_connection.close()
        if process.pid is not None:
            _stop_process(process)


def _assess_query_result(
    selection: dict[str, Any],
    query_result: dict[str, Any],
) -> dict[str, Any]:
    if query_result.get("status") != "ok":
        reason = str(query_result.get("failure_reason") or "query_process_failed")
        if reason not in {
            "query_execution_failed",
            "query_process_failed",
            "query_timed_out",
        }:
            reason = "query_process_failed"
        return {
            "passed": False,
            "failure_reason": reason,
            "matched_doc_id": "",
            "matched_file_url": "",
        }
    if int(query_result.get("evidence_count") or 0) <= 0:
        return {
            "passed": False,
            "failure_reason": "no_evidence",
            "matched_doc_id": "",
            "matched_file_url": "",
        }

    allowed_doc_ids = set(selection.get("catalog_doc_ids") or [])
    allowed_file_urls = set(selection.get("catalog_file_urls") or [])
    for reference in query_result.get("references") or []:
        if not isinstance(reference, dict):
            continue
        doc_id = _reference_identifier(reference.get("doc_id"))
        file_url = _reference_identifier(reference.get("file_url"))
        matched_doc_id = doc_id if doc_id in allowed_doc_ids else ""
        matched_file_url = file_url if file_url in allowed_file_urls else ""
        if matched_doc_id or matched_file_url:
            return {
                "passed": True,
                "failure_reason": "",
                "matched_doc_id": matched_doc_id,
                "matched_file_url": matched_file_url,
            }
    return {
        "passed": False,
        "failure_reason": "catalog_reference_missing",
        "matched_doc_id": "",
        "matched_file_url": "",
    }


def _smoke_process_entry(connection: Any, request: dict[str, str]) -> None:
    selection: dict[str, Any] = {
        "catalog_doc_count": 0,
        "query_source": "unavailable",
        "query": "",
    }
    try:
        selection = select_staging_smoke_query(request["output_dir"])
        if selection["catalog_doc_count"] == 0:
            payload = {
                "status": "skipped_empty",
                "failure_reason": "",
                "matched_doc_id": "",
                "matched_file_url": "",
            }
        elif not selection["query"]:
            payload = {
                "status": "failed",
                "failure_reason": "no_queryable_catalog_document",
                "matched_doc_id": "",
                "matched_file_url": "",
            }
        else:
            try:
                query_result = _run_offline_query(
                    query=str(selection["query"]),
                    output_dir=request["output_dir"],
                    profile=request["profile"],
                    kb_id=request["kb_id"],
                )
            except BaseException:  # noqa: BLE001
                query_result = {
                    "status": "error",
                    "failure_reason": "query_execution_failed",
                }
            assessment = _assess_query_result(selection, query_result)
            payload = {
                "status": "passed" if assessment["passed"] else "failed",
                "failure_reason": str(assessment["failure_reason"]),
                "matched_doc_id": _identifier(assessment["matched_doc_id"]),
                "matched_file_url": _identifier(assessment["matched_file_url"]),
            }
    except BaseException:  # noqa: BLE001
        payload = {
            "status": "failed",
            "failure_reason": "query_selection_failed",
            "matched_doc_id": "",
            "matched_file_url": "",
        }
    payload["selection"] = {
        "catalog_doc_count": max(0, int(selection.get("catalog_doc_count") or 0)),
        "query_source": _bounded_text(selection.get("query_source"), 32),
        "query": _bounded_text(selection.get("query"), STAGING_SMOKE_QUERY_MAX_CHARS),
    }
    try:
        connection.send(payload)
    finally:
        connection.close()


def _audit_result(
    *,
    selection: dict[str, Any],
    status: str,
    failure_reason: str,
    matched_doc_id: str,
    matched_file_url: str,
    started_at: float,
) -> dict[str, Any]:
    query = _bounded_text(selection.get("query"), STAGING_SMOKE_QUERY_MAX_CHARS)
    return {
        "contract_version": STAGING_SMOKE_CONTRACT_VERSION,
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_ms": max(0, int(round((monotonic() - started_at) * 1000))),
        "query_source": _bounded_text(selection.get("query_source"), 32),
        "query": query,
        "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
        "matched_doc_id": _identifier(matched_doc_id),
        "matched_file_url": _identifier(matched_file_url),
        "failure_reason": _bounded_text(failure_reason, 160),
        "catalog_doc_count": max(0, int(selection.get("catalog_doc_count") or 0)),
    }


def run_staging_smoke(
    *,
    output_dir: str,
    profile: str,
    kb_id: str,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Run a deterministic, offline, fail-closed smoke against one staging tree."""
    started_at = monotonic()
    if timeout_seconds is None:
        from ai_actuarial.storage import Storage

        timeout_seconds = float(
            Storage.AGENTIC_READY_FUTURE_EXECUTION_POLICY[
                "staging_smoke_timeout_seconds"
            ]
        )
    timeout = max(0.000001, float(timeout_seconds))
    worker_result = _execute_bounded_smoke(
        {
            "output_dir": str(Path(output_dir)),
            "profile": _bounded_text(profile, 32) or "general",
            "kb_id": _identifier(kb_id),
        },
        timeout_seconds=timeout,
    )
    selection = worker_result.get("selection")
    if not isinstance(selection, dict):
        selection = {
            "catalog_doc_count": 0,
            "query_source": "unavailable",
            "query": "",
        }
    status = str(worker_result.get("status") or "failed")
    if status not in {"passed", "failed", "skipped_empty"}:
        status = "failed"
    failure_reason = str(worker_result.get("failure_reason") or "")
    if status == "failed" and not failure_reason:
        failure_reason = "query_process_failed"
    return _audit_result(
        selection=selection,
        status=status,
        failure_reason=failure_reason,
        matched_doc_id=str(worker_result.get("matched_doc_id") or ""),
        matched_file_url=str(worker_result.get("matched_file_url") or ""),
        started_at=started_at,
    )


__all__ = [
    "STAGING_SMOKE_CONTRACT_VERSION",
    "run_staging_smoke",
    "select_staging_smoke_query",
]
