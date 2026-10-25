#!/usr/bin/env python3
"""Offline daily rotation planner and receipt reporter; never runs collection."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    TIME_ZONE: ZoneInfo | None = ZoneInfo("America/New_York")
except ZoneInfoNotFoundError:
    TIME_ZONE = None

SITES = (
    "iaa", "iaba", "soa", "soa-ai-topic-landing",
    "soa-ai-bulletin-focused", "cas", "aaa", "cia-ica",
    "cia-research-publications", "cca", "aae", "eaa",
    "ifoa-uk", "france", "dav", "swiss-association-of-actuaries",
    "italy", "istituto-italiano-degli-attuari", "spain", "australia",
    "iai", "iaj", "institute-of-actuaries-of", "aict",
    "caa", "ashk", "assa", "task",
    "ama", "iba-brazil", "aca-colombia", "conac-mexico",
)
ROTATION_ANCHOR = date(2026, 10, 25)
BASELINE_SIZE = 6
MAX_EXTRA_RETRIES = 2
HELD_SITES = {"istituto-italiano-degli-attuari"}
MONITOR_ONLY_SITES = {"iaba", "eaa"}
RUN_STATUSES = {"succeeded", "partial", "failed"}
STAGE_STATUSES = RUN_STATUSES | {"pending", "unknown"}
COUNT_STAGES = ("downloaded", "new_versions", "duplicates", "enriched", "ai_candidates")
ACK_STAGES = ("china_ack", "overseas_ack")
ACK_COUNTS = ("acknowledged", "pending", "failed")
ALL_STAGES = (*COUNT_STAGES, *ACK_STAGES)


class FlowError(ValueError):
    """Input cannot safely be interpreted as a schedule, receipt, or ledger."""


def require_time_zone() -> ZoneInfo:
    if TIME_ZONE is None:
        raise FlowError("Python needs IANA zone data for America/New_York; install tzdata in this Python environment")
    return TIME_ZONE


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FlowError(f"{field} must be a non-negative integer")
    return value


def _string_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise FlowError(f"{field} must be an array of non-empty strings")
    return list(value)


def _normalize_failure_fields(raw: dict[str, Any], prefix: str) -> dict[str, Any]:
    error = raw.get("error")
    evidence = _string_list(raw.get("evidence", []), f"{prefix}.evidence")
    if error is not None and (not isinstance(error, str) or not error.strip()):
        raise FlowError(f"{prefix}.error must be a non-empty string when supplied")
    status = raw.get("status", "unknown")
    if status in {"failed", "partial"} and not error:
        raise FlowError(f"{prefix}.error is required for {status} status")
    return {"error": error, "evidence": evidence}


def _normalize_stage(raw: Any, stage: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise FlowError(f"stages.{stage} must be an object")
    if stage == "monitor":
        allowed = {"status", "error", "evidence"}
    elif stage in COUNT_STAGES:
        allowed = {"status", "count", "error", "evidence"}
    else:
        allowed = {"status", *ACK_COUNTS, "ready_status", "ready_error", "ready_evidence", "error", "evidence"}
    extra = set(raw) - allowed
    if extra:
        raise FlowError(f"stages.{stage} has unsupported fields: {sorted(extra)}")
    status = raw.get("status", "unknown")
    if not isinstance(status, str) or status not in STAGE_STATUSES:
        raise FlowError(f"stages.{stage}.status must be one of {sorted(STAGE_STATUSES)}")
    result: dict[str, Any] = {"status": status, **_normalize_failure_fields(raw, f"stages.{stage}")}
    if stage in COUNT_STAGES:
        count = raw.get("count")
        result["count"] = None if count is None else _nonnegative_int(count, f"stages.{stage}.count")
    elif stage in ACK_STAGES:
        for field in ACK_COUNTS:
            count = raw.get(field)
            result[field] = None if count is None else _nonnegative_int(count, f"stages.{stage}.{field}")
        ready_status = raw.get("ready_status", "unknown")
        if not isinstance(ready_status, str) or ready_status not in STAGE_STATUSES:
            raise FlowError(f"stages.{stage}.ready_status must be one of {sorted(STAGE_STATUSES)}")
        ready_error = raw.get("ready_error")
        if ready_error is not None and (not isinstance(ready_error, str) or not ready_error.strip()):
            raise FlowError(f"stages.{stage}.ready_error must be a non-empty string when supplied")
        if ready_status in {"failed", "partial"} and not ready_error:
            raise FlowError(f"stages.{stage}.ready_error is required for {ready_status} ready_status")
        result.update({
            "ready_status": ready_status,
            "ready_error": ready_error,
            "ready_evidence": _string_list(raw.get("ready_evidence", []), f"stages.{stage}.ready_evidence"),
        })
    return result


def normalize_receipt(raw: Any, source: Path) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise FlowError(f"{source}: receipt root must be an object")
    if raw.get("schema_version") == 1:
        raise FlowError(f"{source}: legacy v1 slot receipt is not supported; quarantine it outside the daily v2 receipt directory")
    allowed = {"schema_version", "receipt_id", "date_local", "site_id", "run_status", "reason", "evidence", "attempt_count", "stages"}
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
            raise FlowError(f"{source}: monitor_only site {site} cannot include collection, enrichment, AI, or publish stages: {sorted(extra_stages)}")
        raise FlowError(f"{source}: unsupported stages for {site}: {sorted(extra_stages)}")
    normalized = {stage: _normalize_stage(stages[stage], stage) for stage in stages}
    if site in MONITOR_ONLY_SITES and "monitor" not in normalized:
        raise FlowError(f"{source}: monitor_only receipt must include the structural monitor stage")
    return {
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
            raise FlowError(f"conflicting receipts for {key}; keep one finalized receipt per date/site")
        receipts[key] = receipt
    return receipts


def _date_receipts(receipts: dict[tuple[str, str], dict[str, Any]], day: date) -> dict[str, dict[str, Any]]:
    key = day.isoformat()
    return {site: receipt for (receipt_day, site), receipt in receipts.items() if receipt_day == key}


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
        if stage["status"] in {"failed", "partial"}:
            failures.append({"stage": name, "error": stage["error"] or receipt.get("reason") or "stage reported failure", "evidence": stage["evidence"] or receipt["evidence"]})
        if name in ACK_STAGES and stage.get("ready_status") in {"failed", "partial"}:
            failures.append({"stage": name.replace("_ack", "_ready"), "error": stage["ready_error"] or "Ready reported failure", "evidence": stage["ready_evidence"]})
    if receipt["run_status"] in {"failed", "partial"} and not failures:
        failures.append({"stage": "run", "error": receipt["reason"] or f"run status {receipt['run_status']}", "evidence": receipt["evidence"]})
    return failures


def _effective_status(receipt: dict[str, Any]) -> tuple[str, str | None]:
    failures = _stage_failures(receipt)
    if receipt["run_status"] == "failed":
        return "failed", receipt.get("reason") or (failures[0]["error"] if failures else "run failed")
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
        return "partial", "AI-candidate result is unknown; publish applicability cannot be determined"
    if ai and ai["count"] is not None and ai["count"] > 0:
        for stage_name in ACK_STAGES:
            stage = receipt["stages"].get(stage_name)
            if not stage or stage["status"] in {"pending", "unknown"} or stage["ready_status"] in {"pending", "unknown"}:
                return "partial", f"AI candidates exist; {stage_name} acknowledgement or Ready is pending/unknown"
    return "succeeded", None


def _latest_receipt_by_site(receipts: dict[tuple[str, str], dict[str, Any]], before: date | None = None) -> dict[str, dict[str, Any]]:
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


def make_plan(day: date, receipts: dict[tuple[str, str], dict[str, Any]] | None = None) -> dict[str, Any]:
    receipts = receipts or {}
    baseline = baseline_sites(day)
    baseline_set = set(baseline)
    retry_candidates = [site for site in _retry_candidate_sites(receipts, day) if site not in baseline_set]
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
    if not isinstance(raw, dict) or raw.get("schema_version") != 1 or not isinstance(raw.get("cases"), list):
        raise FlowError(f"{path}: case ledger must be {{\"schema_version\":1,\"cases\":[]}}")
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


def _failure_fold(receipts: dict[tuple[str, str], dict[str, Any]], through: date) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    active: dict[tuple[str, str], dict[str, Any]] = {}
    last_success: dict[tuple[str, str], dict[str, Any]] = {}
    for (day_text, site), receipt in sorted(receipts.items()):
        if date.fromisoformat(day_text) > through:
            continue
        stage_failures = _stage_failures(receipt)
        events: list[tuple[str, str, dict[str, Any]]] = []
        if receipt["run_status"] == "succeeded":
            events.append(("run", "succeeded", {"error": None, "evidence": receipt["evidence"]}))
        elif not stage_failures:
            events.append(("run", receipt["run_status"], {"error": receipt.get("reason"), "evidence": receipt["evidence"]}))
        for stage, value in receipt["stages"].items():
            events.append((stage, value["status"], {"error": value["error"], "evidence": value["evidence"]}))
            if stage in ACK_STAGES:
                events.append((stage.replace("_ack", "_ready"), value["ready_status"], {
                    "error": value["ready_error"], "evidence": value["ready_evidence"],
                }))
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


def _active_failure_cases(receipts: dict[tuple[str, str], dict[str, Any]], day: date) -> dict[str, dict[str, Any]]:
    return _failure_fold(receipts, day)[0]


def _failure_case_updates(active: dict[str, dict[str, Any]], ledger: dict[str, dict[str, Any]], receipts: dict[tuple[str, str], dict[str, Any]], day: date) -> list[dict[str, Any]]:
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
        updates.append({
            **case,
            "action": action,
            "last_researched_date": researched_date,
            "last_researched_fingerprint": researched_fingerprint,
        })
    for case_id, old in ledger.items():
        if case_id in active or old.get("state") == "closed":
            continue
        site, stage = old.get("site_id"), old.get("stage")
        if not isinstance(site, str) or not isinstance(stage, str):
            continue
        replacement = next((case for case in active.values() if case["site_id"] == site and case["stage"] == stage), None)
        if replacement:
            updates.append({**old, "action": "supersede", "superseded_by": replacement["case_id"], "state": "closed"})
            continue
        success = last_success.get((site, stage))
        if success and success["date_local"] > old.get("last_observed_date", "0000-00-00"):
            updates.append({**old, "action": "close", "state": "closed", "closed_by_receipt": success["receipt_id"], "last_observed_date": success["date_local"]})
        else:
            updates.append({**old, "action": "preserve", "state": "active"})
    return sorted(updates, key=lambda c: (SITES.index(c["site_id"]) if c.get("site_id") in SITES else len(SITES), c.get("stage", ""), c["case_id"]))


def _research_queue(active: dict[str, dict[str, Any]], ledger: dict[str, dict[str, Any]], day: date) -> list[dict[str, Any]]:
    pending = []
    for case_id, case in active.items():
        old = ledger.get(case_id, {})
        researched_fingerprint = old.get("last_researched_fingerprint")
        if researched_fingerprint is None and old.get("last_researched_date"):
            researched_fingerprint = old.get("evidence_fingerprint")
        already_researched = old.get("last_researched_date") and researched_fingerprint == case["evidence_fingerprint"]
        if not already_researched:
            pending.append({**case, "last_researched_date": old.get("last_researched_date")})
    def priority(case: dict[str, Any]) -> tuple[str, int, str, str]:
        researched = case["last_researched_date"] or "0000-00-00"
        return researched, SITES.index(case["site_id"]), case["stage"], case["case_id"]
    return sorted(pending, key=priority)


def _site_row(site: str, day: date, plan: dict[str, Any], actual: dict[str, dict[str, Any]]) -> dict[str, Any]:
    planned_item = next((item for item in plan["items"] if item["site_id"] == site), None)
    action = _action(site)
    receipt = actual.get(site)
    if action == "hold":
        state, reason = "hold", "Istituto remains a held maintenance candidate"
    elif receipt is None:
        state = "not_run" if planned_item else "not_scheduled"
        reason = "scheduled receipt missing; this is a scheduling gap, not a source failure" if planned_item else None
    else:
        state, reason = _effective_status(receipt)
    failures = _stage_failures(receipt) if receipt else []
    return {
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
            "has_budget_exception": bool(outside or repeated) or actual_attempts > BASELINE_SIZE + MAX_EXTRA_RETRIES or len(actual) > BASELINE_SIZE + MAX_EXTRA_RETRIES,
        },
        "rows": rows,
        "executes_collection": False,
        "writes_hub_or_servers": False,
        "writes_case_ledger": False,
    }


def _counter_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    states = ("succeeded", "partial", "failed", "not_run", "not_scheduled", "hold")
    return {state: {"count": sum(row["state"] == state for row in rows), "sites": [row["site_id"] for row in rows if row["state"] == state]} for state in states}


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
    return {"run_observation_sum": sum(known_counts) if known_counts else None, "known_receipts": len(known_counts), "unknown_receipts": unknown_count, "status_counts": dict(sorted(states.items()))}


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
        **{field: {"run_observation_sum": sum(values) if values else None, "known_receipts": len(values), "unknown_receipts": unknown[field]} for field, values in counts.items()},
    }


def make_report(day: date, receipts: dict[tuple[str, str], dict[str, Any]], ledger: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    ledger = ledger or {}
    status = make_status(day, receipts)
    actual = _date_receipts(receipts, day)
    collection = [actual[site] for site in SITES if site in actual and _action(site) == "collect"]
    monitors = [actual[site] for site in SITES if site in actual and _action(site) == "monitor_only"]
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
    collection_actual_unique = sorted({site for item in window for site in item["collection_attempted_sites"]})
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
            "actual_collection_receipt_sites": [site for site in SITES if site in actual and _action(site) == "collect"],
            "actual_monitor_receipt_sites": [site for site in SITES if site in actual and _action(site) == "monitor_only"],
            "planned_unique_sites_7d": planned_unique,
            "planned_unique_count_7d": len(planned_unique),
            "actual_unique_sites_7d": actual_unique,
            "actual_unique_count_7d": len(actual_unique),
            "actual_collection_unique_sites_7d": collection_actual_unique,
            "actual_collection_unique_count_7d": len(collection_actual_unique),
            "seven_day_scheduled_coverage_complete": len(planned_unique) == len(SITES),
            "seven_day_actual_coverage_complete": len(actual_unique) == len(SITES) - len(HELD_SITES),
            "actual_coverage_excludes_hold_sites": True,
            "seven_day_actual_collection_coverage_complete": len(collection_actual_unique) == len(SITES) - len(MONITOR_ONLY_SITES) - len(HELD_SITES),
            "missing_receipt_is_not_source_failure": True,
            "budget_exceptions": status["budget_exceptions"],
        },
        "seven_day_window": window,
        "monitoring_only": {
            "planned_sites": [site for site in status["plan"]["baseline_sites"] if site in MONITOR_ONLY_SITES],
            "actual_receipt_sites": [site for site in SITES if site in actual and site in MONITOR_ONLY_SITES],
            "planned_is_not_success": True,
        },
        "stages": stages,
        "failure_cases": list(active_cases.values()),
        "case_updates": case_updates,
        "research_queue": research_queue,
        "suggested_research": research_queue[:2],
        "research_queue_deferred_count": max(0, len(research_queue) - 2),
        "case_ledger_contract": {"schema_version": 1, "empty_json": {"schema_version": 1, "cases": []}, "helper_writes_ledger": False},
        "receipts": [
            {"receipt_id": r["receipt_id"], "date_local": r["date_local"], "site_id": r["site_id"], "action": _action(r["site_id"]), "run_status": r["run_status"], "effective_status": _effective_status(r)[0], "attempt_count": r["attempt_count"]}
            for r in sorted(actual.values(), key=lambda r: r["site_id"])
        ],
        "executes_collection": False,
        "writes_hub_or_servers": False,
        "writes_case_ledger": False,
        "performs_research": False,
    }


def parse_day(value: str) -> date:
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise FlowError(f"date must use YYYY-MM-DD: {value!r}") from exc
    if result.isoformat() != value:
        raise FlowError(f"date must use YYYY-MM-DD: {value!r}")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline daily planner/status/report; never runs collection or writes a case ledger.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan", help="show six daily baseline sites and up to two failure retries")
    plan.add_argument("--date", required=True, help="America/New_York local date (YYYY-MM-DD)")
    plan.add_argument("--receipts", required=True, type=Path, help="directory of finalized daily v2 receipts")
    plan.add_argument("--json", action="store_true", help="emit JSON")
    for command in ("status", "report"):
        sub = subparsers.add_parser(command, help=f"{command} one America/New_York local date from daily v2 receipts")
        sub.add_argument("--date", required=True, help="local calendar date (YYYY-MM-DD)")
        sub.add_argument("--receipts", required=True, type=Path, help="directory of finalized daily v2 receipts")
        if command == "report":
            sub.add_argument("--case-ledger", type=Path, help="optional agent-maintained ledger used to avoid repeated research")
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
            output = make_report(day, receipts, _load_ledger(args.case_ledger))
    except FlowError as exc:
        parser.error(str(exc))
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
