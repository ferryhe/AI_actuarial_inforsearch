#!/usr/bin/env python3
"""Show the PostgreSQL storage factory and separate file-artifact root."""

import os

from ai_actuarial.storage_factory import create_storage_from_config


def main() -> None:
    """Connect using private environment configuration without printing secrets."""
    config = {
        "database": {"type": "postgresql", "url_env": "DATABASE_URL"},
        "paths": {"data": os.getenv("DATA_DIR", "data")},
    }
    storage = create_storage_from_config(config)
    try:
        print(f"Storage: {type(storage).__name__}")
        print(f"File/artifact root: {storage.data_root}")
        print("Database URL loaded from the DATABASE_URL environment variable.")
    finally:
        storage.close()


if __name__ == "__main__":
    main()
