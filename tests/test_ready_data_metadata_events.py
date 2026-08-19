from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import ai_actuarial.catalog_incremental as catalog_incremental
from ai_actuarial.api.services.files_write import update_file_record
from ai_actuarial.api.services.ready_data_automation import (
    run_ready_data_automation_once,
)
from ai_actuarial.catalog import CatalogItem
from ai_actuarial.collectors import CollectionConfig, WebPageCollector
from ai_actuarial.rag.indexing import IndexingPipeline
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.storage import Storage


def _create_kb(storage: Storage, kb_id: str, *, profile: str = "general") -> None:
    KnowledgeBaseManager(storage).create_kb(
        kb_id=kb_id,
        name=f"Metadata {kb_id}",
        kb_mode="manual",
        manifest_profile=profile,
    )


def _catalog_item(file_url: str, *, suffix: str = "") -> dict[str, Any]:
    return {
        "url": file_url,
        "sha256": f"sha-{Path(file_url).name}",
        "keywords": [f"keyword{suffix}"],
        "summary": f"Summary{suffix}",
        "category": f"Category{suffix}",
    }


def _create_file(
    storage: Storage,
    tmp_path: Path,
    file_url: str,
    *,
    status: str = "ok",
) -> None:
    name = Path(file_url).name
    storage.insert_file(
        url=file_url,
        sha256=f"sha-{name}",
        title=f"Title {name}",
        source_site="example.com",
        source_page_url="https://example.com",
        original_filename=name,
        local_path=str(tmp_path / name),
        bytes=100,
        content_type="application/pdf",
        last_modified="Wed, 19 Aug 2026 00:00:00 GMT",
        etag="etag-before",
        published_time="2026-08-01",
    )
    storage.upsert_catalog_item(
        _catalog_item(file_url),
        pipeline_version="catalog-v1",
        status=status,
        error="seed error" if status != "ok" else None,
    )


def _add_membership(storage: Storage, *, kb_id: str, file_url: str) -> None:
    storage._conn.execute(
        "INSERT INTO rag_kb_files(kb_id, file_url, added_at) VALUES (?, ?, ?)",
        (kb_id, file_url, "2026-08-19T00:00:00+00:00"),
    )
    storage._conn.commit()


def _seed_member(
    tmp_path: Path,
    *,
    name: str,
    status: str = "ok",
    kb_id: str | None = None,
) -> tuple[Storage, str, str]:
    storage = Storage(str(tmp_path / f"{name}.db"))
    resolved_kb_id = kb_id or f"kb-{name}"
    file_url = f"https://example.com/{name}.pdf"
    _create_kb(storage, resolved_kb_id)
    _create_file(storage, tmp_path, file_url, status=status)
    _add_membership(storage, kb_id=resolved_kb_id, file_url=file_url)
    return storage, resolved_kb_id, file_url


def _state(storage: Storage, kb_id: str, profile: str = "general") -> dict[str, Any]:
    return storage.get_agentic_ready_source_state(kb_id=kb_id, profile=profile)


def _upsert_file_metadata(storage: Storage, file_url: str, **changes: Any) -> None:
    row = storage.get_file_by_url(file_url)
    assert row is not None
    values = {
        "url": file_url,
        "sha256": row["sha256"],
        "title": row["title"],
        "source_site": row["source_site"],
        "source_page_url": row["source_page_url"],
        "original_filename": row["original_filename"],
        "local_path": row["local_path"],
        "bytes_size": row["bytes"],
        "content_type": row["content_type"],
        "last_modified": row["last_modified"],
        "etag": row["etag"],
        "published_time": row["published_time"],
    }
    values.update(changes)
    storage.upsert_file(**values)


def _assert_single_event(
    storage: Storage,
    kb_id: str,
    *,
    reason: str = "metadata_updated",
    severity: str = "soft_stale",
) -> None:
    state = _state(storage, kb_id)
    assert state["event_generation"] == 1
    assert state["pending_evaluation_generation"] == 1
    assert state["pending_reasons"] == [reason]
    assert state["pending_severity"] == severity


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "Updated title"),
        ("source_site", "updated.example"),
        ("published_time", "2026-08-19"),
    ],
)
def test_file_builder_metadata_changes_mark_one_soft_event(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    storage, kb_id, file_url = _seed_member(tmp_path, name=f"file-{field}")
    try:
        _upsert_file_metadata(storage, file_url, **{field: value})
        _assert_single_event(storage, kb_id)
    finally:
        storage.close()


@pytest.mark.parametrize("field", ["category", "summary", "keywords"])
def test_catalog_builder_metadata_changes_mark_one_soft_event(
    tmp_path: Path,
    field: str,
) -> None:
    storage, kb_id, file_url = _seed_member(tmp_path, name=f"catalog-{field}")
    try:
        value: Any = ["updated", "keywords"] if field == "keywords" else f"Updated {field}"
        success, reason = storage.update_file_catalog(file_url, **{field: value})
        assert (success, reason) == (True, None)
        _assert_single_event(storage, kb_id)
    finally:
        storage.close()


def test_markdown_change_marks_one_soft_event(tmp_path: Path) -> None:
    storage, kb_id, file_url = _seed_member(tmp_path, name="markdown")
    try:
        assert storage.update_file_markdown(file_url, "# Updated\n\nBody") == (True, None)
        _assert_single_event(storage, kb_id)
    finally:
        storage.close()


def test_canonical_noops_and_audit_only_changes_do_not_mark_events(tmp_path: Path) -> None:
    storage, kb_id, file_url = _seed_member(tmp_path, name="canonical-noop")
    try:
        storage.upsert_catalog_item(
            _catalog_item(file_url),
            pipeline_version="catalog-v2",
            status="ok",
            processed_at="2026-08-19T01:00:00+00:00",
        )
        _upsert_file_metadata(storage, file_url, etag="etag-after")
        assert storage.update_file_catalog(file_url, category="Category") == (True, None)
        assert _state(storage, kb_id)["event_generation"] == 0
    finally:
        storage.close()


def test_logically_identical_keywords_are_a_canonical_noop(tmp_path: Path) -> None:
    storage, kb_id, file_url = _seed_member(tmp_path, name="keyword-canonical")
    try:
        storage.update_file_catalog(file_url, keywords=["寿险"])
        first = _state(storage, kb_id)["event_generation"]
        storage.update_file_catalog(file_url, keywords=["寿险"])
        assert _state(storage, kb_id)["event_generation"] == first
    finally:
        storage.close()


def test_non_ok_to_ok_marks_soft_metadata_event(tmp_path: Path) -> None:
    storage, kb_id, file_url = _seed_member(tmp_path, name="recovered", status="error")
    try:
        storage.upsert_catalog_item(
            _catalog_item(file_url),
            pipeline_version="catalog-v2",
            status="ok",
        )
        _assert_single_event(storage, kb_id)
    finally:
        storage.close()


@pytest.mark.parametrize("status", ["error", "invalid"])
def test_ok_to_non_ok_marks_hard_source_invalidated(
    tmp_path: Path,
    status: str,
) -> None:
    storage, kb_id, file_url = _seed_member(tmp_path, name=f"invalidated-{status}")
    try:
        storage.upsert_catalog_item(
            _catalog_item(file_url),
            pipeline_version="catalog-v2",
            status=status,
            error="invalidated",
        )
        _assert_single_event(
            storage,
            kb_id,
            reason="source_invalidated",
            severity="hard_stale",
        )
    finally:
        storage.close()


def test_explicit_file_deletion_marks_hard_source_deleted(tmp_path: Path) -> None:
    storage, kb_id, file_url = _seed_member(tmp_path, name="deleted")
    try:
        storage.mark_file_deleted(file_url, "2026-08-19T01:00:00+00:00")
        _assert_single_event(
            storage,
            kb_id,
            reason="source_deleted",
            severity="hard_stale",
        )
    finally:
        storage.close()


def test_catalog_deleted_status_marks_hard_source_deleted(tmp_path: Path) -> None:
    storage, kb_id, file_url = _seed_member(tmp_path, name="catalog-deleted")
    try:
        storage.upsert_catalog_item(
            _catalog_item(file_url),
            pipeline_version="catalog-v2",
            status="deleted",
        )
        _assert_single_event(
            storage,
            kb_id,
            reason="source_deleted",
            severity="hard_stale",
        )
    finally:
        storage.close()


def test_non_ok_to_non_ok_metadata_changes_do_not_mark_events(tmp_path: Path) -> None:
    storage, kb_id, file_url = _seed_member(tmp_path, name="still-invalid", status="error")
    try:
        storage.upsert_catalog_item(
            _catalog_item(file_url, suffix=" changed"),
            pipeline_version="catalog-v2",
            status="skipped",
            error="still not builder input",
        )
        _upsert_file_metadata(storage, file_url, title="Invisible while invalid")
        assert _state(storage, kb_id)["event_generation"] == 0
    finally:
        storage.close()


def test_non_member_file_changes_do_not_mark_any_kb(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "non-member.db"))
    try:
        _create_kb(storage, "kb-member")
        _create_file(storage, tmp_path, "https://example.com/non-member.pdf")
        _upsert_file_metadata(
            storage,
            "https://example.com/non-member.pdf",
            title="Changed but unselected",
        )
        assert _state(storage, "kb-member")["event_generation"] == 0
    finally:
        storage.close()


def test_multiple_kbs_and_profiles_are_updated_once_and_only_when_members(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "multiple-kbs.db"))
    file_url = "https://example.com/shared.pdf"
    try:
        for kb_id in ("kb-one", "kb-two", "kb-unrelated"):
            _create_kb(storage, kb_id)
            storage.set_agentic_ready_automation(
                kb_id=kb_id,
                profile="special",
                automatic_build_enabled=False,
                automatic_publish_enabled=False,
            )
        _create_file(storage, tmp_path, file_url)
        for kb_id in ("kb-one", "kb-two"):
            _add_membership(storage, kb_id=kb_id, file_url=file_url)

        storage.update_file_catalog(file_url, summary="Shared update")

        for kb_id in ("kb-one", "kb-two"):
            for profile in ("general", "special"):
                state = _state(storage, kb_id, profile)
                assert state["event_generation"] == 1
                assert state["pending_reasons"] == ["metadata_updated"]
        for profile in ("general", "special"):
            assert _state(storage, "kb-unrelated", profile)["event_generation"] == 0
    finally:
        storage.close()


def test_api_title_and_catalog_update_is_atomic_and_advances_once(tmp_path: Path) -> None:
    storage, kb_id, file_url = _seed_member(tmp_path, name="api-combined")
    db_path = storage.db_path
    storage.close()

    result = update_file_record(
        db_path=db_path,
        payload={
            "url": file_url,
            "title": "API title",
            "category": "API category",
            "summary": "API summary",
            "keywords": ["api", "combined"],
        },
    )

    storage = Storage(db_path)
    try:
        assert result["file"]["title"] == "API title"
        assert result["file"]["category"] == "API category"
        _assert_single_event(storage, kb_id)
    finally:
        storage.close()


def test_marker_failure_rolls_back_combined_api_data_and_all_generations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = Storage(str(tmp_path / "api-rollback.db"))
    file_url = "https://example.com/api-rollback.pdf"
    try:
        for kb_id in ("kb-one", "kb-two"):
            _create_kb(storage, kb_id)
            storage.set_agentic_ready_automation(
                kb_id=kb_id,
                profile="special",
                automatic_build_enabled=True,
                automatic_publish_enabled=False,
            )
        _create_file(storage, tmp_path, file_url)
        for kb_id in ("kb-one", "kb-two"):
            _add_membership(storage, kb_id=kb_id, file_url=file_url)
        before = storage.get_file_with_catalog(file_url)
        assert before is not None
    finally:
        storage.close()

    original = Storage.mark_agentic_ready_source_event_for_kb
    calls = 0

    def fail_second(
        self: Storage,
        *,
        kb_id: str,
        reason: str,
    ) -> list[dict[str, Any]]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected metadata marker failure")
        return original(self, kb_id=kb_id, reason=reason)

    monkeypatch.setattr(Storage, "mark_agentic_ready_source_event_for_kb", fail_second)

    with pytest.raises(RuntimeError, match="injected metadata marker failure"):
        update_file_record(
            db_path=str(tmp_path / "api-rollback.db"),
            payload={
                "url": file_url,
                "title": "Should roll back",
                "category": "Should roll back",
            },
        )

    storage = Storage(str(tmp_path / "api-rollback.db"))
    try:
        after = storage.get_file_with_catalog(file_url)
        assert after is not None
        assert after["title"] == before["title"]
        assert after["category"] == before["category"]
        for kb_id in ("kb-one", "kb-two"):
            for profile in ("general", "special"):
                assert _state(storage, kb_id, profile)["event_generation"] == 0
            automation = storage.get_agentic_ready_automation_state(
                kb_id=kb_id,
                profile="special",
            )
            assert automation["automatic_build_enabled"] is True
            assert automation["automation_state"] == "idle"
    finally:
        storage.close()


def test_upsert_catalog_ingestion_detects_change_then_noop(tmp_path: Path) -> None:
    storage, kb_id, file_url = _seed_member(tmp_path, name="catalog-ingestion")
    try:
        changed = _catalog_item(file_url, suffix=" changed")
        storage.upsert_catalog_item(changed, pipeline_version="catalog-v2", status="ok")
        _assert_single_event(storage, kb_id)
        storage.upsert_catalog_item(changed, pipeline_version="catalog-v3", status="ok")
        assert _state(storage, kb_id)["event_generation"] == 1
    finally:
        storage.close()


def test_web_page_collector_does_not_bypass_file_metadata_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage, kb_id, file_url = _seed_member(tmp_path, name="web-page-collector")
    collector = WebPageCollector(storage, str(tmp_path / "downloads"))
    target_path = tmp_path / "collected-page.md"
    target_path.write_text("collected", encoding="utf-8")
    monkeypatch.setattr(
        collector,
        "_fetch_html",
        lambda _url: (
            b"<html><title>Collected title</title></html>",
            {"content-type": "text/html"},
            file_url,
        ),
    )
    monkeypatch.setattr(
        collector,
        "_extract_text",
        lambda _html, _url: "Updated page body " * 20,
    )
    monkeypatch.setattr(
        collector,
        "_save_content",
        lambda _url, _content, _site: target_path,
    )

    try:
        result = collector._collect_page(
            file_url,
            CollectionConfig(name="Updated site", source_type="web_page"),
        )

        assert result is not None
        _assert_single_event(storage, kb_id)
        assert storage.get_file_by_url(file_url)["source_site"] == "Updated site"
    finally:
        storage.close()


def test_incremental_catalog_combines_title_and_catalog_event_without_bypass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage, kb_id, file_url = _seed_member(
        tmp_path,
        name="incremental",
        status="error",
    )
    db_path = storage.db_path
    storage.close()

    item = CatalogItem(
        source_site="example.com",
        title="Incremental source title",
        original_filename="incremental.pdf",
        url=file_url,
        local_path=str(tmp_path / "incremental.pdf"),
        keywords=["incremental"],
        summary="Incremental summary",
        category="Incremental category",
    )

    def fake_process(row: dict[str, Any], *_args: Any, **_kwargs: Any):
        return row, item, "ok", "Incremental suggested title"

    monkeypatch.setattr(catalog_incremental, "_process_single_row", fake_process)
    kwargs = {
        "db_path": db_path,
        "file_urls": [file_url],
        "out_jsonl": tmp_path / "incremental.jsonl",
        "out_md": tmp_path / "incremental.md",
        "skip_existing": False,
        "update_title": True,
        "max_workers": 1,
    }

    catalog_incremental.run_catalog_for_urls(**kwargs)
    storage = Storage(db_path)
    try:
        _assert_single_event(storage, kb_id)
        assert storage.get_file_by_url(file_url)["title"] == "Incremental suggested title"
    finally:
        storage.close()

    catalog_incremental.run_catalog_for_urls(**kwargs)
    storage = Storage(db_path)
    try:
        assert _state(storage, kb_id)["event_generation"] == 1
    finally:
        storage.close()


def test_indexing_rag_chunk_count_change_uses_metadata_event_semantics(
    tmp_path: Path,
) -> None:
    storage, kb_id, file_url = _seed_member(tmp_path, name="indexing")
    try:
        pipeline = IndexingPipeline.__new__(IndexingPipeline)
        pipeline.storage = storage

        pipeline._update_file_index_status(kb_id, file_url, 7)
        _assert_single_event(storage, kb_id)
        pipeline._update_file_index_status(kb_id, file_url, 7)
        assert _state(storage, kb_id)["event_generation"] == 1
    finally:
        storage.close()


def test_metadata_event_does_not_change_publication_slots_or_default_flags(
    tmp_path: Path,
) -> None:
    storage, kb_id, file_url = _seed_member(tmp_path, name="serving-slots")
    try:
        publication = storage.record_agentic_ready_publication(
            kb_id=kb_id,
            index_version_id=None,
            source_version_kind="catalog_chunks_snapshot",
            source_version_id="source-before-metadata",
            profile="general",
            profile_version="1",
            status="validated",
            output_dir=str(tmp_path / "agentic_ready_data" / "staging" / "active"),
            artifact_digest="digest-before-metadata",
        )
        published = storage.publish_agentic_ready_publication(
            str(publication["publication_id"]),
            expected_active_publication_id=None,
        )
        before_active = published["active_publication_id"]
        before_previous = published["previous_publication_id"]

        storage.update_file_catalog(file_url, summary="Serving-safe update")

        after = storage.get_agentic_ready_publication_state(
            kb_id=kb_id,
            profile="general",
        )
        automation = storage.get_agentic_ready_automation_state(
            kb_id=kb_id,
            profile="general",
        )
        assert after["active_publication_id"] == before_active
        assert after["previous_publication_id"] == before_previous
        assert automation["automatic_build_enabled"] is False
        assert automation["automatic_publish_enabled"] is False
    finally:
        storage.close()


def test_enabled_automation_claims_metadata_generation_with_one_shot_runner(
    tmp_path: Path,
) -> None:
    storage, kb_id, file_url = _seed_member(tmp_path, name="automation-metadata")
    db_path = storage.db_path
    try:
        storage.update_file_markdown(file_url, "# Metadata automation\n\nReady body")
        state = _state(storage, kb_id)
        storage.record_agentic_ready_source_evaluation(
            kb_id=kb_id,
            profile="general",
            evaluated_generation=int(state["event_generation"]),
            source_version_kind="catalog_chunks_snapshot",
            source_version_id="seed-source",
        )
        storage.set_agentic_ready_automation(
            kb_id=kb_id,
            profile="general",
            automatic_build_enabled=True,
            automatic_publish_enabled=False,
        )
        _upsert_file_metadata(storage, file_url, title="Automation metadata update")
        pending_generation = int(_state(storage, kb_id)["pending_evaluation_generation"])
    finally:
        storage.close()

    result = run_ready_data_automation_once(
        db_path=db_path,
        heartbeat_interval_seconds=0,
    )

    assert result["status"] == "awaiting_publish"
    assert result["generation"] == pending_generation
