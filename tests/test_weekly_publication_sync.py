from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from ai_actuarial import local_collection_target_worker as target_worker
from ai_actuarial import local_weekly_publication as relay
from ai_actuarial.api.services import weekly_explanations
from ai_actuarial.storage import Storage
from tests.postgres_helpers import postgres_url_for_path
from tests.test_issue_267_weekly_explanations import (
    FakeWeeklyExplanationGenerator,
)
from tests.test_issue_267_weekly_explanations import _write_config as _write_weekly_config

PERIOD_START = "2026-10-26T00:00:00+00:00"
PERIOD_END = "2026-11-02T00:00:00+00:00"
SNAPSHOT_ID = "weekly-canonical-20261102"


def _guide(urls: list[str], *, reverse_zh: bool = False) -> tuple[str, str]:
    en = "English guide\n" + "\n".join(f"- [English {i}]({url})" for i, url in enumerate(urls))
    zh_urls = list(reversed(urls)) if reverse_zh else urls
    zh = "中文导读\n" + "\n".join(f"- [中文 {i}]({url})" for i, url in enumerate(zh_urls))
    return zh, en


def _seed_site(
    database_url: str,
    site: str,
    *,
    snapshot_id: str = SNAPSHOT_ID,
    explanation: bool = True,
    reverse_zh: bool = False,
) -> str:
    storage = Storage(database_url)
    try:
        members = []
        for index in range(7):
            url = f"https://example.org/weekly-{index}.pdf"
            first_seen = (
                datetime(2026, 10, 26, 12, tzinfo=timezone.utc) + timedelta(days=index)
            ).isoformat()
            storage.insert_file(
                url=url,
                sha256=f"{site}-sha-{index}",
                title=f"{site} title {index}",
                source_site="test-source",
                source_page_url="https://example.org/weekly",
                original_filename=f"weekly-{index}.pdf",
                local_path=f"/tmp/{site}-{index}.pdf",
                bytes=100,
                content_type="application/pdf",
            )
            bilingual = {
                "en": {
                    "title": f"{site} English {index}",
                    "summary": f"{site} English summary {index}",
                    "category": "Insurance Applications",
                    "keywords": [f"{site} topic {index}"],
                },
                "zh": {
                    "title": f"{site} 中文标题 {index}",
                    "summary": f"{site} 中文摘要 {index}",
                    "category": "Insurance Applications",
                    "keywords": [f"{site} 中文主题 {index}"],
                },
            }
            storage.upsert_catalog_item(
                {
                    "url": url,
                    "sha256": f"{site}-sha-{index}",
                    "keywords": [f"{site} topic {index}"],
                    "summary": f"{site} base summary {index}",
                    "category": "Insurance Applications",
                    "bilingual_metadata": bilingual,
                },
                pipeline_version="weekly-test-v1",
                status="ok",
                processed_at=first_seen,
            )
            storage._conn.execute(
                "UPDATE files SET first_seen = ?, last_seen = ? WHERE url = ?",
                (first_seen, first_seen, url),
            )
            members.append(
                {"url": url, "first_seen": first_seen, "original_filename": f"weekly-{index}.pdf"}
            )
        snapshot = storage.publish_weekly_snapshot(
            {
                "id": snapshot_id,
                "period_start": PERIOD_START,
                "period_end": PERIOD_END,
                "file_count": len(members),
                "summary_markdown": "# Weekly summary\nSeven current articles.",
                "metadata": {"relative_period": "previous_week", "source": "test"},
            },
            members=members,
        )
        if explanation:
            urls = [member["url"] for member in members[:4]]
            zh, en = _guide(urls, reverse_zh=reverse_zh)
            storage._conn.execute(
                "INSERT INTO weekly_explanations (snapshot_id, input_fingerprint, explanation_zh, "
                "explanation_en, provider, model, prompt_version, generated_at, status, error, "
                "coverage_json, claim_fingerprint, claim_token, claim_expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'complete', '', ?, '', '', '')",
                (
                    snapshot["id"],
                    f"{site}-input-fingerprint",
                    zh,
                    en,
                    "test-provider",
                    "test-model",
                    "weekly-v1",
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps({"generation_mode": "ai", "test": True}),
                ),
            )
            storage._conn.commit()
        return str(snapshot["id"])
    finally:
        storage.close()


def _runtime_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "local-config.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "data_root": str(tmp_path / "data"),
                "state_root": str(tmp_path / "state"),
                "hub_connection_file": str(tmp_path / "hub.json"),
                "targets": {
                    "china": {"host": "weekly-test-china"},
                    "overseas": {"host": "weekly-test-overseas"},
                },
            }
        ),
        encoding="utf-8",
    )
    return config_path


def _set_catalog_prefix(database_url: str, prefix: str) -> None:
    storage = Storage(database_url)
    try:
        for index in range(3):
            url = f"https://example.org/weekly-{index}.pdf"
            bilingual = {
                lang: {
                    "title": f"{prefix} {lang} title {index}",
                    "summary": f"{prefix} {lang} summary {index}",
                    "category": "Pricing",
                    "keywords": [f"{prefix} {lang} keyword {index}"],
                }
                for lang in ("zh", "en")
            }
            storage._conn.execute(
                "UPDATE files SET title = ? WHERE url = ?",
                (f"{prefix} base title {index}", url),
            )
            storage._conn.execute(
                "UPDATE catalog_items SET category = ?, keywords = ?, summary = ?, "
                "bilingual_metadata_json = ? WHERE file_url = ?",
                (
                    "Pricing",
                    json.dumps([f"{prefix} base keyword {index}"]),
                    f"{prefix} base summary {index}",
                    json.dumps(bilingual),
                    url,
                ),
            )
        storage._conn.commit()
    finally:
        storage.close()


def _files(database_url: str) -> list[dict[str, Any]]:
    storage = Storage(database_url)
    try:
        return storage.list_weekly_snapshot_files(snapshot_id=SNAPSHOT_ID, limit=100)[0]
    finally:
        storage.close()


def _invoke_for_databases(urls: dict[str, str], *, lose_overseas_ack: bool = False):
    lost = {"value": lose_overseas_ack}

    def invoke(_config: dict[str, Any], target: str, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("operation") == "export_weekly_publication":
            return target_worker.export_weekly_publication(
                payload,
                storage_factory=lambda: Storage.open_read_only(urls["china"]),
            )
        reply = target_worker.apply_weekly_publication(
            payload,
            storage_factory=lambda: Storage(urls[target]),
        )
        if target == "overseas" and lost["value"]:
            lost["value"] = False
            raise RuntimeError("simulated commit followed by a lost acknowledgement")
        return reply

    return invoke


def test_lost_ack_retry_reuses_frozen_pair_and_refreshes_only_for_new_guide_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    china_url = postgres_url_for_path(tmp_path / "china" / "index.db")
    overseas_url = postgres_url_for_path(tmp_path / "overseas" / "index.db")
    config_path = _runtime_config(tmp_path)
    _seed_site(china_url, "china", explanation=False)
    _seed_site(
        overseas_url,
        "overseas",
        snapshot_id="weekly-overseas-old",
        explanation=False,
    )
    _set_catalog_prefix(china_url, "China")
    _set_catalog_prefix(overseas_url, "Overseas")
    _db_path, site_config_path, _site_config = _write_weekly_config(
        tmp_path, db_path=tmp_path / "china" / "index.db"
    )
    monkeypatch.setenv("CONFIG_PATH", str(site_config_path))
    monkeypatch.setenv("DATABASE_URL", china_url)
    generator = FakeWeeklyExplanationGenerator()
    generated = weekly_explanations.generate_weekly_explanation(
        db_path=china_url,
        snapshot_id=SNAPSHOT_ID,
        generator=generator,
    )
    assert generated["status"] == "complete"
    assert len(generator.calls) == 1

    invoke = _invoke_for_databases(
        {"china": china_url, "overseas": overseas_url}, lose_overseas_ack=True
    )
    with pytest.raises(RuntimeError, match="lost acknowledgement"):
        relay.run_weekly_publication(
            "sync",
            config_path=config_path,
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            wait_seconds=0,
            invoke=invoke,
        )
    state_path = tmp_path / "state" / "weekly-publication-state.json"
    pending = json.loads(state_path.read_text(encoding="utf-8"))["pending"]
    assert pending["acks"]["china"]["target"] == "china"
    assert "overseas" not in pending["acks"]

    result = relay.run_weekly_publication(
        "sync",
        config_path=config_path,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        wait_seconds=0,
        invoke=invoke,
    )
    assert result["status"] == "succeeded"
    assert len(generator.calls) == 1
    china_files, overseas_files = _files(china_url), _files(overseas_url)
    assert [row["url"] for row in china_files] == [row["url"] for row in overseas_files]
    assert (
        china_files[:3] != overseas_files[:3]
    ), "raw storage reads retain site-local catalog metadata"
    assert [row["url"] for row in china_files[:3]] == [
        "https://example.org/weekly-0.pdf",
        "https://example.org/weekly-1.pdf",
        "https://example.org/weekly-2.pdf",
    ]

    source_projection = None
    source_guide = None
    for database_url in (china_url, overseas_url):
        storage = Storage(database_url)
        try:
            before = storage.get_weekly_snapshot(snapshot_id=SNAPSHOT_ID, include_detail=True)
            frozen = before["metadata"]["weekly_recommendation_cards_v1"]
            owner = before["metadata"]["weekly_recommendation_cards_v1_owner"]
            guide = storage.get_weekly_explanation(snapshot_id=SNAPSHOT_ID)
        finally:
            storage.close()
        if source_projection is None:
            source_projection = frozen
            source_guide = guide
        else:
            assert frozen == source_projection
            assert owner == {
                "snapshot_id": SNAPSHOT_ID,
                "guide_generated_at": source_guide["generated_at"],
            }
            assert guide["explanation_zh"] == source_guide["explanation_zh"]
            assert guide["explanation_en"] == source_guide["explanation_en"]
        _set_catalog_prefix(database_url, "Changed after sync")
        after_snapshot = Storage(database_url)
        try:
            after = after_snapshot.get_weekly_snapshot(snapshot_id=SNAPSHOT_ID, include_detail=True)
        finally:
            after_snapshot.close()
        assert after["metadata"]["weekly_recommendation_cards_v1"] == frozen
        raw_files = _files(database_url)
        assert all(row["title"].startswith("Changed after sync") for row in raw_files[:3])
    assert len(generator.calls) == 1

    revision_generator = FakeWeeklyExplanationGenerator()
    revised = weekly_explanations.generate_weekly_explanation(
        db_path=china_url,
        snapshot_id=SNAPSHOT_ID,
        generator=revision_generator,
        force=True,
    )
    assert revised["status"] == "complete"
    assert len(revision_generator.calls) == 1
    assert "Changed after sync" in revision_generator.calls[0]["messages"][-1]["content"]
    revision_result = relay.run_weekly_publication(
        "sync",
        config_path=config_path,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        wait_seconds=0,
        invoke=invoke,
    )
    assert revision_result["status"] == "succeeded"
    assert revision_result["bundle_sha256"] != result["bundle_sha256"]
    assert len(generator.calls) == 1
    assert len(revision_generator.calls) == 1
    for database_url in (china_url, overseas_url):
        storage = Storage(database_url)
        try:
            snapshot = storage.get_weekly_snapshot(snapshot_id=SNAPSHOT_ID, include_detail=True)
            guide = storage.get_weekly_explanation(snapshot_id=SNAPSHOT_ID)
        finally:
            storage.close()
        assert snapshot and guide
        assert snapshot["metadata"]["weekly_recommendation_cards_v1_owner"] == {
            "snapshot_id": SNAPSHOT_ID,
            "guide_generated_at": guide["generated_at"],
        }
        assert snapshot["metadata"]["weekly_recommendation_cards_v1"][0]["title"].startswith(
            "Changed after sync base title"
        )

    def source_read_only(
        _config: dict[str, Any], target: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        assert target == "china" and payload["operation"] == "export_weekly_publication"
        return target_worker.export_weekly_publication(
            payload,
            storage_factory=lambda: Storage.open_read_only(china_url),
        )

    state_before = state_path.read_bytes()
    repeated = relay.run_weekly_publication(
        "sync",
        config_path=config_path,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        wait_seconds=0,
        invoke=source_read_only,
    )
    assert repeated["status"] == "unchanged"
    assert state_path.read_bytes() == state_before
    assert len(generator.calls) == 1
    assert len(revision_generator.calls) == 1


def test_weekly_cli_help_and_json_contract(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    help_result = subprocess.run(
        [sys.executable, "-m", "ai_actuarial.local_weekly_publication", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0
    assert "preview" in help_result.stdout and "sync" in help_result.stdout

    expected = {
        "success": True,
        "status": "ready",
        "snapshot_id": SNAPSHOT_ID,
        "period_start": PERIOD_START,
        "period_end": PERIOD_END,
        "bundle_sha256": "a" * 64,
        "recommendation_urls": [f"https://example.org/weekly-{index}.pdf" for index in range(3)],
        "pending_acknowledgements": [],
    }
    monkeypatch.setattr(relay, "run_weekly_publication", lambda *_args, **_kwargs: expected)
    assert relay.main(["preview", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == expected


def test_export_accepts_existing_zh_order_and_four_guide_links(tmp_path: Path) -> None:
    database_url = postgres_url_for_path(tmp_path / "china" / "index.db")
    _seed_site(database_url, "china", reverse_zh=True)
    result = target_worker.export_weekly_publication(
        {
            "schema_version": 1,
            "target": "china",
            "period_start": PERIOD_START,
            "period_end": PERIOD_END,
        },
        storage_factory=lambda: Storage.open_read_only(database_url),
    )
    assert result["status"] == "ready"
    assert target_worker.validate_weekly_publication_bundle(result["bundle"])[
        "recommendation_urls"
    ] == [
        "https://example.org/weekly-0.pdf",
        "https://example.org/weekly-1.pdf",
        "https://example.org/weekly-2.pdf",
    ]
    projections = result["bundle"]["snapshot"]["metadata"]["weekly_recommendation_cards_v1"]
    assert len(projections) == 3
    member_by_url = {member["url"]: member for member in result["bundle"]["members"]}
    for projection in projections:
        member = member_by_url[projection["url"]]
        assert projection["first_seen"] == member["first_seen"]
        assert projection["original_filename"] == member["original_filename"]


def test_newer_china_guide_replaces_stale_pending_bundle_without_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    china_url = postgres_url_for_path(tmp_path / "china" / "index.db")
    overseas_url = postgres_url_for_path(tmp_path / "overseas" / "index.db")
    config_path = _runtime_config(tmp_path)
    _seed_site(china_url, "china", explanation=False)
    _seed_site(overseas_url, "overseas", snapshot_id="weekly-overseas-old")
    _db_path, site_config_path, _site_config = _write_weekly_config(
        tmp_path, db_path=tmp_path / "china" / "index.db"
    )
    monkeypatch.setenv("CONFIG_PATH", str(site_config_path))
    monkeypatch.setenv("DATABASE_URL", china_url)
    generator = FakeWeeklyExplanationGenerator()
    generated = weekly_explanations.generate_weekly_explanation(
        db_path=china_url,
        snapshot_id=SNAPSHOT_ID,
        generator=generator,
    )
    assert generated["status"] == "complete"
    assert len(generator.calls) == 1
    invoke = _invoke_for_databases(
        {"china": china_url, "overseas": overseas_url}, lose_overseas_ack=True
    )
    with pytest.raises(RuntimeError, match="lost acknowledgement"):
        relay.run_weekly_publication(
            "sync",
            config_path=config_path,
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            wait_seconds=0,
            invoke=invoke,
        )
    state_path = tmp_path / "state" / "weekly-publication-state.json"
    old_digest = json.loads(state_path.read_text(encoding="utf-8"))["pending"]["bundle_sha256"]

    storage = Storage(china_url)
    try:
        previous_guide = storage.get_weekly_explanation(snapshot_id=SNAPSHOT_ID)
    finally:
        storage.close()
    assert previous_guide
    _set_catalog_prefix(china_url, "China revised")
    revision_generator = FakeWeeklyExplanationGenerator()
    revised = weekly_explanations.generate_weekly_explanation(
        db_path=china_url,
        snapshot_id=SNAPSHOT_ID,
        generator=revision_generator,
        force=True,
    )
    assert revised["status"] == "complete"
    assert len(revision_generator.calls) == 1
    assert "China revised" in revision_generator.calls[0]["messages"][-1]["content"]
    storage = Storage(china_url)
    try:
        revised_guide = storage.get_weekly_explanation(snapshot_id=SNAPSHOT_ID)
    finally:
        storage.close()
    assert revised_guide
    assert revised_guide["generated_at"] > previous_guide["generated_at"]

    result = relay.run_weekly_publication(
        "sync",
        config_path=config_path,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        wait_seconds=0,
        invoke=invoke,
    )
    assert result["status"] == "succeeded"
    assert result["bundle_sha256"] != old_digest
    assert len(generator.calls) == 1
    assert len(revision_generator.calls) == 1
    for database_url in (china_url, overseas_url):
        storage = Storage(database_url)
        try:
            guide = storage.get_weekly_explanation(snapshot_id=SNAPSHOT_ID)
            snapshot = storage.get_weekly_snapshot(snapshot_id=SNAPSHOT_ID, include_detail=True)
            assert guide
            assert snapshot
            assert guide["explanation_zh"] == revised_guide["explanation_zh"]
            assert guide["explanation_en"] == revised_guide["explanation_en"]
            assert snapshot["metadata"]["weekly_recommendation_cards_v1_owner"] == {
                "snapshot_id": SNAPSHOT_ID,
                "guide_generated_at": revised_guide["generated_at"],
            }
            assert snapshot["metadata"]["weekly_recommendation_cards_v1"][0]["title"].startswith(
                "China revised base title"
            )
        finally:
            storage.close()


def test_failed_source_maintenance_audit_does_not_block_frozen_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    china_url = postgres_url_for_path(tmp_path / "china" / "index.db")
    overseas_url = postgres_url_for_path(tmp_path / "overseas" / "index.db")
    config_path = _runtime_config(tmp_path)
    _seed_site(china_url, "china", explanation=False)
    _seed_site(overseas_url, "overseas", snapshot_id="weekly-overseas-old")
    _db_path, site_config_path, _site_config = _write_weekly_config(
        tmp_path, db_path=tmp_path / "china" / "index.db"
    )
    monkeypatch.setenv("CONFIG_PATH", str(site_config_path))
    monkeypatch.setenv("DATABASE_URL", china_url)
    initial_generator = FakeWeeklyExplanationGenerator()
    initial = weekly_explanations.generate_weekly_explanation(
        db_path=china_url,
        snapshot_id=SNAPSHOT_ID,
        generator=initial_generator,
    )
    assert initial["status"] == "complete"
    invoke = _invoke_for_databases(
        {"china": china_url, "overseas": overseas_url}, lose_overseas_ack=True
    )
    with pytest.raises(RuntimeError, match="lost acknowledgement"):
        relay.run_weekly_publication(
            "sync",
            config_path=config_path,
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            wait_seconds=0,
            invoke=invoke,
        )
    state_path = tmp_path / "state" / "weekly-publication-state.json"
    frozen_digest = json.loads(state_path.read_text(encoding="utf-8"))["pending"]["bundle_sha256"]

    maintenance_generator = FakeWeeklyExplanationGenerator(
        [TimeoutError("source maintenance timed out"), TimeoutError("source maintenance timed out")]
    )
    maintained = weekly_explanations.generate_weekly_explanation(
        db_path=china_url,
        snapshot_id=SNAPSHOT_ID,
        generator=maintenance_generator,
        force=True,
    )
    assert maintained["status"] == "complete"
    assert len(maintenance_generator.calls) == 2
    storage = Storage(china_url)
    try:
        current = storage.get_weekly_explanation(snapshot_id=SNAPSHOT_ID)
    finally:
        storage.close()
    assert current
    assert current["generated_at"] == initial["generated_at"]
    assert current["explanation_zh"] == initial["explanation_zh"]
    assert current["explanation_en"] == initial["explanation_en"]
    assert current["coverage"]["last_failed_attempt"]["error"]

    result = relay.run_weekly_publication(
        "sync",
        config_path=config_path,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        wait_seconds=0,
        invoke=invoke,
    )
    assert result["status"] == "succeeded"
    assert result["bundle_sha256"] == frozen_digest
    assert len(initial_generator.calls) == 1
    assert len(maintenance_generator.calls) == 2
    storage = Storage(china_url)
    try:
        after = storage.get_weekly_explanation(snapshot_id=SNAPSHOT_ID)
        assert after and after["coverage"]["last_failed_attempt"]["error"]
    finally:
        storage.close()


def test_incomplete_or_tampered_weekly_bundle_is_rejected(tmp_path: Path) -> None:
    database_url = postgres_url_for_path(tmp_path / "china" / "index.db")
    _seed_site(database_url, "china")
    result = target_worker.export_weekly_publication(
        {
            "schema_version": 1,
            "target": "china",
            "period_start": PERIOD_START,
            "period_end": PERIOD_END,
        },
        storage_factory=lambda: Storage.open_read_only(database_url),
    )
    invalid = json.loads(json.dumps(result["bundle"]))
    invalid["explanation"]["explanation_zh"] = "guide without recommendations"
    with pytest.raises(ValueError, match="same distinct recommendations"):
        target_worker.validate_weekly_publication_bundle(invalid)
    missing_member_fields = json.loads(json.dumps(result["bundle"]))
    del missing_member_fields["snapshot"]["metadata"]["weekly_recommendation_cards_v1"][0][
        "first_seen"
    ]
    with pytest.raises(ValueError, match="projection is incomplete or unordered"):
        target_worker.validate_weekly_publication_bundle(missing_member_fields)
    with pytest.raises(ValueError, match="SHA-256"):
        target_worker.apply_weekly_publication(
            {
                "schema_version": 1,
                "target": "overseas",
                "mode": "import_replica",
                "bundle": result["bundle"],
                "bundle_sha256": "0" * 64,
            },
            storage_factory=lambda: Storage(database_url),
        )


def test_due_period_supports_tuesday_catch_up_and_skips_the_sunday_pre_slot(
    tmp_path: Path,
) -> None:
    assert relay._auto_due_period(datetime(2026, 11, 3, 12, tzinfo=timezone.utc)) == (
        PERIOD_START,
        PERIOD_END,
    )
    assert relay._auto_due_period(datetime(2026, 11, 2, 0, 20, tzinfo=timezone.utc)) is None
    assert relay._auto_due_period(datetime(2026, 11, 8, 23, 30, tzinfo=timezone.utc)) is None

    def unexpected_export(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("pre-slot inspection must not infer a new publication period")

    result = relay.run_weekly_publication(
        "sync",
        config_path=_runtime_config(tmp_path),
        wait_seconds=0,
        now=datetime(2026, 11, 8, 23, 30, tzinfo=timezone.utc),
        invoke=unexpected_export,
    )
    assert result["status"] == "not_due"


def test_failed_target_transaction_preserves_previous_published_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    china_url = postgres_url_for_path(tmp_path / "china" / "index.db")
    overseas_url = postgres_url_for_path(tmp_path / "overseas" / "index.db")
    _seed_site(china_url, "china")
    _seed_site(overseas_url, "overseas", snapshot_id="weekly-overseas-old")
    exported = target_worker.export_weekly_publication(
        {
            "schema_version": 1,
            "target": "china",
            "period_start": PERIOD_START,
            "period_end": PERIOD_END,
        },
        storage_factory=lambda: Storage.open_read_only(china_url),
    )

    def fail_before_explanation(_connection: Any, _explanation: dict[str, Any]) -> None:
        raise RuntimeError("injected guide insert failure")

    monkeypatch.setattr(target_worker, "_weekly_insert_explanation", fail_before_explanation)
    with pytest.raises(RuntimeError, match="guide insert failure"):
        target_worker.apply_weekly_publication(
            {
                "schema_version": 1,
                "target": "overseas",
                "mode": "import_replica",
                "bundle": exported["bundle"],
                "bundle_sha256": exported["bundle_sha256"],
            },
            storage_factory=lambda: Storage(overseas_url),
        )
    storage = Storage(overseas_url)
    try:
        published, total = storage.list_weekly_snapshots(limit=20)
        same_period = [row for row in published if row["period_start"] == PERIOD_START]
        assert total == 1
        assert [row["id"] for row in same_period] == ["weekly-overseas-old"]
        assert storage.get_weekly_snapshot(snapshot_id=SNAPSHOT_ID) is None
        old_guide = storage.get_weekly_explanation(snapshot_id="weekly-overseas-old")
        assert old_guide and old_guide["status"] == "complete"
    finally:
        storage.close()


@pytest.mark.parametrize("article_state", ["missing", "deleted"])
def test_missing_recommendation_article_keeps_old_pair_and_pending_until_delivered(
    tmp_path: Path, article_state: str
) -> None:
    china_url = postgres_url_for_path(tmp_path / "china" / "index.db")
    overseas_url = postgres_url_for_path(tmp_path / "overseas" / "index.db")
    config_path = _runtime_config(tmp_path)
    _seed_site(china_url, "china")
    _seed_site(overseas_url, "overseas", snapshot_id="weekly-overseas-old")
    recommendation_url = "https://example.org/weekly-0.pdf"
    target = Storage(overseas_url)
    try:
        if article_state == "missing":
            target._conn.execute("DELETE FROM files WHERE url = ?", (recommendation_url,))
        else:
            target._conn.execute(
                "UPDATE files SET deleted_at = ? WHERE url = ?",
                (datetime.now(timezone.utc).isoformat(), recommendation_url),
            )
        target._conn.commit()
    finally:
        target.close()

    invoke = _invoke_for_databases({"china": china_url, "overseas": overseas_url})
    with pytest.raises(ValueError, match="missing a non-deleted article row"):
        relay.run_weekly_publication(
            "sync",
            config_path=config_path,
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            wait_seconds=0,
            invoke=invoke,
        )

    state_path = tmp_path / "state" / "weekly-publication-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["pending"]["acks"]["china"]["target"] == "china"
    assert "overseas" not in state["pending"]["acks"]
    target = Storage(overseas_url)
    try:
        published, total = target.list_weekly_snapshots(limit=20)
        assert total == 1
        assert [item["id"] for item in published] == ["weekly-overseas-old"]
        assert target.get_weekly_snapshot(snapshot_id=SNAPSHOT_ID) is None
    finally:
        target.close()

    target = Storage(overseas_url)
    try:
        target.upsert_file(
            url=recommendation_url,
            sha256="overseas-article-redelivered",
            title="Weekly article redelivered",
            source_site="test-source",
            source_page_url="https://example.org/weekly",
            original_filename="weekly-0.pdf",
            local_path="/tmp/overseas-redelivered-weekly-0.pdf",
            bytes_size=100,
            content_type="application/pdf",
            last_modified=None,
            etag=None,
            published_time=None,
        )
        if article_state == "deleted":
            with target.transaction(immediate=True):
                target._conn.execute(
                    "UPDATE files SET deleted_at = NULL WHERE url = ?", (recommendation_url,)
                )
    finally:
        target.close()

    result = relay.run_weekly_publication(
        "sync",
        config_path=config_path,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        wait_seconds=0,
        invoke=invoke,
    )
    assert result["status"] == "succeeded"
    target = Storage(overseas_url)
    try:
        published, total = target.list_weekly_snapshots(limit=20)
        same_period = [item for item in published if item["period_start"] == PERIOD_START]
        assert total == 1
        assert [item["id"] for item in same_period] == [SNAPSHOT_ID]
        assert target.get_weekly_explanation(snapshot_id=SNAPSHOT_ID)["status"] == "complete"
    finally:
        target.close()
