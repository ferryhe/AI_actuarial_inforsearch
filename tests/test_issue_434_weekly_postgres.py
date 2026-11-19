from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from ai_actuarial.api.services import weekly_explanations as weekly
from ai_actuarial.api.services.weekly_updates import (
    current_utc_iso_week_period,
    eastern_intake_day,
    get_weekly_update_summary_files,
)
from ai_actuarial.storage import Storage
from tests.postgres_helpers import postgres_url_for_path
from tests.test_issue_267_weekly_explanations import (
    FakeWeeklyExplanationGenerator,
    _seed_files,
    _snapshot,
    _write_config,
)


@pytest.mark.parametrize("count", [0, 1, 5, 60, 216, 1116])
def test_reader_fixture_counts_preserve_all_paged_members(tmp_path, monkeypatch, count):
    db_path, config_path, _ = _write_config(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    _seed_files(db_path, count=count, long_material=True)
    snapshot = _snapshot(db_path)
    db = postgres_url_for_path(db_path)
    before = weekly.preview_weekly_explanation(db_path=db, snapshot_id=snapshot["id"])
    generator = FakeWeeklyExplanationGenerator()
    result = weekly.generate_weekly_explanation(
        db_path=db, snapshot_id=snapshot["id"], generator=generator
    )
    assert result["generation_mode"] == ("empty" if count == 0 else "ai")
    assert len(generator.calls) == (0 if count == 0 else 1)
    after = weekly.preview_weekly_explanation(db_path=db, snapshot_id=snapshot["id"])
    assert before["membership_sha256"] == after["membership_sha256"]
    storage = Storage(db)
    try:
        audit = storage.get_weekly_explanation(snapshot_id=snapshot["id"])["coverage"]
        assert audit["candidate_count"] <= 60
        assert audit["selected_count"] <= 60
        assert audit["material_chars"] <= 24000
        assert audit["user_chars"] <= 26000
        assert audit["all_message_chars"] <= 32000
        assert audit["call_count"] <= 2
        members = []
        for offset in range(0, count, 500):
            page, total = storage.list_weekly_snapshot_files(
                snapshot_id=snapshot["id"], limit=500, offset=offset
            )
            members.extend(page)
            assert total == count
        assert len(members) == count
    finally:
        storage.close()


def test_failed_new_prompt_preserves_existing_success(tmp_path, monkeypatch):
    from config.yaml_config import invalidate_config_cache

    db_path, config_path, config = _write_config(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    _seed_files(db_path, count=5)
    snapshot = _snapshot(db_path)
    db = postgres_url_for_path(db_path)
    first = weekly.generate_weekly_explanation(
        db_path=db, snapshot_id=snapshot["id"], generator=FakeWeeklyExplanationGenerator()
    )
    config["ai_config"]["weekly_explanation"]["prompt"] = "Changed reader prompt"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    invalidate_config_cache()
    failed = weekly.generate_weekly_explanation(
        db_path=db,
        snapshot_id=snapshot["id"],
        generator=FakeWeeklyExplanationGenerator(["bad JSON", "bad JSON"]),
    )
    assert failed == first
    storage = Storage(db)
    try:
        saved = storage.get_weekly_explanation(snapshot_id=snapshot["id"])
        assert saved["status"] == "complete"
        assert saved["coverage"]["last_failed_attempt"]["coverage"]["generation_mode"] == "fallback"
        assert saved["claim_token"] == ""
    finally:
        storage.close()


def test_source_and_weekly_guide_share_verified_publication_window(tmp_path):
    from ai_actuarial.api.services.read import list_source_portals

    db_path, _, _ = _write_config(tmp_path)
    first_seen = "2026-03-11T03:30:00+00:00"
    _seed_files(db_path, count=6, first_seen=first_seen)
    db = postgres_url_for_path(db_path)
    storage = Storage(db)
    try:
        for index, day in enumerate(
            ("2020-06-02", "2026-02-08", "2026-03-09", "2026-03", None, None)
        ):
            url = f"https://example.com/report-{index:03d}.pdf"
            storage._conn.execute("UPDATE files SET published_time = ? WHERE url = ?", (day, url))
            storage._conn.execute("UPDATE files SET source_site = 'iaa' WHERE url = ?", (url,))
            if day:
                fact = {
                    "value": day,
                    "semantic": "publication",
                    "precision": "day" if len(day) == 10 else "month",
                    "evidence": f"Published on {day}",
                }
                storage._conn.execute(
                    "UPDATE catalog_items SET bilingual_metadata_json = ? WHERE file_url = ?",
                    (
                        json.dumps({"hub_enrichment": {"date_facts": {"publication_date": fact}}}),
                        url,
                    ),
                )
    finally:
        storage.close()
    snapshot = _snapshot(db_path)
    storage = Storage(db)
    try:
        storage._conn.execute(
            "UPDATE files SET deleted_at = ? WHERE url = ?",
            ("2026-03-18T00:00:00+00:00", "https://example.com/report-005.pdf"),
        )
        storage._conn.execute(
            "UPDATE files SET source_site = 'manual import' WHERE url = ?",
            ("https://example.com/report-004.pdf",),
        )
        detail = storage.get_weekly_snapshot(snapshot_id=snapshot["id"])
        detail["metadata"]["weekly_publication_date_evidence"] = {
            "https://example.com/report-002.pdf": {
                "catalog_date": "2026-03-09",
                "value": "2026-03-10",
                "semantic": "publication",
                "precision": "day",
                "evidence": "Published March 10, 2026",
                "source_url": "https://example.com/publication-announcement",
            },
            "https://example.com/report-004.pdf": {
                "catalog_date": None,
                "value": "2021-02",
                "semantic": "publication",
                "precision": "month",
                "evidence": "Published February 2021",
                "source_url": "https://example.com/paper-directory",
            },
            "https://example.com/report-005.pdf": {
                "catalog_date": None,
                "value": "2026-03-15",
                "semantic": "publication",
                "precision": "day",
                "evidence": "Published March 15, 2026",
                "source_url": "https://example.com/publication-announcement",
            },
        }
        storage._conn.execute(
            "UPDATE weekly_snapshots SET metadata_json = ? WHERE id = ?",
            (json.dumps(detail["metadata"]), snapshot["id"]),
        )
        storage.publish_weekly_snapshot(
            {
                "period_start": "2026-03-16T00:00:00+00:00",
                "period_end": "2026-03-23T00:00:00+00:00",
                "file_count": 0,
            },
            members=[],
        )
    finally:
        storage.close()
    reference = {"db_path": db, "snapshot_id": snapshot["id"]}
    archived = get_weekly_update_summary_files(**reference)
    first = get_weekly_update_summary_files(**reference, published_only=True, limit=1)
    second = get_weekly_update_summary_files(**reference, published_only=True, offset=1)
    assert archived["total"] == 6
    assert "backfill_count" not in archived
    assert first["total"] == 2
    assert first["backfill_count"] == second["backfill_count"] == 2
    assert first["files"][0]["published_time"] == "2026-03-10"
    assert [row["published_time"] for row in second["files"]] == ["2026-02-08"]
    portal_data = list_source_portals(db_path=db)
    source = next(p for p in portal_data["portals"] if p["portal_key"] == "iaa-papers")
    (intake,) = source["intake_updates"]
    (other_source,) = portal_data["other_intake_updates"]
    assert intake["acquired_on"] == "2026-03-10"
    assert intake["new_count"] == first["total"]
    assert intake["backfill_count"] == other_source["backfill_count"] == 1
    assert intake["backfill_count"] + other_source["backfill_count"] == first["backfill_count"]
    assert intake["other_count"] == 2
    assert [file["published_on"] for file in intake["files"][:2]] == ["2026-03-10", "2026-02-08"]
    assert {file["first_seen"] for file in intake["files"] + other_source["files"]} == {first_seen}
    assert {file["url"] for file in intake["files"] + other_source["files"]} == {
        file["url"] for file in archived["files"]
    }
    assert [file["url"] for file in intake["files"] if not file["available"]] == [
        "https://example.com/report-005.pdf"
    ]

    generator = FakeWeeklyExplanationGenerator()
    revision = weekly.regenerate_weekly_explanation(
        **reference, generator=generator, catalog_only=True
    )
    assert generator.calls == []
    assert revision["explanation"]["generation_mode"] == "catalog"
    for locale in ("en", "zh"):
        guide = revision["explanation"][f"explanation_{locale}"]
        assert guide.index("report-002.pdf") < guide.index("report-001.pdf")
        assert all(f"report-{number:03d}.pdf" not in guide for number in (0, 3, 4, 5))
    assert "另有历史资料补录" in revision["explanation"]["explanation_zh"]
    assert archived == get_weekly_update_summary_files(**reference)


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        ("2026-07-14T04:30:00Z", date(2026, 7, 14)),
        ("2026-11-10T04:30:00", date(2026, 11, 9)),
        ("2026-11-10", date(2026, 11, 10)),
    ],
)
def test_eastern_intake_day_preserves_dates_and_converts_timestamps(timestamp, expected):
    assert eastern_intake_day(timestamp) == expected


def test_open_week_source_counts_active_intake_without_a_local_file(tmp_path):
    from ai_actuarial.api.services.read import list_source_portals

    db_path, _, _ = _write_config(tmp_path)
    week_start, _ = current_utc_iso_week_period()
    start = datetime.fromisoformat(week_start)
    first_seen = (start + timedelta(hours=2)).isoformat()
    eastern_day = (start.date() - timedelta(days=1)).isoformat()
    _seed_files(db_path, count=2, first_seen=eastern_day + "T12:00:00+00:00")
    db = postgres_url_for_path(db_path)
    storage = Storage(db)
    try:
        storage._conn.execute(
            "UPDATE files SET source_site = 'iaa', local_path = NULL, first_seen = ?, last_seen = ?",
            (first_seen, first_seen),
        )
        storage._conn.execute(
            "UPDATE files SET deleted_at = ? WHERE url = ?",
            (first_seen, "https://example.com/report-001.pdf"),
        )
    finally:
        storage.close()
    source = next(
        p for p in list_source_portals(db_path=db)["portals"] if p["portal_key"] == "iaa-papers"
    )
    (intake,) = source["intake_updates"]
    assert intake["acquired_on"] == eastern_day
    assert intake["new_count"] == 1 and intake["backfill_count"] == intake["other_count"] == 0
    assert [row["url"] for row in intake["files"]] == ["https://example.com/report-000.pdf"]


def test_five_historical_ids_isolated_replay_receipts(tmp_path, monkeypatch):
    cases = json.loads(
        Path("tests/fixtures/weekly_reader_history.json").read_text(encoding="utf-8-sig")
    )
    db_path, config_path, _ = _write_config(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    _seed_files(db_path, count=216)
    db = postgres_url_for_path(db_path)
    receipts = []
    for index, case in enumerate(cases):
        storage = Storage(db)
        try:
            start = datetime(2026, 1, 5, tzinfo=timezone.utc) + timedelta(weeks=index)
            members = [
                {
                    "url": f"https://example.com/report-{i:03d}.pdf",
                    "first_seen": (start + timedelta(days=1, hours=8)).isoformat(),
                    "original_filename": f"report-{i:03d}.pdf",
                }
                for i in range(case["file_count"])
            ]
            snapshot = storage.publish_weekly_snapshot(
                {
                    "id": case["snapshot_id"],
                    "period_start": start.isoformat(),
                    "period_end": (start + timedelta(days=7)).isoformat(),
                    "file_count": case["file_count"],
                    "summary_markdown": "Synthetic fixture; this is not production history.",
                },
                members=members,
            )
            attempt = {
                "snapshot_id": snapshot["id"],
                "input_fingerprint": "old-fixture",
                "prompt_version": "weekly-explanation-v1",
                "coverage": {},
            }
            claim = storage.claim_weekly_explanation(attempt, lease_ttl_seconds=1)
            storage.finalize_weekly_explanation(
                {
                    **attempt,
                    "status": case["old_status"],
                    "error": "fixture invalid JSON" if case["old_status"] == "failed" else "",
                    "explanation_zh": "旧版夹具：本快照包含固定UTC区间及资料计数。",
                    "explanation_en": "Old fixture: immutable snapshot facts, exact UTC period and file count.",
                },
                claim_token=claim["claim_token"],
            )
        finally:
            storage.close()
        before = weekly.preview_weekly_explanation(db_path=db, snapshot_id=case["snapshot_id"])
        old = weekly.get_weekly_explanation(db_path=db, snapshot_id=case["snapshot_id"])
        generator = FakeWeeklyExplanationGenerator()
        result = weekly.regenerate_weekly_explanation(
            db_path=db, snapshot_id=case["snapshot_id"], generator=generator
        )
        after = weekly.preview_weekly_explanation(db_path=db, snapshot_id=case["snapshot_id"])
        assert before["membership_sha256"] == after["membership_sha256"]
        assert (
            result["receipt"]["before_membership_sha256"]
            == result["receipt"]["after_membership_sha256"]
        )
        assert generator.calls == []
        assert result["explanation"]["generation_mode"] == "empty"
        if members:
            assert (
                result["explanation"]["explanation_en"] == "No verified new publications this week."
            )
        assert (
            weekly.get_weekly_explanation(db_path=db, snapshot_id=case["snapshot_id"])
            == result["explanation"]
        )
        storage = Storage(db)
        try:
            assert (
                storage.get_weekly_snapshot(snapshot_id=case["snapshot_id"], include_detail=True)
                == snapshot
            )
            audit = storage.get_weekly_explanation(snapshot_id=case["snapshot_id"])["coverage"]
        finally:
            storage.close()
        receipts.append(
            {
                "fixture_only": True,
                "profile": case["profile"],
                "dry_run": before,
                "receipt": result["receipt"],
                "before": old,
                "after": result["explanation"],
                "audit": audit,
                "model_calls": len(generator.calls),
            }
        )
    evidence_dir = os.getenv("ISSUE434_EVIDENCE_DIR")
    if evidence_dir:
        Path(evidence_dir, "historical-isolated-replay.json").write_text(
            json.dumps(
                {"fixture_only": True, "production_replayed": False, "cases": receipts},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


@pytest.mark.parametrize("explicit_action", ["retry", "regenerate"])
def test_failed_new_fingerprint_cached_while_old_success_survives(
    tmp_path, monkeypatch, explicit_action
):
    from config.yaml_config import invalidate_config_cache

    db_path, config_path, config = _write_config(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    _seed_files(db_path, count=1)
    snapshot = _snapshot(db_path)
    db = postgres_url_for_path(db_path)
    first = weekly.generate_weekly_explanation(
        db_path=db, snapshot_id=snapshot["id"], generator=FakeWeeklyExplanationGenerator()
    )
    config["ai_config"]["weekly_explanation"]["prompt"] = "Changed reader prompt"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    invalidate_config_cache()
    failing = FakeWeeklyExplanationGenerator(["bad JSON"] * 4)
    for _ in range(2):
        assert (
            weekly.generate_weekly_explanation(
                db_path=db, snapshot_id=snapshot["id"], generator=failing
            )
            == first
        )
    assert len(failing.calls) == 2
    successful = FakeWeeklyExplanationGenerator()
    if explicit_action == "retry":
        result = weekly.retry_weekly_explanation(
            db_path=db, snapshot_id=snapshot["id"], generator=successful
        )
    else:
        result = weekly.regenerate_weekly_explanation(
            db_path=db, snapshot_id=snapshot["id"], generator=successful
        )["explanation"]
    assert result["status"] == "complete"
    assert len(successful.calls) == 1
    assert (
        weekly.generate_weekly_explanation(
            db_path=db, snapshot_id=snapshot["id"], generator=successful
        )
        == result
    )
    assert len(successful.calls) == 1


def test_busy_waiter_reuses_failed_fingerprint_preserving_old_success(tmp_path, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from config.yaml_config import invalidate_config_cache

    db_path, config_path, config = _write_config(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    _seed_files(db_path, count=1)
    snapshot = _snapshot(db_path)
    db = postgres_url_for_path(db_path)
    first = weekly.generate_weekly_explanation(
        db_path=db, snapshot_id=snapshot["id"], generator=FakeWeeklyExplanationGenerator()
    )
    config["ai_config"]["weekly_explanation"]["prompt"] = "Changed reader prompt"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    invalidate_config_cache()
    started, busy = threading.Event(), threading.Event()
    original_claim = Storage.claim_weekly_explanation

    def observe_claim(self, *args, **kwargs):
        claim = original_claim(self, *args, **kwargs)
        if claim["state"] == "busy":
            busy.set()
        return claim

    monkeypatch.setattr(Storage, "claim_weekly_explanation", observe_claim)

    class Failing:
        calls = 0

        def generate(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                started.set()
                assert busy.wait(timeout=5)
            return "bad JSON"

    failing = Failing()

    def generate():
        return weekly.generate_weekly_explanation(
            db_path=db, snapshot_id=snapshot["id"], generator=failing
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        owner = executor.submit(generate)
        assert started.wait(timeout=5)
        waiter = executor.submit(generate)
        assert owner.result(timeout=10) == first
        assert waiter.result(timeout=10) == first
    assert busy.is_set()
    assert failing.calls == 2
