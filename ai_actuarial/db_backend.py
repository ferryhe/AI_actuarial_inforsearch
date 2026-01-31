"""Database backend abstraction layer for SQLite and PostgreSQL support."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

from .db_models import Base, get_current_timestamp


class DatabaseBackend(ABC):
    """Abstract base class for database backends."""
    
    def __init__(self, connection_string: str) -> None:
        """Initialize database backend.
        
        Args:
            connection_string: Database connection string
        """
        self.connection_string = connection_string
        self.engine: Engine | None = None
        self.SessionLocal: sessionmaker | None = None
        self._tx_depth = 0
        self._session: Session | None = None
        
    @abstractmethod
    def connect(self) -> None:
        """Connect to the database and initialize schema."""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close database connection."""
        pass
    
    @abstractmethod
    def _ensure_columns(self, table: str, columns: dict[str, str]) -> None:
        """Ensure columns exist in the table (for migrations)."""
        pass
    
    @abstractmethod
    def _migrate_catalog_items(self) -> None:
        """Migrate catalog items from legacy schema."""
        pass
    
    def get_session(self) -> Session:
        """Get the current session."""
        if self._session is None:
            if self.SessionLocal is None:
                raise RuntimeError("Database not connected")
            self._session = self.SessionLocal()
        return self._session
    
    def _maybe_commit(self) -> None:
        """Commit if not in a transaction."""
        if self._tx_depth == 0 and self._session is not None:
            self._session.commit()
    
    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        session = self.get_session()
        sp_name = None
        if self._tx_depth == 0:
            # SQLAlchemy sessions auto-begin transactions, so we don't need to call begin()
            # explicitly unless we're using legacy autocommit mode
            if not session.in_transaction():
                session.begin()
        else:
            sp_name = f"sp_{self._tx_depth}"
            session.begin_nested()
        self._tx_depth += 1
        try:
            yield session
        except Exception:
            self._tx_depth -= 1
            session.rollback()
            raise
        else:
            self._tx_depth -= 1
            if sp_name is None:
                session.commit()
    
    def now(self) -> str:
        """Get current timestamp."""
        return get_current_timestamp()


class SQLiteBackend(DatabaseBackend):
    """SQLite database backend."""
    
    def connect(self) -> None:
        """Connect to SQLite database and initialize schema."""
        # Ensure directory exists (if a directory is specified)
        db_path = self.connection_string.replace("sqlite:///", "")
        dir_path = os.path.dirname(db_path)
        if dir_path:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
        
        # Create engine with SQLite-specific settings
        self.engine = create_engine(
            self.connection_string,
            connect_args={"check_same_thread": False},
            echo=False
        )
        
        # Enable WAL mode for better concurrency
        with self.engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL;"))
            conn.commit()
        
        # Create tables
        Base.metadata.create_all(self.engine)
        
        # Create session factory
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        # Initialize session
        self._session = self.SessionLocal()
        
        # Run migrations
        self._ensure_columns(
            "files",
            {
                "source_page_url": "TEXT",
                "original_filename": "TEXT",
                "bytes": "INTEGER",
                "content_type": "TEXT",
                "last_modified": "TEXT",
                "etag": "TEXT",
                "published_time": "TEXT",
                "crawl_time": "TEXT",
            },
        )
        self._ensure_columns(
            "catalog_items",
            {
                "sha256": "TEXT",
                "pipeline_version": "TEXT",
                "processed_at": "TEXT",
                "status": "TEXT DEFAULT 'ok'",
                "error": "TEXT",
                "keywords": "TEXT",
                "summary": "TEXT",
                "category": "TEXT",
                "updated_at": "TEXT",
            },
        )
        self._migrate_catalog_items()
    
    def close(self) -> None:
        """Close database connection."""
        if self._session is not None:
            self._session.close()
            self._session = None
        if self.engine is not None:
            self.engine.dispose()
    
    def _ensure_columns(self, table: str, columns: dict[str, str]) -> None:
        """Ensure columns exist in the table (for SQLite migrations)."""
        # Validate table name to prevent SQL injection
        allowed_tables = {"files", "pages", "blobs", "catalog_items"}
        if table not in allowed_tables:
            raise ValueError(f"Invalid table name: {table}")
        
        # Use SQLAlchemy inspector instead of raw SQL
        inspector = inspect(self.engine)
        existing_columns = {col['name'] for col in inspector.get_columns(table)}
        
        with self.engine.connect() as conn:
            for name, col_type in columns.items():
                if name not in existing_columns:
                    # Validate column name (alphanumeric and underscores only)
                    if not name.replace("_", "").isalnum():
                        raise ValueError(f"Invalid column name: {name}")
                    # Note: DDL statements (ALTER TABLE) cannot use parameterized queries for
                    # identifiers (table/column names). String formatting is safe here because:
                    # 1. Table name is validated against whitelist above
                    # 2. Column name is validated to be alphanumeric + underscores
                    # 3. Column type is from trusted source (migration code)
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"))
            conn.commit()
    
    def _migrate_catalog_items(self) -> None:
        """Migrate catalog items from legacy schema."""
        # Use SQLAlchemy inspector instead of raw SQL
        inspector = inspect(self.engine)
        existing_columns = {col['name'] for col in inspector.get_columns('catalog_items')}
        
        with self.engine.connect() as conn:
            # Map legacy columns into the unified schema
            if "sha256" in existing_columns and "file_sha256" in existing_columns:
                conn.execute(text("""
                    UPDATE catalog_items
                    SET sha256 = file_sha256
                    WHERE (sha256 IS NULL OR sha256 = '') AND file_sha256 IS NOT NULL
                """))
            if "pipeline_version" in existing_columns:
                if "extractor_version" in existing_columns:
                    conn.execute(text("""
                        UPDATE catalog_items
                        SET pipeline_version = extractor_version
                        WHERE (pipeline_version IS NULL OR pipeline_version = '')
                          AND extractor_version IS NOT NULL
                    """))
                if "catalog_version" in existing_columns:
                    conn.execute(text("""
                        UPDATE catalog_items
                        SET pipeline_version = catalog_version
                        WHERE (pipeline_version IS NULL OR pipeline_version = '')
                          AND catalog_version IS NOT NULL
                    """))
            if "keywords" in existing_columns and "keywords_json" in existing_columns:
                conn.execute(text("""
                    UPDATE catalog_items
                    SET keywords = keywords_json
                    WHERE (keywords IS NULL OR keywords = '') AND keywords_json IS NOT NULL
                """))
            conn.commit()


class PostgreSQLBackend(DatabaseBackend):
    """PostgreSQL database backend."""
    
    def connect(self) -> None:
        """Connect to PostgreSQL database and initialize schema."""
        # Create engine
        self.engine = create_engine(
            self.connection_string,
            echo=False,
            pool_pre_ping=True  # Verify connections before using them
        )
        
        # Create tables
        Base.metadata.create_all(self.engine)
        
        # Create session factory
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        # Initialize session
        self._session = self.SessionLocal()
        
        # Run migrations (PostgreSQL-specific)
        self._ensure_columns(
            "files",
            {
                "source_page_url": "TEXT",
                "original_filename": "TEXT",
                "bytes": "INTEGER",
                "content_type": "TEXT",
                "last_modified": "TEXT",
                "etag": "TEXT",
                "published_time": "TEXT",
                "crawl_time": "TEXT",
            },
        )
        self._ensure_columns(
            "catalog_items",
            {
                "sha256": "TEXT",
                "pipeline_version": "TEXT",
                "processed_at": "TEXT",
                "status": "TEXT",
                "error": "TEXT",
                "keywords": "TEXT",
                "summary": "TEXT",
                "category": "TEXT",
                "updated_at": "TEXT",
            },
        )
        self._migrate_catalog_items()
    
    def close(self) -> None:
        """Close database connection."""
        if self._session is not None:
            self._session.close()
            self._session = None
        if self.engine is not None:
            self.engine.dispose()
    
    def _ensure_columns(self, table: str, columns: dict[str, str]) -> None:
        """Ensure columns exist in the table (for PostgreSQL migrations)."""
        # Validate table name to prevent SQL injection
        allowed_tables = {"files", "pages", "blobs", "catalog_items"}
        if table not in allowed_tables:
            raise ValueError(f"Invalid table name: {table}")
        
        # Use SQLAlchemy inspector instead of raw SQL with string interpolation
        inspector = inspect(self.engine)
        existing_columns = {col['name'] for col in inspector.get_columns(table)}
        
        with self.engine.connect() as conn:
            for name, col_type in columns.items():
                if name not in existing_columns:
                    # Validate column name (alphanumeric and underscores only)
                    if not name.replace("_", "").isalnum():
                        raise ValueError(f"Invalid column name: {name}")
                    # Note: DDL statements (ALTER TABLE) cannot use parameterized queries for
                    # identifiers (table/column names). String formatting is safe here because:
                    # 1. Table name is validated against whitelist above
                    # 2. Column name is validated to be alphanumeric + underscores
                    # 3. Column type is from trusted source (migration code)
                    # PostgreSQL uses different syntax for ALTER TABLE
                    col_def = col_type.replace("DEFAULT 'ok'", "")
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {col_def}"))
                    if "DEFAULT" in col_type:
                        default_value = col_type.split("DEFAULT")[1].strip()
                        conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN {name} SET DEFAULT {default_value}"))
            conn.commit()
    
    def _migrate_catalog_items(self) -> None:
        """Migrate catalog items from legacy schema."""
        # Use SQLAlchemy inspector instead of raw SQL
        inspector = inspect(self.engine)
        existing_columns = {col['name'] for col in inspector.get_columns('catalog_items')}
        
        with self.engine.connect() as conn:
            # Map legacy columns into the unified schema
            if "sha256" in existing_columns and "file_sha256" in existing_columns:
                conn.execute(text("""
                    UPDATE catalog_items
                    SET sha256 = file_sha256
                    WHERE (sha256 IS NULL OR sha256 = '') AND file_sha256 IS NOT NULL
                """))
            if "pipeline_version" in existing_columns:
                if "extractor_version" in existing_columns:
                    conn.execute(text("""
                        UPDATE catalog_items
                        SET pipeline_version = extractor_version
                        WHERE (pipeline_version IS NULL OR pipeline_version = '')
                          AND extractor_version IS NOT NULL
                    """))
                if "catalog_version" in existing_columns:
                    conn.execute(text("""
                        UPDATE catalog_items
                        SET pipeline_version = catalog_version
                        WHERE (pipeline_version IS NULL OR pipeline_version = '')
                          AND catalog_version IS NOT NULL
                    """))
            if "keywords" in existing_columns and "keywords_json" in existing_columns:
                conn.execute(text("""
                    UPDATE catalog_items
                    SET keywords = keywords_json
                    WHERE (keywords IS NULL OR keywords = '') AND keywords_json IS NOT NULL
                """))
            conn.commit()


def create_backend(db_config: dict[str, Any]) -> DatabaseBackend:
    """Factory function to create the appropriate database backend.
    
    Args:
        db_config: Database configuration dictionary with keys:
            - type: 'sqlite' or 'postgresql'
            - path: for SQLite (e.g., 'data/index.db')
            - host: for PostgreSQL
            - port: for PostgreSQL
            - database: for PostgreSQL
            - username: for PostgreSQL
            - password: for PostgreSQL
            
    Returns:
        DatabaseBackend instance
    """
    from urllib.parse import quote_plus
    
    db_type = db_config.get("type", "sqlite").lower()
    
    if db_type == "sqlite":
        db_path = db_config.get("path", "data/index.db")
        connection_string = f"sqlite:///{db_path}"
        return SQLiteBackend(connection_string)
    
    elif db_type == "postgresql":
        host = db_config.get("host", "localhost")
        port = db_config.get("port", 5432)
        database = db_config.get("database", "ai_actuarial")
        username = db_config.get("username", "postgres")
        password = db_config.get("password", "")
        
        # URL-encode username and password to handle special characters
        username_encoded = quote_plus(username)
        password_encoded = quote_plus(password)
        
        connection_string = f"postgresql://{username_encoded}:{password_encoded}@{host}:{port}/{database}"
        return PostgreSQLBackend(connection_string)
    
    else:
        raise ValueError(f"Unsupported database type: {db_type}")
