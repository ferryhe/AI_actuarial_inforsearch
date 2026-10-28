"""One-target, additive publisher for the local actuarial collection flow.

This module is deliberately self-contained so its source can be streamed to the
existing ``ai-api`` container without deploying or restarting that application.
It uses only the target's native Storage, KnowledgeBaseManager and TaskRuntime
contracts. Input and output are one JSON object per process on stdin/stdout.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

MAX_BATCH_ITEMS = 100
MAX_ARTICLE_BYTES = 40 * 1024 * 1024
_TERMINAL_TASK_STATES = {"completed", "error", "stopped"}
_DATE_FACT_SEMANTICS = {
    "publication_date": "publication",
    "revision_date": "revision",
    "document_version_date": "document_version",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class _NativeTaskFailure(RuntimeError):
    diagnostic_evidence: list[str]

    def __init__(self, task: dict[str, Any]) -> None:
        task_id = str(task.get("id") or "unknown")
        task_type = str(task.get("type") or "task")
        status = str(task.get("status") or "unknown")
        errors = task.get("errors") or []
        detail = "; ".join(str(error) for error in errors if str(error).strip())
        message = f"native {task_type} task ended with {status} (id={task_id})"
        if detail:
            message += f": {detail}"
        super().__init__(message)
        self.diagnostic_evidence = [_canonical_json(task)]


def _write_cas(data_root: Path, raw: bytes, digest: str) -> Path:
    if not raw or len(raw) > MAX_ARTICLE_BYTES or _hash(raw) != digest:
        raise ValueError("source bytes do not match the declared SHA-256 or size limit")
    relative = Path("cas") / "sha256" / digest[:2] / digest
    destination = (data_root / relative).resolve()
    root = data_root.resolve()
    if root not in destination.parents:
        raise ValueError("CAS path escapes the configured data root")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if _hash(destination.read_bytes()) != digest:
            raise ValueError("existing target CAS object conflicts with its digest")
        return destination
    fd, temporary_name = tempfile.mkstemp(prefix=".local-ingest-", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if _hash(temporary.read_bytes()) != digest:
            raise ValueError("target CAS write failed digest verification")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def _verified_existing_blob(storage: Any, digest: str, expected_size: int) -> Path | None:
    record = storage.get_blob(digest)
    if not record or int(record.get("bytes") or -1) != expected_size:
        return None
    path = Path(str(record.get("canonical_path") or ""))
    try:
        if (
            path.is_file()
            and path.stat().st_size == expected_size
            and _hash(path.read_bytes()) == digest
        ):
            return path
    except OSError:
        return None
    return None


def _pending_ready_path(data_root: Path, target: str) -> Path:
    if target not in {"china", "overseas"}:
        raise ValueError("unknown pending Ready target")
    return data_root / "local_collection" / f"{target}-pending-ready.json"


def _publication_date_value(date_facts: dict[str, Any]) -> str | None:
    fact = date_facts.get("publication_date")
    if fact is None:
        return None
    if not isinstance(fact, dict):
        raise ValueError("publication_date fact must be an object or null")
    value = fact.get("value")
    precision = fact.get("precision")
    if (
        fact.get("semantic") != _DATE_FACT_SEMANTICS["publication_date"]
        or not isinstance(value, str)
        or precision not in {"year", "month", "day"}
        or len(value) != {"year": 4, "month": 7, "day": 10}[precision]
        or not isinstance(fact.get("evidence"), str)
        or not fact["evidence"].strip()
    ):
        raise ValueError("publication_date value, precision, semantic, or evidence is malformed")
    try:
        date.fromisoformat(
            value + ("-01-01" if precision == "year" else "-01" if precision == "month" else "")
        )
    except ValueError as exc:
        raise ValueError("publication_date is not a valid ISO calendar date") from exc
    return value


def _read_pending_ready(data_root: Path, target: str) -> dict[str, list[str]]:
    path = _pending_ready_path(data_root, target)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "pending native Ready state is unreadable; refusing to lose target acknowledgements"
        ) from exc
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or value.get("target") != target
    ):
        raise RuntimeError("pending native Ready state has an unsupported contract")
    pending = value.get("knowledge_bases")
    if not isinstance(pending, dict):
        raise RuntimeError("pending native Ready KB map is malformed")
    output: dict[str, list[str]] = {}
    for kb_id, urls in pending.items():
        if (
            not isinstance(kb_id, str)
            or not isinstance(urls, list)
            or any(not isinstance(url, str) for url in urls)
        ):
            raise RuntimeError("pending native Ready URL list is malformed")
        output[kb_id] = list(dict.fromkeys(urls))
    return output


def _write_pending_ready(data_root: Path, target: str, pending: dict[str, list[str]]) -> None:
    path = _pending_ready_path(data_root, target)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        _canonical_json({"schema_version": 1, "target": target, "knowledge_bases": pending}) + "\n"
    )
    temporary = path.with_suffix(".json.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _add_pending_ready(
    data_root: Path, target: str, kb_ids: list[str], urls: list[str]
) -> dict[str, list[str]]:
    pending = _read_pending_ready(data_root, target)
    for kb_id in kb_ids:
        current = pending.setdefault(kb_id, [])
        current.extend(url for url in urls if url not in current)
    _write_pending_ready(data_root, target, pending)
    return pending


def _clear_pending_ready(data_root: Path, target: str, kb_id: str, urls: list[str]) -> None:
    pending = _read_pending_ready(data_root, target)
    remaining = [url for url in pending.get(kb_id, []) if url not in set(urls)]
    if remaining:
        pending[kb_id] = remaining
    else:
        pending.pop(kb_id, None)
    _write_pending_ready(data_root, target, pending)


def _clear_pending_ready_for_kb(data_root: Path, kb_id: str, urls: list[str]) -> None:
    for target in ("china", "overseas"):
        if _pending_ready_path(data_root, target).exists():
            pending = _read_pending_ready(data_root, target)
            if kb_id in pending:
                _clear_pending_ready(data_root, target, kb_id, urls)


def _pending_cleanup_path(data_root: Path, target: str) -> Path:
    return data_root / "local_collection" / f"{target}-pending-cleanup-ready.json"


def _read_pending_cleanup(data_root: Path, target: str) -> list[str]:
    path = _pending_cleanup_path(data_root, target)
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("pending cleanup Ready state is unreadable") from exc
    pending = value.get("knowledge_bases") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or value.get("target") != target
        or not isinstance(pending, list)
        or any(not isinstance(kb_id, str) or not kb_id for kb_id in pending)
    ):
        raise RuntimeError("pending cleanup Ready state has an unsupported contract")
    return list(dict.fromkeys(pending))


def _write_pending_cleanup(data_root: Path, target: str, kb_ids: list[str]) -> None:
    path = _pending_cleanup_path(data_root, target)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(
                _canonical_json(
                    {
                        "schema_version": 1,
                        "target": target,
                        "knowledge_bases": list(dict.fromkeys(kb_ids)),
                    }
                )
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _clear_pending_cleanup_kb(data_root: Path, target: str, kb_id: str) -> list[str]:
    pending = [item for item in _read_pending_cleanup(data_root, target) if item != kb_id]
    if pending:
        _write_pending_cleanup(data_root, target, pending)
    else:
        _pending_cleanup_path(data_root, target).unlink(missing_ok=True)
    return pending


def _pending_index_refresh_path(data_root: Path, target: str) -> Path:
    return data_root / "local_collection" / f"{target}-pending-index-refresh.json"


def _read_pending_index_refresh(data_root: Path, target: str) -> list[str]:
    path = _pending_index_refresh_path(data_root, target)
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("pending index refresh state is unreadable") from exc
    pending = value.get("knowledge_bases") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or value.get("target") != target
        or not isinstance(pending, list)
        or any(not isinstance(kb_id, str) or not kb_id for kb_id in pending)
    ):
        raise RuntimeError("pending index refresh state has an unsupported contract")
    return list(dict.fromkeys(pending))


def _write_pending_index_refresh(data_root: Path, target: str, kb_ids: list[str]) -> None:
    path = _pending_index_refresh_path(data_root, target)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(
                _canonical_json(
                    {
                        "schema_version": 1,
                        "target": target,
                        "knowledge_bases": list(dict.fromkeys(kb_ids)),
                    }
                )
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _clear_pending_index_refresh_kb(data_root: Path, target: str, kb_id: str) -> list[str]:
    pending = [item for item in _read_pending_index_refresh(data_root, target) if item != kb_id]
    if pending:
        _write_pending_index_refresh(data_root, target, pending)
    else:
        _pending_index_refresh_path(data_root, target).unlink(missing_ok=True)
    return pending


def _normalize_item(
    item: dict[str, Any], target: str, approved_categories: list[str]
) -> dict[str, Any]:
    url = item.get("url")
    raw_sha = str(item.get("raw_sha256") or "")
    md_sha = str(item.get("markdown_sha256") or "")
    hub_md_sha = str(item.get("hub_markdown_sha256") or "")
    hub_md_sha_kind = str(item.get("hub_markdown_sha256_kind") or "")
    markdown = item.get("markdown")
    raw_b64 = item.get("raw_bytes_b64")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise ValueError("target item URL must be HTTP(S)")
    if len(raw_sha) != 64 or any(ch not in "0123456789abcdef" for ch in raw_sha):
        raise ValueError("target item raw SHA-256 is malformed")
    if len(md_sha) != 64 or any(ch not in "0123456789abcdef" for ch in md_sha):
        raise ValueError("target item Markdown SHA-256 is malformed")
    if not isinstance(markdown, str) or not markdown.strip():
        raise ValueError("target item Markdown is empty")
    if _hash(markdown.encode("utf-8")) != md_sha:
        raise ValueError("target item Markdown digest mismatch")
    json_payload_sha = _hash(_canonical_json(markdown).encode("utf-8"))
    expected_hub_sha = {
        "raw_utf8": md_sha,
        "json_payload_utf8": json_payload_sha,
    }.get(hub_md_sha_kind)
    if (
        len(hub_md_sha) != 64
        or any(ch not in "0123456789abcdef" for ch in hub_md_sha)
        or expected_hub_sha is None
        or hub_md_sha != expected_hub_sha
    ):
        raise ValueError("target item Hub Markdown binding digest mismatch")
    if not isinstance(raw_b64, str):
        raise ValueError("target item requires verified source bytes")
    try:
        raw = base64.b64decode(raw_b64, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("target item source bytes are not valid base64") from exc
    if not raw or len(raw) > MAX_ARTICLE_BYTES or _hash(raw) != raw_sha:
        raise ValueError("target item source bytes do not match their digest")
    packages = item.get("bilingual_metadata")
    if not isinstance(packages, dict) or set(packages) != {"zh", "en"}:
        raise ValueError("target item requires complete zh/en packages")
    for language in ("zh", "en"):
        package = packages[language]
        if not isinstance(package, dict) or any(
            not isinstance(package.get(field), str) or not package[field].strip()
            for field in ("title", "summary", "category")
        ):
            raise ValueError(f"target item has incomplete {language} metadata")
        keywords = package.get("keywords")
        if not isinstance(keywords, list) or not any(
            isinstance(value, str) and value.strip() for value in keywords
        ):
            raise ValueError(f"target item has incomplete {language} keywords")
    categories = item.get("categories")
    if not isinstance(categories, list) or not 1 <= len(categories) <= 4:
        raise ValueError("target item requires one to four canonical categories")
    keys = [entry.get("key") for entry in categories if isinstance(entry, dict)]
    source_primary_value = item.get("source_primary_category")
    source_primary_category = source_primary_value if isinstance(source_primary_value, str) else ""
    legacy_hub_annotation = item.get("legacy_hub_annotation") is True
    annotation = {
        key: item.get(key)
        for key in (
            "categories",
            "date_facts",
            "date_review_status",
            "date_review_reason",
            "date_review_unresolved",
        )
    }
    annotation_result_sha = _hash(_canonical_json(annotation).encode("utf-8"))
    source_signature = item.get("source_signature")
    if not isinstance(source_signature, str) or not re.fullmatch(r"[0-9a-f]{64}", source_signature):
        raise ValueError("target item Hub source signature is malformed")
    if item.get("result_sha256") != annotation_result_sha:
        raise ValueError("target item Hub annotation result digest mismatch")
    if (
        len(keys) != len(categories)
        or len(set(keys)) != len(keys)
        or keys[0] != "AI"
        or any(key not in approved_categories for key in keys)
        or source_primary_category != (keys[0] if keys else None)
        or any(
            not isinstance(entry.get("evidence"), list)
            or len(entry["evidence"]) > 3
            or (not entry["evidence"] and not (index == 0 and legacy_hub_annotation))
            or any(not isinstance(text, str) or not text.strip() for text in entry["evidence"])
            for index, entry in enumerate(categories)
        )
        or (not legacy_hub_annotation and any(not entry["evidence"] for entry in categories))
    ):
        raise ValueError("target item primary category must be AI and categories must be unique")
    if any(packages[lang].get("category") != keys[0] for lang in ("zh", "en")):
        raise ValueError(
            "target bilingual primary category does not match its ordered Hub categories"
        )
    if not isinstance(item.get("date_facts"), dict):
        raise ValueError("target item date facts must be an object")
    published_time = _publication_date_value(item["date_facts"])
    version_id = item.get("content_version_id")
    md_variant_id = item.get("markdown_text_variant_id")
    if (
        type(version_id) is not int
        or version_id < 1
        or type(md_variant_id) is not int
        or md_variant_id < 1
    ):
        raise ValueError("target item must carry its Hub version and Markdown variant IDs")
    if not legacy_hub_annotation:
        expected_signature = _hash(
            _canonical_json(
                {
                    "content_version_id": version_id,
                    "source_text_variant_id": md_variant_id,
                    "source_markdown_sha256": md_sha,
                    "source_primary_category": source_primary_category,
                }
            ).encode("utf-8")
        )
        if source_signature != expected_signature:
            raise ValueError("target item Hub source signature mismatch")
    source_site = item.get("source_site")
    if source_site is not None and (not isinstance(source_site, str) or not source_site.strip()):
        raise ValueError("target source-site provenance is malformed")
    serving_metadata = {
        # The serving catalog is an AI bucket. Keep each source primary
        # category and the ordered category evidence in hub_enrichment.
        "zh": {**packages["zh"], "category": "AI"},
        "en": {**packages["en"], "category": "AI"},
        "hub_enrichment": {
            "content_version_id": version_id,
            "markdown_text_variant_id": md_variant_id,
            "markdown_sha256": md_sha,
            "hub_markdown_sha256": hub_md_sha,
            "hub_markdown_sha256_kind": hub_md_sha_kind,
            "source_primary_category": source_primary_category,
            "ordered_categories": categories,
            "date_facts": item["date_facts"],
            "date_review_status": item.get("date_review_status"),
            "date_review_reason": item.get("date_review_reason"),
            "date_review_unresolved": item.get("date_review_unresolved") or [],
            "source_signature": item.get("source_signature"),
            "result_sha256": item.get("result_sha256"),
        },
    }
    fingerprint_input = {
        "content_version_id": version_id,
        "raw_sha256": raw_sha,
        "markdown_text_variant_id": md_variant_id,
        "markdown_sha256": md_sha,
        "hub_markdown_sha256": hub_md_sha,
        "hub_markdown_sha256_kind": hub_md_sha_kind,
        "source_site": source_site,
        "bilingual_metadata": packages,
        "categories": categories,
        "source_primary_category": source_primary_category,
        "date_facts": item["date_facts"],
        "date_review_status": item.get("date_review_status"),
        "date_review_reason": item.get("date_review_reason"),
        "date_review_unresolved": item.get("date_review_unresolved") or [],
        "source_signature": item.get("source_signature"),
        "result_sha256": item.get("result_sha256"),
    }
    if published_time is not None:
        fingerprint_input["published_time"] = published_time
    return {
        **item,
        "url": url,
        "raw_bytes": raw,
        "raw_sha256": raw_sha,
        "markdown_sha256": md_sha,
        "content_type": str(item.get("content_type") or "application/octet-stream"),
        "title": str(item.get("title") or packages["en"]["title"]).strip(),
        "source_site": source_site,
        "published_time": published_time,
        "bilingual_metadata": packages,
        "serving_metadata": serving_metadata,
        "metadata_fingerprint": _hash(_canonical_json(fingerprint_input).encode("utf-8")),
        "target_category": "AI",
        "target_summary": packages["en"]["summary"],
        "target_keywords": packages["en"]["keywords"],
        "target": target,
    }


def _existing_is_current(storage: Any, item: dict[str, Any], kb_ids: list[str]) -> bool:
    row = storage.get_file_with_catalog(item["url"])
    if not row or row.get("deleted_at") is not None:
        return False
    if row.get("sha256") != item["raw_sha256"] or row.get("markdown_content") != item["markdown"]:
        return False
    if item.get("published_time") is not None and row.get("published_time") != item.get(
        "published_time"
    ):
        return False
    if item.get("source_site") is not None and row.get("source_site") != item["source_site"]:
        return False
    if row.get("category") != "AI" or row.get("catalog_status") != "ok":
        return False
    for kb_id in kb_ids:
        membership = storage._conn.execute(
            "SELECT 1 FROM rag_kb_files WHERE kb_id = ? AND file_url = ?",
            (kb_id, item["url"]),
        ).fetchone()
        if membership is None:
            return False
    metadata = row.get("bilingual_metadata") or {}
    enrichment = metadata.get("hub_enrichment") if isinstance(metadata, dict) else None
    if not isinstance(enrichment, dict):
        return False
    if enrichment.get("content_version_id") != item["content_version_id"]:
        return False
    if enrichment.get("markdown_text_variant_id") != item["markdown_text_variant_id"]:
        return False
    if enrichment.get("markdown_sha256") != item["markdown_sha256"]:
        return False
    if enrichment.get("hub_markdown_sha256") != item["hub_markdown_sha256"]:
        return False
    if enrichment.get("hub_markdown_sha256_kind") != item["hub_markdown_sha256_kind"]:
        return False
    if enrichment.get("ordered_categories") != item["categories"]:
        return False
    if enrichment.get("source_primary_category") != str(
        item.get("source_primary_category") or item["bilingual_metadata"]["en"]["category"]
    ):
        return False
    if enrichment.get("date_facts") != item["date_facts"]:
        return False
    for field in (
        "date_review_status",
        "date_review_reason",
        "source_signature",
        "result_sha256",
    ):
        if enrichment.get(field) != item.get(field):
            return False
    if enrichment.get("date_review_unresolved") != (item.get("date_review_unresolved") or []):
        return False
    for language in ("zh", "en"):
        saved_package = metadata.get(language)
        if not isinstance(saved_package, dict) or saved_package.get("category") != "AI":
            return False
    return True


def _existing_content_and_memberships_current(
    storage: Any, item: dict[str, Any], kb_ids: list[str]
) -> bool:
    row = storage.get_file_with_catalog(item["url"])
    if (
        not row
        or row.get("deleted_at") is not None
        or row.get("catalog_status") != "ok"
        or row.get("sha256") != item["raw_sha256"]
    ):
        return False
    if row.get("markdown_content") != item["markdown"]:
        return False
    for kb_id in kb_ids:
        membership = storage._conn.execute(
            "SELECT 1 FROM rag_kb_files WHERE kb_id = ? AND file_url = ?",
            (kb_id, item["url"]),
        ).fetchone()
        if membership is None:
            return False
    return True


def _write_item(
    storage: Any, manager: Any, item: dict[str, Any], data_root: Path, kb_ids: list[str]
) -> tuple[dict[str, Any], bool]:
    if _existing_is_current(storage, item, kb_ids):
        existing = storage.get_file_with_catalog(item["url"])
        return (
            {
                "url": item["url"],
                "content_version_id": item["content_version_id"],
                "raw_sha256": item["raw_sha256"],
                "markdown_text_variant_id": item["markdown_text_variant_id"],
                "markdown_sha256": item["markdown_sha256"],
                "hub_markdown_sha256": item["hub_markdown_sha256"],
                "hub_markdown_sha256_kind": item["hub_markdown_sha256_kind"],
                "metadata_fingerprint": item["metadata_fingerprint"],
                "status": "already_current",
                "source_site": existing.get("source_site"),
                "first_seen": existing.get("first_seen"),
                "published_time_status": (
                    "verified_source_date"
                    if item.get("published_time") is not None
                    else (
                        "legacy_preserved_unverified"
                        if existing.get("published_time") is not None
                        else "unknown"
                    )
                ),
            },
            False,
        )

    existing_before_write = storage.get_file_with_catalog(item["url"])
    needs_chunks = not _existing_content_and_memberships_current(storage, item, kb_ids)
    serving_metadata = item["serving_metadata"]
    prior_metadata = (
        existing_before_write.get("bilingual_metadata")
        if isinstance(existing_before_write, dict)
        else None
    )
    source_content_unchanged = bool(
        isinstance(existing_before_write, dict)
        and existing_before_write.get("sha256") == item["raw_sha256"]
        and existing_before_write.get("markdown_content") == item["markdown"]
    )
    if source_content_unchanged and isinstance(prior_metadata, dict):
        serving_metadata = {**prior_metadata, **serving_metadata}
        for language in ("zh", "en"):
            prior_package = prior_metadata.get(language)
            if isinstance(prior_package, dict):
                serving_metadata[language] = {
                    **item["serving_metadata"][language],
                    **prior_package,
                    "category": "AI",
                }
        serving_metadata["hub_enrichment"] = item["serving_metadata"]["hub_enrichment"]

    from ai_actuarial.capacity import ensure_capacity

    ensure_capacity(path="/", operation="local_content_hub_article_upsert")
    if not needs_chunks and existing_before_write:
        source_site = item.get("source_site") or existing_before_write.get("source_site")
        with storage.transaction(immediate=True):
            before = storage._ready_data_builder_metadata_snapshot(item["url"])
            storage._conn.execute(
                "UPDATE files SET published_time = COALESCE(?, published_time), source_site = ? "
                "WHERE url = ? AND sha256 = ?",
                (item.get("published_time"), source_site, item["url"], item["raw_sha256"]),
            )
            storage._mark_ready_data_builder_metadata_change(file_url=item["url"], before=before)
            storage.upsert_catalog_item(
                {
                    "url": item["url"],
                    "sha256": item["raw_sha256"],
                    "category": "AI",
                    "summary": existing_before_write.get("summary") or "",
                    "keywords": existing_before_write.get("keywords") or [],
                    "bilingual_metadata": serving_metadata,
                },
                pipeline_version="content-hub-live-v1",
                status="ok",
            )
        row = storage.get_file_with_catalog(item["url"])
        if not row or row.get("sha256") != item["raw_sha256"]:
            raise RuntimeError("metadata-only target update failed exact URL/raw-SHA readback")
        if not _existing_is_current(storage, item, kb_ids):
            raise RuntimeError("metadata-only target update failed Hub metadata/date readback")
        return (
            {
                "url": item["url"],
                "content_version_id": item["content_version_id"],
                "raw_sha256": item["raw_sha256"],
                "markdown_text_variant_id": item["markdown_text_variant_id"],
                "markdown_sha256": item["markdown_sha256"],
                "hub_markdown_sha256": item["hub_markdown_sha256"],
                "hub_markdown_sha256_kind": item["hub_markdown_sha256_kind"],
                "metadata_fingerprint": item["metadata_fingerprint"],
                "status": "written",
                "source_site": row.get("source_site"),
                "first_seen": row.get("first_seen"),
                "metadata_only": True,
                "published_time_status": (
                    "verified_source_date"
                    if item.get("published_time") is not None
                    else (
                        "legacy_preserved_unverified"
                        if row.get("published_time") is not None
                        else "unknown"
                    )
                ),
            },
            False,
        )
    local_path = _verified_existing_blob(storage, item["raw_sha256"], len(item["raw_bytes"]))
    if local_path is None:
        local_path = _write_cas(data_root, item["raw_bytes"], item["raw_sha256"])
    existing = storage.get_file_with_catalog(item["url"])
    source_site = item.get("source_site")
    if source_site is None and existing:
        source_site = existing.get("source_site")
    effective_published_time = item.get("published_time")
    if effective_published_time is None and existing:
        effective_published_time = existing.get("published_time")

    # Keep old deployed Storage signatures compatible. The outer transaction
    # ensures the narrowly scoped reactivation joins the native upserts.
    with storage.transaction(immediate=True):
        storage.upsert_blob(
            item["raw_sha256"], str(local_path), len(item["raw_bytes"]), item["content_type"]
        )
        storage.upsert_file(
            item["url"],
            item["raw_sha256"],
            item["title"],
            source_site,
            item.get("source_page_url"),
            item.get("original_filename") or Path(item["url"].split("?")[0]).name,
            str(local_path),
            len(item["raw_bytes"]),
            item["content_type"],
            item.get("last_modified"),
            item.get("etag"),
            effective_published_time,
            content_kind="file",
        )
        # The old ef906bd upsert_file preserves deleted_at. Only the selected
        # exact URL is reactivated; unrelated retired files remain untouched.
        storage._conn.execute("UPDATE files SET deleted_at = NULL WHERE url = ?", (item["url"],))
        ok, reason = storage.update_file_markdown(
            item["url"], item["markdown"], "local-live-capture-v1"
        )
        if not ok:
            raise RuntimeError(f"native Markdown upsert failed: {reason}")
        storage.upsert_catalog_item(
            {
                "url": item["url"],
                "sha256": item["raw_sha256"],
                "title": item["title"],
                "category": "AI",
                "summary": item["target_summary"],
                "keywords": item["target_keywords"],
                "bilingual_metadata": serving_metadata,
            },
            pipeline_version="content-hub-live-v1",
            status="ok",
        )
        memberships = {kb_id: manager.add_files_to_kb(kb_id, [item["url"]]) for kb_id in kb_ids}

    row = storage.get_file_with_catalog(item["url"])
    if (
        not row
        or row.get("deleted_at") is not None
        or row.get("sha256") != item["raw_sha256"]
        or row.get("source_site") != source_site
    ):
        raise RuntimeError("target file readback failed URL/raw SHA/reactivation check")
    if row.get("markdown_content") != item["markdown"]:
        raise RuntimeError("target Markdown exact readback failed")
    if row.get("category") != "AI" or row.get("catalog_status") != "ok":
        raise RuntimeError("target AI catalog selector readback failed")
    if not _existing_is_current(storage, item, kb_ids):
        raise RuntimeError("target bilingual enrichment/version fingerprint readback failed")
    return (
        {
            "url": item["url"],
            "content_version_id": item["content_version_id"],
            "raw_sha256": item["raw_sha256"],
            "markdown_text_variant_id": item["markdown_text_variant_id"],
            "markdown_sha256": item["markdown_sha256"],
            "hub_markdown_sha256": item["hub_markdown_sha256"],
            "hub_markdown_sha256_kind": item["hub_markdown_sha256_kind"],
            "metadata_fingerprint": item["metadata_fingerprint"],
            "status": "written",
            "source_site": row.get("source_site"),
            "published_time_status": (
                "verified_source_date"
                if item.get("published_time") is not None
                else (
                    "legacy_preserved_unverified"
                    if row.get("published_time") is not None
                    else "unknown"
                )
            ),
            "kb_memberships": {
                kb_id: {
                    "added_count": int(value.get("added_count") or 0),
                    "skipped_count": int(value.get("skipped_count") or 0),
                }
                for kb_id, value in memberships.items()
            },
            "first_seen": row.get("first_seen"),
        },
        needs_chunks,
    )


def _wait_task(runtime: Any, task_id: str, *, timeout_seconds: int = 21600) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = runtime._pipeline_task_status(task_id)
        if status in _TERMINAL_TASK_STATES:
            result = dict(runtime._pipeline_task_result(task_id) or {})
            if status != "completed":
                result["id"] = str(result.get("id") or task_id)
                result["type"] = str(result.get("type") or "task")
                result["status"] = str(status)
                diagnostic = {
                    key: result[key]
                    for key in ("id", "type", "status", "errors", "error_details", "log_file")
                    if key in result
                }
                raise _NativeTaskFailure(diagnostic)
            return result
        if status is None:
            raise RuntimeError("native task disappeared before completion")
        time.sleep(1)
    raise TimeoutError("native task did not finish before the bounded wait expired")


def _refresh_ready(runtime: Any, storage: Any, kb: Any, file_urls: list[str]) -> dict[str, Any]:
    from ai_actuarial.rag.kb_index import resolve_kb_bound_chunks

    # Reuse the configured chunk profile, chunk sets and server embedding identity.
    if file_urls:
        chunk_task_id = runtime.start_background_task(
            "chunk_generation",
            {
                "profile_id": str(kb.chunk_profile_id),
                "files": [
                    {
                        "file_url": url,
                        "markdown_hash": hashlib.sha256(
                            str(storage.get_file_with_catalog(url)["markdown_content"]).encode(
                                "utf-8"
                            )
                        ).hexdigest(),
                    }
                    for url in file_urls
                ],
            },
            task_name=f"Local ingest chunks: {kb.kb_id}",
        )
        chunk_result = _wait_task(runtime, chunk_task_id)
        chunk_result_data = chunk_result.get("result")
        chunk_sets = (
            chunk_result_data.get("chunk_sets") if isinstance(chunk_result_data, dict) else None
        )
        if not isinstance(chunk_sets, list):
            raise RuntimeError("native chunk task returned a malformed chunk-set result")
        expected_urls = set(file_urls)
        returned_urls = [
            row.get("file_url") if isinstance(row, dict) else None for row in chunk_sets
        ]
        if (
            len(chunk_sets) != len(expected_urls)
            or any(not isinstance(url, str) or not url for url in returned_urls)
            or set(returned_urls) != expected_urls
        ):
            raise RuntimeError(
                "native chunk task did not return exactly one current chunk set per changed article"
            )
        profile_id = str(kb.chunk_profile_id or "")
        if not profile_id or any(row.get("profile_id") != profile_id for row in chunk_sets):
            raise RuntimeError("native chunk task returned a chunk set for a different KB profile")
        chunk_set_ids = [row.get("chunk_set_id") for row in chunk_sets]
        if any(
            not isinstance(chunk_set_id, str) or not chunk_set_id.strip()
            for chunk_set_id in chunk_set_ids
        ) or len(set(chunk_set_ids)) != len(chunk_set_ids):
            raise RuntimeError("native chunk task did not return distinct nonblank chunk-set IDs")
        embed_id = runtime.start_background_task(
            "embedding_generation",
            {
                "chunk_set_ids": chunk_set_ids,
                "embedding_identity_key": str(kb.embedding_identity_key),
            },
            task_name=f"Local ingest embeddings: {kb.kb_id}",
        )
        _wait_task(runtime, embed_id)
        for row in chunk_sets:
            result = storage.bind_chunk_set_to_kb(
                kb_id=kb.kb_id,
                file_url=str(row["file_url"]),
                chunk_set_id=str(row["chunk_set_id"]),
                bound_by="local-actuarial-flow",
                binding_mode="follow_latest",
            )
            if result.get("kb_id") != kb.kb_id or result.get("file_url") != row["file_url"]:
                raise RuntimeError("native KB chunk binding was not confirmed")
            if (
                result.get("chunk_set_id") != row.get("chunk_set_id")
                or result.get("binding_mode") != "follow_latest"
            ):
                raise RuntimeError("native KB chunk binding readback does not match the source set")
        # Once every requested URL is bound to its native, profile-specific
        # chunk set, a Ready-only retry can safely rebuild the full index
        # without repeating chunk or embedding work.
        _clear_pending_ready_for_kb(Path(runtime.data_root), kb.kb_id, file_urls)

    snapshot = resolve_kb_bound_chunks(storage, kb.kb_id)
    if not snapshot.get("binding_snapshot_fingerprint"):
        raise RuntimeError("full AI KB binding snapshot is unavailable")
    index_payload = {
        "contract_version": 1,
        "kb_id": kb.kb_id,
        "expected_binding_snapshot_fingerprint": snapshot["binding_snapshot_fingerprint"],
        "embedding_identity_key": str(kb.embedding_identity_key),
        "force_rebuild": False,
    }
    index_id = runtime.start_background_task(
        "rag_indexing", index_payload, task_name=f"Local ingest full index: {kb.kb_id}"
    )
    index_task = _wait_task(runtime, index_id)
    index_result = index_task.get("result")
    if not isinstance(index_result, dict) or not index_result.get("index_version_id"):
        raise RuntimeError("native full KB index returned no index version")
    ready_id = str(index_task.get("ready_data_task_id") or "")
    if not ready_id:
        raise RuntimeError("native TaskRuntime did not launch the configured Ready task")
    ready_task = _wait_task(runtime, ready_id)
    ready_result = ready_task.get("result") or {}
    if ready_result.get("publish_status") != "published":
        raise RuntimeError("native Ready Data build did not publish the active Ready version")
    return {
        "index_task_id": index_id,
        "index_version_id": str(index_result["index_version_id"]),
        "ready_task_id": ready_id,
        "ready_result": ready_result,
        "binding_snapshot_fingerprint": snapshot["binding_snapshot_fingerprint"],
    }


def _target_knowledge_bases(manager: Any, target: str) -> dict[str, Any]:
    expected_ids = ("ai", "all") if target == "china" else ("ai",)
    output = {}
    expected_dimension = 1024 if target == "china" else 3072
    for kb_id in expected_ids:
        kb = manager.get_kb(kb_id)
        if not kb or str(kb.kb_id) != kb_id:
            raise RuntimeError(f"existing {target} {kb_id} knowledge base was not found")
        if (
            int(kb.embedding_dimension or 0) != expected_dimension
            or not str(kb.embedding_identity_key or "").strip()
        ):
            raise RuntimeError(
                f"existing {target} {kb_id} embedding profile does not match its approved dimension/identity"
            )
        output[kb_id] = kb
    return output


def _read_target_profiles(runtime: Any, target: str) -> dict[str, dict[str, Any]]:
    """Read the existing serving KB profiles without Storage or schema migration."""
    from ai_actuarial.postgres import PostgresConnection

    config = runtime._load_site_config()
    database = runtime._resolve_db_path(config)
    expected_ids = ("ai", "all") if target == "china" else ("ai",)
    expected_dimension = 1024 if target == "china" else 3072
    connection = PostgresConnection(database, read_only=True)
    try:
        rows = connection.execute(
            "SELECT kb_id, embedding_provider, embedding_model, embedding_dimension, "
            "embedding_identity_key, chunk_size, chunk_overlap, chunk_profile_id "
            "FROM rag_knowledge_bases WHERE kb_id IN (" + ",".join("?" for _ in expected_ids) + ")",
            expected_ids,
        ).fetchall()
    finally:
        connection.close()
    profiles = {
        str(row["kb_id"]): {
            "embedding_provider": str(row["embedding_provider"]),
            "embedding_model": str(row["embedding_model"]),
            "embedding_dimension": int(row["embedding_dimension"] or 0),
            "embedding_identity_key": str(row["embedding_identity_key"] or ""),
            "chunk_size": int(row["chunk_size"] or 0),
            "chunk_overlap": int(row["chunk_overlap"] or 0),
            "chunk_profile_id": str(row["chunk_profile_id"] or ""),
        }
        for row in rows
    }
    if set(profiles) != set(expected_ids):
        raise RuntimeError(
            f"existing {target} knowledge base set does not match the approved profile"
        )
    for kb_id, profile in profiles.items():
        if (
            profile["embedding_dimension"] != expected_dimension
            or not profile["embedding_identity_key"]
        ):
            raise RuntimeError(
                f"existing {target} {kb_id} embedding profile is incomplete or changed"
            )
    return profiles


def _normalize_cleanup_records(raw_records: Any, approved_categories: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_records, list) or not 1 <= len(raw_records) <= MAX_BATCH_ITEMS:
        raise ValueError("cleanup manifest must contain one to 100 exact records")
    if not isinstance(approved_categories, list) or not approved_categories:
        raise ValueError("cleanup requires the current canonical category registry")
    urls: set[str] = set()
    output = []
    for record in raw_records:
        if not isinstance(record, dict):
            raise ValueError("cleanup manifest record must be an object")
        url = record.get("url")
        raw_sha = record.get("raw_sha256")
        evidence = record.get("hub_evidence")
        if (
            not isinstance(url, str)
            or url != url.strip()
            or not url.startswith(("https://", "http://"))
            or url in urls
            or not isinstance(raw_sha, str)
            or not re.fullmatch(r"[0-9a-f]{64}", raw_sha)
            or not isinstance(evidence, dict)
            or evidence.get("url") != url
            or evidence.get("raw_sha256") != raw_sha
        ):
            raise ValueError("cleanup record requires a unique exact URL/raw-SHA Hub binding")
        urls.add(url)
        categories = evidence.get("categories")
        primary = evidence.get("primary_category")
        if not isinstance(categories, list) or not 1 <= len(categories) <= 4:
            raise ValueError("cleanup Hub evidence must include one to four ordered categories")
        keys = [category.get("key") for category in categories if isinstance(category, dict)]
        if (
            len(keys) != len(categories)
            or len(set(keys)) != len(keys)
            or any(key not in approved_categories for key in keys)
            or keys[0] == "AI"
            or primary != keys[0]
            or any(
                not isinstance(category.get("evidence"), list)
                or len(category["evidence"]) > 3
                or (not category["evidence"] and index != 0)
                or (category["evidence"] and not 1 <= len(category["evidence"]) <= 3)
                or any(
                    not isinstance(value, str) or not value.strip()
                    for value in category["evidence"]
                )
                for index, category in enumerate(categories)
            )
        ):
            raise ValueError(
                "cleanup requires exact non-AI-first Hub categories; only legacy primary evidence may be empty"
            )
        version_id = evidence.get("content_version_id")
        if type(version_id) is not int or version_id < 1:
            raise ValueError("cleanup Hub content_version_id is malformed")
        output.append(
            {
                "url": url,
                "raw_sha256": raw_sha,
                "content_version_id": version_id,
                "primary_category": primary,
                "categories": categories,
            }
        )
    return output


def _cleanup_memberships(storage: Any, url: str) -> list[str]:
    rows = storage._conn.execute(
        "SELECT kb_id FROM rag_kb_files WHERE file_url = ? ORDER BY kb_id", (url,)
    ).fetchall()
    return [str(row["kb_id"] if isinstance(row, dict) else row[0]) for row in rows]


def _normalize_metadata_records(raw_records: Any, approved_categories: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_records, list) or not 1 <= len(raw_records) <= MAX_BATCH_ITEMS:
        raise ValueError("metadata backfill manifest must contain one to 100 exact records")
    if not isinstance(approved_categories, list) or not approved_categories:
        raise ValueError("metadata backfill requires the current canonical category registry")
    expected_date_keys = set(_DATE_FACT_SEMANTICS)
    urls: set[str] = set()
    output = []
    for record in raw_records:
        if not isinstance(record, dict):
            raise ValueError("metadata backfill record must be an object")
        url = record.get("url")
        raw_sha = record.get("raw_sha256")
        if (
            not isinstance(url, str)
            or url != url.strip()
            or not url.startswith(("https://", "http://"))
            or url in urls
            or not isinstance(raw_sha, str)
            or not re.fullmatch(r"[0-9a-f]{64}", raw_sha)
        ):
            raise ValueError("metadata backfill requires unique exact URL/raw-SHA identities")
        urls.add(url)
        for field in ("content_version_id", "markdown_text_variant_id"):
            if type(record.get(field)) is not int or record[field] < 1:
                raise ValueError(f"metadata backfill requires a positive {field}")
        hashes = (
            record.get("markdown_sha256"),
            record.get("hub_markdown_sha256"),
            record.get("source_signature"),
            record.get("result_sha256"),
        )
        if any(
            not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
            for value in hashes
        ):
            raise ValueError("metadata backfill requires lowercase verified Hub SHA-256 values")
        if record.get("hub_markdown_sha256_kind") not in {"raw_utf8", "json_payload_utf8"}:
            raise ValueError("metadata backfill Hub Markdown hash kind is unsupported")
        categories = record.get("categories")
        if not isinstance(categories, list) or not 1 <= len(categories) <= 4:
            raise ValueError("metadata backfill requires one to four ordered Hub categories")
        keys = [entry.get("key") for entry in categories if isinstance(entry, dict)]
        if (
            len(keys) != len(categories)
            or len(set(keys)) != len(keys)
            or keys[0] != "AI"
            or any(key not in approved_categories for key in keys)
            or record.get("source_primary_category") != "AI"
            or any(
                not isinstance(entry.get("evidence"), list)
                or len(entry["evidence"]) > 3
                or (not entry["evidence"] and index != 0)
                or (entry["evidence"] and not 1 <= len(entry["evidence"]) <= 3)
                or any(
                    not isinstance(quote, str) or not quote.strip() for quote in entry["evidence"]
                )
                for index, entry in enumerate(categories)
            )
        ):
            raise ValueError(
                "metadata backfill requires AI-first Hub categories; only legacy primary evidence may be empty"
            )
        facts = record.get("date_facts")
        if not isinstance(facts, dict) or set(facts) != expected_date_keys:
            raise ValueError("metadata backfill date_facts must contain the three semantic fields")
        for field, semantic in _DATE_FACT_SEMANTICS.items():
            fact = facts[field]
            if fact is None:
                continue
            if not isinstance(fact, dict):
                raise ValueError(f"metadata backfill {field} fact must be an object or null")
            value, precision = fact.get("value"), fact.get("precision")
            evidence, location = fact.get("evidence"), fact.get("location")
            if (
                fact.get("semantic") != semantic
                or not isinstance(value, str)
                or not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", value)
                or precision not in {"year", "month", "day"}
                or len(value) != {"year": 4, "month": 7, "day": 10}[precision]
                or not isinstance(evidence, str)
                or not evidence.strip()
                or not isinstance(location, str)
                or not location.strip()
                or len(location) > 120
            ):
                raise ValueError(f"metadata backfill {field} fact is malformed")
            try:
                date.fromisoformat(
                    value
                    + ("-01-01" if precision == "year" else "-01" if precision == "month" else "")
                )
            except ValueError as exc:
                raise ValueError(
                    f"metadata backfill {field} value is not a valid ISO date"
                ) from exc
        expected_published_time = record.get("expected_published_time")
        if "expected_published_time" not in record or (
            expected_published_time is not None
            and (
                not isinstance(expected_published_time, str) or not expected_published_time.strip()
            )
        ):
            raise ValueError(
                "metadata backfill requires exact expected_published_time, including null"
            )
        review_status = record.get("date_review_status")
        if review_status not in {"complete", "candidate_limit_gap", "unsupported_format_gap"}:
            raise ValueError("metadata backfill date review status is unsupported")
        review_reason = record.get("date_review_reason")
        if review_reason is not None and not isinstance(review_reason, str):
            raise ValueError("metadata backfill date review reason is malformed")
        unresolved = record.get("date_review_unresolved") or []
        if not isinstance(unresolved, list):
            raise ValueError("metadata backfill unresolved date evidence must be an array")
        if (review_status == "complete" and unresolved) or (
            review_status != "complete" and not (review_reason or "").strip()
        ):
            raise ValueError(
                "metadata backfill date-review status and unresolved evidence disagree"
            )
        if any(
            not isinstance(item, dict)
            or item.get("field") not in expected_date_keys
            or not isinstance(item.get("evidence"), str)
            or not item["evidence"].strip()
            for item in unresolved
        ):
            raise ValueError("metadata backfill unresolved date evidence is malformed")
        annotation = {
            key: record.get(key)
            for key in (
                "categories",
                "date_facts",
                "date_review_status",
                "date_review_reason",
                "date_review_unresolved",
            )
        }
        if _hash(_canonical_json(annotation).encode("utf-8")) != record["result_sha256"]:
            raise ValueError("metadata backfill annotation does not match its Hub result digest")
        output.append(
            {
                **record,
                "expected_published_time": expected_published_time,
                "date_review_unresolved": unresolved,
            }
        )
    return output


def _metadata_backfill_enrichment(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: record.get(key)
        for key in (
            "content_version_id",
            "markdown_text_variant_id",
            "markdown_sha256",
            "hub_markdown_sha256",
            "hub_markdown_sha256_kind",
            "source_primary_category",
            "categories",
            "date_facts",
            "date_review_status",
            "date_review_reason",
            "date_review_unresolved",
            "source_signature",
            "result_sha256",
        )
    } | {"ordered_categories": record["categories"]}


def _metadata_matches(existing: Any, expected: dict[str, Any]) -> bool:
    if not isinstance(existing, dict):
        return False
    return all(existing.get(key) == value for key, value in expected.items())


def apply_metadata_backfill(
    payload: dict[str, Any],
    *,
    runtime_factory: Callable[[], Any] | None = None,
    storage_factory: Callable[..., Any] | None = None,
    manager_factory: Callable[[Any], Any] | None = None,
) -> dict[str, Any]:
    """Update Hub metadata/date fields on exact existing records, without chunk or Ready work."""
    target = str(payload.get("target") or "")
    if target not in {"china", "overseas"}:
        raise ValueError("target must be china or overseas")
    if payload.get("schema_version") != 1:
        raise ValueError("metadata backfill payload schema_version must be 1")
    dry_run = payload.get("dry_run", True)
    if type(dry_run) is not bool:
        raise ValueError("metadata backfill dry_run must be boolean")
    records = _normalize_metadata_records(
        payload.get("records"), payload.get("approved_categories")
    )
    expected_date_keys = set(_DATE_FACT_SEMANTICS)
    if runtime_factory is None:
        from ai_actuarial.task_runtime import NativeTaskRuntime

        runtime_factory = NativeTaskRuntime
    runtime = runtime_factory()
    if storage_factory is None:
        from ai_actuarial.storage import Storage

        storage_factory = Storage.open_read_only if dry_run else Storage
    db_path = runtime._resolve_db_path(runtime._load_site_config())
    storage = storage_factory(db_path, data_root=runtime.data_root)
    try:
        if manager_factory is None:
            expected_kbs = list(_read_target_profiles(runtime, target))
        else:
            knowledge_bases = _target_knowledge_bases(manager_factory(storage), target)
            expected_kbs = list(knowledge_bases)
        data_root = Path(runtime.data_root)
        pending_before = _read_pending_index_refresh(data_root, target)
        unexpected = set(pending_before) - set(expected_kbs)
        if unexpected:
            raise RuntimeError(
                "pending index refresh state references an unexpected knowledge base"
            )
        audit = []
        prepared = []
        for record in records:
            row = storage.get_file_with_catalog(record["url"])
            if not row:
                raise ValueError("metadata backfill URL is absent from the existing target")
            if row.get("sha256") != record["raw_sha256"]:
                raise ValueError("metadata backfill exact target URL/raw-SHA binding mismatch")
            if row.get("deleted_at") is not None or row.get("catalog_status") != "ok":
                raise ValueError(
                    "metadata backfill target record is not active and catalog-visible"
                )
            if row.get("category") != "AI":
                raise ValueError("metadata backfill target catalog category is not AI")
            markdown = row.get("markdown_content")
            if not isinstance(markdown, str) or not markdown.strip():
                raise ValueError("metadata backfill target Markdown is missing")
            markdown_sha = _hash(markdown.encode("utf-8"))
            if markdown_sha != record["markdown_sha256"]:
                raise ValueError("metadata backfill target Markdown binding mismatch")
            expected_hub_sha = {
                "raw_utf8": markdown_sha,
                "json_payload_utf8": _hash(_canonical_json(markdown).encode("utf-8")),
            }[record["hub_markdown_sha256_kind"]]
            if expected_hub_sha != record["hub_markdown_sha256"]:
                raise ValueError("metadata backfill Hub Markdown digest binding mismatch")
            if any(
                quote not in markdown
                for category in record["categories"]
                for quote in category["evidence"]
            ):
                raise ValueError(
                    "metadata backfill category evidence does not match target Markdown"
                )
            if any(
                fact and fact["evidence"] not in markdown for fact in record["date_facts"].values()
            ):
                raise ValueError("metadata backfill date evidence does not match target Markdown")
            if any(
                not isinstance(item, dict)
                or item.get("field") not in expected_date_keys
                or not isinstance(item.get("evidence"), str)
                or item["evidence"] not in markdown
                for item in record["date_review_unresolved"]
            ):
                raise ValueError(
                    "metadata backfill unresolved date evidence does not match Markdown"
                )
            memberships = _cleanup_memberships(storage, record["url"])
            if set(memberships) != set(expected_kbs):
                raise ValueError(
                    "metadata backfill target KB memberships are incomplete or unexpected"
                )
            current_published_time = row.get("published_time")
            projected_date = _publication_date_value(record["date_facts"])
            allowed_dates = {record["expected_published_time"]}
            if projected_date is not None:
                # A retry after the native date write may replay the original CAS value.
                allowed_dates.add(projected_date)
            if current_published_time not in allowed_dates:
                raise ValueError(
                    "metadata backfill published_time changed since exact manifest readback"
                )
            current_metadata = row.get("bilingual_metadata")
            if not isinstance(current_metadata, dict):
                current_metadata = {}
            current_enrichment = current_metadata.get("hub_enrichment")
            if isinstance(current_enrichment, dict):
                existing_version_id = current_enrichment.get("content_version_id")
                if (
                    existing_version_id is not None
                    and existing_version_id != record["content_version_id"]
                ):
                    raise ValueError("metadata backfill existing Hub version binding conflicts")
            expected_enrichment = _metadata_backfill_enrichment(record)
            needs_update = not _metadata_matches(
                current_enrichment, expected_enrichment
            ) or current_published_time != (projected_date or record["expected_published_time"])
            effective_published_time = projected_date or current_published_time
            audit.append(
                {
                    "url": record["url"],
                    "raw_sha256": record["raw_sha256"],
                    "content_version_id": record["content_version_id"],
                    "target_status": "would_update" if needs_update else "already_current",
                    "current_published_time": current_published_time,
                    "projected_published_time": effective_published_time,
                    "published_time_status": (
                        "verified_source_date"
                        if projected_date is not None
                        else (
                            "legacy_preserved_unverified"
                            if current_published_time is not None
                            else "unknown"
                        )
                    ),
                    "knowledge_base_memberships": memberships,
                }
            )
            prepared.append(
                {
                    "record": record,
                    "row": row,
                    "current_published_time": current_published_time,
                    "effective_published_time": effective_published_time,
                    "needs_update": needs_update,
                }
            )
        from ai_actuarial.capacity import capacity_status

        capacity = capacity_status(path="/", threshold_percent=80.0)
        changed_kbs = sorted(
            set(pending_before)
            | (set(expected_kbs) if any(item["needs_update"] for item in prepared) else set())
        )
        if dry_run:
            return {
                "schema_version": 1,
                "target": target,
                "dry_run": True,
                "capacity": capacity,
                "records": audit,
                "ready_status": "deferred",
                "pending_index_refresh": changed_kbs,
            }
        if any(item["needs_update"] for item in prepared) and capacity.get("blocked"):
            error = (
                f"[CAPACITY_BLOCKED] / is {capacity.get('used_percent')}% used, at or over the "
                "80% threshold; no metadata or date changes were made"
            )
            return {
                "schema_version": 1,
                "target": target,
                "dry_run": False,
                "capacity": capacity,
                "records": audit,
                "failures": [{"url": "", "error": error}],
                "backfill_status": "not_started_capacity_blocked",
                "ready_status": "deferred",
                "pending_index_refresh": pending_before,
            }
        if changed_kbs:
            _write_pending_index_refresh(data_root, target, changed_kbs)
        failures = []
        for item in prepared:
            if not item["needs_update"]:
                continue
            record = item["record"]
            try:
                with storage.transaction(immediate=True):
                    storage._lock_postgres_key("file", record["url"])
                    current = storage.get_file_with_catalog(record["url"])
                    if (
                        not current
                        or current.get("sha256") != record["raw_sha256"]
                        or current.get("deleted_at") is not None
                        or current.get("catalog_status") != "ok"
                        or current.get("category") != "AI"
                        or current.get("markdown_content") != item["row"].get("markdown_content")
                        or current.get("published_time")
                        not in {
                            item["current_published_time"],
                            item["effective_published_time"],
                        }
                        or set(_cleanup_memberships(storage, record["url"])) != set(expected_kbs)
                    ):
                        raise RuntimeError(
                            "metadata backfill exact target precondition changed before write"
                        )
                    current_metadata = current.get("bilingual_metadata")
                    if not isinstance(current_metadata, dict):
                        current_metadata = {}
                    current_enrichment = current_metadata.get("hub_enrichment")
                    if isinstance(current_enrichment, dict):
                        existing_version_id = current_enrichment.get("content_version_id")
                        if (
                            existing_version_id is not None
                            and existing_version_id != record["content_version_id"]
                        ):
                            raise RuntimeError(
                                "metadata backfill Hub version binding changed before write"
                            )
                    latest_enrichment = {
                        **(current_enrichment if isinstance(current_enrichment, dict) else {}),
                        **_metadata_backfill_enrichment(record),
                    }
                    latest_metadata = {
                        **current_metadata,
                        "hub_enrichment": latest_enrichment,
                    }
                    before = storage._ready_data_builder_metadata_snapshot(record["url"])
                    if item["effective_published_time"] != current.get("published_time"):
                        storage._conn.execute(
                            "UPDATE files SET published_time = ? WHERE url = ? AND sha256 = ?",
                            (
                                item["effective_published_time"],
                                record["url"],
                                record["raw_sha256"],
                            ),
                        )
                    storage._mark_ready_data_builder_metadata_change(
                        file_url=record["url"], before=before
                    )
                    storage.upsert_catalog_item(
                        {
                            "url": record["url"],
                            "sha256": record["raw_sha256"],
                            "category": "AI",
                            "summary": current.get("summary") or "",
                            "keywords": current.get("keywords") or [],
                            "bilingual_metadata": latest_metadata,
                        },
                        pipeline_version="content-hub-metadata-backfill-v1",
                        status="ok",
                    )
                saved = storage.get_file_with_catalog(record["url"])
                if (
                    not saved
                    or saved.get("sha256") != record["raw_sha256"]
                    or saved.get("markdown_content") != item["row"].get("markdown_content")
                    or saved.get("published_time") != item["effective_published_time"]
                    or not _metadata_matches(
                        (saved.get("bilingual_metadata") or {}).get("hub_enrichment"),
                        _metadata_backfill_enrichment(record),
                    )
                ):
                    raise RuntimeError(
                        "metadata backfill failed exact target metadata/date readback"
                    )
                audit_row = next(row for row in audit if row["url"] == record["url"])
                audit_row["target_status"] = "updated"
            except Exception as exc:
                failures.append({"url": record["url"], "error": str(exc)})
        return {
            "schema_version": 1,
            "target": target,
            "dry_run": False,
            "capacity": capacity,
            "records": audit,
            "failures": failures,
            "backfill_status": "partial" if failures else "succeeded",
            "ready_status": "deferred",
            "pending_index_refresh": _read_pending_index_refresh(data_root, target),
            "resume_with_same_manifest": bool(
                failures or _read_pending_index_refresh(data_root, target)
            ),
        }
    finally:
        storage.close()


def apply_cleanup(
    payload: dict[str, Any],
    *,
    runtime_factory: Callable[[], Any] | None = None,
    storage_factory: Callable[..., Any] | None = None,
    manager_factory: Callable[[Any], Any] | None = None,
    ready_builder: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Audit or retire exact Hub-proven non-AI-first records on one target."""
    target = str(payload.get("target") or "")
    if target not in {"china", "overseas"}:
        raise ValueError("target must be china or overseas")
    if payload.get("schema_version") != 1:
        raise ValueError("cleanup payload schema_version must be 1")
    dry_run = payload.get("dry_run", True)
    if type(dry_run) is not bool:
        raise ValueError("cleanup dry_run must be boolean")
    records = _normalize_cleanup_records(payload.get("records"), payload.get("approved_categories"))
    if runtime_factory is None:
        from ai_actuarial.task_runtime import NativeTaskRuntime

        runtime_factory = NativeTaskRuntime
    runtime = runtime_factory()
    if storage_factory is None:
        from ai_actuarial.storage import Storage

        storage_factory = Storage.open_read_only if dry_run else Storage
    db_path = runtime._resolve_db_path(runtime._load_site_config())
    storage = storage_factory(db_path, data_root=runtime.data_root)
    try:
        if dry_run and manager_factory is None:
            knowledge_bases = {}
            expected_kbs = list(_read_target_profiles(runtime, target))
        else:
            if manager_factory is None:
                from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager

                manager_factory = KnowledgeBaseManager
            manager = manager_factory(storage)
            knowledge_bases = _target_knowledge_bases(manager, target)
            expected_kbs = list(knowledge_bases)
        data_root = Path(runtime.data_root)
        pending_index_refresh = _read_pending_index_refresh(data_root, target)
        unexpected = (
            set(_read_pending_cleanup(data_root, target)) | set(pending_index_refresh)
        ) - set(expected_kbs)
        if unexpected:
            raise RuntimeError(
                "pending cleanup Ready state references an unexpected knowledge base"
            )
        pending_urls = _read_pending_ready(data_root, target)
        audit = []
        affected_kbs: set[str] = set(_read_pending_cleanup(data_root, target))
        affected_kbs.update(pending_index_refresh)
        for record in records:
            row = storage.get_file_with_catalog(record["url"])
            if row and row.get("sha256") != record["raw_sha256"]:
                raise ValueError("target URL exists with a different raw SHA-256; refusing cleanup")
            memberships = _cleanup_memberships(storage, record["url"])
            if set(memberships) - set(expected_kbs):
                raise ValueError(
                    "target URL has a knowledge-base membership outside the approved profile"
                )
            pending_memberships = [
                kb_id for kb_id in expected_kbs if record["url"] in pending_urls.get(kb_id, [])
            ]
            affected_kbs.update(memberships)
            affected_kbs.update(pending_memberships)
            status = (
                "already_absent"
                if row is None
                else (
                    "already_retired"
                    if row.get("deleted_at") is not None
                    and not memberships
                    and not pending_memberships
                    else "present"
                )
            )
            audit.append(
                {
                    **record,
                    "target_status": status,
                    "target_sha256": row.get("sha256") if row else None,
                    "catalog_status": row.get("catalog_status") if row else None,
                    "deleted_at": row.get("deleted_at") if row else None,
                    "knowledge_base_memberships": memberships,
                    "pending_ready_memberships": pending_memberships,
                }
            )
        from ai_actuarial.capacity import capacity_status

        capacity = capacity_status(path="/", threshold_percent=80.0)
        if dry_run:
            return {
                "schema_version": 1,
                "target": target,
                "dry_run": True,
                "capacity": capacity,
                "knowledge_bases": expected_kbs,
                "records": audit,
                "ready_status": "not_required",
                "pending_cleanup_ready": sorted(affected_kbs),
                "pending_index_refresh": pending_index_refresh,
            }
        if affected_kbs and capacity.get("blocked"):
            error = (
                f"[CAPACITY_BLOCKED] / is {capacity.get('used_percent')}% used, at or over the "
                "80% threshold; no file or membership changes were made"
            )
            return {
                "schema_version": 1,
                "target": target,
                "dry_run": False,
                "capacity": capacity,
                "knowledge_bases": expected_kbs,
                "records": audit,
                "failures": [{"url": "", "error": error}],
                "cleanup_status": "not_started_capacity_blocked",
                "ready_status": "failed",
                "ready_error": error,
                "ready": {},
                "pending_cleanup_ready": _read_pending_cleanup(data_root, target),
                "resume_with_same_manifest": True,
            }

        pending_cleanup = sorted(affected_kbs)
        if pending_cleanup:
            _write_pending_cleanup(
                data_root,
                target,
                sorted(set(pending_cleanup) | set(_read_pending_cleanup(data_root, target))),
            )
        failures: list[dict[str, str]] = []
        failed_kbs: set[str] = set()
        for record, detail in zip(records, audit, strict=True):
            url = record["url"]
            audited_memberships = set(detail["knowledge_base_memberships"])
            pending_memberships = set(detail["pending_ready_memberships"])
            record_kbs = audited_memberships | pending_memberships
            cleared_pending_memberships: set[str] = set()
            try:
                # File writers take this advisory key lock while holding their
                # outer transaction. Keep it through the exact SHA/membership
                # recheck, all membership removals, and catalog retirement.
                with storage.transaction(immediate=True):
                    storage._lock_postgres_key("file", url)
                    current = storage.get_file_with_catalog(url)
                    if detail["target_status"] == "already_absent":
                        if current is not None:
                            raise RuntimeError(
                                "target URL appeared after cleanup audit; refusing cleanup"
                            )
                    else:
                        if current is None:
                            raise RuntimeError(
                                "target URL disappeared after cleanup audit; refusing cleanup"
                            )
                        if current.get("sha256") != record["raw_sha256"]:
                            raise RuntimeError(
                                "target URL raw SHA-256 changed after cleanup audit; refusing cleanup"
                            )
                        if (
                            current.get("deleted_at") != detail["deleted_at"]
                            or current.get("catalog_status") != detail["catalog_status"]
                        ):
                            raise RuntimeError(
                                "target visibility changed after cleanup audit; refusing cleanup"
                            )

                    current_memberships = _cleanup_memberships(storage, url)
                    current_kbs = set(current_memberships)
                    record_kbs.update(current_kbs)
                    if current_kbs - set(expected_kbs):
                        raise RuntimeError(
                            "target URL gained a knowledge-base membership outside the approved profile"
                        )
                    if current_kbs != audited_memberships:
                        raise RuntimeError(
                            "target knowledge-base memberships changed after cleanup audit"
                        )

                    latest_pending = _read_pending_ready(data_root, target)
                    cleared_pending_memberships = {
                        kb_id for kb_id in expected_kbs if url in latest_pending.get(kb_id, [])
                    }
                    record_kbs.update(cleared_pending_memberships)
                    if cleared_pending_memberships:
                        current_cleanup = set(_read_pending_cleanup(data_root, target))
                        _write_pending_cleanup(
                            data_root,
                            target,
                            sorted(current_cleanup | cleared_pending_memberships),
                        )
                        for kb_id in sorted(cleared_pending_memberships):
                            _clear_pending_ready(data_root, target, kb_id, [url])

                    for kb_id in expected_kbs:
                        manager.remove_files_from_kb(kb_id, [url])
                    if detail["target_status"] != "already_retired":
                        storage.mark_file_deleted(url, datetime.now(timezone.utc).isoformat())

                detail["catalog_retired"] = True
                detail["membership_removals"] = {kb_id: "completed" for kb_id in expected_kbs}
            except Exception as exc:
                failed_kbs.update(record_kbs)
                # A precondition or native write failure leaves the database
                # transaction unchanged; preserve any pending chunk work too.
                pending_to_restore = pending_memberships | cleared_pending_memberships
                if pending_to_restore:
                    _add_pending_ready(data_root, target, sorted(pending_to_restore), [url])
                failures.append({"url": url, "error": f"cleanup transaction: {exc}"})
                detail["catalog_retired"] = False
                detail["membership_removals"] = {
                    kb_id: "pending" if kb_id in record_kbs else "not_required"
                    for kb_id in expected_kbs
                }

        ready = {}
        ready_errors = {}
        builder = ready_builder or _refresh_ready
        for kb_id in _read_pending_cleanup(data_root, target):
            if kb_id in failed_kbs:
                ready_errors[kb_id] = "native membership removal must be retried before Ready"
                continue
            try:
                from ai_actuarial.capacity import ensure_capacity

                ensure_capacity(path="/", operation="local_non_ai_primary_cleanup_index")
                ready[kb_id] = builder(runtime, storage, knowledge_bases[kb_id], [])
                _clear_pending_cleanup_kb(data_root, target, kb_id)
                _clear_pending_index_refresh_kb(data_root, target, kb_id)
            except Exception as exc:
                ready_errors[kb_id] = str(exc)
        remaining_cleanup = _read_pending_cleanup(data_root, target)
        pending_after = _read_pending_ready(data_root, target)
        if ready_errors:
            failures.extend(
                {"url": "", "error": f"{kb_id} Ready/index: {error}"}
                for kb_id, error in ready_errors.items()
            )
        return {
            "schema_version": 1,
            "target": target,
            "dry_run": False,
            "capacity": capacity,
            "knowledge_bases": expected_kbs,
            "records": audit,
            "failures": failures,
            "cleanup_status": "partial" if failures else "succeeded",
            "ready_status": "failed" if ready_errors else "succeeded" if ready else "not_required",
            "ready_error": ready_errors or None,
            "ready": ready,
            "pending_cleanup_ready": remaining_cleanup,
            "pending_index_refresh": _read_pending_index_refresh(data_root, target),
            "pending_ready_urls": pending_after,
            "resume_with_same_manifest": bool(remaining_cleanup or failures),
        }
    finally:
        storage.close()


def apply_batch(
    payload: dict[str, Any],
    *,
    runtime_factory: Callable[[], Any] | None = None,
    storage_factory: Callable[..., Any] | None = None,
    manager_factory: Callable[[Any], Any] | None = None,
    ready_builder: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    target = str(payload.get("target") or "")
    if target not in {"china", "overseas"}:
        raise ValueError("target must be china or overseas")
    raw_items = payload.get("items") or []
    if not isinstance(raw_items, list) or len(raw_items) > MAX_BATCH_ITEMS:
        raise ValueError("target batch exceeds its item limit")
    approved_categories = payload.get("approved_categories")
    if not isinstance(approved_categories, list) or not approved_categories:
        raise ValueError("target payload requires the current canonical category registry")
    items = [_normalize_item(item, target, approved_categories) for item in raw_items]
    if runtime_factory is None:
        from ai_actuarial.task_runtime import NativeTaskRuntime

        runtime_factory = NativeTaskRuntime
    runtime = runtime_factory()
    if payload.get("preview_only"):
        profiles = _read_target_profiles(runtime, target)
        from ai_actuarial.capacity import capacity_status

        capacity = capacity_status(path="/", threshold_percent=80.0)
        return {
            "schema_version": 1,
            "target": target,
            "preview_only": True,
            "knowledge_bases": profiles,
            "capacity": capacity,
            "acknowledgements": [],
            "failures": [],
            "ready_status": "not_required",
            "ready_error": None,
            "ready": {},
        }
    if storage_factory is None:
        from ai_actuarial.storage import Storage

        storage_factory = Storage
    if manager_factory is None:
        from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager

        manager_factory = KnowledgeBaseManager

    config = runtime._load_site_config()
    db_path = runtime._resolve_db_path(config)
    storage = storage_factory(db_path, data_root=runtime.data_root)
    try:
        manager = manager_factory(storage)
        knowledge_bases = _target_knowledge_bases(manager, target)
        from ai_actuarial.capacity import capacity_status

        capacity = capacity_status(path="/", threshold_percent=80.0)
        data_root = Path(runtime.data_root)
        pending_urls = _read_pending_ready(data_root, target)
        acknowledgements: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        metadata_ready_pending = False
        for item in items:
            was_pending = any(item["url"] in urls for urls in pending_urls.values())
            already_current = _existing_is_current(storage, item, list(knowledge_bases))
            content_current = _existing_content_and_memberships_current(
                storage, item, list(knowledge_bases)
            )
            # Record the intended URL before the item transaction. If the
            # process stops after the file acknowledgement, a restart still
            # knows it must finish native chunk/embed/bind work before Ready.
            if not already_current or was_pending:
                if not content_current or was_pending:
                    pending_urls = _add_pending_ready(
                        data_root, target, list(knowledge_bases), [item["url"]]
                    )
            try:
                ack, needs_chunks = _write_item(
                    storage, manager, item, data_root, list(knowledge_bases)
                )
                acknowledgements.append(ack)
                metadata_ready_pending = metadata_ready_pending or (
                    not needs_chunks and ack.get("status") == "written"
                )
            except Exception as exc:  # per-item isolation preserves earlier acknowledgements
                if not was_pending:
                    for kb_id in knowledge_bases:
                        _clear_pending_ready(data_root, target, kb_id, [item["url"]])
                    pending_urls = _read_pending_ready(data_root, target)
                failures.append({"url": item["url"], "error": str(exc)})

        ready: dict[str, Any] = {}
        ready_errors: dict[str, str] = {}
        ready_evidence: dict[str, list[str]] = {}
        builder = ready_builder or _refresh_ready
        for kb_id, kb in knowledge_bases.items():
            urls = list(dict.fromkeys(pending_urls.get(kb_id, [])))
            needs_ready = bool(urls) or bool(payload.get("ready_pending")) or metadata_ready_pending
            if not needs_ready:
                continue
            try:
                ready[kb_id] = builder(runtime, storage, kb, urls)
            except Exception as exc:
                ready_errors[kb_id] = str(exc)
                if isinstance(exc, _NativeTaskFailure):
                    ready_evidence[kb_id] = exc.diagnostic_evidence
        ready_ok = bool(ready) and not ready_errors
        ready_status = "succeeded" if ready_ok else ("failed" if ready_errors else "not_required")
        pending_after = _read_pending_ready(data_root, target)
        return {
            "schema_version": 1,
            "target": target,
            "knowledge_bases": {
                kb_id: {
                    "embedding_provider": str(kb.embedding_provider),
                    "embedding_model": str(kb.embedding_model),
                    "embedding_dimension": int(kb.embedding_dimension or 0),
                    "embedding_identity_key": str(kb.embedding_identity_key),
                }
                for kb_id, kb in knowledge_bases.items()
            },
            "capacity": capacity,
            "acknowledgements": acknowledgements,
            "failures": failures,
            "ready_status": ready_status,
            "ready_error": ready_errors or None,
            "ready_evidence": ready_evidence or None,
            "ready": ready,
            "pending_ready_urls": pending_after,
        }
    finally:
        storage.close()


def main() -> int:
    payload: Any = None
    try:
        payload = json.load(sys.stdin)
        if isinstance(payload, dict) and payload.get("operation") == "retire_non_ai_primary":
            result = apply_cleanup(payload)
        elif (
            isinstance(payload, dict) and payload.get("operation") == "backfill_ai_primary_metadata"
        ):
            result = apply_metadata_backfill(payload)
        else:
            result = apply_batch(payload)
        sys.stdout.write(_canonical_json(result) + "\n")
        return 0 if not result.get("failures") and result.get("ready_status") != "failed" else 2
    except Exception as exc:
        failure = {"schema_version": 1, "error": str(exc)}
        target = payload.get("target") if isinstance(payload, dict) else None
        if isinstance(target, str):
            failure["target"] = target
        sys.stdout.write(_canonical_json(failure) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
