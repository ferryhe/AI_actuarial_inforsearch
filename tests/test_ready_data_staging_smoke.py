from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_actuarial.agentic_rag import ready_data_builder
from ai_actuarial.api.services import rag_admin as rag_admin_service
from ai_actuarial.api.services.rag_admin import (
    _build_agentic_ready_manifest_core,
    _ready_data_artifact_digest,
)
from ai_actuarial.api.services.ready_data_automation import (
    run_ready_data_automation_once,
)
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.sqlite_schema import schema_status
from ai_actuarial.storage import Storage


def _create_kb(
    storage: Storage,
    tmp_path: Path,
    *,
    kb_id: str,
    with_document: bool,
) -> None:
    KnowledgeBaseManager(storage).create_kb(
        kb_id=kb_id,
        name=f"Smoke {kb_id}",
        kb_mode="manual",
        manifest_profile="general",
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


def _setup_db(
    tmp_path: Path,
    *,
    kb_id: str = "kb-smoke",
    with_document: bool = True,
) -> Path:
    db_path = tmp_path / "index.db"
    storage = Storage(str(db_path))
    try:
        _create_kb(
            storage,
            tmp_path,
            kb_id=kb_id,
            with_document=with_document,
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


def _manual_build(db_path: Path, kb_id: str) -> dict[str, Any]:
    return _build_agentic_ready_manifest_core(
        db_path=str(db_path),
        kb_id=kb_id,
        payload={"profile": "general"},
        publish=True,
    )


def _enable_automation(
    db_path: Path,
    *,
    kb_id: str,
    publish: bool,
) -> None:
    storage = Storage(str(db_path))
    try:
        storage.set_agentic_ready_automation(
            kb_id=kb_id,
            profile="general",
            automatic_build_enabled=True,
            automatic_publish_enabled=publish,
        )
        storage.mark_agentic_ready_source_event(
            kb_id=kb_id,
            profile="general",
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


def test_manual_build_confirms_and_publishes_empty_kb(tmp_path: Path) -> None:
    db_path = _setup_db(tmp_path, with_document=False)

    result = _manual_build(db_path, "kb-smoke")

    candidate = result["candidate_publication"]
    assert result["validation"]["valid"] is True
    assert candidate["doc_count"] == 0
    assert candidate["smoke_result"]["status"] == "skipped_empty"
    assert result["publication_state"]["active_publication_id"] == candidate["publication_id"]


def test_automatic_publish_keeps_empty_kb_awaiting_manual_confirmation(
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
    assert first["status"] == "awaiting_manual_confirmation"
    assert first["candidate_publication"]["doc_count"] == 0
    assert first["candidate_publication"]["smoke_result"]["status"] == "skipped_empty"
    assert second == {"status": "idle"}
    assert automation["automation_state"] == "awaiting_publish"
    assert automation["last_error"] == "empty ready_data requires manual publish confirmation"
    assert state["active_publication_id"] is None
    assert state["previous_publication_id"] is None


def test_enabling_auto_publish_for_existing_empty_candidate_waits_once(
    tmp_path: Path,
) -> None:
    db_path = _setup_db(tmp_path, with_document=False)
    _enable_automation(db_path, kb_id="kb-smoke", publish=False)
    built = run_ready_data_automation_once(
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

    guarded = run_ready_data_automation_once(
        str(db_path),
        heartbeat_interval_seconds=0,
    )
    idle = run_ready_data_automation_once(
        str(db_path),
        heartbeat_interval_seconds=0,
    )

    assert built["status"] == "awaiting_publish"
    assert guarded["status"] == "awaiting_manual_confirmation"
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


def test_automatic_empty_gate_uses_smoke_catalog_result_not_manifest_count(
    tmp_path: Path,
) -> None:
    db_path = _setup_db(tmp_path, with_document=False)
    _enable_automation(db_path, kb_id="kb-smoke", publish=True)

    def misleading_empty_candidate(
        *, db_path: str, kb_id: str, profile: str
    ) -> dict[str, Any]:
        storage = Storage(db_path)
        try:
            output_dir = tmp_path / "agentic_ready_data" / "misleading-empty"
            output_dir.mkdir(parents=True)
            manifest_path = output_dir / "ready_data_manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "profile": profile,
                        "profile_version": "1",
                        "artifact_files": ["ready_data_manifest.json"],
                    }
                ),
                encoding="utf-8",
            )
            candidate = storage.record_agentic_ready_publication(
                kb_id=kb_id,
                index_version_id=None,
                source_version_kind="catalog_chunks_snapshot",
                source_version_id="misleading-empty-source",
                profile=profile,
                profile_version="1",
                status="validated",
                output_dir=str(output_dir),
                artifact_files=["ready_data_manifest.json"],
                doc_count=1,
                section_count=0,
                built_at="2026-08-19T00:00:00+00:00",
                artifact_digest=_ready_data_artifact_digest(
                    str(output_dir),
                    ["ready_data_manifest.json"],
                ),
                source_db=db_path,
                smoke_result={
                    **_passed_smoke(),
                    "status": "skipped_empty",
                    "catalog_doc_count": 0,
                    "matched_doc_id": "",
                    "matched_file_url": "",
                },
            )
        finally:
            storage.close()
        return {
            "candidate_publication": candidate,
            "validation": {"valid": True, "errors": [], "warnings": []},
        }

    result = run_ready_data_automation_once(
        str(db_path),
        build_candidate=misleading_empty_candidate,
        source_fingerprint=lambda **_kwargs: {
            "source_version_kind": "catalog_chunks_snapshot",
            "source_version_id": "misleading-empty-source",
        },
        heartbeat_interval_seconds=0,
    )

    assert result["status"] == "awaiting_manual_confirmation"
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
        )
        artifacts = list(manifest["artifact_files"])
        storage = Storage(str(db_path))
        try:
            competitor = storage.record_agentic_ready_publication(
                kb_id="kb-smoke",
                index_version_id=None,
                source_version_kind="catalog_chunks_snapshot",
                source_version_id="competitor-source",
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
