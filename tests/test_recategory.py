from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ai_actuarial.recategory import (
    _diff_categories,
    _matches_category_keywords,
    apply_recategory,
    plan_recategory,
)
from ai_actuarial.storage import Storage


def _write_categories(path: Path, categories: dict[str, list[str]]) -> None:
    data = {
        "categories": categories,
        "ai_filter_keywords": [],
        "ai_keywords": [],
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _add_item(
    storage: Storage,
    url: str,
    category: str,
    *,
    summary: str = "",
    keywords: list[str] | None = None,
) -> None:
    storage.upsert_catalog_item(
        {
            "url": url,
            "sha256": f"sha-{url}",
            "keywords": keywords or [],
            "summary": summary,
            "category": category,
        }
    )


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    cfg = tmp_path / "categories.yaml"
    monkeypatch.setenv("CATEGORIES_CONFIG_PATH", str(cfg))
    return {"cfg": cfg, "tmp_path": tmp_path, "monkeypatch": monkeypatch}


def _patch_llm(monkeypatch: pytest.MonkeyPatch, value: bool) -> None:
    monkeypatch.setattr(
        "ai_actuarial.recategory.confirm_category_for_summary",
        lambda **kwargs: value,
    )


def _patch_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "ai_actuarial.recategory._sync_affected_kbs",
        lambda storage, categories: 0,
    )


def test_diff_removed_and_added(env: dict) -> None:
    _write_categories(
        env["cfg"],
        {"Finance": ["finance"], "Insurance": ["insurance"], "Technology": ["technology"]},
    )
    storage = Storage(":memory:")
    try:
        _add_item(storage, "u1", "Finance; Healthcare")
        _add_item(storage, "u2", "Insurance")
        _add_item(storage, "u3", "Other")
        removed, added = _diff_categories(storage)
        assert removed == {"Healthcare"}
        assert added == {"Technology"}
    finally:
        storage.close()


def test_diff_empty_when_unchanged(env: dict) -> None:
    _write_categories(
        env["cfg"], {"Finance": ["finance"], "Insurance": ["insurance"]}
    )
    storage = Storage(":memory:")
    try:
        _add_item(storage, "u1", "Finance; Insurance")
        removed, added = _diff_categories(storage)
        assert removed == set()
        assert added == set()
    finally:
        storage.close()


def test_plan_is_dry_run(env: dict) -> None:
    _write_categories(
        env["cfg"],
        {"Finance": ["finance"], "Technology": ["technology"]},
    )
    storage = Storage(":memory:")
    try:
        _add_item(storage, "u1", "Finance; Healthcare")
        _add_item(storage, "u2", "Finance", summary="insurance technology trends")
        plan = plan_recategory(storage)
        assert plan["dry_run"] is True
        assert plan["needs_recategory"] is True
        assert plan["removed_categories"] == ["Healthcare"]
        assert plan["added_categories"] == ["Technology"]
        assert plan["removed_impact"]["Healthcare"] == 1
        assert plan["added_impact"]["Technology"] == 1
        # Nothing changed on disk.
        items = storage.get_catalog_items_for_recategory()
        assert any("Healthcare" in it["category"] for it in items)
    finally:
        storage.close()


def test_apply_removes_category(env: dict) -> None:
    _write_categories(env["cfg"], {"Finance": ["finance"]})
    _patch_sync(env["monkeypatch"])
    storage = Storage(":memory:")
    try:
        _add_item(storage, "u1", "Finance; Healthcare")
        result = apply_recategory(storage)
        assert result["removed_counts"] == {"Healthcare": 1}
        items = {it["file_url"]: it for it in storage.get_catalog_items_for_recategory()}
        assert items["u1"]["category"] == "Finance"
    finally:
        storage.close()


def test_apply_removal_falls_back_to_other(env: dict) -> None:
    _write_categories(env["cfg"], {"Finance": ["finance"]})
    _patch_sync(env["monkeypatch"])
    storage = Storage(":memory:")
    try:
        _add_item(storage, "u1", "Healthcare")
        result = apply_recategory(storage)
        assert result["removed_counts"] == {"Healthcare": 1}
        items = {it["file_url"]: it for it in storage.get_catalog_items_for_recategory()}
        assert items["u1"]["category"] == "Other"
    finally:
        storage.close()


def test_apply_adds_category_via_llm(env: dict) -> None:
    _write_categories(
        env["cfg"], {"Finance": ["finance"], "Technology": ["technology"]}
    )
    _patch_sync(env["monkeypatch"])
    _patch_llm(env["monkeypatch"], True)
    storage = Storage(":memory:")
    try:
        _add_item(
            storage,
            "u1",
            "Finance",
            summary="This document discusses insurance technology trends.",
        )
        result = apply_recategory(storage)
        assert result["added_counts"] == {"Technology": 1}
        items = {it["file_url"]: it for it in storage.get_catalog_items_for_recategory()}
        assert "Technology" in items["u1"]["category"]
    finally:
        storage.close()


def test_apply_skips_full_item(env: dict) -> None:
    _write_categories(
        env["cfg"],
        {
            "Finance": ["finance"],
            "Insurance": ["insurance"],
            "AI": ["ai"],
            "Technology": ["technology"],
        },
    )
    _patch_sync(env["monkeypatch"])
    _patch_llm(env["monkeypatch"], True)
    storage = Storage(":memory:")
    try:
        _add_item(
            storage,
            "u1",
            "Finance; Insurance; AI",
            summary="insurance technology",
        )
        result = apply_recategory(storage)
        # Item already has 3 categories; add is skipped even though LLM says yes.
        assert result["added_counts"] == {"Technology": 0}
        items = {it["file_url"]: it for it in storage.get_catalog_items_for_recategory()}
        assert items["u1"]["category"] == "Finance; Insurance; AI"
    finally:
        storage.close()


def test_apply_replaces_other_with_new_category(env: dict) -> None:
    _write_categories(
        env["cfg"], {"Finance": ["finance"], "Technology": ["technology"]}
    )
    _patch_sync(env["monkeypatch"])
    _patch_llm(env["monkeypatch"], True)
    storage = Storage(":memory:")
    try:
        _add_item(storage, "u1", "Other", summary="insurance technology trends")
        result = apply_recategory(storage)
        assert result["added_counts"]["Technology"] == 1
        items = {it["file_url"]: it for it in storage.get_catalog_items_for_recategory()}
        assert items["u1"]["category"] == "Technology"
    finally:
        storage.close()


def test_apply_seals_applied_hash(env: dict) -> None:
    _write_categories(env["cfg"], {"Finance": ["finance"]})
    _patch_sync(env["monkeypatch"])
    storage = Storage(":memory:")
    try:
        _add_item(storage, "u1", "Finance; Healthcare")
        apply_recategory(storage)
        assert storage.get_applied_taxonomy_hash() == storage.current_taxonomy_hash()
        assert storage.taxonomy_needs_recategory() is False
    finally:
        storage.close()


def test_matches_category_keywords_word_boundary() -> None:
    assert _matches_category_keywords(
        title="", summary="We cover insurance risk.", keywords=[], terms=["insurance"]
    )
    # "assurance" must not match "insurance" (word boundary).
    assert not _matches_category_keywords(
        title="", summary="We cover assurance.", keywords=[], terms=["insurance"]
    )
    # Multi-word term must match the full phrase.
    assert _matches_category_keywords(
        title="",
        summary="machine learning is used here.",
        keywords=[],
        terms=["machine learning"],
    )


def test_catalog_blocked_when_taxonomy_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "sites.yaml"
    db_path = tmp_path / "block.db"
    config_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  db: {db_path.as_posix()}",
                f"  download_dir: {(tmp_path / 'files').as_posix()}",
                f"  updates_dir: {(tmp_path / 'updates').as_posix()}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    cfg = tmp_path / "categories.yaml"
    monkeypatch.setenv("CATEGORIES_CONFIG_PATH", str(cfg))
    _write_categories(cfg, {"Finance": ["finance"]})

    # Seed the baseline applied hash, then edit the taxonomy.
    seed = Storage(str(db_path))
    seed.close()
    _write_categories(cfg, {"Finance": ["finance"], "Technology": ["technology"]})

    from ai_actuarial.task_runtime import NativeTaskRuntime

    runtime = NativeTaskRuntime()
    with pytest.raises(RuntimeError, match="recategory"):
        runtime._run_collection("task-block", "catalog", {})


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q", "--no-cov"]))
