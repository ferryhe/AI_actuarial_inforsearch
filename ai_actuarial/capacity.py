"""Root-disk capacity gate for write-heavy pipeline operations.

Guards recategory, full indexing, and bulk pipeline runs against the root
filesystem (where the SQLite database and RAG index live) crossing the
configured usage threshold. Original artifacts land on ``/data``, so this
gate watches the hot root disk only.
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from typing import Any


class CapacityBlockedError(RuntimeError):
    """Raised when a write-heavy operation is blocked by low root disk space."""

    def __init__(
        self,
        *,
        operation: str,
        path: str,
        used_percent: float,
        threshold_percent: float,
        free_bytes: int,
    ) -> None:
        self.operation = operation
        self.path = path
        self.used_percent = used_percent
        self.threshold_percent = threshold_percent
        self.free_bytes = free_bytes
        free_gb = free_bytes / (1024**3)
        super().__init__(
            f"[CAPACITY_BLOCKED] {path} is {used_percent:.1f}% used, over the "
            f"{threshold_percent:.0f}% threshold ({free_gb:.1f} GB free); blocked "
            f"'{operation}'. Free up root disk space or move cold data to /data "
            f"or object storage, then retry."
        )


def capacity_status(
    path: str = "/",
    threshold_percent: float = 80.0,
    disk_usage: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Report capacity for ``path``. ``disk_usage`` is a test seam over
    ``shutil.disk_usage`` in ``(total, used, free)`` order."""
    if not 0 < threshold_percent <= 100:
        raise ValueError("threshold_percent must be greater than 0 and at most 100")
    total, used, free = (
        tuple(disk_usage) if disk_usage is not None else tuple(shutil.disk_usage(path))
    )
    total, used, free = int(total), int(used), int(free)
    if total <= 0:
        raise ValueError("disk usage total must be positive")
    used_percent = round((used / total) * 100, 2)
    return {
        "path": path,
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "used_percent": used_percent,
        "threshold_percent": float(threshold_percent),
        "blocked": used_percent >= threshold_percent,
    }


def ensure_capacity(
    path: str = "/",
    threshold_percent: float = 80.0,
    operation: str = "",
    disk_usage: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Raise :class:`CapacityBlockedError` when ``path`` is at or over the
    threshold, otherwise return the capacity status."""
    status = capacity_status(
        path, threshold_percent=threshold_percent, disk_usage=disk_usage
    )
    if status["blocked"]:
        raise CapacityBlockedError(
            operation=operation,
            path=path,
            used_percent=status["used_percent"],
            threshold_percent=threshold_percent,
            free_bytes=status["free_bytes"],
        )
    return status
