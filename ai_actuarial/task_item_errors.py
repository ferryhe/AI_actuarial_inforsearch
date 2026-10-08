from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

ITEM_ERROR_LIMIT = 50

_CODES = {
    "catalog": {
        "catalog_failed": "Catalog processing failed.",
        "file_not_found": "The catalog source was not found.",
    },
    "embedding": {
        "provider_error": "Embedding provider failed.",
        "provider_count_mismatch": "Embedding provider returned an unexpected number of vectors.",
        "invalid_embedding_vector": "Embedding provider returned an invalid vector.",
    },
    "markdown": {
        "conversion_failed": "Markdown conversion failed.",
        "markdown_update_failed": "Converted markdown could not be saved.",
    },
}
_FALLBACK_CODES = {
    "catalog": "catalog_failed",
    "embedding": "provider_error",
    "markdown": "conversion_failed",
}
_NATIVE_TASK_ID = re.compile(r"^task_[0-9]+_[0-9a-f]{16}$")
_OBJECT_ID = re.compile(r"^(file|chunk):([0-9a-f]{64})$")
_FILE_ID = re.compile(r"^[1-9][0-9]*$")


def _task_context_url(task_id: str | None) -> str | None:
    value = str(task_id or "")
    return f"/tasks?task_id={value}" if _NATIVE_TASK_ID.fullmatch(value) else None


def _from_digest(
    stage: str,
    code: str,
    digest: str,
    task_id: str | None = None,
    file_id: object = None,
) -> dict[str, str]:
    codes = _CODES[stage]
    safe_code = code if code in codes else _FALLBACK_CODES[stage]
    kind = "chunk" if stage == "embedding" else "file"
    label = "Chunk" if kind == "chunk" else "File"
    item = {
        "object_id": f"{kind}:{digest}",
        "display_name": f"{label} {digest[:12]}",
        "stage": stage,
        "code": safe_code,
        "summary": codes[safe_code],
    }
    if kind == "file" and _FILE_ID.fullmatch(str(file_id or "")):
        item["file_id"] = str(file_id)
        item["context_url"] = f"/file-detail?file_id={file_id}"
    elif kind == "chunk":
        context_url = _task_context_url(task_id)
        if context_url:
            item["context_url"] = context_url
    return item


def make_item_error(
    stage: str,
    code: str,
    identity: str,
    *,
    task_id: str | None = None,
) -> dict[str, str]:
    if stage not in _CODES:
        raise ValueError(f"unsupported item-error stage: {stage}")
    if not isinstance(identity, str) or not identity:
        raise ValueError("item-error identity must be a non-empty string")
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return _from_digest(stage, str(code or ""), digest, task_id=task_id)


def normalize_item_errors(
    rows: object,
    *,
    task_id: str | None = None,
    file_ids_by_digest: Mapping[str, int | str] | None = None,
) -> list[dict[str, str]]:
    if not isinstance(rows, list):
        return []
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        stage = str(row.get("stage") or "")
        match = _OBJECT_ID.fullmatch(str(row.get("object_id") or ""))
        if stage not in _CODES or match is None:
            continue
        kind, digest = match.groups()
        expected_kind = "chunk" if stage == "embedding" else "file"
        object_id = f"{kind}:{digest}"
        if kind != expected_kind or object_id in seen:
            continue
        seen.add(object_id)
        file_id: int | str | None = None
        if kind == "file":
            if file_ids_by_digest is None:
                saved_id = str(row.get("file_id") or "")
                if _FILE_ID.fullmatch(saved_id):
                    file_id = saved_id
            else:
                file_id = file_ids_by_digest.get(digest)
        normalized.append(
            _from_digest(
                stage,
                str(row.get("code") or ""),
                digest,
                task_id=task_id,
                file_id=file_id,
            )
        )
        if len(normalized) == ITEM_ERROR_LIMIT:
            break
    return normalized


def resolve_item_error_file_ids(rows: object, db_path: str) -> dict[str, int]:
    """Match file-error digests to current file URLs, rejecting ambiguous rows."""
    if not isinstance(rows, list) or not db_path:
        return {}
    digests = {
        match.group(2)
        for row in rows
        if isinstance(row, Mapping)
        and str(row.get("stage") or "") in _CODES
        and (match := _OBJECT_ID.fullmatch(str(row.get("object_id") or ""))) is not None
        and match.group(1) == "file"
    }
    if not digests:
        return {}

    from ai_actuarial.storage import Storage

    storage = Storage(db_path)
    try:
        return storage.get_file_ids_by_url_sha256(digests)
    finally:
        storage.close()


def record_item_error(
    rows: list[dict[str, str]],
    seen: set[str],
    stage: str,
    code: str,
    identity: str,
    *,
    task_id: str | None = None,
) -> bool:
    item = make_item_error(stage, code, identity, task_id=task_id)
    object_id = item["object_id"]
    if object_id in seen:
        return False
    seen.add(object_id)
    if len(rows) < ITEM_ERROR_LIMIT:
        rows.append(item)
    return True
