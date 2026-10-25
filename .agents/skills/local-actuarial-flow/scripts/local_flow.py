#!/usr/bin/env python3
"""Offline planner and receipt reporter for the local actuarial collection flow."""

from __future__ import annotations

import argparse
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
SLOT = timedelta(hours=2)
SLOT_SECONDS = int(SLOT.total_seconds())
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
GROUP_SIZE = 4
GROUP_COUNT = len(SITES) // GROUP_SIZE
HELD_SITES = {"istituto-italiano-degli-attuari"}
MONITOR_ONLY_SITES = {"iaba", "eaa"}
RUN_STATUSES = {"succeeded", "partial", "failed"}
STAGE_STATUSES = RUN_STATUSES | {"pending", "unknown"}
COUNT_STAGES = ("downloaded", "new_versions", "duplicates", "enriched", "ai_candidates")
ACK_STAGES = ("china_ack", "overseas_ack")
ACK_COUNTS = ("acknowledged", "pending", "failed")


class FlowError(ValueError):
    """Input cannot safely be interpreted as a schedule or a receipt."""


def require_time_zone() -> ZoneInfo:
    if TIME_ZONE is None:
        raise FlowError("Python needs IANA zone data for America/New_York; install tzdata in this Python environment")
    return TIME_ZONE


def utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_aware(value: str, label: str) -> datetime:
    if not isinstance(value, str):
        raise FlowError(f"{label} must be an ISO 8601 datetime string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FlowError(f"{label} must be an ISO 8601 datetime: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FlowError(f"{label} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def slot_start(at: datetime) -> datetime:
    timestamp = int(at.timestamp())
    return datetime.fromtimestamp(timestamp - timestamp % SLOT_SECONDS, timezone.utc)


def slot_index(start: datetime) -> int:
    return int(start.timestamp()) // SLOT_SECONDS


def group_for(start: datetime) -> int:
    return slot_index(start) % GROUP_COUNT


def assigned_sites(start: datetime) -> list[str]:
    group = group_for(start)
    begin = group * GROUP_SIZE
    return list(SITES[begin : begin + GROUP_SIZE])


def make_slot(start: datetime) -> dict[str, Any]:
    group = group_for(start)
    sites = assigned_sites(start)
    return {
        "slot_start_utc": utc_iso(start),
        "slot_end_utc": utc_iso(start + SLOT),
        "group_index": group,
        "sites": [
            {
                "site_id": site,
                "action": "hold" if site in HELD_SITES else "monitor_only" if site in MONITOR_ONLY_SITES else "collect",
            }
            for site in sites
        ],
    }


def slots_for_local_date(day: date) -> list[datetime]:
    zone = require_time_zone()
    start_local = datetime.combine(day, time.min, zone)
    end_local = datetime.combine(day + timedelta(days=1), time.min, zone)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    first = slot_start(start_utc)
    if first < start_utc:
        first += SLOT
    slots: list[datetime] = []
    current = first
    while current < end_utc:
        slots.append(current)
        current += SLOT
    return slots


def make_plan(at: datetime) -> dict[str, Any]:
    start = slot_start(at)
    zone = require_time_zone()
    local = start.astimezone(zone)
    return {
        "schema_version": 1,
        "mode": "offline_plan",
        "timezone": "America/New_York",
        "cadence_elapsed_hours": 2,
        "anchor": "UTC Unix epoch, evenly spaced across DST transitions",
        "requested_at_utc": utc_iso(at),
        "slot": make_slot(start),
        "next_slot_start_utc": utc_iso(start + SLOT),
        "slot_start_local": local.isoformat(timespec="seconds"),
        "rotation_note": "Four monitored items per slot; eight groups cycle over 16 hours. Item policy controls full collection versus structural-only monitor versus hold; a failure does not delay other items or later slots.",
        "held_sites": sorted(HELD_SITES),
        "executes_collection": False,
        "writes_hub_or_servers": False,
    }


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FlowError(f"{field} must be a non-negative integer")
    return value


def _normalize_stage(raw: Any, stage: str) -> dict[str, Any]:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise FlowError(f"stages.{stage} must be an object")
    allowed_fields = {"status", "count"} if stage in COUNT_STAGES else {"status", *ACK_COUNTS, "ready_status"}
    extra_fields = set(raw) - allowed_fields
    if extra_fields:
        raise FlowError(f"stages.{stage} has unsupported fields: {sorted(extra_fields)}")
    status = raw.get("status", "unknown")
    if not isinstance(status, str) or status not in STAGE_STATUSES:
        raise FlowError(f"stages.{stage}.status must be one of {sorted(STAGE_STATUSES)}")
    result: dict[str, Any] = {"status": status}
    if stage in COUNT_STAGES:
        count = raw.get("count")
        result["count"] = None if count is None else _nonnegative_int(count, f"stages.{stage}.count")
    else:
        for field in ACK_COUNTS:
            count = raw.get(field)
            result[field] = None if count is None else _nonnegative_int(count, f"stages.{stage}.{field}")
        ready_status = raw.get("ready_status", "unknown")
        if not isinstance(ready_status, str) or ready_status not in STAGE_STATUSES:
            raise FlowError(f"stages.{stage}.ready_status must be one of {sorted(STAGE_STATUSES)}")
        result["ready_status"] = ready_status
    return result


def normalize_receipt(raw: Any, source: Path) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise FlowError(f"{source}: receipt root must be an object")
    allowed_fields = {"schema_version", "receipt_id", "slot_start_utc", "site_id", "run_status", "stages"}
    extra_fields = set(raw) - allowed_fields
    if extra_fields:
        raise FlowError(f"{source}: unsupported receipt fields: {sorted(extra_fields)}")
    if isinstance(raw.get("schema_version"), bool) or raw.get("schema_version") != 1:
        raise FlowError(f"{source}: schema_version must be 1")
    receipt_id = raw.get("receipt_id")
    site = raw.get("site_id")
    if not isinstance(receipt_id, str) or not receipt_id:
        raise FlowError(f"{source}: receipt_id is required")
    if not isinstance(site, str) or site not in SITES:
        raise FlowError(f"{source}: unknown site_id {site!r}")
    start = parse_aware(raw.get("slot_start_utc", ""), f"{source}: slot_start_utc")
    if start != slot_start(start):
        raise FlowError(f"{source}: slot_start_utc must align to a two-hour UTC boundary")
    if site not in assigned_sites(start):
        raise FlowError(f"{source}: {site} is not assigned to this slot")
    if site in HELD_SITES:
        raise FlowError(f"{source}: held site {site} must not have a collection receipt")
    expected_id = f"{utc_iso(start)}/{site}"
    if receipt_id != expected_id:
        raise FlowError(f"{source}: receipt_id must be the stable slot/site key {expected_id!r}")
    run_status = raw.get("run_status")
    if not isinstance(run_status, str) or run_status not in RUN_STATUSES:
        raise FlowError(f"{source}: run_status must be one of {sorted(RUN_STATUSES)}")
    stages = raw.get("stages", {})
    if not isinstance(stages, dict):
        raise FlowError(f"{source}: stages must be an object")
    if site in MONITOR_ONLY_SITES and stages:
        raise FlowError(
            f"{source}: monitor_only site {site} must not include collection, enrichment, AI, or target-ack stages"
        )
    extra_stages = set(stages) - set((*COUNT_STAGES, *ACK_STAGES))
    if extra_stages:
        raise FlowError(f"{source}: unsupported stages: {sorted(extra_stages)}")
    normalized_stages: dict[str, dict[str, Any]] = {}
    for stage in (*COUNT_STAGES, *ACK_STAGES):
        normalized_stages[stage] = _normalize_stage(stages.get(stage), stage)
    return {
        "schema_version": 1,
        "receipt_id": receipt_id,
        "slot_start_utc": utc_iso(start),
        "site_id": site,
        "run_status": run_status,
        "stages": normalized_stages,
    }


def read_receipts(receipts_path: Path, day: date) -> dict[tuple[str, str], dict[str, Any]]:
    paths = sorted(receipts_path.glob("*.json")) if receipts_path.is_dir() else [receipts_path]
    receipts: dict[tuple[str, str], dict[str, Any]] = {}
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FlowError(f"cannot read receipt {path}: {exc}") from exc
        receipt = normalize_receipt(raw, path)
        local_day = parse_aware(receipt["slot_start_utc"], "slot_start_utc").astimezone(require_time_zone()).date()
        if local_day != day:
            continue
        key = (receipt["slot_start_utc"], receipt["site_id"])
        existing = receipts.get(key)
        if existing is not None and existing != receipt:
            raise FlowError(f"conflicting receipts for {key}; keep one finalized receipt per slot/site")
        receipts[key] = receipt
    return receipts


def _aggregate_counts(receipts: list[dict[str, Any]], stage: str) -> dict[str, Any]:
    count_values = [receipt["stages"][stage]["count"] for receipt in receipts]
    known = [value for value in count_values if value is not None]
    return {
        "run_observation_sum": sum(known) if known else None,
        "known_receipts": len(known),
        "unknown_receipts": len(receipts) - len(known),
        "status_counts": dict(sorted(Counter(r["stages"][stage]["status"] for r in receipts).items())),
    }


def _aggregate_ack(receipts: list[dict[str, Any]], stage: str) -> dict[str, Any]:
    output: dict[str, Any] = {"status_counts": dict(sorted(Counter(r["stages"][stage]["status"] for r in receipts).items()))}
    output["ready_status_counts"] = dict(
        sorted(Counter(r["stages"][stage]["ready_status"] for r in receipts).items())
    )
    for field in ACK_COUNTS:
        values = [receipt["stages"][stage][field] for receipt in receipts]
        known = [value for value in values if value is not None]
        output[field] = {
            "run_observation_sum": sum(known) if known else None,
            "known_receipts": len(known),
            "unknown_receipts": len(receipts) - len(known),
        }
    return output


def make_status(day: date, receipts: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    zone = require_time_zone()
    for start in slots_for_local_date(day):
        slot = make_slot(start)
        for site in slot["sites"]:
            key = (slot["slot_start_utc"], site["site_id"])
            receipt = receipts.get(key)
            if site["action"] == "hold":
                state = "hold"
            elif receipt is None:
                state = "not_run"
            else:
                state = receipt["run_status"]
            rows.append({
                "slot_start_utc": slot["slot_start_utc"],
                "slot_start_local": parse_aware(slot["slot_start_utc"], "slot_start_utc").astimezone(zone).isoformat(timespec="seconds"),
                "site_id": site["site_id"],
                "action": site["action"],
                "state": state,
                "receipt_id": receipt["receipt_id"] if receipt else None,
            })
    return {
        "schema_version": 1,
        "mode": "offline_status",
        "date_local": day.isoformat(),
        "timezone": "America/New_York",
        "expected_site_slots": len(rows),
        "receipt_count": len(receipts),
        "states": dict(sorted(Counter(row["state"] for row in rows).items())),
        "actions": dict(sorted(Counter(row["action"] for row in rows).items())),
        "rows": rows,
        "executes_collection": False,
        "writes_hub_or_servers": False,
    }


def make_report(day: date, receipts: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    status = make_status(day, receipts)
    receipt_list = list(receipts.values())
    expected_collection_receipts = sum(
        site["action"] == "collect"
        for start in slots_for_local_date(day)
        for site in make_slot(start)["sites"]
    )
    planned_monitoring_slots = sum(
        site["action"] == "monitor_only"
        for start in slots_for_local_date(day)
        for site in make_slot(start)["sites"]
    )
    collection_receipts = [receipt for receipt in receipt_list if receipt["site_id"] not in MONITOR_ONLY_SITES]
    monitoring_receipts = [receipt for receipt in receipt_list if receipt["site_id"] in MONITOR_ONLY_SITES]
    missing_receipts = expected_collection_receipts - len(collection_receipts)
    stages = {
        **{stage: _aggregate_counts(collection_receipts, stage) for stage in COUNT_STAGES},
        **{stage: _aggregate_ack(collection_receipts, stage) for stage in ACK_STAGES},
    }
    for stage in COUNT_STAGES:
        aggregate = stages[stage]
        aggregate["missing_receipts"] = missing_receipts
        aggregate["complete_day_run_sum"] = (
            aggregate["run_observation_sum"]
            if missing_receipts == 0
            and aggregate["unknown_receipts"] == 0
            and all(r["stages"][stage]["status"] == "succeeded" for r in collection_receipts)
            else None
        )
    for stage in ACK_STAGES:
        for field in ACK_COUNTS:
            stages[stage][field]["missing_receipts"] = missing_receipts
    return {
        "schema_version": 1,
        "mode": "offline_daily_report",
        "date_local": day.isoformat(),
        "timezone": "America/New_York",
        "generated_for_local_time": "09:00",
        "coverage": {
            "expected_site_slots": status["expected_site_slots"],
            "expected_collection_receipts": expected_collection_receipts,
            "collection_receipt_count": len(collection_receipts),
            "receipt_count": len(receipt_list),
            "missing_collection_receipts": missing_receipts,
            "states": status["states"],
            "actions": status["actions"],
            "missing_receipt_is_not_zero_success": True,
            "ack_counts_are_run_observations_not_unique_backlog": True,
            "stage_counts_may_repeat_the_same_content_across_sites_or_slots": True,
        },
        "monitoring_only": {
            "planned_slots": planned_monitoring_slots,
            "receipt_count": len(monitoring_receipts),
            "states": dict(sorted(Counter(r["run_status"] for r in monitoring_receipts).items())),
            "cadence_is_external_and_not_inferred": True,
        },
        "stages": stages,
        "receipts": [
            {"receipt_id": r["receipt_id"], "slot_start_utc": r["slot_start_utc"], "site_id": r["site_id"], "action": "monitor_only" if r["site_id"] in MONITOR_ONLY_SITES else "collect", "run_status": r["run_status"]}
            for r in sorted(receipt_list, key=lambda r: (r["slot_start_utc"], r["site_id"]))
        ],
        "executes_collection": False,
        "writes_hub_or_servers": False,
    }


def parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise FlowError(f"date must use YYYY-MM-DD: {value!r}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline planner/status/daily report for the local collection flow.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan", help="show the two-hour site group for a timestamp")
    plan.add_argument("--at", required=True, help="ISO 8601 timestamp with UTC offset")
    plan.add_argument("--json", action="store_true", help="emit JSON")
    for command in ("status", "report"):
        sub = subparsers.add_parser(command, help=f"{command} one America/New_York local date from receipt JSON")
        sub.add_argument("--date", required=True, help="local calendar date (YYYY-MM-DD)")
        sub.add_argument("--receipts", required=True, type=Path, help="directory of finalized receipts or one receipt JSON")
        sub.add_argument("--json", action="store_true", help="emit JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            output = make_plan(parse_aware(args.at, "--at"))
        else:
            day = parse_day(args.date)
            receipts = read_receipts(args.receipts, day)
            output = make_status(day, receipts) if args.command == "status" else make_report(day, receipts)
    except FlowError as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
