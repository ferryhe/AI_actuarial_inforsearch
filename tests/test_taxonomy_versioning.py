from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ai_actuarial.storage import Storage
from ai_actuarial.utils import taxonomy_hash


def test_taxonomy_hash_order_insensitive() -> None:
    # Both dict key order and keyword list order change, but the hash is stable.
    a = {
        "categories": {"A": ["x", "y"], "B": ["z"]},
        "ai_filter_keywords": ["k1", "k2"],
        "ai_keywords": ["ai"],
    }
    b = {
        "ai_keywords": ["ai"],
        "categories": {"B": ["z"], "A": ["y", "x"]},
        "ai_filter_keywords": ["k2", "k1"],
    }
    assert taxonomy_hash(a) == taxonomy_hash(b)


def test_taxonomy_hash_content_sensitive() -> None:
    a = {"categories": {"A": ["x", "y"]}, "ai_filter_keywords": [], "ai_keywords": []}
    b = {"categories": {"A": ["x", "y", "z"]}, "ai_filter_keywords": [], "ai_keywords": []}
    c = {"categories": {"A": ["x", "y"]}, "ai_filter_keywords": ["k"], "ai_keywords": []}
    assert taxonomy_hash(a) != taxonomy_hash(b)
    assert taxonomy_hash(a) != taxonomy_hash(c)


def test_taxonomy_hash_ignores_stray_top_level_keys() -> None:
    a = {"categories": {"A": ["x"]}, "ai_filter_keywords": [], "ai_keywords": []}
    b = {
        "categories": {"A": ["x"]},
        "ai_filter_keywords": [],
        "ai_keywords": [],
        "some_unrelated_key": {"nested": [1, 2, 3]},
    }
    assert taxonomy_hash(a) == taxonomy_hash(b)


def test_taxonomy_hash_tolerates_none_and_non_dict() -> None:
    assert taxonomy_hash(None) == taxonomy_hash({})
    assert taxonomy_hash(None) == taxonomy_hash({"unrelated": True})


def test_taxonomy_hash_missing_equals_explicit_empty() -> None:
    # Missing taxonomy keys must hash the same as explicit empty defaults, so a
    # YAML edit that drops empty keys does not spuriously flag needs_recategory.
    missing = {}
    explicit_empty = {"categories": {}, "ai_filter_keywords": [], "ai_keywords": []}
    assert taxonomy_hash(missing) == taxonomy_hash(explicit_empty)


def test_taxonomy_state_get_set_roundtrip() -> None:
    # :memory: Storage skips baseline seeding, so we can test the raw upsert.
    storage = Storage(":memory:")
    try:
        assert storage.get_applied_taxonomy_hash() is None
        storage.set_applied_taxonomy_hash("deadbeef")
        assert storage.get_applied_taxonomy_hash() == "deadbeef"
        storage.set_applied_taxonomy_hash("cafebabe")
        assert storage.get_applied_taxonomy_hash() == "cafebabe"
    finally:
        storage.close()


def test_seed_baseline_on_first_run(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "seed.db"))
    try:
        # A fresh file-backed DB establishes applied = current immediately.
        assert storage.get_applied_taxonomy_hash() == storage.current_taxonomy_hash()
        assert storage.taxonomy_needs_recategory() is False
    finally:
        storage.close()


def test_taxonomy_needs_recategory_flags_mismatch(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "needs.db"))
    try:
        assert storage.taxonomy_needs_recategory() is False  # seeded baseline
        storage.set_applied_taxonomy_hash("stale")
        assert storage.taxonomy_needs_recategory() is True
    finally:
        storage.close()


def test_current_taxonomy_hash_tolerates_missing_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CATEGORIES_CONFIG_PATH", str(tmp_path / "missing.yaml"))
    storage = Storage(str(tmp_path / "cfg.db"))
    try:
        result = storage.current_taxonomy_hash()
        assert isinstance(result, str) and len(result) == 64
        assert storage.taxonomy_needs_recategory() is False
    finally:
        storage.close()


def test_migration_v1_to_v2_creates_taxonomy_state(tmp_path: Path) -> None:
    from ai_actuarial.sqlite_schema import apply_schema, schema_status

    db_path = tmp_path / "v1.db"
    storage = Storage(str(db_path))
    try:
        storage._conn.execute("DROP TABLE taxonomy_state")
        storage._conn.execute("PRAGMA user_version=1")
        storage._conn.commit()
    finally:
        storage.close()

    status = schema_status(db_path)
    assert status["state"] == "needs_migration"
    assert status["can_apply"] is True

    applied = apply_schema(db_path)
    assert applied["state"] == "current"
    assert applied["applied_migrations"] == [
        "add_taxonomy_state_v2",
        "add_taxonomy_categories_v3",
        "add_files_content_kind_v4",
        "add_pipeline_state_v5",
        "add_pipeline_fks_v6",
        "add_pipeline_lease_v7",
        "add_chunk_embedding_identity_v8",
        "add_kb_index_contract_v9",
        "add_agentic_ready_manual_operation_state_v10",
        "add_weekly_snapshots_v11",
        "add_weekly_explanations_v12",
        "add_chunk_stats_metadata_indexes_v13",
    ]

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='taxonomy_state'"
        ).fetchone()
    assert row is not None
    with sqlite3.connect(db_path) as conn:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(taxonomy_state)")}
    assert "applied_categories" in columns


def test_get_config_categories_includes_version_fields(tmp_path: Path) -> None:
    from ai_actuarial.api.services.ops_read import get_config_categories

    storage = Storage(str(tmp_path / "cfg.db"))
    try:
        result = get_config_categories(storage=storage)
        assert "current_hash" in result
        assert "applied_hash" in result
        assert "needs_recategory" in result
        assert result["applied_hash"] == result["current_hash"]
        assert result["needs_recategory"] is False
    finally:
        storage.close()


def test_get_config_categories_without_storage_has_no_version_fields() -> None:
    from ai_actuarial.api.services.ops_read import get_config_categories

    result = get_config_categories()
    assert "current_hash" not in result
    assert "applied_hash" not in result
    assert "needs_recategory" not in result
    assert "categories" in result


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q", "--no-cov"]))
