#!/usr/bin/env python3
"""Offline daily rotation planner and receipt reporter; never runs collection."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    TIME_ZONE: ZoneInfo | None = ZoneInfo("America/New_York")
except ZoneInfoNotFoundError:
    TIME_ZONE = None

SITES = (
    "iaa",
    "iaba",
    "soa",
    "soa-ai-topic-landing",
    "soa-ai-bulletin-focused",
    "cas",
    "aaa",
    "cia-ica",
    "cia-research-publications",
    "cca",
    "aae",
    "eaa",
    "ifoa-uk",
    "france",
    "dav",
    "swiss-association-of-actuaries",
    "italy",
    "istituto-italiano-degli-attuari",
    "spain",
    "australia",
    "iai",
    "iaj",
    "institute-of-actuaries-of",
    "aict",
    "caa",
    "ashk",
    "assa",
    "task",
    "ama",
    "iba-brazil",
    "aca-colombia",
    "conac-mexico",
)
ROTATION_ANCHOR = date(2026, 10, 25)
BASELINE_SIZE = 6
MAX_EXTRA_RETRIES = 2
HELD_SITES = {"istituto-italiano-degli-attuari"}
MONITOR_ONLY_SITES = {"iaba", "eaa"}
RUN_STATUSES = {"succeeded", "partial", "failed"}
STAGE_STATUSES = RUN_STATUSES | {"pending", "unknown"}
READY_STATUSES = STAGE_STATUSES | {"not_required"}
COUNT_STAGES = ("downloaded", "new_versions", "duplicates", "enriched", "ai_candidates")
ACK_STAGES = ("china_ack", "overseas_ack")
ACK_COUNTS = ("acknowledged", "pending", "failed")
ALL_STAGES = (*COUNT_STAGES, *ACK_STAGES)


class FlowError(ValueError):
    """Input cannot safely be interpreted as a schedule, receipt, or ledger."""


def require_time_zone() -> ZoneInfo:
    if TIME_ZONE is None:
        raise FlowError(
            "Python needs IANA zone data for America/New_York; install tzdata in this Python environment"
        )
    return TIME_ZONE


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FlowError(f"{field} must be a non-negative integer")
    return value


def _string_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise FlowError(f"{field} must be an array of non-empty strings")
    return list(value)


def _normalize_telemetry(raw: Any, source: Path) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise FlowError(f"{source}: telemetry must be an object")
    allowed = {
        "elapsed_seconds",
        "source",
        "database",
        "enrichment",
        "conversion",
        "ai_first_candidate_count",
        "ai_first_candidate_ids",
        "targets",
    }
    extra = set(raw) - allowed
    if extra:
        raise FlowError(f"{source}: unsupported telemetry fields: {sorted(extra)}")
    result: dict[str, Any] = {}
    if "elapsed_seconds" in raw:
        elapsed = raw["elapsed_seconds"]
        if (
            isinstance(elapsed, bool)
            or not isinstance(elapsed, (int, float))
            or not math.isfinite(elapsed)
            or elapsed < 0
        ):
            raise FlowError(
                f"{source}: telemetry.elapsed_seconds must be a finite non-negative number"
            )
        result["elapsed_seconds"] = float(elapsed)
    if "source" in raw:
        value = raw["source"]
        allowed_source = {
            "request_count",
            "pages_visited",
            "links_discovered",
            "files_by_type",
            "file_ids",
            "page_ids",
            "link_ids",
        }
        if not isinstance(value, dict) or set(value) - allowed_source:
            raise FlowError(f"{source}: telemetry.source has an invalid shape")
        normalized_source = dict(value)
        for name in ("request_count", "pages_visited", "links_discovered"):
            if name in value:
                normalized_source[name] = _nonnegative_int(
                    value[name], f"{source}: telemetry.source.{name}"
                )
        if "files_by_type" in value:
            files = value["files_by_type"]
            if not isinstance(files, dict) or set(files) != {"html", "pdf", "other"}:
                raise FlowError(
                    f"{source}: telemetry.source.files_by_type must contain html, pdf and other"
                )
            normalized_source["files_by_type"] = {
                name: _nonnegative_int(
                    files[name], f"{source}: telemetry.source.files_by_type.{name}"
                )
                for name in ("html", "pdf", "other")
            }
        for name in ("file_ids", "page_ids", "link_ids"):
            if name in value:
                normalized_source[name] = sorted(
                    set(_string_list(value[name], f"{source}: telemetry.source.{name}"))
                )
        result["source"] = normalized_source
    if "database" in raw:
        value = raw["database"]
        allowed_database = {"new_version_ids", "duplicate_version_ids"}
        if not isinstance(value, dict) or set(value) - allowed_database:
            raise FlowError(f"{source}: telemetry.database has an invalid shape")
        result["database"] = {
            name: sorted(
                set(_string_list(value.get(name, []), f"{source}: telemetry.database.{name}"))
            )
            for name in allowed_database
            if name in value
        }
    if "conversion" in raw:
        value = raw["conversion"]
        allowed_conversion = {"succeeded_count", "failed_count", "succeeded_ids", "failed_ids"}
        if not isinstance(value, dict) or set(value) - allowed_conversion:
            raise FlowError(f"{source}: telemetry.conversion has an invalid shape")
        result["conversion"] = {
            name: _nonnegative_int(value[name], f"{source}: telemetry.conversion.{name}")
            for name in ("succeeded_count", "failed_count")
            if name in value
        }
        result["conversion"].update(
            {
                name: sorted(
                    set(_string_list(value.get(name, []), f"{source}: telemetry.conversion.{name}"))
                )
                for name in ("succeeded_ids", "failed_ids")
                if name in value
            }
        )
    if "enrichment" in raw:
        value = raw["enrichment"]
        if not isinstance(value, dict) or set(value) - {"succeeded_count", "succeeded_ids"}:
            raise FlowError(f"{source}: telemetry.enrichment has an invalid shape")
        result["enrichment"] = {
            "succeeded_count": _nonnegative_int(
                value["succeeded_count"], f"{source}: telemetry.enrichment.succeeded_count"
            )
        }
        if "succeeded_ids" in value:
            result["enrichment"]["succeeded_ids"] = sorted(
                set(
                    _string_list(
                        value["succeeded_ids"],
                        f"{source}: telemetry.enrichment.succeeded_ids",
                    )
                )
            )
    if "ai_first_candidate_count" in raw:
        result["ai_first_candidate_count"] = _nonnegative_int(
            raw["ai_first_candidate_count"], f"{source}: telemetry.ai_first_candidate_count"
        )
    if "ai_first_candidate_ids" in raw:
        result["ai_first_candidate_ids"] = sorted(
            set(
                _string_list(
                    raw["ai_first_candidate_ids"], f"{source}: telemetry.ai_first_candidate_ids"
                )
            )
        )
    if "targets" in raw:
        values = raw["targets"]
        if not isinstance(values, dict) or set(values) - {"china", "overseas"}:
            raise FlowError(f"{source}: telemetry.targets has an invalid shape")
        targets: dict[str, Any] = {}
        for target, value in values.items():
            if not isinstance(value, dict) or set(value) - {
                "acknowledged_ids",
                "ready_status",
                "ready_ids",
                "invalidated_ready_ids",
            }:
                raise FlowError(f"{source}: telemetry.targets.{target} has an invalid shape")
            normalized = {
                name: sorted(
                    set(
                        _string_list(
                            value.get(name, []), f"{source}: telemetry.targets.{target}.{name}"
                        )
                    )
                )
                for name in ("acknowledged_ids", "ready_ids", "invalidated_ready_ids")
                if name in value
            }
            if "ready_status" in value:
                ready_status = value["ready_status"]
                if not isinstance(ready_status, str) or ready_status not in READY_STATUSES:
                    raise FlowError(f"{source}: telemetry.targets.{target}.ready_status is invalid")
                normalized["ready_status"] = ready_status
            targets[target] = normalized
        result["targets"] = targets
    return result


def _normalize_failure_fields(
    raw: dict[str, Any], prefix: str, *, require_partial_error: bool = True
) -> dict[str, Any]:
    error = raw.get("error")
    evidence = _string_list(raw.get("evidence", []), f"{prefix}.evidence")
    if error is not None and (not isinstance(error, str) or not error.strip()):
        raise FlowError(f"{prefix}.error must be a non-empty string when supplied")
    status = raw.get("status", "unknown")
    if status in {"failed", "partial"} and require_partial_error and not error:
        raise FlowError(f"{prefix}.error is required for {status} status")
    return {"error": error, "evidence": evidence}


def _normalize_stage(raw: Any, stage: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise FlowError(f"stages.{stage} must be an object")
    if stage == "monitor":
        allowed = {"status", "error", "evidence"}
    elif stage in COUNT_STAGES:
        allowed = {"status", "count", "pending_count", "error", "evidence"}
        if stage == "downloaded":
            allowed.add("request_budget")
    else:
        allowed = {
            "status",
            *ACK_COUNTS,
            "ready_status",
            "ready_error",
            "ready_evidence",
            "error",
            "evidence",
        }
    extra = set(raw) - allowed
    if extra:
        raise FlowError(f"stages.{stage} has unsupported fields: {sorted(extra)}")
    status = raw.get("status", "unknown")
    if not isinstance(status, str) or status not in STAGE_STATUSES:
        raise FlowError(f"stages.{stage}.status must be one of {sorted(STAGE_STATUSES)}")
    request_budget = None
    if stage == "downloaded" and "request_budget" in raw:
        budget = raw["request_budget"]
        if not isinstance(budget, dict) or set(budget) != {
            "used",
            "cap",
            "paused",
            "frontier_remaining",
        }:
            raise FlowError("stages.downloaded.request_budget has an invalid shape")
        used = _nonnegative_int(budget["used"], "stages.downloaded.request_budget.used")
        cap = _nonnegative_int(budget["cap"], "stages.downloaded.request_budget.cap")
        remaining = _nonnegative_int(
            budget["frontier_remaining"], "stages.downloaded.request_budget.frontier_remaining"
        )
        paused = budget["paused"]
        if not isinstance(paused, bool) or cap < 1 or used > cap:
            raise FlowError("stages.downloaded.request_budget values are inconsistent")
        request_budget = {
            "used": used,
            "cap": cap,
            "paused": paused,
            "frontier_remaining": remaining,
        }
    pure_budget_pause = bool(
        stage == "downloaded"
        and status == "partial"
        and request_budget
        and request_budget["paused"]
        and raw.get("error") is None
    )
    result: dict[str, Any] = {
        "status": status,
        **_normalize_failure_fields(
            raw, f"stages.{stage}", require_partial_error=not pure_budget_pause
        ),
    }
    if stage in COUNT_STAGES:
        count = raw.get("count")
        result["count"] = (
            None if count is None else _nonnegative_int(count, f"stages.{stage}.count")
        )
        if "pending_count" in raw:
            pending_count = raw["pending_count"]
            result["pending_count"] = (
                None
                if pending_count is None
                else _nonnegative_int(pending_count, f"stages.{stage}.pending_count")
            )
        if stage == "downloaded" and "request_budget" in raw:
            result["request_budget"] = request_budget
    elif stage in ACK_STAGES:
        for field in ACK_COUNTS:
            count = raw.get(field)
            result[field] = (
                None if count is None else _nonnegative_int(count, f"stages.{stage}.{field}")
            )
        ready_status = raw.get("ready_status", "unknown")
        if not isinstance(ready_status, str) or ready_status not in READY_STATUSES:
            raise FlowError(f"stages.{stage}.ready_status must be one of {sorted(READY_STATUSES)}")
        ready_error = raw.get("ready_error")
        if ready_error is not None and (
            not isinstance(ready_error, str) or not ready_error.strip()
        ):
            raise FlowError(f"stages.{stage}.ready_error must be a non-empty string when supplied")
        if ready_status in {"failed", "partial"} and not ready_error:
            raise FlowError(
                f"stages.{stage}.ready_error is required for {ready_status} ready_status"
            )
        result.update(
            {
                "ready_status": ready_status,
                "ready_error": ready_error,
                "ready_evidence": _string_list(
                    raw.get("ready_evidence", []), f"stages.{stage}.ready_evidence"
                ),
            }
        )
    return result


def normalize_receipt(raw: Any, source: Path) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise FlowError(f"{source}: receipt root must be an object")
    if raw.get("schema_version") == 1:
        raise FlowError(
            f"{source}: legacy v1 slot receipt is not supported; quarantine it outside the daily v2 receipt directory"
        )
    allowed = {
        "schema_version",
        "receipt_id",
        "date_local",
        "site_id",
        "run_status",
        "reason",
        "evidence",
        "attempt_count",
        "stages",
        "telemetry",
    }
    extra = set(raw) - allowed
    if extra:
        raise FlowError(f"{source}: unsupported receipt fields: {sorted(extra)}")
    if isinstance(raw.get("schema_version"), bool) or raw.get("schema_version") != 2:
        raise FlowError(f"{source}: schema_version must be 2")
    day_value, site = raw.get("date_local"), raw.get("site_id")
    if not isinstance(day_value, str):
        raise FlowError(f"{source}: date_local is required (YYYY-MM-DD)")
    try:
        day = date.fromisoformat(day_value)
    except ValueError as exc:
        raise FlowError(f"{source}: date_local must use YYYY-MM-DD") from exc
    if day.isoformat() != day_value:
        raise FlowError(f"{source}: date_local must use YYYY-MM-DD")
    if not isinstance(site, str) or site not in SITES:
        raise FlowError(f"{source}: unknown site_id {site!r}")
    receipt_id = raw.get("receipt_id")
    expected_id = f"{day_value}/{site}"
    if receipt_id != expected_id:
        raise FlowError(f"{source}: receipt_id must be the stable date/site key {expected_id!r}")
    if site in HELD_SITES:
        raise FlowError(f"{source}: held site {site} must not have an execution receipt")
    run_status = raw.get("run_status")
    if not isinstance(run_status, str) or run_status not in RUN_STATUSES:
        raise FlowError(f"{source}: run_status must be one of {sorted(RUN_STATUSES)}")
    reason = raw.get("reason")
    if reason is not None and (not isinstance(reason, str) or not reason.strip()):
        raise FlowError(f"{source}: reason must be a non-empty string when supplied")
    evidence = _string_list(raw.get("evidence", []), f"{source}: evidence")
    if run_status in {"failed", "partial"} and not reason:
        raise FlowError(f"{source}: reason is required for {run_status} run_status")
    attempt_count = _nonnegative_int(raw.get("attempt_count", 1), f"{source}: attempt_count")
    if attempt_count < 1:
        raise FlowError(f"{source}: attempt_count must be at least 1")
    stages = raw.get("stages", {})
    if not isinstance(stages, dict):
        raise FlowError(f"{source}: stages must be an object")
    expected_stages = {"monitor"} if site in MONITOR_ONLY_SITES else set(ALL_STAGES)
    extra_stages = set(stages) - expected_stages
    if extra_stages:
        if site in MONITOR_ONLY_SITES:
            raise FlowError(
                f"{source}: monitor_only site {site} cannot include collection, enrichment, AI, or publish stages: {sorted(extra_stages)}"
            )
        raise FlowError(f"{source}: unsupported stages for {site}: {sorted(extra_stages)}")
    normalized = {stage: _normalize_stage(stages[stage], stage) for stage in stages}
    if site in MONITOR_ONLY_SITES and "monitor" not in normalized:
        raise FlowError(f"{source}: monitor_only receipt must include the structural monitor stage")
    receipt = {
        "schema_version": 2,
        "receipt_id": receipt_id,
        "date_local": day_value,
        "site_id": site,
        "run_status": run_status,
        "reason": reason,
        "evidence": evidence,
        "attempt_count": attempt_count,
        "stages": normalized,
    }
    if "telemetry" in raw:
        receipt["telemetry"] = _normalize_telemetry(raw["telemetry"], source)
    return receipt


def read_receipts(receipts_path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    paths = sorted(receipts_path.rglob("*.json")) if receipts_path.is_dir() else [receipts_path]
    receipts: dict[tuple[str, str], dict[str, Any]] = {}
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FlowError(f"cannot read receipt {path}: {exc}") from exc
        receipt = normalize_receipt(raw, path)
        key = (receipt["date_local"], receipt["site_id"])
        prior = receipts.get(key)
        if prior is not None and prior != receipt:
            raise FlowError(
                f"conflicting receipts for {key}; keep one finalized receipt per date/site"
            )
        receipts[key] = receipt
    return receipts


def _date_receipts(
    receipts: dict[tuple[str, str], dict[str, Any]], day: date
) -> dict[str, dict[str, Any]]:
    key = day.isoformat()
    return {
        site: receipt for (receipt_day, site), receipt in receipts.items() if receipt_day == key
    }


def _action(site: str) -> str:
    if site in HELD_SITES:
        return "hold"
    if site in MONITOR_ONLY_SITES:
        return "monitor_only"
    return "collect"


def baseline_sites(day: date) -> list[str]:
    offset = ((day - ROTATION_ANCHOR).days * BASELINE_SIZE) % len(SITES)
    return [SITES[(offset + i) % len(SITES)] for i in range(BASELINE_SIZE)]


def _stage_failures(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    stages = receipt["stages"]
    for name, stage in stages.items():
        budget_only = (
            name == "downloaded"
            and stage["status"] == "partial"
            and stage.get("error") is None
            and stage.get("request_budget", {}).get("paused") is True
        )
        if stage["status"] in {"failed", "partial"} and not budget_only:
            failures.append(
                {
                    "stage": name,
                    "error": stage["error"] or receipt.get("reason") or "stage reported failure",
                    "evidence": stage["evidence"] or receipt["evidence"],
                }
            )
        if name in ACK_STAGES and stage.get("ready_status") in {"failed", "partial"}:
            failures.append(
                {
                    "stage": name.replace("_ack", "_ready"),
                    "error": stage["ready_error"] or "Ready reported failure",
                    "evidence": stage["ready_evidence"],
                }
            )
    if (
        receipt["run_status"] in {"failed", "partial"}
        and not failures
        and not _budget_pause_only(receipt)
    ):
        failures.append(
            {
                "stage": "run",
                "error": receipt["reason"] or f"run status {receipt['run_status']}",
                "evidence": receipt["evidence"],
            }
        )
    return failures


def _budget_pause_only(receipt: dict[str, Any]) -> bool:
    stages = receipt.get("stages") or {}
    downloaded = stages.get("downloaded") or {}
    budget = downloaded.get("request_budget") or {}
    ai = (receipt.get("stages") or {}).get("ai_candidates") or {}
    if not (
        receipt.get("run_status") == "partial"
        and downloaded.get("status") == "partial"
        and downloaded.get("error") is None
        and budget.get("paused") is True
    ):
        return False
    for name, stage in stages.items():
        if name == "downloaded":
            continue
        if stage.get("status") not in {"succeeded", "unknown"}:
            return False
        if name in ACK_STAGES:
            ready = stage.get("ready_status")
            if ready not in {"succeeded", "unknown"} and not (
                ready == "not_required" and not (ai.get("count") or 0)
            ):
                return False
    return True


def _effective_status(receipt: dict[str, Any]) -> tuple[str, str | None]:
    failures = _stage_failures(receipt)
    if receipt["run_status"] == "failed":
        return "failed", receipt.get("reason") or (
            failures[0]["error"] if failures else "run failed"
        )
    if receipt["run_status"] == "partial" or failures:
        return "partial", receipt.get("reason") or failures[0]["error"]
    if receipt["site_id"] in MONITOR_ONLY_SITES:
        monitor = receipt["stages"].get("monitor")
        if not monitor or monitor["status"] in {"pending", "unknown"}:
            return "partial", "structural monitor result is pending or unknown"
    else:
        for name in COUNT_STAGES:
            stage = receipt["stages"].get(name)
            if not stage or stage["status"] in {"pending", "unknown"}:
                return "partial", f"{name} stage is pending or unknown"
    ai = receipt["stages"].get("ai_candidates")
    if ai and (ai["count"] is None or ai["status"] in {"pending", "unknown"}):
        return (
            "partial",
            "AI-candidate result is unknown; publish applicability cannot be determined",
        )
    if ai and ai["count"] is not None and ai["count"] > 0:
        for stage_name in ACK_STAGES:
            stage = receipt["stages"].get(stage_name)
            if (
                not stage
                or stage["status"] in {"pending", "unknown"}
                or stage["ready_status"] in {"pending", "unknown", "not_required"}
            ):
                return (
                    "partial",
                    f"AI candidates exist; {stage_name} acknowledgement or native Ready is not confirmed",
                )
    return "succeeded", None


def _latest_receipt_by_site(
    receipts: dict[tuple[str, str], dict[str, Any]], before: date | None = None
) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for (day_text, site), receipt in receipts.items():
        day = date.fromisoformat(day_text)
        if before is not None and day >= before:
            continue
        if site not in latest or day_text > latest[site]["date_local"]:
            latest[site] = receipt
    return latest


def _retry_candidate_sites(receipts: dict[tuple[str, str], dict[str, Any]], day: date) -> list[str]:
    latest = _latest_receipt_by_site(receipts, before=day)
    ranked: list[tuple[str, int]] = []
    active = _active_failure_cases(receipts, day - timedelta(days=1))
    failed_sites = {case["site_id"] for case in active.values()}
    for site in failed_sites:
        receipt = latest.get(site)
        if site in HELD_SITES or receipt is None:
            continue
        ranked.append((receipt["date_local"], SITES.index(site)))
    sites = [SITES[index] for _, index in sorted(ranked)]
    if sites:
        # A date-based cursor rotates a stable failure queue even if a planned retry has no receipt.
        cursor = (day - ROTATION_ANCHOR).days % len(sites)
        sites = sites[cursor:] + sites[:cursor]
    return sites


def make_plan(
    day: date, receipts: dict[tuple[str, str], dict[str, Any]] | None = None
) -> dict[str, Any]:
    receipts = receipts or {}
    baseline = baseline_sites(day)
    baseline_set = set(baseline)
    retry_candidates = [
        site for site in _retry_candidate_sites(receipts, day) if site not in baseline_set
    ]
    retries = retry_candidates[:MAX_EXTRA_RETRIES]
    items = []
    for site in baseline:
        items.append({"site_id": site, "action": _action(site), "slot": "baseline"})
    for site in retries:
        items.append({"site_id": site, "action": _action(site), "slot": "extra_retry"})
    local_at = datetime.combine(day, time(6, 0), require_time_zone())
    return {
        "schema_version": 2,
        "mode": "offline_daily_plan",
        "date_local": day.isoformat(),
        "timezone": "America/New_York",
        "scheduled_local_at": local_at.isoformat(timespec="minutes"),
        "rotation_anchor_date": ROTATION_ANCHOR.isoformat(),
        "baseline_size": BASELINE_SIZE,
        "max_extra_retries": MAX_EXTRA_RETRIES,
        "baseline_sites": baseline,
        "extra_retry_sites": retries,
        "retry_candidates_deferred": retry_candidates[MAX_EXTRA_RETRIES:],
        "items": items,
        "hold_sites": sorted(HELD_SITES.intersection(items_site for items_site in baseline)),
        "monitor_only_sites": sorted(MONITOR_ONLY_SITES.intersection(baseline)),
        "seven_day_baseline_coverage_claim": "Any consecutive seven local dates cover all 32 site IDs in the deterministic six-position rotation; this is scheduled coverage, not successful collection.",
        "executes_collection": False,
        "writes_hub_or_servers": False,
        "writes_case_ledger": False,
    }


def _load_ledger(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FlowError(f"cannot read case ledger {path}: {exc}") from exc
    if (
        not isinstance(raw, dict)
        or raw.get("schema_version") != 1
        or not isinstance(raw.get("cases"), list)
    ):
        raise FlowError(f'{path}: case ledger must be {{"schema_version":1,"cases":[]}}')
    ledger: dict[str, dict[str, Any]] = {}
    for case in raw["cases"]:
        if not isinstance(case, dict) or not isinstance(case.get("case_id"), str):
            raise FlowError(f"{path}: every ledger case needs a case_id")
        if case["case_id"] in ledger:
            raise FlowError(f"{path}: duplicate case_id {case['case_id']!r}")
        ledger[case["case_id"]] = case
    return ledger


def _case_identity(site: str, stage: str, error: str) -> str:
    stable_error = " ".join(error.casefold().split())
    digest = hashlib.sha256(f"{site}\0{stage}\0{stable_error}".encode()).hexdigest()[:16]
    return f"case-{digest}"


def _evidence_fingerprint(error: str, evidence: list[str]) -> str:
    payload = json.dumps({"error": error, "evidence": evidence}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:20]


def _failure_fold(
    receipts: dict[tuple[str, str], dict[str, Any]], through: date
) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    active: dict[tuple[str, str], dict[str, Any]] = {}
    last_success: dict[tuple[str, str], dict[str, Any]] = {}
    for (day_text, site), receipt in sorted(receipts.items()):
        if date.fromisoformat(day_text) > through:
            continue
        stage_failures = _stage_failures(receipt)
        events: list[tuple[str, str, dict[str, Any]]] = []
        if receipt["run_status"] == "succeeded":
            events.append(("run", "succeeded", {"error": None, "evidence": receipt["evidence"]}))
        elif (
            not stage_failures
            and not _budget_pause_only(receipt)
            and not _not_required_ready_only(receipt)
        ):
            events.append(
                (
                    "run",
                    receipt["run_status"],
                    {"error": receipt.get("reason"), "evidence": receipt["evidence"]},
                )
            )
        for stage, value in receipt["stages"].items():
            if (
                stage == "downloaded"
                and value["status"] == "partial"
                and value.get("error") is None
                and value.get("request_budget", {}).get("paused") is True
            ):
                continue
            events.append(
                (stage, value["status"], {"error": value["error"], "evidence": value["evidence"]})
            )
            if stage in ACK_STAGES:
                events.append(
                    (
                        stage.replace("_ack", "_ready"),
                        value["ready_status"],
                        {
                            "error": value["ready_error"],
                            "evidence": value["ready_evidence"],
                        },
                    )
                )
        for stage, state, detail in events:
            key = (site, stage)
            if state == "succeeded":
                active.pop(key, None)
                last_success[key] = {"receipt_id": receipt["receipt_id"], "date_local": day_text}
            elif state in {"failed", "partial"}:
                error = detail["error"] or f"{stage} reported {state}"
                evidence = detail["evidence"]
                case_id = _case_identity(site, stage, error)
                active[key] = {
                    "case_id": case_id,
                    "site_id": site,
                    "stage": stage,
                    "error": error,
                    "evidence": evidence,
                    "evidence_fingerprint": _evidence_fingerprint(error, evidence),
                    "last_observed_date": day_text,
                    "state": "active",
                }
            # pending/unknown are observations, never recovery evidence.
    return {case["case_id"]: case for case in active.values()}, last_success


def _not_required_ready_only(receipt: dict[str, Any]) -> bool:
    ai_count = ((receipt.get("stages") or {}).get("ai_candidates") or {}).get("count") or 0
    return bool(
        ai_count
        and any(
            stage.get("ready_status") == "not_required"
            for name, stage in (receipt.get("stages") or {}).items()
            if name in ACK_STAGES
        )
        and not _stage_failures(receipt)
    )


def _active_failure_cases(
    receipts: dict[tuple[str, str], dict[str, Any]], day: date
) -> dict[str, dict[str, Any]]:
    return _failure_fold(receipts, day)[0]


def _failure_case_updates(
    active: dict[str, dict[str, Any]],
    ledger: dict[str, dict[str, Any]],
    receipts: dict[tuple[str, str], dict[str, Any]],
    day: date,
) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    _, last_success = _failure_fold(receipts, day)
    for case_id, case in active.items():
        old = ledger.get(case_id)
        if old is None:
            action = "open"
        elif old.get("evidence_fingerprint") != case["evidence_fingerprint"]:
            action = "update"
        elif old.get("state") == "closed":
            action = "reopen"
        else:
            action = "observe"
        researched_date = old.get("last_researched_date") if old else None
        researched_fingerprint = old.get("last_researched_fingerprint") if old else None
        if old and researched_fingerprint is None and researched_date:
            researched_fingerprint = old.get("evidence_fingerprint")
        updates.append(
            {
                **case,
                "action": action,
                "last_researched_date": researched_date,
                "last_researched_fingerprint": researched_fingerprint,
            }
        )
    for case_id, old in ledger.items():
        if case_id in active or old.get("state") == "closed":
            continue
        site, stage = old.get("site_id"), old.get("stage")
        if not isinstance(site, str) or not isinstance(stage, str):
            continue
        replacement = next(
            (
                case
                for case in active.values()
                if case["site_id"] == site and case["stage"] == stage
            ),
            None,
        )
        if replacement:
            updates.append(
                {
                    **old,
                    "action": "supersede",
                    "superseded_by": replacement["case_id"],
                    "state": "closed",
                }
            )
            continue
        success = last_success.get((site, stage))
        if success and success["date_local"] > old.get("last_observed_date", "0000-00-00"):
            updates.append(
                {
                    **old,
                    "action": "close",
                    "state": "closed",
                    "closed_by_receipt": success["receipt_id"],
                    "last_observed_date": success["date_local"],
                }
            )
        else:
            updates.append({**old, "action": "preserve", "state": "active"})
    return sorted(
        updates,
        key=lambda c: (
            SITES.index(c["site_id"]) if c.get("site_id") in SITES else len(SITES),
            c.get("stage", ""),
            c["case_id"],
        ),
    )


def _research_queue(
    active: dict[str, dict[str, Any]], ledger: dict[str, dict[str, Any]], day: date
) -> list[dict[str, Any]]:
    pending = []
    for case_id, case in active.items():
        old = ledger.get(case_id, {})
        researched_fingerprint = old.get("last_researched_fingerprint")
        if researched_fingerprint is None and old.get("last_researched_date"):
            researched_fingerprint = old.get("evidence_fingerprint")
        already_researched = (
            old.get("last_researched_date")
            and researched_fingerprint == case["evidence_fingerprint"]
        )
        if not already_researched:
            pending.append({**case, "last_researched_date": old.get("last_researched_date")})

    def priority(case: dict[str, Any]) -> tuple[str, int, str, str]:
        researched = case["last_researched_date"] or "0000-00-00"
        return researched, SITES.index(case["site_id"]), case["stage"], case["case_id"]

    return sorted(pending, key=priority)


def _site_row(
    site: str, day: date, plan: dict[str, Any], actual: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    planned_item = next((item for item in plan["items"] if item["site_id"] == site), None)
    action = _action(site)
    receipt = actual.get(site)
    if action == "hold":
        state, reason = "hold", "Istituto remains a held maintenance candidate"
    elif receipt is None:
        state = "not_run" if planned_item else "not_scheduled"
        reason = (
            "scheduled receipt missing; this is a scheduling gap, not a source failure"
            if planned_item
            else None
        )
    else:
        state, reason = _effective_status(receipt)
    failures = _stage_failures(receipt) if receipt else []
    stages = receipt.get("stages", {}) if receipt else {}
    pending_stage = stages.get("enriched") or stages.get("new_versions") or {}
    result = {
        "site_id": site,
        "action": action,
        "plan_slot": planned_item["slot"] if planned_item else None,
        "state": state,
        "reason": reason,
        "failure_stages": failures,
        "receipt_id": receipt["receipt_id"] if receipt else None,
        "attempt_count": receipt["attempt_count"] if receipt else 0,
        "evidence": receipt["evidence"] if receipt else [],
    }
    if pending_stage.get("pending_count") is not None:
        result["pending_article_count"] = pending_stage["pending_count"]
    request_budget = (stages.get("downloaded") or {}).get("request_budget")
    if request_budget is not None:
        result["request_budget"] = request_budget
    return result


def make_status(day: date, receipts: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    plan = make_plan(day, receipts)
    actual = _date_receipts(receipts, day)
    rows = [_site_row(site, day, plan, actual) for site in SITES]
    baseline_set = set(plan["baseline_sites"])
    extra_set = set(plan["extra_retry_sites"])
    outside = sorted(site for site in actual if site not in baseline_set and site not in extra_set)
    repeated = sorted(site for site, receipt in actual.items() if receipt["attempt_count"] > 1)
    actual_attempts = sum(receipt["attempt_count"] for receipt in actual.values())
    return {
        "schema_version": 2,
        "mode": "offline_daily_status",
        "date_local": day.isoformat(),
        "timezone": "America/New_York",
        "plan": plan,
        "states": dict(sorted(Counter(row["state"] for row in rows).items())),
        "baseline_count": len(plan["baseline_sites"]),
        "extra_retry_count": len(plan["extra_retry_sites"]),
        "actual_receipt_count": len(actual),
        "unplanned_receipt_sites": outside,
        "budget_exceptions": {
            "unplanned_actual_sites": outside,
            "has_outside_plan_receipts": bool(outside),
            "actual_distinct_receipt_sites": len(actual),
            "daily_distinct_site_cap": BASELINE_SIZE + MAX_EXTRA_RETRIES,
            "exceeds_daily_site_cap": len(actual) > BASELINE_SIZE + MAX_EXTRA_RETRIES,
            "actual_attempt_count": actual_attempts,
            "daily_attempt_cap": BASELINE_SIZE + MAX_EXTRA_RETRIES,
            "exceeds_daily_attempt_cap": actual_attempts > BASELINE_SIZE + MAX_EXTRA_RETRIES,
            "unplanned_repeat_attempt_sites": repeated,
            "has_unplanned_repeat_attempts": bool(repeated),
            "has_budget_exception": bool(outside or repeated)
            or actual_attempts > BASELINE_SIZE + MAX_EXTRA_RETRIES
            or len(actual) > BASELINE_SIZE + MAX_EXTRA_RETRIES,
        },
        "rows": rows,
        "executes_collection": False,
        "writes_hub_or_servers": False,
        "writes_case_ledger": False,
    }


def _counter_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    states = ("succeeded", "partial", "failed", "not_run", "not_scheduled", "hold")
    return {
        state: {
            "count": sum(row["state"] == state for row in rows),
            "sites": [row["site_id"] for row in rows if row["state"] == state],
        }
        for state in states
    }


def _window_day(day: date, receipts: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    status = make_status(day, receipts)
    rows = status["rows"]
    attempted = [site for site in SITES if site in _date_receipts(receipts, day)]
    collection_attempted = [site for site in attempted if _action(site) == "collect"]
    monitor_attempted = [site for site in attempted if _action(site) == "monitor_only"]
    planned = status["plan"]["baseline_sites"] + status["plan"]["extra_retry_sites"]
    return {
        "date_local": day.isoformat(),
        "planned_sites": planned,
        "planned_count": len(planned),
        "planned_unique_sites": sorted(set(planned)),
        "attempted_sites": attempted,
        "attempted_count": len(attempted),
        "collection_attempted_sites": collection_attempted,
        "monitor_attempted_sites": monitor_attempted,
        "states": _counter_rows(rows),
        "budget_exceptions": status["budget_exceptions"],
    }


def _aggregate_count_stage(receipts: list[dict[str, Any]], stage: str) -> dict[str, Any]:
    states = Counter()
    known_counts: list[int] = []
    unknown_count = 0
    pending_counts: list[int] = []
    pending_unknown = 0
    for receipt in receipts:
        value = receipt["stages"].get(stage)
        if value is None:
            states["unknown"] += 1
            unknown_count += 1
        else:
            states[value["status"]] += 1
            if value["count"] is None:
                unknown_count += 1
            else:
                known_counts.append(value["count"])
            if "pending_count" in value:
                if value["pending_count"] is None:
                    pending_unknown += 1
                else:
                    pending_counts.append(value["pending_count"])
    result = {
        "run_observation_sum": sum(known_counts) if known_counts else None,
        "known_receipts": len(known_counts),
        "unknown_receipts": unknown_count,
        "status_counts": dict(sorted(states.items())),
    }
    if pending_counts or pending_unknown:
        result["pending_article_count_observation_sum"] = (
            sum(pending_counts) if pending_counts else None
        )
        result["pending_article_count_known_receipts"] = len(pending_counts)
        result["pending_article_count_unknown_receipts"] = pending_unknown
    return result


def _aggregate_ack_stage(receipts: list[dict[str, Any]], stage: str) -> dict[str, Any]:
    statuses: Counter[str] = Counter()
    ready_statuses: Counter[str] = Counter()
    counts = {field: [] for field in ACK_COUNTS}
    unknown = {field: 0 for field in ACK_COUNTS}
    for receipt in receipts:
        value = receipt["stages"].get(stage)
        if value is None:
            statuses["unknown"] += 1
            ready_statuses["unknown"] += 1
            for field in ACK_COUNTS:
                unknown[field] += 1
            continue
        statuses[value["status"]] += 1
        ready_statuses[value["ready_status"]] += 1
        for field in ACK_COUNTS:
            if value[field] is None:
                unknown[field] += 1
            else:
                counts[field].append(value[field])
    return {
        "status_counts": dict(sorted(statuses.items())),
        "ready_status_counts": dict(sorted(ready_statuses.items())),
        **{
            field: {
                "run_observation_sum": sum(values) if values else None,
                "known_receipts": len(values),
                "unknown_receipts": unknown[field],
            }
            for field, values in counts.items()
        },
    }


def _aggregate_telemetry(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    def observation(field: str, parent: str | None = None) -> dict[str, Any]:
        values = []
        known = 0
        for receipt in receipts:
            source = receipt.get("telemetry") or {}
            value = source.get(parent, {}).get(field) if parent else source.get(field)
            if value is not None:
                values.append(value)
                known += 1
        return {
            "observation_sum": sum(values) if values else None,
            "known_receipts": known,
            "unknown_receipts": len(receipts) - known,
        }

    def unique_count(parent: str, field: str, nested: str | None = None) -> dict[str, Any]:
        known = 0
        identities: set[str] = set()
        for receipt in receipts:
            telemetry = receipt.get("telemetry") or {}
            value = telemetry if parent is None else telemetry.get(parent)
            if nested:
                value = value.get(nested) if isinstance(value, dict) else None
            if isinstance(value, dict) and field in value:
                known += 1
                identities.update(value[field])
            elif nested is None and isinstance(value, list):
                known += 1
                identities.update(value)
        return {
            "exact_unique_count": len(identities) if known else None,
            "known_receipts": known,
            "unknown_receipts": len(receipts) - known,
        }

    source = {
        name: observation(name, "source")
        for name in ("request_count", "pages_visited", "links_discovered")
    }
    for kind in ("html", "pdf", "other"):
        values = []
        known = 0
        for receipt in receipts:
            file_types = (receipt.get("telemetry") or {}).get("source", {}).get("files_by_type")
            if isinstance(file_types, dict):
                values.append(file_types[kind])
                known += 1
        source[f"{kind}_files"] = {
            "observation_sum": sum(values) if values else None,
            "known_receipts": known,
            "unknown_receipts": len(receipts) - known,
        }
    for name in ("file_ids", "page_ids", "link_ids"):
        source[f"unique_{name.removesuffix('_ids')}_count"] = unique_count("source", name)

    database = {}
    for stage, field in (
        ("new_versions", "new_version_ids"),
        ("duplicates", "duplicate_version_ids"),
    ):
        database[stage] = {
            **_aggregate_count_stage(receipts, stage),
            **unique_count("database", field),
        }
    conversion = {}
    for count_field, ids_field in (
        ("succeeded_count", "succeeded_ids"),
        ("failed_count", "failed_ids"),
    ):
        conversion[count_field.removesuffix("_count")] = {
            **observation(count_field, "conversion"),
            **unique_count("conversion", ids_field),
        }
    enrichment = {
        **observation("succeeded_count", "enrichment"),
        **unique_count("enrichment", "succeeded_ids"),
    }
    ai_first = {
        "observations": observation("ai_first_candidate_count"),
        "exact_unique_count": unique_count(None, "ai_first_candidate_ids"),
    }
    targets: dict[str, Any] = {}
    for target in ("china", "overseas"):
        stage_report = _aggregate_ack_stage(receipts, f"{target}_ack")
        ack_ids = set()
        ready_ids = set()
        ack_known = ready_known = 0
        for receipt in receipts:
            stage = (receipt.get("telemetry") or {}).get("targets", {}).get(target, {})
            if "acknowledged_ids" in stage:
                ack_known += 1
                ack_ids.update(stage["acknowledged_ids"])
            if "ready_ids" in stage:
                ready_known += 1
                ready_ids.update(stage["ready_ids"])
        targets[target] = {
            **stage_report,
            "acknowledged_exact_unique_count": len(ack_ids) if ack_known else None,
            "acknowledged_identity_known_receipts": ack_known,
            "ready_confirmed_exact_unique_count": len(ready_ids) if ready_known else None,
            "ready_identity_known_receipts": ready_known,
            "latest_ready_status_counts": stage_report["ready_status_counts"],
        }
    return {
        "elapsed_seconds": observation("elapsed_seconds"),
        "source": source,
        "database": database,
        "enrichment": enrichment,
        "conversion": conversion,
        "ai_first_candidates": ai_first,
        "targets": targets,
        "identity_counts_are_exact_sets": True,
        "observations_include_retries": True,
    }


def _failure_point(receipt: dict[str, Any]) -> dict[str, str] | None:
    stages = receipt.get("stages", {})
    downloaded = stages.get("downloaded") or {}
    budget = downloaded.get("request_budget") or {}
    budget_pause = (
        downloaded.get("status") == "partial"
        and downloaded.get("error") is None
        and budget.get("paused") is True
    )
    budget_reason = None
    if budget_pause:
        remaining = budget.get("frontier_remaining")
        if remaining is None:
            remaining = "未记录"
        budget_reason = f"来源采集因请求预算暂停，剩余队列 {remaining} 项"
    for name in COUNT_STAGES:
        stage = stages.get(name)
        if not stage:
            continue
        if name == "downloaded" and budget_pause:
            continue
        status = stage["status"]
        if status in {"failed", "partial", "pending", "unknown"}:
            reason = stage.get("error")
            conversion = (receipt.get("telemetry") or {}).get("conversion", {})
            encrypted_pdf = (
                reason
                and "pdf" in reason.casefold()
                and any(token in reason.casefold() for token in ("encrypt", "password", "加密"))
            )
            if name in {"new_versions", "enriched"} and (
                conversion.get("failed_count", 0) or encrypted_pdf
            ):
                name = "conversion"
            elif name == "new_versions" and conversion.get("succeeded_count", 0):
                name = "enriched"
            reason = reason or "未记录具体原因"
            if budget_reason:
                reason = f"{reason}；{budget_reason}"
            return {"stage": name, "status": status, "reason": reason}
    for name in ACK_STAGES:
        stage = stages.get(name)
        if not stage:
            continue
        ai_count = (stages.get("ai_candidates") or {}).get("count") or 0
        if stage["status"] in {"failed", "partial", "pending", "unknown"}:
            reason = stage.get("error") or "未记录具体原因"
            if budget_reason:
                reason = f"{reason}；{budget_reason}"
            return {
                "stage": name,
                "status": stage["status"],
                "reason": reason,
            }
        if ai_count and stage["ready_status"] in {
            "failed",
            "partial",
            "pending",
            "unknown",
            "not_required",
        }:
            return {
                "stage": name.replace("_ack", "_ready"),
                "status": stage["ready_status"],
                "reason": (
                    stage.get("ready_error")
                    or (
                        "worker 未要求 Ready；未确认 native Ready"
                        if stage["ready_status"] == "not_required"
                        else "未记录具体原因"
                    )
                )
                + (f"；{budget_reason}" if budget_reason else ""),
            }
    if budget_pause:
        return {"stage": "downloaded", "status": "partial", "reason": budget_reason}
    return None


def _normalize_runtime_output(raw: Any, day: date, source: Path) -> dict[str, Any]:
    if (
        not isinstance(raw, dict)
        or isinstance(raw.get("schema_version"), bool)
        or raw.get("schema_version") != 1
        or raw.get("date_local") != day.isoformat()
    ):
        raise FlowError(f"{source}: runtime output date_local must match {day.isoformat()}")
    runs = raw.get("runs")
    if not isinstance(runs, list):
        raise FlowError(f"{source}: runtime output runs must be an array")
    normalized = []
    seen: set[str] = set()
    for row in runs:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("site_id"), str)
            or row["site_id"] not in SITES
        ):
            raise FlowError(f"{source}: runtime output contains an invalid site row")
        site = row["site_id"]
        if site in seen:
            raise FlowError(f"{source}: runtime output contains duplicate site {site!r}")
        seen.add(site)
        preview = row.get("preview", False)
        if not isinstance(preview, bool):
            raise FlowError(f"{source}: runtime output preview must be a boolean")
        run_elapsed = row.get("elapsed_seconds")
        if run_elapsed is not None and (
            isinstance(run_elapsed, bool)
            or not isinstance(run_elapsed, (int, float))
            or not math.isfinite(run_elapsed)
            or run_elapsed < 0
        ):
            raise FlowError(
                f"{source}: runtime output site elapsed_seconds must be finite and non-negative"
            )
        run_status = row.get("run_status")
        if not isinstance(run_status, str) or run_status not in RUN_STATUSES:
            run_status = None
        attempt_count = row.get("attempt_count")
        if (
            isinstance(attempt_count, bool)
            or not isinstance(attempt_count, int)
            or attempt_count < 1
        ):
            attempt_count = None
        receipt_id = row.get("receipt_id")
        if not isinstance(receipt_id, str) or not receipt_id:
            receipt_id = None
        normalized.append(
            {
                "site_id": site,
                "preview": preview,
                "error": row.get("error") if isinstance(row.get("error"), str) else None,
                "run_status": run_status,
                "elapsed_seconds": run_elapsed,
                "receipt_id": receipt_id,
                "attempt_count": attempt_count,
            }
        )
    elapsed = raw.get("elapsed_seconds")
    if elapsed is not None and (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not math.isfinite(elapsed)
        or elapsed < 0
    ):
        raise FlowError(f"{source}: runtime output elapsed_seconds must be finite and non-negative")
    preview = raw.get("preview", False)
    if not isinstance(preview, bool):
        raise FlowError(f"{source}: runtime output preview must be a boolean")
    return {"elapsed_seconds": elapsed, "preview": preview, "runs": normalized}


def make_report(
    day: date,
    receipts: dict[tuple[str, str], dict[str, Any]],
    ledger: dict[str, dict[str, Any]] | None = None,
    runtime_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ledger = ledger or {}
    status = make_status(day, receipts)
    actual = _date_receipts(receipts, day)
    collection = [actual[site] for site in SITES if site in actual and _action(site) == "collect"]
    runtime_runs = (runtime_output or {}).get("runs", [])
    runtime_attempt_sites = [row["site_id"] for row in runtime_runs if not row["preview"]]
    matched_runtime_sites = {
        row["site_id"]
        for row in runtime_runs
        if not row["preview"]
        and not row["error"]
        and row["site_id"] in actual
        and row.get("receipt_id") is not None
        and row.get("attempt_count") is not None
        and row.get("run_status") is not None
        and row.get("receipt_id") == actual.get(row["site_id"], {}).get("receipt_id")
        and row.get("attempt_count") == actual.get(row["site_id"], {}).get("attempt_count")
        and row.get("run_status") == actual.get(row["site_id"], {}).get("run_status")
    }
    missing_runtime_receipts = [
        site for site in runtime_attempt_sites if site not in matched_runtime_sites
    ]
    stages = {
        **{stage: _aggregate_count_stage(collection, stage) for stage in COUNT_STAGES},
        **{stage: _aggregate_ack_stage(collection, stage) for stage in ACK_STAGES},
    }
    active_cases = _active_failure_cases(receipts, day)
    case_updates = _failure_case_updates(active_cases, ledger, receipts, day)
    research_queue = _research_queue(active_cases, ledger, day)
    rows = status["rows"]
    window = [_window_day(day - timedelta(days=i), receipts) for i in reversed(range(7))]
    planned_unique = sorted({site for item in window for site in item["planned_sites"]})
    actual_unique = sorted({site for item in window for site in item["attempted_sites"]})
    collection_actual_unique = sorted(
        {site for item in window for site in item["collection_attempted_sites"]}
    )
    telemetry_report = _aggregate_telemetry(collection)
    telemetry_report["elapsed_seconds"] = _aggregate_telemetry(list(actual.values()))[
        "elapsed_seconds"
    ]
    return {
        "schema_version": 2,
        "mode": "offline_daily_report",
        "date_local": day.isoformat(),
        "timezone": "America/New_York",
        "generated_for_local_time": "09:00",
        "site_statuses": rows,
        "daily_status_counts": _counter_rows(rows),
        "plan": status["plan"],
        "coverage": {
            "planned_baseline_sites": status["plan"]["baseline_sites"],
            "planned_extra_retry_sites": status["plan"]["extra_retry_sites"],
            "planned_sites": status["plan"]["baseline_sites"] + status["plan"]["extra_retry_sites"],
            "actual_receipt_sites": [site for site in SITES if site in actual],
            "actual_collection_receipt_sites": [
                site for site in SITES if site in actual and _action(site) == "collect"
            ],
            "actual_monitor_receipt_sites": [
                site for site in SITES if site in actual and _action(site) == "monitor_only"
            ],
            "runtime_attempt_sites": runtime_attempt_sites if runtime_output is not None else None,
            "runtime_attempts_with_receipts": (
                [site for site in runtime_attempt_sites if site in matched_runtime_sites]
                if runtime_output is not None
                else None
            ),
            "runtime_attempts_without_receipts": (
                missing_runtime_receipts if runtime_output is not None else None
            ),
            "planned_sites_not_attempted": [
                site
                for site in status["plan"]["baseline_sites"] + status["plan"]["extra_retry_sites"]
                if runtime_output is not None and site not in runtime_attempt_sites
            ],
            "planned_unique_sites_7d": planned_unique,
            "planned_unique_count_7d": len(planned_unique),
            "actual_unique_sites_7d": actual_unique,
            "actual_unique_count_7d": len(actual_unique),
            "actual_collection_unique_sites_7d": collection_actual_unique,
            "actual_collection_unique_count_7d": len(collection_actual_unique),
            "seven_day_scheduled_coverage_complete": len(planned_unique) == len(SITES),
            "seven_day_actual_coverage_complete": len(actual_unique)
            == len(SITES) - len(HELD_SITES),
            "actual_coverage_excludes_hold_sites": True,
            "seven_day_actual_collection_coverage_complete": len(collection_actual_unique)
            == len(SITES) - len(MONITOR_ONLY_SITES) - len(HELD_SITES),
            "missing_receipt_is_not_source_failure": True,
            "budget_exceptions": status["budget_exceptions"],
        },
        "seven_day_window": window,
        "monitoring_only": {
            "planned_sites": [
                site for site in status["plan"]["baseline_sites"] if site in MONITOR_ONLY_SITES
            ],
            "actual_receipt_sites": [
                site for site in SITES if site in actual and site in MONITOR_ONLY_SITES
            ],
            "planned_is_not_success": True,
        },
        "stages": stages,
        "telemetry": telemetry_report,
        "failure_cases": list(active_cases.values()),
        "case_updates": case_updates,
        "research_queue": research_queue,
        "suggested_research": research_queue[:2],
        "research_queue_deferred_count": max(0, len(research_queue) - 2),
        "case_ledger_contract": {
            "schema_version": 1,
            "empty_json": {"schema_version": 1, "cases": []},
            "helper_writes_ledger": False,
        },
        "receipts": [
            {
                "receipt_id": r["receipt_id"],
                "date_local": r["date_local"],
                "site_id": r["site_id"],
                "action": _action(r["site_id"]),
                "run_status": r["run_status"],
                "effective_status": _effective_status(r)[0],
                "attempt_count": r["attempt_count"],
                "reason": r["reason"],
                "evidence": r["evidence"],
                "stages": r["stages"],
                "failure_point": _failure_point(r),
                **({"telemetry": r["telemetry"]} if "telemetry" in r else {}),
                **(
                    {
                        "pending_article_count": (
                            r["stages"].get("enriched") or r["stages"].get("new_versions") or {}
                        ).get("pending_count")
                    }
                    if (r["stages"].get("enriched") or r["stages"].get("new_versions") or {}).get(
                        "pending_count"
                    )
                    is not None
                    else {}
                ),
                **(
                    {"request_budget": r["stages"]["downloaded"]["request_budget"]}
                    if r["stages"].get("downloaded", {}).get("request_budget") is not None
                    else {}
                ),
            }
            for r in sorted(actual.values(), key=lambda r: r["site_id"])
        ],
        "executes_collection": False,
        "writes_hub_or_servers": False,
        "writes_case_ledger": False,
        "performs_research": False,
        **(
            {
                "runtime_evidence": {
                    "elapsed_seconds": runtime_output["elapsed_seconds"],
                    "preview": runtime_output["preview"],
                    "runs": runtime_runs,
                    "missing_receipt_sites": missing_runtime_receipts,
                }
            }
            if runtime_output is not None
            else {}
        ),
    }


def parse_day(value: str) -> date:
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise FlowError(f"date must use YYYY-MM-DD: {value!r}") from exc
    if result.isoformat() != value:
        raise FlowError(f"date must use YYYY-MM-DD: {value!r}")
    return result


def _text(language: str, chinese: str, english: str) -> str:
    return english if language == "en" else chinese


def _count_text(value: int, unit: str, language: str, english_unit: str | None = None) -> str:
    if language == "zh":
        return f"{value}{unit}"
    label = english_unit or {
        "次": "times",
        "份": "files",
        "条": "items",
        "篇": "articles",
        "": "",
    }.get(unit, unit)
    if value == 1 and label.endswith("s"):
        label = label[:-1]
    return f"{value} {label}" if label else str(value)


def _metric_value(metric: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = metric.get(key)
        if value is not None:
            return value
    return None


def _scoped_metric_text(
    report: dict[str, Any],
    metric: dict[str, Any],
    *,
    unit: str = "次",
    english_unit: str | None = None,
    language: str = "zh",
) -> str:
    value = _metric_value(metric, "observation_sum", "run_observation_sum")
    if value is None:
        return _text(language, "未记录", "not recorded")
    rendered_value = _count_text(value, unit, language, english_unit)
    total = len(report["coverage"]["actual_collection_receipt_sites"])
    known = metric.get("known_receipts", total)
    if known < total:
        return _text(
            language,
            f"已有{known}/{total}项回执记录，合计{value}{unit}",
            f"{rendered_value} recorded in {known}/{total} receipts",
        )
    return rendered_value


def _scoped_unique_text(
    report: dict[str, Any],
    metric: dict[str, Any],
    *,
    unit: str,
    language: str = "zh",
) -> str:
    value = metric.get("exact_unique_count")
    if value is None:
        return _text(language, "未记录", "not recorded")
    rendered_value = _count_text(value, unit, language)
    total = len(report["coverage"]["actual_collection_receipt_sites"])
    known = metric.get("known_receipts", total)
    if known < total:
        return _text(
            language,
            f"身份信息已知{known}/{total}项回执，至少{value}{unit}",
            f"at least {rendered_value}; identities known in {known}/{total} receipts",
        )
    return rendered_value


def _stage_metric_text(
    report: dict[str, Any], stage: str, *, unit: str = "份", language: str = "zh"
) -> str:
    return _scoped_metric_text(report, report["stages"][stage], unit=unit, language=language)


def _receipt_request_count(receipt: dict[str, Any]) -> int | None:
    source = (receipt.get("telemetry") or {}).get("source") or {}
    if source.get("request_count") is not None:
        return source["request_count"]
    budget = (receipt.get("stages", {}).get("downloaded") or {}).get("request_budget")
    if receipt.get("attempt_count") == 1 and budget:
        return budget.get("used")
    return None


def _daily_request_count(report: dict[str, Any]) -> tuple[int | None, str]:
    receipts = [row for row in report["receipts"] if row["action"] == "collect"]
    metric = report["telemetry"]["source"]["request_count"]
    if metric.get("known_receipts") == len(receipts) and receipts:
        return metric.get("observation_sum"), "遥测"
    if receipts and all(
        row.get("attempt_count") == 1
        and (row.get("stages", {}).get("downloaded") or {}).get("request_budget")
        for row in receipts
    ):
        return sum(_receipt_request_count(row) or 0 for row in receipts), "单次回执预算"
    return None, ""


def _receipt_scope(report: dict[str, Any], language: str = "zh") -> str:
    collection_count = len(report["coverage"]["actual_collection_receipt_sites"])
    runtime = report.get("runtime_evidence")
    if runtime is not None and not runtime["preview"]:
        collect_runs = [row for row in runtime["runs"] if _action(row["site_id"]) == "collect"]
        run_sites = {row["site_id"] for row in collect_runs}
        matched_sites = set(report["coverage"].get("runtime_attempts_with_receipts") or [])
        matched_count = len(run_sites & matched_sites)
        unmatched_dated = len(
            run_sites & set(report["coverage"]["actual_collection_receipt_sites"]) - matched_sites
        )
        run_count = len(run_sites)
        if unmatched_dated:
            return _text(
                language,
                f"{collection_count}站日期回执（{matched_count}/{run_count}项对应本次运行，"
                f"{unmatched_dated}项仅作历史记录）",
                f"{collection_count} dated site receipts ({matched_count}/{run_count} matched "
                f"this run; {unmatched_dated} historical only)",
            )
        if run_count > collection_count or matched_count < run_count:
            return _text(
                language,
                f"已有{matched_count}/{run_count}站回执",
                f"receipts for {matched_count}/{run_count} sites",
            )
    return _text(language, f"{collection_count}站回执", f"{collection_count} site receipts")


def _escape_cell(value: Any) -> str:
    return " ".join(str(value).replace("|", "\\|").split())


def _short_failure_reason(reason: Any, stage: str, language: str = "zh") -> str:
    """Keep the summary readable while leaving the source receipt untouched."""
    raw = " ".join(
        str(reason or _text(language, "未记录具体原因", "No specific reason recorded")).split()
    )
    lowered = raw.casefold()
    budget_pause = any(
        token in lowered
        for token in (
            "request budget",
            "budget reached",
            "request limit",
            "请求预算",
            "来源采集因请求预算暂停",
        )
    )
    budget_note = _text(language, "请求预算暂停", "Request budget paused")
    if budget_pause:
        remaining = None
        for token in ("frontier_remaining=", "frontier remaining ", "剩余队列 "):
            if token in lowered:
                tail = lowered.split(token, 1)[1]
                digits = "".join(char for char in tail if char.isdigit())
                if digits:
                    remaining = digits
                    break
        budget_note += (
            _text(
                language,
                f"（剩余队列 {remaining} 项）",
                f" ({remaining} queued)",
            )
            if remaining is not None
            else ""
        )
    details = []
    if "redirect left the approved source host" in lowered:
        details.append(
            _text(
                language,
                "文档重定向离开允许来源",
                "Document redirected outside the approved source host",
            )
        )
    if "download exceeded size limit" in lowered or "streamed digest check" in lowered:
        details.append(
            _text(
                language,
                "下载超出大小限制或摘要校验失败",
                "Download exceeded the size limit or failed digest verification",
            )
        )
    if (
        stage == "downloaded"
        and "404" in lowered
        and any(token in lowered for token in ("http", "status_code", "status="))
    ):
        details.append(_text(language, "HTTP 404：链接不存在", "HTTP 404: link not found"))
    if (
        stage == "downloaded"
        and "400" in lowered
        and any(token in lowered for token in ("http", "status_code", "status="))
    ):
        details.append(
            _text(language, "HTTP 400：链接格式或请求错误", "HTTP 400: malformed link or request")
        )
    if "pdf" in lowered and any(token in lowered for token in ("encrypt", "password", "加密")):
        details.append(_text(language, "加密 PDF 无法转换", "Encrypted PDF could not be converted"))
    target_stage = stage in ACK_STAGES or stage.endswith("_ready")
    if target_stage and any(token in lowered for token in ("capacity", "80%", "容量门槛")):
        percentage = re.search(r"(\d+(?:\.\d+)?)\s*%\s+used\b", raw, re.IGNORECASE)
        used = f"（已用{percentage.group(1)}%）" if percentage else ""
        details.append(
            _text(
                language,
                f"目标容量门槛{used}，发布未继续",
                f"Target capacity gate{f' ({percentage.group(1)}% used)' if percentage else ''}; publishing did not proceed",
            )
        )
    if (
        target_stage
        and "ssh" in lowered
        and any(token in lowered for token in ("timeout", "timed out"))
    ):
        details.append(_text(language, "SSH 连接超时", "SSH connection timed out"))
    if target_stage and "target worker failed" in lowered and "no json result" in lowered:
        details.append(_text(language, "目标端未返回有效回执", "Target returned no valid receipt"))
    if "bounded source discovery produced no verified article or document candidates" in lowered:
        details.append(
            _text(
                language,
                "未发现可验证文章或文档链接",
                "No verifiable article or document links found",
            )
        )
    if "ready_status must be one of" in lowered:
        details.append(
            _text(
                language,
                "回执可搜索状态值不兼容",
                "Incompatible searchable-status value in receipt",
            )
        )
    if details:
        separator = _text(language, "；", "; ")
        return separator.join(dict.fromkeys(details + ([budget_note] if budget_pause else [])))
    if budget_pause and (";" not in raw or raw.casefold().startswith("request budget")):
        return budget_note
    if len(raw) > 120:
        raw = raw[:117].rstrip() + "..."
    raw_evidence = _text(language, raw, f"Raw source evidence: {raw}")
    return (
        f"{raw_evidence}{_text(language, '；', '; ')}{budget_note}"
        if budget_pause
        else raw_evidence
    )


def _monitor_result_text(receipt: dict[str, Any], language: str = "zh") -> str:
    status = receipt["effective_status"]
    if status == "succeeded":
        return _text(language, "检查成功", "Check succeeded")
    monitor = receipt.get("stages", {}).get("monitor") or {}
    reason = monitor.get("error") or receipt.get("reason")
    result = _text(
        language,
        f"检查{_status_label(status, language)}",
        f"Check {_status_label(status, language)}",
    )
    return (
        f"{result}{_text(language, '：', ': ')}{_short_failure_reason(reason, 'monitor', language)}"
        if reason
        else result
    )


def _executive_count(receipts: list[dict[str, Any]], stage: str, language: str = "zh") -> str:
    values = [(receipt.get("stages", {}).get(stage) or {}).get("count") for receipt in receipts]
    known = [value for value in values if value is not None]
    if not known:
        return _text(language, "未记录", "not recorded")
    total = sum(known)
    return (
        str(total)
        if len(known) == len(receipts)
        else _text(
            language,
            f"{total}（{len(known)}/{len(receipts)}项回执有记录）",
            f"{total} ({len(known)}/{len(receipts)} receipts recorded)",
        )
    )


def _executive_telemetry(receipts: list[dict[str, Any]], *path: str, language: str = "zh") -> str:
    values = []
    for receipt in receipts:
        value: Any = receipt.get("telemetry") or {}
        for key in path:
            value = value.get(key) if isinstance(value, dict) else None
        values.append(value)
    known = [value for value in values if isinstance(value, (int, float))]
    if not known:
        return _text(language, "未记录", "not recorded")
    total = sum(known)
    return (
        str(total)
        if len(known) == len(receipts)
        else _text(
            language,
            f"{total}（{len(known)}/{len(receipts)}项回执有记录）",
            f"{total} ({len(known)}/{len(receipts)} receipts recorded)",
        )
    )


def _executive_summary(report: dict[str, Any], language: str = "zh") -> list[str]:
    """Summarize only exact current-run collection evidence and visible blockers."""
    coverage = report["coverage"]
    runtime = report.get("runtime_evidence")
    receipt_by_site = {row["site_id"]: row for row in report["receipts"]}
    matched_sites = set(coverage.get("runtime_attempts_with_receipts") or [])
    matched = [
        receipt_by_site[site]
        for site in coverage["actual_collection_receipt_sites"]
        if site in matched_sites and site in receipt_by_site
    ]
    date_receipts = [
        receipt_by_site[site]
        for site in coverage["actual_collection_receipt_sites"]
        if site in receipt_by_site
    ]
    summary_receipts = date_receipts if runtime is None else matched
    run_rows = []
    if runtime is not None and not runtime["preview"]:
        run_rows = [
            row
            for row in runtime["runs"]
            if not row["preview"] and _action(row["site_id"]) == "collect"
        ]
    run_sites = {row["site_id"] for row in run_rows}
    missing_sites = run_sites - matched_sites
    planned_not_run = {
        site
        for site in coverage.get("planned_sites_not_attempted") or []
        if _action(site) == "collect"
    }
    status_counts = Counter(row["effective_status"] for row in summary_receipts)
    useful = any(
        (receipt.get("stages", {}).get(stage) or {}).get("count", 0) > 0
        for receipt in summary_receipts
        for stage in ("downloaded", "new_versions", "duplicates", "enriched")
        if isinstance((receipt.get("stages", {}).get(stage) or {}).get("count"), (int, float))
    )
    if runtime is None:
        overall = (
            _text(
                language,
                f"有{len(date_receipts)}站日期回执可参考，但本次运行覆盖未知",
                f"Dated receipts are available for {len(date_receipts)} sites; current run coverage is unknown",
            )
            if date_receipts
            else _text(
                language,
                "没有日期回执或运行清单，执行情况未知",
                "No dated receipts or run manifest; execution status is unknown",
            )
        )
    elif runtime["preview"]:
        overall = _text(
            language,
            "仅有预览清单，不能据此确认本次来源采集成功",
            "Preview manifest only; it cannot confirm collection success for this run",
        )
    elif not run_rows:
        overall = _text(
            language,
            "本次运行清单没有来源采集项",
            "No collection sites appear in this run manifest",
        )
    elif missing_sites:
        overall = _text(
            language,
            "有产出但未全部完成" if useful else "本次回执不完整，执行结果未能完整核验",
            (
                "Some output was collected, but the run is incomplete"
                if useful
                else "Receipts are incomplete; the run could not be fully verified"
            ),
        )
    elif planned_not_run or status_counts.get("partial") or status_counts.get("failed"):
        overall = _text(
            language,
            "有产出但未全部完成" if useful else "本次未全部完成",
            (
                "Some output was collected, but the run is incomplete"
                if useful
                else "This run did not complete all planned work"
            ),
        )
    elif len(matched) == len(run_rows) and status_counts.get("succeeded") == len(matched):
        overall = _text(
            language, "本次对应回执显示来源采集完成", "Matched receipts show collection completed"
        )
    else:
        overall = _text(
            language, "本次执行结果未能完整核验", "This run could not be fully verified"
        )

    downloaded = _executive_count(summary_receipts, "downloaded", language)
    new_versions = _executive_count(summary_receipts, "new_versions", language)
    duplicates = _executive_count(summary_receipts, "duplicates", language)
    enriched = _executive_count(summary_receipts, "enriched", language)
    ai_first = _executive_telemetry(summary_receipts, "ai_first_candidate_count", language=language)
    converted = _executive_telemetry(
        summary_receipts, "conversion", "succeeded_count", language=language
    )
    conversion_failed = _executive_telemetry(
        summary_receipts, "conversion", "failed_count", language=language
    )
    useful_output = _text(
        language,
        f"下载{downloaded}份；新增入库{new_versions}、复用{duplicates}、摘要分类{enriched}；"
        f"AI首类候选{ai_first}；正文转换成功{converted}、失败{conversion_failed}",
        f"Downloaded {downloaded} files; {new_versions} added to the local database, "
        f"{duplicates} reused, {enriched} classified; AI-first candidates {ai_first}; body conversion "
        f"succeeded {converted}, failed {conversion_failed}",
    )
    if not summary_receipts:
        useful_output = _text(
            language,
            "没有可用采集回执；下载、新增入库、复用、摘要分类和转换数量未记录",
            "No collection receipts available; download, new, reused, classified, and conversion counts are not recorded",
        )

    issue_groups: dict[str, list[str]] = {
        "source": [],
        "conversion": [],
        "china": [],
        "overseas": [],
        "other": [],
        "runtime": [],
    }

    def add_issue(group: str, issue: str) -> None:
        if issue not in issue_groups[group]:
            issue_groups[group].append(issue)

    budget_only = 0
    for receipt in summary_receipts:
        site = _site_label(receipt["site_id"], language)
        if _budget_pause_only(receipt):
            budget_only += 1
        primary_failure = receipt.get("failure_point") or {}
        primary_reason = primary_failure.get("reason") or ""
        conversion_issue_added = False
        for failure in _stage_failures(receipt):
            stage = failure["stage"]
            raw_error = failure["error"]
            if primary_failure.get("stage") == "conversion" and stage in {
                "new_versions",
                "enriched",
                "ai_candidates",
            }:
                error_base = raw_error.casefold().split(";", 1)[0].split("；", 1)[0].strip()
                primary_base = primary_reason.casefold().split(";", 1)[0].split("；", 1)[0].strip()
                if (
                    error_base == primary_base
                    or error_base in primary_base
                    or primary_base in error_base
                ):
                    stage = "conversion"
                    raw_error = primary_reason
                    conversion_issue_added = True
            reason = _short_failure_reason(raw_error, stage, language)
            if (
                (receipt.get("stages", {}).get("downloaded") or {})
                .get("request_budget", {})
                .get("paused")
                and not _budget_pause_only(receipt)
                and _text(language, "请求预算暂停", "Request budget paused") not in reason
            ):
                reason += _text(language, "；兼有预算暂停", "; request budget also paused")
            issue = _text(
                language,
                f"{site}·{_stage_label(stage, language)}：{reason}",
                f"{site} · {_stage_label(stage, language)}: {reason}",
            )
            group = (
                "source"
                if stage == "downloaded"
                else (
                    "china"
                    if stage.startswith("china_")
                    else (
                        "overseas"
                        if stage.startswith("overseas_")
                        else "conversion" if stage == "conversion" else "other"
                    )
                )
            )
            add_issue(group, issue)
        telemetry = receipt.get("telemetry") or {}
        conversion_failed = (telemetry.get("conversion") or {}).get("failed_count")
        if (
            isinstance(conversion_failed, int)
            and conversion_failed > 0
            and not conversion_issue_added
        ):
            issue = _text(
                language,
                f"{site}·正文转换（Markdown）：失败{conversion_failed}份",
                f"{site} · Body conversion (Markdown): {_count_text(conversion_failed, '份', language)} failed",
            )
            add_issue("conversion", issue)
        ai_count = telemetry.get("ai_first_candidate_count")
        ai_ids = telemetry.get("ai_first_candidate_ids")
        if ai_count is None and isinstance(ai_ids, list):
            ai_count = len(ai_ids)
        if ai_count != 0:
            for target, label in (
                ("china", _text(language, "国内", "China")),
                ("overseas", _text(language, "海外", "Overseas")),
            ):
                stage = receipt.get("stages", {}).get(f"{target}_ack")
                if stage is None and ai_count is None:
                    continue
                stage = stage or {}
                ready_status = stage.get("ready_status", "unknown")
                if ready_status in {"failed", "partial", "pending", "not_required"} or (
                    ai_count is not None and ready_status == "unknown"
                ):
                    qualifier = _text(
                        language,
                        "有 AI 首类候选，" if isinstance(ai_count, int) and ai_count > 0 else "",
                        (
                            "AI-first candidates exist; "
                            if isinstance(ai_count, int) and ai_count > 0
                            else ""
                        ),
                    )
                    issue = _text(
                        language,
                        f"{site}·{label}可搜索确认：{qualifier}回执状态{_ready_label(ready_status, language)}",
                        f"{site} · {label} search confirmation: {qualifier}receipt status "
                        f"{_ready_label(ready_status, language)}",
                    )
                    add_issue(target, issue)

    if runtime is not None and not runtime["preview"]:
        missing_details = []
        contract_failure_sites = []
        for row in run_rows:
            site = row["site_id"]
            if site not in missing_sites:
                continue
            reason = row.get("error")
            label = _site_label(site, language)
            if reason:
                short_reason = _short_failure_reason(reason, "run", language)
                if "ready_status must be one of" in reason.casefold():
                    contract_failure_sites.append(label)
                else:
                    missing_details.append(
                        _text(
                            language,
                            f"{label}：运行报错（{short_reason}）",
                            f"{label}: run error ({short_reason})",
                        )
                    )
            else:
                history_note = _text(
                    language,
                    "（同日回执仅作历史记录）" if site in receipt_by_site else "",
                    " (same-day receipt is historical only)" if site in receipt_by_site else "",
                )
                missing_details.append(
                    _text(
                        language,
                        f"{label}：本次回执缺失或无法关联{history_note}",
                        f"{label}: current receipt is missing or unmatched{history_note}",
                    )
                )
        if missing_sites:
            if contract_failure_sites:
                missing_details.append(
                    _text(
                        language,
                        f"已运行但回执保存失败（状态值不兼容）：{'、'.join(contract_failure_sites)}",
                        f"Ran, but receipt save failed (incompatible status value): {', '.join(contract_failure_sites)}",
                    )
                )
            add_issue(
                "runtime",
                _text(
                    language,
                    f"本次运行{len(missing_sites)}站回执缺口（{'；'.join(missing_details[:3])}）",
                    f"Current run missing receipts for {_count_text(len(missing_sites), '', language, 'sites')} ({'; '.join(missing_details[:3])})",
                ),
            )
    if planned_not_run:
        names = _text(language, "、", ", ").join(
            _site_label(site, language) for site in sorted(planned_not_run, key=SITES.index)[:3]
        )
        suffix = (
            _text(language, f"等{len(planned_not_run)}站", f" and {len(planned_not_run) - 3} more")
            if len(planned_not_run) > 3
            else ""
        )
        add_issue(
            "runtime",
            _text(
                language,
                f"计划内未见运行：{names}{suffix}",
                f"Planned sites not seen running: {names}{suffix}",
            ),
        )

    issues: list[str] = []
    for group, limit in (
        ("source", 1),
        ("conversion", 1),
        ("china", 1),
        ("overseas", 1),
        ("other", 1),
        ("runtime", 1),
    ):
        issues.extend(issue_groups[group][:limit])
    omitted_count = sum(len(values) for values in issue_groups.values()) - len(issues)

    if not issues and budget_only:
        blockers = _text(
            language,
            f"纯请求预算暂停{budget_only}站；未见其他已记录故障",
            f"Request budget paused for {budget_only} sites; no other recorded failures",
        )
    elif issues:
        stage_names = (
            {
                "来源读取/收集": "来源",
                "AI 补全/分类": "分类",
                "AI 首类筛选": "AI首类",
                "本地库新增": "本地库新增",
                "本地库去重": "本地库去重",
                "正文转换（Markdown）": "正文转换",
                "国内入库确认": "国内入库",
                "国内可搜索确认": "国内可搜索",
                "海外入库确认": "海外入库",
                "海外可搜索确认": "海外可搜索",
            }
            if language == "zh"
            else {
                "Source read/collection": "Source",
                "AI enrichment/classification": "Classification",
                "AI-first filter": "AI-first",
                "Local database additions": "Database additions",
                "Local database deduplication": "Deduplication",
                "Body conversion (Markdown)": "Conversion",
                "China ingestion confirmation": "China ingestion",
                "China searchable confirmation": "China searchability",
                "Overseas ingestion confirmation": "Overseas ingestion",
                "Overseas searchable confirmation": "Overseas searchability",
            }
        )
        compact_issues = []
        for issue in issues:
            separator, colon = _text(language, "·", " · "), _text(language, "：", ": ")
            if separator in issue and colon in issue:
                site, detail = issue.split(separator, 1)
                stage, reason = detail.split(colon, 1)
                compact_issues.append(
                    _text(
                        language,
                        f"{site}{stage_names.get(stage, stage)}：{reason}",
                        f"{site} — {stage_names.get(stage, stage)}: {reason}",
                    )
                )
            else:
                compact_issues.append(issue)
        blockers = _text(language, "；", "; ").join(compact_issues)
        if omitted_count:
            blockers += _text(
                language,
                f"；另有{omitted_count}项详见逐站结果和 JSON",
                f"; {omitted_count} more in site details and JSON",
            )
        if budget_only:
            blockers += _text(
                language,
                f"；另有{budget_only}站为纯预算暂停",
                f"; budget-only pauses at {budget_only} more sites",
            )
    else:
        blockers = _text(
            language,
            "未见已记录的阻塞；未记录字段仍属未知",
            "No recorded blockers; unrecorded fields remain unknown",
        )

    recommendations = []
    if runtime is None:
        recommendations.append(
            _text(
                language,
                "补看实际运行清单，确认日期回执对应的运行覆盖",
                "Check the actual run manifest to establish receipt coverage",
            )
        )
    elif runtime["preview"]:
        recommendations.append(
            _text(
                language,
                "取得实际运行记录后再判断本次覆盖",
                "Use an actual run record to assess this run's coverage",
            )
        )
    else:
        if missing_sites:
            recommendations.append(
                _text(
                    language,
                    "先核对本次运行回执缺口，避免把旧回执当成本次结果",
                    "Check missing receipts for this run; do not treat old receipts as current",
                )
            )
        if planned_not_run:
            recommendations.append(
                _text(
                    language,
                    "确认计划内未见运行的站点是否应按计划执行",
                    "Confirm whether planned sites not seen running should have run",
                )
            )
    if issue_groups["source"] or issue_groups["conversion"] or issue_groups["other"]:
        recommendations.append(
            _text(
                language,
                "复核来源、转换或处理错误，再按原有单站流程重试",
                "Review source, conversion, or processing errors, then retry through the existing per-site flow",
            )
        )
    target_groups = [name for name in ("china", "overseas") if issue_groups[name]]
    if target_groups:
        target_names = _text(language, "和", " and ").join(
            (
                _text(language, "国内", "China")
                if name == "china"
                else _text(language, "海外", "overseas")
            )
            for name in target_groups
        )
        recommendations.append(
            _text(
                language,
                f"核实{target_names}入库回执、可搜索状态及容量门槛，再按原有流程处理",
                f"Check {target_names} ingestion receipts, searchable status, and capacity gate; follow existing procedures",
            )
        )
    budget_wording = _text(language, "请求预算暂停", "request budget")
    if budget_only or any(budget_wording.casefold() in issue.casefold() for issue in issues):
        caps = {
            (receipt.get("stages", {}).get("downloaded") or {}).get("request_budget", {}).get("cap")
            for receipt in summary_receipts
            if (receipt.get("stages", {}).get("downloaded") or {})
            .get("request_budget", {})
            .get("paused")
        }
        if caps == {30}:
            recommendations.append(
                _text(
                    language,
                    "30次访问预算用完，下次继续",
                    "The 30-request budget is exhausted; continue next time",
                )
            )
        else:
            recommendations.append(
                _text(
                    language,
                    "预算暂停按已有游标续采，维持当前请求上限",
                    "Resume from the saved cursor next time and keep the current request limit",
                )
            )
    if not recommendations:
        recommendations.append(
            _text(
                language,
                "按原计划观察，缺失指标继续保留为未记录",
                "Continue monitoring under the current plan; leave missing metrics unrecorded",
            )
        )
    advice = _text(language, "；", "; ").join(recommendations)
    outcome_counts = (
        _text(
            language,
            f"；{'匹配回执' if runtime is not None and not runtime['preview'] else '日期回执'}状态："
            f"完成{status_counts.get('succeeded', 0)}、部分{status_counts.get('partial', 0)}、"
            f"失败{status_counts.get('failed', 0)}",
            f"; {'matched receipt' if runtime is not None and not runtime['preview'] else 'dated receipt'} status: "
            f"{status_counts.get('succeeded', 0)} complete, {status_counts.get('partial', 0)} partial, "
            f"{status_counts.get('failed', 0)} failed",
        )
        if summary_receipts
        else _text(language, "；暂无可统计回执状态", "; no receipt statuses available")
    )
    if runtime is None:
        coverage_note = _text(
            language,
            f"{len(date_receipts)}站日期回执；本次运行关联未知",
            f"{len(date_receipts)} dated site receipts; current run linkage is unknown",
        )
        output_scope = _text(
            language,
            "按日期回执合计，未确认运行覆盖",
            "Totals use dated receipts; run coverage not confirmed",
        )
    elif runtime["preview"]:
        coverage_note = _text(
            language,
            "仅有预览清单，不计日期回执",
            "Preview manifest only; no dated receipts counted",
        )
        output_scope = _text(
            language, "预览不构成本次成功证据", "Preview is not evidence of success for this run"
        )
    else:
        coverage_note = _text(
            language,
            f"本次运行回执覆盖{len(matched)}/{len(run_rows)}项",
            f"Current run receipts cover {len(matched)}/{len(run_rows)} collection sites",
        )
        output_scope = _text(language, "仅计本次匹配回执", "Current matched receipts only")
    summary = [
        _text(
            language,
            f"- 结论：{overall}（{coverage_note}{outcome_counts}）。",
            f"- Outcome: {overall} ({coverage_note}{outcome_counts}).",
        ),
        _text(
            language,
            f"- 可见产出：{useful_output}（{output_scope}）。",
            f"- Visible output: {useful_output} ({output_scope}).",
        ),
        _text(
            language,
            f"- 阻塞与暂停：{blockers}。监控项另列、不计入来源采集；保留项不执行。",
            f"- Blockers and pauses: {blockers}. Monitoring items are listed separately and excluded from collection; held items are not run.",
        ),
        _text(
            language,
            f"- 建议：{advice}。建议为后续检查，不代表已执行或改变预算、索引、发布规则。",
            f"- Recommendations: {advice}. These are follow-up checks only; no budget, index, or publishing-rule changes were made.",
        ),
    ]
    return summary


def render_markdown(report: dict[str, Any], language: str = "zh") -> str:
    """Render a localized summary and per-site progress table."""
    if language not in {"zh", "en"}:
        raise ValueError("language must be 'zh' or 'en'")
    plan = report["plan"]
    coverage = report["coverage"]
    telemetry = report["telemetry"]
    receipt_by_site = {row["site_id"]: row for row in report["receipts"]}
    baseline = plan["baseline_sites"]
    retries = plan["extra_retry_sites"]
    actual = coverage["actual_receipt_sites"]
    collection_receipts = coverage["actual_collection_receipt_sites"]
    runtime = report.get("runtime_evidence")
    matched_runtime_sites = set(coverage.get("runtime_attempts_with_receipts") or [])
    if runtime is not None and not runtime["preview"]:
        run_count = len(coverage["runtime_attempt_sites"])
        matched_count = len(matched_runtime_sites)
        historical_count = len(
            matched_runtime_sites.symmetric_difference(set(coverage["runtime_attempt_sites"]))
            & set(actual)
        )
        actual_text = _text(
            language,
            f"实际运行{run_count}项；对应本次回执{matched_count}项",
            f"Ran {run_count} sites; {matched_count} matched current receipts",
        )
        if historical_count:
            actual_text += _text(
                language,
                f"；同日另有{historical_count}项历史回执",
                f"; {_count_text(historical_count, '', language, 'additional same-day historical receipts')}",
            )
    else:
        actual_text = _text(
            language, f"收到回执{len(actual)}项", f"{len(actual)} receipts received"
        )
    lines = [
        _text(
            language,
            f"# 精算资料每日简报（{report['date_local']}）",
            f"# Actuarial research daily report ({report['date_local']})",
        ),
        "",
        _text(language, "## 执行摘要", "## Executive summary"),
        "",
        *_executive_summary(report, language),
        "",
        _text(language, "| 项目 | 当日结果 |", "| Item | Result for the day |"),
        "| --- | --- |",
        _text(
            language,
            f"| 计划与实际 | 计划 {len(baseline)} 项常规 + {len(retries)} 项重试；{actual_text} |",
            f"| Plan and actual | {len(baseline)} routine + {len(retries)} retry sites planned; {actual_text} |",
        ),
    ]
    receipt_sites = set(coverage["actual_collection_receipt_sites"])
    if runtime is None:
        coverage_text = _text(
            language,
            f"来源与处理数据只合计已有 {len(receipt_sites)} 站回执；没有运行清单时无法判断是否还有缺失回执",
            f"Collection and processing totals include {len(receipt_sites)} dated site receipts; without a run manifest, missing receipts cannot be determined",
        )
    elif runtime["preview"]:
        coverage_text = _text(
            language,
            f"运行清单为预览；来源与处理数据只合计已有 {len(receipt_sites)} 站回执，不能据预览判断实际运行覆盖",
            f"Run manifest is a preview; collection and processing totals include {len(receipt_sites)} dated site receipts, and preview cannot establish actual run coverage",
        )
    else:
        collection_runs = [row for row in runtime["runs"] if _action(row["site_id"]) == "collect"]
        run_sites = {row["site_id"] for row in collection_runs}
        covered_count = len(run_sites & matched_runtime_sites)
        missing_count = len(run_sites - matched_runtime_sites)
        historical_count = len(run_sites & receipt_sites - matched_runtime_sites)
        coverage_text = (
            _text(
                language,
                f"有运行证据 {len(run_sites)} 项，其中 {covered_count} 项有本次回执、{missing_count} 项缺回执",
                f"Run evidence covers {_count_text(len(run_sites), '', language, 'collection sites')}: "
                f"current receipts {_count_text(covered_count, '', language, 'sites')}; "
                f"missing receipts {_count_text(missing_count, '', language, 'sites')}",
            )
            + (
                _text(
                    language,
                    f"、{historical_count} 项仅有同日历史回执；",
                    f"; same-day historical receipts only: {_count_text(historical_count, '', language, 'sites')}; ",
                )
                if historical_count
                else _text(language, "；", "; ")
            )
            + _text(
                language,
                f"下方来源和处理数字为{_receipt_scope(report, language)}合计",
                f"totals below cover {_receipt_scope(report, language)}",
            )
        )
    lines.append(
        _text(
            language, f"| 回执覆盖 | {coverage_text} |", f"| Receipt coverage | {coverage_text} |"
        )
    )
    if runtime is None:
        receipt_elapsed = telemetry["elapsed_seconds"]
        if receipt_elapsed["observation_sum"] is None:
            runtime_text = _text(
                language,
                "总耗时未记录；未提供运行明细，缺少回执不能证明未运行",
                "Total elapsed time not recorded; without run details, a missing receipt does not prove a site was not run",
            )
        else:
            runtime_text = _text(
                language,
                f"回执记录的站点耗时合计 {_duration_text(receipt_elapsed['observation_sum'], language)}；未提供运行明细，缺少回执不能证明未运行",
                f"Recorded site elapsed times total {_duration_text(receipt_elapsed['observation_sum'], language)}; without run details, a missing receipt does not prove a site was not run",
            )
    else:
        elapsed = runtime.get("elapsed_seconds")
        elapsed_text = (
            _duration_text(elapsed, language)
            if elapsed is not None
            else _text(language, "未记录", "not recorded")
        )
        run_count = (
            len(runtime["runs"]) if runtime["preview"] else len(coverage["runtime_attempt_sites"])
        )
        runtime_text = _text(
            language,
            f"{'预览' if runtime['preview'] else '实际'}运行 {run_count} 项，用时 {elapsed_text}",
            f"{'Preview' if runtime['preview'] else 'Actual'} run: {run_count} sites; elapsed {elapsed_text}",
        )
        if runtime["missing_receipt_sites"]:
            runtime_text += _text(
                language,
                f"；缺少 {len(runtime['missing_receipt_sites'])} 项运行回执",
                f"; {_count_text(len(runtime['missing_receipt_sites']), '', language, 'run receipts')} missing",
            )
    lines.append(
        _text(language, f"| 运行时长 | {runtime_text} |", f"| Elapsed time | {runtime_text} |")
    )
    request_count, _ = _daily_request_count(report)
    request_text = (
        _text(language, "未记录", "not recorded")
        if request_count is None
        else _text(language, f"{request_count}次", str(request_count))
    )
    lines.append(
        _text(
            language,
            f"| 来源发现 | HTTP 请求 {request_text}（{_receipt_scope(report, language)}，含重定向）；成功读取页面/接口（含目录与搜索数据） {_scoped_metric_text(report, telemetry['source']['pages_visited'], unit='次', language=language)}；发现并排队的链接候选 {_scoped_metric_text(report, telemetry['source']['links_discovered'], unit='条', language=language, english_unit='link candidates')} |",
            f"| Source discovery | HTTP requests {request_text} ({_receipt_scope(report, language)}, including redirects); pages/APIs read successfully (including directory and search data) {_scoped_metric_text(report, telemetry['source']['pages_visited'], unit='次', language=language, english_unit='pages')}; newly discovered and queued links {_scoped_metric_text(report, telemetry['source']['links_discovered'], unit='条', language=language, english_unit='link candidates')} |",
        )
    )
    downloaded = _stage_metric_text(report, "downloaded", language=language)
    file_types = _text(language, "；", "; ").join(
        _text(
            language,
            f"{label} {_scoped_metric_text(report, telemetry['source'][f'{kind}_files'], unit='份', language=language)}",
            f"{english_label} {_scoped_metric_text(report, telemetry['source'][f'{kind}_files'], unit='份', language=language)}",
        )
        for kind, label, english_label in (
            ("html", "HTML", "HTML"),
            ("pdf", "PDF", "PDF"),
            ("other", "其他", "Other"),
        )
    )
    lines.append(
        _text(
            language,
            f"| 收集文件 | 下载{downloaded}（{_receipt_scope(report, language)}合计）；{file_types}；唯一文件数 {_scoped_unique_text(report, telemetry['source']['unique_file_count'], unit='份', language=language)} |",
            f"| Collected files | Downloaded {downloaded} ({_receipt_scope(report, language)} total); {file_types}; unique files {_scoped_unique_text(report, telemetry['source']['unique_file_count'], unit='份', language=language)} |",
        )
    )
    new_versions = _stage_metric_text(report, "new_versions", unit="", language=language)
    duplicates = _stage_metric_text(report, "duplicates", unit="", language=language)
    enriched = _stage_metric_text(report, "enriched", unit="", language=language)
    new_unique = telemetry["database"]["new_versions"].get("exact_unique_count")
    duplicate_unique = telemetry["database"]["duplicates"].get("exact_unique_count")
    enriched_unique = telemetry["enrichment"].get("exact_unique_count")
    if new_unique is not None:
        new_versions += _text(
            language,
            f"（唯一版本 {_scoped_unique_text(report, telemetry['database']['new_versions'], unit='份', language=language)}）",
            f" (unique versions: {_scoped_unique_text(report, telemetry['database']['new_versions'], unit='份', language=language)})",
        )
    if duplicate_unique is not None:
        duplicates += _text(
            language,
            f"（唯一版本 {_scoped_unique_text(report, telemetry['database']['duplicates'], unit='份', language=language)}）",
            f" (unique versions: {_scoped_unique_text(report, telemetry['database']['duplicates'], unit='份', language=language)})",
        )
    if enriched_unique is not None:
        enriched += _text(
            language,
            f"（唯一资料 {_scoped_unique_text(report, telemetry['enrichment'], unit='份', language=language)}）",
            f" (unique items: {_scoped_unique_text(report, telemetry['enrichment'], unit='份', language=language)})",
        )
    lines.append(
        _text(
            language,
            f"| 入库与摘要分类 | 新增入库 {new_versions}；复用 {duplicates}；摘要分类 {enriched} |",
            f"| Database and summary classification | New {new_versions}; reused {duplicates}; classified {enriched} |",
        )
    )
    lines.append(
        _text(
            language,
            f"| 正文转换（Markdown） | 成功 {_scoped_metric_text(report, telemetry['conversion']['succeeded'], unit='份', language=language)}；失败 {_scoped_metric_text(report, telemetry['conversion']['failed'], unit='份', language=language)} |",
            f"| Body conversion (Markdown) | Succeeded {_scoped_metric_text(report, telemetry['conversion']['succeeded'], unit='份', language=language)}; failed {_scoped_metric_text(report, telemetry['conversion']['failed'], unit='份', language=language)} |",
        )
    )
    ai = telemetry["ai_first_candidates"]
    ai_observations = ai["observations"]
    ai_unique = ai["exact_unique_count"]["exact_unique_count"]
    if ai_observations.get("observation_sum") is not None:
        ai_text = _text(
            language,
            f"首类候选 {_scoped_metric_text(report, ai_observations, unit='', language=language)}",
            f"AI-first candidates {_scoped_metric_text(report, ai_observations, unit='', language=language)}",
        )
        if ai_unique is not None:
            ai_text += _text(
                language,
                f"，唯一资料 {_scoped_unique_text(report, ai['exact_unique_count'], unit='篇', language=language)}",
                f", unique items {_scoped_unique_text(report, ai['exact_unique_count'], unit='篇', language=language)}",
            )
    else:
        old_ai = report["stages"]["ai_candidates"].get("run_observation_sum")
        ai_text = _text(language, "首类候选未记录", "AI-first candidates not recorded")
        if old_ai is not None:
            ai_text += _text(
                language,
                f"；旧口径 AI 候选 {old_ai}（不能推断首类）",
                f"; legacy any-category AI candidates {old_ai} (primary category cannot be inferred)",
            )
    lines.append(
        _text(language, f"| AI 首类候选 | {ai_text} |", f"| AI-first candidates | {ai_text} |")
    )
    for target, label in (
        ("china", _text(language, "国内", "China")),
        ("overseas", _text(language, "海外", "Overseas")),
    ):
        value = telemetry["targets"][target]
        ack_metric = value["acknowledged"]
        ack_unique = value["acknowledged_exact_unique_count"]
        ack_text = _scoped_metric_text(report, ack_metric, unit="", language=language)
        if ack_unique is not None:
            ack_text += _text(
                language,
                f"，唯一确认 {_scoped_unique_text(report, {'exact_unique_count': ack_unique, 'known_receipts': value['acknowledged_identity_known_receipts']}, unit='篇', language=language)}",
                f", unique confirmations {_scoped_unique_text(report, {'exact_unique_count': ack_unique, 'known_receipts': value['acknowledged_identity_known_receipts']}, unit='篇', language=language)}",
            )
        ready_unique = value["ready_confirmed_exact_unique_count"]
        identity_known = value["ready_identity_known_receipts"]
        receipt_count = len(coverage["actual_collection_receipt_sites"])
        ready_text = (
            _count_text(ready_unique, "篇", language)
            if ready_unique is not None and identity_known == receipt_count
            else (
                _text(
                    language,
                    f"至少 {ready_unique} 篇（身份信息覆盖 {identity_known}/{receipt_count} 站回执）",
                    f"at least {_count_text(ready_unique, '篇', language)} (identities covered by {identity_known}/{receipt_count} site receipts)",
                )
                if ready_unique is not None
                else _text(language, "未记录", "not recorded")
            )
        )
        lines.append(
            _text(
                language,
                f"| {label}同步与可搜索 | 入库确认 {ack_text}次；已可搜索篇数 {ready_text} |",
                f"| {label} sync and searchability | Ingestion confirmations: {ack_text}; searchable articles: {ready_text} |",
            )
        )

    site_rows: dict[str, tuple[str, str, str, str]] = {}
    for site in collection_receipts:
        row = receipt_by_site[site]
        request_count = _receipt_request_count(row)
        download_count = (row.get("stages", {}).get("downloaded") or {}).get("count")
        request_text = (
            _text(language, "HTTP未记录", "HTTP requests not recorded")
            if request_count is None
            else f"HTTP {request_count}"
        )
        download_text = (
            _text(language, "下载未记录", "downloads not recorded")
            if download_count is None
            else _text(
                language,
                f"下载 {download_count}份",
                f"{_count_text(download_count, '份', language)} downloaded",
            )
        )
        hub_parts = []
        for key, label, english_label in (
            ("new_versions", "新增", "new"),
            ("duplicates", "复用", "reused"),
            ("enriched", "分类", "classified"),
        ):
            count = (row.get("stages", {}).get(key) or {}).get("count")
            hub_parts.append(
                _text(
                    language,
                    f"{label} {'未记录' if count is None else count}",
                    f"{english_label} {'not recorded' if count is None else count}",
                )
            )
        site_telemetry = row.get("telemetry") or {}
        ai_first = site_telemetry.get("ai_first_candidate_count")
        ai_ids = site_telemetry.get("ai_first_candidate_ids")
        if ai_first is None and ai_ids is not None:
            ai_first = len(ai_ids)
        old_ai = (row.get("stages", {}).get("ai_candidates") or {}).get("count")
        conversion = site_telemetry.get("conversion") or {}
        conversion_succeeded = conversion.get("succeeded_count")
        conversion_failed = conversion.get("failed_count")
        hub_parts.extend(
            [
                _text(
                    language,
                    "正文转换成功 "
                    + ("未记录" if conversion_succeeded is None else f"{conversion_succeeded}份")
                    + "；失败 "
                    + ("未记录" if conversion_failed is None else f"{conversion_failed}份"),
                    "Body conversion succeeded "
                    + (
                        "not recorded"
                        if conversion_succeeded is None
                        else _count_text(conversion_succeeded, "份", language)
                    )
                    + "; failed "
                    + (
                        "not recorded"
                        if conversion_failed is None
                        else _count_text(conversion_failed, "份", language)
                    ),
                ),
                (
                    _text(language, f"AI首类 {ai_first}篇", f"AI-first {ai_first} articles")
                    if ai_first is not None
                    else _text(language, "AI首类未记录", "AI-first not recorded")
                    + (
                        _text(
                            language,
                            f"（旧口径 AI 候选 {old_ai}）",
                            f" (legacy any-category AI candidates {old_ai})",
                        )
                        if old_ai is not None
                        else ""
                    )
                ),
            ]
        )
        if ai_first == 0:
            target_text = _text(language, "无需同步", "No sync needed")
        else:
            target_parts = []
            for target, target_label in (
                ("china", _text(language, "国内", "China")),
                ("overseas", _text(language, "海外", "Overseas")),
            ):
                ack = (row.get("stages", {}).get(f"{target}_ack") or {}).get("acknowledged")
                ack_text = (
                    _text(language, "入库确认未记录", "ingestion confirmation not recorded")
                    if ack is None
                    else _text(
                        language,
                        f"入库确认{ack}次",
                        f"{_count_text(ack, '次', language, 'ingestion confirmations')}",
                    )
                )
                target_telemetry = site_telemetry.get("targets", {}).get(target) or {}
                ready_ids = target_telemetry.get("ready_ids")
                ready_text = (
                    _text(
                        language,
                        f"可搜索{len(ready_ids)}篇",
                        f"{_count_text(len(ready_ids), '篇', language, 'searchable articles')}",
                    )
                    if ready_ids is not None
                    else _text(language, "可搜索篇数未记录", "searchable count not recorded")
                )
                target_parts.append(
                    _text(
                        language,
                        f"{target_label}{ack_text}；{target_label}{ready_text}",
                        f"{target_label}: {ack_text}; {target_label}: {ready_text}",
                    )
                )
            target_text = _text(language, "；", "; ").join(target_parts)
            if ai_first is None:
                target_text = (
                    _text(language, "AI首类未记录；", "AI-first status not recorded; ")
                    + target_text
                )
        issue = row.get("failure_point")
        if row["effective_status"] != "succeeded" or issue:
            issue = issue or {
                "stage": "run",
                "status": row["effective_status"],
                "reason": row.get("reason")
                or _text(language, "未记录具体原因", "No specific reason recorded"),
            }
            stop_text = _text(
                language,
                f"{_stage_label(issue['stage'], language)}：{_short_failure_reason(issue['reason'], issue['stage'], language)}",
                f"{_stage_label(issue['stage'], language)}: {_short_failure_reason(issue['reason'], issue['stage'], language)}",
            )
        else:
            stop_text = _text(
                language, "已完成当前可证阶段", "All currently verifiable stages completed"
            )
        site_rows[site] = (
            _text(language, f"{request_text}；{download_text}", f"{request_text}; {download_text}"),
            _text(language, "；", "; ").join(hub_parts),
            target_text,
            stop_text,
        )
    if runtime is not None:
        for row in runtime["runs"]:
            site = row["site_id"]
            if row["preview"] or site in matched_runtime_sites or _action(site) != "collect":
                continue
            reason = (
                _short_failure_reason(row["error"], "run", language)
                if row.get("error")
                else _text(
                    language, "本次运行未返回可关联回执", "This run returned no linkable receipt"
                )
            )
            previous = site_rows.get(site)
            if previous is None:
                site_rows[site] = (
                    _text(
                        language,
                        "HTTP未记录；下载未记录",
                        "HTTP requests not recorded; downloads not recorded",
                    ),
                    _text(
                        language,
                        "新增未记录；复用未记录；分类未记录；正文转换成功未记录；失败未记录；AI首类未记录",
                        "New, reused, and classified counts not recorded; body conversion succeeded and failed counts not recorded; AI-first count not recorded",
                    ),
                    _text(
                        language,
                        "国内/海外入库确认未记录；可搜索篇数未记录",
                        "China/overseas ingestion confirmations and searchable counts not recorded",
                    ),
                    _text(
                        language,
                        f"本次运行回执缺失：{reason}",
                        f"Current run receipt missing: {reason}",
                    ),
                )
            else:
                site_rows[site] = (
                    _text(language, f"历史 {previous[0]}", f"Historical: {previous[0]}"),
                    _text(language, f"历史 {previous[1]}", f"Historical: {previous[1]}"),
                    _text(language, f"历史 {previous[2]}", f"Historical: {previous[2]}"),
                    _text(
                        language,
                        f"本次运行回执缺失：{reason}",
                        f"Current run receipt missing: {reason}",
                    ),
                )
    lines.extend(
        [
            "",
            _text(language, "## 各站进度与停点", "## Site progress and stopping points"),
            _text(
                language,
                "| 站点 | 请求 / 下载 | 本地库新增 / 复用 / 分类 / 转换 / AI首类 | 同步与可搜索 | 停点或结果 |",
                "| Site | Requests / downloads | Local database new / reused / classified / conversion / AI-first | Sync and searchability | Stop or result |",
            ),
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for site, values in site_rows.items():
        lines.append(
            f"| {_site_label(site, language)} | {_escape_cell(values[0])} | {_escape_cell(values[1])} | "
            f"{_escape_cell(values[2])} | {_escape_cell(values[3])} |"
        )
    appendix = []
    monitor_sites = set(report["monitoring_only"]["planned_sites"])
    monitor_sites.update(report["monitoring_only"]["actual_receipt_sites"])
    monitor_rows = {
        row["site_id"]: row
        for row in (runtime["runs"] if runtime is not None else [])
        if _action(row["site_id"]) == "monitor_only"
    }
    monitor_sites.update(monitor_rows)
    if monitor_sites:
        monitor_results = []
        for site in sorted(monitor_sites, key=SITES.index):
            receipt = receipt_by_site.get(site)
            run_row = monitor_rows.get(site)
            planned = site in report["monitoring_only"]["planned_sites"]
            if runtime is not None and runtime["preview"]:
                result = (
                    _text(
                        language,
                        f"同日回执（{_monitor_result_text(receipt, language)}）；本次仅为预览",
                        f"Same-day receipt ({_monitor_result_text(receipt, language)}); current run is only a preview",
                    )
                    if receipt
                    else _text(
                        language,
                        "预览列入计划，未证明检查已执行",
                        "Listed in preview plan; execution not confirmed",
                    )
                )
            elif run_row is not None and site in matched_runtime_sites and receipt:
                result = _text(
                    language,
                    "本次回执：" + _monitor_result_text(receipt, language),
                    "Current receipt: " + _monitor_result_text(receipt, language),
                )
            elif run_row is not None:
                previous = (
                    _text(
                        language,
                        f"同日历史回执：{_monitor_result_text(receipt, language)}；",
                        f"Same-day historical receipt: {_monitor_result_text(receipt, language)}; ",
                    )
                    if receipt
                    else ""
                )
                reason = (
                    _short_failure_reason(run_row["error"], "monitor", language)
                    if run_row.get("error")
                    else _text(
                        language,
                        "本次运行未返回可关联回执",
                        "This run returned no linkable receipt",
                    )
                )
                result = previous + _text(
                    language,
                    f"本次检查回执缺失：{reason}",
                    f"Current check receipt missing: {reason}",
                )
            elif receipt and runtime is not None:
                result = _text(
                    language,
                    f"同日回执：{_monitor_result_text(receipt, language)}；本次运行未见该项",
                    f"Same-day receipt: {_monitor_result_text(receipt, language)}; not seen in this run",
                )
            elif receipt:
                result = _text(
                    language,
                    "当日回执：" + _monitor_result_text(receipt, language),
                    "Dated receipt: " + _monitor_result_text(receipt, language),
                )
            elif planned and runtime is not None:
                result = _text(
                    language, "计划检查，未见本次运行证据", "Planned check; no evidence in this run"
                )
            elif planned:
                result = _text(
                    language,
                    "计划检查，未提供运行清单；是否执行未知",
                    "Planned check; no run manifest provided, so execution is unknown",
                )
            else:
                continue
            monitor_results.append(
                _text(
                    language,
                    f"{_site_label(site, language)}：{result}",
                    f"{_site_label(site, language)}: {result}",
                )
            )
        if monitor_results:
            appendix.append(
                _text(
                    language,
                    "监控项（单独报告，不计入来源收集）：" + "；".join(monitor_results),
                    "Monitoring items (reported separately, excluded from collection): "
                    + "; ".join(monitor_results),
                )
            )
    if plan["hold_sites"]:
        appendix.append(
            _text(
                language,
                "保留但不执行："
                + ", ".join(_site_label(site, language) for site in plan["hold_sites"]),
                "Held; not run: "
                + ", ".join(_site_label(site, language) for site in plan["hold_sites"]),
            )
        )
    if runtime is not None and not runtime["preview"]:
        not_run = [
            site
            for site in coverage.get("planned_sites_not_attempted", [])
            if _action(site) == "collect"
        ]
        if not_run:
            appendix.append(
                _text(
                    language,
                    "运行输出中未见：" + ", ".join(_site_label(site, language) for site in not_run),
                    "Not seen in run output: "
                    + ", ".join(_site_label(site, language) for site in not_run),
                )
            )
    if appendix:
        lines.extend(
            [
                "",
                _text(
                    language,
                    "覆盖说明：" + "；".join(appendix) + "。",
                    "Coverage notes: " + "; ".join(appendix) + ".",
                ),
            ]
        )
    lines.extend(
        [
            "",
            _text(
                language,
                "> 数量按当日回执中的运行记录合计；重跑会重复计入。精确唯一数仅在身份集合齐全时显示。缺字段为未记录；旧口径 AI 候选不会被推断为 AI 首类。",
                "> Counts are receipt run observations; retries are counted again. Exact unique counts appear only when identity sets are complete. Missing fields are unrecorded; legacy any-category AI counts are not inferred as AI-first.",
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def _duration_text(seconds: float | int, language: str = "zh") -> str:
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if language == "en":
        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes or hours:
            parts.append(f"{minutes}m")
        parts.append(f"{secs}s")
        return " ".join(parts)
    if hours:
        return f"{hours} 小时 {minutes} 分 {secs} 秒"
    if minutes:
        return f"{minutes} 分 {secs} 秒"
    return f"{secs} 秒"


def _ready_label(status: str, language: str = "zh") -> str:
    labels = {
        "succeeded": ("已可搜索", "searchable"),
        "failed": ("可搜索失败", "searchability failed"),
        "partial": ("部分可搜索", "partially searchable"),
        "pending": ("待确认可搜索", "searchability pending confirmation"),
        "unknown": ("可搜索未记录", "searchability not recorded"),
        "not_required": (
            "worker 未要求确认可搜索",
            "worker did not request searchability confirmation",
        ),
    }
    return labels.get(status, (status, status))[1 if language == "en" else 0]


def _stage_label(stage: str, language: str = "zh") -> str:
    labels = {
        "downloaded": ("来源读取/收集", "Source read/collection"),
        "new_versions": ("本地库新增", "Local database additions"),
        "duplicates": ("本地库去重", "Local database deduplication"),
        "enriched": ("AI 补全/分类", "AI enrichment/classification"),
        "conversion": ("正文转换（Markdown）", "Body conversion (Markdown)"),
        "ai_candidates": ("AI 首类筛选", "AI-first filter"),
        "china_ack": ("国内入库确认", "China ingestion confirmation"),
        "china_ready": ("国内可搜索确认", "China searchable confirmation"),
        "overseas_ack": ("海外入库确认", "Overseas ingestion confirmation"),
        "overseas_ready": ("海外可搜索确认", "Overseas searchable confirmation"),
        "run": ("运行", "Run"),
    }
    pair = labels.get(stage, (stage, stage))
    return pair[1 if language == "en" else 0]


def _status_label(status: str, language: str = "zh") -> str:
    labels = {
        "succeeded": ("成功", "succeeded"),
        "failed": ("失败", "failed"),
        "partial": ("部分完成", "partial"),
        "pending": ("待处理", "pending"),
        "unknown": ("未知/未记录", "unknown/not recorded"),
        "not_required": ("未要求，未确认可搜索", "not required; not confirmed searchable"),
        "缺失": ("缺少回执", "receipt missing"),
    }
    pair = labels.get(status, (status, status))
    return pair[1 if language == "en" else 0]


def _site_label(site: str, language: str = "zh") -> str:
    labels = {
        "iaa": ("国际精算协会", "International Actuarial Association"),
        "iaba": ("国际黑人精算师协会", "International Association of Black Actuaries"),
        "soa": ("美国精算师学会", "Society of Actuaries"),
        "soa-ai-topic-landing": ("美国精算师学会 AI 主题页", "SOA AI topic page"),
        "soa-ai-bulletin-focused": ("美国精算师学会 AI 简报", "SOA AI bulletin"),
        "cas": ("美国意外险精算师协会", "Casualty Actuarial Society"),
        "aaa": ("美国精算师学会 AAA", "American Academy of Actuaries"),
        "cia-ica": ("加拿大精算师协会", "Canadian Institute of Actuaries"),
        "cia-research-publications": ("加拿大精算师协会研究出版", "CIA research publications"),
        "cca": ("美国咨询精算师协会", "Conference of Consulting Actuaries"),
        "aae": ("欧洲精算师协会", "Actuarial Association of Europe"),
        "eaa": ("欧洲精算学院", "European Actuarial Academy"),
        "ifoa-uk": ("英国精算师协会 IFoA", "Institute and Faculty of Actuaries (IFoA)"),
        "france": ("法国精算师协会", "French Institute of Actuaries"),
        "dav": ("德国精算师协会", "German Association of Actuaries (DAV)"),
        "swiss-association-of-actuaries": ("瑞士精算师协会", "Swiss Association of Actuaries"),
        "italy": ("意大利国家精算师协会", "Italian National Council of Actuaries"),
        "istituto-italiano-degli-attuari": ("意大利精算师学会", "Italian Actuarial Institute"),
        "spain": ("西班牙精算师协会", "Spanish Institute of Actuaries"),
        "australia": ("澳大利亚精算师协会", "Actuaries Institute Australia"),
        "iai": ("印度精算师协会", "Institute of Actuaries of India"),
        "iaj": ("日本精算师会", "Institute of Actuaries of Japan"),
        "institute-of-actuaries-of": ("韩国精算师学会", "Institute of Actuaries of Korea"),
        "aict": ("台湾精算学会", "Actuarial Institute of Chinese Taipei"),
        "caa": ("中国精算师协会", "China Association of Actuaries"),
        "ashk": ("香港精算学会", "Actuarial Society of Hong Kong"),
        "assa": ("南非精算学会", "Actuarial Society of South Africa"),
        "task": ("肯尼亚精算师协会", "Actuarial Society of Kenya"),
        "ama": ("摩洛哥精算师协会", "Moroccan Association of Actuaries"),
        "iba-brazil": ("巴西精算师协会", "Brazilian Institute of Actuaries"),
        "aca-colombia": ("哥伦比亚精算师协会", "Colombian Actuarial Association"),
        "conac-mexico": ("墨西哥精算师协会", "Mexican College of Actuaries"),
    }
    pair = labels.get(site, (site, site))
    return pair[1 if language == "en" else 0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offline daily planner/status/report; never runs collection or writes a case ledger."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser(
        "plan", help="show six daily baseline sites and up to two failure retries"
    )
    plan.add_argument("--date", required=True, help="America/New_York local date (YYYY-MM-DD)")
    plan.add_argument(
        "--receipts", required=True, type=Path, help="directory of finalized daily v2 receipts"
    )
    plan.add_argument("--json", action="store_true", help="emit JSON")
    for command in ("status", "report"):
        sub = subparsers.add_parser(
            command, help=f"{command} one America/New_York local date from daily v2 receipts"
        )
        sub.add_argument("--date", required=True, help="local calendar date (YYYY-MM-DD)")
        sub.add_argument(
            "--receipts", required=True, type=Path, help="directory of finalized daily v2 receipts"
        )
        if command == "report":
            sub.add_argument(
                "--case-ledger",
                type=Path,
                help="optional agent-maintained ledger used to avoid repeated research",
            )
            sub.add_argument(
                "--runtime-output",
                type=Path,
                help="optional same-day run-daily JSON, used only to show attempts and missing receipts",
            )
            sub.add_argument(
                "--format",
                choices=("json", "markdown"),
                default="json",
                help="report output format (default: json)",
            )
            sub.add_argument(
                "--language",
                choices=("zh", "en"),
                default="zh",
                help="Markdown language (default: zh); JSON output is locale-neutral",
            )
        sub.add_argument("--json", action="store_true", help="emit JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        day = parse_day(args.date)
        receipts = read_receipts(args.receipts)
        if args.command == "plan":
            output = make_plan(day, receipts)
        elif args.command == "status":
            output = make_status(day, receipts)
        else:
            runtime_output = None
            if args.runtime_output:
                try:
                    raw_runtime_output = json.loads(args.runtime_output.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise FlowError(
                        f"cannot read runtime output {args.runtime_output}: {exc}"
                    ) from exc
                runtime_output = _normalize_runtime_output(
                    raw_runtime_output, day, args.runtime_output
                )
            output = make_report(day, receipts, _load_ledger(args.case_ledger), runtime_output)
    except FlowError as exc:
        parser.error(str(exc))
    if args.command == "report" and args.format == "markdown" and not args.json:
        print(render_markdown(output, language=args.language), end="")
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
