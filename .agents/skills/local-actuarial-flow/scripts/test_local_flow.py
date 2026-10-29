import contextlib
import io
import json
import re
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import local_flow as flow


def receipt_for(
    day,
    site,
    *,
    run_status="succeeded",
    ai=0,
    failed_stage=None,
    error="source parser failed",
    evidence=None,
    china=None,
    overseas=None,
):
    stages = {
        "downloaded": {"status": "succeeded", "count": 1},
        "new_versions": {"status": "succeeded", "count": 1},
        "duplicates": {"status": "succeeded", "count": 0},
        "enriched": {"status": "succeeded", "count": 1},
        "ai_candidates": {"status": "succeeded", "count": ai},
    }
    if failed_stage:
        stages[failed_stage] = {
            "status": "failed",
            "error": error,
            "evidence": evidence or ["https://example.test/list"],
        }
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
    return receipt_for(
        day, site, run_status="failed", failed_stage="downloaded", error=f"failure at {site}"
    )


class LocalFlowTests(unittest.TestCase):
    def test_six_site_rotation_covers_all_32_in_any_seven_dates_including_dst_weeks(self):
        self.assertEqual(len(flow.SITES), 32)
        for start in (date(2026, 3, 5), date(2026, 10, 29), date(2026, 10, 25)):
            plans = [flow.make_plan(start + timedelta(days=i)) for i in range(7)]
            planned = {site for plan in plans for site in plan["baseline_sites"]}
            self.assertEqual(len(planned), 32)
            self.assertTrue(all(len(plan["baseline_sites"]) == 6 for plan in plans))
            self.assertTrue(all(len(plan["items"]) == 6 for plan in plans))
        self.assertTrue(
            any(
                "istituto-italiano-degli-attuari"
                in flow.baseline_sites(date(2026, 10, 25) + timedelta(days=i))
                for i in range(6)
            )
        )

    def test_plan_uses_local_date_at_six_and_handles_both_dst_offsets(self):
        spring = flow.make_plan(date(2026, 3, 8))
        fall = flow.make_plan(date(2026, 11, 1))
        self.assertEqual(spring["scheduled_local_at"], "2026-03-08T06:00-04:00")
        self.assertEqual(fall["scheduled_local_at"], "2026-11-01T06:00-05:00")

    def test_daily_plan_caps_retries_and_never_replaces_baseline(self):
        day = date(2026, 10, 25)
        prior = day - timedelta(days=1)
        baseline = set(flow.baseline_sites(day))
        candidates = [
            site
            for site in flow.SITES
            if site not in baseline and site != next(iter(flow.HELD_SITES))
        ][:9]
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
        failures = [
            failed_receipt(prior, site) for site in flow.SITES if site not in flow.HELD_SITES
        ]
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
        actual = history(
            receipt_for(day, planned[0], run_status="failed", failed_stage="downloaded")
        )
        status = flow.make_status(day, actual)
        rows = {row["site_id"]: row for row in status["rows"]}
        self.assertEqual(rows[planned[0]]["state"], "failed")
        self.assertEqual(rows[planned[1]]["state"], "not_run")
        self.assertIn("scheduling gap", rows[planned[1]]["reason"])
        self.assertEqual(status["budget_exceptions"]["unplanned_actual_sites"], [])
        outside = next(
            site for site in flow.SITES if site not in planned and site not in flow.HELD_SITES
        )
        extra_actual = history(receipt_for(day, outside))
        self.assertTrue(
            flow.make_status(day, extra_actual)["budget_exceptions"]["has_outside_plan_receipts"]
        )
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
        failed_site = next(
            site for site in flow.SITES if site not in flow.HELD_SITES and site not in planned
        )
        with_retry = history(failed_receipt(prior_day, failed_site))
        retry = flow.make_plan(day, with_retry)["extra_retry_sites"][0]
        planned_retry_status = flow.make_status(
            day, history(failed_receipt(prior_day, failed_site), receipt_for(day, retry))
        )
        self.assertFalse(planned_retry_status["budget_exceptions"]["has_outside_plan_receipts"])

    def test_succeeded_top_level_with_failed_overseas_ready_is_partial_and_researchable(self):
        day = date(2026, 10, 25)
        site = flow.baseline_sites(day)[0]
        raw = receipt_for(
            day,
            site,
            ai=1,
            overseas={
                "status": "succeeded",
                "acknowledged": 1,
                "pending": 0,
                "failed": 0,
                "ready_status": "failed",
                "ready_error": "index build failed",
                "ready_evidence": ["kb://version/123"],
            },
        )
        report = flow.make_report(day, history(raw))
        row = next(row for row in report["site_statuses"] if row["site_id"] == site)
        self.assertEqual(raw["run_status"], "succeeded")
        self.assertEqual(row["state"], "partial")
        self.assertEqual(row["failure_stages"][0]["stage"], "overseas_ready")
        self.assertEqual(report["suggested_research"][0]["stage"], "overseas_ready")

    def test_ack_success_does_not_hide_unknown_or_pending_ready(self):
        day = date(2026, 10, 25)
        site = flow.baseline_sites(day)[0]
        raw = receipt_for(
            day,
            site,
            ai=1,
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

    def test_markdown_keeps_known_legacy_stage_totals_and_labels_old_ai_candidates(self):
        day = date(2026, 10, 29)
        raw = receipt_for(day, "caa", ai=1)
        raw["attempt_count"] = 1
        raw["stages"]["downloaded"] = {
            "status": "partial",
            "count": 119,
            "request_budget": {
                "used": 30,
                "cap": 30,
                "paused": True,
                "frontier_remaining": 1,
            },
        }
        raw["stages"]["new_versions"]["count"] = 41
        raw["stages"]["duplicates"]["count"] = 25
        raw["stages"]["enriched"]["count"] = 40
        raw["stages"]["china_ack"] = {
            "status": "succeeded",
            "acknowledged": 1,
            "pending": 0,
            "failed": 0,
            "ready_status": "succeeded",
        }
        raw["stages"]["overseas_ack"] = dict(raw["stages"]["china_ack"])
        raw["run_status"] = "partial"
        raw["reason"] = "source request budget pause"
        zero_ai = receipt_for(day, "ashk", ai=0)
        zero_ai["stages"]["downloaded"]["count"] = 0
        zero_ai["stages"]["downloaded"]["request_budget"] = {
            "used": 30,
            "cap": 30,
            "paused": False,
            "frontier_remaining": 0,
        }
        zero_ai["stages"]["new_versions"]["count"] = 0
        zero_ai["stages"]["duplicates"]["count"] = 0
        zero_ai["stages"]["enriched"]["count"] = 0
        report = flow.make_report(day, history(raw, zero_ai))
        markdown = flow.render_markdown(report)
        self.assertIn("下载119份（2站回执合计）", markdown)
        self.assertIn("HTTP 请求 60次（2站回执，含重定向）", markdown)
        self.assertIn("成功读取页面/接口（含目录与搜索数据） 未记录", markdown)
        self.assertIn("发现并排队的链接候选 未记录", markdown)
        self.assertIn("新增入库 41；复用 25；摘要分类 40", markdown)
        self.assertIn("旧口径 AI 候选 1（不能推断首类）", markdown)
        self.assertIn("AI首类未记录（旧口径 AI 候选 0）", markdown)
        self.assertIn("已可搜索篇数 未记录", markdown)
        self.assertIn("中国精算师协会", markdown)
        self.assertNotIn("无需同步", markdown)
        self.assertNotIn("已确认可搜索 7 项", markdown)

    def test_markdown_scopes_missing_receipts_and_never_sums_retry_budget_as_day_total(self):
        day = date(2026, 10, 28)
        raw = receipt_for(day, "caa")
        raw["attempt_count"] = 2
        raw["stages"]["downloaded"]["count"] = 88
        raw["stages"]["downloaded"]["request_budget"] = {
            "used": 30,
            "cap": 30,
            "paused": True,
            "frontier_remaining": 2,
        }
        receipts = history(raw)
        runtime = {
            "elapsed_seconds": None,
            "preview": False,
            "runs": [
                {
                    "site_id": "caa",
                    "preview": False,
                    "error": None,
                    "run_status": "succeeded",
                    "elapsed_seconds": None,
                    "receipt_id": f"{day.isoformat()}/caa",
                    "attempt_count": 2,
                },
                {
                    "site_id": "ashk",
                    "preview": False,
                    "error": None,
                    "run_status": "partial",
                    "elapsed_seconds": None,
                },
            ],
        }
        report = flow.make_report(day, receipts, runtime_output=runtime)
        markdown = flow.render_markdown(report)
        self.assertIn("已有1/2站回执合计", markdown)
        self.assertIn("HTTP 请求 未记录", markdown)
        self.assertIn("下载88份（已有1/2站回执合计）", markdown)
        self.assertIn("运行回执缺失", markdown)
        self.assertIn("HTTP未记录；下载未记录", markdown)

    def test_executive_summary_uses_date_receipts_when_runtime_is_not_provided(self):
        day = date(2026, 10, 29)
        raw = receipt_for(
            day,
            "caa",
            run_status="partial",
            failed_stage="downloaded",
            error="HTTP Error 404: source article not found",
        )
        raw["attempt_count"] = 1
        raw["stages"]["downloaded"]["count"] = 119
        raw["stages"]["new_versions"]["count"] = 41
        raw["stages"]["duplicates"]["count"] = 25
        raw["stages"]["enriched"]["count"] = 40
        summary = "\n".join(flow._executive_summary(flow.make_report(day, history(raw))))
        self.assertIn("有1站日期回执可参考，但本次运行覆盖未知", summary)
        self.assertIn("日期回执状态：完成0、部分1、失败0", summary)
        self.assertIn("下载119份；新增入库41、复用25、摘要分类40", summary)
        self.assertIn("HTTP 404：链接不存在", summary)
        self.assertIn("按日期回执合计，未确认运行覆盖", summary)
        self.assertNotIn("来源采集完成", summary)

    def test_executive_summary_normalizes_and_deduplicates_dependent_conversion_errors(self):
        day = date(2026, 10, 29)
        raw = receipt_for(day, "italy", run_status="partial", ai=1)
        error = "encrypted PDF cannot be extracted"
        raw["reason"] = error
        for stage in ("new_versions", "enriched", "ai_candidates"):
            raw["stages"][stage] = {"status": "failed", "count": 0, "error": error}
        raw["telemetry"] = {
            "conversion": {"succeeded_count": 0, "failed_count": 1},
            "ai_first_candidate_count": 1,
        }
        receipts = history(raw)
        receipt = next(iter(receipts.values()))
        runtime = flow._normalize_runtime_output(
            {
                "schema_version": 1,
                "date_local": day.isoformat(),
                "preview": False,
                "elapsed_seconds": 1,
                "runs": [
                    {
                        "site_id": "italy",
                        "receipt_id": receipt["receipt_id"],
                        "attempt_count": receipt["attempt_count"],
                        "run_status": receipt["run_status"],
                    }
                ],
            },
            day,
            Path("runtime-output.json"),
        )
        summary = "\n".join(
            flow._executive_summary(flow.make_report(day, receipts, runtime_output=runtime))
        )
        blockers = next(line for line in summary.splitlines() if line.startswith("- 阻塞"))
        self.assertEqual(blockers.count("加密 PDF 无法转换"), 1)
        self.assertIn("意大利国家精算师协会正文转换：加密 PDF 无法转换", blockers)
        self.assertNotIn("AI首类：加密 PDF 无法转换", blockers)

    def test_markdown_shows_partial_content_type_totals_with_receipt_coverage(self):
        day = date(2026, 10, 28)
        sites = [site for site in flow.SITES if flow._action(site) == "collect"][:8]
        raws = []
        for index, site in enumerate(sites):
            raw = receipt_for(day, site)
            if index < 5:
                raw["telemetry"] = {
                    "source": {
                        "files_by_type": {
                            "html": index + 1,
                            "pdf": 1,
                            "other": 0,
                        }
                    }
                }
            raws.append(raw)
        markdown = flow.render_markdown(flow.make_report(day, history(*raws)))
        row = next(line for line in markdown.splitlines() if line.startswith("| 收集文件 |"))
        self.assertIn("HTML 已有5/8项回执记录，合计15份", row)
        self.assertIn("PDF 已有5/8项回执记录，合计5份", row)
        self.assertIn("其他 已有5/8项回执记录，合计0份", row)

    def test_markdown_shows_site_conversion_and_ai_first_without_legacy_inference(self):
        day = date(2026, 10, 29)
        current = receipt_for(day, "iaa", ai=8)
        current["telemetry"] = {
            "conversion": {"succeeded_count": 3, "failed_count": 1},
            "ai_first_candidate_count": 2,
        }
        legacy = receipt_for(day, "ifoa-uk", ai=0)
        report = flow.make_report(day, history(current, legacy))
        lines = flow.render_markdown(report).splitlines()
        current_row = next(line for line in lines if line.startswith("| 国际精算协会 |"))
        legacy_row = next(line for line in lines if line.startswith("| 英国精算师协会 IFoA |"))
        self.assertIn("正文转换成功 3份；失败 1份", current_row)
        self.assertIn("AI首类 2篇", current_row)
        self.assertIn("正文转换成功 未记录；失败 未记录", legacy_row)
        self.assertIn("AI首类未记录（旧口径 AI 候选 0）", legacy_row)
        self.assertNotIn("无需同步", legacy_row)

    def test_markdown_reports_monitor_results_errors_and_planned_missing_separately(self):
        day = date(2026, 10, 25)
        monitor = normalized(monitor_receipt(day, "iaba", "succeeded"))
        raw_runtime = {
            "schema_version": 1,
            "date_local": day.isoformat(),
            "preview": False,
            "elapsed_seconds": 1,
            "runs": [
                {
                    "site_id": "iaba",
                    "receipt_id": monitor["receipt_id"],
                    "attempt_count": monitor["attempt_count"],
                    "run_status": monitor["run_status"],
                },
                {"site_id": "eaa", "error": "RuntimeError: monitor navigation timed out"},
            ],
        }
        runtime = flow._normalize_runtime_output(raw_runtime, day, Path("runtime-output.json"))
        report = flow.make_report(day, {(day.isoformat(), "iaba"): monitor}, runtime_output=runtime)
        markdown = flow.render_markdown(report)
        self.assertEqual(report["coverage"]["actual_collection_receipt_sites"], [])
        self.assertIn("监控项（单独报告，不计入来源收集）", markdown)
        self.assertIn("国际黑人精算师协会：本次回执：检查成功", markdown)
        self.assertIn(
            "欧洲精算学院：本次检查回执缺失：RuntimeError: monitor navigation timed out", markdown
        )

        missing_day = date(2026, 10, 26)
        self.assertIn("eaa", flow.make_plan(missing_day)["baseline_sites"])
        no_runs = flow._normalize_runtime_output(
            {
                "schema_version": 1,
                "date_local": missing_day.isoformat(),
                "preview": False,
                "elapsed_seconds": 0,
                "runs": [],
            },
            missing_day,
            Path("runtime-output.json"),
        )
        missing_report = flow.make_report(missing_day, {}, runtime_output=no_runs)
        self.assertIn(
            "欧洲精算学院：计划检查，未见本次运行证据", flow.render_markdown(missing_report)
        )

    def test_executive_summary_precedes_tables_and_uses_current_successful_receipts(self):
        day = date(2026, 10, 29)
        sites = [
            site
            for site in flow.make_plan(day)["baseline_sites"]
            if flow._action(site) == "collect"
        ]
        raws = [receipt_for(day, site) for site in sites]
        for index, raw in enumerate(raws):
            raw["stages"]["downloaded"]["count"] = index + 1
            raw["stages"]["new_versions"]["count"] = 1
            raw["telemetry"] = {"conversion": {"succeeded_count": 1, "failed_count": 0}}
        receipts = history(*raws)
        runs = [
            {
                "site_id": receipt["site_id"],
                "receipt_id": receipt["receipt_id"],
                "attempt_count": receipt["attempt_count"],
                "run_status": receipt["run_status"],
            }
            for receipt in receipts.values()
        ]
        runtime = flow._normalize_runtime_output(
            {
                "schema_version": 1,
                "date_local": day.isoformat(),
                "preview": False,
                "elapsed_seconds": 30,
                "runs": runs,
            },
            day,
            Path("runtime-output.json"),
        )
        markdown = flow.render_markdown(flow.make_report(day, receipts, runtime_output=runtime))
        self.assertLess(markdown.index("## 执行摘要"), markdown.index("| 项目 | 当日结果 |"))
        self.assertIn("## 执行摘要\n\n- 结论：", markdown)
        self.assertIn("本次对应回执显示来源采集完成", markdown)
        self.assertIn("下载21份", markdown)
        self.assertIn("新增入库6", markdown)
        self.assertIn("正文转换成功6、失败0", markdown)

    def test_executive_summary_keeps_real_faults_budget_and_target_confirmation_visible(self):
        day = date(2026, 10, 29)
        raw = receipt_for(day, "ashk", run_status="partial", ai=0)
        raw["stages"]["downloaded"] = {
            "status": "partial",
            "count": 4,
            "error": "HTTP Error 400: invalid URL",
            "request_budget": {"used": 30, "cap": 30, "paused": True, "frontier_remaining": 2},
        }
        raw["stages"]["enriched"] = {"status": "failed", "count": 0, "error": "model stage failed"}
        raw["stages"]["china_ack"] = {
            "status": "succeeded",
            "acknowledged": 1,
            "pending": 0,
            "failed": 0,
            "ready_status": "pending",
        }
        raw["stages"]["overseas_ack"] = {
            "status": "failed",
            "acknowledged": 0,
            "pending": 0,
            "failed": 1,
            "error": "SSH timed out",
            "ready_status": "unknown",
        }
        raw["telemetry"] = {"ai_first_candidate_count": 1}
        raw["telemetry"]["conversion"] = {"succeeded_count": 1, "failed_count": 1}
        receipts = history(raw)
        receipt = next(iter(receipts.values()))
        runtime = flow._normalize_runtime_output(
            {
                "schema_version": 1,
                "date_local": day.isoformat(),
                "preview": False,
                "elapsed_seconds": 60,
                "runs": [
                    {
                        "site_id": "ashk",
                        "receipt_id": receipt["receipt_id"],
                        "attempt_count": receipt["attempt_count"],
                        "run_status": receipt["run_status"],
                    }
                ],
            },
            day,
            Path("runtime-output.json"),
        )
        summary = "\n".join(
            flow._executive_summary(flow.make_report(day, receipts, runtime_output=runtime))
        )
        self.assertIn("有产出但未全部完成", summary)
        self.assertIn("HTTP 400：链接格式或请求错误", summary)
        self.assertIn("兼有预算暂停", summary)
        self.assertIn("香港精算学会正文转换：失败1份", summary)
        self.assertIn("海外入库：SSH 连接超时", summary)
        self.assertIn("国内可搜索：有 AI 首类候选，回执状态待确认可搜索", summary)
        self.assertIn("复核来源、转换或处理错误，再按原有单站流程重试", summary)
        self.assertIn("核实国内和海外入库回执、可搜索状态及容量门槛", summary)

    def test_executive_summary_does_not_count_stale_receipt_or_preview_monitor_as_success(self):
        day = date(2026, 10, 29)
        stale = receipt_for(day, "caa")
        stale["stages"]["downloaded"]["count"] = 3
        stale_receipts = history(stale)
        stale_runtime = flow._normalize_runtime_output(
            {
                "schema_version": 1,
                "date_local": day.isoformat(),
                "preview": False,
                "elapsed_seconds": 1,
                "runs": [{"site_id": "caa", "error": "RuntimeError: current attempt failed"}],
            },
            day,
            Path("runtime-output.json"),
        )
        stale_report = flow.make_report(day, stale_receipts, runtime_output=stale_runtime)
        stale_summary = "\n".join(flow._executive_summary(stale_report))
        self.assertIn("回执覆盖0/1项", stale_summary)
        self.assertIn("下载、新增入库、复用、摘要分类和转换数量未记录", stale_summary)
        self.assertIn("current attempt failed", stale_summary)
        self.assertNotIn("下载3份", stale_summary)
        self.assertIn("先核对本次运行回执缺口", stale_summary)

        monitor = normalized(monitor_receipt(day, "iaba", "succeeded"))
        preview_runtime = flow._normalize_runtime_output(
            {
                "schema_version": 1,
                "date_local": day.isoformat(),
                "preview": True,
                "elapsed_seconds": 0,
                "runs": [{"site_id": "iaba", "preview": True}],
            },
            day,
            Path("runtime-output.json"),
        )
        preview_report = flow.make_report(
            day, {(day.isoformat(), "iaba"): monitor}, runtime_output=preview_runtime
        )
        preview_summary = "\n".join(flow._executive_summary(preview_report))
        self.assertIn("仅有预览清单", preview_summary)
        self.assertIn("没有可用采集回执", preview_summary)
        self.assertNotIn("检查成功", preview_summary)

    def test_executive_summary_recommends_follow_up_for_ordinary_target_ack_failure(self):
        day = date(2026, 10, 29)
        planned = flow.make_plan(day)["baseline_sites"]
        collect_sites = [site for site in planned if flow._action(site) == "collect"]
        raws = [receipt_for(day, site) for site in collect_sites]
        target_site = collect_sites[0]
        target_raw = next(raw for raw in raws if raw["site_id"] == target_site)
        target_raw["run_status"] = "partial"
        target_raw["reason"] = "overseas write failed"
        target_raw["stages"]["overseas_ack"] = {
            "status": "failed",
            "acknowledged": 0,
            "pending": 0,
            "failed": 1,
            "error": "SSH timed out",
            "ready_status": "unknown",
        }
        receipts = history(*raws)
        runs = [
            {
                "site_id": receipt["site_id"],
                "receipt_id": receipt["receipt_id"],
                "attempt_count": receipt["attempt_count"],
                "run_status": receipt["run_status"],
            }
            for receipt in receipts.values()
        ]
        runtime = flow._normalize_runtime_output(
            {
                "schema_version": 1,
                "date_local": day.isoformat(),
                "preview": False,
                "elapsed_seconds": 10,
                "runs": runs,
            },
            day,
            Path("runtime-output.json"),
        )
        summary = "\n".join(
            flow._executive_summary(flow.make_report(day, receipts, runtime_output=runtime))
        )
        self.assertIn("海外入库：SSH 连接超时", summary)
        self.assertIn("核实海外入库回执、可搜索状态及容量门槛", summary)
        self.assertNotIn("继续按原计划观察", summary)

    def test_executive_summary_distinguishes_unattempted_sites_from_receipt_gaps(self):
        day = date(2026, 10, 29)
        monitor = normalized(monitor_receipt(day, "iaba", "succeeded"))
        runtime = flow._normalize_runtime_output(
            {
                "schema_version": 1,
                "date_local": day.isoformat(),
                "preview": False,
                "elapsed_seconds": 1,
                "runs": [
                    {
                        "site_id": "iaba",
                        "receipt_id": monitor["receipt_id"],
                        "attempt_count": monitor["attempt_count"],
                        "run_status": monitor["run_status"],
                    }
                ],
            },
            day,
            Path("runtime-output.json"),
        )
        report = flow.make_report(day, {(day.isoformat(), "iaba"): monitor}, runtime_output=runtime)
        summary = "\n".join(flow._executive_summary(report))
        advice = next(line for line in summary.splitlines() if line.startswith("- 建议"))
        self.assertEqual(report["coverage"]["runtime_attempts_without_receipts"], [])
        self.assertEqual(report["coverage"]["actual_collection_receipt_sites"], [])
        self.assertIn("计划内未见运行", summary)
        self.assertIn("确认计划内未见运行的站点是否应按计划执行", advice)
        self.assertNotIn("核对本次运行回执缺口", advice)

    def test_executive_summary_translates_receipt_contract_failure(self):
        day = date(2026, 10, 28)
        runtime = flow._normalize_runtime_output(
            {
                "schema_version": 1,
                "date_local": day.isoformat(),
                "preview": False,
                "elapsed_seconds": 1,
                "runs": [
                    {
                        "site_id": "iaj",
                        "error": "FlowError: stages.overseas_ack.ready_status must be one of ['succeeded']",
                    }
                ],
            },
            day,
            Path("runtime-output.json"),
        )
        summary = "\n".join(
            flow._executive_summary(flow.make_report(day, {}, runtime_output=runtime))
        )
        self.assertIn("已运行但回执保存失败（状态值不兼容）", summary)
        self.assertNotIn("ready_status must be one of", summary)

    def test_runtime_attempt_must_match_receipt_attempt_not_only_date_and_site(self):
        day = date(2026, 10, 29)
        old = receipt_for(day, "caa")
        old["stages"]["downloaded"]["count"] = 3
        old_receipts = history(old)
        runtime_raw = {
            "schema_version": 1,
            "date_local": day.isoformat(),
            "preview": False,
            "elapsed_seconds": 2,
            "runs": [
                {
                    "site_id": "caa",
                    "error": "RuntimeError: retry failed before receipt write",
                    "elapsed_seconds": 2,
                }
            ],
        }
        runtime_output = flow._normalize_runtime_output(
            runtime_raw, day, Path("runtime-output.json")
        )
        report = flow.make_report(day, old_receipts, runtime_output=runtime_output)
        markdown = flow.render_markdown(report)
        row = next(line for line in markdown.splitlines() if line.startswith("| 中国精算师协会 |"))
        self.assertEqual(report["receipts"][0]["stages"]["downloaded"]["count"], 3)
        self.assertEqual(report["receipts"][0]["attempt_count"], 1)
        self.assertEqual(report["coverage"]["runtime_attempts_without_receipts"], ["caa"])
        self.assertIn("历史", row)
        self.assertIn("本次运行回执缺失", row)
        self.assertIn("retry failed before receipt write", row)
        self.assertEqual(report["failure_cases"], [])

        matched_raw = {
            **runtime_raw,
            "runs": [
                {
                    "site_id": "caa",
                    "receipt_id": old["receipt_id"],
                    "attempt_count": 1,
                    "run_status": "succeeded",
                    "elapsed_seconds": 2,
                }
            ],
        }
        matched_output = flow._normalize_runtime_output(
            matched_raw, day, Path("runtime-output.json")
        )
        matched_report = flow.make_report(day, old_receipts, runtime_output=matched_output)
        self.assertEqual(matched_report["coverage"]["runtime_attempts_without_receipts"], [])

        stale_raw = {
            **matched_raw,
            "runs": [{**matched_raw["runs"][0], "attempt_count": 2}],
        }
        stale_output = flow._normalize_runtime_output(stale_raw, day, Path("runtime-output.json"))
        stale_report = flow.make_report(day, old_receipts, runtime_output=stale_output)
        self.assertEqual(stale_report["coverage"]["runtime_attempts_without_receipts"], ["caa"])

    def test_download_failure_summary_keeps_source_error_and_budget_pause(self):
        hong_kong = flow._short_failure_reason(
            "PDF: document redirect left the approved source host; request budget reached",
            "downloaded",
        )
        brazil = flow._short_failure_reason(
            "download exceeded size limit or failed streamed digest check; HTTP Error 400; request budget reached",
            "downloaded",
        )
        italy = flow._short_failure_reason(
            "encrypted PDF is unsupported; 来源采集因请求预算暂停，剩余队列 16 项",
            "conversion",
        )
        capacity = flow._short_failure_reason(
            "native ready_data_build blocked at 80.2%: [CAPACITY_BLOCKED] too full",
            "overseas_ready",
        )
        ack_no_result = flow._short_failure_reason(
            "_TargetWorkerFailure: china target worker failed: china target worker returned no JSON result (exit 255)",
            "china_ack",
        )
        self.assertIn("文档重定向离开允许来源", hong_kong)
        self.assertIn("请求预算暂停", hong_kong)
        self.assertIn("下载超出大小限制或摘要校验失败", brazil)
        self.assertIn("HTTP 400", brazil)
        self.assertIn("请求预算暂停", brazil)
        self.assertIn("加密 PDF 无法转换", italy)
        self.assertIn("请求预算暂停", italy)
        self.assertEqual(capacity, "目标容量门槛（已用80.2%），发布未继续")
        self.assertEqual(ack_no_result, "目标端未返回有效回执")
        self.assertEqual(
            flow._short_failure_reason(
                "FlowError: stages.overseas_ack.ready_status must be one of ['failed', 'partial', 'pending', 'succeeded', 'unknown']",
                "run",
            ),
            "回执可搜索状态值不兼容",
        )

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
        failure = receipt_for(
            day0,
            site,
            run_status="partial",
            failed_stage="overseas_ack",
            error="write failed",
            overseas={
                "status": "succeeded",
                "acknowledged": 1,
                "pending": 0,
                "failed": 0,
                "ready_status": "failed",
                "ready_error": "not ready",
            },
        )
        original = normalized(failure)
        case = flow._active_failure_cases(
            {(day0.isoformat(), site): original}, day0 + timedelta(days=1)
        )
        target_case = next(value for value in case.values() if value["stage"] == "overseas_ready")
        ledger = {
            target_case["case_id"]: {
                **target_case,
                "state": "active",
                "last_observed_date": day0.isoformat(),
                "evidence_fingerprint": target_case["evidence_fingerprint"],
            }
        }
        day1 = day0 + timedelta(days=1)
        incomplete = receipt_for(day1, site, ai=0)
        receipts = history(failure, incomplete)
        active_day1 = flow._active_failure_cases(receipts, day1)
        self.assertIn(target_case["case_id"], active_day1)
        updates = flow._failure_case_updates(active_day1, ledger, receipts, day1)
        self.assertEqual(
            next(item["action"] for item in updates if item["case_id"] == target_case["case_id"]),
            "observe",
        )
        day2 = day1 + timedelta(days=1)
        recovered = receipt_for(
            day2,
            site,
            ai=1,
            overseas={
                "status": "succeeded",
                "acknowledged": 1,
                "pending": 0,
                "failed": 0,
                "ready_status": "succeeded",
            },
        )
        updates = flow._failure_case_updates(
            {}, ledger, history(failure, incomplete, recovered), day2
        )
        closed = next(item for item in updates if item["case_id"] == target_case["case_id"])
        self.assertEqual(closed["action"], "close")

    def test_ready_failure_survives_later_download_success_and_unknown_ready(self):
        day0 = date(2026, 10, 20)
        site = "iaa"
        failed = receipt_for(
            day0,
            site,
            ai=1,
            overseas={
                "status": "succeeded",
                "acknowledged": 1,
                "pending": 0,
                "failed": 0,
                "ready_status": "failed",
                "ready_error": "index unavailable",
                "ready_evidence": ["kb://version/old"],
            },
        )
        day1 = day0 + timedelta(days=1)
        later_download = receipt_for(
            day1,
            site,
            ai=1,
            overseas={
                "status": "succeeded",
                "acknowledged": 1,
                "pending": 0,
                "failed": 0,
                "ready_status": "unknown",
            },
        )
        receipts = history(failed, later_download)
        active = flow._active_failure_cases(receipts, day1)
        ready_case = next(case for case in active.values() if case["stage"] == "overseas_ready")
        self.assertEqual(ready_case["last_observed_date"], day0.isoformat())
        self.assertIn(site, flow.make_plan(day0 + timedelta(days=2), receipts)["extra_retry_sites"])
        self.assertIn(
            ready_case["case_id"],
            {case["case_id"] for case in flow.make_report(day1, receipts)["research_queue"]},
        )

    def test_changed_evidence_remains_unresearched_across_daily_ledger_updates(self):
        day0 = date(2026, 10, 20)
        site = "iaa"
        first = receipt_for(
            day0,
            site,
            run_status="failed",
            failed_stage="downloaded",
            error="HTTP request failed",
            evidence=["https://example.test/old"],
        )
        first_case = next(iter(flow._active_failure_cases(history(first), day0).values()))
        ledger = {
            first_case["case_id"]: {
                **first_case,
                "last_researched_date": day0.isoformat(),
                "last_researched_fingerprint": first_case["evidence_fingerprint"],
            }
        }
        day1 = day0 + timedelta(days=1)
        changed = receipt_for(
            day1,
            site,
            run_status="failed",
            failed_stage="downloaded",
            error="HTTP request failed",
            evidence=["https://example.test/new"],
        )
        receipts = history(first, changed)
        report1 = flow.make_report(day1, receipts, ledger)
        update = next(
            item for item in report1["case_updates"] if item["case_id"] == first_case["case_id"]
        )
        self.assertEqual(update["action"], "update")
        self.assertEqual(update["last_researched_fingerprint"], first_case["evidence_fingerprint"])
        self.assertIn(
            first_case["case_id"], {item["case_id"] for item in report1["research_queue"]}
        )
        next_ledger = {update["case_id"]: {**update, "state": "active"}}
        day2 = day1 + timedelta(days=1)
        report2 = flow.make_report(day2, receipts, next_ledger)
        self.assertIn(
            first_case["case_id"], {item["case_id"] for item in report2["research_queue"]}
        )

    def test_research_queue_is_bounded_and_same_evidence_is_not_requeued(self):
        day = date(2026, 10, 25)
        sites = [
            site
            for site in flow.SITES
            if site not in flow.MONITOR_ONLY_SITES and site not in flow.HELD_SITES
        ][:5]
        raws = [
            receipt_for(
                day, site, run_status="failed", failed_stage="downloaded", error=f"failed {site}"
            )
            for site in sites
        ]
        receipts = history(*raws)
        report = flow.make_report(day, receipts)
        self.assertEqual(len(report["research_queue"]), 5)
        self.assertEqual(len(report["suggested_research"]), 2)
        first = report["suggested_research"][0]
        ledger = {
            first["case_id"]: {**first, "state": "active", "last_researched_date": day.isoformat()}
        }
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
                raw = (
                    monitor_receipt(target, site)
                    if site in flow.MONITOR_ONLY_SITES
                    else receipt_for(target, site)
                )
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
            (root / "one.json").write_text(
                json.dumps(receipt_for(day, flow.baseline_sites(day)[0])), encoding="utf-8"
            )
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
            markdown_args = [
                "report",
                "--date",
                day.isoformat(),
                "--receipts",
                str(root),
                "--case-ledger",
                str(ledger),
                "--format",
                "markdown",
            ]
            first, second = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(first):
                self.assertEqual(flow.main(markdown_args), 0)
            with contextlib.redirect_stdout(second):
                self.assertEqual(flow.main(markdown_args), 0)
            self.assertEqual(first.getvalue(), second.getvalue())
            self.assertIn("## 各站进度与停点", first.getvalue())
            help_output = io.StringIO()
            with contextlib.redirect_stdout(help_output), self.assertRaises(SystemExit) as error:
                flow.main(["--help"])
            self.assertEqual(error.exception.code, 0)
            self.assertIn("plan", help_output.getvalue())


if __name__ == "__main__":
    unittest.main()
