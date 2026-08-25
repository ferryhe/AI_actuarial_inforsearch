from __future__ import annotations

import sqlite3

from ai_actuarial.storage import Storage


def test_create_and_get_pipeline_run() -> None:
    storage = Storage(":memory:")
    try:
        storage.create_pipeline_run("run-1", correlation_id="corr-1", source_type="scheduled")
        run = storage.get_pipeline_run("run-1")
        assert run is not None
        assert run["run_id"] == "run-1"
        assert run["correlation_id"] == "corr-1"
        assert run["source_type"] == "scheduled"
        assert run["status"] == "pending"
        assert run["watermark"] == ""
        assert storage.get_pipeline_run("missing") is None
    finally:
        storage.close()


def test_start_pipeline_run_stamps_started_at() -> None:
    storage = Storage(":memory:")
    try:
        storage.create_pipeline_run("run-1")
        storage.start_pipeline_run("run-1")
        run = storage.get_pipeline_run("run-1")
        assert run is not None
        assert run["status"] == "running"
        assert run["started_at"]
    finally:
        storage.close()


def test_update_pipeline_run_fields() -> None:
    storage = Storage(":memory:")
    try:
        storage.create_pipeline_run("run-1")
        storage.update_pipeline_run(
            "run-1", status="failed", watermark="chunk_generation", error="boom", finished_at="2026-01-01T00:00:00+00:00"
        )
        run = storage.get_pipeline_run("run-1")
        assert run is not None
        assert run["status"] == "failed"
        assert run["watermark"] == "chunk_generation"
        assert run["error"] == "boom"
        assert run["finished_at"] == "2026-01-01T00:00:00+00:00"
    finally:
        storage.close()


def test_list_unfinished_pipeline_runs() -> None:
    storage = Storage(":memory:")
    try:
        storage.create_pipeline_run("run-pending")
        storage.create_pipeline_run("run-running")
        storage.start_pipeline_run("run-running")
        storage.create_pipeline_run("run-done")
        storage.update_pipeline_run("run-done", status="succeeded")

        unfinished = storage.list_unfinished_pipeline_runs()
        ids = {r["run_id"] for r in unfinished}
        assert ids == {"run-pending", "run-running"}
    finally:
        storage.close()


def test_upsert_and_get_pipeline_stages() -> None:
    storage = Storage(":memory:")
    try:
        storage.create_pipeline_run("run-1")
        storage.upsert_pipeline_stage("run-1", "acquisition", stage_order=1, options_json='{"sites": 2}')
        storage.upsert_pipeline_stage("run-1", "catalog", stage_order=2, options_json='{"model": "gpt-4o-mini"}')

        stages = storage.get_pipeline_stages("run-1")
        assert [s["stage_name"] for s in stages] == ["acquisition", "catalog"]
        assert stages[0]["options_json"] == '{"sites": 2}'
        assert stages[0]["status"] == "pending"
        assert stages[0]["retry_count"] == 0
        assert stages[0]["committed_artifacts_json"] == "[]"
    finally:
        storage.close()


def test_upsert_pipeline_stage_resets() -> None:
    storage = Storage(":memory:")
    try:
        storage.create_pipeline_run("run-1")
        storage.upsert_pipeline_stage("run-1", "catalog", stage_order=1, options_json='{"model": "a"}')
        # Re-upsert the same stage: fields reset to the new values.
        storage.upsert_pipeline_stage("run-1", "catalog", stage_order=1, options_json='{"model": "b"}')
        stages = storage.get_pipeline_stages("run-1")
        assert len(stages) == 1
        assert stages[0]["options_json"] == '{"model": "b"}'
    finally:
        storage.close()


def test_update_pipeline_stage_fields() -> None:
    storage = Storage(":memory:")
    try:
        storage.create_pipeline_run("run-1")
        storage.upsert_pipeline_stage("run-1", "catalog", stage_order=1)
        storage.update_pipeline_stage(
            "run-1",
            "catalog",
            status="succeeded",
            checkpoint_json='{"cursor": 5}',
            committed_artifacts_json='["a", "b"]',
            error="",
            retry_count=1,
        )
        stages = storage.get_pipeline_stages("run-1")
        stage = stages[0]
        assert stage["status"] == "succeeded"
        assert stage["checkpoint_json"] == '{"cursor": 5}'
        assert stage["committed_artifacts_json"] == '["a", "b"]'
        assert stage["retry_count"] == 1
    finally:
        storage.close()


def test_create_update_get_child_runs() -> None:
    storage = Storage(":memory:")
    try:
        storage.create_pipeline_run("parent-1", correlation_id="corr")
        storage.create_child_run("child-1", "parent-1", correlation_id="corr")
        storage.update_child_run("child-1", status="failed", partial=1, error="search failed")

        children = storage.get_child_runs("parent-1")
        assert len(children) == 1
        child = children[0]
        assert child["child_run_id"] == "child-1"
        assert child["parent_run_id"] == "parent-1"
        assert child["status"] == "failed"
        assert child["partial"] == 1
        assert child["error"] == "search failed"
    finally:
        storage.close()


def test_v5_migration_adds_pipeline_tables(tmp_path) -> None:
    from ai_actuarial.sqlite_schema import apply_schema

    db_path = str(tmp_path / "v4.db")
    storage = Storage(db_path)
    try:
        # Downgrade a fresh v5 DB back to v4: drop the pipeline tables and rewind.
        storage._conn.execute("DROP TABLE pipeline_run")
        storage._conn.execute("DROP TABLE pipeline_stage")
        storage._conn.execute("DROP TABLE child_run")
        storage._conn.execute("PRAGMA user_version=4")
        storage._conn.commit()
    finally:
        storage.close()

    result = apply_schema(db_path)
    assert result["state"] == "current"

    conn = sqlite3.connect(db_path)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"pipeline_run", "pipeline_stage", "child_run"} <= tables
    finally:
        conn.close()
