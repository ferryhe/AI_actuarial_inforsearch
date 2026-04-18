"""
Collection operations service layer.

Contains collection/task start logic extracted from ops_write.py
for better code organization.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ai_actuarial.shared_runtime import get_sites_config_path, load_yaml

logger = logging.getLogger(__name__)

__all__ = [
    "start_collection",
    "browse_folder",
]


# ---------------------------------------------------------------------------
# Collection operations (extracted from ops_write.py)
# ---------------------------------------------------------------------------


def browse_folder(path: str | None = None) -> dict[str, Any]:
    """List the contents of a directory for browsing.

    Returns a dict with:
        - path: the resolved absolute path
        - parent: the parent directory path (or None)
        - items: list of {name, is_dir, size} dicts
    """
    import os

    if not path:
        data_dir = Path("data")
        root = data_dir.resolve()
    else:
        root = Path(path).resolve()

    if not root.exists():
        return {"path": str(root), "parent": None, "items": [], "error": "Path does not exist"}
    if not root.is_dir():
        return {"path": str(root), "parent": str(root.parent), "items": [], "error": "Not a directory"}

    try:
        entries = sorted(os.scandir(root), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        return {"path": str(root), "parent": str(root.parent), "items": [], "error": "Permission denied"}

    items = []
    for entry in entries:
        try:
            stat = entry.stat()
            items.append({
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size": stat.st_size if entry.is_file() else 0,
            })
        except OSError:
            items.append({"name": entry.name, "is_dir": entry.is_dir(), "size": 0})

    return {
        "path": str(root),
        "parent": str(root.parent) if root.parent != root else None,
        "items": items,
    }


def start_collection(data: dict[str, Any], *, bridge: Any) -> dict[str, Any]:
    """Start a new collection/task.

    Delegates to the bridge's start_background_task to actually run the task.
    Returns a dict with task info.
    """
    collection_type = str(data.get("type") or "url").strip().lower()
    task_name = str(data.get("name") or f"{collection_type}-{_timestamp_now()}")
    payload = dict(data)

    start_fn = getattr(bridge, "start_background_task", None)
    if not start_fn:
        raise RuntimeError("Bridge does not support task starting")

    try:
        task_info = start_fn(name=task_name, task_type=collection_type, payload=payload)
        return {"success": True, "task_id": task_info.get("task_id") or task_name, "task": task_info}
    except Exception as exc:
        logger.exception("Failed to start collection task: %s", exc)
        return {"success": False, "error": str(exc)}


def _timestamp_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
