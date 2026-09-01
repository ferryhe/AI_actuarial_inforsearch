from __future__ import annotations

from pathlib import Path

import pytest

from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.storage import Storage


def _create_kb(storage: Storage, kb_id: str) -> None:
    KnowledgeBaseManager(storage).create_kb(
        kb_id=kb_id,
        name=f"Binding events {kb_id}",
        kb_mode="manual",
        manifest_profile="general",
    )


def _create_file(
    storage: Storage,
    tmp_path: Path,
    file_url: str,
    *,
    catalog_status: str = "ok",
) -> None:
    suffix = file_url.rsplit("/", 1)[-1]
    storage.insert_file(
        url=file_url,
        sha256=f"sha-{suffix}",
        title=suffix,
        source_site="example.com",
        source_page_url="https://example.com",
        original_filename=suffix,
        local_path=str(tmp_path / suffix),
        bytes=100,
        content_type="application/pdf",
    )
    storage.upsert_catalog_item(
        item={
            "url": file_url,
            "sha256": f"sha-{suffix}",
            "keywords": ["binding"],
            "summary": f"Summary for {suffix}",
            "category": "Binding",
        },
        pipeline_version="v1",
        status=catalog_status,
    )


def _add_membership(storage: Storage, *, kb_id: str, file_url: str) -> None:
    storage._conn.execute(
        "INSERT INTO rag_kb_files(kb_id, file_url, added_at) VALUES (?, ?, ?)",
        (kb_id, file_url, "2026-08-19T00:00:00+00:00"),
    )
    storage._conn.commit()


def _create_profile(storage: Storage, name: str = "binding-events-profile") -> str:
    profile = storage.create_chunk_profile(
        name=name,
        chunk_size=256,
        chunk_overlap=32,
    )
    return str(profile["profile_id"])


def _create_chunk_set(
    storage: Storage,
    *,
    file_url: str,
    profile_id: str,
    version: str,
) -> str:
    chunk_set = storage.get_or_create_file_chunk_set(
        file_url=file_url,
        profile_id=profile_id,
        markdown_hash=f"hash-{version}",
        status="ready",
    )
    chunk_set_id = str(chunk_set["chunk_set_id"])
    storage._conn.execute(
        """
        INSERT INTO global_chunks (
            chunk_id, chunk_set_id, chunk_index, content, token_count,
            section_hierarchy, content_hash, created_at
        )
        VALUES (?, ?, 0, ?, 3, 'Root', NULL, ?)
        """,
        (
            f"{chunk_set_id}:0",
            chunk_set_id,
            f"Chunk content {version}",
            "2026-08-19T00:00:00+00:00",
        ),
    )
    storage._conn.execute(
        """
        UPDATE file_chunk_sets
        SET chunk_count = 1, status = 'ready', updated_at = ?
        WHERE chunk_set_id = ?
        """,
        ("2026-08-19T00:00:00+00:00", chunk_set_id),
    )
    storage._conn.commit()
    return chunk_set_id


def _insert_binding(
    storage: Storage,
    *,
    kb_id: str,
    file_url: str,
    chunk_set_id: str,
    binding_mode: str = "follow_latest",
    target_profile_id: str | None = None,
    bound_by: str = "seed",
) -> None:
    storage._conn.execute(
        """
        INSERT INTO kb_chunk_bindings (
            kb_id, file_url, chunk_set_id, bound_at, bound_by,
            binding_mode, target_profile_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            kb_id,
            file_url,
            chunk_set_id,
            "2026-08-19T00:00:00+00:00",
            bound_by,
            binding_mode,
            target_profile_id,
        ),
    )
    storage._conn.commit()


def _evaluate_pending(storage: Storage, *, kb_id: str) -> None:
    state = storage.get_agentic_ready_source_state(kb_id=kb_id, profile="general")
    storage.record_agentic_ready_source_evaluation(
        kb_id=kb_id,
        profile="general",
        evaluated_generation=int(state["event_generation"]),
        source_version_kind="catalog_chunks_snapshot",
        source_version_id=f"snapshot-{state['event_generation']}",
    )


def _seed_publication_pointers(storage: Storage, *, kb_id: str) -> None:
    now = "2026-08-19T00:00:00+00:00"
    for publication_id, status in (
        ("pub-previous", "validated"),
        ("pub-active", "active"),
    ):
        storage._conn.execute(
            """
            INSERT INTO agentic_ready_publications (
                publication_id, kb_id, source_version_kind, source_version_id,
                profile, profile_version, status, output_dir, artifact_digest,
                created_at, updated_at
            )
            VALUES (?, ?, 'catalog_chunks_snapshot', ?, 'general', '1', ?, ?, ?, ?, ?)
            """,
            (
                publication_id,
                kb_id,
                f"source-{publication_id}",
                status,
                str(Path(storage.db_path).parent / publication_id),
                f"digest-{publication_id}",
                now,
                now,
            ),
        )
    storage._conn.execute(
        """
        INSERT INTO agentic_ready_slots (
            kb_id, profile, active_publication_id, previous_publication_id,
            automatic_build_enabled, automatic_publish_enabled, updated_at
        )
        VALUES (?, 'general', 'pub-active', 'pub-previous', 0, 0, ?)
        """,
        (kb_id, now),
    )
    storage._conn.commit()


def test_first_valid_binding_marks_hard_stale_without_moving_publication_pointers(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "first-binding.db"))
    try:
        kb_id = "kb-first-binding"
        file_url = "https://example.com/first.pdf"
        _create_kb(storage, kb_id)
        _create_file(storage, tmp_path, file_url)
        _add_membership(storage, kb_id=kb_id, file_url=file_url)
        profile_id = _create_profile(storage)
        chunk_set_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version="first",
        )
        _seed_publication_pointers(storage, kb_id=kb_id)
        before = storage.get_agentic_ready_publication_state(kb_id=kb_id, profile="general")

        result = storage.bind_chunk_set_to_kb(
            kb_id=kb_id,
            file_url=file_url,
            chunk_set_id=chunk_set_id,
            bound_by="test",
            binding_mode="follow_latest",
        )

        state = storage.get_agentic_ready_source_state(kb_id=kb_id, profile="general")
        after = storage.get_agentic_ready_publication_state(kb_id=kb_id, profile="general")
        assert result["created"] is True
        assert state["event_generation"] == 1
        assert state["pending_severity"] == "hard_stale"
        assert state["pending_reasons"] == ["access_scope_restricted"]
        assert state["serving_allowed"] is False
        assert after["active_publication_id"] == before["active_publication_id"]
        assert after["previous_publication_id"] == before["previous_publication_id"]
    finally:
        storage.close()


def test_additional_valid_binding_marks_soft_stale_once(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "additional-binding.db"))
    try:
        kb_id = "kb-additional-binding"
        _create_kb(storage, kb_id)
        profile_id = _create_profile(storage)
        chunk_sets: list[tuple[str, str]] = []
        for name in ("one", "two"):
            file_url = f"https://example.com/{name}.pdf"
            _create_file(storage, tmp_path, file_url)
            _add_membership(storage, kb_id=kb_id, file_url=file_url)
            chunk_sets.append(
                (
                    file_url,
                    _create_chunk_set(
                        storage,
                        file_url=file_url,
                        profile_id=profile_id,
                        version=name,
                    ),
                )
            )
        storage.bind_chunk_set_to_kb(
            kb_id=kb_id,
            file_url=chunk_sets[0][0],
            chunk_set_id=chunk_sets[0][1],
        )
        _evaluate_pending(storage, kb_id=kb_id)

        storage.bind_chunk_set_to_kb(
            kb_id=kb_id,
            file_url=chunk_sets[1][0],
            chunk_set_id=chunk_sets[1][1],
        )

        state = storage.get_agentic_ready_source_state(kb_id=kb_id, profile="general")
        assert state["event_generation"] == 2
        assert state["pending_evaluation_generation"] == 2
        assert state["pending_severity"] == "soft_stale"
        assert state["pending_reasons"] == ["chunk_binding_updated"]
        assert state["serving_allowed"] is True
    finally:
        storage.close()


def test_duplicate_and_metadata_only_binding_changes_do_not_advance_generation(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "binding-noop.db"))
    try:
        kb_id = "kb-binding-noop"
        file_url = "https://example.com/noop.pdf"
        _create_kb(storage, kb_id)
        _create_file(storage, tmp_path, file_url)
        _add_membership(storage, kb_id=kb_id, file_url=file_url)
        profile_id = _create_profile(storage)
        chunk_set_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version="noop",
        )
        storage.bind_chunk_set_to_kb(
            kb_id=kb_id,
            file_url=file_url,
            chunk_set_id=chunk_set_id,
            bound_by="original",
            binding_mode="pin",
        )
        before = storage.get_agentic_ready_source_state(kb_id=kb_id, profile="general")

        duplicate = storage.bind_chunk_set_to_kb(
            kb_id=kb_id,
            file_url=file_url,
            chunk_set_id=chunk_set_id,
            bound_by="original",
            binding_mode="pin",
        )
        metadata_only = storage.bind_chunk_set_to_kb(
            kb_id=kb_id,
            file_url=file_url,
            chunk_set_id=chunk_set_id,
            bound_by="different-actor",
            binding_mode="follow_latest",
        )

        after = storage.get_agentic_ready_source_state(kb_id=kb_id, profile="general")
        binding = storage._conn.execute(
            """
            SELECT binding_mode, target_profile_id
            FROM kb_chunk_bindings
            WHERE kb_id = ? AND file_url = ? AND chunk_set_id = ?
            """,
            (kb_id, file_url, chunk_set_id),
        ).fetchone()
        assert duplicate["created"] is False
        assert metadata_only["created"] is False
        assert after["event_generation"] == before["event_generation"]
        assert binding == ("follow_latest", profile_id)
    finally:
        storage.close()


@pytest.mark.parametrize(
    ("invalid_kind", "kb_exists", "has_membership", "catalog_status"),
    [
        ("missing_kb", False, False, "ok"),
        ("missing_membership", True, False, "ok"),
        ("catalog_not_ok", True, True, "error"),
    ],
)
def test_binding_outside_builder_input_does_not_advance_generation(
    tmp_path: Path,
    invalid_kind: str,
    kb_exists: bool,
    has_membership: bool,
    catalog_status: str,
) -> None:
    storage = Storage(str(tmp_path / f"invalid-binding-{invalid_kind}.db"))
    try:
        kb_id = f"kb-{invalid_kind}"
        file_url = f"https://example.com/{invalid_kind}.pdf"
        if kb_exists:
            _create_kb(storage, kb_id)
        _create_file(storage, tmp_path, file_url, catalog_status=catalog_status)
        if has_membership:
            _add_membership(storage, kb_id=kb_id, file_url=file_url)
        profile_id = _create_profile(storage, name=f"profile-{invalid_kind}")
        chunk_set_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version=invalid_kind,
        )

        result = storage.bind_chunk_set_to_kb(
            kb_id=kb_id,
            file_url=file_url,
            chunk_set_id=chunk_set_id,
        )

        state = storage.get_agentic_ready_source_state(kb_id=kb_id, profile="general")
        assert result["created"] is True
        assert state["event_generation"] == 0
        assert state["pending_reasons"] == []
    finally:
        storage.close()


def test_binding_parameter_validation_is_a_source_state_noop(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "binding-validation.db"))
    try:
        kb_id = "kb-binding-validation"
        file_url = "https://example.com/validation.pdf"
        _create_kb(storage, kb_id)
        _create_file(storage, tmp_path, file_url)
        _add_membership(storage, kb_id=kb_id, file_url=file_url)

        with pytest.raises(ValueError, match="binding_mode"):
            storage.bind_chunk_set_to_kb(
                kb_id=kb_id,
                file_url=file_url,
                chunk_set_id="missing",
                binding_mode="invalid",
            )

        state = storage.get_agentic_ready_source_state(kb_id=kb_id, profile="general")
        binding_count = storage._conn.execute(
            "SELECT COUNT(*) FROM kb_chunk_bindings WHERE kb_id = ?",
            (kb_id,),
        ).fetchone()[0]
        assert state["event_generation"] == 0
        assert binding_count == 0
    finally:
        storage.close()


def test_follow_latest_move_marks_one_soft_stale_event(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "follow-latest.db"))
    try:
        kb_id = "kb-follow-latest"
        file_url = "https://example.com/follow.pdf"
        _create_kb(storage, kb_id)
        _create_file(storage, tmp_path, file_url)
        _add_membership(storage, kb_id=kb_id, file_url=file_url)
        profile_id = _create_profile(storage)
        old_chunk_set_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version="old",
        )
        new_chunk_set_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version="new",
        )
        storage.bind_chunk_set_to_kb(
            kb_id=kb_id,
            file_url=file_url,
            chunk_set_id=old_chunk_set_id,
            binding_mode="follow_latest",
        )
        _evaluate_pending(storage, kb_id=kb_id)

        result = storage.sync_follow_latest_bindings_for_chunk_set(
            file_url=file_url,
            profile_id=profile_id,
            chunk_set_id=new_chunk_set_id,
        )

        state = storage.get_agentic_ready_source_state(kb_id=kb_id, profile="general")
        rows = storage._conn.execute(
            "SELECT chunk_set_id FROM kb_chunk_bindings WHERE kb_id = ?",
            (kb_id,),
        ).fetchall()
        assert result["synced_bindings"] == 1
        assert result["affected_kb_ids"] == [kb_id]
        assert rows == [(new_chunk_set_id,)]
        assert state["event_generation"] == 2
        assert state["pending_severity"] == "soft_stale"
        assert state["pending_reasons"] == ["chunk_binding_updated"]
    finally:
        storage.close()


def test_follow_latest_multiple_old_rows_mark_each_affected_kb_once(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "follow-latest-multiple.db"))
    try:
        kb_ids = ("kb-follow-one", "kb-follow-two")
        file_url = "https://example.com/follow-multiple.pdf"
        for kb_id in kb_ids:
            _create_kb(storage, kb_id)
        _create_kb(storage, "kb-unaffected")
        _create_file(storage, tmp_path, file_url)
        for kb_id in kb_ids:
            _add_membership(storage, kb_id=kb_id, file_url=file_url)
        profile_id = _create_profile(storage)
        old_chunk_set_ids = [
            _create_chunk_set(
                storage,
                file_url=file_url,
                profile_id=profile_id,
                version=f"old-{index}",
            )
            for index in range(2)
        ]
        new_chunk_set_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version="new",
        )
        for kb_id in kb_ids:
            for old_chunk_set_id in old_chunk_set_ids:
                _insert_binding(
                    storage,
                    kb_id=kb_id,
                    file_url=file_url,
                    chunk_set_id=old_chunk_set_id,
                    target_profile_id=profile_id,
                )

        result = storage.sync_follow_latest_bindings_for_chunk_set(
            file_url=file_url,
            profile_id=profile_id,
            chunk_set_id=new_chunk_set_id,
        )

        assert result["synced_bindings"] == 4
        assert result["affected_kb_ids"] == list(kb_ids)
        for kb_id in kb_ids:
            state = storage.get_agentic_ready_source_state(kb_id=kb_id, profile="general")
            assert state["event_generation"] == 1
            assert state["pending_severity"] == "soft_stale"
            assert state["pending_reasons"] == ["chunk_binding_updated"]
        unaffected = storage.get_agentic_ready_source_state(
            kb_id="kb-unaffected",
            profile="general",
        )
        assert unaffected["event_generation"] == 0
    finally:
        storage.close()


def test_bind_marker_failure_rolls_back_binding_and_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = Storage(str(tmp_path / "bind-marker-failure.db"))
    try:
        kb_id = "kb-bind-marker-failure"
        file_url = "https://example.com/bind-failure.pdf"
        _create_kb(storage, kb_id)
        _create_file(storage, tmp_path, file_url)
        _add_membership(storage, kb_id=kb_id, file_url=file_url)
        profile_id = _create_profile(storage)
        chunk_set_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version="failure",
        )
        original = storage.mark_agentic_ready_source_event_for_kb

        def fail_after_mark(**kwargs: str) -> list[dict[str, object]]:
            original(**kwargs)
            raise RuntimeError("source marker failed")

        monkeypatch.setattr(storage, "mark_agentic_ready_source_event_for_kb", fail_after_mark)

        with pytest.raises(RuntimeError, match="source marker failed"):
            storage.bind_chunk_set_to_kb(
                kb_id=kb_id,
                file_url=file_url,
                chunk_set_id=chunk_set_id,
            )

        binding_count = storage._conn.execute(
            "SELECT COUNT(*) FROM kb_chunk_bindings WHERE kb_id = ?",
            (kb_id,),
        ).fetchone()[0]
        state = storage.get_agentic_ready_source_state(kb_id=kb_id, profile="general")
        assert binding_count == 0
        assert state["event_generation"] == 0
    finally:
        storage.close()


@pytest.mark.parametrize("target_preexists", [False, True])
def test_follow_latest_marker_failure_rolls_back_insert_update_and_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_preexists: bool,
) -> None:
    storage = Storage(str(tmp_path / f"sync-marker-failure-{target_preexists}.db"))
    try:
        kb_id = "kb-sync-marker-failure"
        file_url = "https://example.com/sync-failure.pdf"
        _create_kb(storage, kb_id)
        _create_file(storage, tmp_path, file_url)
        _add_membership(storage, kb_id=kb_id, file_url=file_url)
        profile_id = _create_profile(storage)
        old_chunk_set_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version="old",
        )
        new_chunk_set_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version="new",
        )
        _insert_binding(
            storage,
            kb_id=kb_id,
            file_url=file_url,
            chunk_set_id=old_chunk_set_id,
            target_profile_id=profile_id,
            bound_by="old-binding",
        )
        if target_preexists:
            _insert_binding(
                storage,
                kb_id=kb_id,
                file_url=file_url,
                chunk_set_id=new_chunk_set_id,
                binding_mode="pin",
                target_profile_id=None,
                bound_by="target-before",
            )
        before_rows = storage._conn.execute(
            """
            SELECT chunk_set_id, bound_by, binding_mode, target_profile_id
            FROM kb_chunk_bindings
            WHERE kb_id = ?
            ORDER BY chunk_set_id
            """,
            (kb_id,),
        ).fetchall()
        original = storage.mark_agentic_ready_source_event_for_kb

        def fail_after_mark(**kwargs: str) -> list[dict[str, object]]:
            original(**kwargs)
            raise RuntimeError("source marker failed")

        monkeypatch.setattr(storage, "mark_agentic_ready_source_event_for_kb", fail_after_mark)

        with pytest.raises(RuntimeError, match="source marker failed"):
            storage.sync_follow_latest_bindings_for_chunk_set(
                file_url=file_url,
                profile_id=profile_id,
                chunk_set_id=new_chunk_set_id,
            )

        after_rows = storage._conn.execute(
            """
            SELECT chunk_set_id, bound_by, binding_mode, target_profile_id
            FROM kb_chunk_bindings
            WHERE kb_id = ?
            ORDER BY chunk_set_id
            """,
            (kb_id,),
        ).fetchall()
        state = storage.get_agentic_ready_source_state(kb_id=kb_id, profile="general")
        assert after_rows == before_rows
        assert state["event_generation"] == 0
    finally:
        storage.close()


def test_follow_latest_without_matching_rows_is_a_complete_noop(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "follow-noop.db"))
    try:
        kb_id = "kb-follow-noop"
        file_url = "https://example.com/follow-noop.pdf"
        _create_kb(storage, kb_id)
        _create_file(storage, tmp_path, file_url)
        _add_membership(storage, kb_id=kb_id, file_url=file_url)
        profile_id = _create_profile(storage)
        chunk_set_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version="current",
        )
        _insert_binding(
            storage,
            kb_id=kb_id,
            file_url=file_url,
            chunk_set_id=chunk_set_id,
            target_profile_id=profile_id,
        )

        result = storage.sync_follow_latest_bindings_for_chunk_set(
            file_url=file_url,
            profile_id=profile_id,
            chunk_set_id=chunk_set_id,
        )

        state = storage.get_agentic_ready_source_state(kb_id=kb_id, profile="general")
        assert result == {
            "file_url": file_url,
            "profile_id": profile_id,
            "chunk_set_id": chunk_set_id,
            "synced_bindings": 0,
            "affected_kb_ids": [],
        }
        assert state["event_generation"] == 0
    finally:
        storage.close()


def test_follow_latest_without_matching_rows_does_not_validate_missing_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = Storage(str(tmp_path / "follow-noop-missing-target.db"))
    try:

        def fail_if_transaction_starts(*, immediate: bool = False):
            raise AssertionError(f"unexpected transaction: immediate={immediate}")

        monkeypatch.setattr(storage, "transaction", fail_if_transaction_starts)
        result = storage.sync_follow_latest_bindings_for_chunk_set(
            file_url="https://example.com/no-follow-binding.pdf",
            profile_id="missing-profile",
            chunk_set_id="missing-target",
        )

        assert result == {
            "file_url": "https://example.com/no-follow-binding.pdf",
            "profile_id": "missing-profile",
            "chunk_set_id": "missing-target",
            "synced_bindings": 0,
            "affected_kb_ids": [],
        }
    finally:
        storage.close()


@pytest.mark.parametrize("invalid_target_kind", ["missing", "wrong_file", "wrong_profile"])
def test_follow_latest_invalid_target_rolls_back_without_source_event(
    tmp_path: Path,
    invalid_target_kind: str,
) -> None:
    storage = Storage(str(tmp_path / f"follow-invalid-target-{invalid_target_kind}.db"))
    try:
        kb_id = "kb-follow-invalid-target"
        file_url = "https://example.com/follow-invalid-target.pdf"
        _create_kb(storage, kb_id)
        _create_file(storage, tmp_path, file_url)
        _add_membership(storage, kb_id=kb_id, file_url=file_url)
        profile_id = _create_profile(storage)
        old_chunk_set_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version="old",
        )
        _insert_binding(
            storage,
            kb_id=kb_id,
            file_url=file_url,
            chunk_set_id=old_chunk_set_id,
            target_profile_id=profile_id,
        )

        if invalid_target_kind == "missing":
            invalid_target_id = "missing-target"
        elif invalid_target_kind == "wrong_file":
            wrong_file_url = "https://example.com/wrong-file.pdf"
            _create_file(storage, tmp_path, wrong_file_url)
            invalid_target_id = _create_chunk_set(
                storage,
                file_url=wrong_file_url,
                profile_id=profile_id,
                version="wrong-file",
            )
        else:
            wrong_profile_id = str(
                storage.create_chunk_profile(
                    name="wrong-profile",
                    chunk_size=512,
                    chunk_overlap=64,
                )["profile_id"]
            )
            invalid_target_id = _create_chunk_set(
                storage,
                file_url=file_url,
                profile_id=wrong_profile_id,
                version="wrong-profile",
            )

        before_rows = storage._conn.execute(
            """
            SELECT chunk_set_id, bound_by, binding_mode, target_profile_id
            FROM kb_chunk_bindings
            WHERE kb_id = ?
            ORDER BY chunk_set_id
            """,
            (kb_id,),
        ).fetchall()

        with pytest.raises(ValueError, match="chunk_set_id"):
            storage.sync_follow_latest_bindings_for_chunk_set(
                file_url=file_url,
                profile_id=profile_id,
                chunk_set_id=invalid_target_id,
            )

        after_rows = storage._conn.execute(
            """
            SELECT chunk_set_id, bound_by, binding_mode, target_profile_id
            FROM kb_chunk_bindings
            WHERE kb_id = ?
            ORDER BY chunk_set_id
            """,
            (kb_id,),
        ).fetchall()
        state = storage.get_agentic_ready_source_state(kb_id=kb_id, profile="general")
        assert after_rows == before_rows
        assert state["event_generation"] == 0
        assert state["pending_reasons"] == []
    finally:
        storage.close()


def test_same_ready_chunk_set_content_overwrite_is_immutable_noop(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "content-overwrite.db"))
    try:
        kb_id = "kb-content-overwrite"
        file_url = "https://example.com/content-overwrite.pdf"
        _create_kb(storage, kb_id)
        _create_file(storage, tmp_path, file_url)
        _add_membership(storage, kb_id=kb_id, file_url=file_url)
        profile_id = _create_profile(storage)
        chunk_set_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version="original",
        )
        storage.bind_chunk_set_to_kb(
            kb_id=kb_id,
            file_url=file_url,
            chunk_set_id=chunk_set_id,
        )
        before = storage.get_agentic_ready_source_state(kb_id=kb_id, profile="general")

        storage.replace_global_chunks(
            chunk_set_id=chunk_set_id,
            chunks=[
                {
                    "chunk_index": 0,
                    "content": "Overwritten content in the same chunk set",
                    "token_count": 7,
                    "section_hierarchy": "Root",
                }
            ],
            overwrite=True,
        )

        after = storage.get_agentic_ready_source_state(kb_id=kb_id, profile="general")
        assert after["event_generation"] == before["event_generation"]
        assert after["pending_reasons"] == before["pending_reasons"]
    finally:
        storage.close()
