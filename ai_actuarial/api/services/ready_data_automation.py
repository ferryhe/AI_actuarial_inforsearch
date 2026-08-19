from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from ai_actuarial.storage import Storage

from .rag_admin import (
    RagAdminError,
    _build_agentic_ready_manifest_core,
    _kb_id,
    _manifest_profile,
    _require_config_write_token,
    _validate_recorded_ready_publication,
)


logger = logging.getLogger(__name__)

READY_DATA_AUTOMATION_POLL_SECONDS = 60
READY_DATA_AUTOMATION_LEASE_SECONDS = 300
READY_DATA_AUTOMATION_HEARTBEAT_SECONDS = 30

BuildCandidate = Callable[..., dict[str, Any]]
Validator = Callable[[str], dict[str, Any]]
Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _default_build_candidate(*, db_path: str, kb_id: str, profile: str) -> dict[str, Any]:
    return _build_agentic_ready_manifest_core(
        db_path=db_path,
        kb_id=kb_id,
        payload={"profile": profile},
        publish=False,
    )


def set_ready_data_automation(
    *,
    db_path: str,
    kb_id: str,
    payload: dict[str, Any],
    headers: Mapping[str, str],
    auth: Any | None = None,
) -> dict[str, Any]:
    _require_config_write_token(headers, auth)
    kid = _kb_id(kb_id)
    if not isinstance(payload, dict):
        raise RagAdminError("Invalid JSON body")
    profile = _manifest_profile(payload.get("profile") or "general")
    build_enabled = payload.get("automatic_build_enabled")
    publish_enabled = payload.get("automatic_publish_enabled")
    if not isinstance(build_enabled, bool) or not isinstance(publish_enabled, bool):
        raise RagAdminError(
            "automatic_build_enabled and automatic_publish_enabled must be booleans"
        )
    storage = Storage(db_path)
    try:
        try:
            publication_state = storage.set_agentic_ready_automation(
                kb_id=kid,
                profile=profile,
                automatic_build_enabled=build_enabled,
                automatic_publish_enabled=publish_enabled,
            )
        except ValueError as exc:
            status_code = 404 if str(exc) == "knowledge base not found" else 400
            raise RagAdminError(str(exc), status_code=status_code) from exc
        return {
            "kb_id": kid,
            "profile": profile,
            "automation": storage.get_agentic_ready_automation_state(
                kb_id=kid,
                profile=profile,
            ),
            "publication_state": publication_state,
        }
    finally:
        storage.close()


class _ClaimHeartbeat:
    def __init__(
        self,
        *,
        db_path: str,
        claim: dict[str, Any],
        lease_seconds: int,
        interval_seconds: float,
    ) -> None:
        self.db_path = db_path
        self.claim = claim
        self.lease_seconds = lease_seconds
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def lost(self) -> bool:
        return self._lost.is_set()

    def start(self) -> None:
        if self.interval_seconds <= 0:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="ready-data-automation-heartbeat",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds + 1.0))

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            storage = Storage(self.db_path)
            try:
                renewed = storage.heartbeat_agentic_ready_automation_claim(
                    kb_id=str(self.claim["kb_id"]),
                    profile=str(self.claim["profile"]),
                    generation=int(self.claim["generation"]),
                    claim_token=str(self.claim["claim_token"]),
                    lease_seconds=self.lease_seconds,
                )
            except Exception:  # noqa: BLE001
                logger.exception("Ready-data automation heartbeat failed")
                renewed = False
            finally:
                storage.close()
            if not renewed:
                self._lost.set()
                return


def _error_text(validation: dict[str, Any], default: str) -> str:
    errors = [str(item) for item in validation.get("errors") or [] if str(item)]
    return "; ".join(errors) or default


def _finish_claim(
    storage: Storage,
    claim: dict[str, Any],
    *,
    state: str,
    publication_id: str | None,
    error: str = "",
    success: bool = False,
    now: datetime,
) -> bool:
    return storage.finish_agentic_ready_automation_claim(
        kb_id=str(claim["kb_id"]),
        profile=str(claim["profile"]),
        generation=int(claim["generation"]),
        claim_token=str(claim["claim_token"]),
        automation_state=state,
        publication_id=publication_id,
        error_message=error,
        success=success,
        now=now,
    )


def _fenced_non_publish_result(
    storage: Storage,
    claim: dict[str, Any],
    candidate: dict[str, Any],
    *,
    now: datetime,
) -> dict[str, Any] | None:
    fenced = storage.finalize_agentic_ready_automation_build(
        kb_id=str(claim["kb_id"]),
        profile=str(claim["profile"]),
        generation=int(claim["generation"]),
        claim_token=str(claim["claim_token"]),
        publication_id=str(candidate["publication_id"]),
        now=now,
    )
    action = str(fenced["action"])
    reason = str(fenced.get("reason") or "claim_lost")
    if action == "superseded":
        return {
            **claim,
            "status": "superseded",
            "candidate_publication": storage.get_agentic_ready_publication(
                str(candidate["publication_id"])
            )
            or candidate,
            "fence_reason": reason,
        }
    if action == "claim_lost":
        return {
            **claim,
            "status": "claim_lost",
            "candidate_publication": candidate,
            "fence_reason": reason,
        }
    if action == "awaiting_publish":
        return {
            **claim,
            "status": "awaiting_publish",
            "candidate_publication": candidate,
            "fence_reason": reason,
        }
    return None


def run_ready_data_automation_once(
    db_path: str,
    *,
    build_candidate: BuildCandidate = _default_build_candidate,
    validator: Validator | None = None,
    lease_seconds: int = READY_DATA_AUTOMATION_LEASE_SECONDS,
    heartbeat_interval_seconds: float = READY_DATA_AUTOMATION_HEARTBEAT_SECONDS,
    clock: Clock = _utcnow,
) -> dict[str, Any]:
    """Claim and process at most one durable ready-data automation candidate."""
    if validator is None:
        from ai_actuarial.agentic_rag.ready_data_builder import validate

        validator = validate
    storage = Storage(db_path)
    try:
        claim = storage.claim_next_agentic_ready_automation(
            now=clock(),
            lease_seconds=lease_seconds,
        )
    finally:
        storage.close()
    if claim is None:
        return {"status": "idle"}

    heartbeat = _ClaimHeartbeat(
        db_path=db_path,
        claim=claim,
        lease_seconds=lease_seconds,
        interval_seconds=heartbeat_interval_seconds,
    )
    heartbeat.start()
    candidate: dict[str, Any] = {}
    try:
        if claim["mode"] == "build":
            try:
                build_result = build_candidate(
                    db_path=db_path,
                    kb_id=str(claim["kb_id"]),
                    profile=str(claim["profile"]),
                )
            except Exception as exc:  # noqa: BLE001
                failure_storage = Storage(db_path)
                try:
                    finished = _finish_claim(
                        failure_storage,
                        claim,
                        state="failed",
                        publication_id=None,
                        error=str(exc),
                        now=clock(),
                    )
                finally:
                    failure_storage.close()
                return {
                    **claim,
                    "status": "failed" if finished else "claim_lost",
                    "error": str(exc),
                }
            candidate = dict(build_result.get("candidate_publication") or {})
            build_validation = dict(build_result.get("validation") or {})
            if not build_validation.get("valid") or not candidate:
                error = _error_text(build_validation, "ready_data build or validation failed")
                failure_storage = Storage(db_path)
                try:
                    finished = _finish_claim(
                        failure_storage,
                        claim,
                        state="failed",
                        publication_id=str(candidate.get("publication_id") or "") or None,
                        error=error,
                        now=clock(),
                    )
                finally:
                    failure_storage.close()
                return {
                    **claim,
                    "status": "failed" if finished else "claim_lost",
                    "candidate_publication": candidate,
                    "validation": build_validation,
                    "error": error,
                }
        else:
            publication_id = str(claim.get("publication_id") or "")
            lookup = Storage(db_path)
            try:
                candidate = lookup.get_agentic_ready_publication(publication_id) or {}
            finally:
                lookup.close()
            if not candidate:
                failure_storage = Storage(db_path)
                try:
                    finished = _finish_claim(
                        failure_storage,
                        claim,
                        state="failed",
                        publication_id=None,
                        error="validated ready_data candidate is missing",
                        now=clock(),
                    )
                finally:
                    failure_storage.close()
                return {
                    **claim,
                    "status": "failed" if finished else "claim_lost",
                    "error": "validated ready_data candidate is missing",
                }

        if heartbeat.lost:
            return {**claim, "status": "claim_lost", "candidate_publication": candidate}

        publish_storage = Storage(db_path)
        try:
            non_publish = _fenced_non_publish_result(
                publish_storage,
                claim,
                candidate,
                now=clock(),
            )
            if non_publish is not None:
                return non_publish

            allowed_output_root = str(
                (Path(db_path).resolve().parent / "agentic_ready_data").resolve()
            )
            validation = _validate_recorded_ready_publication(
                candidate,
                validator=validator,
                allowed_output_root=allowed_output_root,
            )
            if not validation["valid"]:
                error = _error_text(validation, "ready_data publication validation failed")
                finished = _finish_claim(
                    publish_storage,
                    claim,
                    state="failed",
                    publication_id=str(candidate["publication_id"]),
                    error=error,
                    now=clock(),
                )
                return {
                    **claim,
                    "status": "failed" if finished else "claim_lost",
                    "candidate_publication": candidate,
                    "validation": validation,
                    "error": error,
                }

            current = publish_storage.get_agentic_ready_publication_state(
                kb_id=str(claim["kb_id"]),
                profile=str(claim["profile"]),
            )
            active = current.get("active_publication")
            active_validation = (
                _validate_recorded_ready_publication(
                    active,
                    validator=validator,
                    allowed_output_root=allowed_output_root,
                )
                if active
                else None
            )
            corrupt_active = bool(active_validation and not active_validation["valid"])
            corrupt_error = _error_text(
                active_validation or {},
                "active ready_data failed publication validation",
            ) if corrupt_active else ""
            publication_state = publish_storage.publish_claimed_agentic_ready_publication(
                str(candidate["publication_id"]),
                kb_id=str(claim["kb_id"]),
                profile=str(claim["profile"]),
                generation=int(claim["generation"]),
                claim_token=str(claim["claim_token"]),
                expected_active_publication_id=current["active_publication_id"],
                preserve_expected_active_as_previous=not corrupt_active,
                invalidated_expected_active_error=corrupt_error,
                now=clock(),
            )
            if not publication_state.get("automation_fence_won"):
                fenced = _fenced_non_publish_result(
                    publish_storage,
                    claim,
                    candidate,
                    now=clock(),
                )
                if fenced is not None:
                    return fenced
                return {
                    **claim,
                    "status": "claim_lost",
                    "candidate_publication": candidate,
                    "publication_state": publication_state,
                }
            if not publication_state.get("cas_won"):
                error = "ready_data automatic publication lost expected-active CAS"
                finished = _finish_claim(
                    publish_storage,
                    claim,
                    state="failed",
                    publication_id=str(candidate["publication_id"]),
                    error=error,
                    now=clock(),
                )
                return {
                    **claim,
                    "status": "failed" if finished else "claim_lost",
                    "candidate_publication": candidate,
                    "publication_state": publication_state,
                    "error": error,
                }
            return {
                **claim,
                "status": "published",
                "candidate_publication": publish_storage.get_agentic_ready_publication(
                    str(candidate["publication_id"])
                )
                or candidate,
                "publication_state": publication_state,
                "validation": validation,
            }
        except Exception as exc:  # noqa: BLE001
            fence = publish_storage.check_agentic_ready_automation_claim(
                kb_id=str(claim["kb_id"]),
                profile=str(claim["profile"]),
                generation=int(claim["generation"]),
                claim_token=str(claim["claim_token"]),
                now=clock(),
            )
            if fence.get("reason") == "generation_superseded" and candidate:
                return _fenced_non_publish_result(
                    publish_storage,
                    claim,
                    candidate,
                    now=clock(),
                ) or {**claim, "status": "claim_lost"}
            finished = _finish_claim(
                publish_storage,
                claim,
                state="failed",
                publication_id=str(candidate.get("publication_id") or "") or None,
                error=str(exc),
                now=clock(),
            )
            return {
                **claim,
                "status": "failed" if finished else "claim_lost",
                "candidate_publication": candidate,
                "error": str(exc),
            }
        finally:
            publish_storage.close()
    finally:
        heartbeat.stop()
