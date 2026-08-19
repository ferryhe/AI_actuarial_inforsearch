from __future__ import annotations

from pathlib import Path

import pytest

from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.storage import Storage


def _manager_with_files(
    tmp_path: Path,
    *,
    kb_id: str = "kb-membership",
    manifest_profile: str = "general",
    file_count: int = 2,
) -> tuple[Storage, KnowledgeBaseManager, list[str]]:
    storage = Storage(str(tmp_path / f"{kb_id}.db"))
    manager = KnowledgeBaseManager(
        storage,
        config=RAGConfig(data_dir=str(tmp_path / "rag-data")),
    )
    manager.create_kb(
        kb_id=kb_id,
        name=f"Membership {kb_id}",
        kb_mode="manual",
        manifest_profile=manifest_profile,
    )
    file_urls = [f"https://example.com/{kb_id}-{index}.pdf" for index in range(file_count)]
    for index, file_url in enumerate(file_urls):
        storage.insert_file(
            url=file_url,
            sha256=f"sha-{kb_id}-{index}",
            title=f"File {index}",
            source_site="example.com",
            source_page_url="https://example.com",
            original_filename=f"file-{index}.pdf",
            local_path=str(tmp_path / f"{kb_id}-{index}.pdf"),
            bytes=100 + index,
            content_type="application/pdf",
        )
    return storage, manager, file_urls


def _evaluate_pending(storage: Storage, *, kb_id: str, profile: str = "general") -> None:
    state = storage.get_agentic_ready_source_state(kb_id=kb_id, profile=profile)
    storage.record_agentic_ready_source_evaluation(
        kb_id=kb_id,
        profile=profile,
        evaluated_generation=int(state["event_generation"]),
        source_version_kind="catalog_chunks_snapshot",
        source_version_id=f"snapshot-{state['event_generation']}",
    )


def test_membership_add_marks_soft_stale_once(tmp_path: Path) -> None:
    storage, manager, file_urls = _manager_with_files(tmp_path)
    try:
        storage._conn.execute(
            "UPDATE rag_knowledge_bases SET manifest_profile = NULL WHERE kb_id = ?",
            ("kb-membership",),
        )
        storage._conn.commit()

        result = manager.add_files_to_kb("kb-membership", [file_urls[0]])

        state = storage.get_agentic_ready_source_state(
            kb_id="kb-membership",
            profile="general",
        )
        assert result == {"added_count": 1, "skipped_count": 0, "total_files": 1}
        assert state["event_generation"] == 1
        assert state["pending_evaluation_generation"] == 1
        assert state["pending_severity"] == "soft_stale"
        assert state["pending_reasons"] == ["membership_added"]
        assert state["serving_allowed"] is True
    finally:
        storage.close()


def test_batch_add_marks_all_known_profiles_once_without_touching_other_kbs(tmp_path: Path) -> None:
    storage, manager, file_urls = _manager_with_files(tmp_path)
    try:
        manager.create_kb(
            kb_id="kb-other",
            name="Other KB",
            kb_mode="manual",
        )
        storage.mark_agentic_ready_source_event(
            kb_id="kb-membership",
            profile="state-profile",
            reason="profile_contract_changed",
        )
        storage.set_agentic_ready_automation(
            kb_id="kb-membership",
            profile="slot-profile",
            automatic_build_enabled=False,
            automatic_publish_enabled=False,
        )
        storage.upsert_agentic_ready_manifest(
            kb_id="kb-membership",
            profile="manifest-profile",
            profile_version="1",
            status="missing",
        )
        storage.record_agentic_ready_publication(
            kb_id="kb-membership",
            index_version_id=None,
            source_version_kind="catalog_chunks_snapshot",
            source_version_id="publication-source",
            profile="publication-profile",
            profile_version="1",
            status="failed",
            output_dir=str(tmp_path / "unused-publication"),
            artifact_digest="publication-digest",
        )
        other_before = storage.mark_agentic_ready_source_event(
            kb_id="kb-other",
            profile="general",
            reason="membership_added",
        )

        result = manager.add_files_to_kb("kb-membership", file_urls)

        assert result["added_count"] == 2
        expected_generations = {
            "general": 1,
            "state-profile": 2,
            "slot-profile": 1,
            "manifest-profile": 1,
            "publication-profile": 1,
        }
        for profile, generation in expected_generations.items():
            state = storage.get_agentic_ready_source_state(
                kb_id="kb-membership",
                profile=profile,
            )
            assert state["event_generation"] == generation
            assert state["pending_reasons"][-1] == "membership_added"
        other_after = storage.get_agentic_ready_source_state(
            kb_id="kb-other",
            profile="general",
        )
        assert other_after["event_generation"] == other_before["event_generation"]
    finally:
        storage.close()


def test_duplicate_add_does_not_advance_generation(tmp_path: Path) -> None:
    storage, manager, file_urls = _manager_with_files(tmp_path)
    try:
        storage.set_agentic_ready_automation(
            kb_id="kb-membership",
            profile="slot-profile",
            automatic_build_enabled=False,
            automatic_publish_enabled=False,
        )
        manager.add_files_to_kb("kb-membership", [file_urls[0]])
        before = {
            profile: storage.get_agentic_ready_source_state(
                kb_id="kb-membership",
                profile=profile,
            )
            for profile in ("general", "slot-profile")
        }

        result = manager.add_files_to_kb("kb-membership", [file_urls[0]])

        assert result["added_count"] == 0
        assert result["skipped_count"] == 1
        for profile in before:
            after = storage.get_agentic_ready_source_state(
                kb_id="kb-membership",
                profile=profile,
            )
            assert after["event_generation"] == before[profile]["event_generation"]
            assert after["pending_reasons"] == before[profile]["pending_reasons"]
    finally:
        storage.close()


def test_membership_remove_marks_hard_stale_once(tmp_path: Path) -> None:
    storage, manager, file_urls = _manager_with_files(tmp_path)
    try:
        manager.add_files_to_kb("kb-membership", file_urls)
        _evaluate_pending(storage, kb_id="kb-membership")

        removed = manager.remove_files_from_kb("kb-membership", file_urls)

        state = storage.get_agentic_ready_source_state(
            kb_id="kb-membership",
            profile="general",
        )
        assert removed == 2
        assert state["event_generation"] == 2
        assert state["pending_evaluation_generation"] == 2
        assert state["pending_severity"] == "hard_stale"
        assert state["pending_reasons"] == ["membership_removed"]
        assert state["serving_allowed"] is False
    finally:
        storage.close()


def test_missing_remove_does_not_advance_generation(tmp_path: Path) -> None:
    storage, manager, file_urls = _manager_with_files(tmp_path)
    try:
        manager.add_files_to_kb("kb-membership", [file_urls[0]])
        before = storage.get_agentic_ready_source_state(
            kb_id="kb-membership",
            profile="general",
        )

        removed = manager.remove_files_from_kb("kb-membership", [file_urls[1]])

        after = storage.get_agentic_ready_source_state(
            kb_id="kb-membership",
            profile="general",
        )
        assert removed == 0
        assert after["event_generation"] == before["event_generation"]
        assert after["pending_reasons"] == before["pending_reasons"]
    finally:
        storage.close()


def test_source_mark_failure_rolls_back_membership_count_and_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage, manager, file_urls = _manager_with_files(tmp_path)
    storage.set_agentic_ready_automation(
        kb_id="kb-membership",
        profile="slot-profile",
        automatic_build_enabled=False,
        automatic_publish_enabled=False,
    )
    original = storage.mark_agentic_ready_source_event_for_kb

    def fail_after_mark(*, kb_id: str, reason: str):
        original(kb_id=kb_id, reason=reason)
        raise RuntimeError("injected source-state failure")

    monkeypatch.setattr(storage, "mark_agentic_ready_source_event_for_kb", fail_after_mark)
    try:
        with pytest.raises(RuntimeError, match="injected source-state failure"):
            manager.add_files_to_kb("kb-membership", [file_urls[0]])

        membership_count = storage._conn.execute(
            "SELECT COUNT(*) FROM rag_kb_files WHERE kb_id = ?",
            ("kb-membership",),
        ).fetchone()[0]
        file_count = storage._conn.execute(
            "SELECT file_count FROM rag_knowledge_bases WHERE kb_id = ?",
            ("kb-membership",),
        ).fetchone()[0]
        assert membership_count == 0
        assert file_count == 0
        for profile in ("general", "slot-profile"):
            state = storage.get_agentic_ready_source_state(
                kb_id="kb-membership",
                profile=profile,
            )
            assert state["has_source_state"] is False
            assert state["event_generation"] == 0
    finally:
        storage.close()


def test_source_mark_failure_rolls_back_removal_count_and_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage, manager, file_urls = _manager_with_files(tmp_path)
    try:
        manager.add_files_to_kb("kb-membership", [file_urls[0]])
        before = storage.get_agentic_ready_source_state(
            kb_id="kb-membership",
            profile="general",
        )
        original = storage.mark_agentic_ready_source_event_for_kb

        def fail_after_mark(*, kb_id: str, reason: str):
            original(kb_id=kb_id, reason=reason)
            raise RuntimeError("injected source-state failure")

        monkeypatch.setattr(storage, "mark_agentic_ready_source_event_for_kb", fail_after_mark)

        with pytest.raises(RuntimeError, match="injected source-state failure"):
            manager.remove_files_from_kb("kb-membership", [file_urls[0]])

        membership_count = storage._conn.execute(
            "SELECT COUNT(*) FROM rag_kb_files WHERE kb_id = ?",
            ("kb-membership",),
        ).fetchone()[0]
        file_count = storage._conn.execute(
            "SELECT file_count FROM rag_knowledge_bases WHERE kb_id = ?",
            ("kb-membership",),
        ).fetchone()[0]
        after = storage.get_agentic_ready_source_state(
            kb_id="kb-membership",
            profile="general",
        )
        assert membership_count == 1
        assert file_count == 1
        assert after["event_generation"] == before["event_generation"]
        assert after["pending_reasons"] == before["pending_reasons"]
    finally:
        storage.close()


def test_membership_events_preserve_publication_pointers_and_serving_manifest(tmp_path: Path) -> None:
    storage, manager, file_urls = _manager_with_files(tmp_path)
    try:
        previous = storage.record_agentic_ready_publication(
            kb_id="kb-membership",
            index_version_id=None,
            source_version_kind="catalog_chunks_snapshot",
            source_version_id="previous-source",
            profile="general",
            profile_version="1",
            status="validated",
            output_dir=str(tmp_path / "previous-publication"),
            artifact_digest="previous-digest",
        )
        active = storage.record_agentic_ready_publication(
            kb_id="kb-membership",
            index_version_id=None,
            source_version_kind="catalog_chunks_snapshot",
            source_version_id="active-source",
            profile="general",
            profile_version="1",
            status="validated",
            output_dir=str(tmp_path / "active-publication"),
            artifact_digest="active-digest",
        )
        storage._conn.execute(
            """
            INSERT INTO agentic_ready_slots (
                kb_id, profile, active_publication_id, previous_publication_id,
                automatic_build_enabled, automatic_publish_enabled, updated_at
            )
            VALUES (?, 'general', ?, ?, 0, 0, ?)
            """,
            (
                "kb-membership",
                active["publication_id"],
                previous["publication_id"],
                storage._utcnow_iso(),
            ),
        )
        storage._conn.commit()
        manifest_before = storage.upsert_agentic_ready_manifest(
            kb_id="kb-membership",
            profile="general",
            profile_version="1",
            status="ready",
            output_dir=str(tmp_path / "serving-manifest"),
            publication_id=str(active["publication_id"]),
            source_version_kind="catalog_chunks_snapshot",
            source_version_id="active-source",
            artifact_digest="active-digest",
        )
        before = storage.get_agentic_ready_publication_state(
            kb_id="kb-membership",
            profile="general",
        )

        manager.add_files_to_kb("kb-membership", [file_urls[0]])

        after = storage.get_agentic_ready_publication_state(
            kb_id="kb-membership",
            profile="general",
        )
        assert after["active_publication_id"] == before["active_publication_id"]
        assert after["previous_publication_id"] == before["previous_publication_id"]
        assert storage.get_agentic_ready_manifest(
            kb_id="kb-membership",
            profile="general",
        ) == manifest_before

        manager.remove_files_from_kb("kb-membership", [file_urls[0]])

        after_removal = storage.get_agentic_ready_publication_state(
            kb_id="kb-membership",
            profile="general",
        )
        assert after_removal["active_publication_id"] == before["active_publication_id"]
        assert after_removal["previous_publication_id"] == before["previous_publication_id"]
        assert storage.get_agentic_ready_manifest(
            kb_id="kb-membership",
            profile="general",
        ) == manifest_before
    finally:
        storage.close()
