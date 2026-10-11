from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import psycopg2
import pytest

from ai_actuarial import storage_factory
from ai_actuarial.postgres import (
    POSTGRES_SCHEMA_VERSION,
    DatabaseConfig,
    PostgresConnection,
    _postgres_placeholders,
    postgresql_schema_plan,
)
from tests.postgres_helpers import postgres_url_for_path

_INITIAL_DATABASE_URL = os.environ.get("DATABASE_URL")
_INITIAL_DATA_DIR = os.environ.get("DATA_DIR")


def _postgres_test_url() -> str:
    value = os.getenv("POSTGRES_TEST_URL")
    if not value:
        pytest.fail("POSTGRES_TEST_URL is required for PostgreSQL integration tests")
    return value


@pytest.fixture
def postgres_connection():
    base_url = _postgres_test_url()
    schema = f"test_postgres_{uuid4().hex}"
    admin = psycopg2.connect(base_url)
    admin.autocommit = True
    with admin.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA "{schema}"')
    admin.close()

    parsed = urlsplit(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["options"] = f"-c search_path={schema}"
    encoded_query = urlencode(query).replace("+", "%20")
    url = urlunsplit(parsed._replace(query=encoded_query))
    connection = PostgresConnection(DatabaseConfig(url))
    try:
        yield connection
    finally:
        connection.close()
        admin = psycopg2.connect(base_url)
        admin.autocommit = True
        with admin.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA "{schema}" CASCADE')
        admin.close()


def test_qmark_translation_preserves_quoted_percent_and_modulo():
    sql = "SELECT '100%' AS literal_percent, value % 2 = ? -- 50% comment\nFROM sample"
    assert _postgres_placeholders(sql, has_parameters=True) == (
        "SELECT '100%%' AS literal_percent, value %% 2 = %s -- 50%% comment\nFROM sample"
    )
    assert _postgres_placeholders("SELECT '100%'", has_parameters=False) == "SELECT '100%'"


def test_bound_query_keeps_literal_percent_and_modulo(postgres_connection: PostgresConnection):
    row = postgres_connection.execute(
        "SELECT '100%' AS literal_percent, '(%)' LIKE ? AS wildcard_match, 5 % 2 = ? AS modulo",
        ("(%)", 1),
    ).fetchone()
    assert row["literal_percent"] == "100%"
    assert row["wildcard_match"] is True
    assert row["modulo"] is True


def test_empty_postgres_schema_plan_lists_each_pending_migration(
    postgres_connection: PostgresConnection,
):
    base_url = _postgres_test_url()
    schema = postgres_connection.execute("SELECT current_schema()").fetchone()[0]
    parsed = urlsplit(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["options"] = f"-c search_path={schema}"
    url = urlunsplit(parsed._replace(query=urlencode(query).replace("+", "%20")))

    plan = postgresql_schema_plan(url)

    assert [migration["version"] for migration in plan["plan"]] == list(
        range(1, POSTGRES_SCHEMA_VERSION + 1)
    )
    assert [migration["file"] for migration in plan["plan"]] == [
        path.name
        for path in sorted(Path("ai_actuarial/migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))
    ]
    assert [migration["action"] for migration in plan["plan"]] == [
        "initialize",
        *("upgrade" for _ in range(POSTGRES_SCHEMA_VERSION - 1)),
    ]


def test_storage_factory_uses_configured_data_root_without_rendering_dsn(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    captured: dict[str, object] = {}

    def fake_storage(database, *, data_root=None):
        captured["database"] = database
        captured["data_root"] = data_root
        return object()

    monkeypatch.setattr(storage_factory, "Storage", fake_storage)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.setenv("APP_POSTGRES_URL", "postgresql://private:secret@example.invalid/app")
    data_root = tmp_path / "configured-data"

    storage_factory.create_storage_from_config(
        {
            "database": {"type": "postgresql", "url_env": "APP_POSTGRES_URL"},
            "paths": {"data": str(data_root)},
        }
    )

    assert captured["data_root"] == data_root.resolve()
    assert "secret" not in repr(captured["database"])


def test_a_legacy_path_helper_selects_an_isolated_database_for_callers(tmp_path):
    url = postgres_url_for_path(tmp_path / "helper.db")
    assert os.environ["DATABASE_URL"] == url


def test_b_helper_environment_does_not_leak_into_the_next_test():
    assert os.environ.get("DATABASE_URL") == _INITIAL_DATABASE_URL
    assert os.environ.get("DATA_DIR") == _INITIAL_DATA_DIR


def test_path_helper_cache_restores_the_requested_database_and_data_root(tmp_path):
    path_a = tmp_path / "a" / "index.db"
    path_b = tmp_path / "b" / "index.db"

    url_a = postgres_url_for_path(path_a)
    url_b = postgres_url_for_path(path_b)
    url_a_again = postgres_url_for_path(path_a)

    assert url_a_again == url_a
    assert url_b != url_a
    assert os.environ["DATABASE_URL"] == url_a
    assert os.environ["DATA_DIR"] == str(path_a.parent.resolve())
