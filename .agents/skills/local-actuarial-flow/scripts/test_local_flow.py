import contextlib
import io
import json
import re
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import local_flow as flow


def receipt_for(start, site, *, run_status="succeeded", downloaded=1, china=None, overseas=None):
    stages = {
        "downloaded": {"status": "succeeded", "count": downloaded},
        "new_versions": {"status": "succeeded", "count": 1},
        "duplicates": {"status": "succeeded", "count": 0},
        "enriched": {"status": "succeeded", "count": 1},
        "ai_candidates": {"status": "succeeded", "count": 1},
    }
    if china is not None:
        stages["china_ack"] = china
    if overseas is not None:
        stages["overseas_ack"] = overseas
    slot = flow.utc_iso(start)
    return {
        "schema_version": 1,
        "receipt_id": f"{slot}/{site}",
        "slot_start_utc": slot,
        "site_id": site,
        "run_status": run_status,
        "stages": stages,
    }


def monitoring_receipt_for(start, site, *, run_status="succeeded"):
    slot = flow.utc_iso(start)
    return {
        "schema_version": 1,
        "receipt_id": f"{slot}/{site}",
        "slot_start_utc": slot,
        "site_id": site,
        "run_status": run_status,
        "stages": {},
    }


class LocalFlowTests(unittest.TestCase):
    def test_eight_groups_cover_all_sites_and_hold_is_visible(self):
        start = datetime(2026, 10, 25, 0, tzinfo=timezone.utc)
        groups = [flow.assigned_sites(start + i * flow.SLOT) for i in range(8)]
        self.assertEqual(len(flow.SITES), 32)
        self.assertEqual(len({site for group in groups for site in group}), 32)
        self.assertTrue(all(len(group) == 4 for group in groups))
        self.assertIn("istituto-italiano-degli-attuari", flow.SITES)
        held_start = next(start + i * flow.SLOT for i in range(8) if "istituto-italiano-degli-attuari" in flow.assigned_sites(start + i * flow.SLOT))
        held = next(site for site in flow.make_slot(held_start)["sites"] if site["site_id"] == "istituto-italiano-degli-attuari")
        self.assertEqual(held["action"], "hold")
        monitor_start = next(start + i * flow.SLOT for i in range(8) if "iaba" in flow.assigned_sites(start + i * flow.SLOT))
        monitor = next(site for site in flow.make_slot(monitor_start)["sites"] if site["site_id"] == "iaba")
        self.assertEqual(monitor["action"], "monitor_only")

    def test_rotation_and_status_do_not_starve_sites_after_a_failure(self):
        start = datetime(2026, 10, 25, 0, tzinfo=timezone.utc)
        group = next(flow.assigned_sites(start + i * flow.SLOT) for i in range(8) if "istituto-italiano-degli-attuari" not in flow.assigned_sites(start + i * flow.SLOT))
        slot = next(start + i * flow.SLOT for i in range(8) if flow.assigned_sites(start + i * flow.SLOT) == group)
        receipt = receipt_for(slot, group[0], run_status="failed")
        day = slot.astimezone(flow.TIME_ZONE).date()
        status = flow.make_status(day, {(receipt["slot_start_utc"], group[0]): flow.normalize_receipt(receipt, Path("fixture.json"))})
        rows = [row for row in status["rows"] if row["slot_start_utc"] == flow.utc_iso(slot)]
        self.assertEqual(sum(row["state"] == "failed" for row in rows), 1)
        self.assertEqual(sum(row["state"] == "not_run" for row in rows), 3)

    def test_dst_local_date_uses_elapsed_two_hour_slots(self):
        self.assertEqual(len(flow.slots_for_local_date(date(2026, 3, 8))), 11)
        self.assertEqual(len(flow.slots_for_local_date(date(2026, 11, 1))), 13)
        self.assertEqual(len(flow.slots_for_local_date(date(2026, 10, 25))), 12)
        plan = flow.make_plan(datetime.fromisoformat("2026-11-01T01:30:00-04:00"))
        self.assertIn("slot_start_utc", plan["slot"])

    def test_missing_iana_database_has_install_hint(self):
        original = flow.TIME_ZONE
        flow.TIME_ZONE = None
        try:
            with self.assertRaisesRegex(flow.FlowError, "install tzdata"):
                flow.require_time_zone()
        finally:
            flow.TIME_ZONE = original

    def test_duplicate_receipts_count_once_and_conflict_fails_closed(self):
        day = date(2026, 10, 25)
        slot = flow.slots_for_local_date(day)[0]
        site = next(site for site in flow.assigned_sites(slot) if site not in flow.HELD_SITES)
        receipt = receipt_for(slot, site)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "one.json").write_text(json.dumps(receipt), encoding="utf-8")
            (root / "copy.json").write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
            loaded = flow.read_receipts(root, day)
            self.assertEqual(len(loaded), 1)
            conflict = dict(receipt)
            conflict["run_status"] = "failed"
            (root / "conflict.json").write_text(json.dumps(conflict), encoding="utf-8")
            with self.assertRaises(flow.FlowError):
                flow.read_receipts(root, day)

    def test_receipt_document_example_normalizes(self):
        doc = Path(__file__).resolve().parents[1] / "references" / "receipts.zh-CN.md"
        content = doc.read_text(encoding="utf-8")
        match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
        self.assertIsNotNone(match, "receipt contract must contain a JSON example")
        raw = json.loads(match.group(1))
        receipt = flow.normalize_receipt(raw, doc)
        self.assertEqual(receipt["site_id"], "aae")
        self.assertEqual(receipt["slot_start_utc"], "2026-10-25T12:00:00Z")

    def test_report_keeps_missing_unknown_and_independent_publish_outcomes(self):
        day = date(2026, 10, 25)
        slot = flow.slots_for_local_date(day)[0]
        sites = [site for site in flow.assigned_sites(slot) if site not in flow.HELD_SITES]
        one = receipt_for(
            slot,
            sites[0],
            china={"status": "succeeded", "acknowledged": 2, "pending": 0, "failed": 0},
            overseas={"status": "failed", "acknowledged": 0, "pending": 1, "failed": 1},
        )
        two = receipt_for(slot, sites[1], run_status="partial", downloaded=3)
        two["stages"].pop("enriched")
        receipts = {
            (one["slot_start_utc"], one["site_id"]): flow.normalize_receipt(one, Path("one.json")),
            (two["slot_start_utc"], two["site_id"]): flow.normalize_receipt(two, Path("two.json")),
        }
        report = flow.make_report(day, receipts)
        self.assertEqual(report["stages"]["downloaded"]["run_observation_sum"], 4)
        self.assertIsNone(report["stages"]["downloaded"]["complete_day_run_sum"])
        self.assertGreater(report["coverage"]["missing_collection_receipts"], 0)
        self.assertEqual(report["stages"]["china_ack"]["acknowledged"]["run_observation_sum"], 2)
        self.assertEqual(report["stages"]["overseas_ack"]["status_counts"]["failed"], 1)
        self.assertEqual(report["stages"]["china_ack"]["ready_status_counts"], {"unknown": 2})
        self.assertEqual(report["stages"]["overseas_ack"]["ready_status_counts"], {"unknown": 2})
        self.assertGreater(report["stages"]["enriched"]["unknown_receipts"], 0)
        self.assertTrue(report["coverage"]["missing_receipt_is_not_zero_success"])

    def test_ready_status_is_independent_of_ack_and_validates_enum(self):
        day = date(2026, 10, 25)
        slot = flow.slots_for_local_date(day)[0]
        site = next(site for site in flow.assigned_sites(slot) if site not in flow.HELD_SITES)
        receipt = receipt_for(
            slot,
            site,
            china={
                "status": "succeeded",
                "acknowledged": 1,
                "pending": 0,
                "failed": 0,
                "ready_status": "succeeded",
            },
            overseas={
                "status": "succeeded",
                "acknowledged": 1,
                "pending": 0,
                "failed": 0,
                "ready_status": "pending",
            },
        )
        normalized = flow.normalize_receipt(receipt, Path("target-ready.json"))
        report = flow.make_report(day, {(normalized["slot_start_utc"], site): normalized})
        china = report["stages"]["china_ack"]
        overseas = report["stages"]["overseas_ack"]
        self.assertEqual(china["status_counts"], {"succeeded": 1})
        self.assertEqual(overseas["status_counts"], {"succeeded": 1})
        self.assertEqual(china["ready_status_counts"], {"succeeded": 1})
        self.assertEqual(overseas["ready_status_counts"], {"pending": 1})

        receipt["stages"]["overseas_ack"]["ready_status"] = "ready"
        with self.assertRaisesRegex(flow.FlowError, "ready_status must be one of"):
            flow.normalize_receipt(receipt, Path("invalid-ready.json"))

    def test_cli_help_json_and_idempotent_plan(self):
        output1 = io.StringIO()
        with contextlib.redirect_stdout(output1):
            self.assertEqual(flow.main(["plan", "--at", "2026-10-25T09:00:00-04:00", "--json"]), 0)
        output2 = io.StringIO()
        with contextlib.redirect_stdout(output2):
            self.assertEqual(flow.main(["plan", "--at", "2026-10-25T09:00:00-04:00", "--json"]), 0)
        self.assertEqual(output1.getvalue(), output2.getvalue())
        self.assertEqual(json.loads(output1.getvalue())["executes_collection"], False)
        help_output = io.StringIO()
        with contextlib.redirect_stdout(help_output):
            with self.assertRaises(SystemExit) as error:
                flow.main(["--help"])
        self.assertEqual(error.exception.code, 0)
        self.assertIn("plan", help_output.getvalue())

    def test_missing_receipt_has_no_zero_success_totals(self):
        report = flow.make_report(date(2026, 10, 25), {})
        self.assertEqual(report["coverage"]["receipt_count"], 0)
        self.assertIsNone(report["stages"]["downloaded"]["complete_day_run_sum"])
        self.assertIsNone(report["stages"]["downloaded"]["run_observation_sum"])
        self.assertEqual(
            report["coverage"]["states"]["not_run"],
            report["coverage"]["expected_collection_receipts"] + report["monitoring_only"]["planned_slots"],
        )

    def test_monitor_only_receipt_is_reported_separately(self):
        day = date(2026, 10, 25)
        receipts = {}
        for site in sorted(flow.MONITOR_ONLY_SITES):
            start = next(slot for slot in flow.slots_for_local_date(day) if site in flow.assigned_sites(slot))
            receipt = monitoring_receipt_for(start, site)
            normalized = flow.normalize_receipt(receipt, Path(f"{site}.json"))
            receipts[(receipt["slot_start_utc"], site)] = normalized

            invalid = monitoring_receipt_for(start, site)
            invalid["stages"] = {
                "downloaded": {"status": "succeeded", "count": 1},
                "ai_candidates": {"status": "succeeded", "count": 1},
                "china_ack": {"status": "succeeded", "acknowledged": 1, "pending": 0, "failed": 0},
            }
            with self.assertRaisesRegex(flow.FlowError, "monitor_only site"):
                flow.normalize_receipt(invalid, Path(f"{site}-invalid.json"))

        report = flow.make_report(day, receipts)
        self.assertEqual(report["monitoring_only"]["receipt_count"], 2)
        self.assertEqual(report["coverage"]["collection_receipt_count"], 0)
        self.assertIsNone(report["stages"]["downloaded"]["run_observation_sum"])

    def test_monitor_only_receipt_does_not_invalidate_collection_complete_sum(self):
        day = date(2026, 10, 25)
        receipts = {}
        for start in flow.slots_for_local_date(day):
            for site in flow.assigned_sites(start):
                if site in flow.HELD_SITES:
                    continue
                receipt = monitoring_receipt_for(start, site) if site in flow.MONITOR_ONLY_SITES else receipt_for(start, site)
                normalized = flow.normalize_receipt(receipt, Path("fixture.json"))
                receipts[(normalized["slot_start_utc"], site)] = normalized
        report = flow.make_report(day, receipts)
        self.assertEqual(
            report["stages"]["downloaded"]["complete_day_run_sum"],
            report["coverage"]["expected_collection_receipts"],
        )

    def test_status_and_report_json_cli_contract(self):
        day = date(2026, 10, 25)
        start = flow.slots_for_local_date(day)[0]
        site = next(site for site in flow.assigned_sites(start) if site not in flow.HELD_SITES)
        receipt = receipt_for(start, site)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
            for command in ("status", "report"):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    result = flow.main([command, "--date", day.isoformat(), "--receipts", str(root), "--json"])
                self.assertEqual(result, 0)
                parsed = json.loads(output.getvalue())
                self.assertEqual(parsed["date_local"], day.isoformat())
                self.assertEqual(parsed["writes_hub_or_servers"], False)
                if command == "report":
                    self.assertEqual(parsed["stages"]["china_ack"]["ready_status_counts"], {"unknown": 1})


if __name__ == "__main__":
    unittest.main()
