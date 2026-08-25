"""Per-stage pipeline configuration model (#179).

Encodes the canonical stage taxonomy, each stage's config source + option keys
(reusing each module's existing options — no new schema), and the three-class
mutability model (mutable / immutable / versioned).

This is the config layer the state machine records per stage (v3 §1), plus the
resolution of a task's ``stage_options`` overrides (v3 §2).
"""

from __future__ import annotations

import copy
from typing import Any

# --- Mutability classes (v3 §1.1) --------------------------------------------
# 可变 (mutable):    old output stays valid; a change only affects future runs.
# 不可变 (immutable): old output is incompatible; a change requires full rebuild.
# 版本化 (versioned): migrate via expand/backfill/switch/contract, never in-place.
MUTABLE = "mutable"
IMMUTABLE = "immutable"
VERSIONED = "versioned"

# Canonical stage names, in pipeline execution order.
PIPELINE_STAGES: tuple[str, ...] = (
    "acquisition",
    "manifest_ingestion",
    "markdown_conversion",
    "catalog",
    "kb_reconciliation",
    "chunk_generation",
    "rag_indexing",
    "ready_data_publish",
)

# --- Per-stage config (v3 §1.2) ----------------------------------------------
# source       where the stage's config lives (existing module/file/DB).
# option_keys  the option keys the state machine records for the stage.
# mutability   the stage's config mutability class (§1.1).
_STAGE_CONFIG: dict[str, dict[str, Any]] = {
    "acquisition": {
        "source": "config/sites.yaml (crawler.SiteConfig)",
        "option_keys": (
            "max_pages",
            "max_depth",
            "keywords",
            "acquisition_tools",
            "content_selector",
            "allow_url_patterns",
            "queries",
            "check_database",
        ),
        "mutability": MUTABLE,
    },
    "manifest_ingestion": {
        "source": "manifest schema_version + idempotency keys",
        "option_keys": ("schema_version",),
        "mutability": VERSIONED,
    },
    "markdown_conversion": {
        "source": "config/markdown_conversion.yaml + ai_config.ocr",
        "option_keys": ("default_tool", "tools", "ocr"),
        "mutability": MUTABLE,
    },
    "catalog": {
        # The *model* (provider/model/temperature) is mutable; the *taxonomy*
        # (category set, CATEGORY_RULES) is versioned via #178's mechanism.
        "source": "ai_config.catalog + CATEGORY_RULES",
        "option_keys": ("provider", "model", "temperature"),
        "mutability": MUTABLE,
    },
    "kb_reconciliation": {
        "source": "kb_mode + rag_kb_category_mappings (DB)",
        "option_keys": ("kb_mode", "rag_kb_category_mappings"),
        "mutability": MUTABLE,
    },
    "chunk_generation": {
        "source": "rag_config",
        "option_keys": (
            "chunk_strategy",
            "max_chunk_tokens",
            "min_chunk_tokens",
            "preserve_headers",
            "preserve_citations",
            "include_hierarchy",
        ),
        "mutability": IMMUTABLE,
    },
    "rag_indexing": {
        "source": "ai_config.embeddings + rag_config.index_type",
        "option_keys": ("provider", "model", "batch_size", "similarity_threshold", "index_type"),
        "mutability": IMMUTABLE,
    },
    "ready_data_publish": {
        "source": "staging / active·previous slot / publication pointer (DB)",
        "option_keys": ("staging", "active_publication_id", "previous_publication_id"),
        "mutability": MUTABLE,
    },
}

# Public views.
STAGE_CONFIG: dict[str, dict[str, Any]] = _STAGE_CONFIG

STAGE_MUTABILITY: dict[str, str] = {
    stage: cfg["mutability"] for stage, cfg in _STAGE_CONFIG.items()
}

STAGE_CONFIG_SOURCE: dict[str, str] = {
    stage: cfg["source"] for stage, cfg in _STAGE_CONFIG.items()
}

STAGE_OPTION_KEYS: dict[str, tuple[str, ...]] = {
    stage: tuple(cfg["option_keys"]) for stage, cfg in _STAGE_CONFIG.items()
}

IMMUTABLE_STAGES = frozenset(
    stage for stage, mutability in STAGE_MUTABILITY.items() if mutability == IMMUTABLE
)
VERSIONED_STAGES = frozenset(
    stage for stage, mutability in STAGE_MUTABILITY.items() if mutability == VERSIONED
)
MUTABLE_STAGES = frozenset(
    stage for stage, mutability in STAGE_MUTABILITY.items() if mutability == MUTABLE
)


def _require_known_stage(stage: str) -> None:
    if stage not in STAGE_MUTABILITY:
        raise ValueError(
            f"unknown pipeline stage: {stage!r} (valid: {', '.join(PIPELINE_STAGES)})"
        )


def stage_mutability(stage: str) -> str:
    """Return the mutability class for ``stage`` (raises for an unknown stage)."""
    _require_known_stage(stage)
    return STAGE_MUTABILITY[stage]


def stage_config_source(stage: str) -> str:
    """Return the config source description for ``stage``."""
    _require_known_stage(stage)
    return STAGE_CONFIG_SOURCE[stage]


def stage_option_keys(stage: str) -> tuple[str, ...]:
    """Return the option keys the state machine records for ``stage``."""
    _require_known_stage(stage)
    return STAGE_OPTION_KEYS[stage]


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` onto ``base``.

    Nested dicts are merged recursively; scalar values are replaced. Neither
    input is mutated, and nested dict/list values are deep-copied so the result
    does not alias the inputs.
    """
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def normalize_stage_options(stage_options: Any) -> dict[str, dict[str, Any]]:
    """Validate and normalize a task's ``stage_options`` payload.

    Returns ``{stage_name: {option_key: value}}`` for known stages. Raises
    ``TypeError`` for a non-dict payload or a non-dict stage entry, and
    ``ValueError`` for an unknown stage name. Unknown option keys within a
    known stage are passed through unchanged (each stage module tolerates
    unknown keys).
    """
    if stage_options is None:
        return {}
    if not isinstance(stage_options, dict):
        raise TypeError("stage_options must be a mapping of stage name -> options")
    normalized: dict[str, dict[str, Any]] = {}
    for stage, options in stage_options.items():
        stage_name = str(stage)
        _require_known_stage(stage_name)
        if not isinstance(options, dict):
            raise TypeError(f"stage_options[{stage_name!r}] must be a mapping")
        normalized[stage_name] = dict(options)
    return normalized


def resolve_effective_options(
    stage: str,
    stage_options: dict[str, dict[str, Any]] | None,
    defaults: dict[str, Any],
) -> dict[str, Any]:
    """Return the effective options for ``stage``.

    ``defaults`` are deep-merged with the stage's override
    (``stage_options[stage]``), if any. The result is a fresh dict. Raises
    ``ValueError`` for an unknown stage.
    """
    _require_known_stage(stage)
    overrides = (stage_options or {}).get(stage) or {}
    return deep_merge(dict(defaults), dict(overrides))
