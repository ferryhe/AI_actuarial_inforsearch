from __future__ import annotations

import pytest

from ai_actuarial.pipeline_config import (
    IMMUTABLE,
    IMMUTABLE_STAGES,
    MUTABLE,
    MUTABLE_STAGES,
    PIPELINE_STAGES,
    STAGE_CONFIG,
    STAGE_OPTION_KEYS,
    VERSIONED,
    VERSIONED_STAGES,
    deep_merge,
    normalize_stage_options,
    resolve_effective_options,
    stage_config_source,
    stage_mutability,
    stage_option_keys,
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


def test_deep_merge_returns_fresh_nested_values() -> None:
    base = {"nested": {"x": 1}, "items": [1, 2]}
    override = {"extra": {"y": 2}}
    merged = deep_merge(base, override)

    merged["nested"]["x"] = 99
    merged["items"].append(3)
    merged["extra"]["y"] = 42

    assert base == {"nested": {"x": 1}, "items": [1, 2]}
    assert override == {"extra": {"y": 2}}


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


def test_resolve_effective_options_rejects_unknown_stage() -> None:
    with pytest.raises(ValueError, match="unknown pipeline stage"):
        resolve_effective_options("bogus", {}, {"a": 1})


def test_stage_config_covers_all_stages() -> None:
    assert set(STAGE_CONFIG.keys()) == set(PIPELINE_STAGES)
    for stage in PIPELINE_STAGES:
        cfg = STAGE_CONFIG[stage]
        assert {"source", "option_keys", "mutability"} <= set(cfg)
        assert isinstance(cfg["source"], str) and cfg["source"]
        assert isinstance(cfg["option_keys"], tuple) and cfg["option_keys"]


def test_mutability_is_derived_from_config() -> None:
    for stage in PIPELINE_STAGES:
        assert stage_mutability(stage) == STAGE_CONFIG[stage]["mutability"]
        assert stage_option_keys(stage) == STAGE_CONFIG[stage]["option_keys"]
        assert stage_config_source(stage) == STAGE_CONFIG[stage]["source"]


def test_immutable_stage_option_keys() -> None:
    assert STAGE_OPTION_KEYS["chunk_generation"] == (
        "chunk_strategy",
        "max_chunk_tokens",
        "min_chunk_tokens",
        "preserve_headers",
        "preserve_citations",
        "include_hierarchy",
    )
    assert STAGE_OPTION_KEYS["rag_indexing"] == (
        "provider",
        "model",
        "batch_size",
        "similarity_threshold",
        "index_type",
    )


def test_mutable_and_versioned_option_keys() -> None:
    assert STAGE_OPTION_KEYS["acquisition"] == (
        "max_pages",
        "max_depth",
        "keywords",
        "acquisition_tools",
        "content_selector",
        "allow_url_patterns",
        "queries",
        "check_database",
    )
    assert STAGE_OPTION_KEYS["catalog"] == ("provider", "model", "temperature")
    assert STAGE_OPTION_KEYS["markdown_conversion"] == ("default_tool", "tools", "ocr")
    assert STAGE_OPTION_KEYS["manifest_ingestion"] == ("schema_version",)
    assert STAGE_OPTION_KEYS["kb_reconciliation"] == ("kb_mode", "rag_kb_category_mappings")


def test_stage_helpers_reject_unknown_stage() -> None:
    with pytest.raises(ValueError, match="unknown pipeline stage"):
        stage_config_source("bogus")
    with pytest.raises(ValueError, match="unknown pipeline stage"):
        stage_option_keys("bogus")
