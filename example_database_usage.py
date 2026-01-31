#!/usr/bin/env python3
"""
Example: Using the Database Backend Abstraction

This example demonstrates how to use both SQLite and PostgreSQL backends.
"""

import yaml
from ai_actuarial.storage_factory import create_storage_from_config


def example_legacy_mode():
    """Example: Legacy mode using direct database path (SQLite)."""
    print("=" * 60)
    print("Example 1: Legacy Mode (Backward Compatible)")
    print("=" * 60)
    
    # This is how the application was used before
    # No changes needed to existing code!
    config = {
        "paths": {
            "db": "data/index.db"
        }
    }
    
    storage = create_storage_from_config(config)
    print(f"✓ Created storage: {type(storage).__name__}")
    print(f"  Using database: {storage.db_path}")
    storage.close()
    print()


def example_sqlite_explicit():
    """Example: Explicit SQLite configuration."""
    print("=" * 60)
    print("Example 2: Explicit SQLite Configuration")
    print("=" * 60)
    
    config = {
        "database": {
            "type": "sqlite",
            "path": "data/my_custom.db"
        }
    }
    
    storage = create_storage_from_config(config)
    print(f"✓ Created storage: {type(storage).__name__}")
    print(f"  Database type: SQLite")
    print(f"  Database path: data/my_custom.db")
    storage.close()
    print()


def example_postgresql_config():
    """Example: PostgreSQL configuration."""
    print("=" * 60)
    print("Example 3: PostgreSQL Configuration")
    print("=" * 60)
    
    # This configuration would be in config/sites.yaml
    config = {
        "database": {
            "type": "postgresql",
            "host": "localhost",
            "port": 5432,
            "database": "ai_actuarial",
            "username": "postgres",
            "password": "secret"  # Use environment variables in production!
        }
    }
    
    print("Configuration:")
    print(f"  Type: PostgreSQL")
    print(f"  Host: {config['database']['host']}")
    print(f"  Port: {config['database']['port']}")
    print(f"  Database: {config['database']['database']}")
    print(f"  Username: {config['database']['username']}")
    print()
    print("Note: To use this configuration:")
    print("  1. Install PostgreSQL")
    print("  2. Create the database")
    print("  3. Add the 'database' section to config/sites.yaml")
    print()


def example_from_yaml():
    """Example: Loading configuration from YAML file."""
    print("=" * 60)
    print("Example 4: Loading from sites.yaml")
    print("=" * 60)
    
    # Load actual configuration
    with open("config/sites.yaml", "r") as f:
        config = yaml.safe_load(f)
    
    # This automatically detects whether to use SQLite or PostgreSQL
    # based on what's configured in the YAML file
    storage = create_storage_from_config(config)
    print(f"✓ Created storage from config/sites.yaml: {type(storage).__name__}")
    
    # Use storage as normal
    # storage.insert_file(...)
    # storage.file_exists(...)
    # etc.
    
    storage.close()
    print()


def example_environment_variables():
    """Example: Using environment variables for PostgreSQL."""
    print("=" * 60)
    print("Example 5: Environment Variables (Production)")
    print("=" * 60)
    
    print("In production, use environment variables for database credentials:")
    print()
    print("  export DB_TYPE=postgresql")
    print("  export DB_HOST=prod-db.example.com")
    print("  export DB_PORT=5432")
    print("  export DB_NAME=ai_actuarial_prod")
    print("  export DB_USER=app_user")
    print("  export DB_PASSWORD=<strong-password>")
    print()
    print("Then in config/sites.yaml:")
    print("  database:")
    print("    type: postgresql")
    print("    host: ${DB_HOST}")
    print("    port: ${DB_PORT}")
    print("    database: ${DB_NAME}")
    print("    username: ${DB_USER}")
    print("    password: ${DB_PASSWORD}")
    print()


def main():
    """Run all examples."""
    print("\n")
    print("=" * 60)
    print("DATABASE BACKEND ABSTRACTION EXAMPLES")
    print("=" * 60)
    print()
    
    example_legacy_mode()
    example_sqlite_explicit()
    example_postgresql_config()
    example_from_yaml()
    example_environment_variables()
    
    print("=" * 60)
    print("For more information, see DATABASE_BACKEND_GUIDE.md")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
