from __future__ import annotations

import pytest

from ai_actuarial.pipeline_config import (
    IMMUTABLE,
    IMMUTABLE_STAGES,
    MUTABLE,
    MUTABLE_STAGES,
    PIPELINE_STAGES,
    VERSIONED,
    VERSIONED_STAGES,
    deep_merge,
    normalize_stage_options,
    resolve_effective_options,
    stage_mutability,
)


def test_pipeline_stages_are_ordered() -> None:
    assert PIPELINE_STAGES == (
        "acquisition",
        "manifest_ingestion",
        "markdown_conversion",
        "catalog",
        "kb_reconciliation",
        "chunk_generation",
        "rag_indexing",
        "ready_data_publish",
    )


def test_mutability_classification() -> None:
    assert stage_mutability("acquisition") == MUTABLE
    assert stage_mutability("manifest_ingestion") == VERSIONED
    assert stage_mutability("markdown_conversion") == MUTABLE
    assert stage_mutability("catalog") == MUTABLE
    assert stage_mutability("kb_reconciliation") == MUTABLE
    assert stage_mutability("chunk_generation") == IMMUTABLE
    assert stage_mutability("rag_indexing") == IMMUTABLE
    assert stage_mutability("ready_data_publish") == MUTABLE


def test_immutable_and_versioned_frozensets() -> None:
    assert IMMUTABLE_STAGES == {"chunk_generation", "rag_indexing"}
    assert VERSIONED_STAGES == {"manifest_ingestion"}
    assert MUTABLE_STAGES == {
        "acquisition",
        "markdown_conversion",
        "catalog",
        "kb_reconciliation",
        "ready_data_publish",
    }


def test_stage_mutability_rejects_unknown_stage() -> None:
    with pytest.raises(ValueError, match="unknown pipeline stage"):
        stage_mutability("not_a_stage")


def test_deep_merge_nested_and_scalar() -> None:
    base = {"a": 1, "nested": {"x": 1, "y": 2}}
    override = {"b": 2, "nested": {"y": 3}}
    assert deep_merge(base, override) == {"a": 1, "b": 2, "nested": {"x": 1, "y": 3}}
    # inputs unchanged
    assert base == {"a": 1, "nested": {"x": 1, "y": 2}}


def test_normalize_stage_options_none_and_empty() -> None:
    assert normalize_stage_options(None) == {}
    assert normalize_stage_options({}) == {}


def test_normalize_stage_options_passes_through() -> None:
    raw = {"catalog": {"model": "gpt-5.4-mini"}, "chunk_generation": {"max_chunk_tokens": 1000}}
    assert normalize_stage_options(raw) == raw


def test_normalize_stage_options_tolerates_unknown_option_keys() -> None:
    raw = {"catalog": {"model": "gpt-5.4-mini", "some_future_key": 1}}
    assert normalize_stage_options(raw) == raw


def test_normalize_stage_options_rejects_non_dict_payload() -> None:
    with pytest.raises(TypeError, match="mapping"):
        normalize_stage_options("not-a-dict")


def test_normalize_stage_options_rejects_unknown_stage() -> None:
    with pytest.raises(ValueError, match="unknown pipeline stage"):
        normalize_stage_options({"bogus_stage": {}})


def test_normalize_stage_options_rejects_non_dict_entry() -> None:
    with pytest.raises(TypeError, match="must be a mapping"):
        normalize_stage_options({"catalog": "not-a-dict"})


def test_resolve_effective_options_applies_override() -> None:
    defaults = {"model": "gpt-4o-mini", "temperature": 0.3}
    stage_options = {"catalog": {"model": "gpt-5.4-mini"}}
    effective = resolve_effective_options("catalog", stage_options, defaults)
    assert effective == {"model": "gpt-5.4-mini", "temperature": 0.3}


def test_resolve_effective_options_without_override_returns_defaults() -> None:
    defaults = {"model": "gpt-4o-mini", "temperature": 0.3}
    effective = resolve_effective_options("catalog", {}, defaults)
    assert effective == defaults
    assert effective is not defaults  # fresh dict
