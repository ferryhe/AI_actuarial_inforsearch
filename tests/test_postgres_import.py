from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import psycopg2
import pytest

from ai_actuarial.api.services.chat import _ensure_conversation_schema
from ai_actuarial.postgres import (
    DatabaseConfig,
    PostgresConnection,
    initialize_postgresql_schema,
)
from ai_actuarial.postgres_import import SQLiteImportError, import_sqlite_v16
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.sqlite_schema import (
    _OPTIONAL_TABLE_ALLOWED_COLUMNS,
    _current_storage_signature,
    schema_status,
)
from ai_actuarial.storage import Storage

ROOT = Path(__file__).resolve().parents[1]


def _base_test_url() -> str:
    value = os.getenv("POSTGRES_TEST_URL") or os.getenv("DATABASE_URL")
    if not value:
        pytest.fail("POSTGRES_TEST_URL is required for PostgreSQL import integration tests")
    return value


def _create_test_schema() -> tuple[str, str]:
    base_url = _base_test_url()
    schema = f"test_import_{uuid4().hex}"
    admin = psycopg2.connect(base_url)
    admin.autocommit = True
    with admin.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA "{schema}"')
    admin.close()

    parsed = urlsplit(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["options"] = f"-c search_path={schema}"
    url = urlunsplit(parsed._replace(query=urlencode(query).replace("+", "%20")))
    return schema, url


def _drop_test_schema(schema: str) -> None:
    admin = psycopg2.connect(_base_test_url())
    admin.autocommit = True
    with admin.cursor() as cursor:
        cursor.execute(f'DROP SCHEMA "{schema}" CASCADE')
    admin.close()


def _create_populated_v16_source(path: Path) -> None:
    storage = Storage._legacy_sqlite_schema_for_validation(path)
    try:
        manager = KnowledgeBaseManager(storage)
        manager._ensure_category_mapping_table()
        _ensure_conversation_schema(storage)
        conn = storage._conn
        for column in ("title", "source_site", "original_filename", "local_path", "keywords_json"):
            conn.execute(f"ALTER TABLE catalog_items ADD COLUMN {column} TEXT")

        file_url = "https://legacy.example/document%?version=1"
        conn.execute(
            "INSERT INTO files (id, url, sha256, title, bytes) VALUES (101, ?, ?, ?, ?)",
            (file_url, "legacy-sha", "文件 100%", 3_000_000_000),
        )
        conn.execute(
            "INSERT INTO pages (id, url, last_seen) VALUES (201, ?, ?)",
            ("https://legacy.example/路径?q=1", "not a timestamp"),
        )
        conn.execute(
            "INSERT INTO catalog_items "
            "(file_url, sha256, pipeline_version, title, source_site, original_filename, "
            "local_path, keywords_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                file_url,
                "legacy-sha",
                "pipeline-v16",
                "Catalog 100% ? 'quoted'",
                "legacy-site",
                "原始 file.pdf",
                r"D:\legacy files\actuary.pdf",
                '["财务", "100%", "?"]',
            ),
        )
        conn.execute(
            "INSERT INTO rag_knowledge_bases "
            "(kb_id, name, embedding_model, chunk_size, chunk_overlap, index_type, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("kb-legacy", "知识库 100%", "stub-model", 800, 100, "Flat", "bad time", "2026-10-11"),
        )
        conn.execute(
            "INSERT INTO rag_kb_files (kb_id, file_url, added_at, chunk_count) VALUES (?, ?, ?, ?)",
            ("kb-legacy", file_url, "2026-10-11", 1),
        )
        conn.execute(
            "INSERT INTO rag_chunks "
            "(chunk_id, kb_id, file_url, chunk_index, content, token_count, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("chunk-legacy", "kb-legacy", file_url, 0, "Résumé 100% ?", 3, "invalid legacy time"),
        )
        conn.execute(
            "INSERT INTO rag_kb_category_mappings (kb_id, category, auto_sync) VALUES (?, ?, ?)",
            ("kb-legacy", "财务", 1),
        )
        conn.execute(
            "INSERT INTO conversations "
            "(conversation_id, user_id, title, created_at, updated_at, message_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("conversation-legacy", "user-1", "Chat 100% ?", "invalid", "invalid", 1),
        )
        conn.execute(
            "INSERT INTO messages (rowid, message_id, conversation_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                40,
                "message-legacy",
                "conversation-legacy",
                "assistant",
                "回答 100% ?",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        for rowid, message_id in ((41, "message-a"), (42, "message-y"), (43, "message-b")):
            conn.execute(
                "INSERT INTO messages "
                "(rowid, message_id, conversation_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    rowid,
                    message_id,
                    "conversation-legacy",
                    "user",
                    f"content-{message_id}",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
        conn.commit()
    finally:
        storage.close()

    status = schema_status(path)
    assert status["state"] == "current", status


def _create_core_only_v16_source(path: Path) -> None:
    storage = Storage._legacy_sqlite_schema_for_validation(path)
    try:
        storage._conn.execute(
            "INSERT INTO files (id, url, sha256, bytes) VALUES (?, ?, ?, ?)",
            (501, "https://legacy.example/core-only", "core-only", 3_000_000_000),
        )
        storage._conn.commit()
    finally:
        storage.close()
    status = schema_status(path)
    assert status["state"] == "current", status


def test_imports_populated_optional_rag_chat_and_lazy_catalog_tables(
    tmp_path: Path,
) -> None:
    schema, database_url = _create_test_schema()
    source_path = tmp_path / "populated-v16.sqlite"
    try:
        _create_populated_v16_source(source_path)
        database = DatabaseConfig(database_url)

        first = import_sqlite_v16(source_path, database)
        second = import_sqlite_v16(source_path, database)

        assert first["already_imported"] is False
        assert second["already_imported"] is True
        assert first["source_schema_version"] == 16
        assert first["row_counts"]["rag_chunks"] == 1
        assert first["row_counts"]["messages"] == 4
        assert first["row_counts"]["catalog_items"] == 1

        pg = PostgresConnection(database)
        try:
            catalog = pg.execute(
                "SELECT title, source_site, original_filename, local_path, keywords_json "
                "FROM catalog_items WHERE file_url = ?",
                ("https://legacy.example/document%?version=1",),
            ).fetchone()
            assert tuple(catalog) == (
                "Catalog 100% ? 'quoted'",
                "legacy-site",
                "原始 file.pdf",
                r"D:\legacy files\actuary.pdf",
                '["财务", "100%", "?"]',
            )
            assert tuple(pg.execute("SELECT id, bytes FROM files").fetchone()) == (
                101,
                3_000_000_000,
            )
            assert pg.execute("SELECT content FROM rag_chunks").fetchone()[0] == "Résumé 100% ?"
            assert [
                tuple(row)
                for row in pg.execute(
                    "SELECT message_id, message_order FROM messages ORDER BY message_order"
                ).fetchall()
            ] == [
                ("message-legacy", 40),
                ("message-a", 41),
                ("message-y", 42),
                ("message-b", 43),
            ]
            assert pg.execute("SELECT content FROM messages").fetchone()[0] == "回答 100% ?"
            next_id = pg.execute(
                "INSERT INTO files (url) VALUES (?) RETURNING id",
                ("https://legacy.example/next",),
            ).fetchone()[0]
            assert next_id == 102
        finally:
            pg.close()

        storage = Storage(database)
        try:
            from ai_actuarial.chatbot.config import ChatbotConfig
            from ai_actuarial.chatbot.conversation import ConversationManager

            manager = ConversationManager(storage, ChatbotConfig(api_key="test-key"))
            assert [row["message_id"] for row in manager.get_messages("conversation-legacy")] == [
                "message-legacy",
                "message-a",
                "message-y",
                "message-b",
            ]
            assert [
                row["message_id"] for row in manager.get_messages("conversation-legacy", limit=2)
            ] == [
                "message-y",
                "message-b",
            ]
            manager.add_message("conversation-legacy", "assistant", "new message")
            assert [row["message_id"] for row in manager.get_messages("conversation-legacy")][
                -1
            ].startswith("msg_")
        finally:
            storage.close()

        second_source = tmp_path / "same-data-different-file.sqlite"
        shutil.copyfile(source_path, second_source)
        with sqlite3.connect(second_source) as conn:
            conn.execute("VACUUM")
        with pytest.raises(SQLiteImportError, match="another source"):
            import_sqlite_v16(second_source, database)

        pg = PostgresConnection(database)
        try:
            assert pg.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 5
            assert pg.execute("SELECT COUNT(*) FROM ai_actuarial_sqlite_imports").fetchone()[0] == 1
        finally:
            pg.close()
    finally:
        _drop_test_schema(schema)


@pytest.mark.parametrize(
    ("filename", "contents"),
    [
        ("README.md", b"# Project README\nThis is not a SQLite database.\n"),
        ("damaged.sqlite", b"SQLite format 3\x00" + b"\xff" * 4096),
    ],
    ids=("readme-source", "damaged-sqlite-source"),
)
def test_schema_import_cli_reports_invalid_sources_as_json_without_mutation(
    tmp_path: Path,
    filename: str,
    contents: bytes,
) -> None:
    schema, database_url = _create_test_schema()
    source_path = tmp_path / filename
    source_path.write_bytes(contents)
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    database = DatabaseConfig(database_url)
    business_tables = sorted(
        set(_current_storage_signature()) | set(_OPTIONAL_TABLE_ALLOWED_COLUMNS)
    )
    try:
        initialize_postgresql_schema(database)
        pg = PostgresConnection(database)
        try:
            pg.execute(
                "INSERT INTO files (url, sha256, title) VALUES (?, ?, ?)",
                ("https://target.example/preserved", "target-hash", "Preserve this row"),
            )
            pg.commit()
            before_counts = {
                table: int(pg.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                for table in business_tables
            }
            before_file = tuple(
                pg.execute(
                    "SELECT id, url, sha256, title FROM files WHERE url = ?",
                    ("https://target.example/preserved",),
                ).fetchone()
            )
        finally:
            pg.close()

        child_env = os.environ.copy()
        child_env["DATABASE_URL"] = database_url
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ai_actuarial.cli",
                "schema",
                "import-sqlite-v16",
                "--source",
                str(source_path),
                "--json",
            ],
            cwd=ROOT,
            env=child_env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 2
        payload = json.loads(result.stdout)
        assert payload["success"] is False
        assert payload["error"] == "SQLite import source is not a valid v16 database"
        assert "Traceback" not in result.stdout + result.stderr
        assert database_url not in result.stdout + result.stderr
        assert hashlib.sha256(source_path.read_bytes()).hexdigest() == source_sha256

        pg = PostgresConnection(database)
        try:
            after_counts = {
                table: int(pg.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                for table in business_tables
            }
            after_file = tuple(
                pg.execute(
                    "SELECT id, url, sha256, title FROM files WHERE url = ?",
                    ("https://target.example/preserved",),
                ).fetchone()
            )
            provenance_count = int(
                pg.execute("SELECT COUNT(*) FROM ai_actuarial_sqlite_imports").fetchone()[0]
            )
        finally:
            pg.close()
        assert after_counts == before_counts
        assert after_file == before_file
        assert provenance_count == 0
    finally:
        _drop_test_schema(schema)


def test_core_only_import_rejects_preexisting_optional_business_rows(tmp_path: Path) -> None:
    schema, database_url = _create_test_schema()
    source_path = tmp_path / "core-only-v16.sqlite"
    database = DatabaseConfig(database_url)
    try:
        _create_core_only_v16_source(source_path)
        initialize_postgresql_schema(database)
        pg = PostgresConnection(database)
        try:
            pg.execute(
                "INSERT INTO conversations "
                "(conversation_id, user_id, title, created_at, updated_at, message_count) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("preexisting", "user", "keep", "2026-10-11", "2026-10-11", 0),
            )
            pg.commit()
        finally:
            pg.close()

        with pytest.raises(SQLiteImportError, match="requires an empty"):
            import_sqlite_v16(source_path, database)

        pg = PostgresConnection(database)
        try:
            assert pg.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
            assert pg.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 1
            assert pg.execute("SELECT COUNT(*) FROM ai_actuarial_sqlite_imports").fetchone()[0] == 0
        finally:
            pg.close()
    finally:
        _drop_test_schema(schema)


def test_import_rejects_a_different_source_after_empty_snapshot(tmp_path: Path) -> None:
    schema, database_url = _create_test_schema()
    empty_source = tmp_path / "empty-v16.sqlite"
    second_source = tmp_path / "second-v16.sqlite"
    database = DatabaseConfig(database_url)
    try:
        empty = Storage._legacy_sqlite_schema_for_validation(empty_source)
        empty.close()
        assert schema_status(empty_source)["state"] == "current"
        _create_core_only_v16_source(second_source)

        first = import_sqlite_v16(empty_source, database)
        assert first["already_imported"] is False
        assert not any(first["row_counts"].values())

        with pytest.raises(SQLiteImportError, match="another source"):
            import_sqlite_v16(second_source, database)

        pg = PostgresConnection(database)
        try:
            assert pg.execute("SELECT COUNT(*) FROM ai_actuarial_sqlite_imports").fetchone()[0] == 1
            assert pg.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
        finally:
            pg.close()
    finally:
        _drop_test_schema(schema)


def test_import_streams_tables_across_multiple_bounded_batches(tmp_path: Path) -> None:
    schema, database_url = _create_test_schema()
    source_path = tmp_path / "many-files-v16.sqlite"
    database = DatabaseConfig(database_url)
    try:
        _create_core_only_v16_source(source_path)
        legacy = Storage._legacy_sqlite_schema_for_validation(source_path)
        try:
            legacy._conn.executemany(
                "INSERT INTO files (id, url, sha256, title) VALUES (?, ?, ?, ?)",
                (
                    (
                        file_id,
                        f"https://legacy.example/{file_id}",
                        f"sha-{file_id}",
                        f"File {file_id}",
                    )
                    for file_id in range(1000, 2205)
                ),
            )
            legacy._conn.commit()
        finally:
            legacy.close()

        imported = import_sqlite_v16(source_path, database)
        assert imported["row_counts"]["files"] == 1206

        pg = PostgresConnection(database)
        try:
            assert pg.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 1206
            assert tuple(
                pg.execute("SELECT id, url, title FROM files WHERE id = ?", (2204,)).fetchone()
            ) == (2204, "https://legacy.example/2204", "File 2204")
        finally:
            pg.close()
    finally:
        _drop_test_schema(schema)
