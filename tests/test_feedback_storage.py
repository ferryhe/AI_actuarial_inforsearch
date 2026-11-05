from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import psycopg2
import pytest

from ai_actuarial.feedback.store import (
    FeedbackConflict,
    FeedbackRequest,
    list_feedback,
    submit_feedback,
    update_feedback_status,
)
from ai_actuarial.postgres import (
    POSTGRES_SCHEMA_VERSION,
    initialize_postgresql_schema,
    postgresql_schema_plan,
    postgresql_schema_status,
)
from tests.postgres_helpers import postgres_url_for_path, uninitialized_postgres_url_for_path


def _request(**values):
    return FeedbackRequest.model_validate(
        {"client_request_id": str(uuid4()), "content": "请保留原文", **values}
    )


def test_empty_schema_apply_and_repeat_are_versioned_and_idempotent(tmp_path):
    database = uninitialized_postgres_url_for_path(tmp_path / "empty")
    assert postgresql_schema_status(database)["state"] == "empty"
    initialize_postgresql_schema(database)
    with psycopg2.connect(database) as connection, connection.cursor() as cursor:
        cursor.execute("SHOW server_version_num")
        assert 160000 <= int(cursor.fetchone()[0]) < 170000
    receipt = submit_feedback(database, _request(), site_key="test", user_id=None)
    initialize_postgresql_schema(database)
    assert postgresql_schema_plan(database)["plan"] == []
    with psycopg2.connect(database) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version FROM ai_actuarial_schema_migrations ORDER BY version")
        assert [row[0] for row in cursor] == list(range(1, POSTGRES_SCHEMA_VERSION + 1))
        cursor.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema() "
            "AND tablename = 'feedback_items'"
        )
        assert {
            "feedback_items_status_id",
            "feedback_items_site_id",
            "feedback_items_site_status_id",
        } <= {row[0] for row in cursor}
    assert list_feedback(database)["items"][0]["feedback_id"] == receipt["feedback_id"]


def test_upgrade_from_v6_preserves_every_existing_table_row(tmp_path):
    database = uninitialized_postgres_url_for_path(tmp_path / "upgrade")
    with psycopg2.connect(database) as connection, connection.cursor() as cursor:
        for path in sorted(Path("ai_actuarial/migrations").glob("*.sql")):
            version = int(path.name.split("_", 1)[0])
            if version > 6:
                break
            cursor.execute(path.read_text(encoding="utf-8"))
            cursor.execute(
                "INSERT INTO ai_actuarial_schema_migrations(version) VALUES (%s)", (version,)
            )
        cursor.execute(
            "INSERT INTO auth_tokens(subject,group_name,token_hash) VALUES "
            "('migration-sentinel','registered','synthetic-not-a-secret')"
        )
        cursor.execute(
            "INSERT INTO files(url,title,sha256) VALUES "
            "('https://example.test/migration.pdf','保留标题','synthetic-hash')"
        )
        cursor.execute(
            "INSERT INTO users(email,password_hash,role) VALUES "
            "('migration@example.test','synthetic-hash','registered')"
        )
        cursor.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema=current_schema() ORDER BY table_name"
        )
        tables = [row[0] for row in cursor if row[0] != "ai_actuarial_schema_migrations"]
        before = {}
        for table in tables:
            cursor.execute(f'SELECT row_to_json(t)::text FROM "{table}" t ORDER BY 1')
            before[table] = cursor.fetchall()
    assert postgresql_schema_status(database)["state"] == "upgrade_required"
    assert [item["version"] for item in postgresql_schema_plan(database)["plan"]] == list(
        range(7, POSTGRES_SCHEMA_VERSION + 1)
    )
    initialize_postgresql_schema(database)
    initialize_postgresql_schema(database)
    with psycopg2.connect(database) as connection, connection.cursor() as cursor:
        for table, rows in before.items():
            cursor.execute(f'SELECT row_to_json(t)::text FROM "{table}" t ORDER BY 1')
            assert cursor.fetchall() == rows, table
    assert (
        postgresql_schema_status(database)["database"]["schema_version"] == POSTGRES_SCHEMA_VERSION
    )


def test_same_key_concurrent_replay_and_conflict_preserve_one_record(tmp_path):
    database = postgres_url_for_path(tmp_path / "concurrent")
    request = _request(page_path="/files?q=private#fragment", content="  原始建议  ")
    with ThreadPoolExecutor(max_workers=4) as executor:
        receipts = list(
            executor.map(
                lambda _: submit_feedback(database, request, site_key="test", user_id=None),
                range(4),
            )
        )
    assert all(receipt == receipts[0] for receipt in receipts)
    with pytest.raises(FeedbackConflict):
        submit_feedback(
            database,
            _request(client_request_id=request.client_request_id, content="不同正文"),
            site_key="test",
            user_id=None,
        )
    items = list_feedback(database)["items"]
    assert len(items) == 1 and items[0]["content"] == "原始建议"
    assert items[0]["page_path"] == "/files"
    second = submit_feedback(
        database, _request(content="原始建议", page_path="/files"), site_key="test", user_id=None
    )
    assert second != receipts[0]


def test_replay_receipt_survives_admin_status_changes(tmp_path):
    database = postgres_url_for_path(tmp_path / "status")
    request = _request()
    receipt = submit_feedback(database, request, site_key="test", user_id=None)
    for status in ("reviewed", "closed", "new"):
        item = update_feedback_status(database, UUID(receipt["feedback_id"]), status)
        assert item["status"] == status and item["content"] == request.content
        assert submit_feedback(database, request, site_key="test", user_id=None) == receipt


def test_full_rescan_recovers_lower_id_committed_after_cursor_was_observed(tmp_path):
    database = postgres_url_for_path(tmp_path / "late-commit")
    late_feedback_id = str(uuid4())
    delayed = psycopg2.connect(database)
    try:
        with delayed.cursor() as cursor:
            cursor.execute(
                "INSERT INTO feedback_items "
                "(feedback_id, client_request_id, request_hash, site_key, content, kind, origin, "
                "page_path, locale) VALUES (%s, %s, %s, 'test', 'late commit', 'other', "
                "'widget', '/', 'en') RETURNING id",
                (late_feedback_id, str(uuid4()), "0" * 64),
            )
            late_id = cursor.fetchone()[0]
        first_receipt = submit_feedback(database, _request(), site_key="test", user_id=None)
        first_scan = list_feedback(database)["items"]
        assert [item["feedback_id"] for item in first_scan] == [first_receipt["feedback_id"]]
        observed_id = first_scan[0]["id"]
        assert late_id < observed_id
        delayed.commit()
        assert list_feedback(database, cursor=observed_id)["items"] == []
        rescan = list_feedback(database, cursor=0)["items"]
        assert [item["id"] for item in rescan] == [late_id, observed_id]
        known_ids = {item["feedback_id"] for item in first_scan}
        assert {item["feedback_id"] for item in rescan} - known_ids == {late_feedback_id}
    finally:
        delayed.close()


def test_real_deferred_commit_failure_rolls_back_before_receipt(tmp_path):
    database = postgres_url_for_path(tmp_path / "commit-failure")
    with psycopg2.connect(database) as connection, connection.cursor() as cursor:
        cursor.execute(
            "CREATE FUNCTION reject_feedback_commit() RETURNS trigger LANGUAGE plpgsql "
            "AS $$ BEGIN RAISE EXCEPTION 'synthetic commit failure'; END $$"
        )
        cursor.execute(
            "CREATE CONSTRAINT TRIGGER reject_commit AFTER INSERT ON feedback_items "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION reject_feedback_commit()"
        )
    with pytest.raises(psycopg2.Error, match="synthetic commit failure"):
        submit_feedback(database, _request(), site_key="test", user_id=None)
    assert list_feedback(database)["items"] == []
