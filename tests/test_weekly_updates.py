from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from ai_actuarial.api.app import create_app
from ai_actuarial.api.services.weekly_updates import generate_weekly_update_summary, previous_utc_iso_week_period
from ai_actuarial.storage import Storage
from ai_actuarial.task_runtime import NativeTaskRuntime


PERIOD_START = "2026-03-09T00:00:00+00:00"
PERIOD_END = "2026-03-16T00:00:00+00:00"


def _write_config(tmp_path: Path) -> tuple[Path, Path]:
    db_path = tmp_path / "index.db"
    config_path = tmp_path / "sites.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "paths": {
                    "db": str(db_path),
                    "download_dir": str(tmp_path / "files"),
                    "updates_dir": str(tmp_path / "updates"),
                },
                "defaults": {"file_exts": [".pdf"]},
                "sites": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return db_path, config_path


def _seed_weekly_files(db_path: Path) -> None:
    storage = Storage(str(db_path))
    try:
        storage.insert_file(
            url="https://old-first-seen.example/old.pdf",
            sha256="hash-old",
            title="Old First Seen",
            source_site="old-first-seen.example",
            source_page_url="https://old-first-seen.example",
            original_filename="old.pdf",
            local_path="/tmp/old.pdf",
            bytes=100,
            content_type="application/pdf",
        )
        storage.insert_file(
            url="https://current-first-seen.example/current.pdf",
            sha256="hash-current",
            title="Current First Seen",
            source_site="current-first-seen.example",
            source_page_url="https://current-first-seen.example",
            original_filename="current.pdf",
            local_path="/tmp/current.pdf",
            bytes=200,
            content_type="application/pdf",
        )
        storage.upsert_catalog_item(
            item={
                "url": "https://current-first-seen.example/current.pdf",
                "sha256": "hash-current",
                "keywords": ["weekly"],
                "summary": "Current file summary",
                "category": "Pricing",
            },
            pipeline_version="v1",
            status="ok",
        )
        storage._conn.execute(
            "UPDATE files SET first_seen = ?, last_seen = ? WHERE url = ?",
            (
                "2026-03-01T12:00:00+00:00",
                "2026-03-10T12:00:00+00:00",
                "https://old-first-seen.example/old.pdf",
            ),
        )
        storage._conn.execute(
            "UPDATE files SET first_seen = ?, last_seen = ? WHERE url = ?",
            (
                "2026-03-10T08:00:00+00:00",
                "2026-03-10T08:00:00+00:00",
                "https://current-first-seen.example/current.pdf",
            ),
        )
        storage._conn.commit()
    finally:
        storage.close()


def test_weekly_summary_uses_first_seen_not_last_seen(tmp_path: Path) -> None:
    db_path, _config_path = _write_config(tmp_path)
    _seed_weekly_files(db_path)

    summary = generate_weekly_update_summary(
        db_path=str(db_path),
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )

    assert summary["file_count"] == 1
    assert [item["url"] for item in summary["files"]] == ["https://current-first-seen.example/current.pdf"]
    assert summary["files"][0]["summary"] == "Current file summary"
    assert summary["metadata"]["content_change_detection"] is False
    assert "files.first_seen" in summary["metadata"]["logic"]


def test_previous_utc_iso_week_period_returns_completed_iso_week() -> None:
    start, end = previous_utc_iso_week_period(datetime(2026, 3, 18, 12, tzinfo=timezone.utc))

    assert start == "2026-03-09T00:00:00+00:00"
    assert end == "2026-03-16T00:00:00+00:00"


def test_weekly_updates_api_lists_summaries_and_empty_latest(tmp_path: Path, monkeypatch) -> None:
    db_path, config_path = _write_config(tmp_path)
    _seed_weekly_files(db_path)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)

    client = TestClient(create_app())

    empty_latest = client.get("/api/weekly-updates/latest")
    assert empty_latest.status_code == 200
    assert empty_latest.json() == {"summary": None}

    generate_weekly_update_summary(
        db_path=str(db_path),
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )

    latest = client.get("/api/weekly-updates/latest")
    assert latest.status_code == 200
    assert latest.json()["summary"]["file_count"] == 1

    listing = client.get("/api/weekly-updates?limit=10")
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    assert body["summaries"][0]["period_start"] == PERIOD_START


def test_weekly_updates_api_is_public_readable_when_auth_required(tmp_path: Path, monkeypatch) -> None:
    _db_path, config_path = _write_config(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("REQUIRE_AUTH", "true")

    client = TestClient(create_app())
    response = client.get("/api/weekly-updates/latest")
    assert response.status_code == 200
    assert response.json() == {"summary": None}


def test_native_task_runtime_runs_weekly_summary(tmp_path: Path, monkeypatch) -> None:
    db_path, config_path = _write_config(tmp_path)
    _seed_weekly_files(db_path)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))

    runtime = NativeTaskRuntime()
    result = runtime._run_collection(
        "task-weekly-summary",
        "weekly_summary",
        {"period_start": PERIOD_START, "period_end": PERIOD_END, "relative_period": "previous_week"},
    )

    assert result.success is True
    assert result.items_found == 1
    assert result.metadata["file_count"] == 1

    storage = Storage(str(db_path))
    try:
        latest = storage.get_latest_weekly_update_summary()
    finally:
        storage.close()
    assert latest is not None
    assert latest["files"][0]["url"] == "https://current-first-seen.example/current.pdf"
    assert latest["metadata"]["relative_period"] == "previous_week"


def test_native_task_runtime_weekly_summary_clamps_invalid_max_files(tmp_path: Path, monkeypatch) -> None:
    db_path, config_path = _write_config(tmp_path)
    _seed_weekly_files(db_path)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))

    runtime = NativeTaskRuntime()
    result = runtime._run_collection(
        "task-weekly-summary-invalid-max",
        "weekly_summary",
        {"period_start": PERIOD_START, "period_end": PERIOD_END, "max_files": "not-a-number"},
    )

    assert result.success is True
    assert result.items_found == 1


def test_default_config_includes_previous_weekly_summary_schedule() -> None:
    config_path = Path(__file__).resolve().parents[1] / "config" / "sites.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    task = next(task for task in config.get("scheduled_tasks", []) if task.get("name") == "Weekly Update Summary")

    assert task["type"] == "weekly_summary"
    assert task["interval"] == "weekly"
    assert task["enabled"] is True
    assert task["params"]["relative_period"] == "previous_week"
    assert task["params"]["max_files"] == 500


def test_generate_weekly_summary_can_reuse_existing_storage(tmp_path: Path) -> None:
    db_path, _config_path = _write_config(tmp_path)
    _seed_weekly_files(db_path)
    storage = Storage(str(db_path))
    try:
        summary = generate_weekly_update_summary(
            db_path=str(db_path),
            storage=storage,
            period_start=PERIOD_START,
            period_end=PERIOD_END,
        )
        assert summary["file_count"] == 1
        assert storage.get_latest_weekly_update_summary() is not None
    finally:
        storage.close()
