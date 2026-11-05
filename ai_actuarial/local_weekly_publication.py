"""Locally relay one completed China weekly publication to both sites."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from contextlib import nullcontext
from pathlib import Path
from typing import Any, Callable

from ai_actuarial import local_collection_runtime as local_runtime
from ai_actuarial import local_collection_target_worker as target_worker

_TARGETS = ("china", "overseas")
_POLL_SECONDS = 15


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "pending": None, "last_completed": None}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("weekly publication state is unreadable; no state was changed") from exc
    if (
        not isinstance(state, dict)
        or state.get("schema_version") != 1
        or set(state) != {"schema_version", "pending", "last_completed"}
    ):
        raise RuntimeError("weekly publication state does not match schema v1")
    pending = state.get("pending")
    if pending is not None:
        if (
            not isinstance(pending, dict)
            or set(pending) != {"bundle", "bundle_sha256", "acks", "frozen_at"}
            or not isinstance(pending.get("acks"), dict)
            or set(pending["acks"]) - set(_TARGETS)
            or not isinstance(pending.get("frozen_at"), str)
        ):
            raise RuntimeError("weekly publication pending state is malformed")
        summary = target_worker.validate_weekly_publication_bundle(pending.get("bundle"))
        digest = target_worker.weekly_publication_bundle_sha256(pending["bundle"])
        if pending.get("bundle_sha256") != digest:
            raise RuntimeError("weekly publication frozen bundle hash does not match state")
        for target, ack in pending["acks"].items():
            if (
                not isinstance(ack, dict)
                or ack.get("target") != target
                or ack.get("snapshot_id") != pending["bundle"]["snapshot"]["id"]
                or ack.get("bundle_sha256") != digest
                or ack.get("guide_generated_at") != summary["guide_generated_at"]
                or ack.get("card_projection_sha256") != summary["card_projection_sha256"]
                or ack.get("recommendation_urls") != summary["recommendation_urls"]
            ):
                raise RuntimeError(
                    "weekly publication acknowledgement does not match frozen bundle"
                )
    completed = state.get("last_completed")
    if completed is not None and (
        not isinstance(completed, dict)
        or not isinstance(completed.get("snapshot_id"), str)
        or not isinstance(completed.get("period_start"), str)
        or not isinstance(completed.get("period_end"), str)
        or not isinstance(completed.get("bundle_sha256"), str)
        or completed.get("source_revision_sha256") is not None
        and not isinstance(completed.get("source_revision_sha256"), str)
        or completed.get("source_revision_key") is not None
        and (
            not isinstance(completed.get("source_revision_key"), list)
            or len(completed["source_revision_key"]) != 3
            or any(not isinstance(value, str) for value in completed["source_revision_key"])
        )
    ):
        raise RuntimeError("weekly publication completion receipt is malformed")
    return state


def _parse_period(period_start: str, period_end: str) -> tuple[dt.datetime, dt.datetime]:
    try:
        start = dt.datetime.fromisoformat(period_start.replace("Z", "+00:00"))
        end = dt.datetime.fromisoformat(period_end.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("weekly period must use ISO timestamps") from exc
    if (
        start.tzinfo is None
        or end.tzinfo is None
        or start.utcoffset() != dt.timedelta(0)
        or end.utcoffset() != dt.timedelta(0)
        or start.weekday() != 0
        or start.time() != dt.time(0)
        or end - start != dt.timedelta(days=7)
    ):
        raise ValueError("weekly period must be one complete Monday-to-Monday UTC week")
    return start, end


def _revision_key(bundle: dict[str, Any]) -> tuple[dt.datetime, dt.datetime, dt.datetime]:
    snapshot = bundle["snapshot"]
    explanation = bundle["explanation"]
    start, end = _parse_period(snapshot["period_start"], snapshot["period_end"])
    del start
    snapshot_at = dt.datetime.fromisoformat(snapshot["generated_at"].replace("Z", "+00:00"))
    explanation_at = dt.datetime.fromisoformat(explanation["generated_at"].replace("Z", "+00:00"))
    return end, snapshot_at, explanation_at


def _same_source_revision(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_snapshot = dict(left["snapshot"])
    right_snapshot = dict(right["snapshot"])
    left_metadata = target_worker._weekly_base_metadata(dict(left_snapshot.pop("metadata")))
    right_metadata = target_worker._weekly_base_metadata(dict(right_snapshot.pop("metadata")))
    return (
        left_snapshot == right_snapshot
        and left_metadata == right_metadata
        and left["members"] == right["members"]
        and target_worker._weekly_explanation_revision(left["explanation"])
        == target_worker._weekly_explanation_revision(right["explanation"])
    )


def _source_revision_sha256(bundle: dict[str, Any]) -> str:
    normalized = dict(bundle)
    explanation = dict(bundle["explanation"])
    coverage = dict(explanation["coverage"])
    coverage.pop("last_failed_attempt", None)
    explanation["coverage"] = coverage
    normalized["explanation"] = explanation
    return target_worker.weekly_publication_bundle_sha256(normalized)


def _revision_key_values(bundle: dict[str, Any]) -> list[str]:
    snapshot = bundle["snapshot"]
    explanation = bundle["explanation"]
    return [snapshot["period_end"], snapshot["generated_at"], explanation["generated_at"]]


def _auto_due_period(now: dt.datetime) -> tuple[str, str] | None:
    utc_now = now.astimezone(dt.timezone.utc)
    if utc_now.weekday() == 6 and utc_now.time() >= dt.time(23, 0):
        return None
    monday = utc_now.date() - dt.timedelta(days=utc_now.weekday())
    end = dt.datetime.combine(monday, dt.time(0), tzinfo=dt.timezone.utc)
    if utc_now < end + dt.timedelta(minutes=30):
        return None
    start = end - dt.timedelta(days=7)
    return start.isoformat(), end.isoformat()


def _period_for_bundle(bundle: dict[str, Any]) -> tuple[str, str]:
    return bundle["snapshot"]["period_start"], bundle["snapshot"]["period_end"]


def _export_source(
    config: dict[str, Any],
    period: tuple[str, str],
    *,
    wait_seconds: float,
    invoke: Callable[..., dict[str, Any]] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    dispatch = invoke or local_runtime._invoke_target_worker
    deadline = time.monotonic() + max(0.0, wait_seconds)
    while True:
        result = dispatch(
            config,
            "china",
            {
                "operation": "export_weekly_publication",
                "schema_version": 1,
                "target": "china",
                "period_start": period[0],
                "period_end": period[1],
            },
        )
        if result.get("status") == "ready":
            bundle = result.get("bundle")
            target_worker.validate_weekly_publication_bundle(bundle)
            digest = target_worker.weekly_publication_bundle_sha256(bundle)
            if (
                result.get("bundle_sha256") != digest
                or _period_for_bundle(bundle) != period
                or result.get("snapshot_id") != bundle["snapshot"]["id"]
            ):
                raise RuntimeError("China export did not match the requested weekly period/hash")
            return {"bundle": bundle, "bundle_sha256": digest}
        if result.get("status") != "pending":
            raise RuntimeError("China export returned an unknown weekly publication state")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {
                "pending_reason": result.get("reason"),
                "snapshot_id": result.get("snapshot_id"),
            }
        sleep(min(_POLL_SECONDS, remaining))


def _save_pending(
    state: dict[str, Any], bundle: dict[str, Any], digest: str, state_path: Path
) -> None:
    state["pending"] = {
        "bundle": bundle,
        "bundle_sha256": digest,
        "acks": {},
        "frozen_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    local_runtime._atomic_json(state_path, state)


def _result(status: str, **fields: Any) -> dict[str, Any]:
    return {"success": status not in {"pending", "conflict"}, "status": status, **fields}


def run_weekly_publication(
    action: str,
    *,
    config_path: Path,
    period_start: str | None = None,
    period_end: str | None = None,
    wait_seconds: float = 600,
    now: dt.datetime | None = None,
    invoke: Callable[..., dict[str, Any]] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if action not in {"preview", "sync"}:
        raise ValueError("weekly publication action must be preview or sync")
    if (period_start is None) != (period_end is None):
        raise ValueError("--period-start and --period-end must be provided together")
    explicit_period = None
    if period_start is not None and period_end is not None:
        _parse_period(period_start, period_end)
        explicit_period = (period_start, period_end)
    if wait_seconds < 0 or wait_seconds > 3600:
        raise ValueError("--wait-seconds must be between 0 and 3600")
    config = local_runtime._load_config(config_path.resolve())
    state_root = Path(config["state_root"]).expanduser().resolve()
    state_path = state_root / "weekly-publication-state.json"
    pending_path = state_root / "weekly-publication.lock"
    current = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    lock = local_runtime._exclusive_lock(pending_path) if action == "sync" else nullcontext()
    with lock:
        state = _load_state(state_path)
        pending = state.get("pending")
        pending_period = _period_for_bundle(pending["bundle"]) if pending else None
        if explicit_period and pending_period and explicit_period != pending_period:
            raise RuntimeError(
                "an older weekly publication is still pending; finish it before selecting another period"
            )
        if explicit_period:
            period = explicit_period
        elif pending_period:
            due_period = _auto_due_period(current)
            if due_period and due_period[1] > pending_period[1]:
                period = due_period
            else:
                period = pending_period
        else:
            period = _auto_due_period(current)
            if period is None:
                return _result("not_due", reason="no completed weekly publication is due")
        exported = _export_source(
            config,
            period,
            wait_seconds=wait_seconds if action == "sync" else 0,
            invoke=invoke,
            sleep=sleep,
        )
        if "pending_reason" in exported:
            return _result(
                "pending",
                period_start=period[0],
                period_end=period[1],
                reason=exported["pending_reason"],
                snapshot_id=exported.get("snapshot_id"),
            )
        bundle, digest = exported["bundle"], exported["bundle_sha256"]
        completed = state.get("last_completed")
        completed_same_period = (
            pending is None and completed is not None and completed.get("period_end") == period[1]
        )
        if completed_same_period:
            current_revision = _source_revision_sha256(bundle)
            completed_revision = completed.get("source_revision_sha256")
            if completed_revision == current_revision or (
                completed_revision is None and completed.get("bundle_sha256") == digest
            ):
                return _result(
                    "unchanged",
                    snapshot_id=completed["snapshot_id"],
                    bundle_sha256=completed["bundle_sha256"],
                    acknowledgements=_TARGETS,
                )
            completed_key = completed.get("source_revision_key")
            if not completed_key:
                return _result(
                    "conflict",
                    snapshot_id=completed["snapshot_id"],
                    reason="completed source revision changed without a stored revision key",
                )
            completed_key_dt = tuple(
                dt.datetime.fromisoformat(value.replace("Z", "+00:00")) for value in completed_key
            )
            if _revision_key(bundle) <= completed_key_dt:
                return _result(
                    "conflict",
                    snapshot_id=completed["snapshot_id"],
                    reason="completed source changed without a provably newer guide revision",
                )
            if action == "sync":
                _save_pending(state, bundle, digest, state_path)
                pending = state["pending"]
        if pending is not None:
            old_bundle = pending["bundle"]
            if _same_source_revision(old_bundle, bundle):
                bundle, digest = old_bundle, pending["bundle_sha256"]
            elif _revision_key(bundle) > _revision_key(old_bundle):
                if action == "sync":
                    _save_pending(state, bundle, digest, state_path)
                pending = state["pending"] if action == "sync" else None
            else:
                return _result(
                    "conflict",
                    snapshot_id=old_bundle["snapshot"]["id"],
                    reason="source publication changed without a provably newer revision",
                )
        elif action == "sync":
            _save_pending(state, bundle, digest, state_path)
            pending = state["pending"]
        summary = target_worker.validate_weekly_publication_bundle(bundle)
        if action == "preview":
            return _result(
                "ready",
                snapshot_id=summary["snapshot_id"],
                period_start=summary["period_start"],
                period_end=summary["period_end"],
                bundle_sha256=digest,
                recommendation_urls=summary["recommendation_urls"],
                pending_acknowledgements=tuple(
                    target for target in _TARGETS if pending and target not in pending["acks"]
                ),
            )
        assert pending is not None
        for target in _TARGETS:
            existing_ack = pending["acks"].get(target)
            if (
                target == "overseas"
                and existing_ack
                and existing_ack.get("bundle_sha256") == digest
            ):
                continue
            reply = (invoke or local_runtime._invoke_target_worker)(
                config,
                target,
                {
                    "operation": "apply_weekly_publication",
                    "schema_version": 1,
                    "target": target,
                    "mode": "freeze_source" if target == "china" else "import_replica",
                    "bundle": bundle,
                    "bundle_sha256": digest,
                },
            )
            if (
                reply.get("target") != target
                or reply.get("status") not in {"applied", "unchanged"}
                or reply.get("snapshot_id") != summary["snapshot_id"]
                or reply.get("bundle_sha256") != digest
                or reply.get("guide_generated_at") != summary["guide_generated_at"]
                or reply.get("card_projection_sha256") != summary["card_projection_sha256"]
                or reply.get("recommendation_urls") != summary["recommendation_urls"]
            ):
                raise RuntimeError(f"{target} did not acknowledge the frozen weekly publication")
            pending["acks"][target] = {
                "target": target,
                "snapshot_id": summary["snapshot_id"],
                "bundle_sha256": digest,
                "guide_generated_at": summary["guide_generated_at"],
                "card_projection_sha256": summary["card_projection_sha256"],
                "recommendation_urls": summary["recommendation_urls"],
                "status": reply["status"],
                "acknowledged_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
            local_runtime._atomic_json(state_path, state)
        state["last_completed"] = {
            "snapshot_id": summary["snapshot_id"],
            "period_start": summary["period_start"],
            "period_end": summary["period_end"],
            "bundle_sha256": digest,
            "source_revision_sha256": _source_revision_sha256(bundle),
            "source_revision_key": _revision_key_values(bundle),
            "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        state["pending"] = None
        local_runtime._atomic_json(state_path, state)
        return _result(
            "succeeded",
            snapshot_id=summary["snapshot_id"],
            period_start=summary["period_start"],
            period_end=summary["period_end"],
            bundle_sha256=digest,
            acknowledgements=_TARGETS,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview or relay a completed China weekly publication locally."
    )
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("preview", "sync"):
        command = sub.add_parser(
            action, help=f"{action} the exact China weekly publication locally"
        )
        command.add_argument(
            "--config",
            type=Path,
            default=Path("reports/local-automation-state/config.local.json"),
        )
        command.add_argument(
            "--period-start", help="Exact UTC week start for a manual one-time sync"
        )
        command.add_argument("--period-end", help="Exact UTC week end for a manual one-time sync")
        command.add_argument(
            "--wait-seconds",
            type=float,
            default=600 if action == "sync" else 0,
            help="Bounded read-only wait for the exact snapshot and complete guide (sync only)",
        )
        command.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_weekly_publication(
            args.action,
            config_path=args.config,
            period_start=args.period_start,
            period_end=args.period_end,
            wait_seconds=args.wait_seconds,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        result = {"success": False, "status": "error", "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("success") else 2


if __name__ == "__main__":
    raise SystemExit(main())
