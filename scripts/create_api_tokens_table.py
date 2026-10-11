"""Initialize and verify the PostgreSQL schema used by the token API.

The table is owned by the versioned application schema migration; this script
is an idempotent operator entry point for deployments and local setup.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_actuarial.postgres import (  # noqa: E402
    PostgresConnection,
    initialize_postgresql_schema,
    resolve_database_config,
)
from config.yaml_config import load_database_config  # noqa: E402


def create_api_tokens_table(database_url_env: str | None = None) -> None:
    database_settings = load_database_config()
    if database_url_env:
        database_settings = {**database_settings, "url_env": database_url_env}
    database = resolve_database_config({"database": database_settings})
    initialize_postgresql_schema(database)
    connection = PostgresConnection(database, read_only=True)
    try:
        columns = sorted(connection.table_columns("api_tokens"))
        if not columns:
            raise RuntimeError("PostgreSQL schema is missing api_tokens")
    finally:
        connection.close()
    print(f"Verified api_tokens in PostgreSQL ({len(columns)} columns).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url-env", default="")
    create_api_tokens_table(parser.parse_args().database_url_env or None)
