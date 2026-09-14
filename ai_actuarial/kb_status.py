"""Public KB status classification.

Serving state, maintenance state, and the re-embedding requirement are
deliberately separate.  In particular, ordinary content or binding work must
not make an already-serving compatible index unavailable to Ask AI.
"""

from __future__ import annotations

from typing import Any, Mapping

KB_STATUS_REASONS = frozenset(
    {
        "embedding_incompatible",
        "content_dirty",
        "binding_dirty",
        "index_missing",
        "index_building",
        "publish_failed",
        "serving_disabled",
        "healthy",
    }
)


def classify_kb_status(
    *,
    composition: Mapping[str, Any],
    embedding_compatible: bool,
    serving_enabled: bool | None = None,
    publish_failed: bool = False,
) -> dict[str, Any]:
    """Classify the public KB state without conflating maintenance with serving."""
    latest_index = composition.get("latest_index") or {}
    has_index = bool(composition.get("has_index"))
    index_status = str(latest_index.get("status") or "").strip().lower()
    building = index_status in {"pending", "queued", "running", "building", "indexing"}
    binding_dirty = bool(composition.get("outdated_binding_count")) or bool(
        composition.get("new_chunk_versions_available")
    )
    content_dirty = bool(composition.get("pending_file_count")) or bool(
        composition.get("dirty_after_index")
    )
    if bool(composition.get("needs_reindex")) and not (binding_dirty or content_dirty):
        # Legacy composition payloads do not always expose the component counts.
        content_dirty = True

    if not embedding_compatible:
        reason = "embedding_incompatible"
    elif serving_enabled is False:
        reason = "serving_disabled"
    elif publish_failed:
        reason = "publish_failed"
    elif not has_index:
        reason = "index_missing"
    elif building:
        reason = "index_building"
    elif binding_dirty:
        reason = "binding_dirty"
    elif content_dirty:
        reason = "content_dirty"
    else:
        reason = "healthy"

    # A usable index may continue serving while follow-up content/binding work
    # is pending.  Only an incompatible embedding space is a re-embed gate.
    serving = bool(
        has_index and not building and embedding_compatible and serving_enabled is not False
    )
    if reason == "embedding_incompatible":
        availability = "needs_reindex"
    elif reason in {"index_missing", "index_building"}:
        availability = "building"
    else:
        availability = "ready" if serving else "unavailable"
    return {
        "reason": reason,
        "needs_reembed": reason == "embedding_incompatible",
        "serving": serving,
        "availability": availability,
    }
