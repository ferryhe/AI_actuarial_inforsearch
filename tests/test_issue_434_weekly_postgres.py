from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from ai_actuarial.api.services import weekly_explanations as weekly
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
                    "first_seen": "2026-03-10T08:00:00+00:00",
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
        assert len(generator.calls) == (0 if not members else 1)
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
