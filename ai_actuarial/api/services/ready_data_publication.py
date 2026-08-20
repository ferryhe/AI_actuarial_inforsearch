from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ai_actuarial.storage import (
    AGENTIC_READY_PUBLICATION_PROFILES,
    Storage,
    agentic_ready_publication_matches_scope,
)

from .rag_admin import (
    RagAdminError,
    _build_agentic_manifest_status,
    _kb_id,
    _manager_and_storage,
    _manifest_profile,
    _validate_recorded_ready_publication,
)


_PUBLIC_STATUS_MESSAGES = frozenset(
    {
        "ready_data manifest has not been built",
        "ready_data source evaluation is pending",
        "KB source files changed after the ready_data manifest was built",
        "KB document count differs from the ready_data manifest",
        "ready_data is blocked by a hard source-state gate",
        "ready_data is unavailable",
        "empty ready_data requires manual publish confirmation",
    }
)
_PUBLIC_STALE_REASON_CODES = frozenset(
    {
        "membership_added",
        "metadata_updated",
        "builder_contract_changed",
        "profile_contract_changed",
        "chunk_binding_updated",
        "chunk_content_updated",
        "membership_removed",
        "chunk_binding_removed",
        "source_invalidated",
        "source_deleted",
        "access_scope_restricted",
        "index_committed",
        "embedding_index_committed",
        "embedding_config_changed",
        "source_version_changed",
    }
)
_PUBLIC_SERVING_STATUSES = frozenset(
    {"missing", "ready", "stale", "failed", "unavailable"}
)
_PUBLIC_AUTOMATION_STATUSES = frozenset(
    {
        "idle",
        "pending",
        "running",
        "building",
        "awaiting_publish",
        "awaiting_manual_confirmation",
        "succeeded",
        "failed",
    }
)
_PUBLIC_PUBLICATION_STATUSES = frozenset(
    {"failed", "validated", "active", "previous"}
)
_PUBLIC_SMOKE_STATUSES = frozenset(
    {"not_run", "skipped_empty", "failed", "passed"}
)
_PUBLIC_SOURCE_STATES = frozenset(
    {"legacy_fallback", "pending_evaluation", "stale", "legacy_hard_gate", "fresh"}
)
_PUBLIC_STALE_SEVERITIES = frozenset({"none", "soft_stale", "hard_stale"})
_PUBLIC_FALLBACK_MODES = frozenset({"standard", "agentic"})
_PUBLIC_PROFILES = AGENTIC_READY_PUBLICATION_PROFILES
_PUBLIC_SOURCE_VERSION_KINDS = frozenset(
    {
        "catalog_chunks_snapshot",
        "failed_build_attempt",
        "index",
        "kb_snapshot",
        "legacy_artifact",
        "legacy_manifest",
        "legacy_ready_data",
    }
)


def _public_enum(value: Any, *, allowed: frozenset[str], fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    normalized = value.strip().lower()
    return normalized if normalized in allowed else fallback


def _public_automation_state(value: Any) -> str:
    if isinstance(value, str) and value.strip().lower() == "disabled":
        return "idle"
    return _public_enum(
        value,
        allowed=_PUBLIC_AUTOMATION_STATUSES,
        fallback="failed",
    )


def _public_source_version_kind(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return _public_enum(
        value,
        allowed=_PUBLIC_SOURCE_VERSION_KINDS,
        fallback="unknown",
    )


def _public_stale_severity(value: Any) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return "none"
    return _public_enum(
        value,
        allowed=_PUBLIC_STALE_SEVERITIES,
        fallback="hard_stale",
    )


def _has_unknown_stale_severity(value: Any) -> bool:
    if value is None or (isinstance(value, str) and not value.strip()):
        return False
    return not (
        isinstance(value, str)
        and value.strip().lower() in _PUBLIC_STALE_SEVERITIES
    )


def _current_ready_index_version_id(storage: Storage, *, kb_id: str) -> str | None:
    row = storage._conn.execute(
        "SELECT index_version_id FROM kb_ready_index_state WHERE kb_id = ? LIMIT 1",
        (kb_id,),
    ).fetchone()
    return str(row[0]) if row and row[0] else None


def _public_error(value: Any) -> str:
    text = " ".join(str(value or "").split())[:320].rstrip()
    if not text:
        return ""
    if text in _PUBLIC_STATUS_MESSAGES:
        return text
    reason_codes = [part.strip() for part in text.split(";") if part.strip()]
    if reason_codes and all(
        reason_code in _PUBLIC_STALE_REASON_CODES for reason_code in reason_codes
    ):
        return "; ".join(reason_codes)
    return "ready_data operation failed"


def _public_stale_reasons(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    projected: list[str] = []
    unknown = False
    for raw_value in values:
        value = str(raw_value or "").strip()
        if not value:
            continue
        if value in _PUBLIC_STALE_REASON_CODES or value in _PUBLIC_STATUS_MESSAGES:
            if value not in projected:
                projected.append(value)
        else:
            unknown = True
    if unknown:
        projected.append("ready_data_source_changed")
    return projected


def _public_smoke(publication: Mapping[str, Any] | None) -> dict[str, Any]:
    smoke = (publication or {}).get("smoke_result")
    if not isinstance(smoke, Mapping):
        smoke = {}
    return {
        "status": _public_enum(
            smoke.get("status"),
            allowed=_PUBLIC_SMOKE_STATUSES,
            fallback="not_run",
        ),
        "checked_at": smoke.get("checked_at"),
    }


def _public_source_state(source_state: Any) -> dict[str, Any] | None:
    if not isinstance(source_state, Mapping):
        return None
    return {
        "state": _public_enum(
            source_state.get("state"),
            allowed=_PUBLIC_SOURCE_STATES,
            fallback="legacy_fallback",
        ),
        "event_generation": int(source_state.get("event_generation") or 0),
        "pending_evaluation_generation": source_state.get(
            "pending_evaluation_generation"
        ),
        "evaluated_generation": int(source_state.get("evaluated_generation") or 0),
        "pending_evaluation": bool(source_state.get("pending_evaluation")),
        "pending_severity": _public_stale_severity(
            source_state.get("pending_severity")
        ),
        "pending_reasons": _public_stale_reasons(
            source_state.get("pending_reasons")
        ),
        "evaluated_severity": _public_stale_severity(
            source_state.get("evaluated_severity")
        ),
        "evaluated_reasons": _public_stale_reasons(
            source_state.get("evaluated_reasons")
        ),
        "evaluated_source_version_kind": _public_source_version_kind(
            source_state.get("evaluated_source_version_kind")
        ),
        "evaluated_source_version_id": source_state.get(
            "evaluated_source_version_id"
        ),
        "active_source_version_kind": _public_source_version_kind(
            source_state.get("active_source_version_kind")
        ),
        "active_source_version_id": source_state.get("active_source_version_id"),
        "source_identity_comparable": bool(
            source_state.get("source_identity_comparable")
        ),
        "legacy_heuristic_required": bool(
            source_state.get("legacy_heuristic_required")
        ),
        "legacy_hard_gate": bool(source_state.get("legacy_hard_gate")),
        "stale_confirmed": bool(source_state.get("stale_confirmed")),
        "stale_severity": _public_stale_severity(
            source_state.get("stale_severity")
        ),
        "stale_reasons": _public_stale_reasons(source_state.get("stale_reasons")),
        "serving_stale": bool(source_state.get("serving_stale")),
        "serving_allowed": bool(source_state.get("serving_allowed", True)),
        "automatic_build_enabled": bool(
            source_state.get("automatic_build_enabled")
        ),
        "automatic_publish_enabled": bool(
            source_state.get("automatic_publish_enabled")
        ),
        "evaluated_at": source_state.get("evaluated_at"),
        "updated_at": source_state.get("updated_at"),
    }


def _publication_matches_scope(
    publication: Any,
    *,
    kb_id: str,
    profile: str,
) -> bool:
    return agentic_ready_publication_matches_scope(
        publication,
        kb_id=kb_id,
        profile=profile,
    )


def _public_publication(
    publication: Mapping[str, Any] | None,
    *,
    profile: str,
    current_ready_index_version_id: str | None,
) -> dict[str, Any] | None:
    if not publication:
        return None
    smoke = _public_smoke(publication)
    return {
        "publication_id": publication.get("publication_id"),
        "profile": _public_enum(
            publication.get("profile"),
            allowed=_PUBLIC_PROFILES,
            fallback=profile,
        ),
        "profile_version": publication.get("profile_version"),
        "status": _public_enum(
            publication.get("status"),
            allowed=_PUBLIC_PUBLICATION_STATUSES,
            fallback="failed",
        ),
        "authoritative_source_version_kind": _public_source_version_kind(
            publication.get("source_version_kind")
        ),
        "authoritative_source_version_id": publication.get("source_version_id"),
        "observed_index_version_id": publication.get("index_version_id"),
        "current_ready_index_version_id": current_ready_index_version_id,
        "index_consumed_by_builder": False,
        "artifact_digest": publication.get("artifact_digest") or "",
        "doc_count": int(publication.get("doc_count") or 0),
        "section_count": int(publication.get("section_count") or 0),
        "built_at": publication.get("built_at"),
        "validated_at": publication.get("validated_at"),
        "published_at": publication.get("published_at"),
        "smoke_status": smoke["status"],
        "smoke_checked_at": smoke["checked_at"],
    }


def _public_ready_data_state_in_snapshot(
    storage: Storage,
    *,
    kb_id: str,
    profile: str,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_profile = _manifest_profile(profile)
    current_index_id = _current_ready_index_version_id(storage, kb_id=kb_id)
    state = storage.get_agentic_ready_publication_state(
        kb_id=kb_id,
        profile=normalized_profile,
    )
    automation = storage.get_agentic_ready_automation_state(
        kb_id=kb_id,
        profile=normalized_profile,
    )
    source_state = storage.get_agentic_ready_source_state(
        kb_id=kb_id,
        profile=normalized_profile,
    )
    active_record = state.get("active_publication")
    previous_record = state.get("previous_publication")
    active_record = (
        active_record
        if _publication_matches_scope(
            active_record,
            kb_id=kb_id,
            profile=normalized_profile,
        )
        else None
    )
    previous_record = (
        previous_record
        if _publication_matches_scope(
            previous_record,
            kb_id=kb_id,
            profile=normalized_profile,
        )
        and isinstance(previous_record.get("status"), str)
        and previous_record.get("status").strip().lower() == "previous"
        else None
    )
    active = _public_publication(
        active_record,
        profile=normalized_profile,
        current_ready_index_version_id=current_index_id,
    )
    previous = _public_publication(
        previous_record,
        profile=normalized_profile,
        current_ready_index_version_id=current_index_id,
    )
    serving = dict(manifest or _build_agentic_manifest_status(
        storage=storage,
        kb_id=kb_id,
        profile=normalized_profile,
    ))
    smoke_source = active_record
    smoke = _public_smoke(smoke_source)
    automation_state = _public_automation_state(automation.get("automation_state"))
    public_last_error = _public_error(automation.get("last_error"))
    raw_serving_status = (
        serving.get("status").strip().lower()
        if isinstance(serving.get("status"), str)
        else ""
    )
    source_severity_invalid = any(
        _has_unknown_stale_severity(source_state.get(field))
        for field in ("pending_severity", "evaluated_severity", "stale_severity")
    )
    serving_stale = (
        bool(serving.get("serving_stale"))
        or bool(source_state.get("serving_stale"))
        or raw_serving_status == "stale"
        or source_severity_invalid
    )
    has_active = bool(
        isinstance(active_record, Mapping)
        and active_record.get("publication_id")
        and _public_enum(
            active_record.get("status"),
            allowed=_PUBLIC_PUBLICATION_STATUSES,
            fallback="failed",
        )
        == "active"
    )
    corrupt_active_slot = bool(state.get("active_publication_id")) and not has_active
    if corrupt_active_slot:
        serving_status = "unavailable"
    elif has_active:
        serving_status = "stale" if serving_stale else "ready"
    elif raw_serving_status == "building":
        serving_status = "missing"
    else:
        serving_status = _public_enum(
            raw_serving_status,
            allowed=_PUBLIC_SERVING_STATUSES,
            fallback="unavailable",
        )
    if raw_serving_status == "building" and automation_state == "idle":
        automation_state = "building"
    stale_severity = (
        "hard_stale"
        if source_severity_invalid
        else _public_stale_severity(serving.get("stale_severity"))
    )
    if serving_stale and stale_severity == "none":
        stale_severity = "soft_stale"
    stale_reasons = _public_stale_reasons(source_state.get("stale_reasons"))
    if source_severity_invalid and not stale_reasons:
        stale_reasons = ["ready_data_source_changed"]
    legacy_stale_reason = _public_error(serving.get("stale_reason"))
    if serving_stale and not stale_reasons and legacy_stale_reason:
        stale_reasons = [legacy_stale_reason]
    if (
        automation_state == "awaiting_publish"
        and public_last_error == "empty ready_data requires manual publish confirmation"
    ):
        automation_state = "awaiting_manual_confirmation"
    return {
        "kb_id": kb_id,
        "profile": normalized_profile,
        "serving_status": serving_status,
        "serving_usable": (
            False
            if corrupt_active_slot or source_severity_invalid
            else bool(source_state.get("serving_allowed", True))
            if has_active
            else bool(serving.get("usable"))
        ),
        "serving_stale": serving_stale,
        "stale_confirmed": bool(serving.get("stale_confirmed")) or serving_stale,
        "stale_severity": stale_severity,
        "stale_reasons": stale_reasons,
        "source_generation": int(source_state.get("event_generation") or 0),
        "pending_evaluation_generation": source_state.get(
            "pending_evaluation_generation"
        ),
        "evaluated_generation": int(source_state.get("evaluated_generation") or 0),
        "automation_state": automation_state,
        "automatic_build_enabled": bool(automation.get("automatic_build_enabled")),
        "automatic_publish_enabled": bool(automation.get("automatic_publish_enabled")),
        "pending_generation": automation.get("pending_evaluation_generation"),
        "running_generation": automation.get("running_generation"),
        "last_attempt_publication_id": automation.get("last_attempt_publication_id"),
        "last_success_at": automation.get("last_success_at"),
        "last_error": public_last_error,
        "publication_revision": int(state.get("publication_revision") or 0),
        "active_publication_id": state.get("active_publication_id"),
        "previous_publication_id": state.get("previous_publication_id"),
        "active_publication": active,
        "previous_publication": previous,
        "current_ready_index_version_id": current_index_id,
        "smoke_status": smoke["status"],
        "smoke_checked_at": smoke["checked_at"],
    }


def public_ready_data_state(
    storage: Storage,
    *,
    kb_id: str,
    profile: str,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    with storage.transaction():
        return _public_ready_data_state_in_snapshot(
            storage,
            kb_id=kb_id,
            profile=profile,
            manifest=manifest,
        )


def public_ready_data_manifest(
    manifest: Mapping[str, Any],
    publication_state: Mapping[str, Any],
    *,
    include_legacy_output_dir: bool = True,
) -> dict[str, Any]:
    active = publication_state.get("active_publication")
    active = active if isinstance(active, Mapping) else {}
    serving_usable = bool(publication_state.get("serving_usable"))
    fallback_mode = _public_enum(
        manifest.get("fallback_mode"),
        allowed=_PUBLIC_FALLBACK_MODES,
        fallback="standard",
    )
    if not serving_usable:
        fallback_mode = "standard"
    public_source_state = _public_source_state(manifest.get("source_state"))
    if public_source_state is not None:
        public_source_state.update(
            {
                "stale_confirmed": bool(
                    publication_state.get("stale_confirmed")
                ),
                "stale_severity": _public_stale_severity(
                    publication_state.get("stale_severity")
                ),
                "stale_reasons": list(
                    publication_state.get("stale_reasons") or []
                ),
                "serving_stale": bool(
                    publication_state.get("serving_stale")
                ),
                "serving_allowed": serving_usable,
            }
        )
    return {
        "kb_id": manifest.get("kb_id"),
        "profile": _public_enum(
            manifest.get("profile"),
            allowed=_PUBLIC_PROFILES,
            fallback=_public_enum(
                publication_state.get("profile"),
                allowed=_PUBLIC_PROFILES,
                fallback="general",
            ),
        ),
        "profile_version": manifest.get("profile_version"),
        "status": _public_enum(
            publication_state.get("serving_status"),
            allowed=_PUBLIC_SERVING_STATUSES,
            fallback="unavailable",
        ),
        "usable": serving_usable,
        "fallback_mode": fallback_mode,
        **(
            {"output_dir": manifest.get("output_dir") or ""}
            if include_legacy_output_dir
            else {}
        ),
        "publication_id": manifest.get("publication_id"),
        "index_version_id": manifest.get("index_version_id"),
        "source_version_kind": _public_source_version_kind(
            manifest.get("source_version_kind")
        ),
        "source_version_id": manifest.get("source_version_id"),
        "artifact_digest": manifest.get("artifact_digest") or "",
        "doc_count": int(manifest.get("doc_count") or 0),
        "section_count": int(manifest.get("section_count") or 0),
        "built_at": manifest.get("built_at"),
        "current_doc_count": int(manifest.get("current_doc_count") or 0),
        "latest_source_at": manifest.get("latest_source_at"),
        "error_message": _public_error(manifest.get("error_message")),
        "stale_reason": _public_error(manifest.get("stale_reason")),
        "serving_stale": bool(publication_state.get("serving_stale")),
        "stale_confirmed": bool(publication_state.get("stale_confirmed")),
        "stale_severity": _public_stale_severity(
            publication_state.get("stale_severity")
        ),
        "stale_reasons": list(publication_state.get("stale_reasons") or []),
        "source_state": public_source_state,
        "event_generation": publication_state.get("source_generation"),
        "pending_evaluation_generation": publication_state.get(
            "pending_evaluation_generation"
        ),
        "evaluated_generation": publication_state.get("evaluated_generation"),
        "automation_state": _public_automation_state(
            publication_state.get("automation_state")
        ),
        "automatic_build_enabled": bool(
            publication_state.get("automatic_build_enabled")
        ),
        "automatic_publish_enabled": bool(
            publication_state.get("automatic_publish_enabled")
        ),
        "pending_generation": publication_state.get("pending_generation"),
        "running_generation": publication_state.get("running_generation"),
        "last_attempt_publication_id": publication_state.get(
            "last_attempt_publication_id"
        ),
        "last_success_at": publication_state.get("last_success_at"),
        "last_error": publication_state.get("last_error") or "",
        "publication_revision": int(
            publication_state.get("publication_revision") or 0
        ),
        "authoritative_source_version_kind": active.get(
            "authoritative_source_version_kind"
        ),
        "authoritative_source_version_id": active.get(
            "authoritative_source_version_id"
        ),
        "observed_index_version_id": active.get("observed_index_version_id"),
        "current_ready_index_version_id": publication_state.get(
            "current_ready_index_version_id"
        ),
        "index_consumed_by_builder": False,
        "smoke_status": publication_state.get("smoke_status"),
        "smoke_checked_at": publication_state.get("smoke_checked_at"),
        "publication_state": dict(publication_state),
    }


def read_public_ready_data_snapshot(
    storage: Storage,
    *,
    kb_id: str,
    profile: str,
    include_legacy_output_dir: bool = True,
) -> dict[str, Any]:
    with storage.transaction():
        manifest = _build_agentic_manifest_status(
            storage=storage,
            kb_id=kb_id,
            profile=profile,
        )
        publication_state = _public_ready_data_state_in_snapshot(
            storage,
            kb_id=kb_id,
            profile=profile,
            manifest=manifest,
        )
        return {
            "kb_id": kb_id,
            "manifest": public_ready_data_manifest(
                manifest,
                publication_state,
                include_legacy_output_dir=include_legacy_output_dir,
            ),
            "publication_state": publication_state,
        }


def rollback_ready_data_publication(
    *,
    db_path: str,
    kb_id: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    kid = _kb_id(kb_id)
    if not isinstance(payload, Mapping):
        raise RagAdminError("Invalid JSON body")
    profile_value = payload.get("profile")
    if not isinstance(profile_value, str) or not profile_value.strip():
        raise RagAdminError("profile is required")
    profile = _manifest_profile(profile_value)
    expected_active_value = payload.get("expected_active_publication_id")
    expected_previous_value = payload.get("expected_previous_publication_id")
    if (
        not isinstance(expected_active_value, str)
        or not expected_active_value.strip()
        or not isinstance(expected_previous_value, str)
        or not expected_previous_value.strip()
    ):
        raise RagAdminError(
            "expected_active_publication_id and expected_previous_publication_id are required"
        )
    expected_active = expected_active_value.strip()
    expected_previous = expected_previous_value.strip()

    _KnowledgeBase, manager, storage = _manager_and_storage(db_path)
    try:
        if not manager.get_kb(kid):
            raise RagAdminError(f"Knowledge base '{kid}' not found", status_code=404)
        state = storage.get_agentic_ready_publication_state(kb_id=kid, profile=profile)
        if (
            state.get("active_publication_id") != expected_active
            or state.get("previous_publication_id") != expected_previous
        ):
            raise RagAdminError(
                "ready_data publication state changed; refresh before rollback",
                status_code=409,
            )
        previous = state.get("previous_publication")
        if (
            not previous
            or not _publication_matches_scope(
                previous,
                kb_id=kid,
                profile=profile,
            )
            or previous.get("status") != "previous"
        ):
            raise RagAdminError(
                "previous ready_data publication is not eligible for rollback",
                status_code=422,
            )

        from ai_actuarial.agentic_rag import ready_data_builder

        allowed_output_root = str(
            Path(db_path).resolve().parent / "agentic_ready_data"
        )

        def validate_previous(candidate: dict[str, Any]) -> bool:
            if (
                not _publication_matches_scope(
                    candidate,
                    kb_id=kid,
                    profile=profile,
                )
                or candidate.get("status") != "previous"
            ):
                return False
            validation = _validate_recorded_ready_publication(
                candidate,
                validator=ready_data_builder.validate,
                allowed_output_root=allowed_output_root,
            )
            return bool(validation["valid"])

        try:
            rolled = storage.rollback_agentic_ready_publication(
                kb_id=kid,
                profile=profile,
                expected_active_publication_id=expected_active,
                expected_previous_publication_id=expected_previous,
                validated_previous_publication_id=expected_previous,
                validate_previous_publication=validate_previous,
            )
        except ValueError as exc:
            raise RagAdminError(
                "previous ready_data publication failed integrity validation",
                status_code=422,
            ) from exc
        if not rolled.get("cas_won"):
            raise RagAdminError(
                "ready_data publication state changed; refresh before rollback",
                status_code=409,
            )
        return read_public_ready_data_snapshot(
            storage,
            kb_id=kid,
            profile=profile,
        )
    finally:
        storage.close()
