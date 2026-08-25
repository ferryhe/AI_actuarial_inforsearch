"""Per-stage pipeline configuration model (#179).

Defines the canonical stage taxonomy, the mutability class of each stage's
configuration (mutable / immutable / versioned), and the resolution of a task's
``stage_options`` overrides onto each module's existing defaults.

This is the config layer that the state machine records per stage. It reuses
each module's existing option keys and does NOT introduce a new schema.
"""

from __future__ import annotations

from typing import Any

# --- Mutability classes -------------------------------------------------------
# 可变 (mutable):     old output stays valid; a change only affects future runs.
# 不可变 (immutable):  old output is incompatible; a change requires full rebuild.
# 版本化 (versioned):  migrate via expand/backfill/switch/contract, never in-place.

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

# Mutability class per stage. ``catalog``'s *model* choice is mutable while its
# *taxonomy* (category set) is versioned via ``CATEGORY_RULES`` (#178); the
# stage is classified mutable here, with taxonomy versioning handled separately.
STAGE_MUTABILITY: dict[str, str] = {
    "acquisition": MUTABLE,
    "manifest_ingestion": VERSIONED,
    "markdown_conversion": MUTABLE,
    "catalog": MUTABLE,
    "kb_reconciliation": MUTABLE,
    "chunk_generation": IMMUTABLE,
    "rag_indexing": IMMUTABLE,
    "ready_data_publish": MUTABLE,
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


def stage_mutability(stage: str) -> str:
    """Return the mutability class for ``stage`` (raises for an unknown stage)."""
    if stage not in STAGE_MUTABILITY:
        raise ValueError(
            f"unknown pipeline stage: {stage!r} (valid: {', '.join(PIPELINE_STAGES)})"
        )
    return STAGE_MUTABILITY[stage]


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` onto ``base``.

    Nested dicts are merged recursively; scalar values are replaced. Neither
    input is mutated.
    """
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
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
        if stage_name not in STAGE_MUTABILITY:
            raise ValueError(
                f"unknown pipeline stage {stage_name!r} in stage_options "
                f"(valid: {', '.join(PIPELINE_STAGES)})"
            )
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
    (``stage_options[stage]``), if any. The result is a fresh dict.
    """
    overrides = (stage_options or {}).get(stage) or {}
    return deep_merge(dict(defaults), dict(overrides))
