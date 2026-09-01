from __future__ import annotations

from pathlib import Path

import pytest

from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.storage import Storage


def _create_kb(storage: Storage, kb_id: str, *, profile: str = "general") -> None:
    KnowledgeBaseManager(storage).create_kb(
        kb_id=kb_id,
        name=f"Chunk content {kb_id}",
        kb_mode="manual",
        manifest_profile=profile,
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
            "keywords": ["chunks"],
            "summary": f"Summary for {suffix}",
            "category": "Chunks",
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


def _create_profile(storage: Storage, name: str = "chunk-content-profile") -> str:
    return str(
        storage.create_chunk_profile(
            name=name,
            chunk_size=256,
            chunk_overlap=32,
        )["profile_id"]
    )


def _chunk(
    content: str,
    *,
    chunk_index: int = 0,
    token_count: int = 3,
    section_hierarchy: object = "Root",
) -> dict[str, object]:
    return {
        "chunk_index": chunk_index,
        "content": content,
        "token_count": token_count,
        "section_hierarchy": section_hierarchy,
    }


def _create_chunk_set(
    storage: Storage,
    *,
    file_url: str,
    profile_id: str,
    version: str,
    chunks: list[dict[str, object]] | None = None,
) -> str:
    chunk_set = storage.get_or_create_file_chunk_set(
        file_url=file_url,
        profile_id=profile_id,
        markdown_hash=f"hash-{version}",
        status="building",
    )
    chunk_set_id = str(chunk_set["chunk_set_id"])
    if chunks:
        storage.replace_global_chunks(
            chunk_set_id=chunk_set_id,
            chunks=chunks,
            overwrite=True,
        )
    return chunk_set_id


def _insert_binding(
    storage: Storage,
    *,
    kb_id: str,
    file_url: str,
    chunk_set_id: str,
    profile_id: str | None = None,
    mode: str = "pin",
) -> None:
    storage._conn.execute(
        """
        INSERT INTO kb_chunk_bindings (
            kb_id, file_url, chunk_set_id, bound_at, bound_by,
            binding_mode, target_profile_id
        )
        VALUES (?, ?, ?, ?, 'seed', ?, ?)
        """,
        (
            kb_id,
            file_url,
            chunk_set_id,
            "2026-08-19T00:00:00+00:00",
            mode,
            profile_id if mode == "follow_latest" else None,
        ),
    )
    storage._conn.commit()


def _stored_chunks(storage: Storage, chunk_set_id: str) -> list[tuple[object, ...]]:
    return storage._conn.execute(
        """
        SELECT chunk_id, chunk_index, content, token_count, section_hierarchy,
               content_hash, created_at
        FROM global_chunks
        WHERE chunk_set_id = ?
        ORDER BY chunk_index, chunk_id
        """,
        (chunk_set_id,),
    ).fetchall()


def _chunk_set_metadata(storage: Storage, chunk_set_id: str) -> tuple[object, ...]:
    row = storage._conn.execute(
        """
        SELECT chunk_count, status, created_at, updated_at
        FROM file_chunk_sets
        WHERE chunk_set_id = ?
        """,
        (chunk_set_id,),
    ).fetchone()
    assert row is not None
    return row


def _state(storage: Storage, kb_id: str, profile: str = "general") -> dict[str, object]:
    return storage.get_agentic_ready_source_state(kb_id=kb_id, profile=profile)


def _seed_bound_context(
    storage: Storage,
    tmp_path: Path,
    *,
    name: str,
    initial_chunks: list[dict[str, object]] | None = None,
) -> tuple[str, str, str]:
    kb_id = f"kb-{name}"
    file_url = f"https://example.com/{name}.pdf"
    _create_file(storage, tmp_path, file_url)
    profile_id = _create_profile(storage, name=f"profile-{name}")
    chunk_set_id = _create_chunk_set(
        storage,
        file_url=file_url,
        profile_id=profile_id,
        version=name,
        chunks=initial_chunks,
    )
    _create_kb(storage, kb_id)
    _add_membership(storage, kb_id=kb_id, file_url=file_url)
    _insert_binding(
        storage,
        kb_id=kb_id,
        file_url=file_url,
        chunk_set_id=chunk_set_id,
    )
    return kb_id, file_url, chunk_set_id


def test_identical_canonical_overwrite_is_zero_write_and_zero_generation(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "identical.db"))
    try:
        kb_id, _file_url, chunk_set_id = _seed_bound_context(
            storage,
            tmp_path,
            name="identical",
            initial_chunks=[
                _chunk("First", chunk_index=0, token_count=1, section_hierarchy=None),
                _chunk("Second", chunk_index=1, token_count=2, section_hierarchy="Root > Two"),
            ],
        )
        storage._conn.execute(
            "UPDATE global_chunks SET content_hash = 'audit-only' WHERE chunk_set_id = ?",
            (chunk_set_id,),
        )
        storage._conn.execute(
            "UPDATE file_chunk_sets SET updated_at = '2000-01-01T00:00:00+00:00' WHERE chunk_set_id = ?",
            (chunk_set_id,),
        )
        storage._conn.commit()
        before_chunks = _stored_chunks(storage, chunk_set_id)
        before_metadata = _chunk_set_metadata(storage, chunk_set_id)

        result = storage.replace_global_chunks(
            chunk_set_id=chunk_set_id,
            chunks=[
                _chunk("Second", chunk_index=1, token_count=2, section_hierarchy="Root > Two"),
                _chunk("First", chunk_index=0, token_count=1, section_hierarchy=None),
            ],
            overwrite=True,
        )

        assert result["chunk_count"] == 2
        assert result["replaced"] is False
        assert result["inserted"] == 0
        assert _stored_chunks(storage, chunk_set_id) == before_chunks
        assert _chunk_set_metadata(storage, chunk_set_id) == before_metadata
        assert _state(storage, kb_id)["event_generation"] == 0
    finally:
        storage.close()


def test_section_hierarchy_uses_sqlite_text_affinity_for_canonical_noop(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "section-affinity.db"))
    try:
        kb_id, _file_url, chunk_set_id = _seed_bound_context(
            storage,
            tmp_path,
            name="section-affinity",
            initial_chunks=[_chunk("Content", section_hierarchy=7)],
        )
        before_chunks = _stored_chunks(storage, chunk_set_id)
        before_metadata = _chunk_set_metadata(storage, chunk_set_id)

        result = storage.replace_global_chunks(
            chunk_set_id=chunk_set_id,
            chunks=[_chunk("Content", section_hierarchy=7)],
            overwrite=True,
        )

        assert result["replaced"] is False
        assert result["inserted"] == 0
        assert _stored_chunks(storage, chunk_set_id) == before_chunks
        assert _chunk_set_metadata(storage, chunk_set_id) == before_metadata
        assert _state(storage, kb_id)["event_generation"] == 0
    finally:
        storage.close()


def test_bound_selected_ready_chunk_content_change_is_immutable_noop(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "bound-soft.db"))
    try:
        kb_id, _file_url, chunk_set_id = _seed_bound_context(
            storage,
            tmp_path,
            name="bound-soft",
            initial_chunks=[_chunk("Before")],
        )

        result = storage.replace_global_chunks(
            chunk_set_id=chunk_set_id,
            chunks=[_chunk("After", token_count=4)],
            overwrite=True,
        )

        state = _state(storage, kb_id)
        assert result["replaced"] is False
        assert result["inserted"] == 0
        assert state["event_generation"] == 0
        assert state["pending_reasons"] == []
        assert state["serving_allowed"] is True
    finally:
        storage.close()


def test_fallback_visible_chunk_content_change_marks_soft_stale_once(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "fallback-soft.db"))
    try:
        file_url = "https://example.com/fallback-soft.pdf"
        _create_file(storage, tmp_path, file_url)
        profile_id = _create_profile(storage)
        chunk_set_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version="fallback-soft",
        )
        kb_id = "kb-fallback-soft"
        _create_kb(storage, kb_id)
        _add_membership(storage, kb_id=kb_id, file_url=file_url)

        storage.replace_global_chunks(
            chunk_set_id=chunk_set_id,
            chunks=[_chunk("After")],
            overwrite=True,
        )

        state = _state(storage, kb_id)
        assert state["event_generation"] == 1
        assert state["pending_severity"] == "soft_stale"
        assert state["pending_reasons"] == ["chunk_content_updated"]
    finally:
        storage.close()


def test_compare_and_write_use_begin_immediate(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "begin-immediate.db"))
    try:
        file_url = "https://example.com/begin-immediate.pdf"
        _create_file(storage, tmp_path, file_url)
        profile_id = _create_profile(storage)
        chunk_set_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version="begin-immediate",
            chunks=[_chunk("Before")],
        )
        statements: list[str] = []
        storage._conn.set_trace_callback(statements.append)

        storage.replace_global_chunks(
            chunk_set_id=chunk_set_id,
            chunks=[_chunk("After")],
            overwrite=True,
        )

        assert any(statement.strip().upper() == "BEGIN IMMEDIATE" for statement in statements)
    finally:
        storage.close()


def test_selected_nonempty_ready_chunk_set_cannot_become_empty(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "hard-empty.db"))
    try:
        kb_id, _file_url, chunk_set_id = _seed_bound_context(
            storage,
            tmp_path,
            name="hard-empty",
            initial_chunks=[_chunk("Before")],
        )

        result = storage.replace_global_chunks(
            chunk_set_id=chunk_set_id,
            chunks=[],
            overwrite=True,
        )

        state = _state(storage, kb_id)
        assert result["chunk_count"] == 1
        assert result["replaced"] is False
        assert result["inserted"] == 0
        assert state["event_generation"] == 0
        assert state["pending_reasons"] == []
        assert state["serving_allowed"] is True
    finally:
        storage.close()


def test_ready_empty_chunk_set_is_immutable_and_fails_closed(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "empty-noop.db"))
    try:
        kb_id, _file_url, chunk_set_id = _seed_bound_context(
            storage,
            tmp_path,
            name="empty-noop",
        )
        storage._conn.execute(
            "UPDATE file_chunk_sets SET status = 'ready' WHERE chunk_set_id = ?",
            (chunk_set_id,),
        )
        storage._conn.commit()
        before_metadata = _chunk_set_metadata(storage, chunk_set_id)

        with pytest.raises(
            ValueError,
            match="ready chunk set has no persisted chunks and is immutable",
        ):
            storage.replace_global_chunks(
                chunk_set_id=chunk_set_id,
                chunks=[],
                overwrite=True,
            )

        assert _chunk_set_metadata(storage, chunk_set_id) == before_metadata
        assert _state(storage, kb_id)["event_generation"] == 0
    finally:
        storage.close()


@pytest.mark.parametrize(
    ("case", "create_kb", "add_membership", "catalog_status"),
    [
        ("orphan-kb", False, False, "ok"),
        ("non-member", True, False, "ok"),
        ("catalog-error", True, True, "error"),
    ],
)
def test_non_builder_inputs_and_orphan_bindings_do_not_emit_content_events(
    tmp_path: Path,
    case: str,
    create_kb: bool,
    add_membership: bool,
    catalog_status: str,
) -> None:
    storage = Storage(str(tmp_path / f"{case}.db"))
    try:
        kb_id = f"kb-{case}"
        file_url = f"https://example.com/{case}.pdf"
        _create_file(storage, tmp_path, file_url, catalog_status=catalog_status)
        profile_id = _create_profile(storage, name=f"profile-{case}")
        chunk_set_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version=case,
            chunks=[_chunk("Before")],
        )
        if create_kb:
            _create_kb(storage, kb_id)
        if add_membership:
            _add_membership(storage, kb_id=kb_id, file_url=file_url)
        _insert_binding(
            storage,
            kb_id=kb_id,
            file_url=file_url,
            chunk_set_id=chunk_set_id,
        )

        storage.replace_global_chunks(
            chunk_set_id=chunk_set_id,
            chunks=[_chunk("After")],
            overwrite=True,
        )

        event_rows = storage._conn.execute(
            "SELECT COUNT(*) FROM agentic_ready_source_state WHERE kb_id = ?",
            (kb_id,),
        ).fetchone()[0]
        assert event_rows == 0
    finally:
        storage.close()


def test_bound_mode_ignores_an_unselected_chunk_set(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "bound-unselected.db"))
    try:
        file_url = "https://example.com/bound-unselected.pdf"
        _create_file(storage, tmp_path, file_url)
        profile_id = _create_profile(storage)
        selected_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version="selected",
            chunks=[_chunk("Selected")],
        )
        unselected_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version="unselected",
            chunks=[_chunk("Unselected before")],
        )
        kb_id = "kb-bound-unselected"
        _create_kb(storage, kb_id)
        _add_membership(storage, kb_id=kb_id, file_url=file_url)
        _insert_binding(
            storage,
            kb_id=kb_id,
            file_url=file_url,
            chunk_set_id=selected_id,
        )

        storage.replace_global_chunks(
            chunk_set_id=unselected_id,
            chunks=[_chunk("Unselected after")],
            overwrite=True,
        )

        assert _state(storage, kb_id)["event_generation"] == 0
    finally:
        storage.close()


def test_affected_kb_lookup_does_not_materialize_each_full_bound_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = Storage(str(tmp_path / "set-based-affected-kbs.db"))
    try:
        kb_id, _file_url, chunk_set_id = _seed_bound_context(
            storage,
            tmp_path,
            name="set-based-affected-kbs",
            initial_chunks=[_chunk("Before")],
        )

        def fail_materialization(*_args: object, **_kwargs: object) -> frozenset[tuple[str, str]]:
            pytest.fail("affected-KB lookup must not materialize every KB's full selection")

        monkeypatch.setattr(
            storage,
            "_ready_data_bound_chunk_selection",
            fail_materialization,
        )

        storage.replace_global_chunks(
            chunk_set_id=chunk_set_id,
            chunks=[_chunk("After")],
            overwrite=True,
        )

        assert _state(storage, kb_id)["pending_reasons"] == []
    finally:
        storage.close()


def test_multiple_affected_kbs_each_advance_once(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "multiple-kbs.db"))
    try:
        file_url = "https://example.com/multiple-kbs.pdf"
        _create_file(storage, tmp_path, file_url)
        profile_id = _create_profile(storage)
        chunk_set_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version="multiple-kbs",
            chunks=[_chunk("Before")],
        )
        for kb_id in ("kb-bound", "kb-fallback"):
            _create_kb(storage, kb_id)
            _add_membership(storage, kb_id=kb_id, file_url=file_url)
        _insert_binding(
            storage,
            kb_id="kb-bound",
            file_url=file_url,
            chunk_set_id=chunk_set_id,
        )

        storage.replace_global_chunks(
            chunk_set_id=chunk_set_id,
            chunks=[_chunk("After")],
            overwrite=True,
        )

        for kb_id in ("kb-bound", "kb-fallback"):
            state = _state(storage, kb_id)
            assert state["event_generation"] == 0
            assert state["pending_reasons"] == []
    finally:
        storage.close()


def test_all_known_ready_data_profiles_advance_once(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "multiple-profiles.db"))
    try:
        kb_id, _file_url, chunk_set_id = _seed_bound_context(
            storage,
            tmp_path,
            name="multiple-profiles",
            initial_chunks=[_chunk("Before")],
        )
        storage.mark_agentic_ready_source_event(
            kb_id=kb_id,
            profile="state-profile",
            reason="profile_contract_changed",
        )
        state_profile = _state(storage, kb_id, "state-profile")
        storage.record_agentic_ready_source_evaluation(
            kb_id=kb_id,
            profile="state-profile",
            evaluated_generation=int(state_profile["event_generation"]),
            source_version_kind="catalog_chunks_snapshot",
            source_version_id="seed-state-profile",
        )
        storage.set_agentic_ready_automation(
            kb_id=kb_id,
            profile="slot-profile",
            automatic_build_enabled=False,
            automatic_publish_enabled=False,
        )
        storage.upsert_agentic_ready_manifest(
            kb_id=kb_id,
            profile="manifest-profile",
            profile_version="1",
            status="missing",
        )
        storage.record_agentic_ready_publication(
            kb_id=kb_id,
            index_version_id=None,
            source_version_kind="catalog_chunks_snapshot",
            source_version_id="publication-source",
            profile="publication-profile",
            profile_version="1",
            status="failed",
            output_dir=str(tmp_path / "unused-publication"),
            artifact_digest="publication-digest",
        )
        profiles = {
            "general",
            "state-profile",
            "slot-profile",
            "manifest-profile",
            "publication-profile",
        }
        before = {
            profile: int(_state(storage, kb_id, profile)["event_generation"])
            for profile in profiles
        }

        storage.replace_global_chunks(
            chunk_set_id=chunk_set_id,
            chunks=[_chunk("After")],
            overwrite=True,
        )

        for profile in profiles:
            state = _state(storage, kb_id, profile)
            assert state["event_generation"] == before[profile]
    finally:
        storage.close()


def test_ready_chunk_immutability_skips_content_event_markers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = Storage(str(tmp_path / "marker-rollback.db"))
    try:
        file_url = "https://example.com/marker-rollback.pdf"
        _create_file(storage, tmp_path, file_url)
        profile_id = _create_profile(storage)
        chunk_set_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version="marker-rollback",
            chunks=[_chunk("Before")],
        )
        kb_ids = ("kb-marker-one", "kb-marker-two")
        for kb_id in kb_ids:
            _create_kb(storage, kb_id)
            _add_membership(storage, kb_id=kb_id, file_url=file_url)
        before_chunks = _stored_chunks(storage, chunk_set_id)
        before_metadata = _chunk_set_metadata(storage, chunk_set_id)
        original_marker = storage.mark_agentic_ready_source_event_for_kb
        marker_calls = 0

        def fail_second_marker(*, kb_id: str, reason: str) -> list[dict[str, object]]:
            nonlocal marker_calls
            marker_calls += 1
            if marker_calls == 2:
                raise RuntimeError("injected marker failure")
            return original_marker(kb_id=kb_id, reason=reason)

        monkeypatch.setattr(storage, "mark_agentic_ready_source_event_for_kb", fail_second_marker)

        result = storage.replace_global_chunks(
            chunk_set_id=chunk_set_id,
            chunks=[_chunk("After")],
            overwrite=True,
        )

        assert result["replaced"] is False
        assert marker_calls == 0
        assert _stored_chunks(storage, chunk_set_id) == before_chunks
        assert _chunk_set_metadata(storage, chunk_set_id) == before_metadata
        for kb_id in kb_ids:
            assert _state(storage, kb_id)["event_generation"] == 0
    finally:
        storage.close()


def test_overwrite_false_with_existing_chunks_is_a_complete_noop(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "overwrite-false.db"))
    try:
        kb_id, _file_url, chunk_set_id = _seed_bound_context(
            storage,
            tmp_path,
            name="overwrite-false",
            initial_chunks=[_chunk("Before")],
        )
        before_chunks = _stored_chunks(storage, chunk_set_id)
        before_metadata = _chunk_set_metadata(storage, chunk_set_id)

        result = storage.replace_global_chunks(
            chunk_set_id=chunk_set_id,
            chunks=[_chunk("Ignored")],
            overwrite=False,
        )

        assert result["chunk_count"] == 1
        assert result["replaced"] is False
        assert result["inserted"] == 0
        assert _stored_chunks(storage, chunk_set_id) == before_chunks
        assert _chunk_set_metadata(storage, chunk_set_id) == before_metadata
        assert _state(storage, kb_id)["event_generation"] == 0
    finally:
        storage.close()


def test_duplicate_chunk_indexes_compare_the_final_persisted_rows(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "duplicate-index.db"))
    try:
        kb_id, _file_url, chunk_set_id = _seed_bound_context(
            storage,
            tmp_path,
            name="duplicate-index",
            initial_chunks=[_chunk("Final", token_count=2)],
        )

        noop = storage.replace_global_chunks(
            chunk_set_id=chunk_set_id,
            chunks=[
                _chunk("Transient", token_count=1),
                _chunk("Final", token_count=2),
            ],
            overwrite=True,
        )
        changed = storage.replace_global_chunks(
            chunk_set_id=chunk_set_id,
            chunks=[
                _chunk("Transient", token_count=1),
                _chunk("Changed final", token_count=3),
            ],
            overwrite=True,
        )

        rows = _stored_chunks(storage, chunk_set_id)
        assert noop["replaced"] is False
        assert noop["inserted"] == 0
        assert changed["replaced"] is False
        assert changed["inserted"] == 0
        assert len(rows) == 1
        assert rows[0][2:4] == ("Final", 2)
        assert _state(storage, kb_id)["event_generation"] == 0
    finally:
        storage.close()


def test_same_ready_set_overwrite_emits_no_content_reason(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "content-only.db"))
    try:
        kb_id, _file_url, chunk_set_id = _seed_bound_context(
            storage,
            tmp_path,
            name="content-only",
            initial_chunks=[_chunk("Before")],
        )

        storage.replace_global_chunks(
            chunk_set_id=chunk_set_id,
            chunks=[_chunk("After")],
            overwrite=True,
        )

        assert _state(storage, kb_id)["pending_reasons"] == []
    finally:
        storage.close()


def test_follow_latest_new_set_emits_binding_event_without_duplicate_content_event(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "follow-latest.db"))
    try:
        file_url = "https://example.com/follow-latest.pdf"
        _create_file(storage, tmp_path, file_url)
        profile_id = _create_profile(storage)
        old_chunk_set_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version="old",
            chunks=[_chunk("Old")],
        )
        kb_id = "kb-follow-latest"
        _create_kb(storage, kb_id)
        _add_membership(storage, kb_id=kb_id, file_url=file_url)
        _insert_binding(
            storage,
            kb_id=kb_id,
            file_url=file_url,
            chunk_set_id=old_chunk_set_id,
            profile_id=profile_id,
            mode="follow_latest",
        )
        new_chunk_set_id = _create_chunk_set(
            storage,
            file_url=file_url,
            profile_id=profile_id,
            version="new",
        )

        storage.replace_global_chunks(
            chunk_set_id=new_chunk_set_id,
            chunks=[_chunk("New")],
            overwrite=True,
        )
        after_content = _state(storage, kb_id)
        sync = storage.sync_follow_latest_bindings_for_chunk_set(
            file_url=file_url,
            profile_id=profile_id,
            chunk_set_id=new_chunk_set_id,
        )

        state = _state(storage, kb_id)
        assert after_content["event_generation"] == 0
        assert sync["synced_bindings"] == 1
        assert state["event_generation"] == 1
        assert state["pending_reasons"] == ["chunk_binding_updated"]
    finally:
        storage.close()


def test_content_events_do_not_move_publication_pointers_or_enable_automation(
    tmp_path: Path,
) -> None:
    storage = Storage(str(tmp_path / "publication-pointers.db"))
    try:
        kb_id, _file_url, chunk_set_id = _seed_bound_context(
            storage,
            tmp_path,
            name="publication-pointers",
            initial_chunks=[_chunk("Before")],
        )
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
                    str(tmp_path / publication_id),
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
        before = storage.get_agentic_ready_publication_state(kb_id=kb_id, profile="general")

        storage.replace_global_chunks(
            chunk_set_id=chunk_set_id,
            chunks=[_chunk("After")],
            overwrite=True,
        )

        after = storage.get_agentic_ready_publication_state(kb_id=kb_id, profile="general")
        state = _state(storage, kb_id)
        assert after["active_publication_id"] == before["active_publication_id"]
        assert after["previous_publication_id"] == before["previous_publication_id"]
        assert after["automatic_build_enabled"] is False
        assert after["automatic_publish_enabled"] is False
        assert state["serving_stale"] is False
        assert state["serving_allowed"] is True
    finally:
        storage.close()


def test_ready_chunk_immutability_ignores_invalid_replacement_input(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "invalid-input.db"))
    try:
        kb_id, _file_url, chunk_set_id = _seed_bound_context(
            storage,
            tmp_path,
            name="invalid-input",
            initial_chunks=[_chunk("Before")],
        )
        before_chunks = _stored_chunks(storage, chunk_set_id)
        before_metadata = _chunk_set_metadata(storage, chunk_set_id)

        result = storage.replace_global_chunks(
            chunk_set_id=chunk_set_id,
            chunks=[{"chunk_index": "not-an-index", "content": "Invalid"}],
            overwrite=True,
        )

        assert result["replaced"] is False
        assert _stored_chunks(storage, chunk_set_id) == before_chunks
        assert _chunk_set_metadata(storage, chunk_set_id) == before_metadata
        assert _state(storage, kb_id)["event_generation"] == 0
    finally:
        storage.close()
