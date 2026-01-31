"""Storage factory with database backend abstraction.

This module provides a factory function to create Storage instances
with support for both SQLite (local dev) and PostgreSQL (production).
"""

from __future__ import annotations

import os
from typing import Any

from .storage import Storage


def create_storage_from_config(config: dict[str, Any]) -> Storage:
    """Create a Storage instance from configuration.
    
    This factory function supports two modes:
    1. Legacy mode: Direct database path (SQLite only)
    2. Backend mode: Database configuration dict
    
    Args:
        config: Configuration dictionary, either:
            - {"paths": {"db": "data/index.db"}} for legacy SQLite
            - {"database": {"type": "sqlite", "path": "data/index.db"}}
            - {"database": {"type": "postgresql", "host": "...", ...}}
            
    Returns:
        Storage instance configured with the appropriate backend
        
    Examples:
        # Legacy SQLite mode
        config = {"paths": {"db": "data/index.db"}}
        storage = create_storage_from_config(config)
        
        # New SQLite mode with explicit config
        config = {"database": {"type": "sqlite", "path": "data/index.db"}}
        storage = create_storage_from_config(config)
        
        # PostgreSQL mode
        config = {
            "database": {
                "type": "postgresql",
                "host": "localhost",
                "port": 5432,
                "database": "ai_actuarial",
                "username": "postgres",
                "password": "secret"
            }
        }
        storage = create_storage_from_config(config)
    """
    # Check if new database config is present
    if "database" in config:
        db_config = config["database"]
        db_type = db_config.get("type", "sqlite").lower()
        
        if db_type == "sqlite":
            # SQLite with backend abstraction
            db_path = db_config.get("path", "data/index.db")
            # For SQLite, we can still use the legacy Storage class
            # since it's optimized for SQLite
            return Storage(db_path)
        
        elif db_type == "postgresql":
            # PostgreSQL requires the backend abstraction
            # Import here to avoid circular dependency
            from .storage_v2 import StorageV2
            return StorageV2(db_config=db_config)
        
        else:
            raise ValueError(f"Unsupported database type: {db_type}")
    
    # Legacy mode: use paths.db
    elif "paths" in config and "db" in config["paths"]:
        db_path = config["paths"]["db"]
        return Storage(db_path)
    
    else:
        raise ValueError(
            "Invalid configuration: must provide either 'database' or 'paths.db'"
        )


def get_database_config_from_env() -> dict[str, Any]:
    """Get database configuration from environment variables.
    
    Environment variables:
        DB_TYPE: Database type ('sqlite' or 'postgresql')
        DB_PATH: SQLite database path (if DB_TYPE=sqlite)
        DB_HOST: PostgreSQL host (if DB_TYPE=postgresql)
        DB_PORT: PostgreSQL port (if DB_TYPE=postgresql)
        DB_NAME: PostgreSQL database name (if DB_TYPE=postgresql)
        DB_USER: PostgreSQL username (if DB_TYPE=postgresql)
        DB_PASSWORD: PostgreSQL password (if DB_TYPE=postgresql)
        
    Returns:
        Database configuration dictionary
    """
    db_type = os.getenv("DB_TYPE", "sqlite").lower()
    
    if db_type == "sqlite":
        return {
            "type": "sqlite",
            "path": os.getenv("DB_PATH", "data/index.db")
        }
    elif db_type == "postgresql":
        return {
            "type": "postgresql",
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", "5432")),
            "database": os.getenv("DB_NAME", "ai_actuarial"),
            "username": os.getenv("DB_USER", "postgres"),
            "password": os.getenv("DB_PASSWORD", "")
        }
    else:
        raise ValueError(f"Unsupported DB_TYPE: {db_type}")
