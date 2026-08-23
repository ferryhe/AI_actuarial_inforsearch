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


def _make_storage(env: dict, categories: dict[str, list[str]], name: str = "test.db") -> Storage:
    # Seed the applied taxonomy baseline against the *initial* config, then
    # return an open Storage whose taxonomy_state.applied_categories == initial.
    _write_categories(env["cfg"], categories)
    return Storage(str(env["tmp_path"] / name))


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
    storage = _make_storage(
        env, {"Finance": ["finance"], "Insurance": ["insurance"]}
    )
    try:
        _add_item(storage, "u1", "Finance; Insurance")
        _write_categories(
            env["cfg"], {"Finance": ["finance"], "Technology": ["technology"]}
        )
        removed, added = _diff_categories(storage)
        assert removed == {"Insurance"}
        assert added == {"Technology"}
    finally:
        storage.close()


def test_diff_empty_when_unchanged(env: dict) -> None:
    storage = _make_storage(env, {"Finance": ["finance"], "Insurance": ["insurance"]})
    try:
        _add_item(storage, "u1", "Finance; Insurance")
        removed, added = _diff_categories(storage)
        assert removed == set()
        assert added == set()
    finally:
        storage.close()


def test_plan_is_dry_run(env: dict) -> None:
    storage = _make_storage(env, {"Finance": ["finance"], "Insurance": ["insurance"]})
    try:
        _add_item(storage, "u1", "Finance; Insurance")
        _write_categories(
            env["cfg"], {"Finance": ["finance"], "Technology": ["technology"]}
        )
        plan = plan_recategory(storage)
        assert plan["dry_run"] is True
        assert plan["needs_recategory"] is True
        assert plan["removed_categories"] == ["Insurance"]
        assert plan["added_categories"] == ["Technology"]
        assert plan["removed_impact"]["Insurance"] == 1
        assert plan["added_impact"]["Technology"] == 0  # summary has no tech keyword
        # Nothing changed on disk.
        items = {it["file_url"]: it for it in storage.get_catalog_items_for_recategory()}
        assert items["u1"]["category"] == "Finance; Insurance"
    finally:
        storage.close()


def test_apply_removes_category(env: dict) -> None:
    storage = _make_storage(env, {"Finance": ["finance"], "Insurance": ["insurance"]})
    _patch_sync(env["monkeypatch"])
    try:
        _add_item(storage, "u1", "Finance; Insurance")
        _write_categories(env["cfg"], {"Finance": ["finance"]})
        result = apply_recategory(storage)
        assert result["removed_counts"] == {"Insurance": 1}
        items = {it["file_url"]: it for it in storage.get_catalog_items_for_recategory()}
        assert items["u1"]["category"] == "Finance"
    finally:
        storage.close()


def test_apply_removal_falls_back_to_other(env: dict) -> None:
    storage = _make_storage(env, {"Finance": ["finance"], "Insurance": ["insurance"]})
    _patch_sync(env["monkeypatch"])
    try:
        _add_item(storage, "u1", "Insurance")
        _write_categories(env["cfg"], {"Finance": ["finance"]})
        result = apply_recategory(storage)
        assert result["removed_counts"] == {"Insurance": 1}
        items = {it["file_url"]: it for it in storage.get_catalog_items_for_recategory()}
        assert items["u1"]["category"] == "Other"
    finally:
        storage.close()


def test_apply_adds_category_via_llm(env: dict) -> None:
    storage = _make_storage(env, {"Finance": ["finance"]})
    _patch_sync(env["monkeypatch"])
    _patch_llm(env["monkeypatch"], True)
    try:
        _add_item(
            storage,
            "u1",
            "Finance",
            summary="This document discusses insurance technology trends.",
        )
        _write_categories(
            env["cfg"], {"Finance": ["finance"], "Technology": ["technology"]}
        )
        result = apply_recategory(storage)
        assert result["added_counts"]["Technology"] == 1
        items = {it["file_url"]: it for it in storage.get_catalog_items_for_recategory()}
        assert "Technology" in items["u1"]["category"]
    finally:
        storage.close()


def test_apply_skips_full_item(env: dict) -> None:
    storage = _make_storage(
        env,
        {"Finance": ["finance"], "Insurance": ["insurance"], "AI": ["ai"]},
    )
    _patch_sync(env["monkeypatch"])
    _patch_llm(env["monkeypatch"], True)
    try:
        _add_item(
            storage,
            "u1",
            "Finance; Insurance; AI",
            summary="insurance technology",
        )
        _write_categories(
            env["cfg"],
            {
                "Finance": ["finance"],
                "Insurance": ["insurance"],
                "AI": ["ai"],
                "Technology": ["technology"],
            },
        )
        result = apply_recategory(storage)
        assert result["added_counts"]["Technology"] == 0
        items = {it["file_url"]: it for it in storage.get_catalog_items_for_recategory()}
        assert items["u1"]["category"] == "Finance; Insurance; AI"
    finally:
        storage.close()


def test_apply_replaces_other_with_new_category(env: dict) -> None:
    storage = _make_storage(env, {"Finance": ["finance"]})
    _patch_sync(env["monkeypatch"])
    _patch_llm(env["monkeypatch"], True)
    try:
        _add_item(storage, "u1", "Other", summary="insurance technology trends")
        _write_categories(
            env["cfg"], {"Finance": ["finance"], "Technology": ["technology"]}
        )
        result = apply_recategory(storage)
        assert result["added_counts"]["Technology"] == 1
        items = {it["file_url"]: it for it in storage.get_catalog_items_for_recategory()}
        assert items["u1"]["category"] == "Technology"
    finally:
        storage.close()


def test_apply_seals_applied_hash_and_categories(env: dict) -> None:
    storage = _make_storage(env, {"Finance": ["finance"], "Insurance": ["insurance"]})
    _patch_sync(env["monkeypatch"])
    try:
        _add_item(storage, "u1", "Finance; Insurance")
        _write_categories(env["cfg"], {"Finance": ["finance"]})
        apply_recategory(storage)
        assert storage.get_applied_taxonomy_hash() == storage.current_taxonomy_hash()
        assert storage.get_applied_taxonomy_categories() == ["Finance"]
        assert storage.taxonomy_needs_recategory() is False
    finally:
        storage.close()


def test_apply_resumes_after_partial_llm_failure(env: dict) -> None:
    """C1 regression: a partially-failed add run must resume on retry."""
    storage = _make_storage(env, {"Finance": ["finance"]}, name="resume.db")
    _patch_sync(env["monkeypatch"])
    try:
        _add_item(storage, "u1", "Finance", summary="insurance technology trends")
        _add_item(storage, "u2", "Finance", summary="technology innovation report")
        _write_categories(
            env["cfg"], {"Finance": ["finance"], "Technology": ["technology"]}
        )

        call_count = {"n": 0}

        def flaky_confirm(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return True
            raise RuntimeError("LLM timeout")

        env["monkeypatch"].setattr(
            "ai_actuarial.recategory.confirm_category_for_summary", flaky_confirm
        )

        with pytest.raises(RuntimeError, match="LLM timeout"):
            apply_recategory(storage)

        # Partially applied: u1 has Technology, u2 does not, hash not sealed.
        items = {it["file_url"]: it for it in storage.get_catalog_items_for_recategory()}
        assert "Technology" in items["u1"]["category"]
        assert "Technology" not in items["u2"]["category"]
        assert storage.taxonomy_needs_recategory() is True

        # Retry with a healthy LLM: u2 is completed, hash is sealed.
        _patch_llm(env["monkeypatch"], True)
        result = apply_recategory(storage)
        assert result["added_counts"]["Technology"] == 1
        items = {it["file_url"]: it for it in storage.get_catalog_items_for_recategory()}
        assert "Technology" in items["u2"]["category"]
        assert storage.taxonomy_needs_recategory() is False
    finally:
        storage.close()


def test_v3_backfill_with_pending_change_falls_back_to_db(env: dict) -> None:
    """F1 regression: a v2->v3 upgrade with a pending taxonomy change must not
    seal the new category set as applied, or the pending adds would be dropped."""
    storage = _make_storage(env, {"Finance": ["finance"]}, name="f1.db")
    try:
        _add_item(storage, "u1", "Finance", summary="insurance technology trends")
        # Simulate a v2->v3 upgrade where applied_categories is NULL.
        storage._conn.execute("UPDATE taxonomy_state SET applied_categories = NULL")
        storage._conn.commit()
        # Pending change: add Technology.
        _write_categories(
            env["cfg"], {"Finance": ["finance"], "Technology": ["technology"]}
        )

        # Re-open to trigger the backfill path (hash no longer matches current).
        storage.close()
        storage = Storage(str(env["tmp_path"] / "f1.db"))

        assert storage.get_applied_taxonomy_categories() is None

        removed, added = _diff_categories(storage)
        assert removed == set()
        assert added == {"Technology"}  # falls back to DB contents, not dropped
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


def test_configured_categories_raises_when_file_missing(env: dict) -> None:
    """#4 regression: a missing categories.yaml must fail closed, not empty."""
    from ai_actuarial.recategory import _configured_categories

    env["monkeypatch"].setenv(
        "CATEGORIES_CONFIG_PATH", str(env["tmp_path"] / "missing.yaml")
    )
    with pytest.raises(RuntimeError, match="missing"):
        _configured_categories()


def test_apply_refuses_to_seal_when_taxonomy_changes_midrun(env: dict) -> None:
    """#3 regression: a mid-run taxonomy edit must refuse the seal."""
    storage = _make_storage(env, {"Finance": ["finance"]})
    _patch_sync(env["monkeypatch"])
    try:
        _add_item(storage, "u1", "Finance", summary="insurance technology trends")
        _write_categories(
            env["cfg"], {"Finance": ["finance"], "Technology": ["technology"]}
        )

        def mutating_confirm(**kwargs):
            _write_categories(
                env["cfg"],
                {
                    "Finance": ["finance"],
                    "Technology": ["technology"],
                    "Health": ["health"],
                },
            )
            return True

        env["monkeypatch"].setattr(
            "ai_actuarial.recategory.confirm_category_for_summary",
            mutating_confirm,
        )

        with pytest.raises(RuntimeError, match="changed during re-categorization"):
            apply_recategory(storage)

        assert storage.taxonomy_needs_recategory() is True
    finally:
        storage.close()


def test_apply_stops_without_sealing(env: dict) -> None:
    """#6 regression: a stop request interrupts apply without sealing."""
    storage = _make_storage(env, {"Finance": ["finance"], "Insurance": ["insurance"]})
    _patch_sync(env["monkeypatch"])
    try:
        _add_item(storage, "u1", "Finance; Insurance")
        _add_item(storage, "u2", "Finance; Insurance")
        _write_categories(env["cfg"], {"Finance": ["finance"]})

        calls = {"n": 0}

        def stop_after_one():
            calls["n"] += 1
            return calls["n"] > 1

        result = apply_recategory(storage, stop_check=stop_after_one)
        assert result["stopped"] is True
        assert result["success"] is False
        assert storage.taxonomy_needs_recategory() is True

        # Partial: only u1's Insurance was removed before the stop.
        items = {
            it["file_url"]: it for it in storage.get_catalog_items_for_recategory()
        }
        assert items["u1"]["category"] == "Finance"
        assert items["u2"]["category"] == "Finance; Insurance"
    finally:
        storage.close()


def test_recategory_rejects_scoped_request(env: dict) -> None:
    """#7 regression: scoped recategory requests are rejected fail-closed."""
    storage = _make_storage(env, {"Finance": ["finance"]})
    try:
        from ai_actuarial.task_runtime import NativeTaskRuntime

        runtime = NativeTaskRuntime()
        with pytest.raises(RuntimeError, match="scoping"):
            runtime._run_recategory(
                "task-scope", storage, {"mode": "apply", "category": "Finance"}
            )
    finally:
        storage.close()


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q", "--no-cov"]))
