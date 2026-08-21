from __future__ import annotations

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest

from ai_actuarial.storage import Storage
from ai_actuarial.sqlite_schema import CURRENT_SQLITE_SCHEMA_VERSION
from ai_actuarial.api.services.rag_admin import (
    _ready_data_artifact_digest,
    _remove_unreferenced_staging_dir,
)


def _open_storage(tmp_path: Path) -> Storage:
    db_path = tmp_path / "index.db"
    storage = Storage(str(db_path))
    storage._conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rag_knowledge_bases (
            kb_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            kb_mode TEXT DEFAULT 'category',
            chunk_profile_id TEXT,
            manifest_profile TEXT DEFAULT 'general',
            embedding_provider TEXT DEFAULT 'openai',
            embedding_model TEXT NOT NULL,
            embedding_dimension INTEGER,
            chunk_size INTEGER NOT NULL,
            chunk_overlap INTEGER NOT NULL,
            index_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            file_count INTEGER DEFAULT 0,
            chunk_count INTEGER DEFAULT 0,
            index_dirty_at TEXT
        )
        """
    )
    storage._conn.executemany(
        """
        INSERT OR IGNORE INTO rag_knowledge_bases (
            kb_id, name, embedding_model, chunk_size, chunk_overlap,
            index_type, created_at, updated_at
        )
        VALUES (?, ?, 'text-embedding-3-large', 800, 120, 'faiss', ?, ?)
        """,
        [
            ("kb-ready", "Ready KB", "2026-08-18T00:00:00Z", "2026-08-18T00:00:00Z"),
            ("kb-other", "Other KB", "2026-08-18T00:00:00Z", "2026-08-18T00:00:00Z"),
        ],
    )
    storage._conn.commit()
    return storage


def _record(
    storage: Storage,
    *,
    index_version_id: str,
    artifact_digest: str,
    output_dir: str,
    status: str = "validated",
    kb_id: str = "kb-ready",
    profile: str = "general",
) -> dict[str, object]:
    return storage.record_agentic_ready_publication(
        kb_id=kb_id,
        index_version_id=index_version_id,
        source_version_kind="index",
        source_version_id=index_version_id,
        profile=profile,
        profile_version="1",
        status=status,
        output_dir=output_dir,
        artifact_files=["doc_catalog.jsonl", "sections.jsonl", "ready_data_manifest.json"],
        doc_count=4,
        section_count=12,
        built_at="2026-08-18T12:00:00+00:00",
        artifact_digest=artifact_digest,
        source_db=storage.db_path,
        schema_versions={"ready_data": "1"},
        error_message="validation failed" if status == "failed" else "",
    )


@pytest.mark.parametrize("read_only", [False, True])
def test_publication_column_capability_is_checked_once_per_storage_instance(
    tmp_path: Path,
    read_only: bool,
) -> None:
    storage = _open_storage(tmp_path)
    first = _record(
        storage,
        index_version_id="idx-1",
        artifact_digest="digest-1",
        output_dir=str(tmp_path / "staging" / "first"),
    )
    _record(
        storage,
        index_version_id="idx-2",
        artifact_digest="digest-2",
        output_dir=str(tmp_path / "staging" / "second"),
    )
    db_path = storage.db_path
    storage.close()

    reopened = Storage.open_read_only(db_path) if read_only else Storage(db_path)
    statements: list[str] = []
    reopened._conn.set_trace_callback(statements.append)
    try:
        publications = reopened.list_agentic_ready_publications_for_gc()
        assert len(publications) == 2
        assert reopened.get_agentic_ready_publication(
            str(first["publication_id"])
        ) is not None
        capability_checks = [
            statement
            for statement in statements
            if statement.strip().lower()
            == "pragma table_info(agentic_ready_publications)"
        ]
        assert len(capability_checks) == 1
    finally:
        reopened.close()


def test_failed_staging_record_does_not_replace_active_publication(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        first = _record(
            storage,
            index_version_id="idx-1",
            artifact_digest="digest-1",
            output_dir=str(tmp_path / "staging" / "first"),
        )
        storage.publish_agentic_ready_publication(
            str(first["publication_id"]),
            expected_active_publication_id=None,
        )

        failed = _record(
            storage,
            index_version_id="idx-2",
            artifact_digest="digest-failed",
            output_dir=str(tmp_path / "staging" / "failed"),
            status="failed",
        )

        state = storage.get_agentic_ready_publication_state(kb_id="kb-ready", profile="general")
        serving = storage.get_agentic_ready_manifest(kb_id="kb-ready", profile="general")
        assert failed["status"] == "failed"
        assert state["active_publication_id"] == first["publication_id"]
        assert state["previous_publication_id"] is None
        assert state["automatic_publish_enabled"] is False
        assert serving is not None
        assert serving["publication_id"] == first["publication_id"]
        assert serving["status"] == "ready"
    finally:
        storage.close()


def test_publish_retains_previous_validated_slot_and_rollback_swaps_slots(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        initial = storage.get_agentic_ready_publication_state(
            kb_id="kb-ready",
            profile="general",
        )
        assert initial["publication_revision"] == 0
        first = _record(
            storage,
            index_version_id="idx-1",
            artifact_digest="digest-1",
            output_dir=str(tmp_path / "staging" / "first"),
        )
        first_published = storage.publish_agentic_ready_publication(
            str(first["publication_id"]),
            expected_active_publication_id=None,
        )
        assert first_published["publication_revision"] == 1
        second = _record(
            storage,
            index_version_id="idx-2",
            artifact_digest="digest-2",
            output_dir=str(tmp_path / "staging" / "second"),
        )

        published = storage.publish_agentic_ready_publication(
            str(second["publication_id"]),
            expected_active_publication_id=str(first["publication_id"]),
        )
        serving = storage.get_agentic_ready_manifest(kb_id="kb-ready", profile="general")
        assert published["active_publication_id"] == second["publication_id"]
        assert published["previous_publication_id"] == first["publication_id"]
        assert published["publication_revision"] == 2
        assert serving is not None
        assert serving["publication_id"] == second["publication_id"]
        assert serving["index_version_id"] == "idx-2"
        assert serving["profile"] == "general"
        assert serving["built_at"] == "2026-08-18T12:00:00+00:00"
        assert serving["artifact_digest"] == "digest-2"
        assert serving["status"] == "ready"

        with pytest.raises(ValueError, match="explicitly validated"):
            storage.rollback_agentic_ready_publication(
                kb_id="kb-ready",
                profile="general",
                expected_active_publication_id=str(second["publication_id"]),
                expected_previous_publication_id=str(first["publication_id"]),
                validated_previous_publication_id="",
            )
        rolled_back = storage.rollback_agentic_ready_publication(
            kb_id="kb-ready",
            profile="general",
            expected_active_publication_id=str(second["publication_id"]),
            expected_previous_publication_id=str(first["publication_id"]),
            validated_previous_publication_id=str(first["publication_id"]),
        )
        serving = storage.get_agentic_ready_manifest(kb_id="kb-ready", profile="general")
        assert rolled_back["active_publication_id"] == first["publication_id"]
        assert rolled_back["previous_publication_id"] == second["publication_id"]
        assert rolled_back["publication_revision"] == 3
        assert serving is not None
        assert serving["publication_id"] == first["publication_id"]
        assert serving["index_version_id"] == "idx-1"
        assert serving["artifact_digest"] == "digest-1"
    finally:
        storage.close()


@pytest.mark.parametrize(
    "corruption",
    (
        "dangling_active",
        "active_not_active",
        "active_wrong_profile",
        "previous_wrong_kb",
        "previous_wrong_profile",
    ),
)
def test_rollback_fail_closes_invalid_slot_publication_invariants(
    tmp_path: Path,
    corruption: str,
) -> None:
    storage = _open_storage(tmp_path)
    try:
        previous = _record(
            storage,
            index_version_id="idx-previous",
            artifact_digest="digest-previous",
            output_dir=str(tmp_path / "staging" / "previous"),
        )
        storage.publish_agentic_ready_publication(
            str(previous["publication_id"]),
            expected_active_publication_id=None,
        )
        active = _record(
            storage,
            index_version_id="idx-active",
            artifact_digest="digest-active",
            output_dir=str(tmp_path / "staging" / "active"),
        )
        storage.publish_agentic_ready_publication(
            str(active["publication_id"]),
            expected_active_publication_id=str(previous["publication_id"]),
        )

        expected_active = str(active["publication_id"])
        expected_previous = str(previous["publication_id"])
        if corruption == "dangling_active":
            expected_active = "pub_missing_active"
            storage._conn.execute("PRAGMA foreign_keys = OFF")
            storage._conn.execute(
                "UPDATE agentic_ready_slots SET active_publication_id = ? "
                "WHERE kb_id = ? AND profile = ?",
                (expected_active, "kb-ready", "general"),
            )
            storage._conn.commit()
            storage._conn.execute("PRAGMA foreign_keys = ON")
        else:
            with storage.transaction(immediate=True):
                if corruption == "active_not_active":
                    storage._conn.execute(
                        "UPDATE agentic_ready_publications SET status = 'validated' "
                        "WHERE publication_id = ?",
                        (expected_active,),
                    )
                elif corruption == "active_wrong_profile":
                    storage._conn.execute(
                        "UPDATE agentic_ready_publications SET profile = ? "
                        "WHERE publication_id = ?",
                        ("special", expected_active),
                    )
                elif corruption == "previous_wrong_kb":
                    storage._conn.execute(
                        "UPDATE agentic_ready_publications SET kb_id = ? "
                        "WHERE publication_id = ?",
                        ("kb-other", expected_previous),
                    )
                else:
                    storage._conn.execute(
                        "UPDATE agentic_ready_publications SET profile = ? "
                        "WHERE publication_id = ?",
                        ("special", expected_previous),
                    )

        slots_before = storage._conn.execute(
            "SELECT active_publication_id, previous_publication_id FROM agentic_ready_slots "
            "WHERE kb_id = ? AND profile = ?",
            ("kb-ready", "general"),
        ).fetchone()
        publications_before = storage._conn.execute(
            "SELECT publication_id, kb_id, profile, status FROM agentic_ready_publications "
            "ORDER BY publication_id"
        ).fetchall()
        manifest_before = storage.get_agentic_ready_manifest(
            kb_id="kb-ready",
            profile="general",
        )

        with pytest.raises(ValueError, match="publication"):
            storage.rollback_agentic_ready_publication(
                kb_id="kb-ready",
                profile="general",
                expected_active_publication_id=expected_active,
                expected_previous_publication_id=expected_previous,
                validated_previous_publication_id=expected_previous,
                validate_previous_publication=lambda _candidate: True,
            )

        assert storage._conn.execute(
            "SELECT active_publication_id, previous_publication_id FROM agentic_ready_slots "
            "WHERE kb_id = ? AND profile = ?",
            ("kb-ready", "general"),
        ).fetchone() == slots_before
        assert storage._conn.execute(
            "SELECT publication_id, kb_id, profile, status FROM agentic_ready_publications "
            "ORDER BY publication_id"
        ).fetchall() == publications_before
        assert storage.get_agentic_ready_manifest(
            kb_id="kb-ready",
            profile="general",
        ) == manifest_before
    finally:
        storage.close()


def test_publication_revision_changes_only_with_committed_pointer_swaps(
    tmp_path: Path,
    monkeypatch,
) -> None:
    storage = _open_storage(tmp_path)
    try:
        first = _record(
            storage,
            index_version_id="idx-revision-1",
            artifact_digest="digest-revision-1",
            output_dir=str(tmp_path / "staging" / "revision-first"),
        )
        first_state = storage.publish_agentic_ready_publication(
            str(first["publication_id"]),
            expected_active_publication_id=None,
        )
        assert first_state["publication_revision"] == 1

        idempotent = storage.publish_agentic_ready_publication(
            str(first["publication_id"]),
            expected_active_publication_id=str(first["publication_id"]),
        )
        assert idempotent["idempotent"] is True
        assert idempotent["publication_revision"] == 1

        second = _record(
            storage,
            index_version_id="idx-revision-2",
            artifact_digest="digest-revision-2",
            output_dir=str(tmp_path / "staging" / "revision-second"),
        )
        cas_lost = storage.publish_agentic_ready_publication(
            str(second["publication_id"]),
            expected_active_publication_id="arp-stale-client",
        )
        assert cas_lost["cas_won"] is False
        assert cas_lost["publication_revision"] == 1

        second_state = storage.publish_agentic_ready_publication(
            str(second["publication_id"]),
            expected_active_publication_id=str(first["publication_id"]),
        )
        assert second_state["publication_revision"] == 2

        with pytest.raises(ValueError, match="integrity validation"):
            storage.rollback_agentic_ready_publication(
                kb_id="kb-ready",
                profile="general",
                expected_active_publication_id=str(second["publication_id"]),
                expected_previous_publication_id=str(first["publication_id"]),
                validated_previous_publication_id=str(first["publication_id"]),
                validate_previous_publication=lambda _publication: False,
            )
        assert storage.get_agentic_ready_publication_state(
            kb_id="kb-ready",
            profile="general",
        )["publication_revision"] == 2

        def fail_serving_manifest(_publication: dict[str, object]) -> None:
            raise RuntimeError("injected rollback manifest failure")

        monkeypatch.setattr(
            storage,
            "_publish_agentic_ready_manifest_row",
            fail_serving_manifest,
        )
        with pytest.raises(RuntimeError, match="rollback manifest failure"):
            storage.rollback_agentic_ready_publication(
                kb_id="kb-ready",
                profile="general",
                expected_active_publication_id=str(second["publication_id"]),
                expected_previous_publication_id=str(first["publication_id"]),
                validated_previous_publication_id=str(first["publication_id"]),
            )
        unchanged = storage.get_agentic_ready_publication_state(
            kb_id="kb-ready",
            profile="general",
        )
        assert unchanged["active_publication_id"] == second["publication_id"]
        assert unchanged["previous_publication_id"] == first["publication_id"]
        assert unchanged["publication_revision"] == 2
    finally:
        storage.close()


def test_rollback_expected_slots_cas_rejects_stale_validated_previous(
    tmp_path: Path,
) -> None:
    storage = _open_storage(tmp_path)
    try:
        first = _record(
            storage,
            index_version_id="idx-1",
            artifact_digest="digest-1",
            output_dir=str(tmp_path / "staging" / "first"),
        )
        storage.publish_agentic_ready_publication(
            str(first["publication_id"]),
            expected_active_publication_id=None,
        )
        second = _record(
            storage,
            index_version_id="idx-2",
            artifact_digest="digest-2",
            output_dir=str(tmp_path / "staging" / "second"),
        )
        storage.publish_agentic_ready_publication(
            str(second["publication_id"]),
            expected_active_publication_id=str(first["publication_id"]),
        )
        third = _record(
            storage,
            index_version_id="idx-3",
            artifact_digest="digest-3",
            output_dir=str(tmp_path / "staging" / "third"),
        )
        storage.publish_agentic_ready_publication(
            str(third["publication_id"]),
            expected_active_publication_id=str(second["publication_id"]),
        )

        stale = storage.rollback_agentic_ready_publication(
            kb_id="kb-ready",
            profile="general",
            expected_active_publication_id=str(second["publication_id"]),
            expected_previous_publication_id=str(first["publication_id"]),
            validated_previous_publication_id=str(first["publication_id"]),
        )

        assert stale["cas_won"] is False
        assert stale["rolled_back"] is False
        assert stale["active_publication_id"] == third["publication_id"]
        assert stale["previous_publication_id"] == second["publication_id"]
        serving = storage.get_agentic_ready_manifest(kb_id="kb-ready", profile="general")
        assert serving is not None
        assert serving["publication_id"] == third["publication_id"]
    finally:
        storage.close()


def test_publication_identity_creates_independent_attempts_for_same_source_and_digest(
    tmp_path: Path,
) -> None:
    storage = _open_storage(tmp_path)
    try:
        original = _record(
            storage,
            index_version_id="idx-1",
            artifact_digest="digest-1",
            output_dir=str(tmp_path / "staging" / "original"),
        )
        duplicate = _record(
            storage,
            index_version_id="idx-1",
            artifact_digest="digest-1",
            output_dir=str(tmp_path / "staging" / "duplicate"),
        )
        assert duplicate["publication_id"] != original["publication_id"]
        assert duplicate["output_dir"] != original["output_dir"]

        first_publish = storage.publish_agentic_ready_publication(
            str(original["publication_id"]),
            expected_active_publication_id=None,
        )
        repeated_publish = storage.publish_agentic_ready_publication(
            str(original["publication_id"]),
            expected_active_publication_id=str(original["publication_id"]),
        )
        assert repeated_publish["active_publication_id"] == first_publish["active_publication_id"]
        assert repeated_publish["previous_publication_id"] is None
        assert repeated_publish["idempotent"] is True
    finally:
        storage.close()


def test_publish_rejects_reactivating_previous_publication(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        first = _record(
            storage,
            index_version_id="idx-1",
            artifact_digest="digest-1",
            output_dir=str(tmp_path / "staging" / "first"),
        )
        storage.publish_agentic_ready_publication(
            str(first["publication_id"]),
            expected_active_publication_id=None,
        )
        second = _record(
            storage,
            index_version_id="idx-2",
            artifact_digest="digest-2",
            output_dir=str(tmp_path / "staging" / "second"),
        )
        storage.publish_agentic_ready_publication(
            str(second["publication_id"]),
            expected_active_publication_id=str(first["publication_id"]),
        )
        state_before = storage.get_agentic_ready_publication_state(
            kb_id="kb-ready",
            profile="general",
        )
        serving_before = storage.get_agentic_ready_manifest(kb_id="kb-ready", profile="general")

        with pytest.raises(ValueError, match="validated"):
            storage.publish_agentic_ready_publication(
                str(first["publication_id"]),
                expected_active_publication_id=str(second["publication_id"]),
            )

        state_after = storage.get_agentic_ready_publication_state(
            kb_id="kb-ready",
            profile="general",
        )
        serving_after = storage.get_agentic_ready_manifest(kb_id="kb-ready", profile="general")
        assert state_after == state_before
        assert serving_after == serving_before
    finally:
        storage.close()


def test_publish_rechecks_candidate_status_after_write_lock(
    tmp_path: Path,
    monkeypatch,
) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _record(
            storage,
            index_version_id="idx-active",
            artifact_digest="digest-active",
            output_dir=str(tmp_path / "staging" / "active"),
        )
        storage.publish_agentic_ready_publication(
            str(active["publication_id"]),
            expected_active_publication_id=None,
        )
        candidate = _record(
            storage,
            index_version_id="idx-candidate",
            artifact_digest="digest-candidate",
            output_dir=str(tmp_path / "staging" / "candidate"),
        )
        state_before = storage.get_agentic_ready_publication_state(
            kb_id="kb-ready",
            profile="general",
        )
        serving_before = storage.get_agentic_ready_manifest(kb_id="kb-ready", profile="general")
        original_transaction = storage.transaction
        failed_before_lock = False

        @contextmanager
        def transaction_after_candidate_failure():
            nonlocal failed_before_lock
            if not failed_before_lock:
                storage._conn.execute(
                    "UPDATE agentic_ready_publications SET status = 'failed' WHERE publication_id = ?",
                    (candidate["publication_id"],),
                )
                storage._conn.commit()
                failed_before_lock = True
            with original_transaction():
                yield

        monkeypatch.setattr(storage, "transaction", transaction_after_candidate_failure)

        with pytest.raises(ValueError, match="validated"):
            storage.publish_agentic_ready_publication(
                str(candidate["publication_id"]),
                expected_active_publication_id=str(active["publication_id"]),
            )

        state_after = storage.get_agentic_ready_publication_state(
            kb_id="kb-ready",
            profile="general",
        )
        serving_after = storage.get_agentic_ready_manifest(kb_id="kb-ready", profile="general")
        candidate_after = storage.get_agentic_ready_publication(str(candidate["publication_id"]))
        assert failed_before_lock is True
        assert state_after == state_before
        assert serving_after == serving_before
        assert candidate_after is not None and candidate_after["status"] == "failed"
    finally:
        storage.close()


def test_validated_retry_preserves_failed_attempt_and_uses_new_publication_id(
    tmp_path: Path,
) -> None:
    storage = _open_storage(tmp_path)
    try:
        failed = _record(
            storage,
            index_version_id="idx-retry",
            artifact_digest="digest-retry",
            output_dir=str(tmp_path / "staging" / "retry"),
            status="failed",
        )
        validated = _record(
            storage,
            index_version_id="idx-retry",
            artifact_digest="digest-retry",
            output_dir=str(tmp_path / "staging" / "retry-validated"),
            status="validated",
        )
        assert validated["publication_id"] != failed["publication_id"]
        assert validated["status"] == "validated"
        assert validated["validated_at"]
        failed_after = storage.get_agentic_ready_publication(str(failed["publication_id"]))
        assert failed_after is not None and failed_after["status"] == "failed"

        published = storage.publish_agentic_ready_publication(
            str(validated["publication_id"]),
            expected_active_publication_id=None,
        )
        assert published["active_publication_id"] == validated["publication_id"]
    finally:
        storage.close()


def test_discard_duplicate_requires_the_same_expected_active(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        active = _record(
            storage,
            index_version_id="idx-dedupe",
            artifact_digest="digest-dedupe",
            output_dir=str(tmp_path / "staging" / "active"),
        )
        storage.publish_agentic_ready_publication(
            str(active["publication_id"]),
            expected_active_publication_id=None,
        )
        duplicate = _record(
            storage,
            index_version_id="idx-dedupe",
            artifact_digest="digest-dedupe",
            output_dir=str(tmp_path / "staging" / "duplicate"),
        )

        assert storage.discard_agentic_ready_publication(
            str(duplicate["publication_id"]),
            expected_active_publication_id="arp-concurrent-winner",
        ) is False
        assert storage.get_agentic_ready_publication(str(duplicate["publication_id"])) is not None
        assert storage.discard_agentic_ready_publication(
            str(duplicate["publication_id"]),
            expected_active_publication_id=str(active["publication_id"]),
        ) is True
        assert storage.get_agentic_ready_publication(str(duplicate["publication_id"])) is None
    finally:
        storage.close()


def test_publish_failure_rolls_back_slots_statuses_and_serving_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    storage = _open_storage(tmp_path)
    try:
        first = _record(
            storage,
            index_version_id="idx-1",
            artifact_digest="digest-1",
            output_dir=str(tmp_path / "staging" / "first"),
        )
        storage.publish_agentic_ready_publication(
            str(first["publication_id"]),
            expected_active_publication_id=None,
        )
        second = _record(
            storage,
            index_version_id="idx-2",
            artifact_digest="digest-2",
            output_dir=str(tmp_path / "staging" / "second"),
        )
        serving_before = storage.get_agentic_ready_manifest(kb_id="kb-ready", profile="general")

        def fail_serving_manifest(_publication: dict[str, object]) -> None:
            raise RuntimeError("injected serving-manifest write failure")

        monkeypatch.setattr(storage, "_publish_agentic_ready_manifest_row", fail_serving_manifest)
        with pytest.raises(RuntimeError, match="injected serving-manifest"):
            storage.publish_agentic_ready_publication(
                str(second["publication_id"]),
                expected_active_publication_id=str(first["publication_id"]),
            )

        state = storage.get_agentic_ready_publication_state(kb_id="kb-ready", profile="general")
        serving_after = storage.get_agentic_ready_manifest(kb_id="kb-ready", profile="general")
        first_after = storage.get_agentic_ready_publication(str(first["publication_id"]))
        second_after = storage.get_agentic_ready_publication(str(second["publication_id"]))
        assert state["active_publication_id"] == first["publication_id"]
        assert state["previous_publication_id"] is None
        assert first_after is not None and first_after["status"] == "active"
        assert second_after is not None and second_after["status"] == "validated"
        assert serving_after == serving_before
    finally:
        storage.close()


def test_publication_attempts_are_independent_across_storage_connections(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    db_path = storage.db_path
    storage.close()
    barrier = threading.Barrier(2)

    def record_from_connection(output_name: str) -> str:
        connection = Storage(db_path)
        try:
            barrier.wait(timeout=5)
            publication = _record(
                connection,
                index_version_id="idx-concurrent",
                artifact_digest="digest-concurrent",
                output_dir=str(tmp_path / "staging" / output_name),
            )
            return str(publication["publication_id"])
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        publication_ids = list(pool.map(record_from_connection, ("first", "second")))

    assert publication_ids[0] != publication_ids[1]
    check = Storage(db_path)
    try:
        count = check._conn.execute(
            "SELECT COUNT(*) FROM agentic_ready_publications WHERE kb_id = ?",
            ("kb-ready",),
        ).fetchone()[0]
        assert count == 2
    finally:
        check.close()


def test_publish_cas_allows_only_one_concurrent_winner(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    first = _record(
        storage,
        index_version_id="idx-cas",
        artifact_digest="digest-cas",
        output_dir=str(tmp_path / "staging" / "cas-first"),
    )
    second = _record(
        storage,
        index_version_id="idx-cas",
        artifact_digest="digest-cas",
        output_dir=str(tmp_path / "staging" / "cas-second"),
    )
    db_path = storage.db_path
    storage.close()
    barrier = threading.Barrier(2)

    def publish(publication_id: str) -> dict[str, object]:
        connection = Storage(db_path)
        try:
            barrier.wait(timeout=5)
            return connection.publish_agentic_ready_publication(
                publication_id,
                expected_active_publication_id=None,
            )
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                publish,
                (str(first["publication_id"]), str(second["publication_id"])),
            )
        )

    assert sum(bool(result["cas_won"]) for result in results) == 1
    check = Storage(db_path)
    try:
        state = check.get_agentic_ready_publication_state(kb_id="kb-ready", profile="general")
        assert state["active_publication_id"] in {
            first["publication_id"],
            second["publication_id"],
        }
        assert state["previous_publication_id"] is None
        loser_id = (
            second["publication_id"]
            if state["active_publication_id"] == first["publication_id"]
            else first["publication_id"]
        )
        loser = check.get_agentic_ready_publication(str(loser_id))
        assert loser is not None and loser["status"] == "validated"
    finally:
        check.close()


def test_corrupt_expected_active_is_atomically_excluded_from_previous(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    try:
        corrupt = _record(
            storage,
            index_version_id="idx-corrupt",
            artifact_digest="digest-same",
            output_dir=str(tmp_path / "staging" / "corrupt"),
        )
        storage.publish_agentic_ready_publication(
            str(corrupt["publication_id"]),
            expected_active_publication_id=None,
        )
        replacement = _record(
            storage,
            index_version_id="idx-corrupt",
            artifact_digest="digest-same",
            output_dir=str(tmp_path / "staging" / "replacement"),
        )

        state = storage.publish_agentic_ready_publication(
            str(replacement["publication_id"]),
            expected_active_publication_id=str(corrupt["publication_id"]),
            preserve_expected_active_as_previous=False,
            invalidated_expected_active_error="digest mismatch",
        )

        corrupt_after = storage.get_agentic_ready_publication(str(corrupt["publication_id"]))
        assert state["cas_won"] is True
        assert state["active_publication_id"] == replacement["publication_id"]
        assert state["previous_publication_id"] is None
        assert corrupt_after is not None
        assert corrupt_after["status"] == "failed"
        assert corrupt_after["error_message"] == "digest mismatch"
    finally:
        storage.close()


def test_storage_rejects_legacy_draft_identity_schema_without_mutating(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "index.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE rag_knowledge_bases (
            kb_id TEXT PRIMARY KEY,
            embedding_model TEXT NOT NULL DEFAULT 'text-embedding-3-large'
        );
        INSERT INTO rag_knowledge_bases (kb_id) VALUES ('kb-ready');
        CREATE TABLE agentic_ready_publications (
            publication_id TEXT PRIMARY KEY,
            kb_id TEXT NOT NULL,
            index_version_id TEXT,
            source_version_kind TEXT NOT NULL,
            source_version_id TEXT NOT NULL,
            profile TEXT NOT NULL,
            profile_version TEXT NOT NULL,
            status TEXT NOT NULL,
            output_dir TEXT NOT NULL,
            artifact_files_json TEXT NOT NULL DEFAULT '[]',
            doc_count INTEGER NOT NULL DEFAULT 0,
            section_count INTEGER NOT NULL DEFAULT 0,
            built_at TEXT,
            artifact_digest TEXT NOT NULL,
            source_db TEXT,
            schema_versions_json TEXT NOT NULL DEFAULT '{}',
            error_message TEXT,
            validated_at TEXT,
            published_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(kb_id, source_version_kind, source_version_id, profile, artifact_digest)
        );
        CREATE TABLE agentic_ready_slots (
            kb_id TEXT NOT NULL,
            profile TEXT NOT NULL,
            active_publication_id TEXT,
            previous_publication_id TEXT,
            automatic_publish_enabled INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(kb_id, profile),
            FOREIGN KEY(active_publication_id) REFERENCES agentic_ready_publications(publication_id),
            FOREIGN KEY(previous_publication_id) REFERENCES agentic_ready_publications(publication_id)
        );
        INSERT INTO agentic_ready_publications (
            publication_id, kb_id, index_version_id, source_version_kind,
            source_version_id, profile, profile_version, status, output_dir,
            artifact_files_json, doc_count, section_count, built_at,
            artifact_digest, source_db, schema_versions_json, error_message,
            validated_at, published_at, created_at, updated_at
        ) VALUES
            ('arp-active', 'kb-ready', 'idx-active', 'index', 'idx-active',
             'general', '1', 'active', 'active', '[]', 1, 1, NULL,
             'digest-active', '', '{}', '', '2026-08-18', '2026-08-18',
             '2026-08-18', '2026-08-18'),
            ('arp-previous', 'kb-ready', 'idx-previous', 'index', 'idx-previous',
             'general', '1', 'previous', 'previous', '[]', 1, 1, NULL,
             'digest-previous', '', '{}', '', '2026-08-17', '2026-08-17',
             '2026-08-17', '2026-08-17');
        INSERT INTO agentic_ready_slots (
            kb_id, profile, active_publication_id, previous_publication_id, updated_at
        ) VALUES ('kb-ready', 'general', 'arp-active', 'arp-previous', '2026-08-18');
        """
    )
    conn.execute(f"PRAGMA user_version={CURRENT_SQLITE_SCHEMA_VERSION}")
    conn.commit()
    conn.close()

    before_rows = sqlite3.connect(db_path)
    try:
        before_schema = {
            str(row[1])
            for row in before_rows.execute(
                "PRAGMA table_info(agentic_ready_slots)"
            ).fetchall()
        }
        slot_pointer = before_rows.execute(
            """
            SELECT active_publication_id, previous_publication_id
            FROM agentic_ready_slots
            """
        ).fetchone()
    finally:
        before_rows.close()

    with pytest.raises(RuntimeError, match="schema preflight"):
        Storage(str(db_path))

    check = sqlite3.connect(db_path)
    try:
        after_schema = {
            str(row[1])
            for row in check.execute("PRAGMA table_info(agentic_ready_slots)").fetchall()
        }
        assert after_schema == before_schema
        assert "publication_revision" not in after_schema
        assert check.execute(
            """
            SELECT active_publication_id, previous_publication_id
            FROM agentic_ready_slots
            """
        ).fetchone() == slot_pointer
        assert check.execute(
            "SELECT 1 FROM sqlite_schema WHERE name = ?",
            ("agentic_ready_publications_attempts_new",),
        ).fetchone() is None
    finally:
        check.close()


def test_storage_rejects_dangling_draft_slots_without_committing_migration(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "index.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE rag_knowledge_bases (
            kb_id TEXT PRIMARY KEY,
            embedding_model TEXT NOT NULL DEFAULT 'text-embedding-3-large'
        );
        INSERT INTO rag_knowledge_bases (kb_id) VALUES ('kb-ready');
        CREATE TABLE agentic_ready_publications (
            publication_id TEXT PRIMARY KEY,
            kb_id TEXT NOT NULL,
            index_version_id TEXT,
            source_version_kind TEXT NOT NULL,
            source_version_id TEXT NOT NULL,
            profile TEXT NOT NULL,
            profile_version TEXT NOT NULL,
            status TEXT NOT NULL,
            output_dir TEXT NOT NULL,
            artifact_files_json TEXT NOT NULL DEFAULT '[]',
            doc_count INTEGER NOT NULL DEFAULT 0,
            section_count INTEGER NOT NULL DEFAULT 0,
            built_at TEXT,
            artifact_digest TEXT NOT NULL,
            source_db TEXT,
            schema_versions_json TEXT NOT NULL DEFAULT '{}',
            error_message TEXT,
            validated_at TEXT,
            published_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(kb_id, source_version_kind, source_version_id, profile, artifact_digest)
        );
        CREATE TABLE agentic_ready_slots (
            kb_id TEXT NOT NULL,
            profile TEXT NOT NULL,
            active_publication_id TEXT,
            previous_publication_id TEXT,
            automatic_publish_enabled INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(kb_id, profile),
            FOREIGN KEY(active_publication_id) REFERENCES agentic_ready_publications(publication_id),
            FOREIGN KEY(previous_publication_id) REFERENCES agentic_ready_publications(publication_id)
        );
        INSERT INTO agentic_ready_slots (
            kb_id, profile, active_publication_id, previous_publication_id, updated_at
        ) VALUES ('kb-ready', 'general', 'arp-missing', NULL, '2026-08-18');
        """
    )
    conn.execute(f"PRAGMA user_version={CURRENT_SQLITE_SCHEMA_VERSION}")
    conn.commit()
    conn.close()

    for _attempt in range(2):
        with pytest.raises(
            RuntimeError,
            match="schema preflight",
        ):
            Storage(str(db_path))

        check = sqlite3.connect(db_path)
        try:
            indexes = check.execute(
                "PRAGMA index_list(agentic_ready_publications)"
            ).fetchall()
            unique_column_sets = [
                {
                    str(column[2])
                    for column in check.execute(
                        f"PRAGMA index_info({json.dumps(str(index[1]))})"
                    ).fetchall()
                }
                for index in indexes
                if bool(index[2])
            ]
            assert {
                "kb_id",
                "source_version_kind",
                "source_version_id",
                "profile",
                "artifact_digest",
            } in unique_column_sets
            assert check.execute(
                "SELECT active_publication_id FROM agentic_ready_slots"
            ).fetchone() == ("arp-missing",)
            assert check.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                ("agentic_ready_publications_attempts_new",),
            ).fetchone() is None
        finally:
            check.close()


def test_artifact_digest_ignores_restore_specific_manifest_paths(tmp_path: Path) -> None:
    artifact_files = ["doc_catalog.jsonl", "ready_data_manifest.json"]
    digests: list[str] = []
    for name in ("original", "restored"):
        output_dir = tmp_path / name
        output_dir.mkdir()
        (output_dir / "doc_catalog.jsonl").write_text('{"doc_id":"a"}\n', encoding="utf-8")
        (output_dir / "ready_data_manifest.json").write_text(
            json.dumps(
                {
                    "artifact_files": artifact_files,
                    "built_at": name,
                    "output_dir": str(output_dir),
                    "source_db": str(tmp_path / name / "index.db"),
                }
            ),
            encoding="utf-8",
        )
        digests.append(_ready_data_artifact_digest(str(output_dir), artifact_files))

    assert digests[0] == digests[1]


def test_cleanup_rejects_symlink_candidate_without_deleting_outside_sentinel(tmp_path: Path) -> None:
    storage = _open_storage(tmp_path)
    staging_root = tmp_path / "agentic_ready_data" / "staging"
    staging_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    candidate = staging_root / "build-link"
    try:
        candidate.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        storage.close()
        pytest.skip(f"directory symlink unavailable: {exc}")
    try:
        with pytest.raises(ValueError, match="link|reparse"):
            _remove_unreferenced_staging_dir(
                storage,
                output_dir=str(candidate),
                staging_root=str(staging_root),
                allowed_output_root=str(tmp_path / "agentic_ready_data"),
            )
        assert sentinel.read_text(encoding="utf-8") == "keep"
        assert outside.is_dir()
    finally:
        storage.close()
