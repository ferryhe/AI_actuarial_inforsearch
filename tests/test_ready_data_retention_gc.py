from __future__ import annotations

import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from ai_actuarial.api.services import rag_admin as rag_admin_service
from ai_actuarial.api.services.agentic_rag import (
    AgenticRagError,
    _resolve_ready_output_dir,
)
from ai_actuarial.api.services.rag_admin import (
    READY_DATA_GC_POLICY_VERSION,
    _ready_data_gc_tree_is_safe,
    execute_ready_data_publication_gc,
    plan_ready_data_publication_gc,
)
from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.storage import Storage

CUTOFF = "2026-09-01T00:00:00+00:00"
OLD_MARK = "2026-08-01T00:00:00+00:00"
YOUNG_MARK = "2026-08-20T00:00:00+00:00"


def _open_storage(tmp_path: Path) -> Storage:
    db_path = tmp_path / "index.db"
    storage = Storage(str(db_path))
    KnowledgeBaseManager(
        storage,
        config=RAGConfig(data_dir=str(tmp_path / "rag-data")),
    ).create_kb(
        kb_id="kb-ready",
        name="Ready data GC",
        kb_mode="manual",
        manifest_profile="general",
    )
    return storage


def _candidate_dir(tmp_path: Path, name: str) -> Path:
    candidate = (
        tmp_path / "agentic_ready_data" / "kbs" / "kb-ready" / "general" / "1" / "staging" / name
    )
    candidate.mkdir(parents=True)
    (candidate / "artifact.jsonl").write_text('{"ok":true}\n', encoding="utf-8")
    return candidate


def _record(
    storage: Storage,
    output_dir: Path,
    *,
    source_version_id: str = "idx-duplicate",
    digest: str = "digest-duplicate",
) -> dict[str, object]:
    return storage.record_agentic_ready_publication(
        kb_id="kb-ready",
        index_version_id=source_version_id,
        source_version_kind="index",
        source_version_id=source_version_id,
        profile="general",
        profile_version="1",
        status="validated",
        output_dir=str(output_dir),
        artifact_files=["artifact.jsonl"],
        doc_count=1,
        section_count=1,
        built_at="2026-08-01T00:00:00+00:00",
        artifact_digest=digest,
        source_db=storage.db_path,
        schema_versions={"ready_data": "1"},
    )


def _active(storage: Storage, tmp_path: Path) -> dict[str, object]:
    active = _record(storage, _candidate_dir(tmp_path, "build-active"))
    storage.publish_agentic_ready_publication(
        str(active["publication_id"]),
        expected_active_publication_id=None,
    )
    return active


def _mark(
    storage: Storage,
    active: dict[str, object],
    candidate: dict[str, object],
    *,
    marked_at: str = OLD_MARK,
) -> None:
    assert storage.mark_agentic_ready_publication_redundant_duplicate(
        str(candidate["publication_id"]),
        expected_active_publication_id=str(active["publication_id"]),
    )
    storage._conn.execute(
        """
        UPDATE agentic_ready_publication_gc
        SET marked_at = ?, updated_at = ?
        WHERE publication_id = ?
        """,
        (marked_at, marked_at, candidate["publication_id"]),
    )
    storage._conn.commit()


def _reason_ids(plan: dict[str, object], bucket: str, reason: str) -> set[str]:
    return {
        str(item["publication_id"])
        for item in plan[bucket]  # type: ignore[index]
        if item["reason"] == reason
    }


def _plan(
    storage: Storage,
    *,
    cutoff_at: str = CUTOFF,
) -> dict[str, object]:
    checkpoint = storage._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    assert checkpoint is not None and checkpoint[0] == 0
    return plan_ready_data_publication_gc(
        db_path=storage.db_path,
        cutoff_at=cutoff_at,
    )


def test_active_previous_retryable_and_unknown_attempts_are_protected(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        previous = _active(storage, tmp_path)
        active = _record(storage, _candidate_dir(tmp_path, "build-active-2"), digest="digest-2")
        storage.publish_agentic_ready_publication(
            str(active["publication_id"]),
            expected_active_publication_id=str(previous["publication_id"]),
        )
        retryable = _record(storage, _candidate_dir(tmp_path, "build-retryable"))
        unknown = _record(storage, _candidate_dir(tmp_path, "build-unknown"), digest="unknown")

        plan = _plan(storage)

        assert plan["candidates"] == []
        assert str(active["publication_id"]) in _reason_ids(plan, "retained", "active_slot")
        assert str(previous["publication_id"]) in _reason_ids(plan, "retained", "previous_slot")
        assert str(retryable["publication_id"]) in _reason_ids(
            plan, "retained", "retryable_validated_candidate"
        )
        assert str(unknown["publication_id"]) in _reason_ids(
            plan, "retained", "retryable_validated_candidate"
        )
    finally:
        storage.close()


def test_superseded_generation_removes_retryable_gc_metadata_and_stays_protected(
    tmp_path: Path,
) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        candidate = _record(storage, _candidate_dir(tmp_path, "build-superseded"))
        candidate_id = str(candidate["publication_id"])
        candidate_path = Path(str(candidate["output_dir"]))
        _mark(storage, active, candidate)
        marked = storage.get_agentic_ready_publication(candidate_id)
        assert marked is not None

        assert storage.mark_agentic_ready_publication_superseded_generation(candidate_id)
        superseded = storage.get_agentic_ready_publication(candidate_id)
        assert superseded is not None
        assert superseded["attempt_disposition"] == "superseded_generation"
        assert superseded["retention_class"] == ""
        assert superseded["gc_state"] == ""

        plan = _plan(storage)
        assert candidate_id in _reason_ids(
            plan,
            "retained",
            "attempt_disposition_superseded_generation",
        )
        retained_item = next(
            item for item in plan["retained"] if item["publication_id"] == candidate_id
        )
        assert retained_item["attempt_disposition"] == "superseded_generation"
        assert candidate_id not in {str(item["publication_id"]) for item in plan["candidates"]}
        result = execute_ready_data_publication_gc(
            db_path=storage.db_path,
            cutoff_at=CUTOFF,
            plan_fingerprint=str(plan["plan_fingerprint"]),
        )
        assert candidate_id in _reason_ids(
            result,
            "retained",
            "attempt_disposition_superseded_generation",
        )
        assert candidate_path.is_dir()
        assert (
            storage.claim_agentic_ready_publication_gc(
                candidate_id,
                expected_gc_state="eligible",
                expected_marked_at=str(marked["gc_marked_at"]),
                quarantine_dir=str(candidate_path.parent / f".gc-quarantine-{candidate_id}"),
                cutoff_at=CUTOFF,
            )
            is None
        )
    finally:
        storage.close()


def test_superseded_generation_rejects_serving_or_claimed_attempts(
    tmp_path: Path,
) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        assert (
            storage.mark_agentic_ready_publication_superseded_generation(
                str(active["publication_id"])
            )
            is False
        )

        candidate = _record(storage, _candidate_dir(tmp_path, "build-claimed"))
        _mark(storage, active, candidate)
        storage._conn.execute(
            """
            UPDATE agentic_ready_publication_gc
            SET state = 'claimed', claim_token = 'held', updated_at = ?
            WHERE publication_id = ?
            """,
            (OLD_MARK, candidate["publication_id"]),
        )
        storage._conn.commit()

        assert (
            storage.mark_agentic_ready_publication_superseded_generation(
                str(candidate["publication_id"])
            )
            is False
        )
        claimed = storage.get_agentic_ready_publication(str(candidate["publication_id"]))
        assert claimed is not None
        assert claimed["attempt_disposition"] == ""
        assert claimed["gc_state"] == "claimed"
    finally:
        storage.close()


def test_superseded_generation_rejects_delete_failed_and_preserves_gc_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        attempts = [
            _record(storage, _candidate_dir(tmp_path, f"build-delete-failed-{index}"))
            for index in range(3)
        ]
        for attempt in attempts:
            _mark(storage, active, attempt)
        first_plan = _plan(storage)
        doomed = first_plan["candidates"][0]
        doomed_id = str(doomed["publication_id"])
        original_rmtree = rag_admin_service.shutil.rmtree

        def fail_delete(_path: Path) -> None:
            raise OSError("synthetic delete failure")

        monkeypatch.setattr(rag_admin_service.shutil, "rmtree", fail_delete)
        first = execute_ready_data_publication_gc(
            db_path=storage.db_path,
            cutoff_at=CUTOFF,
            plan_fingerprint=str(first_plan["plan_fingerprint"]),
        )
        failed = storage.get_agentic_ready_publication(doomed_id)
        assert _reason_ids(first, "failures", "delete_failed") == {doomed_id}
        assert failed is not None
        assert failed["gc_state"] == "delete_failed"
        assert failed["retention_class"] == "redundant_duplicate"
        quarantine_dir = Path(str(failed["gc_quarantine_dir"]))
        assert quarantine_dir.is_dir()
        assert not Path(str(doomed["output_dir"])).exists()

        before = storage.get_agentic_ready_publication(doomed_id)
        assert storage.mark_agentic_ready_publication_superseded_generation(doomed_id) is False
        after = storage.get_agentic_ready_publication(doomed_id)
        assert after == before
        assert after is not None
        assert after["attempt_disposition"] == ""
        assert after["gc_state"] == "delete_failed"
        assert after["gc_quarantine_dir"] == str(quarantine_dir)
        assert quarantine_dir.is_dir()

        monkeypatch.setattr(rag_admin_service.shutil, "rmtree", original_rmtree)
        retry_plan = _plan(storage)
        retry = execute_ready_data_publication_gc(
            db_path=storage.db_path,
            cutoff_at=CUTOFF,
            plan_fingerprint=str(retry_plan["plan_fingerprint"]),
        )
        tombstone = storage.get_agentic_ready_publication(doomed_id)
        assert _reason_ids(retry, "deleted", "deleted") == {doomed_id}
        assert tombstone is not None and tombstone["gc_state"] == "deleted"
        assert not quarantine_dir.exists()
    finally:
        storage.close()


def test_superseded_generation_candidate_cannot_be_published(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        candidate = _record(storage, _candidate_dir(tmp_path, "build-superseded-publish"))
        candidate_id = str(candidate["publication_id"])
        assert storage.mark_agentic_ready_publication_superseded_generation(candidate_id)
        assert (
            storage.discard_agentic_ready_publication(
                candidate_id,
                expected_active_publication_id=str(active["publication_id"]),
            )
            is False
        )

        with pytest.raises(ValueError, match="attempt disposition"):
            storage.publish_agentic_ready_publication(
                candidate_id,
                expected_active_publication_id=str(active["publication_id"]),
            )
        state = storage.get_agentic_ready_publication_state(
            kb_id="kb-ready",
            profile="general",
        )
        assert state["active_publication_id"] == active["publication_id"]
        assert state["previous_publication_id"] is None
    finally:
        storage.close()


def test_retention_uses_age_and_newest_two_with_stable_id_tiebreak(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        attempts = [
            _record(storage, _candidate_dir(tmp_path, f"build-duplicate-{index}"))
            for index in range(5)
        ]
        for attempt in attempts[:4]:
            _mark(storage, active, attempt, marked_at=OLD_MARK)
        _mark(storage, active, attempts[4], marked_at=YOUNG_MARK)

        plan = _plan(storage)

        old_ids_desc = sorted((str(item["publication_id"]) for item in attempts[:4]), reverse=True)
        candidate_ids = {str(item["publication_id"]) for item in plan["candidates"]}
        assert candidate_ids == set(old_ids_desc[1:])
        assert {
            old_ids_desc[0],
            str(attempts[4]["publication_id"]),
        } == _reason_ids(plan, "retained", "newest_two")
        assert plan["policy"] == {
            "version": READY_DATA_GC_POLICY_VERSION,
            "minimum_age_days": 14,
            "keep_latest": 2,
            "claim_lease_seconds": 300,
        }
    finally:
        storage.close()


def test_dry_run_does_not_change_database_or_files(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        attempts = [
            _record(storage, _candidate_dir(tmp_path, f"build-dry-{index}")) for index in range(3)
        ]
        for attempt in attempts:
            _mark(storage, active, attempt)
        before = storage._conn.iterdump()
        before_sql = "\n".join(before)
        candidate_paths = [Path(str(item["output_dir"])) for item in attempts]

        plan = _plan(storage)

        after_sql = "\n".join(storage._conn.iterdump())
        assert plan["mode"] == "dry_run"
        assert before_sql == after_sql
        assert all(path.is_dir() for path in candidate_paths)
    finally:
        storage.close()


def test_dry_run_does_not_create_or_change_sqlite_sidecars(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    active = _active(storage, tmp_path)
    attempts = [
        _record(storage, _candidate_dir(tmp_path, f"build-sidecar-{index}")) for index in range(3)
    ]
    for attempt in attempts:
        _mark(storage, active, attempt)
    checkpoint = storage._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    assert checkpoint is not None and checkpoint[0] == 0
    db_path = Path(storage.db_path)
    storage.close()
    before = {
        path.name: path.read_bytes()
        for path in db_path.parent.glob(f"{db_path.name}*")
        if path.is_file()
    }

    plan = plan_ready_data_publication_gc(db_path=str(db_path), cutoff_at=CUTOFF)

    after = {
        path.name: path.read_bytes()
        for path in db_path.parent.glob(f"{db_path.name}*")
        if path.is_file()
    }
    assert plan["mode"] == "dry_run"
    assert after == before


def test_dry_run_fails_closed_on_nonempty_wal_without_changing_files(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        checkpoint = storage._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        assert checkpoint is not None and checkpoint[0] == 0
        storage._conn.execute(
            "UPDATE rag_knowledge_bases SET embedding_model = ? WHERE kb_id = ?",
            ("text-embedding-3-small", "kb-ready"),
        )
        storage._conn.commit()
        db_path = Path(storage.db_path)
        wal_path = Path(f"{storage.db_path}-wal")
        assert wal_path.stat().st_size > 0
        before = {
            path.name: path.read_bytes()
            for path in db_path.parent.glob(f"{db_path.name}*")
            if path.is_file()
        }

        with pytest.raises(ValueError, match="checkpointed"):
            plan_ready_data_publication_gc(db_path=storage.db_path, cutoff_at=CUTOFF)

        after = {
            path.name: path.read_bytes()
            for path in db_path.parent.glob(f"{db_path.name}*")
            if path.is_file()
        }
        assert after == before
    finally:
        storage.close()


def test_plan_fingerprint_binds_derived_candidate_membership(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        attempts = [
            _record(storage, _candidate_dir(tmp_path, f"build-derived-{index}"))
            for index in range(3)
        ]
        for attempt in attempts:
            _mark(storage, active, attempt)
        first = _plan(storage)
        candidate = first["candidates"][0]
        output_path = Path(str(candidate["output_dir"]))
        rag_admin_service.shutil.rmtree(output_path)
        output_path.write_text("not a directory", encoding="utf-8")

        second = _plan(storage)

        assert str(candidate["publication_id"]) in _reason_ids(second, "skipped", "unsafe_path")
        assert first["plan_fingerprint"] != second["plan_fingerprint"]
    finally:
        storage.close()


def test_dry_run_refuses_a_missing_database_without_creating_any_path(tmp_path: Path) -> None:
    missing_db = tmp_path / "missing-parent" / "index.db"

    with pytest.raises(ValueError, match="existing database"):
        plan_ready_data_publication_gc(db_path=str(missing_db), cutoff_at=CUTOFF)

    assert not missing_db.exists()
    assert not missing_db.parent.exists()


def test_dry_run_does_not_migrate_a_legacy_database(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE legacy_only (id INTEGER PRIMARY KEY)")
    connection.commit()
    before = connection.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
    connection.close()

    with pytest.raises((sqlite3.OperationalError, ValueError)):
        plan_ready_data_publication_gc(db_path=str(db_path), cutoff_at=CUTOFF)

    check = sqlite3.connect(db_path)
    try:
        after = check.execute("SELECT name, sql FROM sqlite_master ORDER BY name").fetchall()
    finally:
        check.close()
    assert after == before


def test_tree_walk_errors_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    def broken_walk(_path: Path, **kwargs):
        kwargs["onerror"](OSError("synthetic scandir failure"))
        return iter(())

    monkeypatch.setattr(rag_admin_service.os, "walk", broken_walk)
    with pytest.raises(OSError, match="synthetic scandir failure"):
        _ready_data_gc_tree_is_safe(candidate)


def test_minimum_age_is_required_even_outside_newest_two(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        attempts = [
            _record(storage, _candidate_dir(tmp_path, f"build-age-{index}")) for index in range(4)
        ]
        for attempt in attempts[:2]:
            _mark(storage, active, attempt, marked_at="2026-08-25T00:00:00+00:00")
        _mark(storage, active, attempts[2], marked_at=YOUNG_MARK)
        _mark(storage, active, attempts[3], marked_at="2026-08-18T00:00:00+00:00")

        plan = _plan(storage)

        assert str(attempts[2]["publication_id"]) in _reason_ids(
            plan, "retained", "minimum_age_not_met"
        )
        assert {str(item["publication_id"]) for item in plan["candidates"]} == {
            str(attempts[3]["publication_id"])
        }
    finally:
        storage.close()


def test_execute_deletes_candidate_and_keeps_audit_tombstone(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        attempts = [
            _record(storage, _candidate_dir(tmp_path, f"build-delete-{index}"))
            for index in range(3)
        ]
        for attempt in attempts:
            _mark(storage, active, attempt)
        plan = _plan(storage)
        doomed = plan["candidates"][0]

        result = execute_ready_data_publication_gc(
            db_path=storage.db_path,
            cutoff_at=CUTOFF,
            plan_fingerprint=str(plan["plan_fingerprint"]),
        )

        assert _reason_ids(result, "deleted", "deleted") == {doomed["publication_id"]}
        assert not Path(str(doomed["output_dir"])).exists()
        tombstone = storage.get_agentic_ready_publication(str(doomed["publication_id"]))
        assert tombstone is not None
        assert tombstone["gc_state"] == "deleted"
        assert tombstone["output_dir"] == ""
        assert tombstone["artifact_files"] == []
        before = dict(tombstone)
        assert (
            storage.mark_agentic_ready_publication_superseded_generation(
                str(doomed["publication_id"])
            )
            is False
        )
        assert storage.get_agentic_ready_publication(str(doomed["publication_id"])) == before
    finally:
        storage.close()


def test_delete_failure_is_recoverable_and_retry_is_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        attempts = [
            _record(storage, _candidate_dir(tmp_path, f"build-failure-{index}"))
            for index in range(3)
        ]
        for attempt in attempts:
            _mark(storage, active, attempt)
        first_plan = _plan(storage)
        doomed_id = str(first_plan["candidates"][0]["publication_id"])
        original_rmtree = rag_admin_service.shutil.rmtree

        def fail_delete(_path: Path) -> None:
            raise OSError("synthetic delete failure")

        monkeypatch.setattr(rag_admin_service.shutil, "rmtree", fail_delete)
        first = execute_ready_data_publication_gc(
            db_path=storage.db_path,
            cutoff_at=CUTOFF,
            plan_fingerprint=str(first_plan["plan_fingerprint"]),
        )
        failed = storage.get_agentic_ready_publication(doomed_id)
        assert _reason_ids(first, "failures", "delete_failed") == {doomed_id}
        assert failed is not None and failed["gc_state"] == "delete_failed"
        assert not Path(str(first_plan["candidates"][0]["output_dir"])).exists()
        assert Path(str(failed["gc_quarantine_dir"])).is_dir()
        with pytest.raises(AgenticRagError, match="not the current serving") as exc_info:
            _resolve_ready_output_dir(
                db_path=storage.db_path,
                payload={"output_dir": str(failed["gc_quarantine_dir"])},
            )
        assert exc_info.value.status_code == 409

        monkeypatch.setattr(rag_admin_service.shutil, "rmtree", original_rmtree)
        retry_plan = _plan(storage)
        retry = execute_ready_data_publication_gc(
            db_path=storage.db_path,
            cutoff_at=CUTOFF,
            plan_fingerprint=str(retry_plan["plan_fingerprint"]),
        )
        tombstone = storage.get_agentic_ready_publication(doomed_id)
        assert _reason_ids(retry, "deleted", "deleted") == {doomed_id}
        assert tombstone is not None and tombstone["gc_state"] == "deleted"
        assert not Path(str(failed["gc_quarantine_dir"])).exists()
    finally:
        storage.close()


def test_publication_that_wins_before_gc_claim_is_not_deleted(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        attempts = [
            _record(storage, _candidate_dir(tmp_path, f"build-race-{index}")) for index in range(3)
        ]
        for attempt in attempts:
            _mark(storage, active, attempt)
        plan = _plan(storage)
        winner_id = str(plan["candidates"][0]["publication_id"])
        storage.publish_agentic_ready_publication(
            winner_id,
            expected_active_publication_id=str(active["publication_id"]),
        )

        with pytest.raises(ValueError, match="fingerprint"):
            execute_ready_data_publication_gc(
                db_path=storage.db_path,
                cutoff_at=CUTOFF,
                plan_fingerprint=str(plan["plan_fingerprint"]),
            )

        assert Path(str(plan["candidates"][0]["output_dir"])).is_dir()
        assert (
            storage.get_agentic_ready_publication_state(kb_id="kb-ready", profile="general")[
                "active_publication_id"
            ]
            == winner_id
        )
    finally:
        storage.close()


def test_gc_claim_that_wins_causes_publish_to_reject(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        attempts = [
            _record(storage, _candidate_dir(tmp_path, f"build-claim-{index}")) for index in range(3)
        ]
        for attempt in attempts:
            _mark(storage, active, attempt)
        plan = _plan(storage)
        doomed = plan["candidates"][0]
        claim = storage.claim_agentic_ready_publication_gc(
            str(doomed["publication_id"]),
            expected_gc_state="eligible",
            expected_marked_at=str(doomed["marked_at"]),
            quarantine_dir=str(doomed["quarantine_dir"]),
        )
        assert claim is not None
        assert (
            storage.discard_agentic_ready_publication(
                str(doomed["publication_id"]),
                expected_active_publication_id=str(active["publication_id"]),
            )
            is False
        )

        with pytest.raises(ValueError, match="garbage collection"):
            storage.publish_agentic_ready_publication(
                str(doomed["publication_id"]),
                expected_active_publication_id=str(active["publication_id"]),
            )
    finally:
        storage.close()


def test_serving_output_path_alias_is_protected_by_plan_and_claim(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        alias = _record(storage, _candidate_dir(tmp_path, "build-historical-alias"))
        protected = [
            _record(storage, _candidate_dir(tmp_path, f"build-alias-new-{index}"))
            for index in range(2)
        ]
        storage._conn.execute(
            "UPDATE agentic_ready_publications SET output_dir = ? WHERE publication_id = ?",
            (active["output_dir"], alias["publication_id"]),
        )
        storage._conn.execute(
            """
            INSERT INTO agentic_ready_publication_gc (
                publication_id, retention_class, state, marked_at,
                last_error, updated_at
            ) VALUES (?, 'redundant_duplicate', 'eligible', ?, '', ?)
            """,
            (alias["publication_id"], OLD_MARK, OLD_MARK),
        )
        storage._conn.commit()
        for attempt in protected:
            _mark(storage, active, attempt, marked_at=YOUNG_MARK)

        plan = _plan(storage)

        assert str(alias["publication_id"]) in _reason_ids(plan, "retained", "serving_output_path")
        claim = storage.claim_agentic_ready_publication_gc(
            str(alias["publication_id"]),
            expected_gc_state="eligible",
            expected_marked_at=OLD_MARK,
            quarantine_dir=str(
                Path(str(alias["output_dir"])).parent / f'.gc-quarantine-{alias["publication_id"]}'
            ),
            cutoff_at=CUTOFF,
            minimum_age_days=14,
            keep_latest=2,
        )
        assert claim is None
        assert Path(str(active["output_dir"])).is_dir()
    finally:
        storage.close()


@pytest.mark.parametrize(
    ("reservation_kind", "serving_is_ancestor", "expected_reason"),
    [
        ("active", False, "serving_output_path"),
        ("active", True, "serving_output_path"),
        ("legacy", False, "reserved_output_path"),
        ("manifest", False, "serving_output_path"),
        ("manifest", True, "serving_output_path"),
        ("failed_unknown", False, "reserved_output_path"),
        ("failed_unknown", True, "reserved_output_path"),
    ],
)
def test_nested_reserved_paths_are_never_recursive_gc_candidates(
    tmp_path: Path,
    reservation_kind: str,
    serving_is_ancestor: bool,
    expected_reason: str,
) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        attempts = [
            _record(storage, _candidate_dir(tmp_path, f"build-nested-{index}"))
            for index in range(3)
        ]
        for attempt in attempts:
            _mark(storage, active, attempt)
        initial = _plan(storage)
        doomed = initial["candidates"][0]
        doomed_path = Path(str(doomed["output_dir"]))
        reserved_path = doomed_path.parent if serving_is_ancestor else doomed_path / "reserved"
        reserved_path.mkdir(parents=True, exist_ok=True)

        if reservation_kind == "active":
            storage._conn.execute(
                "UPDATE agentic_ready_publications SET output_dir = ? WHERE publication_id = ?",
                (str(reserved_path), active["publication_id"]),
            )
        elif reservation_kind == "legacy":
            legacy_dir = _candidate_dir(tmp_path, "build-legacy-placeholder")
            legacy = storage.record_agentic_ready_publication(
                kb_id="kb-ready",
                index_version_id=None,
                source_version_kind="legacy_manifest",
                source_version_id="legacy:nested",
                profile="general",
                profile_version="1",
                status="validated",
                output_dir=str(legacy_dir),
                artifact_files=[],
                artifact_digest="legacy-nested-digest",
                source_db=storage.db_path,
            )
            storage._conn.execute(
                "UPDATE agentic_ready_publications SET output_dir = ? WHERE publication_id = ?",
                (str(reserved_path), legacy["publication_id"]),
            )
        elif reservation_kind == "manifest":
            storage._conn.execute(
                "UPDATE agentic_ready_manifests SET output_dir = ? WHERE publication_id = ?",
                (str(reserved_path), active["publication_id"]),
            )
        else:
            failed_dir = _candidate_dir(tmp_path, "build-failed-placeholder")
            failed = storage.record_agentic_ready_publication(
                kb_id="kb-ready",
                index_version_id="idx-failed-history",
                source_version_kind="index",
                source_version_id="idx-failed-history",
                profile="general",
                profile_version="1",
                status="failed",
                output_dir=str(failed_dir),
                artifact_files=[],
                artifact_digest="failed-history-digest",
                source_db=storage.db_path,
            )
            storage._conn.execute(
                "UPDATE agentic_ready_publications SET output_dir = ? WHERE publication_id = ?",
                (str(reserved_path), failed["publication_id"]),
            )
        storage._conn.commit()

        plan = _plan(storage)

        publication_id = str(doomed["publication_id"])
        assert publication_id not in {str(item["publication_id"]) for item in plan["candidates"]}
        assert publication_id in _reason_ids(plan, "retained", expected_reason)
        assert doomed_path.is_dir()
        assert reserved_path.is_dir()
    finally:
        storage.close()


def test_claim_rechecks_newest_two_after_a_concurrent_publication(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        attempts = [
            _record(storage, _candidate_dir(tmp_path, f"build-cohort-{index}"))
            for index in range(3)
        ]
        for attempt in attempts:
            _mark(storage, active, attempt)
        plan = _plan(storage)
        doomed = plan["candidates"][0]
        newest = max(attempts, key=lambda item: str(item["publication_id"]))
        storage.publish_agentic_ready_publication(
            str(newest["publication_id"]),
            expected_active_publication_id=str(active["publication_id"]),
        )

        claim = storage.claim_agentic_ready_publication_gc(
            str(doomed["publication_id"]),
            expected_gc_state="eligible",
            expected_marked_at=str(doomed["marked_at"]),
            quarantine_dir=str(doomed["quarantine_dir"]),
            cutoff_at=CUTOFF,
            minimum_age_days=14,
            keep_latest=2,
        )

        assert claim is None
        assert Path(str(doomed["output_dir"])).is_dir()
    finally:
        storage.close()


def test_claimed_path_cannot_be_reused_or_published_before_delete(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        attempts = [
            _record(storage, _candidate_dir(tmp_path, f"build-path-race-{index}"))
            for index in range(3)
        ]
        for attempt in attempts:
            _mark(storage, active, attempt)
        other = _record(storage, _candidate_dir(tmp_path, "build-path-race-other"), digest="other")
        plan = _plan(storage)
        doomed = plan["candidates"][0]
        claim = storage.claim_agentic_ready_publication_gc(
            str(doomed["publication_id"]),
            expected_gc_state="eligible",
            expected_marked_at=str(doomed["marked_at"]),
            quarantine_dir=str(doomed["quarantine_dir"]),
            cutoff_at=CUTOFF,
        )
        assert claim is not None

        with pytest.raises(ValueError, match="path is already reserved"):
            _record(storage, Path(str(doomed["output_dir"])), digest="late")

        storage._conn.execute(
            "UPDATE agentic_ready_publications SET output_dir = ? WHERE publication_id = ?",
            (doomed["output_dir"], other["publication_id"]),
        )
        storage._conn.commit()
        with pytest.raises(ValueError, match="path is already reserved"):
            storage.publish_agentic_ready_publication(
                str(other["publication_id"]),
                expected_active_publication_id=str(active["publication_id"]),
            )
        assert Path(str(doomed["output_dir"])).is_dir()
    finally:
        storage.close()


def test_concurrent_publish_and_gc_claim_have_exactly_one_winner(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    active = _active(storage, tmp_path)
    attempts = [
        _record(storage, _candidate_dir(tmp_path, f"build-concurrent-{index}"))
        for index in range(3)
    ]
    for attempt in attempts:
        _mark(storage, active, attempt)
    plan = _plan(storage)
    candidate = plan["candidates"][0]
    db_path = storage.db_path
    storage.close()
    barrier = threading.Barrier(2)

    def publish() -> str:
        connection = Storage(db_path)
        try:
            barrier.wait(timeout=5)
            connection.publish_agentic_ready_publication(
                str(candidate["publication_id"]),
                expected_active_publication_id=str(active["publication_id"]),
            )
            return "published"
        except ValueError as exc:
            assert "garbage collection" in str(exc)
            return "publish_rejected"
        finally:
            connection.close()

    def claim() -> str:
        connection = Storage(db_path)
        try:
            barrier.wait(timeout=5)
            result = connection.claim_agentic_ready_publication_gc(
                str(candidate["publication_id"]),
                expected_gc_state="eligible",
                expected_marked_at=str(candidate["marked_at"]),
                quarantine_dir=str(candidate["quarantine_dir"]),
            )
            return "claimed" if result else "claim_lost"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        publish_result = pool.submit(publish)
        claim_result = pool.submit(claim)
        outcomes = {publish_result.result(timeout=10), claim_result.result(timeout=10)}

    check = Storage(db_path)
    try:
        publication = check.get_agentic_ready_publication(str(candidate["publication_id"]))
        state = check.get_agentic_ready_publication_state(kb_id="kb-ready", profile="general")
        if "published" in outcomes:
            assert outcomes == {"published", "claim_lost"}
            assert state["active_publication_id"] == candidate["publication_id"]
            assert publication is not None and publication["gc_state"] == ""
        else:
            assert outcomes == {"publish_rejected", "claimed"}
            assert state["active_publication_id"] == active["publication_id"]
            assert publication is not None and publication["gc_state"] == "claimed"
        assert Path(str(candidate["output_dir"])).is_dir()
    finally:
        check.close()


def test_expired_claim_recovery_lease_has_only_one_new_owner(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    active = _active(storage, tmp_path)
    attempts = [
        _record(storage, _candidate_dir(tmp_path, f"build-recovery-owner-{index}"))
        for index in range(3)
    ]
    for attempt in attempts:
        _mark(storage, active, attempt)
    plan = _plan(storage)
    candidate = plan["candidates"][0]
    first_claim = storage.claim_agentic_ready_publication_gc(
        str(candidate["publication_id"]),
        expected_gc_state="eligible",
        expected_marked_at=str(candidate["marked_at"]),
        quarantine_dir=str(candidate["quarantine_dir"]),
        cutoff_at=CUTOFF,
    )
    assert first_claim is not None
    storage._conn.execute(
        """
        UPDATE agentic_ready_publication_gc
        SET lease_expires_at = '2000-01-01T00:00:00+00:00'
        WHERE publication_id = ?
        """,
        (candidate["publication_id"],),
    )
    storage._conn.commit()
    old_token = str(first_claim["gc_claim_token"])
    db_path = storage.db_path
    storage.close()
    barrier = threading.Barrier(2)

    def resume() -> str:
        connection = Storage(db_path)
        try:
            barrier.wait(timeout=5)
            claim = connection.claim_agentic_ready_publication_gc(
                str(candidate["publication_id"]),
                expected_gc_state="claimed",
                expected_marked_at=str(candidate["marked_at"]),
                quarantine_dir=str(candidate["quarantine_dir"]),
                cutoff_at=CUTOFF,
                expected_claim_token=old_token,
            )
            return str(claim["gc_claim_token"]) if claim else "lost"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [
            future.result(timeout=10) for future in (pool.submit(resume), pool.submit(resume))
        ]

    assert outcomes.count("lost") == 1
    assert sum(outcome.startswith("argc_") for outcome in outcomes) == 1
    assert old_token not in outcomes


def test_claim_lease_membership_is_bound_to_the_canonical_cutoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        attempts = [
            _record(storage, _candidate_dir(tmp_path, f"build-lease-cutoff-{index}"))
            for index in range(3)
        ]
        for attempt in attempts:
            _mark(storage, active, attempt)
        plan = _plan(storage)
        candidate = plan["candidates"][0]
        claim = storage.claim_agentic_ready_publication_gc(
            str(candidate["publication_id"]),
            expected_gc_state="eligible",
            expected_marked_at=str(candidate["marked_at"]),
            quarantine_dir=str(candidate["quarantine_dir"]),
            cutoff_at=CUTOFF,
            claim_lease_seconds=1,
        )
        assert claim is not None
        lease_expires_at = str(claim["gc_lease_expires_at"])
        before_lease = Storage._parse_iso_to_utc(lease_expires_at)
        assert before_lease is not None
        fixed_cutoff = (before_lease - rag_admin_service.timedelta(seconds=1)).isoformat()

        first = _plan(storage, cutoff_at=fixed_cutoff)
        time.sleep(1.1)
        second = _plan(storage, cutoff_at=fixed_cutoff)

        publication_id = str(candidate["publication_id"])
        assert publication_id in _reason_ids(first, "skipped", "claim_in_progress")
        assert publication_id in _reason_ids(second, "skipped", "claim_in_progress")
        assert first["plan_fingerprint"] == second["plan_fingerprint"]
    finally:
        storage.close()


def test_slow_delete_keeps_claim_fenced_past_lease_expiry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _open_storage(tmp_path)
    active = _active(storage, tmp_path)
    attempts = [
        _record(storage, _candidate_dir(tmp_path, f"build-slow-delete-{index}"))
        for index in range(3)
    ]
    for attempt in attempts:
        _mark(storage, active, attempt)
    monkeypatch.setattr(rag_admin_service, "READY_DATA_GC_CLAIM_LEASE_SECONDS", 1)
    plan = _plan(storage)
    candidate = plan["candidates"][0]
    db_path = storage.db_path
    storage.close()

    claim_seen = threading.Event()
    delete_entered = threading.Event()
    allow_delete = threading.Event()
    first_claim_token: list[str] = []
    original_claim = Storage.claim_agentic_ready_publication_gc
    original_rmtree = rag_admin_service.shutil.rmtree

    def recording_claim(self: Storage, *args, **kwargs):
        claimed = original_claim(self, *args, **kwargs)
        if claimed is not None and not first_claim_token:
            first_claim_token.append(str(claimed["gc_claim_token"]))
            claim_seen.set()
        return claimed

    def slow_rmtree(path: str | Path, *args, **kwargs) -> None:
        delete_entered.set()
        assert allow_delete.wait(timeout=10)
        original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(Storage, "claim_agentic_ready_publication_gc", recording_claim)
    monkeypatch.setattr(rag_admin_service.shutil, "rmtree", slow_rmtree)

    with ThreadPoolExecutor(max_workers=3) as pool:
        execute_future = pool.submit(
            execute_ready_data_publication_gc,
            db_path=db_path,
            cutoff_at=CUTOFF,
            plan_fingerprint=str(plan["plan_fingerprint"]),
        )
        assert claim_seen.wait(timeout=5)
        assert delete_entered.wait(timeout=5)
        time.sleep(1.1)

        def steal_claim() -> dict[str, object] | None:
            connection = Storage(db_path)
            try:
                return connection.claim_agentic_ready_publication_gc(
                    str(candidate["publication_id"]),
                    expected_gc_state="claimed",
                    expected_marked_at=str(candidate["marked_at"]),
                    quarantine_dir=str(candidate["quarantine_dir"]),
                    cutoff_at=CUTOFF,
                    claim_lease_seconds=1,
                    expected_claim_token=first_claim_token[0],
                )
            finally:
                connection.close()

        steal_future = pool.submit(steal_claim)

        def publish_candidate() -> str:
            connection = Storage(db_path)
            try:
                connection.publish_agentic_ready_publication(
                    str(candidate["publication_id"]),
                    expected_active_publication_id=str(active["publication_id"]),
                )
            except ValueError as exc:
                assert "garbage collection" in str(exc)
                return "rejected"
            finally:
                connection.close()
            return "published"

        publish_future = pool.submit(publish_candidate)
        time.sleep(0.2)
        assert not steal_future.done()
        assert not publish_future.done()
        allow_delete.set()
        result = execute_future.result(timeout=10)
        stolen = steal_future.result(timeout=10)
        published = publish_future.result(timeout=10)

    assert stolen is None
    assert published == "rejected"
    assert _reason_ids(result, "deleted", "deleted") == {candidate["publication_id"]}


@pytest.mark.parametrize("crash_stage", ["after_rename", "after_delete"])
def test_transaction_rollback_recovers_crash_during_filesystem_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_stage: str,
) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        attempts = [
            _record(storage, _candidate_dir(tmp_path, f"build-transaction-crash-{index}"))
            for index in range(3)
        ]
        for attempt in attempts:
            _mark(storage, active, attempt)
        plan = _plan(storage)
        candidate = plan["candidates"][0]

        with monkeypatch.context() as patcher:
            if crash_stage == "after_rename":
                patcher.setattr(
                    rag_admin_service.shutil,
                    "rmtree",
                    lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
                )
            else:
                original_finish = Storage.finish_agentic_ready_publication_gc

                def crash_before_tombstone(self: Storage, *args, **kwargs):
                    if kwargs.get("deleted") is True:
                        raise KeyboardInterrupt
                    return original_finish(self, *args, **kwargs)

                patcher.setattr(
                    Storage,
                    "finish_agentic_ready_publication_gc",
                    crash_before_tombstone,
                )
            with pytest.raises(KeyboardInterrupt):
                execute_ready_data_publication_gc(
                    db_path=storage.db_path,
                    cutoff_at=CUTOFF,
                    plan_fingerprint=str(plan["plan_fingerprint"]),
                )

        retry_plan = _plan(storage)
        result = execute_ready_data_publication_gc(
            db_path=storage.db_path,
            cutoff_at=CUTOFF,
            plan_fingerprint=str(retry_plan["plan_fingerprint"]),
        )

        assert _reason_ids(result, "deleted", "deleted") == {str(candidate["publication_id"])}
        tombstone = storage.get_agentic_ready_publication(str(candidate["publication_id"]))
        assert tombstone is not None and tombstone["gc_state"] == "deleted"
    finally:
        storage.close()


def test_escape_link_and_non_staging_paths_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        outside = tmp_path / "outside" / "build-escape"
        outside.mkdir(parents=True)
        (outside / "keep.txt").write_text("keep", encoding="utf-8")
        escaped = _record(storage, outside)
        _mark(storage, active, escaped)

        linked = _record(storage, _candidate_dir(tmp_path, "build-link-sentinel"))
        _mark(storage, active, linked)
        protected = [
            _record(storage, _candidate_dir(tmp_path, f"build-path-protected-{index}"))
            for index in range(2)
        ]
        for attempt in protected:
            _mark(storage, active, attempt, marked_at=YOUNG_MARK)
        linked_path = Path(str(linked["output_dir"]))
        original_link_check = rag_admin_service._is_link_or_reparse
        monkeypatch.setattr(
            rag_admin_service,
            "_is_link_or_reparse",
            lambda path: path == linked_path or original_link_check(path),
        )

        plan = _plan(storage)

        skipped = {str(item["publication_id"]): str(item["reason"]) for item in plan["skipped"]}
        assert skipped[str(escaped["publication_id"])] == "unsafe_path"
        assert skipped[str(linked["publication_id"])] == "unsafe_path"
        assert (outside / "keep.txt").read_text(encoding="utf-8") == "keep"
    finally:
        storage.close()


def test_real_symlink_tree_entry_is_skipped_without_touching_target(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        attempts = [
            _record(storage, _candidate_dir(tmp_path, f"build-symlink-{index}"))
            for index in range(3)
        ]
        for attempt in attempts:
            _mark(storage, active, attempt)
        oldest_id = sorted(str(item["publication_id"]) for item in attempts)[0]
        oldest = next(item for item in attempts if item["publication_id"] == oldest_id)
        outside = tmp_path / "symlink-target.txt"
        outside.write_text("keep", encoding="utf-8")
        try:
            (Path(str(oldest["output_dir"])) / "escape-link").symlink_to(outside)
        except OSError as exc:
            pytest.skip(f"file symlink unavailable: {exc}")

        plan = _plan(storage)

        assert str(oldest["publication_id"]) in _reason_ids(plan, "skipped", "unsafe_path")
        assert outside.read_text(encoding="utf-8") == "keep"
    finally:
        storage.close()


def test_repeated_plan_and_execute_are_idempotent(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        attempts = [
            _record(storage, _candidate_dir(tmp_path, f"build-idempotent-{index}"))
            for index in range(3)
        ]
        for attempt in attempts:
            _mark(storage, active, attempt)
        first_plan = _plan(storage)
        first = execute_ready_data_publication_gc(
            db_path=storage.db_path,
            cutoff_at=CUTOFF,
            plan_fingerprint=str(first_plan["plan_fingerprint"]),
        )
        second_plan = _plan(storage)
        second = execute_ready_data_publication_gc(
            db_path=storage.db_path,
            cutoff_at=CUTOFF,
            plan_fingerprint=str(second_plan["plan_fingerprint"]),
        )

        assert len(first["deleted"]) == 1
        assert second["deleted"] == []
        assert second["failures"] == []
        assert second["candidates"] == []
    finally:
        storage.close()


def test_execute_requires_an_explicit_plan_fingerprint(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        with pytest.raises(ValueError, match="fingerprint is required"):
            execute_ready_data_publication_gc(
                db_path=storage.db_path,
                cutoff_at=CUTOFF,
                plan_fingerprint="",
            )
    finally:
        storage.close()


def test_legacy_ready_data_is_never_a_gc_candidate(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        legacy_dir = tmp_path / "agentic_ready_data" / "legacy-serving"
        legacy_dir.mkdir(parents=True)
        legacy = storage.record_agentic_ready_publication(
            kb_id="kb-ready",
            index_version_id=None,
            source_version_kind="legacy_manifest",
            source_version_id="legacy:manifest",
            profile="general",
            profile_version="1",
            status="validated",
            output_dir=str(legacy_dir),
            artifact_files=[],
            artifact_digest="legacy-digest",
            source_db=storage.db_path,
        )
        plan = _plan(storage)

        assert str(legacy["publication_id"]) in _reason_ids(plan, "retained", "legacy_publication")
        assert legacy_dir.is_dir()
    finally:
        storage.close()


@pytest.mark.parametrize(
    ("drift", "expected_message"),
    [
        ("candidate", "fingerprint"),
        ("slot", "fingerprint"),
        ("cutoff", "fingerprint"),
        ("policy", "policy"),
    ],
)
def test_execute_rejects_plan_candidate_slot_cutoff_or_policy_drift(
    tmp_path: Path,
    drift: str,
    expected_message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        attempts = [
            _record(storage, _candidate_dir(tmp_path, f"build-drift-{index}")) for index in range(3)
        ]
        for attempt in attempts:
            _mark(storage, active, attempt)
        plan = _plan(storage)
        cutoff = CUTOFF
        if drift == "candidate":
            storage._conn.execute(
                "UPDATE agentic_ready_publication_gc SET marked_at = ? WHERE publication_id = ?",
                ("2026-07-31T00:00:00+00:00", plan["candidates"][0]["publication_id"]),
            )
            storage._conn.commit()
        elif drift == "slot":
            storage._conn.execute(
                "UPDATE agentic_ready_slots SET updated_at = ? WHERE kb_id = 'kb-ready'",
                ("2099-01-01T00:00:00+00:00",),
            )
            storage._conn.commit()
        elif drift == "cutoff":
            cutoff = "2026-09-02T00:00:00+00:00"
        else:
            monkeypatch.setattr(
                rag_admin_service,
                "READY_DATA_GC_POLICY_VERSION",
                "ready-data-retention-gc.v999",
            )

        with pytest.raises(ValueError, match=expected_message):
            execute_ready_data_publication_gc(
                db_path=storage.db_path,
                cutoff_at=cutoff,
                plan_fingerprint=str(plan["plan_fingerprint"]),
                policy_version=(
                    READY_DATA_GC_POLICY_VERSION if drift != "policy" else "unsupported-policy"
                ),
            )
    finally:
        storage.close()


def test_claimed_quarantine_from_interrupted_run_converges_on_retry(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        attempts = [
            _record(storage, _candidate_dir(tmp_path, f"build-crash-{index}")) for index in range(3)
        ]
        for attempt in attempts:
            _mark(storage, active, attempt)
        plan = _plan(storage)
        doomed = plan["candidates"][0]
        claim = storage.claim_agentic_ready_publication_gc(
            str(doomed["publication_id"]),
            expected_gc_state="eligible",
            expected_marked_at=str(doomed["marked_at"]),
            quarantine_dir=str(doomed["quarantine_dir"]),
        )
        assert claim is not None
        os.replace(str(doomed["output_dir"]), str(doomed["quarantine_dir"]))

        lease_expires_at = Storage._parse_iso_to_utc(claim["gc_lease_expires_at"])
        assert lease_expires_at is not None
        in_progress_plan = _plan(
            storage,
            cutoff_at=(lease_expires_at - rag_admin_service.timedelta(seconds=1)).isoformat(),
        )
        assert str(doomed["publication_id"]) in _reason_ids(
            in_progress_plan, "skipped", "claim_in_progress"
        )
        storage._conn.execute(
            """
            UPDATE agentic_ready_publication_gc
            SET lease_expires_at = '2000-01-01T00:00:00+00:00'
            WHERE publication_id = ?
            """,
            (doomed["publication_id"],),
        )
        storage._conn.commit()

        retry_plan = _plan(storage)
        result = execute_ready_data_publication_gc(
            db_path=storage.db_path,
            cutoff_at=CUTOFF,
            plan_fingerprint=str(retry_plan["plan_fingerprint"]),
        )

        assert _reason_ids(result, "deleted", "deleted") == {doomed["publication_id"]}
        tombstone = storage.get_agentic_ready_publication(str(doomed["publication_id"]))
        assert tombstone is not None and tombstone["gc_state"] == "deleted"
    finally:
        storage.close()


def test_deleted_quarantine_before_tombstone_converges_on_retry(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _active(storage, tmp_path)
        attempts = [
            _record(storage, _candidate_dir(tmp_path, f"build-finalize-crash-{index}"))
            for index in range(3)
        ]
        for attempt in attempts:
            _mark(storage, active, attempt)
        plan = _plan(storage)
        doomed = plan["candidates"][0]
        claim = storage.claim_agentic_ready_publication_gc(
            str(doomed["publication_id"]),
            expected_gc_state="eligible",
            expected_marked_at=str(doomed["marked_at"]),
            quarantine_dir=str(doomed["quarantine_dir"]),
        )
        assert claim is not None
        os.replace(str(doomed["output_dir"]), str(doomed["quarantine_dir"]))
        rag_admin_service.shutil.rmtree(str(doomed["quarantine_dir"]))
        storage._conn.execute(
            """
            UPDATE agentic_ready_publication_gc
            SET lease_expires_at = '2000-01-01T00:00:00+00:00'
            WHERE publication_id = ?
            """,
            (doomed["publication_id"],),
        )
        storage._conn.commit()

        retry_plan = _plan(storage)
        result = execute_ready_data_publication_gc(
            db_path=storage.db_path,
            cutoff_at=CUTOFF,
            plan_fingerprint=str(retry_plan["plan_fingerprint"]),
        )

        assert _reason_ids(result, "deleted", "deleted") == {doomed["publication_id"]}
        tombstone = storage.get_agentic_ready_publication(str(doomed["publication_id"]))
        assert tombstone is not None and tombstone["gc_state"] == "deleted"
    finally:
        storage.close()
