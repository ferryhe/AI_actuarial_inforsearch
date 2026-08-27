from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml
from fastapi.testclient import TestClient

import ai_actuarial.task_runtime as task_runtime_module
from ai_actuarial.api.app import create_app
from ai_actuarial.api.services.rag_admin import (
    _build_agentic_manifest_status,
    _ready_data_artifact_digest,
)
from ai_actuarial.api.services.ready_data_automation import (
    run_ready_data_automation_once,
)
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.rag.kb_index import resolve_kb_bound_chunks
from ai_actuarial.storage import Storage
from ai_actuarial.task_runtime import NativeTaskRuntime


UTC = timezone.utc


def _create_kb(storage: Storage, kb_id: str = "kb-auto") -> None:
    KnowledgeBaseManager(storage).create_kb(
        kb_id=kb_id,
        name=f"Automation {kb_id}",
        kb_mode="manual",
        manifest_profile="general",
        embedding_provider="test",
        embedding_model="automation-model",
        embedding_dimension=3,
        embedding_identity_key=f"identity-{kb_id}",
    )
    file_url = f"https://example.com/{kb_id}.pdf"
    now = "2026-08-19T00:00:00+00:00"
    storage.insert_file(
        url=file_url,
        sha256=f"sha-{kb_id}",
        title=f"Automation source {kb_id}",
        source_site="example.com",
        source_page_url="https://example.com",
        original_filename=f"{kb_id}.pdf",
        local_path=str(Path(storage.db_path).resolve().parent / f"{kb_id}.pdf"),
        bytes=10,
        content_type="application/pdf",
    )
    storage.upsert_catalog_item(
        {
            "url": file_url,
            "sha256": f"sha-{kb_id}",
            "keywords": ["automation"],
            "summary": f"Automation source for {kb_id}",
            "category": "test",
        },
        pipeline_version="test-v1",
        status="ok",
    )
    with storage.transaction():
        storage._conn.execute(
            "INSERT INTO rag_kb_files(kb_id, file_url, added_at) VALUES (?, ?, ?)",
            (kb_id, file_url, now),
        )
        storage._conn.execute(
            """
            INSERT INTO chunk_profiles(
                profile_id, name, config_hash, config_json, chunk_size,
                chunk_overlap, splitter, tokenizer, version, created_at, updated_at
            ) VALUES (?, ?, ?, '{}', 100, 10, 'semantic', 'test', '1', ?, ?)
            """,
            (f"cp-{kb_id}", f"Profile {kb_id}", f"cfg-{kb_id}", now, now),
        )
        storage._conn.execute(
            """
            INSERT INTO file_chunk_sets(
                chunk_set_id, file_url, profile_id, markdown_hash,
                status, chunk_count, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'ready', 1, ?, ?)
            """,
            (f"cs-{kb_id}", file_url, f"cp-{kb_id}", f"md-{kb_id}", now, now),
        )
        storage._conn.execute(
            """
            INSERT INTO global_chunks(
                chunk_id, chunk_set_id, chunk_index, content,
                token_count, section_hierarchy, content_hash, created_at
            ) VALUES (?, ?, 0, ?, 3, 'Section', ?, ?)
            """,
            (f"chunk-{kb_id}", f"cs-{kb_id}", f"Content {kb_id}", f"content-{kb_id}", now),
        )
        storage._conn.execute(
            """
            INSERT INTO kb_chunk_bindings(
                kb_id, file_url, chunk_set_id, bound_at, bound_by,
                binding_mode, target_profile_id
            ) VALUES (?, ?, ?, ?, 'test', 'pin', ?)
            """,
            (kb_id, file_url, f"cs-{kb_id}", now, f"cp-{kb_id}"),
        )
        storage._conn.execute(
            "UPDATE rag_knowledge_bases SET chunk_profile_id = ? WHERE kb_id = ?",
            (f"cp-{kb_id}", kb_id),
        )
    snapshot = resolve_kb_bound_chunks(storage, kb_id)
    storage.create_kb_index_version(
        kb_id=kb_id,
        embedding_provider="test",
        embedding_model="automation-model",
        embedding_dimension=3,
        embedding_identity_key=f"identity-{kb_id}",
        binding_snapshot_fingerprint=snapshot["binding_snapshot_fingerprint"],
        index_type="faiss",
        chunk_count=1,
        artifact_path=f"indexes/{kb_id}",
        artifact_digest=f"digest-{kb_id}",
        chunk_ids=[f"chunk-{kb_id}"],
        status="ready",
    )
    storage._conn.execute(
        "DELETE FROM agentic_ready_source_state WHERE kb_id = ? AND profile = 'general'",
        (kb_id,),
    )
    storage._conn.commit()


def _mark_event(storage: Storage, kb_id: str = "kb-auto", reason: str = "membership_added") -> int:
    state = storage.mark_agentic_ready_source_event(
        kb_id=kb_id,
        profile="general",
        reason=reason,
    )
    return int(state["event_generation"])


def _set_automation(
    storage: Storage,
    *,
    kb_id: str = "kb-auto",
    build: bool,
    publish: bool,
) -> None:
    storage.set_agentic_ready_automation(
        kb_id=kb_id,
        profile="general",
        automatic_build_enabled=build,
        automatic_publish_enabled=publish,
    )


def _record_candidate(
    db_path: str,
    *,
    kb_id: str,
    generation: int,
    status: str = "validated",
    source_version_id: str | None = None,
    index_version_id: str = "idx-test",
) -> dict[str, Any]:
    storage = Storage(db_path)
    try:
        output_dir = (
            Path(db_path).resolve().parent
            / "agentic_ready_data"
            / "staging"
            / f"auto-{kb_id}-{generation}-{source_version_id or 'source'}"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / "ready_data_manifest.json"
        manifest_path.write_text(
            '{"profile":"general","profile_version":"1"}',
            encoding="utf-8",
        )
        artifact_files = ["ready_data_manifest.json"]
        artifact_digest = _ready_data_artifact_digest(str(output_dir), artifact_files)
        return storage.record_agentic_ready_publication(
            kb_id=kb_id,
            index_version_id=index_version_id,
            source_version_kind="catalog_chunks_snapshot",
            source_version_id=source_version_id or f"source-{generation}",
            profile="general",
            profile_version="1",
            status=status,
            output_dir=str(output_dir) if status == "validated" else "",
            artifact_files=artifact_files,
            doc_count=1,
            section_count=1,
            built_at="2026-08-19T00:00:00+00:00",
            artifact_digest=artifact_digest,
            source_db=db_path,
            smoke_result={
                "contract_version": "ready-data-staging-smoke.v1",
                "status": "passed",
                "checked_at": "2026-08-19T00:00:00+00:00",
                "elapsed_ms": 1,
                "query_source": "title",
                "query": "Synthetic automation candidate",
                "query_sha256": "a" * 64,
                "matched_doc_id": "doc-auto",
                "matched_file_url": "https://example.com/auto",
                "failure_reason": "",
                "catalog_doc_count": 1,
            },
            error_message="build failed" if status == "failed" else "",
        )
    finally:
        storage.close()


def _publish_seed(
    storage: Storage,
    tmp_path: Path,
    *,
    kb_id: str = "kb-auto",
    source_version_id: str = "source-active",
) -> dict[str, Any]:
    publication = _record_candidate(
        storage.db_path,
        kb_id=kb_id,
        generation=0,
        source_version_id=source_version_id,
    )
    state = storage.get_agentic_ready_publication_state(kb_id=kb_id, profile="general")
    published = storage.publish_agentic_ready_publication(
        str(publication["publication_id"]),
        expected_active_publication_id=state["active_publication_id"],
    )
    return dict(published["active_publication"])


def _valid(_: str) -> dict[str, Any]:
    return {"valid": True, "errors": [], "warnings": []}


def _invalid(_: str) -> dict[str, Any]:
    return {
        "valid": False,
        "errors": ["synthetic validation failure"],
        "warnings": [],
    }


def _builder(
    calls: list[int],
    *,
    hook: Callable[[str, str, int], None] | None = None,
    fail: bool = False,
) -> Callable[..., dict[str, Any]]:
    def build(
        *,
        db_path: str,
        kb_id: str,
        profile: str,
        index_version_id: str,
        expected_source_snapshot_fingerprint: str,
    ) -> dict[str, Any]:
        assert profile == "general"
        storage = Storage(db_path)
        try:
            source_state = storage.get_agentic_ready_source_state(
                kb_id=kb_id,
                profile=profile,
            )
            generation = int(source_state["pending_evaluation_generation"])
        finally:
            storage.close()
        calls.append(generation)
        if hook:
            hook(db_path, kb_id, generation)
        if fail:
            raise RuntimeError("synthetic build failure")
        publication = _record_candidate(
            db_path,
            kb_id=kb_id,
            generation=generation,
            index_version_id=index_version_id,
            source_version_id=expected_source_snapshot_fingerprint,
        )
        return {
            "kb_id": kb_id,
            "candidate_publication": publication,
            "publication_state": {},
            "validation": {"valid": True, "errors": [], "warnings": []},
        }

    return build


def _setup_pending(
    tmp_path: Path,
    *,
    build: bool = True,
    publish: bool = False,
    reason: str = "membership_added",
    kb_id: str = "kb-auto",
) -> Path:
    db_path = tmp_path / "index.db"
    storage = Storage(str(db_path))
    try:
        _create_kb(storage, kb_id)
        _set_automation(storage, kb_id=kb_id, build=build, publish=publish)
        _mark_event(storage, kb_id=kb_id, reason=reason)
    finally:
        storage.close()
    return db_path


def test_default_off_runner_does_not_build_or_write_attempt_state(tmp_path: Path) -> None:
    db_path = _setup_pending(tmp_path, build=False, publish=False)
    calls: list[int] = []

    result = run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=_builder(calls),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    assert result["status"] == "idle"
    assert calls == []
    storage = Storage(str(db_path))
    try:
        assert storage._conn.execute("SELECT COUNT(*) FROM agentic_ready_publications").fetchone()[0] == 0
        assert storage._conn.execute("SELECT COUNT(*) FROM agentic_ready_automation").fetchone()[0] == 0
    finally:
        storage.close()


def test_runner_is_idle_before_any_knowledge_base_exists(tmp_path: Path) -> None:
    db_path = tmp_path / "index.db"
    storage = Storage(str(db_path))
    storage.close()

    result = run_ready_data_automation_once(
        db_path=str(db_path),
        heartbeat_interval_seconds=0,
    )

    assert result == {"status": "idle"}


def test_publish_without_build_is_rejected(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "index.db"))
    try:
        _create_kb(storage)
        with pytest.raises(ValueError, match="automatic publish requires automatic build"):
            _set_automation(storage, build=False, publish=True)
    finally:
        storage.close()


def test_runner_coalesces_events_and_attempts_only_latest_generation(tmp_path: Path) -> None:
    db_path = _setup_pending(tmp_path)
    storage = Storage(str(db_path))
    try:
        _mark_event(storage)
        latest = _mark_event(storage)
    finally:
        storage.close()
    calls: list[int] = []

    first = run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=_builder(calls),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )
    second = run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=_builder(calls),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    assert first["status"] == "awaiting_publish"
    assert second["status"] == "idle"
    assert calls == [latest]


def test_new_generation_supersedes_prior_awaiting_publish_candidate(tmp_path: Path) -> None:
    db_path = _setup_pending(tmp_path)
    first = run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=_builder([]),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )
    storage = Storage(str(db_path))
    try:
        _mark_event(storage)
    finally:
        storage.close()

    second = run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=_builder([]),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    storage = Storage(str(db_path))
    try:
        prior = storage.get_agentic_ready_publication(
            str(first["candidate_publication"]["publication_id"])
        )
        assert prior["attempt_disposition"] == "superseded_generation"
        assert second["status"] == "awaiting_publish"
        assert second["generation"] == 2
    finally:
        storage.close()


def test_build_only_keeps_validated_candidate_and_active_slot(tmp_path: Path) -> None:
    db_path = _setup_pending(tmp_path)
    storage = Storage(str(db_path))
    try:
        active = _publish_seed(storage, tmp_path)
    finally:
        storage.close()
    calls: list[int] = []

    result = run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=_builder(calls),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    assert result["status"] == "awaiting_publish"
    assert result["candidate_publication"]["status"] == "validated"
    storage = Storage(str(db_path))
    try:
        state = storage.get_agentic_ready_publication_state(kb_id="kb-auto", profile="general")
        automation = storage.get_agentic_ready_automation_state(kb_id="kb-auto", profile="general")
        assert state["active_publication_id"] == active["publication_id"]
        assert automation["automation_state"] == "awaiting_publish"
    finally:
        storage.close()


def test_default_runner_reuses_internal_staging_build_core(tmp_path: Path) -> None:
    db_path = _setup_pending(tmp_path)

    result = run_ready_data_automation_once(
        db_path=str(db_path),
        heartbeat_interval_seconds=0,
    )

    assert result["status"] == "awaiting_publish"
    assert result["candidate_publication"]["status"] == "validated"
    assert Path(result["candidate_publication"]["output_dir"]).is_dir()
    storage = Storage(str(db_path))
    try:
        manifest = _build_agentic_manifest_status(
            storage=storage,
            kb_id="kb-auto",
            profile="general",
        )
        assert manifest["automation_state"] == "awaiting_publish"
    finally:
        storage.close()


def test_enabling_publish_revalidates_and_publishes_existing_candidate(tmp_path: Path) -> None:
    db_path = _setup_pending(tmp_path)
    calls: list[int] = []
    first = run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=_builder(calls),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )
    storage = Storage(str(db_path))
    try:
        _set_automation(storage, build=True, publish=True)
    finally:
        storage.close()

    second = run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=_builder(calls),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    assert first["status"] == "awaiting_publish"
    assert second["status"] == "published"
    assert calls == [1]
    assert second["publication_state"]["active_publication_id"] == first[
        "candidate_publication"
    ]["publication_id"]


def test_build_and_publish_preserves_previous_slot_and_settles_generation(tmp_path: Path) -> None:
    db_path = _setup_pending(tmp_path, publish=True)
    storage = Storage(str(db_path))
    try:
        previous_active = _publish_seed(storage, tmp_path)
    finally:
        storage.close()

    result = run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=_builder([]),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    assert result["status"] == "published"
    storage = Storage(str(db_path))
    try:
        state = storage.get_agentic_ready_publication_state(kb_id="kb-auto", profile="general")
        source = storage.get_agentic_ready_source_state(kb_id="kb-auto", profile="general")
        assert state["previous_publication_id"] == previous_active["publication_id"]
        assert source["evaluated_generation"] == 1
        assert source["pending_evaluation_generation"] is None
    finally:
        storage.close()


def test_generation_change_supersedes_candidate_without_moving_slots(tmp_path: Path) -> None:
    db_path = _setup_pending(tmp_path, publish=True)
    storage = Storage(str(db_path))
    try:
        active = _publish_seed(storage, tmp_path)
    finally:
        storage.close()

    def advance(db_path: str, kb_id: str, _generation: int) -> None:
        changing = Storage(db_path)
        try:
            _mark_event(changing, kb_id=kb_id)
        finally:
            changing.close()

    result = run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=_builder([], hook=advance),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    assert result["status"] == "superseded"
    storage = Storage(str(db_path))
    try:
        candidate = storage.get_agentic_ready_publication(
            str(result["candidate_publication"]["publication_id"])
        )
        state = storage.get_agentic_ready_publication_state(kb_id="kb-auto", profile="general")
        source = storage.get_agentic_ready_source_state(kb_id="kb-auto", profile="general")
        assert candidate["attempt_disposition"] == "superseded_generation"
        assert state["active_publication_id"] == active["publication_id"]
        assert source["pending_evaluation_generation"] == 2
        assert source["evaluated_generation"] == 0
    finally:
        storage.close()


def test_disabling_automation_during_build_prevents_publication(tmp_path: Path) -> None:
    db_path = _setup_pending(tmp_path, publish=True)

    def disable(db_path: str, kb_id: str, _generation: int) -> None:
        changing = Storage(db_path)
        try:
            _set_automation(changing, kb_id=kb_id, build=False, publish=False)
        finally:
            changing.close()

    result = run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=_builder([], hook=disable),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    assert result["status"] == "awaiting_publish"
    storage = Storage(str(db_path))
    try:
        state = storage.get_agentic_ready_publication_state(kb_id="kb-auto", profile="general")
        assert state["active_publication_id"] is None
    finally:
        storage.close()


def test_concurrent_runners_allow_only_one_claim_owner(tmp_path: Path) -> None:
    db_path = _setup_pending(tmp_path)
    storage = Storage(str(db_path))
    try:
        _create_kb(storage, "kb-second")
        _set_automation(storage, kb_id="kb-second", build=True, publish=False)
        _mark_event(storage, kb_id="kb-second")
    finally:
        storage.close()
    entered = threading.Event()
    release = threading.Event()
    calls: list[int] = []

    def blocking_hook(_db_path: str, _kb_id: str, _generation: int) -> None:
        entered.set()
        assert release.wait(timeout=5)

    first_result: list[dict[str, Any]] = []

    def first_runner() -> None:
        first_result.append(
            run_ready_data_automation_once(
                db_path=str(db_path),
                build_candidate=_builder(calls, hook=blocking_hook),
                validator=_valid,
                heartbeat_interval_seconds=0,
            )
        )

    thread = threading.Thread(target=first_runner)
    thread.start()
    assert entered.wait(timeout=5)
    second = run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=_builder(calls),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )
    release.set()
    thread.join(timeout=5)

    assert second["status"] == "idle"
    assert first_result[0]["status"] == "awaiting_publish"
    assert calls == [1]


def test_lost_claim_owner_cannot_publish(tmp_path: Path) -> None:
    db_path = _setup_pending(tmp_path, publish=True)

    def steal_claim(db_path: str, kb_id: str, _generation: int) -> None:
        storage = Storage(db_path)
        try:
            with storage.transaction(immediate=True):
                storage._conn.execute(
                    "UPDATE agentic_ready_automation SET claim_token = 'stolen' "
                    "WHERE kb_id = ? AND profile = 'general'",
                    (kb_id,),
                )
        finally:
            storage.close()

    result = run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=_builder([], hook=steal_claim),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    assert result["status"] == "claim_lost"
    storage = Storage(str(db_path))
    try:
        assert storage.get_agentic_ready_publication_state(
            kb_id="kb-auto", profile="general"
        )["active_publication_id"] is None
    finally:
        storage.close()


@pytest.mark.parametrize("failure_kind", ["build", "validation", "cas"])
def test_failures_do_not_move_serving_slots_or_retry_same_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    db_path = _setup_pending(tmp_path, publish=True)
    storage = Storage(str(db_path))
    try:
        active = _publish_seed(storage, tmp_path)
    finally:
        storage.close()
    calls: list[int] = []
    validator = _valid
    builder = _builder(calls, fail=failure_kind == "build")
    if failure_kind == "validation":
        validator = _invalid
    if failure_kind == "cas":
        original = Storage.publish_claimed_agentic_ready_publication

        def lose_cas(self: Storage, publication_id: str, **kwargs: Any) -> dict[str, Any]:
            current = self.get_agentic_ready_publication_state(
                kb_id=kwargs["kb_id"],
                profile=kwargs["profile"],
            )
            winner = _record_candidate(
                self.db_path,
                kb_id=kwargs["kb_id"],
                generation=99,
                source_version_id="cas-winner",
            )
            other = Storage(self.db_path)
            try:
                other.publish_agentic_ready_publication(
                    str(winner["publication_id"]),
                    expected_active_publication_id=current["active_publication_id"],
                )
            finally:
                other.close()
            return original(self, publication_id, **kwargs)

        monkeypatch.setattr(Storage, "publish_claimed_agentic_ready_publication", lose_cas)

    first = run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=builder,
        validator=validator,
        heartbeat_interval_seconds=0,
    )
    second = run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=builder,
        validator=validator,
        heartbeat_interval_seconds=0,
    )

    assert first["status"] == "failed"
    assert second["status"] == "idle"
    storage = Storage(str(db_path))
    try:
        state = storage.get_agentic_ready_publication_state(kb_id="kb-auto", profile="general")
        if failure_kind != "cas":
            assert state["active_publication_id"] == active["publication_id"]
        else:
            assert state["active_publication"]["source_version_id"] == "cas-winner"
        assert state["active_publication_id"] != first.get("candidate_publication", {}).get(
            "publication_id"
        )
    finally:
        storage.close()


def test_new_generation_can_run_after_prior_failure(tmp_path: Path) -> None:
    db_path = _setup_pending(tmp_path)
    calls: list[int] = []
    failed = run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=_builder(calls, fail=True),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )
    storage = Storage(str(db_path))
    try:
        latest = _mark_event(storage)
    finally:
        storage.close()

    retried = run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=_builder(calls),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    assert failed["status"] == "failed"
    assert retried["status"] == "awaiting_publish"
    assert calls == [1, latest]


def test_expired_crash_claim_is_recovered_without_sleep(tmp_path: Path) -> None:
    db_path = _setup_pending(tmp_path)
    started = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
    storage = Storage(str(db_path))
    try:
        abandoned = storage.claim_next_agentic_ready_automation(
            now=started,
            lease_seconds=30,
            claim_token="abandoned",
        )
        public_state = storage.get_agentic_ready_automation_state(
            kb_id="kb-auto",
            profile="general",
        )
        internal_state = storage.get_agentic_ready_automation_state(
            kb_id="kb-auto",
            profile="general",
            include_claim_token=True,
        )
    finally:
        storage.close()
    assert abandoned and abandoned["claim_token"] == "abandoned"
    assert public_state["claim_token"] is None
    assert internal_state["claim_token"] == "abandoned"

    recovered = run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=_builder([]),
        validator=_valid,
        lease_seconds=30,
        heartbeat_interval_seconds=0,
        clock=lambda: started + timedelta(seconds=31),
    )

    assert recovered["status"] == "awaiting_publish"
    assert recovered["claim_token"] != "abandoned"


@pytest.mark.parametrize(
    ("reason", "serving_allowed"),
    [("chunk_content_updated", True), ("membership_removed", False)],
)
def test_build_only_keeps_existing_soft_or_hard_stale_serving_rule(
    tmp_path: Path,
    reason: str,
    serving_allowed: bool,
) -> None:
    db_path = tmp_path / "index.db"
    storage = Storage(str(db_path))
    try:
        _create_kb(storage)
        active = _publish_seed(storage, tmp_path)
        _set_automation(storage, build=True, publish=False)
        _mark_event(storage, reason=reason)
    finally:
        storage.close()

    run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=_builder([]),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    storage = Storage(str(db_path))
    try:
        publication = storage.get_agentic_ready_publication_state(
            kb_id="kb-auto", profile="general"
        )
        source = storage.get_agentic_ready_source_state(kb_id="kb-auto", profile="general")
        assert publication["active_publication_id"] == active["publication_id"]
        assert source["serving_allowed"] is serving_allowed
    finally:
        storage.close()


def test_automatic_execution_never_enables_or_runs_gc(tmp_path: Path) -> None:
    db_path = _setup_pending(tmp_path, publish=True)

    result = run_ready_data_automation_once(
        db_path=str(db_path),
        build_candidate=_builder([]),
        validator=_valid,
        heartbeat_interval_seconds=0,
    )

    storage = Storage(str(db_path))
    try:
        candidate = storage.get_agentic_ready_publication(
            str(result["candidate_publication"]["publication_id"])
        )
        assert not candidate["gc_state"]
        assert candidate["attempt_disposition"] == ""
        assert storage._conn.execute(
            "SELECT COUNT(*) FROM agentic_ready_publication_gc"
        ).fetchone()[0] == 0
    finally:
        storage.close()


def test_scheduler_registers_nonblocking_injected_automation_wakeup(tmp_path: Path) -> None:
    invoked = threading.Event()
    release = threading.Event()

    def runner(*, db_path: str) -> dict[str, Any]:
        assert db_path == str(tmp_path / "index.db")
        invoked.set()
        assert release.wait(timeout=5)
        return {"status": "idle"}

    runtime = NativeTaskRuntime(
        ready_data_db_path=str(tmp_path / "index.db"),
        ready_data_poll_interval_seconds=7,
        ready_data_runner=runner,
    )
    runtime.init_scheduler()
    jobs = [job for job in runtime.scheduler.jobs if getattr(job, "unit", "") == "seconds"]

    assert len(jobs) == 1
    assert jobs[0].interval == 7
    jobs[0].job_func()
    assert invoked.wait(timeout=5)
    jobs[0].job_func()
    release.set()


def test_scheduler_loop_honors_injected_automation_poll_interval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_sleeps: list[float] = []

    class StopSchedulerLoop(Exception):
        pass

    def stop_after_first_sleep(seconds: float) -> None:
        observed_sleeps.append(seconds)
        raise StopSchedulerLoop

    runtime = NativeTaskRuntime(
        ready_data_db_path=str(tmp_path / "index.db"),
        ready_data_poll_interval_seconds=7,
    )
    monkeypatch.setattr(task_runtime_module.time, "sleep", stop_after_first_sleep)

    with pytest.raises(StopSchedulerLoop):
        runtime._scheduler_loop()

    assert observed_sleeps == [7]


def test_automation_api_is_permission_protected_and_kb_scoped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "index.db"
    config_path = tmp_path / "sites.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "paths": {"db": str(db_path)},
                "defaults": {},
                "sites": [],
                "scheduled_tasks": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("FASTAPI_SESSION_SECRET", "automation-test-secret")
    storage = Storage(str(db_path))
    try:
        _create_kb(storage, "kb-one")
        _create_kb(storage, "kb-two")
        storage.upsert_auth_token_by_hash(
            subject="admin",
            group_name="admin",
            token_hash=hashlib.sha256(b"admin-token").hexdigest(),
            is_active=True,
        )
    finally:
        storage.close()
    client = TestClient(create_app())
    url = "/api/rag/knowledge-bases/kb-one/agentic-ready-automation"
    payload = {
        "profile": "general",
        "automatic_build_enabled": True,
        "automatic_publish_enabled": False,
    }

    assert client.put(url, json=payload).status_code == 401
    response = client.put(url, json=payload, headers={"X-Auth-Token": "admin-token"})

    assert response.status_code == 200
    assert response.json()["automation"]["automatic_build_enabled"] is True
    assert response.json()["automation"]["claim_token"] is None
    storage = Storage(str(db_path))
    try:
        assert storage.get_agentic_ready_publication_state(
            kb_id="kb-one", profile="general"
        )["automatic_build_enabled"] is True
        assert storage.get_agentic_ready_publication_state(
            kb_id="kb-two", profile="general"
        )["automatic_build_enabled"] is False
    finally:
        storage.close()
