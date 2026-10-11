"""Helpers for integration tests against the designated disposable PostgreSQL server."""

from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg2
from psycopg2.extensions import quote_ident

from ai_actuarial.postgres import DatabaseConfig, initialize_postgresql_schema

_lock = threading.Lock()
_schemas: set[str] = set()
_urls: dict[str, str] = {}
_data_roots: dict[str, str] = {}
_schema_urls: dict[str, str] = {}


def postgres_test_schema_snapshot() -> frozenset[str]:
    """Return the owned schemas that existed before the current test."""
    with _lock:
        return frozenset(_schemas)


def postgres_url_for_path(path: object) -> str:
    """Return one isolated, initialized PG schema URL for a test's former DB path."""
    base_url = os.getenv("POSTGRES_TEST_URL", "").strip()
    if not base_url:
        raise RuntimeError("POSTGRES_TEST_URL is required for PostgreSQL integration tests")
    if isinstance(path, DatabaseConfig):
        existing_url = path._url
    else:
        candidate = str(path)
        existing_url = candidate if urlsplit(candidate).scheme in {"postgres", "postgresql"} else ""
    if existing_url:
        with _lock:
            os.environ["DATABASE_URL"] = existing_url
            if existing_url in _data_roots:
                os.environ["DATA_DIR"] = _data_roots[existing_url]
        return existing_url
    test_id = os.getenv("PYTEST_CURRENT_TEST", "").split(" (", 1)[0]
    key = f"{test_id}\0{path}"
    data_dir = str(Path(str(path)).expanduser().resolve().parent)
    with _lock:
        if key in _urls:
            url = _urls[key]
            os.environ["DATABASE_URL"] = url
            os.environ["DATA_DIR"] = data_dir
            _data_roots[url] = data_dir
            return url
        schema = "test_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        admin = psycopg2.connect(base_url)
        admin.autocommit = True
        try:
            with admin.cursor() as cursor:
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {quote_ident(schema, cursor)}")
        finally:
            admin.close()
        parsed = urlsplit(base_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        existing_options = query.get("options", "").strip()
        query["options"] = f"{existing_options} -c search_path={schema}".strip()
        url = urlunsplit(parsed._replace(query=urlencode(query).replace("+", "%20")))
        initialize_postgresql_schema(url)
        _urls[key] = url
        _schemas.add(schema)
        _schema_urls[schema] = url
        _data_roots[url] = data_dir
        os.environ["DATABASE_URL"] = url
        os.environ["DATA_DIR"] = data_dir
        return url


def uninitialized_postgres_url_for_path(path: object) -> str:
    """Return a URL for an empty, isolated schema without applying migrations."""
    base_url = os.getenv("POSTGRES_TEST_URL", "").strip()
    if not base_url:
        raise RuntimeError("POSTGRES_TEST_URL is required for PostgreSQL integration tests")
    test_id = os.getenv("PYTEST_CURRENT_TEST", "").split(" (", 1)[0]
    key = f"uninitialized\0{test_id}\0{path}"
    data_dir = str(Path(str(path)).expanduser().resolve().parent)
    schema = "test_empty_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    with _lock:
        admin = psycopg2.connect(base_url)
        admin.autocommit = True
        try:
            with admin.cursor() as cursor:
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {quote_ident(schema, cursor)}")
        finally:
            admin.close()
        parsed = urlsplit(base_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        existing_options = query.get("options", "").strip()
        query["options"] = f"{existing_options} -c search_path={schema}".strip()
        url = urlunsplit(parsed._replace(query=urlencode(query).replace("+", "%20")))
        _schemas.add(schema)
        _schema_urls[schema] = url
        _data_roots[url] = data_dir
        os.environ["DATABASE_URL"] = url
        os.environ["DATA_DIR"] = data_dir
        return url


def cleanup_postgres_test_schemas(
    preserve_schemas: frozenset[str] | set[str] = frozenset(),
) -> None:
    """Drop newly created owned schemas and evict their URL cache entries."""
    base_url = os.getenv("POSTGRES_TEST_URL", "").strip()
    if not base_url:
        return
    with _lock:
        to_drop = sorted(_schemas.difference(preserve_schemas))
        if not to_drop:
            return
        admin = psycopg2.connect(base_url)
        admin.autocommit = True
        try:
            with admin.cursor() as cursor:
                for schema in to_drop:
                    quoted = quote_ident(schema, cursor)
                    cursor.execute(f"DROP SCHEMA IF EXISTS {quoted} CASCADE")
        finally:
            admin.close()

        dropped_urls = {_schema_urls.pop(schema) for schema in to_drop if schema in _schema_urls}
        _schemas.difference_update(to_drop)
        for key, url in list(_urls.items()):
            if url in dropped_urls:
                del _urls[key]
        for url in dropped_urls:
            _data_roots.pop(url, None)


def record_sql(connection, statements: list[str], *, include=None):
    """Record statements sent through one connection in a PostgreSQL test."""
    original_execute = connection.execute

    def execute(sql, parameters=None):
        if include is None or include(sql):
            statements.append(sql)
        return original_execute(sql, parameters)

    connection.execute = execute

    def stop() -> None:
        connection.execute = original_execute

    return stop
