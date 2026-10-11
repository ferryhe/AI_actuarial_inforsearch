"""PostgreSQL connection and versioned runtime schema."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import parse_qsl, unquote, urlsplit
from uuid import uuid4

import psycopg2
from psycopg2.extras import DictCursor

_MIGRATION_DIR = Path(__file__).with_name("migrations")
_MIGRATIONS = {
    int(path.name.split("_", 1)[0]): path
    for path in _MIGRATION_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql")
}
POSTGRES_SCHEMA_VERSION = max(_MIGRATIONS, default=0)
if sorted(_MIGRATIONS) != list(range(1, POSTGRES_SCHEMA_VERSION + 1)):
    raise RuntimeError("PostgreSQL schema migrations must be numbered without gaps")


class DatabaseConfigurationError(ValueError):
    """The PostgreSQL runtime has no valid database configuration."""


class DatabaseConnectionError(RuntimeError):
    """A PostgreSQL connection failed without exposing its credentials."""


def _postgres_client_settings(
    database_url: DatabaseConfig | str,
) -> tuple[list[str], dict[str, str]]:
    url = database_url._url if isinstance(database_url, DatabaseConfig) else database_url
    parsed = urlsplit(url)
    DatabaseConfig(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    environment = os.environ.copy()
    environment["PGHOST"] = parsed.hostname or ""
    environment["PGPORT"] = str(parsed.port or 5432)
    if parsed.username is not None:
        environment["PGUSER"] = unquote(parsed.username)
    environment["PGDATABASE"] = unquote(parsed.path.lstrip("/"))
    if parsed.password is not None:
        environment["PGPASSWORD"] = unquote(parsed.password)
    environment_keys = {
        "hostaddr": "PGHOSTADDR",
        "service": "PGSERVICE",
        "passfile": "PGPASSFILE",
        "connect_timeout": "PGCONNECT_TIMEOUT",
        "sslmode": "PGSSLMODE",
        "sslrootcert": "PGSSLROOTCERT",
        "sslcert": "PGSSLCERT",
        "sslkey": "PGSSLKEY",
        "sslcrl": "PGSSLCRL",
        "sslcrldir": "PGSSLCRLDIR",
        "sslsni": "PGSSLSNI",
        "gssencmode": "PGGSSENCMODE",
        "channel_binding": "PGCHANNELBINDING",
        "options": "PGOPTIONS",
        "application_name": "PGAPPNAME",
        "target_session_attrs": "PGTARGETSESSIONATTRS",
    }
    for key, environment_key in environment_keys.items():
        if key in query:
            environment[environment_key] = query[key]
    return [], environment


def _client_failure(result: subprocess.CompletedProcess[str], environment: dict[str, str]) -> str:
    """Return useful native-client diagnostics without printing login material."""
    detail = (result.stderr or "").strip()
    for key in ("PGPASSWORD", "PGUSER"):
        value = environment.get(key)
        if value:
            detail = detail.replace(value, "[redacted]")
    detail = " ".join(detail.split())[:500]
    suffix = f": {detail}" if detail else ""
    return f"PostgreSQL client failed (exit {result.returncode}){suffix}"


def run_postgres_dump(
    database_url: DatabaseConfig | str,
    destination: str | Path,
    *,
    schema: str,
) -> None:
    """Create a native custom-format dump of one application schema."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise ValueError("Invalid PostgreSQL schema name")
    binary = os.getenv("PG_DUMP_BIN") or shutil.which("pg_dump")
    if not binary or not Path(binary).is_file():
        raise RuntimeError("PostgreSQL client pg_dump is required (version 16 or newer)")
    connection_args, environment = _postgres_client_settings(database_url)
    command = [
        binary,
        "--no-password",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "--schema",
        schema,
        "--file",
        str(destination),
        *connection_args,
        environment["PGDATABASE"],
    ]
    result = subprocess.run(command, env=environment, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(_client_failure(result, environment))


def verify_postgres_dump(dump_path: str | Path) -> None:
    """Read a custom-format dump directory without connecting to a database."""
    binary = os.getenv("PG_RESTORE_BIN") or shutil.which("pg_restore")
    if not binary or not Path(binary).is_file():
        raise RuntimeError("PostgreSQL client pg_restore is required (version 16 or newer)")
    result = subprocess.run(
        [binary, "--list", str(dump_path)], capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise RuntimeError("PostgreSQL dump is not a readable custom-format archive")


def run_postgres_restore(
    database_url: DatabaseConfig | str,
    dump_path: str | Path,
    *,
    schema: str,
) -> None:
    """Restore one schema into a caller-provisioned, empty database."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise ValueError("Invalid PostgreSQL schema name")
    binary = os.getenv("PG_RESTORE_BIN") or shutil.which("pg_restore")
    if not binary or not Path(binary).is_file():
        raise RuntimeError("PostgreSQL client pg_restore is required (version 16 or newer)")
    connection_args, environment = _postgres_client_settings(database_url)
    command = [
        binary,
        "--no-password",
        "--exit-on-error",
        "--no-owner",
        "--no-privileges",
        "--schema",
        schema,
        "--dbname",
        environment["PGDATABASE"],
        *connection_args,
        str(dump_path),
    ]
    result = subprocess.run(command, env=environment, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(_client_failure(result, environment))


@dataclass(frozen=True, repr=False)
class DatabaseConfig:
    """Opaque PostgreSQL connection settings; its URL is never rendered."""

    _url: str

    def __post_init__(self) -> None:
        try:
            parsed = urlsplit(self._url)
            valid = parsed.scheme in {"postgres", "postgresql"} and bool(parsed.hostname)
        except ValueError:
            valid = False
        if not valid:
            raise DatabaseConfigurationError("DATABASE_URL must be a valid PostgreSQL URL")

    def __repr__(self) -> str:
        return "DatabaseConfig(<redacted>)"

    __str__ = __repr__


def resolve_database_config(config: dict[str, Any] | None = None) -> DatabaseConfig:
    """Resolve a PostgreSQL URL from the environment or an explicit env key."""
    url = os.getenv("DATABASE_URL", "").strip()
    if not url and config:
        database = config.get("database")
        if isinstance(database, dict):
            env_name = str(database.get("url_env") or "DATABASE_URL").strip()
            url = os.getenv(env_name, "").strip()
    if not url:
        raise DatabaseConfigurationError(
            "PostgreSQL is required; configure DATABASE_URL or database.url_env"
        )
    return DatabaseConfig(url)


def resolve_data_root(config: dict[str, Any] | None = None) -> Path:
    """Resolve file/artifact placement independently from the database URL."""
    if config is None:
        try:
            from .shared_runtime import load_sites_config

            config = load_sites_config()
        except Exception:  # noqa: BLE001
            config = {}
    paths = config.get("paths") if isinstance(config, dict) else None
    configured = paths.get("data") if isinstance(paths, dict) else None
    value = os.getenv("DATA_DIR", "").strip() or str(configured or "data")
    return Path(value).expanduser().resolve()


def _postgres_placeholders(sql: str, *, has_parameters: bool) -> str:
    """Translate DB-API qmark parameters without changing quoted SQL text."""
    out: list[str] = []
    index = 0
    state = "normal"
    dollar_tag = ""
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        if state == "single":
            out.append("%%" if char == "%" and has_parameters else char)
            if char == "'":
                if next_char == "'":
                    out.append(next_char)
                    index += 1
                else:
                    state = "normal"
        elif state == "double":
            out.append("%%" if char == "%" and has_parameters else char)
            if char == '"':
                if next_char == '"':
                    out.append(next_char)
                    index += 1
                else:
                    state = "normal"
        elif state == "line_comment":
            out.append("%%" if char == "%" and has_parameters else char)
            if char in "\r\n":
                state = "normal"
        elif state == "block_comment":
            out.append("%%" if char == "%" and has_parameters else char)
            if char == "*" and next_char == "/":
                out.append(next_char)
                index += 1
                state = "normal"
        elif state == "dollar":
            if sql.startswith(dollar_tag, index):
                out.append(dollar_tag)
                index += len(dollar_tag) - 1
                state = "normal"
            else:
                out.append("%%" if char == "%" and has_parameters else char)
        elif char == "'":
            state = "single"
            out.append(char)
        elif char == '"':
            state = "double"
            out.append(char)
        elif char == "-" and next_char == "-":
            state = "line_comment"
            out.extend((char, next_char))
            index += 1
        elif char == "/" and next_char == "*":
            state = "block_comment"
            out.extend((char, next_char))
            index += 1
        elif char == "$":
            match = re.match(r"\$[A-Za-z_0-9]*\$", sql[index:])
            if match:
                dollar_tag = match.group(0)
                state = "dollar"
                out.append(dollar_tag)
                index += len(dollar_tag) - 1
            else:
                out.append(char)
        elif char == "?":
            out.append("%s")
        elif char == "%" and has_parameters:
            out.append("%%")
        else:
            out.append(char)
        index += 1
    return "".join(out)


class PostgresConnection:
    """Small DB-API facade preserving the existing execute/fetch call pattern."""

    def __init__(
        self,
        database_url: DatabaseConfig | str,
        *,
        read_only: bool = False,
        autocommit: bool = True,
    ):
        url = database_url._url if isinstance(database_url, DatabaseConfig) else database_url
        DatabaseConfig(url)
        try:
            self._connection = psycopg2.connect(
                url,
                cursor_factory=DictCursor,
                application_name="ai_actuarial",
            )
        except psycopg2.Error:
            raise DatabaseConnectionError(
                "Unable to connect to the configured PostgreSQL database"
            ) from None
        self._connection.set_session(readonly=read_only, autocommit=autocommit)
        self.read_only = read_only
        self._total_changes = 0

    @property
    def in_transaction(self) -> bool:
        return (
            self._connection.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE
        )

    @property
    def total_changes(self) -> int:
        return self._total_changes

    def _record_changes(self, cursor: Any) -> None:
        if str(cursor.statusmessage or "").split(" ", 1)[0] in {
            "INSERT",
            "UPDATE",
            "DELETE",
            "MERGE",
        }:
            self._total_changes += max(0, int(cursor.rowcount or 0))

    def execute(self, sql: str, parameters: Iterable[Any] | None = None):
        cursor = self._connection.cursor()
        values = tuple(parameters) if parameters is not None else ()
        statement = _postgres_placeholders(sql, has_parameters=bool(values))
        if parameters is None:
            cursor.execute(statement)
        elif not values:
            cursor.execute(sql)
        else:
            cursor.execute(statement, values)
        self._record_changes(cursor)
        return cursor

    def executemany(self, sql: str, parameters: Iterable[Iterable[Any]]):
        cursor = self._connection.cursor()
        cursor.executemany(_postgres_placeholders(sql, has_parameters=True), parameters)
        self._record_changes(cursor)
        return cursor

    def iter_batches(
        self,
        sql: str,
        parameters: Iterable[Any] = (),
        *,
        batch_size: int = 1000,
    ) -> Iterator[list[Any]]:
        """Yield bounded result batches from a server-side PostgreSQL cursor."""
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        cursor = self._connection.cursor(
            name=f"ai_actuarial_stream_{uuid4().hex}", cursor_factory=DictCursor
        )
        bound = tuple(parameters)
        try:
            statement = _postgres_placeholders(sql, has_parameters=bool(bound))
            if bound:
                cursor.execute(statement, bound)
            else:
                cursor.execute(statement)
            while batch := cursor.fetchmany(batch_size):
                yield batch
        finally:
            cursor.close()

    def cursor(self):
        return self._connection.cursor()

    def commit(self) -> None:
        if self._connection.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
            with self._connection.cursor() as cursor:
                cursor.execute("COMMIT")

    def rollback(self) -> None:
        if self._connection.get_transaction_status() != psycopg2.extensions.TRANSACTION_STATUS_IDLE:
            with self._connection.cursor() as cursor:
                cursor.execute("ROLLBACK")

    def close(self) -> None:
        self._connection.close()

    def table_exists(self, table: str) -> bool:
        return self.execute("SELECT to_regclass(?) IS NOT NULL", (table,)).fetchone()[0]

    def table_columns(self, table: str) -> set[str]:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
            raise ValueError("Invalid PostgreSQL table name")
        rows = self.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = ?",
            (table,),
        ).fetchall()
        return {str(row[0]) for row in rows}

    def index_names(self, table: str) -> set[str]:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
            raise ValueError("Invalid PostgreSQL table name")
        rows = self.execute(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = current_schema() AND tablename = ?",
            (table,),
        ).fetchall()
        return {str(row[0]) for row in rows}

    def assert_read_only(self) -> None:
        if not self.read_only:
            raise RuntimeError("database snapshot is not read-only")


def initialize_postgresql_schema(database_url: DatabaseConfig | str) -> None:
    """Apply the complete baseline once, rejecting unversioned existing schemas."""
    connection = PostgresConnection(database_url)
    try:
        connection.execute("BEGIN")
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended("
            "current_database() || ':' || current_schema() || ':ai_actuarial_schema', 0))"
        )
        has_version_table = connection.table_exists("ai_actuarial_schema_migrations")
        if not has_version_table:
            existing = connection.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE' "
                "AND table_name NOT LIKE 'ai_actuarial_%' LIMIT 1"
            ).fetchone()
            if existing:
                raise RuntimeError(
                    "PostgreSQL schema is not initialized; use the explicit schema migration command"
                )
            version = 0
        else:
            version = int(
                connection.execute(
                    "SELECT COALESCE(MAX(version), 0) FROM ai_actuarial_schema_migrations"
                ).fetchone()[0]
            )
            if version > POSTGRES_SCHEMA_VERSION:
                raise RuntimeError("PostgreSQL schema version is newer than this code")
        for migration_version in range(version + 1, POSTGRES_SCHEMA_VERSION + 1):
            path = _MIGRATIONS[migration_version]
            connection.execute(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO ai_actuarial_schema_migrations(version) VALUES (?)",
                (migration_version,),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def postgresql_schema_status(database_url: DatabaseConfig | str) -> dict[str, Any]:
    connection = PostgresConnection(database_url, read_only=True)
    try:
        has_version_table = bool(connection.table_exists("ai_actuarial_schema_migrations"))
        version = 0
        if has_version_table:
            version = int(
                connection.execute(
                    "SELECT COALESCE(MAX(version), 0) FROM ai_actuarial_schema_migrations"
                ).fetchone()[0]
            )
        if not has_version_table:
            existing = connection.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE' "
                "AND table_name NOT LIKE 'ai_actuarial_%' LIMIT 1"
            ).fetchone()
            state = "uninitialized" if existing else "empty"
        elif version == POSTGRES_SCHEMA_VERSION:
            state = "current"
        elif version < POSTGRES_SCHEMA_VERSION:
            state = "upgrade_required"
        else:
            state = "newer_than_code"
        return {
            "success": state == "current",
            "state": state,
            "database": {
                "engine": "postgresql",
                "schema": str(connection.execute("SELECT current_schema()").fetchone()[0]),
                "schema_version": version,
            },
            "current_schema_version": POSTGRES_SCHEMA_VERSION,
        }
    finally:
        connection.close()


def postgresql_schema_plan(database_url: DatabaseConfig | str) -> dict[str, Any]:
    status = postgresql_schema_status(database_url)
    current = int(status["database"]["schema_version"])
    pending = [
        {
            "version": version,
            "action": "initialize" if version == current + 1 and current == 0 else "upgrade",
            "file": _MIGRATIONS[version].name,
        }
        for version in range(current + 1, POSTGRES_SCHEMA_VERSION + 1)
    ]
    return {
        **status,
        "plan": pending,
    }


@contextmanager
def postgres_connection(database_url: DatabaseConfig | str, *, read_only: bool = False):
    connection = PostgresConnection(database_url, read_only=read_only)
    try:
        yield connection
    finally:
        connection.close()
