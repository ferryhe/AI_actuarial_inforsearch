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


def _context_url(task_id: str | None) -> str | None:
    value = str(task_id or "")
    if _NATIVE_TASK_ID.fullmatch(value):
        return f"/tasks?task_id={value}"
    return None


def _from_digest(stage: str, code: str, digest: str, task_id: str | None) -> dict[str, str]:
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
    context_url = _context_url(task_id)
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
    return _from_digest(stage, str(code or ""), digest, task_id)


def normalize_item_errors(
    rows: object,
    *,
    task_id: str | None = None,
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
        normalized.append(_from_digest(stage, str(row.get("code") or ""), digest, task_id))
        if len(normalized) == ITEM_ERROR_LIMIT:
            break
    return normalized


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
