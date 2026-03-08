from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
import hashlib


class Storage:
    # Allowlist for schema/migration helpers that interpolate table names into PRAGMA.
    _SCHEMA_TABLES = frozenset(
        {
            "files",
            "pages",
            "blobs",
            "catalog_items",
            "auth_tokens",
            "audit_events",
            "api_tokens",
            "chunk_profiles",
            "file_chunk_sets",
            "global_chunks",
            "chunk_embeddings",
            "kb_chunk_bindings",
            "kb_index_versions",
            "kb_index_items",
            "users",
            "user_quotas",
            "user_activity_logs",
        }
    )

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(os.path.dirname(db_path)).mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._tx_depth = 0
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY,
                url TEXT UNIQUE,
                sha256 TEXT,
                title TEXT,
                source_site TEXT,
                source_page_url TEXT,
                original_filename TEXT,
                local_path TEXT,
                bytes INTEGER,
                content_type TEXT,
                last_modified TEXT,
                etag TEXT,
                published_time TEXT,
                first_seen TEXT,
                last_seen TEXT,
                crawl_time TEXT
            )
            """
        )
        # Migrate: Check if deleted_at exists, if not add it
        try:
            self._conn.execute("SELECT deleted_at FROM files LIMIT 1")
        except sqlite3.OperationalError:
             self._conn.execute("ALTER TABLE files ADD COLUMN deleted_at TEXT")

        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY,
                url TEXT UNIQUE,
                last_seen TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blobs (
                sha256 TEXT PRIMARY KEY,
                canonical_path TEXT,
                bytes INTEGER,
                content_type TEXT,
                first_seen TEXT,
                last_seen TEXT
            )
            """
        )
        # catalog_items: incremental catalog state tracking
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS catalog_items (
                file_url TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL,
                pipeline_version TEXT NOT NULL,
                processed_at TEXT,
                status TEXT NOT NULL DEFAULT 'ok',
                error TEXT,
                keywords TEXT,
                summary TEXT,
                category TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_catalog_items_status ON catalog_items(status)
            """
        )

        # auth_tokens: token-based authentication for public deployments
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_tokens (
                id INTEGER PRIMARY KEY,
                subject TEXT NOT NULL,
                group_name TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT,
                last_used_at TEXT,
                revoked_at TEXT,
                expires_at TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_auth_tokens_active ON auth_tokens(is_active)
            """
        )

        # audit_events: security/audit log for sensitive operations (optional)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY,
                token_id INTEGER,
                event_type TEXT NOT NULL,
                resource TEXT,
                detail TEXT,
                ip TEXT,
                created_at TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_events_created_at ON audit_events(created_at)
            """
        )

        # api_tokens: encrypted API keys for LLM and other external service providers
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'llm',
                api_key_encrypted TEXT NOT NULL,
                api_base_url TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT,
                updated_at TEXT,
                notes TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_api_tokens_provider_category
            ON api_tokens(provider, category)
            """
        )
        self._conn.commit()
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
                "file_sha256": "TEXT",
                "sha256": "TEXT",
                "catalog_version": "TEXT",
                "pipeline_version": "TEXT",
                "processed_at": "TEXT",
                "status": "TEXT DEFAULT 'ok'",
                "error": "TEXT",
                "keywords": "TEXT",
                "summary": "TEXT",
                "category": "TEXT",
                "updated_at": "TEXT",
                "markdown_content": "TEXT",
                "markdown_updated_at": "TEXT",
                "markdown_source": "TEXT",
                "rag_chunk_count": "INTEGER DEFAULT 0",
                "rag_indexed_at": "TEXT",
            },
        )
        self._migrate_catalog_items()

        # Minimal auth schema migrations (future-proofing)
        self._ensure_columns(
            "auth_tokens",
            {
                "subject": "TEXT",
                "group_name": "TEXT",
                "token_hash": "TEXT",
                "is_active": "INTEGER",
                "created_at": "TEXT",
                "last_used_at": "TEXT",
                "revoked_at": "TEXT",
                "expires_at": "TEXT",
            },
        )

        self._ensure_columns(
            "audit_events",
            {
                "token_id": "INTEGER",
                "event_type": "TEXT",
                "resource": "TEXT",
                "detail": "TEXT",
                "ip": "TEXT",
                "created_at": "TEXT",
            },
        )
        self._init_global_chunk_schema()
        self._init_user_management_schema()

    def _init_user_management_schema(self) -> None:
        """Initialize schema for email-based user management with quotas."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'registered',
                is_active INTEGER NOT NULL DEFAULT 1,
                email_verified INTEGER NOT NULL DEFAULT 0,
                display_name TEXT,
                notes TEXT,
                created_at TEXT,
                last_login_at TEXT,
                email_verified_at TEXT
            )
            """
        )
        # email has UNIQUE constraint above which already creates an index.
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)"
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_quotas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                ip_address TEXT,
                quota_date TEXT NOT NULL,
                ai_chat_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        # Partial unique indexes allow INSERT OR IGNORE / ON CONFLICT semantics
        # while tolerating NULLs in the non-keyed column.
        self._conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_uq_user_quotas_user
            ON user_quotas(user_id, quota_date)
            WHERE user_id IS NOT NULL
            """
        )
        self._conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_uq_user_quotas_ip
            ON user_quotas(ip_address, quota_date)
            WHERE ip_address IS NOT NULL
            """
        )
        # Plain composite indexes (kept for query planner on NULL-keyed lookups)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_quotas_user_date ON user_quotas(user_id, quota_date)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_quotas_ip_date ON user_quotas(ip_address, quota_date)"
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                ip_address TEXT,
                action TEXT NOT NULL,
                resource TEXT,
                detail TEXT,
                created_at TEXT
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_activity_user ON user_activity_logs(user_id)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_activity_created ON user_activity_logs(created_at)"
        )
        self._conn.commit()

    def _init_global_chunk_schema(self) -> None:
        """Initialize schema for global chunk generation and KB composition."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunk_profiles (
                profile_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                config_hash TEXT NOT NULL UNIQUE,
                config_json TEXT NOT NULL,
                chunk_size INTEGER NOT NULL,
                chunk_overlap INTEGER NOT NULL,
                splitter TEXT NOT NULL,
                tokenizer TEXT NOT NULL,
                version TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS file_chunk_sets (
                chunk_set_id TEXT PRIMARY KEY,
                file_url TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                markdown_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ready',
                chunk_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(file_url, profile_id, markdown_hash),
                FOREIGN KEY(file_url) REFERENCES files(url) ON DELETE CASCADE,
                FOREIGN KEY(profile_id) REFERENCES chunk_profiles(profile_id) ON DELETE CASCADE
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS global_chunks (
                chunk_id TEXT PRIMARY KEY,
                chunk_set_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                token_count INTEGER NOT NULL DEFAULT 0,
                section_hierarchy TEXT,
                content_hash TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(chunk_set_id, chunk_index),
                FOREIGN KEY(chunk_set_id) REFERENCES file_chunk_sets(chunk_set_id) ON DELETE CASCADE
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunk_embeddings (
                chunk_id TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                dim INTEGER NOT NULL DEFAULT 0,
                vector_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (chunk_id, embedding_model),
                FOREIGN KEY(chunk_id) REFERENCES global_chunks(chunk_id) ON DELETE CASCADE
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kb_chunk_bindings (
                kb_id TEXT NOT NULL,
                file_url TEXT NOT NULL,
                chunk_set_id TEXT NOT NULL,
                bound_at TEXT NOT NULL,
                bound_by TEXT,
                binding_mode TEXT NOT NULL DEFAULT 'pin',
                target_profile_id TEXT,
                PRIMARY KEY (kb_id, file_url, chunk_set_id),
                FOREIGN KEY(file_url) REFERENCES files(url) ON DELETE CASCADE,
                FOREIGN KEY(chunk_set_id) REFERENCES file_chunk_sets(chunk_set_id) ON DELETE CASCADE
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kb_index_versions (
                index_version_id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                index_type TEXT NOT NULL,
                status TEXT NOT NULL,
                artifact_path TEXT,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                built_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kb_index_items (
                index_version_id TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                PRIMARY KEY (index_version_id, chunk_id),
                FOREIGN KEY(index_version_id) REFERENCES kb_index_versions(index_version_id) ON DELETE CASCADE,
                FOREIGN KEY(chunk_id) REFERENCES global_chunks(chunk_id) ON DELETE CASCADE
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_file_chunk_sets_file_url
            ON file_chunk_sets(file_url)
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_file_chunk_sets_profile_id
            ON file_chunk_sets(profile_id)
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_global_chunks_chunk_set_id
            ON global_chunks(chunk_set_id)
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_kb_chunk_bindings_kb_id
            ON kb_chunk_bindings(kb_id)
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_kb_chunk_bindings_file_url
            ON kb_chunk_bindings(file_url)
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_kb_index_versions_kb_id
            ON kb_index_versions(kb_id)
            """
        )
        self._ensure_columns(
            "kb_chunk_bindings",
            {
                "binding_mode": "TEXT NOT NULL DEFAULT 'pin'",
                "target_profile_id": "TEXT",
            },
        )
        self._conn.commit()

    def _ensure_columns(self, table: str, columns: dict[str, str]) -> None:
        if table not in self._SCHEMA_TABLES:
            raise ValueError(f"Invalid table name for schema migration: {table!r}")
        cur = self._conn.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cur.fetchall()}
        for name, col_type in columns.items():
            if name not in existing:
                self._conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"
                )
        self._conn.commit()

    def _maybe_commit(self) -> None:
        if self._tx_depth == 0:
            self._conn.commit()

    @contextmanager
    def transaction(self):
        sp_name = None
        if self._tx_depth == 0:
            self._conn.execute("BEGIN")
        else:
            sp_name = f"sp_{self._tx_depth}"
            self._conn.execute(f"SAVEPOINT {sp_name}")
        self._tx_depth += 1
        try:
            yield
        except Exception:
            self._tx_depth -= 1
            if sp_name is None:
                self._conn.rollback()
            else:
                self._conn.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
                self._conn.execute(f"RELEASE SAVEPOINT {sp_name}")
            raise
        else:
            self._tx_depth -= 1
            if sp_name is None:
                self._conn.commit()
            else:
                self._conn.execute(f"RELEASE SAVEPOINT {sp_name}")

    def _migrate_catalog_items(self) -> None:
        cur = self._conn.execute("PRAGMA table_info(catalog_items)")
        existing = {row[1] for row in cur.fetchall()}

        # Map legacy columns into the unified schema without dropping data.
        if "sha256" in existing and "file_sha256" in existing:
            self._conn.execute(
                """
                UPDATE catalog_items
                SET sha256 = file_sha256
                WHERE (sha256 IS NULL OR sha256 = '') AND file_sha256 IS NOT NULL
                """
            )
        if "pipeline_version" in existing:
            if "extractor_version" in existing:
                self._conn.execute(
                    """
                    UPDATE catalog_items
                    SET pipeline_version = extractor_version
                    WHERE (pipeline_version IS NULL OR pipeline_version = '')
                      AND extractor_version IS NOT NULL
                    """
                )
            if "catalog_version" in existing:
                self._conn.execute(
                    """
                    UPDATE catalog_items
                    SET pipeline_version = catalog_version
                    WHERE (pipeline_version IS NULL OR pipeline_version = '')
                      AND catalog_version IS NOT NULL
                    """
                )
        if "keywords" in existing and "keywords_json" in existing:
            self._conn.execute(
                """
                UPDATE catalog_items
                SET keywords = keywords_json
                WHERE (keywords IS NULL OR keywords = '') AND keywords_json IS NOT NULL
                """
            )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -----------------------------
    # Auth tokens (public deployments)
    # -----------------------------

    def get_auth_token_by_id(self, token_id: int) -> dict | None:
        cur = self._conn.execute(
            """
            SELECT id, subject, group_name, is_active, created_at, last_used_at, revoked_at, expires_at
            FROM auth_tokens
            WHERE id = ?
            """,
            (int(token_id),),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "subject": row[1],
            "group_name": row[2],
            "is_active": bool(row[3]),
            "created_at": row[4],
            "last_used_at": row[5],
            "revoked_at": row[6],
            "expires_at": row[7],
        }

    def get_auth_token_by_hash(self, token_hash: str) -> dict | None:
        cur = self._conn.execute(
            """
            SELECT id, subject, group_name, is_active, created_at, last_used_at, revoked_at, expires_at
            FROM auth_tokens
            WHERE token_hash = ?
            """,
            (str(token_hash),),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "subject": row[1],
            "group_name": row[2],
            "is_active": bool(row[3]),
            "created_at": row[4],
            "last_used_at": row[5],
            "revoked_at": row[6],
            "expires_at": row[7],
        }

    def list_auth_tokens(self) -> list[dict]:
        cur = self._conn.execute(
            """
            SELECT id, subject, group_name, is_active, created_at, last_used_at, revoked_at, expires_at
            FROM auth_tokens
            ORDER BY id DESC
            """
        )
        out: list[dict] = []
        for row in cur.fetchall():
            out.append(
                {
                    "id": row[0],
                    "subject": row[1],
                    "group_name": row[2],
                    "is_active": bool(row[3]),
                    "created_at": row[4],
                    "last_used_at": row[5],
                    "revoked_at": row[6],
                    "expires_at": row[7],
                }
            )
        return out

    def create_auth_token(
        self,
        *,
        subject: str,
        group_name: str,
        token_hash: str,
        expires_at: str | None = None,
    ) -> int:
        ts = self.now()
        cur = self._conn.execute(
            """
            INSERT INTO auth_tokens (subject, group_name, token_hash, is_active, created_at, expires_at)
            VALUES (?, ?, ?, 1, ?, ?)
            """,
            (str(subject), str(group_name), str(token_hash), ts, expires_at),
        )
        self._maybe_commit()
        return int(cur.lastrowid)

    def upsert_auth_token_by_hash(
        self,
        *,
        subject: str,
        group_name: str,
        token_hash: str,
        is_active: bool = True,
    ) -> int:
        ts = self.now()
        self._conn.execute(
            """
            INSERT INTO auth_tokens (subject, group_name, token_hash, is_active, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(token_hash) DO UPDATE SET
                subject=excluded.subject,
                group_name=excluded.group_name,
                is_active=excluded.is_active
            """,
            (str(subject), str(group_name), str(token_hash), 1 if is_active else 0, ts),
        )
        self._maybe_commit()
        # Fetch id
        token = self.get_auth_token_by_hash(token_hash)
        if not token:
            raise RuntimeError("Failed to upsert auth token")
        return int(token["id"])

    def revoke_auth_token(self, token_id: int) -> bool:
        ts = self.now()
        cur = self._conn.execute(
            """
            UPDATE auth_tokens
            SET is_active = 0,
                revoked_at = ?
            WHERE id = ?
            """,
            (ts, int(token_id)),
        )
        self._maybe_commit()
        return cur.rowcount > 0

    def touch_auth_token_last_used(self, token_id: int) -> None:
        ts = self.now()
        self._conn.execute(
            "UPDATE auth_tokens SET last_used_at = ? WHERE id = ?",
            (ts, int(token_id)),
        )
        self._maybe_commit()

    # ---------------------------------------------------------------------------
    # LLM provider API token management
    # ---------------------------------------------------------------------------

    _LLM_TOKEN_COLS = (
        "id", "provider", "category", "api_key_encrypted",
        "api_base_url", "status", "created_at", "updated_at", "notes",
    )

    def upsert_llm_provider(
        self,
        provider: str,
        api_key_encrypted: str,
        base_url: str | None = None,
        notes: str | None = None,
        category: str = "llm",
    ) -> None:
        """Insert or update an LLM provider API token.

        Args:
            provider: Provider identifier (e.g. 'openai', 'mistral').
            api_key_encrypted: Fernet-encrypted API key string.
            base_url: Optional custom API base URL.
            notes: Optional notes.
            category: Token category (default 'llm').
        """
        ts = self.now()
        self._conn.execute(
            """
            INSERT INTO api_tokens
                (provider, category, api_key_encrypted, api_base_url, status, created_at, updated_at, notes)
            VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
            ON CONFLICT(provider, category) DO UPDATE SET
                api_key_encrypted = excluded.api_key_encrypted,
                api_base_url = excluded.api_base_url,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (provider, category, api_key_encrypted, base_url, ts, ts, notes),
        )
        self._maybe_commit()

    def get_llm_provider(
        self, provider: str, category: str = "llm"
    ) -> dict | None:
        """Get a single LLM provider record.

        Args:
            provider: Provider identifier.
            category: Token category (default 'llm').

        Returns:
            Dictionary with provider data or None if not found.
        """
        cur = self._conn.execute(
            "SELECT id, provider, category, api_key_encrypted, api_base_url, status, "
            "created_at, updated_at, notes FROM api_tokens WHERE provider=? AND category=?",
            (provider, category),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return dict(zip(self._LLM_TOKEN_COLS, row))

    def list_llm_providers(self, category: str = "llm") -> list[dict]:
        """List all LLM provider records for the given category.

        Args:
            category: Token category (default 'llm').

        Returns:
            List of provider dictionaries ordered by provider name.
        """
        cur = self._conn.execute(
            "SELECT id, provider, category, api_key_encrypted, api_base_url, status, "
            "created_at, updated_at, notes FROM api_tokens WHERE category=? ORDER BY provider",
            (category,),
        )
        return [dict(zip(self._LLM_TOKEN_COLS, row)) for row in cur.fetchall()]

    def delete_llm_provider(self, provider: str, category: str = "llm") -> bool:
        """Delete an LLM provider record.

        Args:
            provider: Provider identifier.
            category: Token category (default 'llm').

        Returns:
            True if a record was deleted, False if not found.
        """
        cur = self._conn.execute(
            "DELETE FROM api_tokens WHERE provider=? AND category=?",
            (provider, category),
        )
        self._maybe_commit()
        return cur.rowcount > 0

    def file_exists_by_hash(self, sha256: str) -> bool:
        """Check if a file with the given hash already exists in the database.
        
        Args:
            sha256: The SHA256 hash of the file content.
            
        Returns:
            True if a file with this hash exists, False otherwise.
        """
        cur = self._conn.execute(
            "SELECT 1 FROM blobs WHERE sha256 = ?", (sha256,)
        )
        if cur.fetchone():
            return True
            
        # Also check files table as fallback
        cur = self._conn.execute(
            "SELECT 1 FROM files WHERE sha256 = ?", (sha256,)
        )
        return cur.fetchone() is not None

    def now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def file_exists(self, url: str) -> bool:
        cur = self._conn.execute("SELECT 1 FROM files WHERE url = ? LIMIT 1", (url,))
        return cur.fetchone() is not None

    def get_file_by_url(self, url: str) -> dict | None:
        """Get file record by URL.
        
        Args:
            url: File URL
            
        Returns:
            File record dict or None if not found
        """
        cur = self._conn.execute(
            "SELECT * FROM files WHERE url = ? LIMIT 1", (url,)
        )
        row = cur.fetchone()
        if not row:
            return None
        
        columns = [desc[0] for desc in cur.description]
        return dict(zip(columns, row))
    
    def get_file_by_sha256(self, sha256: str) -> dict | None:
        """Get file record by SHA256 hash.
        
        Args:
            sha256: File SHA256 hash
            
        Returns:
            File record dict or None if not found
        """
        cur = self._conn.execute(
            "SELECT * FROM files WHERE sha256 = ? LIMIT 1", (sha256,)
        )
        row = cur.fetchone()
        if not row:
            return None
        
        columns = [desc[0] for desc in cur.description]
        return dict(zip(columns, row))
    
    def insert_file(
        self,
        url: str,
        sha256: str,
        title: str | None,
        source_site: str,
        source_page_url: str | None,
        original_filename: str | None,
        local_path: str,
        bytes: int | None,
        content_type: str | None,
        last_modified: str | None = None,
        etag: str | None = None,
        published_time: str | None = None,
    ) -> None:
        """Insert a new file record (raises error if URL exists).
        
        Args:
            url: File URL
            sha256: SHA256 hash
            title: File title
            source_site: Source site name
            source_page_url: URL of the page where file was found
            original_filename: Original filename
            local_path: Path to downloaded file
            bytes: File size in bytes
            content_type: Content type
            last_modified: Last modified timestamp
            etag: ETag header value
            published_time: Published time
        """
        # Note: Parameter 'bytes' shadows built-in, but this is intentional
        # to match the database column name 'bytes' for consistency
        ts = self.now()
        self._conn.execute(
            """
            INSERT INTO files (
                url, sha256, title, source_site, source_page_url, original_filename,
                local_path, bytes, content_type, last_modified, etag, published_time,
                first_seen, last_seen, crawl_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                url,
                sha256,
                title,
                source_site,
                source_page_url,
                original_filename,
                local_path,
                bytes,
                content_type,
                last_modified,
                etag,
                published_time,
                ts,
                ts,
                ts,
            ),
        )
        self._maybe_commit()

    def upsert_file(
        self,
        url: str,
        sha256: str,
        title: str | None,
        source_site: str,
        source_page_url: str | None,
        original_filename: str | None,
        local_path: str,
        bytes_size: int | None,
        content_type: str | None,
        last_modified: str | None,
        etag: str | None,
        published_time: str | None,
    ) -> None:
        ts = self.now()
        self._conn.execute(
            """
            INSERT INTO files (
                url, sha256, title, source_site, source_page_url, original_filename,
                local_path, bytes, content_type, last_modified, etag, published_time,
                first_seen, last_seen, crawl_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                sha256=excluded.sha256,
                title=excluded.title,
                source_site=excluded.source_site,
                source_page_url=excluded.source_page_url,
                original_filename=excluded.original_filename,
                local_path=excluded.local_path,
                bytes=excluded.bytes,
                content_type=excluded.content_type,
                last_modified=excluded.last_modified,
                etag=excluded.etag,
                published_time=excluded.published_time,
                last_seen=excluded.last_seen,
                crawl_time=excluded.crawl_time
            """,
            (
                url,
                sha256,
                title,
                source_site,
                source_page_url,
                original_filename,
                local_path,
                bytes_size,
                content_type,
                last_modified,
                etag,
                published_time,
                ts,
                ts,
                ts,
            ),
        )
        self._maybe_commit()

    def mark_page_seen(self, url: str) -> None:
        ts = self.now()
        self._conn.execute(
            """
            INSERT INTO pages (url, last_seen)
            VALUES (?, ?)
            ON CONFLICT(url) DO UPDATE SET last_seen=excluded.last_seen
            """,
            (url, ts),
        )
        self._maybe_commit()

    def export_files(self) -> list[dict]:
        cur = self._conn.execute(
            """
            SELECT url, sha256, title, source_site, source_page_url, original_filename,
                   local_path, bytes, content_type, last_modified, etag, published_time,
                   first_seen, last_seen, crawl_time
            FROM files
            ORDER BY last_seen DESC
            """
        )
        rows = cur.fetchall()
        keys = [
            "url",
            "sha256",
            "title",
            "source_site",
            "source_page_url",
            "original_filename",
            "local_path",
            "bytes",
            "content_type",
            "last_modified",
            "etag",
            "published_time",
            "first_seen",
            "last_seen",
            "crawl_time",
        ]
        return [dict(zip(keys, row)) for row in rows]

    # Allowed columns for ORDER BY to prevent SQL injection
    _ALLOWED_ORDER_COLUMNS = frozenset([
        "id", "url", "sha256", "title", "source_site", "local_path",
        "bytes", "first_seen", "last_seen", "crawl_time"
    ])
    
    # Allowed column mapping for query_files_with_catalog ORDER BY
    # Maps user-facing column names to actual SQL column references with table prefix
    _QUERY_ORDER_COLUMN_MAP = {
        'id': 'f.id',
        'url': 'f.url',
        'title': 'f.title',
        'source_site': 'f.source_site',
        'bytes': 'f.bytes',
        'last_seen': 'f.last_seen',
        'crawl_time': 'f.crawl_time',
    }

    def iter_files(
        self,
        site_filter: str | None,
        limit: int | None,
        offset: int = 0,
        require_local_path: bool = True,
        order_by: str = "id",
        only_changed: bool = False,
        extractor_version: str | None = None,
        include_errors: bool = False,
    ) -> list[dict]:
        # Validate order_by to prevent SQL injection
        if order_by not in self._ALLOWED_ORDER_COLUMNS:
            raise ValueError(f"Invalid order_by column: {order_by}. Allowed: {self._ALLOWED_ORDER_COLUMNS}")
        
        filters: list[str] = []
        params: list[object] = []
        if require_local_path:
            filters.append("f.local_path IS NOT NULL AND f.local_path != ''")
        if site_filter:
            tokens = [t.strip().lower() for t in site_filter.split(",") if t.strip()]
            if tokens:
                like_parts = []
                for t in tokens:
                    like_parts.append("LOWER(f.source_site) LIKE ?")
                    params.append(f"%{t}%")
                    like_parts.append("LOWER(f.url) LIKE ?")
                    params.append(f"%{t}%")
                filters.append("(" + " OR ".join(like_parts) + ")")
        join = ""
        if only_changed:
            if not extractor_version:
                raise ValueError("extractor_version is required when only_changed is True")
            join = "LEFT JOIN catalog_items c ON c.file_url = f.url"
            clause = "c.file_url IS NULL OR c.sha256 != f.sha256 OR c.pipeline_version != ?"
            if include_errors:
                clause += " OR c.status IS NULL OR c.status != 'ok'"
            filters.append(f"({clause})")
            params.append(extractor_version)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        cur = self._conn.execute(
            f"""
            SELECT f.url AS url,
                   f.sha256 AS sha256,
                   f.title AS title,
                   f.source_site AS source_site,
                   f.source_page_url AS source_page_url,
                   f.original_filename AS original_filename,
                   f.local_path AS local_path,
                   f.bytes AS bytes,
                   f.content_type AS content_type,
                   f.last_modified AS last_modified,
                   f.etag AS etag,
                   f.published_time AS published_time,
                   f.first_seen AS first_seen,
                   f.last_seen AS last_seen,
                   f.crawl_time AS crawl_time
            FROM files f
            {join}
            {where}
            ORDER BY f.{order_by}
            {limit_clause}
            """,
            tuple(params),
        )
        rows = cur.fetchall()
        keys = [
            "url",
            "sha256",
            "title",
            "source_site",
            "source_page_url",
            "original_filename",
            "local_path",
            "bytes",
            "content_type",
            "last_modified",
            "etag",
            "published_time",
            "first_seen",
            "last_seen",
            "crawl_time",
        ]
        return [dict(zip(keys, row)) for row in rows]

    def get_blob(self, sha256: str) -> dict | None:
        cur = self._conn.execute(
            "SELECT sha256, canonical_path, bytes, content_type FROM blobs WHERE sha256 = ?",
            (sha256,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "sha256": row[0],
            "canonical_path": row[1],
            "bytes": row[2],
            "content_type": row[3],
        }

    def upsert_blob(
        self,
        sha256: str,
        canonical_path: str,
        bytes_size: int | None,
        content_type: str | None,
    ) -> None:
        ts = self.now()
        self._conn.execute(
            """
            INSERT INTO blobs (sha256, canonical_path, bytes, content_type, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(sha256) DO UPDATE SET
                canonical_path=excluded.canonical_path,
                bytes=excluded.bytes,
                content_type=excluded.content_type,
                last_seen=excluded.last_seen
            """,
            (sha256, canonical_path, bytes_size, content_type, ts, ts),
        )
        self._maybe_commit()

    def catalog_item_fresh(
        self,
        url: str,
        sha256: str,
        pipeline_version: str | None = None,
        extractor_version: str | None = None,
    ) -> bool:
        effective_pipeline_version = pipeline_version or extractor_version or ""
        cur = self._conn.execute(
            """
            SELECT 1 FROM catalog_items
            WHERE file_url = ? AND sha256 = ? AND pipeline_version = ? AND status = 'ok'
            """,
            (url, sha256, effective_pipeline_version),
        )
        return cur.fetchone() is not None

    def upsert_catalog_item(
        self,
        item: dict,
        pipeline_version: str | None = None,
        status: str = "ok",
        error: str | None = None,
        processed_at: str | None = None,
        extractor_version: str | None = None,
    ) -> None:
        processed_ts = processed_at or self.now()
        updated_ts = self.now()
        effective_pipeline_version = pipeline_version or extractor_version or ""
        self._conn.execute(
            """
            INSERT INTO catalog_items (
                file_url, sha256, pipeline_version, processed_at, status, error,
                keywords, summary, category, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_url) DO UPDATE SET
                sha256=excluded.sha256,
                pipeline_version=excluded.pipeline_version,
                processed_at=excluded.processed_at,
                status=excluded.status,
                error=excluded.error,
                keywords=excluded.keywords,
                summary=excluded.summary,
                category=excluded.category,
                updated_at=excluded.updated_at
            """,
            (
                item.get("url"),
                item.get("sha256"),
                effective_pipeline_version,
                processed_ts,
                status,
                error,
                json.dumps(item.get("keywords") or [], ensure_ascii=False),
                item.get("summary") or "",
                item.get("category") or "",
                updated_ts,
            ),
        )
        self._maybe_commit()

    def write_last_run(self, output_path: str, items: Iterable[dict]) -> None:
        Path(os.path.dirname(output_path)).mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(list(items), f, ensure_ascii=False, indent=2)
    
    def get_file_count(self, require_local: bool = True) -> int:
        """Get count of files in the database.
        
        Args:
            require_local: Only count files with local_path set
            
        Returns:
            Number of files
        """
        if require_local:
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM files WHERE local_path IS NOT NULL AND local_path != ''"
            )
        else:
            cur = self._conn.execute("SELECT COUNT(*) FROM files")
        return cur.fetchone()[0]
    
    def get_cataloged_count(self) -> int:
        """Get count of successfully cataloged items.
        
        Returns:
            Number of cataloged items with status='ok'
        """
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM catalog_items WHERE status = 'ok'"
        )
        return cur.fetchone()[0]
    
    def get_sources_count(self) -> int:
        """Get count of unique source sites.
        
        Returns:
            Number of unique sources
        """
        cur = self._conn.execute("SELECT COUNT(DISTINCT source_site) FROM files")
        return cur.fetchone()[0]
    
    def get_unique_sources(self) -> list[str]:
        """Get list of unique source sites.
        
        Returns:
            List of source site names
        """
        cur = self._conn.execute("""
            SELECT DISTINCT source_site 
            FROM files 
            WHERE source_site IS NOT NULL 
            ORDER BY source_site
        """)
        return [row[0] for row in cur.fetchall()]
    
    def get_unique_categories(self) -> list[str]:
        """Get list of unique categories from catalog.
        
        Returns:
            List of category names
        """
        cur = self._conn.execute("""
            SELECT DISTINCT category 
            FROM catalog_items 
            WHERE category IS NOT NULL AND category != ''
            ORDER BY category
        """)
        categories: set[str] = set()
        for row in cur.fetchall():
            raw = row[0] or ""
            # Support semicolon-separated multi-categories: "AI; Risk; Pricing"
            parts = [p.strip() for p in raw.split(";") if p.strip()]
            for part in parts:
                categories.add(part)
        return sorted(categories, key=lambda x: x.lower())
    
    def query_files_with_catalog(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        order_by: str = 'last_seen',
        order_dir: str = 'desc',
        query: str = '',
        source: str = '',
        category: str = '',
        include_deleted: bool = False,
    ) -> tuple[list[dict], int]:
        """Query files with catalog information, filtering and pagination.
        
        Args:
            limit: Maximum number of results
            offset: Offset for pagination
            order_by: Column to order by
            order_dir: Order direction ('asc' or 'desc')
            query: Search term for title/filename/url
            source: Source site filter
            category: Category filter
            include_deleted: Whether to include deleted files
            
        Returns:
            Tuple of (list of file dicts, total count)
        """
        # Validate and map order_by column using class-level mapping
        if order_by not in self._QUERY_ORDER_COLUMN_MAP:
            order_by = 'last_seen'  # default
        order_column = self._QUERY_ORDER_COLUMN_MAP[order_by]
        
        # Validate order_dir to prevent SQL injection
        if order_dir.lower() not in ['asc', 'desc']:
            order_dir = 'desc'
        
        # Build query
        filters = []
        
        # When not including deleted files, only show files with valid local_path
        # When including deleted files, show all (deleted files have local_path cleared)
        if not include_deleted:
            filters.append("f.local_path IS NOT NULL AND f.local_path != ''")
            filters.append("f.deleted_at IS NULL")
        
        params = []
        
        if query:
            filters.append("(LOWER(f.title) LIKE ? OR LOWER(f.original_filename) LIKE ? OR LOWER(f.url) LIKE ?)")
            search_term = f"%{query.lower()}%"
            params.extend([search_term, search_term, search_term])
        
        if source:
            filters.append("LOWER(f.source_site) LIKE ?")
            params.append(f"%{source.lower()}%")
        
        # Join with catalog_items if filtering by category (or always for data)
        join_clause = ""
        if category:
            join_clause = "LEFT JOIN catalog_items c ON c.file_url = f.url"
            if category == '__uncategorized__':
                filters.append("(c.category IS NULL OR c.category = '')")
            else:
                # Precise matching for semicolon-separated categories
                # Category format: "AI; Risk & Capital; Pricing"
                # Match exact string, OR start of list, OR end of list, OR middle of list
                filters.append("(c.category = ? OR c.category LIKE ? OR c.category LIKE ? OR c.category LIKE ?)")
                params.extend([category, f"{category};%", f"%; {category}", f"%; {category};%"])
        
        # Avoid empty WHERE which causes SQLite "incomplete input"
        where_clause = " AND ".join(filters) if filters else "1=1"
        
        # Get total count
        count_query = f"""
            SELECT COUNT(*)
            FROM files f
            {join_clause}
            WHERE {where_clause}
        """
        cur = self._conn.execute(count_query, tuple(params))
        total = cur.fetchone()[0]
        
        # Get files with catalog data using validated column mapping
        # Always use LEFT JOIN to return category columns even if not filtering
        if not join_clause:
            join_clause = "LEFT JOIN catalog_items c ON c.file_url = f.url"
        
        order_clause = f"{order_column} {order_dir.upper()}"
        query_sql = f"""
            SELECT f.url, f.sha256, f.title, f.source_site, f.source_page_url,
                   f.original_filename, f.local_path, f.bytes, f.content_type,
                   f.last_modified, f.etag, f.published_time, f.first_seen,
                   f.last_seen, f.crawl_time, f.deleted_at,
                   c.category, c.summary, c.keywords,
                   c.markdown_content, c.markdown_source, c.markdown_updated_at,
                   c.rag_chunk_count, c.rag_indexed_at
            FROM files f
            {join_clause}
            WHERE {where_clause}
            ORDER BY {order_clause}
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        cur = self._conn.execute(query_sql, tuple(params))
        
        files = []
        for row in cur.fetchall():
            file_dict = {
                "url": row[0],
                "sha256": row[1],
                "title": row[2],
                "source_site": row[3],
                "source_page_url": row[4],
                "original_filename": row[5],
                "local_path": row[6],
                "bytes": row[7],
                "content_type": row[8],
                "last_modified": row[9],
                "etag": row[10],
                "published_time": row[11],
                "first_seen": row[12],
                "last_seen": row[13],
                "crawl_time": row[14],
                "deleted_at": row[15],
                "category": row[16],
                "summary": row[17],
                "keywords": json.loads(row[18]) if row[18] else [],
                "markdown_content": row[19],
                "markdown_source": row[20],
                "markdown_updated_at": row[21],
                "rag_chunk_count": row[22] or 0,
                "rag_indexed_at": row[23]
            }
            files.append(file_dict)
        
        return files, total
    
    def mark_file_deleted(self, url: str, deleted_time: str) -> None:
        """Mark a file and its catalog item as deleted.
        
        Args:
            url: File URL
            deleted_time: ISO timestamp for deletion
        """
        self._conn.execute(
            "UPDATE files SET deleted_at = ? WHERE url = ?",
            (deleted_time, url)
        )
        self._conn.execute(
            "UPDATE catalog_items SET status = 'deleted' WHERE file_url = ?",
            (url,)
        )
        self._maybe_commit()
    
    def get_file_with_catalog(self, url: str) -> dict | None:
        """Get file details with catalog information.
        
        Args:
            url: File URL
            
        Returns:
            Combined file and catalog dict or None if not found
        """
        query = """
            SELECT f.url, f.sha256, f.title, f.source_site, f.source_page_url,
                   f.original_filename, f.local_path, f.bytes, f.content_type,
                   f.last_modified, f.etag, f.published_time, f.first_seen,
                   f.last_seen, f.crawl_time, f.deleted_at,
                   c.category, c.summary, c.keywords, c.status,
                   c.markdown_content, c.markdown_updated_at, c.markdown_source,
                   c.catalog_version, c.processed_at, c.updated_at,
                   c.rag_chunk_count, c.rag_indexed_at
            FROM files f
            LEFT JOIN catalog_items c ON c.file_url = f.url
            WHERE f.url = ?
        """
        cur = self._conn.execute(query, (url,))
        row = cur.fetchone()
        
        if not row:
            return None
        
        return {
            "url": row[0],
            "sha256": row[1],
            "title": row[2],
            "source_site": row[3],
            "source_page_url": row[4],
            "original_filename": row[5],
            "local_path": row[6],
            "bytes": row[7],
            "content_type": row[8],
            "last_modified": row[9],
            "etag": row[10],
            "published_time": row[11],
            "first_seen": row[12],
            "last_seen": row[13],
            "crawl_time": row[14],
            "deleted_at": row[15],
            "category": row[16],
            "summary": row[17],
            "keywords": json.loads(row[18]) if row[18] else [],
            "catalog_status": row[19],
            "markdown_content": row[20],
            "markdown_updated_at": row[21],
            "markdown_source": row[22],
            "catalog_version": row[23],
            "catalog_processed_at": row[24],
            "catalog_updated_at": row[25],
            "rag_chunk_count": row[26] or 0,
            "rag_indexed_at": row[27],
        }

    def get_file_rag_kb_entries(self, file_url: str) -> list[dict]:
        """Return KB-level RAG metadata for a specific file.

        Each entry contains KB identity, embedding model, and file index status.
        Returns an empty list when RAG tables are not present.
        """
        try:
            cur = self._conn.execute(
                """
                SELECT
                    kf.kb_id,
                    kb.name,
                    kb.embedding_model,
                    kf.chunk_count,
                    kf.indexed_at,
                    kf.added_at
                FROM rag_kb_files kf
                LEFT JOIN rag_knowledge_bases kb ON kb.kb_id = kf.kb_id
                WHERE kf.file_url = ?
                ORDER BY
                    CASE WHEN kf.indexed_at IS NULL OR kf.indexed_at = '' THEN 1 ELSE 0 END,
                    kf.indexed_at DESC,
                    kf.added_at DESC
                """,
                (file_url,),
            )
        except sqlite3.OperationalError:
            return []

        out: list[dict] = []
        for row in cur.fetchall():
            out.append(
                {
                    "kb_id": row[0],
                    "kb_name": row[1] or row[0],
                    "embedding_model": row[2] or "",
                    "chunk_count": row[3] or 0,
                    "indexed_at": row[4],
                    "added_at": row[5],
                }
            )
        return out
    
    def update_file_catalog(self, url: str, category: str = None, summary: str = None, keywords: list = None) -> tuple[bool, str | None]:
        """Update catalog information for a file.
        
        Args:
            url: File URL
            category: New category value (optional)
            summary: New summary value (optional)
            keywords: New keywords list (optional)
            
        Returns:
            Tuple of (success: bool, error_reason: str | None)
            - (True, None) if update succeeded
            - (False, "file_not_found") if file doesn't exist
            - (False, "no_updates") if no update fields were provided
        """
        # Check if file exists
        file_cur = self._conn.execute(
            "SELECT url FROM files WHERE url = ?",
            (url,)
        )
        if file_cur.fetchone() is None:
            # File doesn't exist, can't update
            return (False, "file_not_found")
        
        # Check if catalog entry exists
        cur = self._conn.execute(
            "SELECT file_url FROM catalog_items WHERE file_url = ?",
            (url,)
        )
        exists = cur.fetchone() is not None
        
        if not exists:
            # Create a catalog entry if it doesn't exist
            self._conn.execute(
                """
                INSERT INTO catalog_items (file_url, sha256, pipeline_version, status)
                SELECT url, sha256, 'manual', 'ok' FROM files WHERE url = ?
                """,
                (url,)
            )
        
        # Build update query dynamically based on provided fields
        updates = []
        params = []
        
        if category is not None:
            updates.append("category = ?")
            params.append(category)
        
        if summary is not None:
            updates.append("summary = ?")
            params.append(summary)
        
        if keywords is not None:
            updates.append("keywords = ?")
            params.append(json.dumps(keywords) if keywords else "")
        
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            query = f"UPDATE catalog_items SET {', '.join(updates)} WHERE file_url = ?"
            params.append(url)
            self._conn.execute(query, tuple(params))
            self._maybe_commit()
            return (True, None)
        
        return (False, "no_updates")
    
    def update_file_markdown(self, url: str, markdown_content: str, markdown_source: str = "manual") -> tuple[bool, str | None]:
        """Update markdown content for a file.
        
        Args:
            url: File URL
            markdown_content: Markdown content to save
            markdown_source: Source of the markdown (manual/converted/original)
            
        Returns:
            Tuple of (success: bool, error_reason: str | None)
            - (True, None) if update succeeded
            - (False, "file_not_found") if file doesn't exist
        """
        # Check if file exists
        file_cur = self._conn.execute(
            "SELECT url FROM files WHERE url = ?",
            (url,)
        )
        if file_cur.fetchone() is None:
            return (False, "file_not_found")
        
        # Check if catalog entry exists
        cur = self._conn.execute(
            "SELECT file_url FROM catalog_items WHERE file_url = ?",
            (url,)
        )
        exists = cur.fetchone() is not None
        
        if not exists:
            # Create a catalog entry if it doesn't exist
            self._conn.execute(
                """
                INSERT INTO catalog_items (file_url, sha256, pipeline_version, status)
                SELECT url, sha256, 'manual', 'ok' FROM files WHERE url = ?
                """,
                (url,)
            )
        
        # Update markdown content
        self._conn.execute(
            """
            UPDATE catalog_items 
            SET markdown_content = ?, 
                markdown_updated_at = CURRENT_TIMESTAMP,
                markdown_source = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE file_url = ?
            """,
            (markdown_content, markdown_source, url)
        )
        self._maybe_commit()
        return (True, None)
    
    def get_file_markdown(self, url: str) -> dict | None:
        """Get markdown content for a file.
        
        Args:
            url: File URL
            
        Returns:
            Dict with markdown_content, markdown_updated_at, markdown_source or None
        """
        cur = self._conn.execute(
            """
            SELECT markdown_content, markdown_updated_at, markdown_source
            FROM catalog_items
            WHERE file_url = ?
            """,
            (url,)
        )
        row = cur.fetchone()
        
        if not row:
            return None
        
        return {
            "markdown_content": row[0],
            "markdown_updated_at": row[1],
            "markdown_source": row[2],
        }

    @staticmethod
    def _utcnow_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _parse_iso_to_utc(value: str | None) -> datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        text = raw.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except Exception:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def create_chunk_profile(
        self,
        *,
        name: str,
        chunk_size: int,
        chunk_overlap: int,
        splitter: str = "semantic",
        tokenizer: str = "cl100k_base",
        version: str = "v1",
        metadata: dict[str, Any] | None = None,
        upsert: bool = True,
    ) -> dict[str, Any]:
        """Create (or reuse) a chunk profile."""
        normalized_name = str(name or "").strip()
        payload = {
            "chunk_size": int(chunk_size),
            "chunk_overlap": int(chunk_overlap),
            "splitter": str(splitter or "semantic"),
            "tokenizer": str(tokenizer or "cl100k_base"),
            "version": str(version or "v1"),
            "metadata": metadata or {},
        }
        config_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        config_hash = hashlib.sha256(config_json.encode("utf-8")).hexdigest()

        # Enforce unique profile names (case-insensitive).
        if normalized_name:
            same_name = self._conn.execute(
                """
                SELECT profile_id, name, chunk_size, chunk_overlap, splitter, tokenizer, version,
                       config_hash, config_json, created_at, updated_at
                FROM chunk_profiles
                WHERE LOWER(name) = LOWER(?)
                LIMIT 1
                """,
                (normalized_name,),
            ).fetchone()
            if same_name:
                if same_name[7] != config_hash:
                    raise ValueError(f"chunk profile name already exists: {normalized_name}")
                return {
                    "profile_id": same_name[0],
                    "name": same_name[1],
                    "chunk_size": same_name[2],
                    "chunk_overlap": same_name[3],
                    "splitter": same_name[4],
                    "tokenizer": same_name[5],
                    "version": same_name[6],
                    "config_hash": same_name[7],
                    "config_json": same_name[8],
                    "created_at": same_name[9],
                    "updated_at": same_name[10],
                }

        existing = self._conn.execute(
            """
            SELECT profile_id, name, chunk_size, chunk_overlap, splitter, tokenizer, version,
                   config_hash, config_json, created_at, updated_at
            FROM chunk_profiles
            WHERE config_hash = ?
            LIMIT 1
            """,
            (config_hash,),
        ).fetchone()
        if existing:
            return {
                "profile_id": existing[0],
                "name": existing[1],
                "chunk_size": existing[2],
                "chunk_overlap": existing[3],
                "splitter": existing[4],
                "tokenizer": existing[5],
                "version": existing[6],
                "config_hash": existing[7],
                "config_json": existing[8],
                "created_at": existing[9],
                "updated_at": existing[10],
            }

        profile_id = f"cp_{uuid.uuid4().hex}"
        now = self._utcnow_iso()
        self._conn.execute(
            """
            INSERT INTO chunk_profiles (
                profile_id, name, config_hash, config_json, chunk_size, chunk_overlap,
                splitter, tokenizer, version, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                normalized_name or profile_id,
                config_hash,
                config_json,
                payload["chunk_size"],
                payload["chunk_overlap"],
                payload["splitter"],
                payload["tokenizer"],
                payload["version"],
                now,
                now,
            ),
        )
        self._maybe_commit()
        return {
            "profile_id": profile_id,
            "name": normalized_name or profile_id,
            "chunk_size": payload["chunk_size"],
            "chunk_overlap": payload["chunk_overlap"],
            "splitter": payload["splitter"],
            "tokenizer": payload["tokenizer"],
            "version": payload["version"],
            "config_hash": config_hash,
            "config_json": config_json,
            "created_at": now,
            "updated_at": now,
        }

    def list_chunk_profiles(self) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            """
            SELECT profile_id, name, chunk_size, chunk_overlap, splitter, tokenizer, version,
                   config_hash, config_json, created_at, updated_at
            FROM chunk_profiles
            ORDER BY updated_at DESC, created_at DESC
            """
        )
        rows = []
        for row in cur.fetchall():
            rows.append(
                {
                    "profile_id": row[0],
                    "name": row[1],
                    "chunk_size": row[2],
                    "chunk_overlap": row[3],
                    "splitter": row[4],
                    "tokenizer": row[5],
                    "version": row[6],
                    "config_hash": row[7],
                    "config_json": row[8],
                    "created_at": row[9],
                    "updated_at": row[10],
                }
            )
        return rows

    def get_chunk_profile(self, profile_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT profile_id, name, chunk_size, chunk_overlap, splitter, tokenizer, version,
                   config_hash, config_json, created_at, updated_at
            FROM chunk_profiles
            WHERE profile_id = ?
            LIMIT 1
            """,
            (profile_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "profile_id": row[0],
            "name": row[1],
            "chunk_size": row[2],
            "chunk_overlap": row[3],
            "splitter": row[4],
            "tokenizer": row[5],
            "version": row[6],
            "config_hash": row[7],
            "config_json": row[8],
            "created_at": row[9],
            "updated_at": row[10],
        }

    def get_or_create_file_chunk_set(
        self,
        *,
        file_url: str,
        profile_id: str,
        markdown_hash: str,
        status: str = "ready",
    ) -> dict[str, Any]:
        existing = self._conn.execute(
            """
            SELECT chunk_set_id, file_url, profile_id, markdown_hash, status, chunk_count, created_at, updated_at
            FROM file_chunk_sets
            WHERE file_url = ? AND profile_id = ? AND markdown_hash = ?
            LIMIT 1
            """,
            (file_url, profile_id, markdown_hash),
        ).fetchone()
        if existing:
            return {
                "chunk_set_id": existing[0],
                "file_url": existing[1],
                "profile_id": existing[2],
                "markdown_hash": existing[3],
                "status": existing[4],
                "chunk_count": existing[5],
                "created_at": existing[6],
                "updated_at": existing[7],
                "created": False,
            }

        now = self._utcnow_iso()
        chunk_set_id = f"cs_{uuid.uuid4().hex}"
        self._conn.execute(
            """
            INSERT INTO file_chunk_sets (
                chunk_set_id, file_url, profile_id, markdown_hash, status, chunk_count, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (chunk_set_id, file_url, profile_id, markdown_hash, status, now, now),
        )
        self._maybe_commit()
        return {
            "chunk_set_id": chunk_set_id,
            "file_url": file_url,
            "profile_id": profile_id,
            "markdown_hash": markdown_hash,
            "status": status,
            "chunk_count": 0,
            "created_at": now,
            "updated_at": now,
            "created": True,
        }

    def replace_global_chunks(
        self,
        *,
        chunk_set_id: str,
        chunks: list[dict[str, Any]],
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Insert chunks for one chunk set.

        When overwrite=False and existing chunks are present, this method keeps existing
        records and returns current counts without modification.
        """
        current_n = int(
            self._conn.execute(
                "SELECT COUNT(*) FROM global_chunks WHERE chunk_set_id = ?",
                (chunk_set_id,),
            ).fetchone()[0]
            or 0
        )
        if current_n > 0 and not overwrite:
            return {"chunk_set_id": chunk_set_id, "chunk_count": current_n, "replaced": False, "inserted": 0}

        with self.transaction():
            if current_n > 0:
                self._conn.execute("DELETE FROM global_chunks WHERE chunk_set_id = ?", (chunk_set_id,))

            now = self._utcnow_iso()
            inserted = 0
            for idx, chunk in enumerate(chunks):
                content = str((chunk or {}).get("content") or "")
                token_count = int((chunk or {}).get("token_count") or 0)
                section_hierarchy = (chunk or {}).get("section_hierarchy")
                chunk_index = int((chunk or {}).get("chunk_index") if (chunk or {}).get("chunk_index") is not None else idx)
                chunk_id = f"{chunk_set_id}:{chunk_index}"
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO global_chunks (
                        chunk_id, chunk_set_id, chunk_index, content, token_count,
                        section_hierarchy, content_hash, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        chunk_set_id,
                        chunk_index,
                        content,
                        token_count,
                        section_hierarchy,
                        content_hash,
                        now,
                    ),
                )
                inserted += 1

            self._conn.execute(
                """
                UPDATE file_chunk_sets
                SET chunk_count = ?, status = 'ready', updated_at = ?
                WHERE chunk_set_id = ?
                """,
                (inserted, now, chunk_set_id),
            )

        return {
            "chunk_set_id": chunk_set_id,
            "chunk_count": inserted,
            "replaced": current_n > 0,
            "inserted": inserted,
        }

    def list_file_chunk_sets(self, file_url: str) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            """
            SELECT
                s.chunk_set_id,
                s.file_url,
                s.profile_id,
                p.name,
                p.chunk_size,
                p.chunk_overlap,
                p.splitter,
                p.tokenizer,
                p.version,
                s.markdown_hash,
                s.status,
                s.chunk_count,
                s.created_at,
                s.updated_at,
                (
                    SELECT COUNT(*)
                    FROM kb_chunk_bindings b
                    WHERE b.chunk_set_id = s.chunk_set_id
                ) AS bound_kb_count
            FROM file_chunk_sets s
            JOIN chunk_profiles p ON p.profile_id = s.profile_id
            WHERE s.file_url = ?
            ORDER BY s.updated_at DESC, s.created_at DESC
            """,
            (file_url,),
        )
        out: list[dict[str, Any]] = []
        for row in cur.fetchall():
            out.append(
                {
                    "chunk_set_id": row[0],
                    "file_url": row[1],
                    "profile_id": row[2],
                    "profile_name": row[3],
                    "chunk_size": row[4],
                    "chunk_overlap": row[5],
                    "splitter": row[6],
                    "tokenizer": row[7],
                    "version": row[8],
                    "markdown_hash": row[9],
                    "status": row[10],
                    "chunk_count": row[11],
                    "created_at": row[12],
                    "updated_at": row[13],
                    "bound_kb_count": row[14] or 0,
                }
            )
        return out

    def bind_chunk_set_to_kb(
        self,
        *,
        kb_id: str,
        file_url: str,
        chunk_set_id: str,
        bound_by: str = "system",
        binding_mode: str = "pin",
    ) -> dict[str, Any]:
        """Bind one chunk set to one KB.

        binding_mode:
            - pin: fixed chunk_set_id for this binding
            - follow_latest: auto-track latest chunk_set for same file/profile
        """
        mode = str(binding_mode or "pin").strip().lower()
        if mode not in {"pin", "follow_latest"}:
            raise ValueError("binding_mode must be 'pin' or 'follow_latest'")
        now = self._utcnow_iso()
        # Validate chunk_set belongs to this file and get profile relation.
        rel = self._conn.execute(
            """
            SELECT file_url, profile_id
            FROM file_chunk_sets
            WHERE chunk_set_id = ?
            LIMIT 1
            """,
            (chunk_set_id,),
        ).fetchone()
        if not rel:
            raise ValueError("chunk_set_id not found")
        if (rel[0] or "") != file_url:
            raise ValueError("chunk_set_id does not belong to the specified file_url")
        target_profile_id = (rel[1] or "") if mode == "follow_latest" else None

        with self.transaction():
            # For follow_latest mode, keep only one active binding per (kb, file, profile).
            if mode == "follow_latest":
                self._conn.execute(
                    """
                    DELETE FROM kb_chunk_bindings
                    WHERE kb_id = ?
                      AND file_url = ?
                      AND binding_mode = 'follow_latest'
                      AND COALESCE(target_profile_id, '') = ?
                      AND chunk_set_id != ?
                    """,
                    (kb_id, file_url, target_profile_id or "", chunk_set_id),
                )

            exists = self._conn.execute(
                """
                SELECT binding_mode, COALESCE(target_profile_id, '')
                FROM kb_chunk_bindings
                WHERE kb_id = ? AND file_url = ? AND chunk_set_id = ?
                LIMIT 1
                """,
                (kb_id, file_url, chunk_set_id),
            ).fetchone()
            if exists:
                current_mode = (exists[0] or "pin").strip().lower()
                current_target_profile = exists[1] or ""
                if current_mode != mode or current_target_profile != (target_profile_id or ""):
                    self._conn.execute(
                        """
                        UPDATE kb_chunk_bindings
                        SET bound_at = ?, bound_by = ?, binding_mode = ?, target_profile_id = ?
                        WHERE kb_id = ? AND file_url = ? AND chunk_set_id = ?
                        """,
                        (now, bound_by, mode, target_profile_id, kb_id, file_url, chunk_set_id),
                    )
                return {
                    "kb_id": kb_id,
                    "file_url": file_url,
                    "chunk_set_id": chunk_set_id,
                    "binding_mode": mode,
                    "target_profile_id": target_profile_id or "",
                    "created": False,
                }

            self._conn.execute(
                """
                INSERT INTO kb_chunk_bindings (
                    kb_id, file_url, chunk_set_id, bound_at, bound_by, binding_mode, target_profile_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (kb_id, file_url, chunk_set_id, now, bound_by, mode, target_profile_id),
            )
            return {
                "kb_id": kb_id,
                "file_url": file_url,
                "chunk_set_id": chunk_set_id,
                "binding_mode": mode,
                "target_profile_id": target_profile_id or "",
                "created": True,
            }

    def sync_follow_latest_bindings_for_chunk_set(
        self,
        *,
        file_url: str,
        profile_id: str,
        chunk_set_id: str,
        bound_by: str = "system_follow_latest",
    ) -> dict[str, Any]:
        """Move follow_latest bindings to the newest chunk_set for same file/profile."""
        now = self._utcnow_iso()
        rows = self._conn.execute(
            """
            SELECT kb_id, file_url, chunk_set_id
            FROM kb_chunk_bindings
            WHERE file_url = ?
              AND binding_mode = 'follow_latest'
              AND COALESCE(target_profile_id, '') = ?
              AND chunk_set_id != ?
            """,
            (file_url, profile_id, chunk_set_id),
        ).fetchall()
        if not rows:
            return {
                "file_url": file_url,
                "profile_id": profile_id,
                "chunk_set_id": chunk_set_id,
                "synced_bindings": 0,
                "affected_kb_ids": [],
            }

        affected_kb_ids: set[str] = set()
        synced = 0
        with self.transaction():
            for row in rows:
                kb_id = str(row[0] or "")
                old_chunk_set_id = str(row[2] or "")
                if not kb_id or not old_chunk_set_id:
                    continue

                target_exists = self._conn.execute(
                    """
                    SELECT 1
                    FROM kb_chunk_bindings
                    WHERE kb_id = ? AND file_url = ? AND chunk_set_id = ?
                    LIMIT 1
                    """,
                    (kb_id, file_url, chunk_set_id),
                ).fetchone()

                if target_exists:
                    self._conn.execute(
                        """
                        UPDATE kb_chunk_bindings
                        SET bound_at = ?, bound_by = ?, binding_mode = 'follow_latest', target_profile_id = ?
                        WHERE kb_id = ? AND file_url = ? AND chunk_set_id = ?
                        """,
                        (now, bound_by, profile_id, kb_id, file_url, chunk_set_id),
                    )
                else:
                    self._conn.execute(
                        """
                        INSERT INTO kb_chunk_bindings (
                            kb_id, file_url, chunk_set_id, bound_at, bound_by, binding_mode, target_profile_id
                        )
                        VALUES (?, ?, ?, ?, ?, 'follow_latest', ?)
                        """,
                        (kb_id, file_url, chunk_set_id, now, bound_by, profile_id),
                    )
                self._conn.execute(
                    """
                    DELETE FROM kb_chunk_bindings
                    WHERE kb_id = ? AND file_url = ? AND chunk_set_id = ?
                    """,
                    (kb_id, file_url, old_chunk_set_id),
                )
                synced += 1
                affected_kb_ids.add(kb_id)

        return {
            "file_url": file_url,
            "profile_id": profile_id,
            "chunk_set_id": chunk_set_id,
            "synced_bindings": synced,
            "affected_kb_ids": sorted(affected_kb_ids),
        }

    def list_file_index_status(self, file_url: str) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            """
            SELECT
                b.kb_id,
                COUNT(DISTINCT b.chunk_set_id) AS chunk_set_count,
                COALESCE((
                    SELECT iv.embedding_model
                    FROM kb_index_versions iv
                    WHERE iv.kb_id = b.kb_id
                    ORDER BY COALESCE(iv.built_at, iv.created_at) DESC
                    LIMIT 1
                ), '') AS embedding_model,
                (
                    SELECT COALESCE(iv.built_at, iv.created_at)
                    FROM kb_index_versions iv
                    WHERE iv.kb_id = b.kb_id
                    ORDER BY COALESCE(iv.built_at, iv.created_at) DESC
                    LIMIT 1
                ) AS indexed_at,
                COALESCE((
                    SELECT iv.chunk_count
                    FROM kb_index_versions iv
                    WHERE iv.kb_id = b.kb_id
                    ORDER BY COALESCE(iv.built_at, iv.created_at) DESC
                    LIMIT 1
                ), 0) AS indexed_chunk_count
            FROM kb_chunk_bindings b
            WHERE b.file_url = ?
            GROUP BY b.kb_id
            ORDER BY indexed_at DESC
            """,
            (file_url,),
        )
        out: list[dict[str, Any]] = []
        for row in cur.fetchall():
            out.append(
                {
                    "kb_id": row[0],
                    "chunk_set_count": row[1] or 0,
                    "embedding_model": row[2] or "",
                    "indexed_at": row[3],
                    "indexed_chunk_count": row[4] or 0,
                }
            )
        return out

    def get_kb_composition_status(self, kb_id: str) -> dict[str, Any]:
        file_count = int(
            self._conn.execute(
                "SELECT COUNT(DISTINCT file_url) FROM kb_chunk_bindings WHERE kb_id = ?",
                (kb_id,),
            ).fetchone()[0]
            or 0
        )
        chunk_set_count = int(
            self._conn.execute(
                "SELECT COUNT(DISTINCT chunk_set_id) FROM kb_chunk_bindings WHERE kb_id = ?",
                (kb_id,),
            ).fetchone()[0]
            or 0
        )
        latest = self._conn.execute(
            """
            SELECT embedding_model, index_type, status, chunk_count, built_at, created_at
            FROM kb_index_versions
            WHERE kb_id = ?
            ORDER BY COALESCE(built_at, created_at) DESC
            LIMIT 1
            """,
            (kb_id,),
        ).fetchone()
        latest_binding_at = self._conn.execute(
            """
            SELECT MAX(bound_at)
            FROM kb_chunk_bindings
            WHERE kb_id = ?
            """,
            (kb_id,),
        ).fetchone()[0]
        mode_counts = self._conn.execute(
            """
            SELECT
                SUM(CASE WHEN binding_mode = 'follow_latest' THEN 1 ELSE 0 END) AS follow_latest_count,
                SUM(CASE WHEN binding_mode = 'pin' OR binding_mode IS NULL THEN 1 ELSE 0 END) AS pin_count
            FROM kb_chunk_bindings
            WHERE kb_id = ?
            """,
            (kb_id,),
        ).fetchone()
        follow_latest_count = int((mode_counts[0] or 0) if mode_counts else 0)
        pin_count = int((mode_counts[1] or 0) if mode_counts else 0)
        outdated_binding_count = int(
            self._conn.execute(
                """
                SELECT COUNT(*)
                FROM kb_chunk_bindings b
                LEFT JOIN file_chunk_sets s ON s.chunk_set_id = b.chunk_set_id
                WHERE b.kb_id = ?
                  AND s.profile_id IS NOT NULL
                  AND b.chunk_set_id != (
                    SELECT s2.chunk_set_id
                    FROM file_chunk_sets s2
                    WHERE s2.file_url = b.file_url
                      AND s2.profile_id = s.profile_id
                    ORDER BY s2.updated_at DESC, s2.created_at DESC
                    LIMIT 1
                  )
                """,
                (kb_id,),
            ).fetchone()[0]
            or 0
        )
        has_index = bool(latest)
        latest_index_time = (latest[4] or latest[5]) if latest else None
        needs_reindex = bool(file_count > 0 and (not has_index or (latest_binding_at and latest_index_time and latest_binding_at > latest_index_time)))
        return {
            "kb_id": kb_id,
            "file_count": file_count,
            "chunk_set_count": chunk_set_count,
            "has_index": has_index,
            "latest_binding_at": latest_binding_at,
            "binding_mode_counts": {
                "follow_latest": follow_latest_count,
                "pin": pin_count,
            },
            "outdated_binding_count": outdated_binding_count,
            "new_chunk_versions_available": outdated_binding_count > 0,
            "needs_reindex": needs_reindex,
            "latest_index": {
                "embedding_model": latest[0],
                "index_type": latest[1],
                "status": latest[2],
                "chunk_count": latest[3] or 0,
                "built_at": latest[4] or latest[5],
            }
            if latest
            else None,
        }

    def list_kb_chunk_bindings(self, kb_id: str) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            """
            SELECT
                b.kb_id,
                b.file_url,
                b.chunk_set_id,
                b.bound_at,
                b.bound_by,
                b.binding_mode,
                b.target_profile_id,
                s.profile_id,
                p.name AS profile_name,
                s.chunk_count,
                s.markdown_hash,
                s.updated_at AS chunk_set_updated_at,
                (
                    SELECT s2.chunk_set_id
                    FROM file_chunk_sets s2
                    WHERE s2.file_url = b.file_url
                      AND s2.profile_id = s.profile_id
                    ORDER BY s2.updated_at DESC, s2.created_at DESC
                    LIMIT 1
                ) AS latest_chunk_set_id
            FROM kb_chunk_bindings b
            LEFT JOIN file_chunk_sets s ON s.chunk_set_id = b.chunk_set_id
            LEFT JOIN chunk_profiles p ON p.profile_id = s.profile_id
            WHERE b.kb_id = ?
            ORDER BY b.bound_at DESC
            """,
            (kb_id,),
        )
        out: list[dict[str, Any]] = []
        for row in cur.fetchall():
            out.append(
                {
                    "kb_id": row[0],
                    "file_url": row[1],
                    "chunk_set_id": row[2],
                    "bound_at": row[3],
                    "bound_by": row[4],
                    "binding_mode": row[5] or "pin",
                    "target_profile_id": row[6] or "",
                    "profile_id": row[7],
                    "profile_name": row[8] or "",
                    "chunk_count": row[9] or 0,
                    "markdown_hash": row[10] or "",
                    "chunk_set_updated_at": row[11],
                    "latest_chunk_set_id": row[12] or "",
                    "is_latest_for_profile": (row[12] or "") == (row[2] or ""),
                }
            )
        return out

    def create_kb_index_version(
        self,
        *,
        kb_id: str,
        embedding_model: str,
        index_type: str,
        chunk_count: int,
        status: str = "ready",
        artifact_path: str = "",
        chunk_ids: list[str] | None = None,
        built_at: str | None = None,
    ) -> dict[str, Any]:
        now = self._utcnow_iso()
        index_version_id = f"idxv_{uuid.uuid4().hex}"
        built_time = built_at or now
        with self.transaction():
            # Keep only the latest index version record per KB.
            old_ids = [
                str(r[0])
                for r in self._conn.execute(
                    "SELECT index_version_id FROM kb_index_versions WHERE kb_id = ?",
                    (kb_id,),
                ).fetchall()
            ]
            if old_ids:
                for old_id in old_ids:
                    self._conn.execute(
                        "DELETE FROM kb_index_items WHERE index_version_id = ?",
                        (old_id,),
                    )
                self._conn.execute("DELETE FROM kb_index_versions WHERE kb_id = ?", (kb_id,))

            self._conn.execute(
                """
                INSERT INTO kb_index_versions (
                    index_version_id, kb_id, embedding_model, index_type, status,
                    artifact_path, chunk_count, built_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    index_version_id,
                    kb_id,
                    embedding_model,
                    index_type,
                    status,
                    artifact_path,
                    int(chunk_count),
                    built_time,
                    now,
                ),
            )
            if chunk_ids:
                for chunk_id in chunk_ids:
                    self._conn.execute(
                        """
                        INSERT OR IGNORE INTO kb_index_items (index_version_id, chunk_id)
                        VALUES (?, ?)
                        """,
                        (index_version_id, chunk_id),
                    )
        return {
            "index_version_id": index_version_id,
            "kb_id": kb_id,
            "embedding_model": embedding_model,
            "index_type": index_type,
            "status": status,
            "artifact_path": artifact_path,
            "chunk_count": int(chunk_count),
            "built_at": built_time,
            "created_at": now,
        }

    def cleanup_orphan_chunk_sets(
        self,
        *,
        older_than_days: int = 30,
        limit: int = 5000,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        days = max(1, int(older_than_days))
        max_rows = max(1, min(int(limit), 20000))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        rows = self._conn.execute(
            """
            SELECT s.chunk_set_id, s.file_url, s.profile_id, s.created_at, s.updated_at,
                   COALESCE((SELECT COUNT(*) FROM global_chunks g WHERE g.chunk_set_id = s.chunk_set_id), 0) AS chunk_count
            FROM file_chunk_sets s
            WHERE NOT EXISTS (
                SELECT 1 FROM kb_chunk_bindings b WHERE b.chunk_set_id = s.chunk_set_id
            )
            ORDER BY COALESCE(s.updated_at, s.created_at) ASC
            LIMIT ?
            """,
            (max_rows,),
        ).fetchall()

        candidates: list[dict[str, Any]] = []
        for row in rows:
            updated_at = row[4] or row[3]
            updated_dt = self._parse_iso_to_utc(updated_at)
            if not updated_dt or updated_dt >= cutoff:
                continue
            candidates.append(
                {
                    "chunk_set_id": row[0],
                    "file_url": row[1],
                    "profile_id": row[2],
                    "created_at": row[3],
                    "updated_at": row[4],
                    "chunk_count": int(row[5] or 0),
                }
            )

        total_chunks = sum(int(item.get("chunk_count") or 0) for item in candidates)
        if dry_run or not candidates:
            return {
                "older_than_days": days,
                "dry_run": bool(dry_run),
                "deleted_chunk_sets": 0,
                "deleted_chunks": 0,
                "candidates": len(candidates),
                "candidate_chunk_sets": candidates,
            }

        with self.transaction():
            for item in candidates:
                chunk_set_id = str(item["chunk_set_id"])
                # Remove index references first (safe even when SQLite FK is disabled).
                self._conn.execute(
                    "DELETE FROM kb_index_items WHERE chunk_id LIKE ?",
                    (f"{chunk_set_id}:%",),
                )
                self._conn.execute(
                    """
                    DELETE FROM chunk_embeddings
                    WHERE chunk_id IN (
                        SELECT chunk_id FROM global_chunks WHERE chunk_set_id = ?
                    )
                    """,
                    (chunk_set_id,),
                )
                self._conn.execute("DELETE FROM global_chunks WHERE chunk_set_id = ?", (chunk_set_id,))
                self._conn.execute("DELETE FROM file_chunk_sets WHERE chunk_set_id = ?", (chunk_set_id,))

        return {
            "older_than_days": days,
            "dry_run": False,
            "deleted_chunk_sets": len(candidates),
            "deleted_chunks": total_chunks,
            "candidates": len(candidates),
            "candidate_chunk_sets": candidates[:50],
        }
    
    def clear_local_path(self, url: str) -> None:
        """Clear the local_path for a file (for deletion tracking).
        
        Args:
            url: File URL
        """
        self._conn.execute(
            "UPDATE files SET local_path = NULL WHERE url = ?",
            (url,)
        )
        self._maybe_commit()

    # =========================================================================
    # User Management Methods
    # =========================================================================

    def create_user(
        self,
        email: str,
        password_hash: str,
        role: str = "registered",
        display_name: str | None = None,
    ) -> int:
        """Create a new email-based user.

        Returns the new user id.
        Raises ValueError if the email already exists.
        """
        now = self.now()
        try:
            cur = self._conn.execute(
                """
                INSERT INTO users (email, password_hash, role, is_active, email_verified,
                                   display_name, created_at)
                VALUES (?, ?, ?, 1, 0, ?, ?)
                """,
                (email.lower().strip(), password_hash, role, display_name, now),
            )
            self._maybe_commit()
            return cur.lastrowid  # type: ignore[return-value]
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise ValueError(f"Email already registered: {email}") from exc
            raise

    def get_user_by_email(self, email: str) -> dict | None:
        """Return user record by email, or None.

        Returns the record regardless of ``is_active`` status so callers can
        provide specific error messages for disabled accounts rather than a
        generic "user not found" response.
        """
        cur = self._conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email.lower().strip(),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))

    def get_user_by_id(self, user_id: int) -> dict | None:
        """Return user record by id, or None."""
        cur = self._conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))

    def update_user_last_login(self, user_id: int) -> None:
        """Update the last_login_at timestamp."""
        self._conn.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?",
            (self.now(), user_id),
        )
        self._maybe_commit()

    def update_user_role(self, user_id: int, role: str) -> bool:
        """Change a user's role. Returns True if user was found."""
        cur = self._conn.execute(
            "UPDATE users SET role = ? WHERE id = ?",
            (role, user_id),
        )
        self._maybe_commit()
        return cur.rowcount > 0

    def update_user_active(self, user_id: int, is_active: bool) -> bool:
        """Enable/disable a user account."""
        cur = self._conn.execute(
            "UPDATE users SET is_active = ? WHERE id = ?",
            (1 if is_active else 0, user_id),
        )
        self._maybe_commit()
        return cur.rowcount > 0

    def update_user_profile(
        self,
        user_id: int,
        display_name: str | None = None,
        password_hash: str | None = None,
    ) -> bool:
        """Update a user's display name and/or password hash.

        Only the fields passed as non-None are updated.
        Returns True if the user was found.
        """
        updates: list[str] = []
        params: list = []
        if display_name is not None:
            updates.append("display_name = ?")
            params.append(display_name or None)
        if password_hash is not None:
            updates.append("password_hash = ?")
            params.append(password_hash)
        if not updates:
            # nothing to do; return True if user exists
            row = self._conn.execute(
                "SELECT id FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            return row is not None
        params.append(user_id)
        cur = self._conn.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        self._maybe_commit()
        return cur.rowcount > 0

    def list_users(
        self,
        page: int = 1,
        per_page: int = 50,
        role: str | None = None,
        search: str | None = None,
    ) -> tuple[list[dict], int]:
        """Return a page of users and total count."""
        filters: list[str] = []
        params: list[Any] = []
        if role:
            filters.append("role = ?")
            params.append(role)
        if search:
            filters.append("(email LIKE ? OR display_name LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        where = ("WHERE " + " AND ".join(filters)) if filters else ""
        total = self._conn.execute(
            f"SELECT COUNT(*) FROM users {where}", params
        ).fetchone()[0]
        offset = (page - 1) * per_page
        rows = self._conn.execute(
            f"SELECT * FROM users {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()
        cur = self._conn.execute("SELECT * FROM users LIMIT 0")
        cols = [d[0] for d in cur.description]
        users = [dict(zip(cols, r)) for r in rows]
        return users, total

    # -------------------------------------------------------------------------
    # Quota helpers
    # -------------------------------------------------------------------------

    def get_ai_chat_quota_used(
        self,
        quota_date: str,
        *,
        user_id: int | None = None,
        ip_address: str | None = None,
    ) -> int:
        """Return the number of AI chat queries used today for user or IP."""
        if user_id is not None:
            row = self._conn.execute(
                "SELECT ai_chat_count FROM user_quotas WHERE user_id = ? AND quota_date = ?",
                (user_id, quota_date),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT ai_chat_count FROM user_quotas WHERE ip_address = ? AND quota_date = ?",
                (ip_address, quota_date),
            ).fetchone()
        return int(row[0]) if row else 0

    def check_and_increment_ai_chat_quota(
        self,
        quota_date: str,
        limit: int,
        *,
        user_id: int | None = None,
        ip_address: str | None = None,
    ) -> tuple[bool, int]:
        """Atomically check quota and increment if under the limit.

        Returns ``(allowed, new_count)`` where ``allowed`` is True when the
        query should proceed (count was below *limit* before incrementing).
        Uses a single atomic UPDATE/INSERT so concurrent requests from the same
        user/IP cannot race past the limit.
        """
        if limit <= 0:
            # A limit of zero means the role has no AI chat access at all.
            return False, 0
        now = self.now()
        if user_id is not None:
            # Try to increment an existing row only when still under the limit.
            cur = self._conn.execute(
                """
                UPDATE user_quotas
                   SET ai_chat_count = ai_chat_count + 1,
                       updated_at    = ?
                 WHERE user_id    = ?
                   AND quota_date = ?
                   AND ai_chat_count < ?
                """,
                (now, user_id, quota_date, limit),
            )
            if cur.rowcount > 0:
                # Read back the new value (the UPDATE already succeeded).
                row = self._conn.execute(
                    "SELECT ai_chat_count FROM user_quotas WHERE user_id = ? AND quota_date = ?",
                    (user_id, quota_date),
                ).fetchone()
                self._maybe_commit()
                return True, int(row[0]) if row else 1
            # Row didn't exist yet — try to insert (first query of the day).
            # Use INSERT OR IGNORE so a concurrent insert loses gracefully.
            self._conn.execute(
                """
                INSERT OR IGNORE INTO user_quotas
                    (user_id, quota_date, ai_chat_count, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                """,
                (user_id, quota_date, now, now),
            )
            if self._conn.execute(
                "SELECT changes()"
            ).fetchone()[0] > 0:
                # Insert succeeded — we are at count=1.
                self._maybe_commit()
                return True, 1
            # Another thread already inserted: re-check with atomic update.
            cur2 = self._conn.execute(
                """
                UPDATE user_quotas
                   SET ai_chat_count = ai_chat_count + 1,
                       updated_at    = ?
                 WHERE user_id    = ?
                   AND quota_date = ?
                   AND ai_chat_count < ?
                """,
                (now, user_id, quota_date, limit),
            )
            if cur2.rowcount > 0:
                row2 = self._conn.execute(
                    "SELECT ai_chat_count FROM user_quotas WHERE user_id = ? AND quota_date = ?",
                    (user_id, quota_date),
                ).fetchone()
                self._maybe_commit()
                return True, int(row2[0]) if row2 else 1
            # Already at or over limit.
            current = self._conn.execute(
                "SELECT ai_chat_count FROM user_quotas WHERE user_id = ? AND quota_date = ?",
                (user_id, quota_date),
            ).fetchone()
            self._maybe_commit()
            return False, int(current[0]) if current else limit
        else:
            # IP-address path — same logic.
            cur = self._conn.execute(
                """
                UPDATE user_quotas
                   SET ai_chat_count = ai_chat_count + 1,
                       updated_at    = ?
                 WHERE ip_address = ?
                   AND quota_date = ?
                   AND ai_chat_count < ?
                """,
                (now, ip_address, quota_date, limit),
            )
            if cur.rowcount > 0:
                row = self._conn.execute(
                    "SELECT ai_chat_count FROM user_quotas WHERE ip_address = ? AND quota_date = ?",
                    (ip_address, quota_date),
                ).fetchone()
                self._maybe_commit()
                return True, int(row[0]) if row else 1
            self._conn.execute(
                """
                INSERT OR IGNORE INTO user_quotas
                    (ip_address, quota_date, ai_chat_count, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                """,
                (ip_address, quota_date, now, now),
            )
            if self._conn.execute(
                "SELECT changes()"
            ).fetchone()[0] > 0:
                self._maybe_commit()
                return True, 1
            cur2 = self._conn.execute(
                """
                UPDATE user_quotas
                   SET ai_chat_count = ai_chat_count + 1,
                       updated_at    = ?
                 WHERE ip_address = ?
                   AND quota_date = ?
                   AND ai_chat_count < ?
                """,
                (now, ip_address, quota_date, limit),
            )
            if cur2.rowcount > 0:
                row2 = self._conn.execute(
                    "SELECT ai_chat_count FROM user_quotas WHERE ip_address = ? AND quota_date = ?",
                    (ip_address, quota_date),
                ).fetchone()
                self._maybe_commit()
                return True, int(row2[0]) if row2 else 1
            current = self._conn.execute(
                "SELECT ai_chat_count FROM user_quotas WHERE ip_address = ? AND quota_date = ?",
                (ip_address, quota_date),
            ).fetchone()
            self._maybe_commit()
            return False, int(current[0]) if current else limit

    def increment_ai_chat_quota(
        self,
        quota_date: str,
        *,
        user_id: int | None = None,
        ip_address: str | None = None,
    ) -> int:
        """Increment AI chat quota counter. Returns new count.

        .. deprecated::
            Use :meth:`check_and_increment_ai_chat_quota` instead.
            This method is a non-atomic read-modify-write and is unsafe under
            concurrent access. The atomic version is the only correct API.
        """
        now = self.now()
        if user_id is not None:
            existing = self._conn.execute(
                "SELECT id, ai_chat_count FROM user_quotas WHERE user_id = ? AND quota_date = ?",
                (user_id, quota_date),
            ).fetchone()
            if existing:
                new_count = existing[1] + 1
                self._conn.execute(
                    "UPDATE user_quotas SET ai_chat_count = ?, updated_at = ? WHERE id = ?",
                    (new_count, now, existing[0]),
                )
            else:
                new_count = 1
                self._conn.execute(
                    "INSERT INTO user_quotas (user_id, quota_date, ai_chat_count, created_at, updated_at) VALUES (?, ?, 1, ?, ?)",
                    (user_id, quota_date, now, now),
                )
        else:
            existing = self._conn.execute(
                "SELECT id, ai_chat_count FROM user_quotas WHERE ip_address = ? AND quota_date = ?",
                (ip_address, quota_date),
            ).fetchone()
            if existing:
                new_count = existing[1] + 1
                self._conn.execute(
                    "UPDATE user_quotas SET ai_chat_count = ?, updated_at = ? WHERE id = ?",
                    (new_count, now, existing[0]),
                )
            else:
                new_count = 1
                self._conn.execute(
                    "INSERT INTO user_quotas (ip_address, quota_date, ai_chat_count, created_at, updated_at) VALUES (?, ?, 1, ?, ?)",
                    (ip_address, quota_date, now, now),
                )
        self._maybe_commit()
        return new_count

    def reset_user_quota(self, user_id: int, quota_date: str | None = None) -> None:
        """Reset quota for a user, optionally only for a specific date."""
        if quota_date:
            self._conn.execute(
                "UPDATE user_quotas SET ai_chat_count = 0 WHERE user_id = ? AND quota_date = ?",
                (user_id, quota_date),
            )
        else:
            self._conn.execute(
                "UPDATE user_quotas SET ai_chat_count = 0 WHERE user_id = ?",
                (user_id,),
            )
        self._maybe_commit()

    # -------------------------------------------------------------------------
    # Activity log helpers
    # -------------------------------------------------------------------------

    def log_user_activity(
        self,
        action: str,
        *,
        user_id: int | None = None,
        ip_address: str | None = None,
        resource: str | None = None,
        detail: str | None = None,
    ) -> None:
        """Insert a user activity log entry."""
        self._conn.execute(
            """
            INSERT INTO user_activity_logs (user_id, ip_address, action, resource, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, ip_address, action, resource, detail, self.now()),
        )
        self._maybe_commit()

    def list_user_activity(
        self,
        user_id: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Return activity log entries, optionally filtered by user."""
        if user_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM user_activity_logs WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (user_id, limit, offset),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM user_activity_logs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        cur = self._conn.execute("SELECT * FROM user_activity_logs LIMIT 0")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]
