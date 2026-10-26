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
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

MAX_BATCH_ITEMS = 100
MAX_ARTICLE_BYTES = 40 * 1024 * 1024
_TERMINAL_TASK_STATES = {"completed", "error", "stopped"}


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
    if (
        len(keys) != len(categories)
        or len(set(keys)) != len(keys)
        or "AI" not in keys
        or any(key not in approved_categories for key in keys)
        or any(
            not isinstance(entry.get("evidence"), list)
            or len(entry["evidence"]) > 3
            or any(not isinstance(text, str) or not text.strip() for text in entry["evidence"])
            for entry in categories
        )
    ):
        raise ValueError("target item must have unique canonical categories including AI")
    if any(packages[lang].get("category") != keys[0] for lang in ("zh", "en")):
        raise ValueError(
            "target bilingual primary category does not match its ordered Hub categories"
        )
    if not isinstance(item.get("date_facts"), dict):
        raise ValueError("target item date facts must be an object")
    version_id = item.get("content_version_id")
    md_variant_id = item.get("markdown_text_variant_id")
    if (
        type(version_id) is not int
        or version_id < 1
        or type(md_variant_id) is not int
        or md_variant_id < 1
    ):
        raise ValueError("target item must carry its Hub version and Markdown variant IDs")
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
            "source_primary_category": str(
                item.get("source_primary_category") or packages["en"]["category"]
            ),
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
        "source_primary_category": str(
            item.get("source_primary_category") or packages["en"]["category"]
        ),
        "date_facts": item["date_facts"],
        "date_review_status": item.get("date_review_status"),
        "date_review_reason": item.get("date_review_reason"),
        "date_review_unresolved": item.get("date_review_unresolved") or [],
        "source_signature": item.get("source_signature"),
        "result_sha256": item.get("result_sha256"),
    }
    return {
        **item,
        "url": url,
        "raw_bytes": raw,
        "raw_sha256": raw_sha,
        "markdown_sha256": md_sha,
        "content_type": str(item.get("content_type") or "application/octet-stream"),
        "title": str(item.get("title") or packages["en"]["title"]).strip(),
        "source_site": source_site,
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
        if metadata.get(language) != {**item["bilingual_metadata"][language], "category": "AI"}:
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
            },
            False,
        )

    from ai_actuarial.capacity import ensure_capacity

    ensure_capacity(path="/", operation="local_content_hub_article_upsert")
    local_path = _verified_existing_blob(storage, item["raw_sha256"], len(item["raw_bytes"]))
    if local_path is None:
        local_path = _write_cas(data_root, item["raw_bytes"], item["raw_sha256"])
    existing = storage.get_file_with_catalog(item["url"])
    source_site = item.get("source_site")
    if source_site is None and existing:
        source_site = existing.get("source_site")

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
            item.get("published_time"),
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
                "bilingual_metadata": item["serving_metadata"],
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
            "kb_memberships": {
                kb_id: {
                    "added_count": int(value.get("added_count") or 0),
                    "skipped_count": int(value.get("skipped_count") or 0),
                }
                for kb_id, value in memberships.items()
            },
            "first_seen": row.get("first_seen"),
        },
        True,
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
        for item in items:
            was_pending = any(item["url"] in urls for urls in pending_urls.values())
            already_current = _existing_is_current(storage, item, list(knowledge_bases))
            # Record the intended URL before the item transaction. If the
            # process stops after the file acknowledgement, a restart still
            # knows it must finish native chunk/embed/bind work before Ready.
            if not already_current or was_pending:
                pending_urls = _add_pending_ready(
                    data_root, target, list(knowledge_bases), [item["url"]]
                )
            try:
                ack, _changed = _write_item(
                    storage, manager, item, data_root, list(knowledge_bases)
                )
                acknowledgements.append(ack)
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
            needs_ready = bool(urls) or bool(payload.get("ready_pending"))
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
        result = apply_batch(payload)
        sys.stdout.write(_canonical_json(result) + "\n")
        return 0 if not result["failures"] and result["ready_status"] != "failed" else 2
    except Exception as exc:
        failure = {"schema_version": 1, "error": str(exc)}
        target = payload.get("target") if isinstance(payload, dict) else None
        if isinstance(target, str):
            failure["target"] = target
        sys.stdout.write(_canonical_json(failure) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
