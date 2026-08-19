from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from ai_actuarial.api.services.agentic_rag import AgenticRagError, _resolve_ready_output_dir
from ai_actuarial.api.services.rag_admin import (
    _bootstrap_legacy_ready_publication,
    _build_agentic_manifest_status,
)
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.storage import Storage


def _ready_dir(tmp_path: Path, name: str) -> Path:
    output_dir = tmp_path / "agentic_ready_data" / "staging" / name
    output_dir.mkdir(parents=True)
    (output_dir / "ready_data_manifest.json").write_text(
        json.dumps({"profile": "general", "profile_version": "1"}),
        encoding="utf-8",
    )
    return output_dir


def _create_kb(storage: Storage, kb_id: str = "kb-source-state") -> None:
    KnowledgeBaseManager(storage).create_kb(
        kb_id=kb_id,
        name="Ready source state",
        kb_mode="manual",
        manifest_profile="general",
    )


def _publish(
    storage: Storage,
    tmp_path: Path,
    *,
    kb_id: str = "kb-source-state",
    source_version_id: str = "rdsnap_active",
) -> dict[str, object]:
    output_dir = _ready_dir(tmp_path, source_version_id)
    publication = storage.record_agentic_ready_publication(
        kb_id=kb_id,
        index_version_id=None,
        source_version_kind="catalog_chunks_snapshot",
        source_version_id=source_version_id,
        profile="general",
        profile_version="1",
        status="validated",
        output_dir=str(output_dir),
        artifact_files=["ready_data_manifest.json"],
        doc_count=1,
        section_count=1,
        built_at="2026-08-18T00:00:00+00:00",
        artifact_digest=f"digest-{source_version_id}",
        source_db=storage.db_path,
    )
    current_state = storage.get_agentic_ready_publication_state(
        kb_id=kb_id,
        profile="general",
    )
    storage.publish_agentic_ready_publication(
        str(publication["publication_id"]),
        expected_active_publication_id=current_state["active_publication_id"],
    )
    return storage.get_agentic_ready_manifest(kb_id=kb_id, profile="general") or {}


def _mark_and_evaluate(
    storage: Storage,
    *,
    reason: str,
    source_version_id: str,
    kb_id: str = "kb-source-state",
) -> dict[str, object]:
    marked = storage.mark_agentic_ready_source_event(
        kb_id=kb_id,
        profile="general",
        reason=reason,
    )
    return storage.record_agentic_ready_source_evaluation(
        kb_id=kb_id,
        profile="general",
        evaluated_generation=int(marked["event_generation"]),
        source_version_kind="catalog_chunks_snapshot",
        source_version_id=source_version_id,
    )


def test_soft_stale_remains_usable_and_is_explicitly_marked(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        _publish(storage, tmp_path)

        source_state = _mark_and_evaluate(
            storage,
            reason="membership_added",
            source_version_id="rdsnap_with_addition",
        )
        status = _build_agentic_manifest_status(
            storage=storage,
            kb_id="kb-source-state",
            profile="general",
        )

        assert source_state["stale_severity"] == "soft_stale"
        assert source_state["stale_confirmed"] is True
        assert source_state["serving_stale"] is True
        assert source_state["serving_allowed"] is True
        assert status["status"] == "stale"
        assert status["usable"] is True
        assert status["serving_stale"] is True
        assert status["fallback_mode"] == "agentic"
        assert _resolve_ready_output_dir(
            db_path=storage.db_path,
            payload={"kb_id": "kb-source-state", "profile": "general"},
        )[0] == status["output_dir"]
    finally:
        storage.close()


def test_hard_stale_blocks_old_agentic_publication(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        _publish(storage, tmp_path)

        source_state = _mark_and_evaluate(
            storage,
            reason="membership_removed",
            source_version_id="rdsnap_after_removal",
        )
        status = _build_agentic_manifest_status(
            storage=storage,
            kb_id="kb-source-state",
            profile="general",
        )

        assert source_state["stale_severity"] == "hard_stale"
        assert source_state["serving_allowed"] is False
        assert status["usable"] is False
        assert status["fallback_mode"] == "standard"
        with pytest.raises(AgenticRagError, match="hard stale") as exc_info:
            _resolve_ready_output_dir(
                db_path=storage.db_path,
                payload={"kb_id": "kb-source-state", "profile": "general"},
            )
        assert exc_info.value.status_code == 409
    finally:
        storage.close()


def test_prior_hard_is_not_inherited_after_active_catches_up(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        _publish(storage, tmp_path, source_version_id="rdsnap_a")
        hard = _mark_and_evaluate(
            storage,
            reason="membership_removed",
            source_version_id="rdsnap_b",
        )
        assert hard["stale_severity"] == "hard_stale"

        _publish(storage, tmp_path, source_version_id="rdsnap_b")
        caught_up = storage.get_agentic_ready_source_state(
            kb_id="kb-source-state",
            profile="general",
        )
        assert caught_up["stale_severity"] == "none"
        assert caught_up["serving_allowed"] is True

        soft = _mark_and_evaluate(
            storage,
            reason="membership_added",
            source_version_id="rdsnap_c",
        )

        assert soft["stale_severity"] == "soft_stale"
        assert soft["serving_allowed"] is True
        assert soft["stale_reasons"] == ["membership_added"]
    finally:
        storage.close()


def test_addition_and_removal_have_distinct_severity(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        addition = storage.mark_agentic_ready_source_event(
            kb_id="kb-source-state",
            profile="general",
            reason="membership_added",
        )
        assert addition["pending_severity"] == "soft_stale"
        assert addition["stale_confirmed"] is False
        assert addition["stale_severity"] == "none"
        assert addition["serving_stale"] is False
        assert addition["serving_allowed"] is True

        removal = storage.mark_agentic_ready_source_event(
            kb_id="kb-source-state",
            profile="general",
            reason="membership_removed",
        )
        assert removal["pending_severity"] == "hard_stale"
        assert removal["serving_allowed"] is False
    finally:
        storage.close()


def test_index_only_evaluation_does_not_create_false_stale(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        _publish(storage, tmp_path)
        marked = storage.mark_agentic_ready_source_event(
            kb_id="kb-source-state",
            profile="general",
            reason="index_committed",
        )

        evaluated = storage.record_agentic_ready_source_evaluation(
            kb_id="kb-source-state",
            profile="general",
            evaluated_generation=int(marked["event_generation"]),
            source_version_kind="catalog_chunks_snapshot",
            source_version_id="rdsnap_active",
        )

        assert evaluated["event_generation"] == 1
        assert evaluated["evaluated_generation"] == 1
        assert evaluated["pending_evaluation_generation"] is None
        assert evaluated["stale_confirmed"] is False
        assert evaluated["stale_severity"] == "none"
        assert evaluated["serving_stale"] is False
    finally:
        storage.close()


def test_unchanged_authoritative_source_clears_pending_evaluation(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        _publish(storage, tmp_path)
        marked = storage.mark_agentic_ready_source_event(
            kb_id="kb-source-state",
            profile="general",
            reason="metadata_updated",
        )

        evaluated = storage.record_agentic_ready_source_evaluation(
            kb_id="kb-source-state",
            profile="general",
            evaluated_generation=int(marked["event_generation"]),
            source_version_kind="catalog_chunks_snapshot",
            source_version_id="rdsnap_active",
        )

        assert evaluated["pending_evaluation"] is False
        assert evaluated["pending_evaluation_generation"] is None
        assert evaluated["pending_reasons"] == []
        assert evaluated["stale_severity"] == "none"
    finally:
        storage.close()


@pytest.mark.parametrize(
    ("automatic_build_enabled", "automatic_publish_enabled"),
    [(False, False), (True, False), (True, True)],
)
def test_valid_automatic_build_publish_configurations_are_persisted(
    tmp_path: Path,
    automatic_build_enabled: bool,
    automatic_publish_enabled: bool,
) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        state = storage.set_agentic_ready_automation(
            kb_id="kb-source-state",
            profile="general",
            automatic_build_enabled=automatic_build_enabled,
            automatic_publish_enabled=automatic_publish_enabled,
        )
        assert state["automatic_build_enabled"] is automatic_build_enabled
        assert state["automatic_publish_enabled"] is automatic_publish_enabled
    finally:
        storage.close()


def test_automatic_publish_without_build_is_rejected(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        with pytest.raises(ValueError, match="automatic publish requires automatic build"):
            storage.set_agentic_ready_automation(
                kb_id="kb-source-state",
                profile="general",
                automatic_build_enabled=False,
                automatic_publish_enabled=True,
            )
        state = storage.get_agentic_ready_publication_state(
            kb_id="kb-source-state",
            profile="general",
        )
        assert state["automatic_build_enabled"] is False
        assert state["automatic_publish_enabled"] is False
    finally:
        storage.close()


def test_transaction_rollback_does_not_advance_generation(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        with pytest.raises(RuntimeError, match="rollback"):
            with storage.transaction():
                storage.mark_agentic_ready_source_event(
                    kb_id="kb-source-state",
                    profile="general",
                    reason="membership_added",
                )
                raise RuntimeError("rollback")

        state = storage.get_agentic_ready_source_state(
            kb_id="kb-source-state",
            profile="general",
        )
        assert state["event_generation"] == 0
        assert state["evaluated_generation"] == 0
        assert state["pending_evaluation"] is False
    finally:
        storage.close()


def test_legacy_manifest_does_not_bypass_pending_hard_gate(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage, "kb-legacy")
        output_dir = _ready_dir(tmp_path, "legacy")
        storage.upsert_agentic_ready_manifest(
            kb_id="kb-legacy",
            profile="general",
            profile_version="1",
            status="ready",
            output_dir=str(output_dir),
            artifact_files=["ready_data_manifest.json"],
            doc_count=1,
            section_count=1,
            built_at="2026-08-18T00:00:00+00:00",
            source_db=storage.db_path,
        )
        marked = storage.mark_agentic_ready_source_event(
            kb_id="kb-legacy",
            profile="general",
            reason="access_scope_restricted",
        )

        assert marked["pending_evaluation"] is True
        assert marked["stale_confirmed"] is False
        assert marked["stale_severity"] == "hard_stale"
        assert marked["serving_allowed"] is False
        with pytest.raises(AgenticRagError, match="hard stale"):
            _resolve_ready_output_dir(
                db_path=storage.db_path,
                payload={"kb_id": "kb-legacy", "profile": "general"},
            )
    finally:
        storage.close()


def test_generation_evaluation_is_rejected_when_a_newer_event_exists(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        _publish(storage, tmp_path)
        first = storage.mark_agentic_ready_source_event(
            kb_id="kb-source-state",
            profile="general",
            reason="membership_added",
        )
        storage.mark_agentic_ready_source_event(
            kb_id="kb-source-state",
            profile="general",
            reason="membership_removed",
        )

        with pytest.raises(ValueError, match="latest event generation"):
            storage.record_agentic_ready_source_evaluation(
                kb_id="kb-source-state",
                profile="general",
                evaluated_generation=int(first["event_generation"]),
                source_version_kind="catalog_chunks_snapshot",
                source_version_id="rdsnap_old_candidate",
            )
        state = storage.get_agentic_ready_source_state(
            kb_id="kb-source-state",
            profile="general",
        )
        assert state["event_generation"] == 2
        assert state["evaluated_generation"] == 0
        assert state["pending_severity"] == "hard_stale"
    finally:
        storage.close()


def test_superseded_generation_is_reserved_outside_duplicate_gc(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        publication = _publish(storage, tmp_path)
        recorded = storage.get_agentic_ready_publication(str(publication["publication_id"]))
        assert recorded is not None
        assert recorded["attempt_disposition"] == ""
        assert "superseded_generation" in storage.AGENTIC_READY_RESERVED_ATTEMPT_DISPOSITIONS
        assert recorded["retention_class"] == ""
    finally:
        storage.close()


@pytest.mark.parametrize("later_reason", ["index_committed", "metadata_updated"])
def test_confirmed_hard_stale_is_not_downgraded_by_later_evaluation(
    tmp_path: Path,
    later_reason: str,
) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        _publish(storage, tmp_path)
        hard = _mark_and_evaluate(
            storage,
            reason="membership_removed",
            source_version_id="rdsnap_after_removal",
        )
        assert hard["stale_severity"] == "hard_stale"

        later = _mark_and_evaluate(
            storage,
            reason=later_reason,
            source_version_id="rdsnap_still_not_active",
        )

        assert later["stale_severity"] == "hard_stale"
        assert later["serving_allowed"] is False
        assert "membership_removed" in later["stale_reasons"]
    finally:
        storage.close()


def test_neutral_legacy_evaluation_does_not_create_false_soft_stale(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage, "kb-legacy-neutral")
        output_dir = _ready_dir(tmp_path, "legacy-neutral")
        storage.upsert_agentic_ready_manifest(
            kb_id="kb-legacy-neutral",
            profile="general",
            profile_version="1",
            status="ready",
            output_dir=str(output_dir),
            artifact_files=["ready_data_manifest.json"],
            doc_count=1,
            section_count=1,
            built_at="2026-08-18T00:00:00+00:00",
            source_db=storage.db_path,
        )
        marked = storage.mark_agentic_ready_source_event(
            kb_id="kb-legacy-neutral",
            profile="general",
            reason="embedding_config_changed",
        )

        evaluated = storage.record_agentic_ready_source_evaluation(
            kb_id="kb-legacy-neutral",
            profile="general",
            evaluated_generation=int(marked["event_generation"]),
            source_version_kind="catalog_chunks_snapshot",
            source_version_id="rdsnap_evaluated",
        )

        assert evaluated["source_identity_comparable"] is False
        assert evaluated["stale_confirmed"] is False
        assert evaluated["stale_severity"] == "none"
        assert evaluated["serving_allowed"] is True
        assert evaluated["legacy_heuristic_required"] is True
    finally:
        storage.close()


def test_legacy_hard_gate_survives_evaluation_without_comparable_identity(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage, "kb-legacy-hard")
        output_dir = _ready_dir(tmp_path, "legacy-hard")
        storage.upsert_agentic_ready_manifest(
            kb_id="kb-legacy-hard",
            profile="general",
            profile_version="1",
            status="ready",
            output_dir=str(output_dir),
            artifact_files=["ready_data_manifest.json"],
            built_at="2026-08-18T00:00:00+00:00",
            source_db=storage.db_path,
        )
        marked = storage.mark_agentic_ready_source_event(
            kb_id="kb-legacy-hard",
            profile="general",
            reason="membership_removed",
        )

        evaluated = storage.record_agentic_ready_source_evaluation(
            kb_id="kb-legacy-hard",
            profile="general",
            evaluated_generation=int(marked["event_generation"]),
            source_version_kind="catalog_chunks_snapshot",
            source_version_id="rdsnap_after_removal",
        )

        assert evaluated["source_identity_comparable"] is False
        assert evaluated["legacy_hard_gate"] is True
        assert evaluated["stale_severity"] == "hard_stale"
        assert evaluated["serving_allowed"] is False
    finally:
        storage.close()


@pytest.mark.parametrize("legacy", [False, True])
def test_registered_explicit_output_dir_cannot_bypass_hard_gate(
    tmp_path: Path,
    legacy: bool,
) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        kb_id = "kb-explicit-legacy" if legacy else "kb-explicit-active"
        _create_kb(storage, kb_id)
        if legacy:
            output_dir = _ready_dir(tmp_path, "explicit-legacy")
            storage.upsert_agentic_ready_manifest(
                kb_id=kb_id,
                profile="general",
                profile_version="1",
                status="ready",
                output_dir=str(output_dir),
                artifact_files=["ready_data_manifest.json"],
                source_db=storage.db_path,
            )
        else:
            manifest = _publish(storage, tmp_path, kb_id=kb_id)
            output_dir = Path(str(manifest["output_dir"]))
        storage.mark_agentic_ready_source_event(
            kb_id=kb_id,
            profile="general",
            reason="access_scope_restricted",
        )

        with pytest.raises(AgenticRagError, match="hard stale"):
            _resolve_ready_output_dir(
                db_path=storage.db_path,
                payload={"output_dir": str(output_dir)},
            )
    finally:
        storage.close()


def test_unregistered_explicit_output_dir_keeps_legacy_standalone_behavior(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    storage.close()
    output_dir = _ready_dir(tmp_path, "standalone")

    resolved, kb_id, profile = _resolve_ready_output_dir(
        db_path=str(tmp_path / "index.db"),
        payload={"output_dir": str(output_dir)},
    )

    assert resolved == str(output_dir.resolve())
    assert kb_id == ""
    assert profile == "general"


def test_registered_previous_output_is_rejected_after_hard_state_catches_up(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        previous_manifest = _publish(
            storage,
            tmp_path,
            source_version_id="rdsnap_a",
        )
        _mark_and_evaluate(
            storage,
            reason="membership_removed",
            source_version_id="rdsnap_b",
        )
        active_manifest = _publish(
            storage,
            tmp_path,
            source_version_id="rdsnap_b",
        )
        assert storage.get_agentic_ready_source_state(
            kb_id="kb-source-state",
            profile="general",
        )["serving_allowed"] is True

        with pytest.raises(AgenticRagError, match="not the current serving") as exc_info:
            _resolve_ready_output_dir(
                db_path=storage.db_path,
                payload={"output_dir": previous_manifest["output_dir"]},
            )
        assert exc_info.value.status_code == 409
        assert _resolve_ready_output_dir(
            db_path=storage.db_path,
            payload={"output_dir": active_manifest["output_dir"]},
        )[0] == str(Path(str(active_manifest["output_dir"])).resolve())
    finally:
        storage.close()


def test_bootstrapped_legacy_previous_output_is_not_explicitly_servable(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage, "kb-legacy-previous")
        legacy_output = _ready_dir(tmp_path, "legacy-previous")
        storage.upsert_agentic_ready_manifest(
            kb_id="kb-legacy-previous",
            profile="general",
            profile_version="1",
            status="ready",
            output_dir=str(legacy_output),
            artifact_files=["ready_data_manifest.json"],
            source_db=storage.db_path,
        )
        _bootstrap_legacy_ready_publication(
            storage,
            kb_id="kb-legacy-previous",
            profile="general",
            validator=lambda _path: {"valid": True, "errors": []},
        )
        active_manifest = _publish(
            storage,
            tmp_path,
            kb_id="kb-legacy-previous",
            source_version_id="rdsnap_current",
        )

        with pytest.raises(AgenticRagError, match="not the current serving"):
            _resolve_ready_output_dir(
                db_path=storage.db_path,
                payload={"output_dir": str(legacy_output)},
            )
        assert _resolve_ready_output_dir(
            db_path=storage.db_path,
            payload={"output_dir": active_manifest["output_dir"]},
        )[0] == str(Path(str(active_manifest["output_dir"])).resolve())
    finally:
        storage.close()


def test_concurrent_marks_serialize_without_losing_generation(tmp_path: Path) -> None:
    db_path = tmp_path / "index.db"
    storage = Storage(str(db_path))
    try:
        _create_kb(storage)
    finally:
        storage.close()
    barrier = Barrier(2)

    def mark(reason: str) -> int:
        connection = Storage(str(db_path))
        try:
            barrier.wait(timeout=5)
            state = connection.mark_agentic_ready_source_event(
                kb_id="kb-source-state",
                profile="general",
                reason=reason,
            )
            return int(state["event_generation"])
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(mark, "membership_added"),
            executor.submit(mark, "membership_removed"),
        ]
        generations = sorted(future.result(timeout=10) for future in futures)

    check = Storage(str(db_path))
    try:
        state = check.get_agentic_ready_source_state(
            kb_id="kb-source-state",
            profile="general",
        )
        assert generations == [1, 2]
        assert state["event_generation"] == 2
        assert state["pending_severity"] == "hard_stale"
    finally:
        check.close()


def test_legacy_slot_migration_preserves_publish_as_valid_build_publish_pair(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "index.db"
    storage = Storage(str(db_path))
    try:
        _create_kb(storage)
        storage.set_agentic_ready_automation(
            kb_id="kb-source-state",
            profile="general",
            automatic_build_enabled=True,
            automatic_publish_enabled=True,
        )
        storage._conn.execute(
            """
            UPDATE agentic_ready_slots
            SET automatic_build_enabled = 0, automatic_publish_enabled = 1
            WHERE kb_id = ? AND profile = ?
            """,
            ("kb-source-state", "general"),
        )
        storage._conn.commit()
    finally:
        storage.close()

    migrated = Storage(str(db_path))
    try:
        state = migrated.get_agentic_ready_publication_state(
            kb_id="kb-source-state",
            profile="general",
        )
        assert state["automatic_build_enabled"] is True
        assert state["automatic_publish_enabled"] is True
    finally:
        migrated.close()


def test_superseded_attempt_cannot_be_classified_as_redundant_duplicate(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        active_manifest = _publish(storage, tmp_path)
        duplicate = storage.record_agentic_ready_publication(
            kb_id="kb-source-state",
            index_version_id=None,
            source_version_kind="catalog_chunks_snapshot",
            source_version_id="rdsnap_active",
            profile="general",
            profile_version="1",
            status="validated",
            output_dir=str(_ready_dir(tmp_path, "superseded-duplicate")),
            artifact_files=["ready_data_manifest.json"],
            artifact_digest="digest-rdsnap_active",
            source_db=storage.db_path,
        )
        storage._conn.execute(
            """
            UPDATE agentic_ready_publications
            SET attempt_disposition = 'superseded_generation'
            WHERE publication_id = ?
            """,
            (duplicate["publication_id"],),
        )
        storage._conn.commit()

        assert storage.mark_agentic_ready_publication_redundant_duplicate(
            str(duplicate["publication_id"]),
            expected_active_publication_id=str(active_manifest["publication_id"]),
        ) is False
        recorded = storage.get_agentic_ready_publication(str(duplicate["publication_id"]))
        assert recorded is not None
        assert recorded["retention_class"] == ""
    finally:
        storage.close()


def test_missing_manifest_flattens_hard_source_state_consistently(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        storage.mark_agentic_ready_source_event(
            kb_id="kb-source-state",
            profile="general",
            reason="source_deleted",
        )

        status = _build_agentic_manifest_status(
            storage=storage,
            kb_id="kb-source-state",
            profile="general",
        )

        assert status["status"] == "missing"
        assert status["source_state"]["stale_severity"] == "hard_stale"
        assert status["stale_severity"] == "hard_stale"
        assert status["serving_stale"] is True
        assert status["stale_confirmed"] is False
        assert status["event_generation"] == 1
        assert status["pending_evaluation_generation"] == 1
        assert status["evaluated_generation"] == 0
        assert status["authoritative_source_version_kind"] == ""
        assert status["authoritative_source_version_id"] == ""
    finally:
        storage.close()


def test_neutral_legacy_evaluation_keeps_timestamp_fallback_until_identity_is_comparable(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage, "kb-legacy-heuristic")
        output_dir = _ready_dir(tmp_path, "legacy-heuristic")
        storage.upsert_agentic_ready_manifest(
            kb_id="kb-legacy-heuristic",
            profile="general",
            profile_version="1",
            status="ready",
            output_dir=str(output_dir),
            artifact_files=["ready_data_manifest.json"],
            built_at="2026-01-01T00:00:00+00:00",
            source_db=storage.db_path,
        )
        storage._conn.execute(
            "UPDATE rag_knowledge_bases SET updated_at = ? WHERE kb_id = ?",
            ("2099-01-01T00:00:00+00:00", "kb-legacy-heuristic"),
        )
        storage._conn.commit()
        marked = storage.mark_agentic_ready_source_event(
            kb_id="kb-legacy-heuristic",
            profile="general",
            reason="index_committed",
        )
        storage.record_agentic_ready_source_evaluation(
            kb_id="kb-legacy-heuristic",
            profile="general",
            evaluated_generation=int(marked["event_generation"]),
            source_version_kind="catalog_chunks_snapshot",
            source_version_id="rdsnap_evaluated",
        )

        status = _build_agentic_manifest_status(
            storage=storage,
            kb_id="kb-legacy-heuristic",
            profile="general",
        )

        assert status["source_state"]["legacy_heuristic_required"] is True
        assert status["status"] == "stale"
        assert status["usable"] is False
    finally:
        storage.close()
