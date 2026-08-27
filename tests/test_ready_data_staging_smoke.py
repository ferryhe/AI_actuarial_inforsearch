from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from ai_actuarial.agentic_rag import ready_data_builder
from ai_actuarial.api.services import rag_admin as rag_admin_service
from ai_actuarial.api.services import ready_data_publication as publication_service
from ai_actuarial.api.services.rag_admin import (
    _build_agentic_ready_manifest_core,
    _ready_data_artifact_digest,
)
from ai_actuarial.api.services.ready_data_automation import (
    run_ready_data_automation_once,
)
from ai_actuarial.rag.kb_index import resolve_kb_bound_chunks
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.sqlite_schema import schema_status
from ai_actuarial.storage import Storage
from ai_actuarial.task_runtime import NativeTaskRuntime


def _create_kb(
    storage: Storage,
    tmp_path: Path,
    *,
    kb_id: str,
    with_document: bool,
    manifest_profile: str = "general",
) -> None:
    KnowledgeBaseManager(storage).create_kb(
        kb_id=kb_id,
        name=f"Smoke {kb_id}",
        kb_mode="manual",
        manifest_profile=manifest_profile,
        embedding_provider="test",
        embedding_model="smoke-model",
        embedding_dimension=3,
        embedding_identity_key="emb-smoke-v1",
    )
    if not with_document:
        return
    file_url = f"https://example.com/{kb_id}"
    local_path = tmp_path / f"{kb_id}.pdf"
    local_path.write_bytes(b"ready-data staging smoke fixture")
    storage.insert_file(
        url=file_url,
        sha256=f"sha-{kb_id}",
        title=f"Deterministic {kb_id} Rule",
        source_site="example.com",
        source_page_url="https://example.com",
        original_filename=local_path.name,
        local_path=str(local_path),
        bytes=local_path.stat().st_size,
        content_type="application/pdf",
        published_time="2026-08-19",
    )
    storage.upsert_catalog_item(
        {
            "url": file_url,
            "sha256": f"sha-{kb_id}",
            "keywords": ["deterministic", "smoke"],
            "summary": f"Deterministic staging smoke summary for {kb_id}",
            "category": "regulation",
        },
        pipeline_version="staging-smoke-test-v1",
        status="ok",
    )
    now = "2026-08-19T00:00:00+00:00"
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
            (
                f"cs-{kb_id}",
                file_url,
                f"cp-{kb_id}",
                f"md-{kb_id}",
                now,
                now,
            ),
        )
        storage._conn.execute(
            """
            INSERT INTO global_chunks(
                chunk_id, chunk_set_id, chunk_index, content,
                token_count, section_hierarchy, content_hash, created_at
            ) VALUES (?, ?, 0, ?, 6, ?, ?, ?)
            """,
            (
                f"chunk-{kb_id}",
                f"cs-{kb_id}",
                f"Deterministic evidence for {kb_id}",
                "Main > Evidence",
                f"content-{kb_id}",
                now,
            ),
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
        embedding_model="smoke-model",
        embedding_dimension=3,
        embedding_identity_key="emb-smoke-v1",
        binding_snapshot_fingerprint=str(
            snapshot["binding_snapshot_fingerprint"]
        ),
        index_type="faiss",
        chunk_count=1,
        artifact_path=str(tmp_path / "indexes" / kb_id),
        artifact_digest=f"digest-{kb_id}",
        chunk_ids=[f"chunk-{kb_id}"],
        status="ready",
    )


def _setup_db(
    tmp_path: Path,
    *,
    kb_id: str = "kb-smoke",
    with_document: bool = True,
    manifest_profile: str = "general",
) -> Path:
    db_path = tmp_path / "index.db"
    storage = Storage(str(db_path))
    try:
        _create_kb(
            storage,
            tmp_path,
            kb_id=kb_id,
            with_document=with_document,
            manifest_profile=manifest_profile,
        )
    finally:
        storage.close()
    return db_path


def _passed_smoke(*, query: str = "Synthetic deterministic query") -> dict[str, Any]:
    return {
        "contract_version": "ready-data-staging-smoke.v1",
        "status": "passed",
        "checked_at": "2026-08-19T00:00:00+00:00",
        "elapsed_ms": 1,
        "query_source": "title",
        "query": query,
        "query_sha256": "a" * 64,
        "matched_doc_id": "doc",
        "matched_file_url": "https://example.com/doc",
        "failure_reason": "",
        "catalog_doc_count": 1,
    }


def _failed_smoke(reason: str = "no_evidence") -> dict[str, Any]:
    result = _passed_smoke()
    result.update(
        {
            "status": "failed",
            "matched_doc_id": "",
            "matched_file_url": "",
            "failure_reason": reason,
        }
    )
    return result


def _ready_input(db_path: Path, kb_id: str) -> dict[str, str]:
    storage = Storage(str(db_path))
    try:
        row = storage._conn.execute(
            "SELECT index_version_id FROM kb_ready_index_state WHERE kb_id = ?",
            (kb_id,),
        ).fetchone()
    finally:
        storage.close()
    if not row:
        raise ValueError("invalid_selector: Ready Data requires a committed KB index")
    index_version_id = str(row[0])
    source = ready_data_builder.get_builder_source_fingerprint(
        db_path=str(db_path),
        kb_id=kb_id,
        profile="general",
        index_version_id=index_version_id,
    )
    return {
        "index_version_id": index_version_id,
        "expected_source_snapshot_fingerprint": source[
            "source_snapshot_fingerprint"
        ],
    }


def _manual_build(
    db_path: Path,
    kb_id: str,
    *,
    should_stop=None,
) -> dict[str, Any]:
    return _build_agentic_ready_manifest_core(
        db_path=str(db_path),
        kb_id=kb_id,
        payload={"profile": "general", **_ready_input(db_path, kb_id)},
        publish=True,
        should_stop=should_stop,
    )


def _enable_automation(
    db_path: Path,
    *,
    kb_id: str,
    publish: bool,
    profile: str = "general",
) -> None:
    storage = Storage(str(db_path))
    try:
        storage.set_agentic_ready_automation(
            kb_id=kb_id,
            profile=profile,
            automatic_build_enabled=True,
            automatic_publish_enabled=publish,
        )
        storage.mark_agentic_ready_source_event(
            kb_id=kb_id,
            profile=profile,
            reason="membership_added",
        )
    finally:
        storage.close()


def test_manual_build_persists_passed_smoke_before_publication(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path)

    result = _manual_build(db_path, "kb-smoke")

    candidate = result["candidate_publication"]
    assert result["validation"]["valid"] is True
    assert candidate["status"] == "active"
    assert candidate["smoke_result"]["status"] == "passed"
    assert candidate["smoke_result"]["matched_doc_id"] == "https://example.com/kb-smoke"
    assert result["publication_state"]["active_publication_id"] == candidate["publication_id"]


def _validated_manual_candidate(
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    kb_id: str = "kb-smoke",
) -> dict[str, Any]:
    monkeypatch.setattr(rag_admin_service, "run_staging_smoke", lambda **_kwargs: _passed_smoke())
    return _build_agentic_ready_manifest_core(
        db_path=str(db_path),
        kb_id=kb_id,
        payload={"profile": "general", **_ready_input(db_path, kb_id)},
        publish=False,
    )


def test_explicit_ready_publish_promotes_validated_manual_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup_db(tmp_path)
    built = _validated_manual_candidate(db_path, monkeypatch)
    candidate_id = str(built["candidate_publication"]["publication_id"])
    expected_ready_input = _ready_input(db_path, "kb-smoke")

    storage = Storage(str(db_path))
    try:
        pending = publication_service.read_public_ready_data_snapshot(
            storage,
            kb_id="kb-smoke",
            profile="general",
            include_legacy_output_dir=False,
        )
    finally:
        storage.close()

    assert pending["manifest"]["automation_state"] == "awaiting_publish"
    assert pending["manifest"]["last_attempt_publication_id"] == candidate_id
    assert pending["manifest"]["ready_build_input"] == {
        "contract_version": 1,
        **expected_ready_input,
    }
    assert pending["publication_state"]["automatic_build_enabled"] is False
    assert pending["publication_state"]["automatic_publish_enabled"] is False

    result = publication_service.publish_ready_data_publication(
        db_path=str(db_path),
        kb_id="kb-smoke",
        payload={
            "profile": "general",
            "publication_id": candidate_id,
            "expected_active_publication_id": None,
        },
    )

    assert result == {
        "kb_id": "kb-smoke",
        "profile": "general",
        "publication_id": candidate_id,
        "publish_status": "published",
        "active_publication_id": candidate_id,
    }
    storage = Storage(str(db_path))
    try:
        published = publication_service.read_public_ready_data_snapshot(
            storage,
            kb_id="kb-smoke",
            profile="general",
            include_legacy_output_dir=False,
        )
    finally:
        storage.close()
    assert published["manifest"]["automation_state"] == "succeeded"
    assert published["manifest"]["last_attempt_publication_id"] == candidate_id
    assert published["publication_state"]["active_publication_id"] == candidate_id


def test_newer_manual_ready_source_supersedes_older_awaiting_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup_db(tmp_path)
    first = _validated_manual_candidate(db_path, monkeypatch)
    first_id = str(first["candidate_publication"]["publication_id"])
    storage = Storage(str(db_path))
    try:
        with storage.transaction(immediate=True):
            storage._conn.execute(
                "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
                ("new manual ready source", "https://example.com/kb-smoke"),
            )
            storage.mark_agentic_ready_source_event(
                kb_id="kb-smoke",
                profile="general",
                reason="metadata_updated",
            )
    finally:
        storage.close()

    second = _validated_manual_candidate(db_path, monkeypatch)
    second_id = str(second["candidate_publication"]["publication_id"])

    storage = Storage(str(db_path))
    try:
        prior = storage.get_agentic_ready_publication(first_id)
        automation = storage.get_agentic_ready_automation_state(
            kb_id="kb-smoke",
            profile="general",
        )
    finally:
        storage.close()
    assert prior["attempt_disposition"] == "superseded_generation"
    assert automation["automation_state"] == "awaiting_publish"
    assert automation["last_attempt_publication_id"] == second_id


@pytest.mark.parametrize("failure", ["source", "index", "artifact", "cas"])
def test_explicit_ready_publish_failure_preserves_active_pointer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    db_path = _setup_db(tmp_path)
    active = _manual_build(db_path, "kb-smoke")
    active_id = str(active["publication_state"]["active_publication_id"])
    built = _validated_manual_candidate(db_path, monkeypatch)
    candidate = dict(built["candidate_publication"])
    expected_active: str | None = active_id

    storage = Storage(str(db_path))
    try:
        if failure == "source":
            storage._conn.execute(
                "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
                ("source changed", "https://example.com/kb-smoke"),
            )
            storage._conn.commit()
        elif failure == "index":
            snapshot = resolve_kb_bound_chunks(storage, "kb-smoke")
            storage.create_kb_index_version(
                kb_id="kb-smoke",
                embedding_provider="test",
                embedding_model="smoke-model",
                embedding_dimension=3,
                embedding_identity_key="emb-smoke-v1",
                binding_snapshot_fingerprint=str(snapshot["binding_snapshot_fingerprint"]),
                index_type="faiss",
                chunk_count=1,
                artifact_path=str(tmp_path / "indexes" / "kb-smoke-new"),
                artifact_digest="digest-new",
                chunk_ids=["chunk-kb-smoke"],
                status="ready",
            )
        elif failure == "artifact":
            (Path(str(candidate["output_dir"])) / "doc_catalog.jsonl").write_text(
                "tampered\n", encoding="utf-8"
            )
        else:
            expected_active = None
    finally:
        storage.close()

    with pytest.raises(rag_admin_service.RagAdminError) as exc_info:
        publication_service.publish_ready_data_publication(
            db_path=str(db_path),
            kb_id="kb-smoke",
            payload={
                "profile": "general",
                "publication_id": candidate["publication_id"],
                "expected_active_publication_id": expected_active,
            },
        )

    assert exc_info.value.status_code in {409, 422}
    storage = Storage(str(db_path))
    try:
        state = storage.get_agentic_ready_publication_state(
            kb_id="kb-smoke", profile="general"
        )
        assert state["active_publication_id"] == active_id
    finally:
        storage.close()


def test_explicit_ready_publish_rechecks_source_inside_cas_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup_db(tmp_path)
    active = _manual_build(db_path, "kb-smoke")
    active_id = str(active["publication_state"]["active_publication_id"])
    built = _validated_manual_candidate(db_path, monkeypatch)
    candidate_id = str(built["candidate_publication"]["publication_id"])

    service_parts = publication_service._manager_and_storage(str(db_path))
    service_storage = service_parts[2]
    original_transaction = service_storage.transaction

    @contextmanager
    def source_race_transaction(*args: Any, **kwargs: Any):
        service_storage._conn.execute(
            "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
            ("source changed at publish transaction", "https://example.com/kb-smoke"),
        )
        service_storage._conn.commit()
        with original_transaction(*args, **kwargs):
            yield

    monkeypatch.setattr(service_storage, "transaction", source_race_transaction)
    monkeypatch.setattr(
        publication_service,
        "_manager_and_storage",
        lambda _db_path: service_parts,
    )

    with pytest.raises(rag_admin_service.RagAdminError) as exc_info:
        publication_service.publish_ready_data_publication(
            db_path=str(db_path),
            kb_id="kb-smoke",
            payload={
                "profile": "general",
                "publication_id": candidate_id,
                "expected_active_publication_id": active_id,
            },
        )

    assert exc_info.value.status_code == 409
    assert str(exc_info.value).startswith("stale_snapshot:")
    storage = Storage(str(db_path))
    try:
        state = storage.get_agentic_ready_publication_state(
            kb_id="kb-smoke", profile="general"
        )
        assert state["active_publication_id"] == active_id
        assert storage.get_agentic_ready_publication(candidate_id)["status"] == "validated"
    finally:
        storage.close()


def test_manual_build_rechecks_source_after_smoke_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup_db(tmp_path)
    first = _manual_build(db_path, "kb-smoke")
    storage = Storage(str(db_path))
    try:
        storage._conn.execute(
            "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
            ("source before raced build", "https://example.com/kb-smoke"),
        )
        storage._conn.commit()
    finally:
        storage.close()

    def smoke_then_change_source(**_kwargs: Any) -> dict[str, Any]:
        concurrent = Storage(str(db_path))
        try:
            concurrent._conn.execute(
                "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
                ("source changed during smoke", "https://example.com/kb-smoke"),
            )
            concurrent._conn.commit()
        finally:
            concurrent.close()
        return _passed_smoke()

    monkeypatch.setattr(
        rag_admin_service,
        "run_staging_smoke",
        smoke_then_change_source,
    )

    raced = _manual_build(db_path, "kb-smoke")

    assert raced["validation"]["valid"] is False
    assert raced["validation"]["errors"] == [
        "stale_snapshot: Ready Data source changed before publication"
    ]
    assert (
        raced["publication_state"]["active_publication_id"]
        == first["publication_state"]["active_publication_id"]
    )


def test_automatic_publish_rechecks_source_after_smoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup_db(tmp_path)
    _enable_automation(db_path, kb_id="kb-smoke", publish=True)

    def smoke_then_change_source(**_kwargs: Any) -> dict[str, Any]:
        concurrent = Storage(str(db_path))
        try:
            concurrent._conn.execute(
                "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
                ("automatic source changed during smoke", "https://example.com/kb-smoke"),
            )
            concurrent._conn.commit()
        finally:
            concurrent.close()
        return _passed_smoke()

    monkeypatch.setattr(
        rag_admin_service,
        "run_staging_smoke",
        smoke_then_change_source,
    )

    raced = run_ready_data_automation_once(
        str(db_path),
        heartbeat_interval_seconds=0,
    )

    assert raced["status"] == "failed"
    assert raced["error"] == (
        "stale_snapshot: Ready Data source changed before publication"
    )
    storage = Storage(str(db_path))
    try:
        state = storage.get_agentic_ready_publication_state(
            kb_id="kb-smoke",
            profile="general",
        )
    finally:
        storage.close()
    assert state["active_publication_id"] is None


def test_automation_resolves_source_for_selected_manifest_profile(
    tmp_path: Path,
) -> None:
    db_path = _setup_db(tmp_path, manifest_profile="regulation")
    _enable_automation(
        db_path,
        kb_id="kb-smoke",
        publish=False,
        profile="regulation",
    )

    result = run_ready_data_automation_once(
        str(db_path),
        heartbeat_interval_seconds=0,
    )

    assert result["status"] == "awaiting_publish"
    assert result["candidate_publication"]["profile"] == "regulation"


def test_ready_core_requires_explicit_index_and_source_contract(
    tmp_path: Path,
) -> None:
    db_path = _setup_db(tmp_path)

    with pytest.raises(
        rag_admin_service.RagAdminError,
        match="invalid_selector: Ready Data requires index_version_id and "
        "expected_source_snapshot_fingerprint",
    ):
        _build_agentic_ready_manifest_core(
            db_path=str(db_path),
            kb_id="kb-smoke",
            payload={"profile": "general"},
            publish=True,
        )


def test_ready_task_stop_preserves_active_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup_db(tmp_path)
    active = _manual_build(db_path, "kb-smoke")
    source_storage = Storage(str(db_path))
    try:
        source_storage._conn.execute(
            "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
            ("Ready task stop source", "https://example.com/kb-smoke"),
        )
        source_storage._conn.commit()
    finally:
        source_storage.close()
    ready_input = _ready_input(db_path, "kb-smoke")
    runtime = NativeTaskRuntime(ready_data_db_path=str(db_path))
    task_id = "task-ready-stop"
    runtime.active_tasks[task_id] = {"stop_requested": False}

    def smoke_then_stop(**_kwargs: Any) -> dict[str, Any]:
        runtime.active_tasks[task_id]["stop_requested"] = True
        return _passed_smoke()

    monkeypatch.setattr(rag_admin_service, "run_staging_smoke", smoke_then_stop)

    task_storage = Storage(str(db_path))
    try:
        stopped = runtime._run_ready_data_build(
            task_id,
            task_storage,
            str(db_path),
            {
            "contract_version": 1,
            "kb_id": "kb-smoke",
            "profile": "general",
            **ready_input,
        },
        )
    finally:
        task_storage.close()

    assert stopped.success is False
    assert stopped.metadata["stopped"] is True
    storage = Storage(str(db_path))
    try:
        state = storage.get_agentic_ready_publication_state(
            kb_id="kb-smoke",
            profile="general",
        )
    finally:
        storage.close()
    assert state["active_publication_id"] == active["publication_state"][
        "active_publication_id"
    ]


def test_builder_classifies_prebuild_source_change_as_stale_snapshot(
    tmp_path: Path,
) -> None:
    db_path = _setup_db(tmp_path)
    ready_input = _ready_input(db_path, "kb-smoke")

    with pytest.raises(ValueError, match="^stale_snapshot:"):
        ready_data_builder.build_l0(
            db_path=str(db_path),
            output_dir=str(tmp_path / "stale-builder"),
            profile="general",
            kb_id="kb-smoke",
            index_version_id=ready_input["index_version_id"],
            expected_source_snapshot_fingerprint="rdsnap_wrong",
        )


def test_smoke_failure_keeps_active_and_previous_unchanged_and_cleans_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup_db(tmp_path)
    first = _manual_build(db_path, "kb-smoke")
    staging_root = (
        tmp_path
        / "agentic_ready_data"
        / "kbs"
        / "kb-smoke"
        / "general"
        / "1"
        / "staging"
    )
    staging_before_failure = sorted(staging_root.glob("build-*"))
    storage = Storage(str(db_path))
    try:
        before = storage.get_agentic_ready_publication_state(
            kb_id="kb-smoke",
            profile="general",
        )
        storage._conn.execute(
            "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
            (
                "Changed summary creates a new source snapshot",
                "https://example.com/kb-smoke",
            ),
        )
        storage._conn.commit()
    finally:
        storage.close()
    monkeypatch.setattr(rag_admin_service, "run_staging_smoke", lambda **_kwargs: _failed_smoke())

    failed = _manual_build(db_path, "kb-smoke")

    storage = Storage(str(db_path))
    try:
        after = storage.get_agentic_ready_publication_state(
            kb_id="kb-smoke",
            profile="general",
        )
        persisted = storage.get_agentic_ready_publication(
            str(failed["candidate_publication"]["publication_id"])
        )
    finally:
        storage.close()
    assert first["candidate_publication"]["publication_id"] == before["active_publication_id"]
    assert after["active_publication_id"] == before["active_publication_id"]
    assert after["previous_publication_id"] == before["previous_publication_id"]
    assert failed["validation"]["valid"] is False
    assert failed["validation"]["errors"] == [
        "ready_data staging smoke failed: no_evidence"
    ]
    assert persisted is not None
    assert persisted["status"] == "failed"
    assert persisted["smoke_result"]["failure_reason"] == "no_evidence"
    assert sorted(staging_root.glob("build-*")) == staging_before_failure


def test_unexpected_smoke_exception_is_fail_closed_and_does_not_leak_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup_db(tmp_path)
    first = _manual_build(db_path, "kb-smoke")
    storage = Storage(str(db_path))
    try:
        before = storage.get_agentic_ready_publication_state(
            kb_id="kb-smoke",
            profile="general",
        )
        storage._conn.execute(
            "UPDATE catalog_items SET summary = ? WHERE file_url = ?",
            (
                "Changed summary creates another source snapshot",
                "https://example.com/kb-smoke",
            ),
        )
        storage._conn.commit()
    finally:
        storage.close()

    sensitive_detail = "sensitive document body " + ("x" * 500)

    def raise_unexpected(**_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError(sensitive_detail)

    monkeypatch.setattr(rag_admin_service, "run_staging_smoke", raise_unexpected)

    failed = _manual_build(db_path, "kb-smoke")

    storage = Storage(str(db_path))
    try:
        after = storage.get_agentic_ready_publication_state(
            kb_id="kb-smoke",
            profile="general",
        )
        persisted = storage.get_agentic_ready_publication(
            str(failed["candidate_publication"]["publication_id"])
        )
    finally:
        storage.close()
    assert before["active_publication_id"] == first["candidate_publication"]["publication_id"]
    assert after["active_publication_id"] == before["active_publication_id"]
    assert after["previous_publication_id"] == before["previous_publication_id"]
    assert failed["validation"]["errors"] == [
        "ready_data staging smoke failed: smoke_execution_failed"
    ]
    assert persisted is not None
    assert persisted["status"] == "failed"
    assert persisted["smoke_result"]["failure_reason"] == "smoke_execution_failed"
    assert sensitive_detail not in json.dumps(persisted, sort_keys=True)


@pytest.mark.parametrize(
    ("status", "catalog_doc_count"),
    [
        ("not_run", 1),
        ("", 1),
        ("passed", 0),
        ("skipped_empty", 1),
    ],
)
def test_unexpected_smoke_status_is_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    catalog_doc_count: int,
) -> None:
    db_path = _setup_db(tmp_path)
    smoke_result = _passed_smoke()
    smoke_result.update(
        {
            "status": status,
            "catalog_doc_count": catalog_doc_count,
            "failure_reason": "",
        }
    )
    monkeypatch.setattr(
        rag_admin_service,
        "run_staging_smoke",
        lambda **_kwargs: smoke_result,
    )

    failed = _manual_build(db_path, "kb-smoke")

    assert failed["validation"]["valid"] is False
    assert failed["validation"]["errors"] == [
        "ready_data staging smoke failed: invalid_smoke_status"
    ]
    assert failed["candidate_publication"]["status"] == "failed"
    assert failed["publication_state"]["active_publication_id"] is None
    assert failed["publication_state"]["previous_publication_id"] is None


@pytest.mark.parametrize(
    ("updates", "expected_reason"),
    [
        ({"contract_version": "wrong-contract"}, "invalid_smoke_contract"),
        (
            {"matched_doc_id": "", "matched_file_url": ""},
            "catalog_reference_missing",
        ),
    ],
)
def test_incomplete_passed_smoke_is_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    updates: dict[str, Any],
    expected_reason: str,
) -> None:
    db_path = _setup_db(tmp_path)
    smoke_result = _passed_smoke()
    smoke_result.update(updates)
    monkeypatch.setattr(
        rag_admin_service,
        "run_staging_smoke",
        lambda **_kwargs: smoke_result,
    )

    failed = _manual_build(db_path, "kb-smoke")

    assert failed["validation"]["errors"] == [
        f"ready_data staging smoke failed: {expected_reason}"
    ]
    assert failed["candidate_publication"]["status"] == "failed"
    assert failed["publication_state"]["active_publication_id"] is None


def test_manual_and_automatic_build_share_the_same_smoke_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup_db(tmp_path, kb_id="kb-manual")
    storage = Storage(str(db_path))
    try:
        _create_kb(storage, tmp_path, kb_id="kb-auto", with_document=True)
    finally:
        storage.close()
    calls: list[str] = []

    def smoke_spy(**kwargs: Any) -> dict[str, Any]:
        calls.append(str(kwargs["kb_id"]))
        return _passed_smoke(query=f"query for {kwargs['kb_id']}")

    monkeypatch.setattr(rag_admin_service, "run_staging_smoke", smoke_spy)

    _manual_build(db_path, "kb-manual")
    _enable_automation(db_path, kb_id="kb-auto", publish=False)
    automatic = run_ready_data_automation_once(
        str(db_path),
        heartbeat_interval_seconds=0,
    )

    assert automatic["status"] == "awaiting_publish"
    assert calls == ["kb-manual", "kb-auto"]


def test_active_revalidation_does_not_repeat_staging_smoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup_db(tmp_path)
    calls: list[str] = []

    def smoke_spy(**kwargs: Any) -> dict[str, Any]:
        calls.append(str(kwargs["output_dir"]))
        return _passed_smoke()

    monkeypatch.setattr(rag_admin_service, "run_staging_smoke", smoke_spy)

    _manual_build(db_path, "kb-smoke")
    _manual_build(db_path, "kb-smoke")

    assert len(calls) == 2
    assert calls[0] != calls[1]


def test_automatic_smoke_failure_finishes_claim_as_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup_db(tmp_path)
    _enable_automation(db_path, kb_id="kb-smoke", publish=True)
    monkeypatch.setattr(
        rag_admin_service,
        "run_staging_smoke",
        lambda **_kwargs: _failed_smoke("catalog_reference_missing"),
    )

    result = run_ready_data_automation_once(
        str(db_path),
        heartbeat_interval_seconds=0,
    )

    storage = Storage(str(db_path))
    try:
        automation = storage.get_agentic_ready_automation_state(
            kb_id="kb-smoke",
            profile="general",
            include_claim_token=True,
        )
        publication_state = storage.get_agentic_ready_publication_state(
            kb_id="kb-smoke",
            profile="general",
        )
    finally:
        storage.close()
    assert result["status"] == "failed"
    assert result["error"] == "ready_data staging smoke failed: catalog_reference_missing"
    assert automation["automation_state"] == "failed"
    assert automation["claim_token"] is None
    assert publication_state["active_publication_id"] is None
    assert publication_state["previous_publication_id"] is None


def test_manual_build_rejects_empty_kb_without_committed_index(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path, with_document=False)

    with pytest.raises(
        ValueError,
        match="invalid_selector: Ready Data requires a committed KB index",
    ):
        _manual_build(db_path, "kb-smoke")


def test_automatic_publish_rejects_empty_kb_without_committed_index(
    tmp_path: Path,
) -> None:
    db_path = _setup_db(tmp_path, with_document=False)
    _enable_automation(db_path, kb_id="kb-smoke", publish=True)

    first = run_ready_data_automation_once(
        str(db_path),
        heartbeat_interval_seconds=0,
    )
    second = run_ready_data_automation_once(
        str(db_path),
        heartbeat_interval_seconds=0,
    )

    storage = Storage(str(db_path))
    try:
        automation = storage.get_agentic_ready_automation_state(
            kb_id="kb-smoke",
            profile="general",
        )
        state = storage.get_agentic_ready_publication_state(
            kb_id="kb-smoke",
            profile="general",
        )
    finally:
        storage.close()
    assert first["status"] == "failed"
    assert "non-empty KB membership" in first["error"]
    assert second == {"status": "idle"}
    assert automation["automation_state"] == "failed"
    assert "non-empty KB membership" in automation["last_error"]
    assert state["active_publication_id"] is None
    assert state["previous_publication_id"] is None


def test_empty_kb_build_only_fails_closed_before_publish_toggle(
    tmp_path: Path,
) -> None:
    db_path = _setup_db(tmp_path, with_document=False)
    _enable_automation(db_path, kb_id="kb-smoke", publish=False)
    failed = run_ready_data_automation_once(
        str(db_path),
        heartbeat_interval_seconds=0,
    )
    storage = Storage(str(db_path))
    try:
        storage.set_agentic_ready_automation(
            kb_id="kb-smoke",
            profile="general",
            automatic_build_enabled=True,
            automatic_publish_enabled=True,
        )
    finally:
        storage.close()

    idle = run_ready_data_automation_once(
        str(db_path),
        heartbeat_interval_seconds=0,
    )

    assert failed["status"] == "failed"
    assert "non-empty KB membership" in failed["error"]
    assert idle == {"status": "idle"}


@pytest.mark.parametrize(
    "stored_smoke_json",
    [
        "{}",
        "{malformed",
        json.dumps(
            {
                "contract_version": "ready-data-staging-smoke.v1",
                "status": "passed",
                "catalog_doc_count": 1,
            }
        ),
        json.dumps(
            {
                "contract_version": "wrong-contract",
                "status": "passed",
                "catalog_doc_count": 1,
                "matched_doc_id": "doc",
            }
        ),
    ],
)
def test_unproven_legacy_candidate_is_not_claimed_for_automatic_publish(
    tmp_path: Path,
    stored_smoke_json: str,
) -> None:
    db_path = _setup_db(tmp_path)
    _enable_automation(db_path, kb_id="kb-smoke", publish=False)
    built = run_ready_data_automation_once(
        str(db_path),
        heartbeat_interval_seconds=0,
    )
    storage = Storage(str(db_path))
    try:
        storage._conn.execute(
            "UPDATE agentic_ready_publications SET smoke_result_json = ? "
            "WHERE publication_id = ?",
            (stored_smoke_json, built["candidate_publication"]["publication_id"]),
        )
        storage._conn.commit()
        storage.set_agentic_ready_automation(
            kb_id="kb-smoke",
            profile="general",
            automatic_build_enabled=True,
            automatic_publish_enabled=True,
        )
    finally:
        storage.close()

    result = run_ready_data_automation_once(
        str(db_path),
        heartbeat_interval_seconds=0,
    )
    storage = Storage(str(db_path))
    try:
        automation = storage.get_agentic_ready_automation_state(
            kb_id="kb-smoke",
            profile="general",
        )
        state = storage.get_agentic_ready_publication_state(
            kb_id="kb-smoke",
            profile="general",
        )
    finally:
        storage.close()

    assert result == {"status": "idle"}
    assert automation["automation_state"] == "awaiting_publish"
    assert state["active_publication_id"] is None
    assert state["previous_publication_id"] is None


def test_automatic_empty_kb_fails_before_custom_builder_is_called(
    tmp_path: Path,
) -> None:
    db_path = _setup_db(tmp_path, with_document=False)
    _enable_automation(db_path, kb_id="kb-smoke", publish=True)

    called = False

    def unexpected_builder(**_kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("empty KB must fail before build")

    result = run_ready_data_automation_once(
        str(db_path),
        build_candidate=unexpected_builder,
        heartbeat_interval_seconds=0,
    )

    assert result["status"] == "failed"
    assert "non-empty KB membership" in result["error"]
    assert called is False
    storage = Storage(str(db_path))
    try:
        state = storage.get_agentic_ready_publication_state(
            kb_id="kb-smoke",
            profile="general",
        )
    finally:
        storage.close()
    assert state["active_publication_id"] is None


def test_generation_change_during_smoke_is_still_stopped_by_existing_fence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup_db(tmp_path)
    _enable_automation(db_path, kb_id="kb-smoke", publish=True)
    changed = False

    def smoke_then_change_generation(**_kwargs: Any) -> dict[str, Any]:
        nonlocal changed
        if not changed:
            changed = True
            concurrent = Storage(str(db_path))
            try:
                concurrent.mark_agentic_ready_source_event(
                    kb_id="kb-smoke",
                    profile="general",
                    reason="metadata_updated",
                )
            finally:
                concurrent.close()
        return _passed_smoke()

    monkeypatch.setattr(
        rag_admin_service,
        "run_staging_smoke",
        smoke_then_change_generation,
    )

    result = run_ready_data_automation_once(
        str(db_path),
        heartbeat_interval_seconds=0,
    )

    assert result["status"] == "superseded"
    assert result["candidate_publication"]["attempt_disposition"] == "superseded_generation"
    storage = Storage(str(db_path))
    try:
        state = storage.get_agentic_ready_publication_state(
            kb_id="kb-smoke",
            profile="general",
        )
    finally:
        storage.close()
    assert state["active_publication_id"] is None


def test_active_pointer_change_during_smoke_loses_expected_active_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = _setup_db(tmp_path)
    _enable_automation(db_path, kb_id="kb-smoke", publish=True)
    competitor_id = ""

    def smoke_then_publish_competitor(**_kwargs: Any) -> dict[str, Any]:
        nonlocal competitor_id
        if competitor_id:
            return _passed_smoke()
        competitor_dir = (
            tmp_path
            / "agentic_ready_data"
            / "competitor"
        )
        manifest = ready_data_builder.build_l0(
            db_path=str(db_path),
            output_dir=str(competitor_dir),
            profile="general",
            kb_id="kb-smoke",
            **_ready_input(db_path, "kb-smoke"),
        )
        artifacts = list(manifest["artifact_files"])
        storage = Storage(str(db_path))
        try:
            competitor = storage.record_agentic_ready_publication(
                kb_id="kb-smoke",
                index_version_id=_ready_input(db_path, "kb-smoke")[
                    "index_version_id"
                ],
                source_version_kind=str(manifest["source_version_kind"]),
                source_version_id=str(manifest["source_version_id"]),
                profile="general",
                profile_version="1",
                status="validated",
                output_dir=str(competitor_dir),
                artifact_files=artifacts,
                doc_count=int(manifest["doc_count"]),
                section_count=int(manifest["section_count"]),
                built_at=str(manifest["built_at"]),
                artifact_digest=_ready_data_artifact_digest(
                    str(competitor_dir),
                    artifacts,
                ),
                source_db=str(db_path),
                schema_versions=dict(manifest["schema_versions"]),
                smoke_result=_passed_smoke(query="competitor"),
            )
            competitor_id = str(competitor["publication_id"])
            storage.publish_agentic_ready_publication(
                competitor_id,
                expected_active_publication_id=None,
            )
        finally:
            storage.close()
        return _passed_smoke()

    monkeypatch.setattr(
        rag_admin_service,
        "run_staging_smoke",
        smoke_then_publish_competitor,
    )

    result = run_ready_data_automation_once(
        str(db_path),
        heartbeat_interval_seconds=0,
    )

    assert result["status"] == "failed"
    assert "expected-active CAS" in result["error"]
    storage = Storage(str(db_path))
    try:
        state = storage.get_agentic_ready_publication_state(
            kb_id="kb-smoke",
            profile="general",
        )
    finally:
        storage.close()
    assert state["active_publication_id"] == competitor_id
    assert state["previous_publication_id"] is None


def test_legacy_publication_without_smoke_column_is_readable_but_startup_fails_closed(
    tmp_path: Path,
) -> None:
    db_path = _setup_db(tmp_path)
    built = _manual_build(db_path, "kb-smoke")
    publication_id = str(built["candidate_publication"]["publication_id"])
    storage = Storage(str(db_path))
    storage.close()

    import sqlite3

    connection = sqlite3.connect(db_path)
    connection.execute(
        "ALTER TABLE agentic_ready_publications DROP COLUMN smoke_result_json"
    )
    connection.commit()
    connection.close()

    legacy = Storage.open_read_only(str(db_path))
    try:
        publication = legacy.get_agentic_ready_publication(publication_id)
    finally:
        legacy.close()
    assert publication is not None
    assert publication["status"] == "active"
    assert publication["smoke_result"] == {}

    status = schema_status(str(db_path))
    assert status["state"] == "invalid"
    assert status["blocked"] is True

    with pytest.raises(RuntimeError, match="schema preflight failed"):
        Storage(str(db_path))


def test_repeated_identical_manual_build_keeps_active_and_query_identity(
    tmp_path: Path,
) -> None:
    db_path = _setup_db(tmp_path)

    first = _manual_build(db_path, "kb-smoke")
    second = _manual_build(db_path, "kb-smoke")

    assert second["publication_state"]["idempotent"] is True
    assert (
        second["publication_state"]["active_publication_id"]
        == first["publication_state"]["active_publication_id"]
    )
    assert (
        second["candidate_publication"]["smoke_result"]["query_sha256"]
        == first["candidate_publication"]["smoke_result"]["query_sha256"]
    )


def test_repeated_automatic_ready_task_returns_existing_active_publication(
    tmp_path: Path,
) -> None:
    db_path = _setup_db(tmp_path)
    _enable_automation(db_path, kb_id="kb-smoke", publish=True)
    ready_input = _ready_input(db_path, "kb-smoke")
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    runtime._progress_callback = lambda _task_id: lambda *_args: None
    runtime._stop_requested = lambda _task_id: False
    task_input = {
        "contract_version": 1,
        "kb_id": "kb-smoke",
        "profile": "general",
        **ready_input,
    }

    storage = Storage(str(db_path))
    try:
        first = runtime._run_ready_data_build(
            "ready-first",
            storage,
            str(db_path),
            task_input,
        )
        second = runtime._run_ready_data_build(
            "ready-second",
            storage,
            str(db_path),
            task_input,
        )
        state = storage.get_agentic_ready_publication_state(
            kb_id="kb-smoke",
            profile="general",
        )
    finally:
        storage.close()

    assert first.success is True
    assert second.success is True
    assert second.metadata["result"]["publication_id"] == first.metadata["result"][
        "publication_id"
    ]
    assert second.metadata["result"]["publication_id"] == state[
        "active_publication_id"
    ]
