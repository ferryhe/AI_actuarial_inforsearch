from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml
from fastapi.testclient import TestClient

from ai_actuarial import cli, task_runtime
from ai_actuarial.api.app import create_app
from ai_actuarial.api.route_inventory import _iter_routes
from ai_actuarial.api.services import weekly_updates
from ai_actuarial.sqlite_schema import (
    CURRENT_SQLITE_SCHEMA_VERSION,
    SchemaMigrationError,
    apply_schema,
    schema_plan,
    schema_status,
)
from ai_actuarial.storage import Storage
from ai_actuarial.task_runtime import NativeTaskRuntime

PERIOD_START = "2026-03-09T00:00:00+00:00"
PERIOD_END = "2026-03-16T00:00:00+00:00"


def _write_config(
    tmp_path: Path, *, scheduled_tasks: list[dict[str, object]] | None = None
) -> tuple[Path, Path]:
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
                "scheduled_tasks": list(scheduled_tasks or []),
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    Storage(str(db_path)).close()
    return db_path, config_path


def _seed_files(
    db_path: Path, count: int, *, first_seen: str = "2026-03-10T08:00:00+00:00"
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO files (
                url, sha256, title, original_filename, first_seen, last_seen,
                content_type, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'application/pdf', NULL)
            """,
            (
                (
                    f"https://example.com/report-{index:05d}.pdf",
                    f"hash-{index:05d}",
                    f"Report {index:05d}",
                    f"report-{index:05d}.pdf",
                    first_seen,
                    first_seen,
                )
                for index in range(count)
            ),
        )


def _downgrade_to_v10(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE weekly_explanations")
        conn.execute("DROP TABLE weekly_snapshot_members")
        conn.execute("DROP TABLE weekly_snapshots")
        conn.execute("DROP INDEX idx_global_chunks_stats_metadata")
        conn.execute("DROP INDEX idx_chunk_embeddings_stats_metadata")
        conn.execute("DROP TABLE markdown_terminal_source_state")
        conn.execute("PRAGMA user_version=10")


def _insert_legacy_summary(
    db_path: Path,
    *,
    summary_id: str,
    period_start: str,
    period_end: str,
    generated_at: str,
    files: list[dict[str, object]] | None = None,
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO weekly_update_summaries (
                id, period_start, period_end, generated_at, file_count,
                files_json, summary_markdown, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary_id,
                period_start,
                period_end,
                generated_at,
                len(files or []),
                json.dumps(files or []),
                f"# {summary_id}",
                json.dumps({"legacy": True}),
            ),
        )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"period_start": PERIOD_START},
        {"period_end": PERIOD_END},
        {"relative_period": "current_week"},
        {"relative_period": "previous_iso_week"},
        {
            "relative_period": "previous_week",
            "period_start": PERIOD_START,
            "period_end": PERIOD_END,
        },
        {"period_start": "2026-03-09T00:00:00", "period_end": PERIOD_END},
        {"period_start": "2026-03-09", "period_end": PERIOD_END},
        {"period_start": "not-a-time", "period_end": PERIOD_END},
        {"period_start": PERIOD_END, "period_end": PERIOD_START},
        {"period_start": PERIOD_START, "period_end": PERIOD_START},
    ],
)
def test_period_validator_rejects_invalid_or_mixed_selectors(payload: dict[str, str]) -> None:
    with pytest.raises(weekly_updates.WeeklySnapshotValidationError):
        weekly_updates.validate_weekly_snapshot_period(**payload)


def test_period_validator_normalizes_explicit_rfc3339_and_previous_iso_week() -> None:
    explicit = weekly_updates.validate_weekly_snapshot_period(
        period_start="2026-03-08T19:00:00-05:00",
        period_end="2026-03-15T20:00:00-04:00",
    )
    lower_case_rfc3339 = weekly_updates.validate_weekly_snapshot_period(
        period_start="2026-03-09t00:00:00z",
        period_end="2026-03-16t00:00:00z",
    )
    relative = weekly_updates.validate_weekly_snapshot_period(
        relative_period="previous_week",
        now=datetime(2026, 3, 18, 12, tzinfo=timezone.utc),
    )

    assert explicit.period_start == PERIOD_START
    assert explicit.period_end == PERIOD_END
    assert explicit.relative_period is None
    assert lower_case_rfc3339.period_start == PERIOD_START
    assert lower_case_rfc3339.period_end == PERIOD_END
    assert relative.period_start == PERIOD_START
    assert relative.period_end == PERIOD_END
    assert relative.relative_period == "previous_week"


def test_independent_count_preview_pagination_and_empty_period(tmp_path: Path) -> None:
    db_path, _config_path = _write_config(tmp_path)
    _seed_files(db_path, 12_345)
    statements: list[str] = []
    storage = Storage(str(db_path))
    storage._conn.set_trace_callback(statements.append)
    try:
        generated = weekly_updates.generate_weekly_update_summary(
            db_path=str(db_path),
            storage=storage,
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            max_files=500,
        )
    finally:
        storage.close()

    assert generated["file_count"] == 12_345
    assert len(generated["files"]) == 500
    assert generated["included_count"] == 500
    assert generated["truncated"] is True
    assert any(
        "count(*)" in statement.lower() and "from files" in statement.lower()
        for statement in statements
    )

    page = weekly_updates.get_weekly_update_summary_files(
        db_path=str(db_path),
        snapshot_id=generated["id"],
        limit=500,
        offset=12_000,
    )
    assert page["total"] == 12_345
    assert page["included_count"] == 345
    assert page["truncated"] is False

    empty = weekly_updates.generate_weekly_update_summary(
        db_path=str(db_path),
        period_start="2026-03-16T00:00:00+00:00",
        period_end="2026-03-23T00:00:00+00:00",
    )
    assert empty["file_count"] == 0
    assert empty["files"] == []
    assert empty["included_count"] == 0
    assert empty["truncated"] is False


def test_replay_force_and_failed_force_preserve_publication_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, _config_path = _write_config(tmp_path)
    _seed_files(db_path, 1)
    generated_times = iter(
        [
            "2026-03-18T12:00:00+00:00",
            "2026-03-18T13:00:00+00:00",
            "2026-03-18T14:00:00+00:00",
        ]
    )
    monkeypatch.setattr(Storage, "now", lambda _self: next(generated_times))

    first = weekly_updates.generate_weekly_update_summary(
        db_path=str(db_path),
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO files (
                url, sha256, title, original_filename, first_seen, last_seen,
                content_type, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'application/pdf', NULL)
            """,
            (
                "https://example.com/backdated.pdf",
                "hash-backdated",
                "Backdated",
                "backdated.pdf",
                "2026-03-11T08:00:00+00:00",
                "2026-03-11T08:00:00+00:00",
            ),
        )
    replay = weekly_updates.generate_weekly_update_summary(
        db_path=str(db_path),
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    forced = weekly_updates.generate_weekly_update_summary(
        db_path=str(db_path),
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        force=True,
    )

    assert replay["id"] == first["id"]
    assert replay["generated_at"] == first["generated_at"]
    assert replay["file_count"] == first["file_count"] == 1
    assert len(replay["files"]) == 1
    assert forced["id"] != first["id"]
    assert forced["generated_at"] != first["generated_at"]
    assert forced["file_count"] == 2

    failing_storage = Storage(str(db_path))
    try:
        failing_storage._conn.execute("""
            CREATE TRIGGER fail_weekly_member_insert
            BEFORE INSERT ON weekly_snapshot_members
            BEGIN
                SELECT RAISE(ABORT, 'simulated publication failure');
            END
            """)
        failing_storage._conn.commit()
        with pytest.raises(sqlite3.IntegrityError, match="simulated publication failure"):
            weekly_updates.generate_weekly_update_summary(
                db_path=str(db_path),
                storage=failing_storage,
                period_start=PERIOD_START,
                period_end=PERIOD_END,
                force=True,
            )
        failing_storage._conn.execute("DROP TRIGGER fail_weekly_member_insert")
        failing_storage._conn.commit()
    finally:
        failing_storage.close()

    latest = weekly_updates.get_latest_weekly_update_summary(db_path=str(db_path))["summary"]
    assert latest["id"] == forced["id"]
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, status FROM weekly_snapshots WHERE period_start = ? AND period_end = ?",
            (PERIOD_START, PERIOD_END),
        ).fetchall()
    assert sum(status == "published" for _snapshot_id, status in rows) == 1
    assert {status for _snapshot_id, status in rows} == {"published", "superseded"}


def test_concurrent_same_period_generation_publishes_one_identity(tmp_path: Path) -> None:
    db_path, _config_path = _write_config(tmp_path)
    _seed_files(db_path, 20)

    def generate() -> dict[str, object]:
        return weekly_updates.generate_weekly_update_summary(
            db_path=str(db_path),
            period_start=PERIOD_START,
            period_end=PERIOD_END,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _index: generate(), range(8)))

    assert len({row["id"] for row in results}) == 1
    assert len({row["generated_at"] for row in results}) == 1
    with sqlite3.connect(db_path) as conn:
        successful = conn.execute(
            """
            SELECT COUNT(*) FROM weekly_snapshots
            WHERE period_start = ? AND period_end = ? AND status = 'published'
            """,
            (PERIOD_START, PERIOD_END),
        ).fetchone()[0]
    assert successful == 1


def test_snapshot_member_title_is_resolved_live_with_safe_fallbacks(tmp_path: Path) -> None:
    db_path, _config_path = _write_config(tmp_path)
    _seed_files(db_path, 1)
    generated = weekly_updates.generate_weekly_update_summary(
        db_path=str(db_path),
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE files SET title = 'Edited Canonical Title' WHERE url = ?",
            ("https://example.com/report-00000.pdf",),
        )
    page = weekly_updates.get_weekly_update_summary_files(
        db_path=str(db_path),
        snapshot_id=generated["id"],
        limit=20,
        offset=0,
    )
    assert page["files"][0]["title"] == "Edited Canonical Title"
    assert page["files"][0]["first_seen"] == "2026-03-10T08:00:00+00:00"
    assert set(page["files"][0]) == {
        "url",
        "title",
        "original_filename",
        "first_seen",
        "category",
        "keywords",
        "summary",
    }

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE files SET title = NULL, original_filename = NULL WHERE url = ?",
            ("https://example.com/report-00000.pdf",),
        )
    fallback = weekly_updates.get_weekly_update_summary_files(
        db_path=str(db_path),
        snapshot_id=generated["id"],
        limit=20,
        offset=0,
    )
    assert fallback["files"][0]["title"] == "report-00000.pdf"


def test_api_list_latest_detail_and_files_are_typed_and_lightweight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path, config_path = _write_config(tmp_path)
    _seed_files(db_path, 2)
    current = weekly_updates.generate_weekly_update_summary(
        db_path=str(db_path),
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    weekly_updates.generate_weekly_update_summary(
        db_path=str(db_path),
        period_start="2099-03-09T00:00:00+00:00",
        period_end="2099-03-16T00:00:00+00:00",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("REQUIRE_AUTH", "false")
    app = create_app()
    client = TestClient(app)

    listing = client.get("/api/weekly-updates?limit=10&offset=0")
    latest = client.get("/api/weekly-updates/latest")
    detail = client.get(f"/api/weekly-updates/{current['id']}")
    files = client.get(f"/api/weekly-updates/{current['id']}/files?limit=1&offset=0")

    assert (
        listing.status_code == latest.status_code == detail.status_code == files.status_code == 200
    )
    assert all("files" not in summary for summary in listing.json()["summaries"])
    assert "files" not in latest.json()["summary"]
    assert "files" not in detail.json()["summary"]
    assert latest.json()["summary"]["id"] == current["id"]
    assert files.json()["total"] == 2
    assert files.json()["included_count"] == 1
    assert files.json()["truncated"] is True

    typed_paths = {
        "/api/weekly-updates",
        "/api/weekly-updates/latest",
        "/api/weekly-updates/{snapshot_id}",
        "/api/weekly-updates/{snapshot_id}/files",
    }
    routes = {
        path: route for route, path, _include_in_schema in _iter_routes(app.router.routes) if path
    }
    assert all(routes[path].response_model is not None for path in typed_paths)


def test_snapshot_list_and_latest_use_declared_list_index(tmp_path: Path) -> None:
    db_path, _config_path = _write_config(tmp_path)
    period_start = datetime(2020, 1, 6, tzinfo=timezone.utc)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO weekly_snapshots (
                id, period_start, period_end, generated_at, status
            ) VALUES (?, ?, ?, ?, 'published')
            """,
            (
                (
                    f"snapshot-{week}",
                    (period_start + timedelta(weeks=week)).isoformat(),
                    (period_start + timedelta(weeks=week + 1)).isoformat(),
                    (period_start + timedelta(weeks=week + 1, hours=1)).isoformat(),
                )
                for week in range(200)
            ),
        )

    storage = Storage(str(db_path))
    statements: list[str] = []
    try:
        storage._conn.execute("ANALYZE")
        storage._conn.set_trace_callback(statements.append)
        storage.list_weekly_snapshots(limit=20, offset=0)
        storage.get_latest_weekly_snapshot(
            now="2030-01-01T00:00:00+00:00",
        )
        storage._conn.set_trace_callback(None)
        queries = [
            statement
            for statement in statements
            if statement.lstrip().startswith("SELECT id, period_start")
            and "FROM weekly_snapshots" in statement
        ]
        plans = [
            [str(row[3]) for row in storage._conn.execute(f"EXPLAIN QUERY PLAN {query}")]
            for query in queries
        ]
    finally:
        storage._conn.set_trace_callback(None)
        storage.close()

    assert len(plans) == 2
    for plan in plans:
        assert any("USING INDEX idx_weekly_snapshots_list" in detail for detail in plan)
        assert all("USE TEMP B-TREE FOR ORDER BY" not in detail for detail in plan)


def test_async_weekly_run_validates_and_normalizes_before_enqueue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _db_path, config_path = _write_config(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("REQUIRE_AUTH", "false")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_TOKEN", "issue-266-test-token")
    app = create_app()
    started: list[tuple[str, dict[str, object]]] = []

    def start_background_task(
        collection_type: str,
        data: dict[str, object],
        **_kwargs: object,
    ) -> str:
        started.append((collection_type, dict(data)))
        return "weekly-task"

    app.state.start_background_task = start_background_task
    client = TestClient(app)
    headers = {"X-Auth-Token": "issue-266-test-token"}
    invalid = client.post(
        "/api/collections/run",
        json={
            "name": "Invalid Weekly",
            "type": "weekly_summary",
            "relative_period": "previous_week",
            "period_start": PERIOD_START,
            "period_end": PERIOD_END,
        },
        headers=headers,
    )
    assert invalid.status_code == 400
    assert started == []

    valid = client.post(
        "/api/collections/run",
        json={
            "name": "Valid Weekly",
            "type": "weekly_summary",
            "period_start": "2026-03-08T19:00:00-05:00",
            "period_end": "2026-03-15T20:00:00-04:00",
        },
        headers=headers,
    )
    assert valid.status_code == 200
    assert started == [
        (
            "weekly_summary",
            {
                "name": "Valid Weekly",
                "type": "weekly_summary",
                "period_start": PERIOD_START,
                "period_end": PERIOD_END,
            },
        )
    ]


def _run_weekly_cli(argv: list[str], capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    args = cli.build_parser().parse_args(argv)
    assert args.func(args) == 0
    return json.loads(capsys.readouterr().out)


def test_weekly_snapshot_cli_json_parity_replay_force_and_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path, config_path = _write_config(tmp_path)
    _seed_files(db_path, 3)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("REQUIRE_AUTH", "false")
    generated = _run_weekly_cli(
        [
            "weekly",
            "snapshot",
            "generate",
            "--db",
            str(db_path),
            "--period-start",
            PERIOD_START,
            "--period-end",
            PERIOD_END,
            "--json",
        ],
        capsys,
    )
    replay = _run_weekly_cli(
        [
            "weekly",
            "snapshot",
            "generate",
            "--db",
            str(db_path),
            "--period-start",
            PERIOD_START,
            "--period-end",
            PERIOD_END,
            "--json",
        ],
        capsys,
    )
    api_response = TestClient(create_app()).get("/api/weekly-updates/latest")
    assert api_response.status_code == 200
    api_latest = api_response.json()["summary"]
    assert generated["id"] == replay["id"] == api_latest["id"]
    assert generated["generated_at"] == replay["generated_at"]
    assert generated["file_count"] == api_latest["file_count"] == 3
    assert (generated["period_start"], generated["period_end"]) == (
        api_latest["period_start"],
        api_latest["period_end"],
    )

    forced = _run_weekly_cli(
        [
            "weekly",
            "snapshot",
            "generate",
            "--db",
            str(db_path),
            "--period-start",
            PERIOD_START,
            "--period-end",
            PERIOD_END,
            "--force",
            "--json",
        ],
        capsys,
    )
    assert forced["id"] != generated["id"]
    latest = _run_weekly_cli(
        ["weekly", "snapshot", "latest", "--db", str(db_path), "--json"],
        capsys,
    )
    listing = _run_weekly_cli(
        ["weekly", "snapshot", "list", "--db", str(db_path), "--json"],
        capsys,
    )
    files = _run_weekly_cli(
        [
            "weekly",
            "snapshot",
            "files",
            forced["id"],
            "--db",
            str(db_path),
            "--limit",
            "2",
            "--json",
        ],
        capsys,
    )
    assert latest["summary"]["id"] == forced["id"]
    assert listing["summaries"][0]["id"] == forced["id"]
    assert "files" not in latest["summary"]
    assert "files" not in listing["summaries"][0]
    assert files["total"] == 3
    assert files["included_count"] == 2
    assert files["truncated"] is True


@pytest.mark.parametrize("use_fallback_scheduler", [False, True], ids=["schedule", "fallback"])
def test_real_scheduler_registration_invokes_previous_week_snapshot_to_persistence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    use_fallback_scheduler: bool,
) -> None:
    scheduled_utc_run = datetime(2026, 8, 31, 0, 30, tzinfo=timezone.utc)
    production_local_run = datetime(2026, 8, 31, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai"))

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            if tz is None:
                return scheduled_utc_run.replace(tzinfo=None)
            return scheduled_utc_run.astimezone(tz)  # type: ignore[arg-type]

    monkeypatch.setattr(weekly_updates, "datetime", FrozenDateTime)
    start, end = weekly_updates.previous_utc_iso_week_period()
    one_week_early = weekly_updates.previous_utc_iso_week_period(production_local_run)
    assert (start, end) == (
        "2026-08-24T00:00:00+00:00",
        "2026-08-31T00:00:00+00:00",
    )
    assert one_week_early == (
        "2026-08-17T00:00:00+00:00",
        "2026-08-24T00:00:00+00:00",
    )
    db_path, _config_path = _write_config(
        tmp_path,
        scheduled_tasks=[
            {
                "name": "Weekly Update Summary",
                "type": "weekly_summary",
                "interval": "weekly",
                "enabled": True,
                "params": {"relative_period": "previous_week", "max_files": 500},
            }
        ],
    )
    _seed_files(db_path, 1, first_seen=start)
    runtime = NativeTaskRuntime(pipeline_baton_state_path=str(tmp_path / "pipeline.json"))
    if use_fallback_scheduler:
        runtime.scheduler = task_runtime._FallbackScheduler()
    runtime._scheduler_loop_started = True
    runtime.set_site_config(
        {
            "paths": {"db": str(db_path)},
            "scheduled_tasks": [
                {
                    "name": "Weekly Update Summary",
                    "type": "weekly_summary",
                    "interval": "weekly",
                    "enabled": True,
                    "params": {"relative_period": "previous_week", "max_files": 500},
                }
            ],
        }
    )
    results = []

    def run_now(collection_type: str, data: dict[str, object], **_kwargs: object) -> str:
        results.append(runtime._run_collection("scheduled-weekly", collection_type, dict(data)))
        return "scheduled-weekly"

    runtime.start_background_task = run_now  # type: ignore[method-assign]
    runtime.init_scheduler()
    weekly_job = next(
        job for job in runtime.scheduler.jobs if job.unit == "weeks" and job.start_day == "monday"
    )
    weekly_job.job_func()
    weekly_job.job_func()

    latest = weekly_updates.get_latest_weekly_update_summary(db_path=str(db_path))["summary"]
    assert len(results) == 2
    assert all(result.success for result in results)
    assert str(weekly_job.at_time_zone) == "UTC"
    assert (latest["period_start"], latest["period_end"]) == (start, end)
    assert (latest["period_start"], latest["period_end"]) != one_week_early
    assert latest["file_count"] == 1
    with sqlite3.connect(db_path) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM weekly_snapshots WHERE status = 'published'"
            ).fetchone()[0]
            == 1
        )


def test_v11_migration_backfills_legacy_weekly_rows_and_runner_agrees(tmp_path: Path) -> None:
    db_path, _config_path = _write_config(tmp_path)
    _seed_files(db_path, 1)
    legacy_files = [
        {
            "url": "https://example.com/report-00000.pdf",
            "title": "Legacy Title",
            "original_filename": "report-00000.pdf",
            "first_seen": "2026-03-10T08:00:00+00:00",
        }
    ]
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE IF EXISTS weekly_explanations")
        conn.execute("DROP TABLE IF EXISTS weekly_snapshot_members")
        conn.execute("DROP TABLE IF EXISTS weekly_snapshots")
        conn.execute("DROP INDEX idx_global_chunks_stats_metadata")
        conn.execute("DROP INDEX idx_chunk_embeddings_stats_metadata")
        conn.execute("DROP TABLE markdown_terminal_source_state")
        conn.execute(
            """
            INSERT INTO weekly_update_summaries (
                id, period_start, period_end, generated_at, file_count,
                files_json, summary_markdown, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-weekly-id",
                PERIOD_START,
                PERIOD_END,
                "2026-03-18T10:00:00+00:00",
                1,
                json.dumps(legacy_files),
                "# Legacy",
                json.dumps({"legacy": True}),
            ),
        )
        conn.execute("PRAGMA user_version=10")

    status = schema_status(db_path)
    plan = schema_plan(db_path)
    assert status["state"] == "needs_migration"
    assert status["database"]["user_version"] == 10
    assert [action["id"] for action in plan["plan"]["actions"]] == [
        "add_weekly_snapshots_v11",
        "add_weekly_explanations_v12",
        "add_chunk_stats_metadata_indexes_v13",
        "add_markdown_terminal_source_state_v14",
    ]

    applied = apply_schema(db_path)
    assert applied["state"] == "current"
    assert applied["applied_migrations"] == [
        "add_weekly_snapshots_v11",
        "add_weekly_explanations_v12",
        "add_chunk_stats_metadata_indexes_v13",
        "add_markdown_terminal_source_state_v14",
    ]
    with sqlite3.connect(db_path) as conn:
        legacy = conn.execute(
            "SELECT id, file_count, files_json FROM weekly_update_summaries WHERE id = ?",
            ("legacy-weekly-id",),
        ).fetchone()
    assert legacy == ("legacy-weekly-id", 1, json.dumps(legacy_files))

    detail = weekly_updates.get_weekly_update_summary_detail(
        db_path=str(db_path),
        snapshot_id="legacy-weekly-id",
    )["summary"]
    members = weekly_updates.get_weekly_update_summary_files(
        db_path=str(db_path),
        snapshot_id="legacy-weekly-id",
        limit=20,
        offset=0,
    )
    assert detail["file_count"] == 1
    assert detail["metadata"]["legacy"] is True
    assert members["files"][0]["url"] == "https://example.com/report-00000.pdf"
    assert members["files"][0]["first_seen"] == "2026-03-10T08:00:00+00:00"


def test_v11_migration_canonicalizes_offset_period_for_idempotent_replay(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "offset-replay.db"
    Storage(str(db_path)).close()
    _downgrade_to_v10(db_path)
    _insert_legacy_summary(
        db_path,
        summary_id="legacy-offset",
        period_start="2026-03-08T19:00:00-05:00",
        period_end="2026-03-15T20:00:00-04:00",
        generated_at="2026-03-18T10:00:00+00:00",
    )

    assert apply_schema(db_path)["state"] == "current"
    replay = weekly_updates.generate_weekly_update_summary(
        db_path=str(db_path),
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )

    assert replay["id"] == "legacy-offset"
    assert replay["generated_at"] == "2026-03-18T10:00:00+00:00"
    assert (replay["period_start"], replay["period_end"]) == (
        PERIOD_START,
        PERIOD_END,
    )
    with sqlite3.connect(db_path) as conn:
        published = conn.execute(
            "SELECT id, period_start, period_end FROM weekly_snapshots WHERE status = 'published'"
        ).fetchall()
        legacy_period = conn.execute(
            "SELECT period_start, period_end FROM weekly_update_summaries WHERE id = 'legacy-offset'"
        ).fetchone()
    assert published == [("legacy-offset", PERIOD_START, PERIOD_END)]
    assert legacy_period == (
        "2026-03-08T19:00:00-05:00",
        "2026-03-15T20:00:00-04:00",
    )


def test_v11_migration_resolves_normalized_period_collisions_deterministically(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "normalized-collision.db"
    Storage(str(db_path)).close()
    _downgrade_to_v10(db_path)
    _insert_legacy_summary(
        db_path,
        summary_id="later-offset-row",
        period_start="2026-03-08T19:00:00-05:00",
        period_end="2026-03-15T20:00:00-04:00",
        generated_at="2026-03-18T12:00:00+00:00",
    )
    _insert_legacy_summary(
        db_path,
        summary_id="earliest-publication",
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        generated_at="2026-03-18T09:00:00+00:00",
    )

    assert apply_schema(db_path)["state"] == "current"
    with sqlite3.connect(db_path) as conn:
        published = conn.execute("""
            SELECT id, period_start, period_end, generated_at
            FROM weekly_snapshots
            WHERE status = 'published'
            """).fetchall()
        legacy_count = conn.execute("SELECT COUNT(*) FROM weekly_update_summaries").fetchone()[0]

    assert published == [
        (
            "earliest-publication",
            PERIOD_START,
            PERIOD_END,
            "2026-03-18T09:00:00+00:00",
        )
    ]
    assert legacy_count == 2


def test_v10_source_rejects_preexisting_published_collision_before_migration(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "malformed-v10-published-collision.db"
    Storage(str(db_path)).close()
    _insert_legacy_summary(
        db_path,
        summary_id="later-offset-row",
        period_start="2026-03-08T19:00:00-05:00",
        period_end="2026-03-15T20:00:00-04:00",
        generated_at="2026-03-18T12:00:00+00:00",
    )
    _insert_legacy_summary(
        db_path,
        summary_id="deterministic-legacy-survivor",
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        generated_at="2026-03-18T09:00:00+00:00",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO weekly_snapshots (
                id, period_start, period_end, generated_at, status, file_count,
                summary_markdown, metadata_json
            ) VALUES (?, ?, ?, ?, 'published', 0, '', '{}')
            """,
            (
                "malformed-preexisting-snapshot",
                PERIOD_START,
                PERIOD_END,
                "2026-03-18T14:00:00+00:00",
            ),
        )
        conn.execute("PRAGMA user_version=10")

    status = schema_status(db_path)
    assert status["state"] == "invalid"
    assert status["can_apply"] is False
    with pytest.raises(SchemaMigrationError, match="not safe to migrate"):
        apply_schema(db_path)

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 10
        published = conn.execute(
            "SELECT id FROM weekly_snapshots WHERE status = 'published'"
        ).fetchall()
    assert published == [("malformed-preexisting-snapshot",)]


def test_v11_migration_skips_invalid_naive_and_reversed_legacy_periods(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "invalid-periods.db"
    Storage(str(db_path)).close()
    _downgrade_to_v10(db_path)
    legacy_file = [{"url": "https://example.com/legacy.pdf"}]
    _insert_legacy_summary(
        db_path,
        summary_id="malformed",
        period_start="not-a-time",
        period_end=PERIOD_END,
        generated_at="2026-03-18T09:00:00+00:00",
        files=legacy_file,
    )
    _insert_legacy_summary(
        db_path,
        summary_id="naive",
        period_start="2026-03-09T00:00:00",
        period_end="2026-03-16T00:00:00",
        generated_at="2026-03-18T10:00:00+00:00",
        files=legacy_file,
    )
    _insert_legacy_summary(
        db_path,
        summary_id="reversed",
        period_start=PERIOD_END,
        period_end=PERIOD_START,
        generated_at="2026-03-18T11:00:00+00:00",
        files=legacy_file,
    )

    assert apply_schema(db_path)["state"] == "current"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM weekly_update_summaries").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM weekly_snapshots").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM weekly_snapshot_members").fetchone()[0] == 0


def test_legacy_and_snapshot_lists_share_current_rows_without_double_counting(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "new-snapshots.db"
    Storage(str(db_path)).close()
    first = weekly_updates.generate_weekly_update_summary(
        db_path=str(db_path),
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )
    second = weekly_updates.generate_weekly_update_summary(
        db_path=str(db_path),
        period_start="2026-03-16T00:00:00+00:00",
        period_end="2026-03-23T00:00:00+00:00",
    )
    storage = Storage(str(db_path))
    try:
        legacy_page_1, legacy_total = storage.list_weekly_update_summaries(
            limit=1,
            offset=0,
        )
        legacy_page_2, legacy_total_2 = storage.list_weekly_update_summaries(
            limit=1,
            offset=1,
        )
        snapshots, snapshot_total = storage.list_weekly_snapshots(limit=10, offset=0)
    finally:
        storage.close()

    assert legacy_total == legacy_total_2 == snapshot_total == 2
    assert [legacy_page_1[0]["id"], legacy_page_2[0]["id"]] == [
        second["id"],
        first["id"],
    ]
    assert [row["id"] for row in snapshots] == [second["id"], first["id"]]
    assert set(legacy_page_1[0]) == {
        "id",
        "period_start",
        "period_end",
        "generated_at",
        "file_count",
        "files",
        "summary_markdown",
        "metadata",
    }

    migrated_db = tmp_path / "migrated-snapshot.db"
    Storage(str(migrated_db)).close()
    _downgrade_to_v10(migrated_db)
    _insert_legacy_summary(
        migrated_db,
        summary_id="migrated-once",
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        generated_at="2026-03-18T09:00:00+00:00",
    )
    apply_schema(migrated_db)
    migrated_storage = Storage(str(migrated_db))
    try:
        legacy_rows, legacy_total = migrated_storage.list_weekly_update_summaries()
        snapshot_rows, snapshot_total = migrated_storage.list_weekly_snapshots()
    finally:
        migrated_storage.close()
    assert legacy_total == snapshot_total == 1
    assert [row["id"] for row in legacy_rows] == ["migrated-once"]
    assert [row["id"] for row in snapshot_rows] == ["migrated-once"]


def test_legacy_latest_excludes_future_rows_and_keeps_ended_fallback(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy-latest.db"
    Storage(str(db_path)).close()
    _downgrade_to_v10(db_path)
    _insert_legacy_summary(
        db_path,
        summary_id="future-only",
        period_start="2099-03-09T00:00:00+00:00",
        period_end="2099-03-16T00:00:00+00:00",
        generated_at="2026-03-18T09:00:00+00:00",
    )
    apply_schema(db_path)

    storage = Storage(str(db_path))
    try:
        assert storage.get_latest_weekly_update_summary() is None
        _insert_legacy_summary(
            db_path,
            summary_id="ended-legacy",
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            generated_at="2026-03-18T10:00:00+00:00",
        )
        latest = storage.get_latest_weekly_update_summary()
    finally:
        storage.close()
    assert latest is not None
    assert latest["id"] == "ended-legacy"


def test_weekly_snapshot_cli_json_handles_sqlite_operational_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    directory_path = tmp_path / "sqlite-directory"
    directory_path.mkdir()
    args = cli.build_parser().parse_args(
        [
            "weekly",
            "snapshot",
            "latest",
            "--db",
            str(directory_path),
            "--json",
        ]
    )

    assert args.func(args) == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert json.loads(captured.out) == {
        "error": "unable to open database file",
        "success": False,
    }


def test_weekly_snapshot_cli_json_missing_id_uses_stable_domain_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path, _config_path = _write_config(tmp_path)
    args = cli.build_parser().parse_args(
        [
            "weekly",
            "snapshot",
            "files",
            "missing-id",
            "--db",
            str(db_path),
            "--json",
        ]
    )

    assert args.func(args) == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.count("\n") == 1
    assert json.loads(captured.out) == {
        "error": "Weekly snapshot not found",
        "success": False,
    }
