"""Re-categorization task for categories.yaml taxonomy changes.

When ``categories.yaml`` changes (tracked via ``taxonomy_state``), existing
catalog items must be re-classified without re-running the full catalog
pipeline (no re-download, no OCR, no summary/keyword re-generation).

The taxonomy change is decomposed into two disjoint sets:

- ``removed``: categories present on catalog items but no longer in the config.
- ``added``: categories in the config but not yet present on any catalog item.

Apply order is fixed: removals first (freeing the 3-category slot), then adds.

- Removal is deterministic and never calls the LLM.
- Addition pre-filters by keyword match over title/summary/keywords, then asks
  the LLM (from the summary only) to confirm membership before appending.
  Items already at ``MAX_CATEGORIES_PER_ITEM`` are skipped.
- An item left with no visible category after removal falls back to "Other".

The configured taxonomy is always re-read from disk (not ``catalog.CATEGORY_RULES``,
which is frozen at import time) so the diff reflects the latest edit.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from ai_actuarial.catalog_llm import confirm_category_for_summary
from ai_actuarial.shared_runtime import get_categories_config_path
from ai_actuarial.storage import Storage, _split_visible_categories
from ai_actuarial.utils import load_category_config

MAX_CATEGORIES_PER_ITEM = 3
_FALLBACK_CATEGORY = "Other"


def _configured_categories() -> dict[str, list[str]]:
    """Read the current taxonomy from disk (name -> keyword list)."""
    try:
        config = load_category_config(get_categories_config_path())
    except FileNotFoundError:
        config = {}
    categories = config.get("categories") if isinstance(config, dict) else {}
    if not isinstance(categories, dict):
        return {}
    return {
        str(name): [str(term) for term in (terms or [])]
        for name, terms in categories.items()
    }


def _diff_categories(storage: Storage) -> tuple[set[str], set[str]]:
    """Return (removed, added) category sets.

    ``removed`` is diffed against current DB contents (idempotent: once removed,
    the category no longer appears). ``added`` is diffed against the *applied*
    taxonomy recorded in ``taxonomy_state`` (idempotent: it only advances when
    apply seals a new hash), so a partially-failed add run is resumed correctly
    on retry instead of silently dropping the unfinished categories.
    """
    configured = set(_configured_categories().keys())
    existing = set(storage.get_unique_categories())
    applied = set(storage.get_applied_taxonomy_categories() or [])
    removed = {c for c in existing if c not in configured and c != _FALLBACK_CATEGORY}
    added = {c for c in configured if c not in applied}
    return removed, added


def _matches_category_keywords(
    *, title: str, summary: str, keywords: list[str], terms: list[str]
) -> bool:
    """Word-boundary keyword pre-filter mirroring ``catalog.categorize``."""
    hay = " ".join([title or "", summary or "", " ".join(keywords or [])]).lower()
    words = re.findall(r"\b\w+\b", hay)
    word_set = set(words)
    for raw_term in terms:
        term = str(raw_term or "").strip().lower()
        if not term:
            continue
        term_words = term.split()
        if len(term_words) == 1:
            if term in word_set:
                return True
        else:
            pattern = r"\b" + r"\s+".join(re.escape(w) for w in term_words) + r"\b"
            if re.search(pattern, hay):
                return True
    return False


def plan_recategory(storage: Storage) -> dict[str, Any]:
    """Dry-run: report the taxonomy diff and per-category impact without changes."""
    removed, added = _diff_categories(storage)
    configured = _configured_categories()
    items = storage.get_catalog_items_for_recategory()

    removed_impact: dict[str, int] = {}
    for category in sorted(removed):
        removed_impact[category] = sum(
            1
            for item in items
            if category in _split_visible_categories(item["category"])
        )

    added_impact: dict[str, int] = {}
    for category in sorted(added):
        added_impact[category] = sum(
            1
            for item in items
            if _matches_category_keywords(
                title=item["title"],
                summary=item["summary"],
                keywords=item["keywords"],
                terms=configured.get(category, []),
            )
        )

    return {
        "needs_recategory": bool(removed or added),
        "removed_categories": sorted(removed),
        "added_categories": sorted(added),
        "removed_impact": removed_impact,
        "added_impact": added_impact,
        "dry_run": True,
    }


def _remove_category_from_items(
    storage: Storage,
    category: str,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> int:
    """Remove ``category`` from every item that carries it. No LLM calls."""
    items = storage.get_catalog_items_for_recategory()
    affected = 0
    total = len(items)
    for idx, item in enumerate(items):
        cats = _split_visible_categories(item["category"])
        if category not in cats:
            continue
        new_cats = [c for c in cats if c != category]
        new_category = "; ".join(new_cats) if new_cats else _FALLBACK_CATEGORY
        storage.update_catalog_item_category(item["file_url"], new_category)
        affected += 1
        if progress_callback:
            progress_callback(idx + 1, total, f"Removing category '{category}'")
    return affected


def _add_category_to_items(
    storage: Storage,
    category: str,
    terms: list[str],
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> int:
    """Pre-filter by keywords, confirm via LLM from summary, then append."""
    items = storage.get_catalog_items_for_recategory()
    candidates = [
        item
        for item in items
        if _matches_category_keywords(
            title=item["title"],
            summary=item["summary"],
            keywords=item["keywords"],
            terms=terms,
        )
    ]
    added = 0
    total = len(candidates)
    for idx, item in enumerate(candidates):
        cats = _split_visible_categories(item["category"])
        if category in cats:
            continue
        non_other = [c for c in cats if c != _FALLBACK_CATEGORY]
        if len(non_other) >= MAX_CATEGORIES_PER_ITEM:
            continue  # full: skip (removal phase already freed slots where relevant)
        if confirm_category_for_summary(
            summary=item["summary"],
            title=item["title"],
            candidate_category=category,
            category_terms=terms,
            storage=storage,
        ):
            new_cats = non_other + [category]
            storage.update_catalog_item_category(
                item["file_url"], "; ".join(new_cats[:MAX_CATEGORIES_PER_ITEM])
            )
            added += 1
        if progress_callback:
            progress_callback(idx + 1, total, f"Adding category '{category}'")
    return added


def _sync_affected_kbs(storage: Storage, categories: set[str]) -> int:
    """Reconcile KB membership for every KB mapped to an affected category."""
    from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager

    manager = KnowledgeBaseManager(storage)
    affected_kb_ids: set[str] = set()
    for category in categories:
        for kb_id in manager.get_category_kbs(category):
            if kb_id:
                affected_kb_ids.add(str(kb_id))
    for kb_id in sorted(affected_kb_ids):
        manager.sync_category_files(kb_id)
    return len(affected_kb_ids)


def apply_recategory(
    storage: Storage,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Apply the taxonomy change: removals, then adds, KB reconcile, then seal hash."""
    removed, added = _diff_categories(storage)
    configured = _configured_categories()

    removed_counts: dict[str, int] = {}
    for category in sorted(removed):
        removed_counts[category] = _remove_category_from_items(
            storage, category, progress_callback
        )

    added_counts: dict[str, int] = {}
    for category in sorted(added):
        added_counts[category] = _add_category_to_items(
            storage, category, configured.get(category, []), progress_callback
        )

    synced_kbs = _sync_affected_kbs(storage, removed | added)
    storage.set_applied_taxonomy_hash(
        storage.current_taxonomy_hash(),
        storage.current_taxonomy_categories(),
    )

    return {
        "success": True,
        "removed_categories": sorted(removed),
        "added_categories": sorted(added),
        "removed_counts": removed_counts,
        "added_counts": added_counts,
        "synced_kbs": synced_kbs,
        "applied_hash": storage.get_applied_taxonomy_hash(),
    }
