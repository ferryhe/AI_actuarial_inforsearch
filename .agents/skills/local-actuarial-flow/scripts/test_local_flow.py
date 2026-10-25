import contextlib
import io
import json
import re
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import local_flow as flow


def receipt_for(day, site, *, run_status="succeeded", ai=0, failed_stage=None, error="source parser failed", evidence=None, china=None, overseas=None):
    stages = {
        "downloaded": {"status": "succeeded", "count": 1},
        "new_versions": {"status": "succeeded", "count": 1},
        "duplicates": {"status": "succeeded", "count": 0},
        "enriched": {"status": "succeeded", "count": 1},
        "ai_candidates": {"status": "succeeded", "count": ai},
    }
    if failed_stage:
        stages[failed_stage] = {"status": "failed", "error": error, "evidence": evidence or ["https://example.test/list"]}
    if china is not None:
        stages["china_ack"] = china
    if overseas is not None:
        stages["overseas_ack"] = overseas
    result = {
        "schema_version": 2,
        "receipt_id": f"{day.isoformat()}/{site}",
        "date_local": day.isoformat(),
        "site_id": site,
        "run_status": run_status,
        "stages": stages,
    }
    if run_status in {"failed", "partial"}:
        result["reason"] = error
    return result


def monitor_receipt(day, site="iaba", status="succeeded"):
    stage = {"status": status}
    if status in {"failed", "partial"}:
        stage["error"] = "navigation changed"
        stage["evidence"] = ["https://example.test/monitor"]
    return {
        "schema_version": 2,
        "receipt_id": f"{day.isoformat()}/{site}",
        "date_local": day.isoformat(),
        "site_id": site,
        "run_status": status,
        **({"reason": "navigation changed"} if status in {"failed", "partial"} else {}),
        "stages": {"monitor": stage},
    }


def normalized(raw, name="fixture.json"):
    return flow.normalize_receipt(raw, Path(name))


def history(*raw_receipts):
    result = {}
    for raw in raw_receipts:
        receipt = normalized(raw)
        result[(receipt["date_local"], receipt["site_id"])] = receipt
    return result


def failed_receipt(day, site):
    if site in flow.MONITOR_ONLY_SITES:
        return monitor_receipt(day, site, "failed")
    return receipt_for(day, site, run_status="failed", failed_stage="downloaded", error=f"failure at {site}")


class LocalFlowTests(unittest.TestCase):
    def test_six_site_rotation_covers_all_32_in_any_seven_dates_including_dst_weeks(self):
        self.assertEqual(len(flow.SITES), 32)
        for start in (date(2026, 3, 5), date(2026, 10, 29), date(2026, 10, 25)):
            plans = [flow.make_plan(start + timedelta(days=i)) for i in range(7)]
            planned = {site for plan in plans for site in plan["baseline_sites"]}
            self.assertEqual(len(planned), 32)
            self.assertTrue(all(len(plan["baseline_sites"]) == 6 for plan in plans))
            self.assertTrue(all(len(plan["items"]) == 6 for plan in plans))
        self.assertTrue(any("istituto-italiano-degli-attuari" in flow.baseline_sites(date(2026, 10, 25) + timedelta(days=i)) for i in range(6)))

    def test_plan_uses_local_date_at_six_and_handles_both_dst_offsets(self):
        spring = flow.make_plan(date(2026, 3, 8))
        fall = flow.make_plan(date(2026, 11, 1))
        self.assertEqual(spring["scheduled_local_at"], "2026-03-08T06:00-04:00")
        self.assertEqual(fall["scheduled_local_at"], "2026-11-01T06:00-05:00")

    def test_daily_plan_caps_retries_and_never_replaces_baseline(self):
        day = date(2026, 10, 25)
        prior = day - timedelta(days=1)
        baseline = set(flow.baseline_sites(day))
        candidates = [site for site in flow.SITES if site not in baseline and site != next(iter(flow.HELD_SITES))][:9]
        failed = [failed_receipt(prior, site) for site in candidates]
        plan = flow.make_plan(day, history(*failed))
        self.assertEqual(len(plan["baseline_sites"]), 6)
        self.assertEqual(len(plan["extra_retry_sites"]), 2)
        self.assertEqual(len(set(plan["extra_retry_sites"])), 2)
        self.assertFalse(set(plan["extra_retry_sites"]) & baseline)
        self.assertEqual(len(plan["retry_candidates_deferred"]), len(candidates) - 2)

    def test_failure_retry_rotation_prevents_unattempted_failure_queue_starvation(self):
        first = date(2026, 10, 25)
        prior = first - timedelta(days=1)
        failures = [failed_receipt(prior, site) for site in flow.SITES if site not in flow.HELD_SITES]
        receipts = history(*failures)
        retried = set()
        for offset in range(32):
            plan = flow.make_plan(first + timedelta(days=offset), receipts)
            retried.update(plan["extra_retry_sites"])
            self.assertLessEqual(len(plan["extra_retry_sites"]), 2)
        self.assertEqual(set(flow.SITES) - flow.HELD_SITES, retried)

    def test_receipts_deduplicate_identical_files_and_reject_conflicts_or_v1(self):
        day = date(2026, 10, 25)
        site = flow.baseline_sites(day)[0]
        raw = receipt_for(day, site)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.json").write_text(json.dumps(raw), encoding="utf-8")
            (root / "copy.json").write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")
            self.assertEqual(len(flow.read_receipts(root)), 1)
            conflict = dict(raw, run_status="partial", reason="partial run")
            (root / "conflict.json").write_text(json.dumps(conflict), encoding="utf-8")
            with self.assertRaisesRegex(flow.FlowError, "conflicting receipts"):
                flow.read_receipts(root)
            (root / "conflict.json").unlink()
            legacy = dict(raw, schema_version=1, slot_start_utc="2026-10-25T12:00:00Z")
            (root / "legacy.json").write_text(json.dumps(legacy), encoding="utf-8")
            with self.assertRaisesRegex(flow.FlowError, "quarantine.*v2"):
                flow.read_receipts(root)

    def test_status_distinguishes_not_run_from_source_failure_and_daily_budget_exceptions(self):
        day = date(2026, 10, 25)
        planned = flow.baseline_sites(day)
        actual = history(receipt_for(day, planned[0], run_status="failed", failed_stage="downloaded"))
        status = flow.make_status(day, actual)
        rows = {row["site_id"]: row for row in status["rows"]}
        self.assertEqual(rows[planned[0]]["state"], "failed")
        self.assertEqual(rows[planned[1]]["state"], "not_run")
        self.assertIn("scheduling gap", rows[planned[1]]["reason"])
        self.assertEqual(status["budget_exceptions"]["unplanned_actual_sites"], [])
        outside = next(site for site in flow.SITES if site not in planned and site not in flow.HELD_SITES)
        extra_actual = history(receipt_for(day, outside))
        self.assertTrue(flow.make_status(day, extra_actual)["budget_exceptions"]["has_outside_plan_receipts"])
        repeated_receipt = receipt_for(day, planned[0])
        repeated_receipt["attempt_count"] = 2
        repeated = flow.make_status(day, history(repeated_receipt))["budget_exceptions"]
        self.assertEqual(repeated["unplanned_repeat_attempt_sites"], [planned[0]])
        self.assertTrue(repeated["has_budget_exception"])

        nine = [
            receipt_for(day, site)
            for site in flow.SITES
            if site not in flow.HELD_SITES and site not in flow.MONITOR_ONLY_SITES
        ][:9]
        over_cap = flow.make_status(day, history(*nine))["budget_exceptions"]
        self.assertTrue(over_cap["exceeds_daily_site_cap"])
        self.assertTrue(over_cap["exceeds_daily_attempt_cap"])

        prior_day = day - timedelta(days=1)
        failed_site = next(site for site in flow.SITES if site not in flow.HELD_SITES and site not in planned)
        with_retry = history(failed_receipt(prior_day, failed_site))
        retry = flow.make_plan(day, with_retry)["extra_retry_sites"][0]
        planned_retry_status = flow.make_status(day, history(failed_receipt(prior_day, failed_site), receipt_for(day, retry)))
        self.assertFalse(planned_retry_status["budget_exceptions"]["has_outside_plan_receipts"])

    def test_succeeded_top_level_with_failed_overseas_ready_is_partial_and_researchable(self):
        day = date(2026, 10, 25)
        site = flow.baseline_sites(day)[0]
        raw = receipt_for(day, site, ai=1, overseas={
            "status": "succeeded", "acknowledged": 1, "pending": 0, "failed": 0,
            "ready_status": "failed", "ready_error": "index build failed", "ready_evidence": ["kb://version/123"],
        })
        report = flow.make_report(day, history(raw))
        row = next(row for row in report["site_statuses"] if row["site_id"] == site)
        self.assertEqual(raw["run_status"], "succeeded")
        self.assertEqual(row["state"], "partial")
        self.assertEqual(row["failure_stages"][0]["stage"], "overseas_ready")
        self.assertEqual(report["suggested_research"][0]["stage"], "overseas_ready")

    def test_ack_success_does_not_hide_unknown_or_pending_ready(self):
        day = date(2026, 10, 25)
        site = flow.baseline_sites(day)[0]
        raw = receipt_for(day, site, ai=1, china={
            "status": "succeeded", "acknowledged": 1, "pending": 0, "failed": 0,
            "ready_status": "succeeded",
        }, overseas={
            "status": "succeeded", "acknowledged": 1, "pending": 0, "failed": 0,
            "ready_status": "pending",
        })
        report = flow.make_report(day, history(raw))
        self.assertEqual(report["stages"]["china_ack"]["ready_status_counts"], {"succeeded": 1})
        self.assertEqual(report["stages"]["overseas_ack"]["ready_status_counts"], {"pending": 1})
        row = next(row for row in report["site_statuses"] if row["site_id"] == site)
        self.assertEqual(row["state"], "partial")
        self.assertEqual(row["failure_stages"], [])
        self.assertEqual(report["research_queue"], [])

    def test_zero_ai_candidates_does_not_invent_target_failure(self):
        day = date(2026, 10, 25)
        site = flow.baseline_sites(day)[0]
        report = flow.make_report(day, history(receipt_for(day, site, ai=0)))
        row = next(row for row in report["site_statuses"] if row["site_id"] == site)
        self.assertEqual(row["state"], "succeeded")
        self.assertEqual(report["research_queue"], [])
        self.assertEqual(report["stages"]["overseas_ack"]["ready_status_counts"], {"unknown": 1})

    def test_daily_receipt_counts_are_cumulative_even_when_latest_attempt_succeeds_with_zero(self):
        day = date(2026, 10, 25)
        site = flow.baseline_sites(day)[0]
        raw = receipt_for(day, site, ai=0)
        raw["attempt_count"] = 2
        raw["stages"]["downloaded"]["count"] = 4
        raw["stages"]["new_versions"]["count"] = 3
        report = flow.make_report(day, history(raw))
        self.assertEqual(report["receipts"][0]["attempt_count"], 2)
        self.assertEqual(report["stages"]["downloaded"]["run_observation_sum"], 4)
        self.assertEqual(report["stages"]["new_versions"]["run_observation_sum"], 3)

    def test_monitor_only_receipts_allow_structural_monitor_and_reject_collection_payload(self):
        day = date(2026, 10, 25)
        valid = normalized(monitor_receipt(day))
        report = flow.make_report(day, {(day.isoformat(), "iaba"): valid})
        self.assertEqual(report["monitoring_only"]["actual_receipt_sites"], ["iaba"])
        invalid = monitor_receipt(day)
        invalid["stages"]["ai_candidates"] = {"status": "succeeded", "count": 1}
        with self.assertRaisesRegex(flow.FlowError, "cannot include.*AI"):
            normalized(invalid)
        invalid = monitor_receipt(day)
        invalid["stages"]["monitor"] = {"status": "failed"}
        with self.assertRaisesRegex(flow.FlowError, "error is required"):
            normalized(invalid)
        missing = monitor_receipt(day)
        missing["stages"] = {}
        with self.assertRaisesRegex(flow.FlowError, "must include the structural monitor stage"):
            normalized(missing)

    def test_case_recovery_requires_success_for_same_stage_and_unknown_preserves_case(self):
        day0 = date(2026, 10, 20)
        site = "iaa"
        failure = receipt_for(day0, site, run_status="partial", failed_stage="overseas_ack", error="write failed", overseas={
            "status": "succeeded", "acknowledged": 1, "pending": 0, "failed": 0,
            "ready_status": "failed", "ready_error": "not ready",
        })
        original = normalized(failure)
        case = flow._active_failure_cases({(day0.isoformat(), site): original}, day0 + timedelta(days=1))
        target_case = next(value for value in case.values() if value["stage"] == "overseas_ready")
        ledger = {target_case["case_id"]: {**target_case, "state": "active", "last_observed_date": day0.isoformat(), "evidence_fingerprint": target_case["evidence_fingerprint"]}}
        day1 = day0 + timedelta(days=1)
        incomplete = receipt_for(day1, site, ai=0)
        receipts = history(failure, incomplete)
        active_day1 = flow._active_failure_cases(receipts, day1)
        self.assertIn(target_case["case_id"], active_day1)
        updates = flow._failure_case_updates(active_day1, ledger, receipts, day1)
        self.assertEqual(next(item["action"] for item in updates if item["case_id"] == target_case["case_id"]), "observe")
        day2 = day1 + timedelta(days=1)
        recovered = receipt_for(day2, site, ai=1, overseas={
            "status": "succeeded", "acknowledged": 1, "pending": 0, "failed": 0,
            "ready_status": "succeeded",
        })
        updates = flow._failure_case_updates({}, ledger, history(failure, incomplete, recovered), day2)
        closed = next(item for item in updates if item["case_id"] == target_case["case_id"])
        self.assertEqual(closed["action"], "close")

    def test_ready_failure_survives_later_download_success_and_unknown_ready(self):
        day0 = date(2026, 10, 20)
        site = "iaa"
        failed = receipt_for(day0, site, ai=1, overseas={
            "status": "succeeded", "acknowledged": 1, "pending": 0, "failed": 0,
            "ready_status": "failed", "ready_error": "index unavailable", "ready_evidence": ["kb://version/old"],
        })
        day1 = day0 + timedelta(days=1)
        later_download = receipt_for(day1, site, ai=1, overseas={
            "status": "succeeded", "acknowledged": 1, "pending": 0, "failed": 0,
            "ready_status": "unknown",
        })
        receipts = history(failed, later_download)
        active = flow._active_failure_cases(receipts, day1)
        ready_case = next(case for case in active.values() if case["stage"] == "overseas_ready")
        self.assertEqual(ready_case["last_observed_date"], day0.isoformat())
        self.assertIn(site, flow.make_plan(day0 + timedelta(days=2), receipts)["extra_retry_sites"])
        self.assertIn(ready_case["case_id"], {case["case_id"] for case in flow.make_report(day1, receipts)["research_queue"]})

    def test_changed_evidence_remains_unresearched_across_daily_ledger_updates(self):
        day0 = date(2026, 10, 20)
        site = "iaa"
        first = receipt_for(day0, site, run_status="failed", failed_stage="downloaded", error="HTTP request failed", evidence=["https://example.test/old"])
        first_case = next(iter(flow._active_failure_cases(history(first), day0).values()))
        ledger = {first_case["case_id"]: {
            **first_case,
            "last_researched_date": day0.isoformat(),
            "last_researched_fingerprint": first_case["evidence_fingerprint"],
        }}
        day1 = day0 + timedelta(days=1)
        changed = receipt_for(day1, site, run_status="failed", failed_stage="downloaded", error="HTTP request failed", evidence=["https://example.test/new"])
        receipts = history(first, changed)
        report1 = flow.make_report(day1, receipts, ledger)
        update = next(item for item in report1["case_updates"] if item["case_id"] == first_case["case_id"])
        self.assertEqual(update["action"], "update")
        self.assertEqual(update["last_researched_fingerprint"], first_case["evidence_fingerprint"])
        self.assertIn(first_case["case_id"], {item["case_id"] for item in report1["research_queue"]})
        next_ledger = {update["case_id"]: {**update, "state": "active"}}
        day2 = day1 + timedelta(days=1)
        report2 = flow.make_report(day2, receipts, next_ledger)
        self.assertIn(first_case["case_id"], {item["case_id"] for item in report2["research_queue"]})

    def test_research_queue_is_bounded_and_same_evidence_is_not_requeued(self):
        day = date(2026, 10, 25)
        sites = [site for site in flow.SITES if site not in flow.MONITOR_ONLY_SITES and site not in flow.HELD_SITES][:5]
        raws = [receipt_for(day, site, run_status="failed", failed_stage="downloaded", error=f"failed {site}") for site in sites]
        receipts = history(*raws)
        report = flow.make_report(day, receipts)
        self.assertEqual(len(report["research_queue"]), 5)
        self.assertEqual(len(report["suggested_research"]), 2)
        first = report["suggested_research"][0]
        ledger = {first["case_id"]: {**first, "state": "active", "last_researched_date": day.isoformat()}}
        updated = flow.make_report(day, receipts, ledger)
        self.assertNotIn(first["case_id"], {item["case_id"] for item in updated["research_queue"]})

    def test_seven_day_report_separates_scheduled_from_actual_coverage(self):
        day = date(2026, 11, 3)
        receipts = {}
        for offset in range(7):
            target = day - timedelta(days=offset)
            for site in flow.baseline_sites(target):
                if site in flow.HELD_SITES:
                    continue
                raw = monitor_receipt(target, site) if site in flow.MONITOR_ONLY_SITES else receipt_for(target, site)
                item = normalized(raw)
                receipts[(target.isoformat(), site)] = item
        report = flow.make_report(day, receipts)
        self.assertEqual(report["coverage"]["planned_unique_count_7d"], 32)
        self.assertEqual(report["coverage"]["seven_day_scheduled_coverage_complete"], True)
        self.assertLess(report["coverage"]["actual_unique_count_7d"], 32)
        self.assertEqual(len(report["seven_day_window"]), 7)
        self.assertIn("not_run", report["seven_day_window"][0]["states"])

    def test_document_receipt_example_loads_and_normalizes(self):
        doc = Path(__file__).resolve().parents[1] / "references" / "receipts.zh-CN.md"
        content = doc.read_text(encoding="utf-8")
        match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
        self.assertIsNotNone(match, "receipt contract must contain a JSON example")
        raw = json.loads(match.group(1))
        receipt = flow.normalize_receipt(raw, doc)
        self.assertEqual(receipt["site_id"], "iaa")
        self.assertEqual(receipt["date_local"], "2026-10-25")

    def test_timezone_missing_has_install_hint(self):
        original = flow.TIME_ZONE
        flow.TIME_ZONE = None
        try:
            with self.assertRaisesRegex(flow.FlowError, "install tzdata"):
                flow.require_time_zone()
        finally:
            flow.TIME_ZONE = original

    def test_cli_help_json_and_idempotent_plan_status_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "receipts"
            root.mkdir()
            day = date(2026, 10, 25)
            (root / "one.json").write_text(json.dumps(receipt_for(day, flow.baseline_sites(day)[0])), encoding="utf-8")
            ledger = root.parent / "ledger.json"
            ledger.write_text('{"schema_version":1,"cases":[]}', encoding="utf-8")
            for command in ("plan", "status", "report"):
                args = [command, "--date", day.isoformat(), "--receipts", str(root), "--json"]
                if command == "report":
                    args.extend(["--case-ledger", str(ledger)])
                first, second = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(first):
                    self.assertEqual(flow.main(args), 0)
                with contextlib.redirect_stdout(second):
                    self.assertEqual(flow.main(args), 0)
                self.assertEqual(first.getvalue(), second.getvalue())
                self.assertEqual(json.loads(first.getvalue())["writes_hub_or_servers"], False)
            help_output = io.StringIO()
            with contextlib.redirect_stdout(help_output), self.assertRaises(SystemExit) as error:
                flow.main(["--help"])
            self.assertEqual(error.exception.code, 0)
            self.assertIn("plan", help_output.getvalue())


if __name__ == "__main__":
    unittest.main()
