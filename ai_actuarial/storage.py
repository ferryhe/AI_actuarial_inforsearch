from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
import hashlib

from ai_actuarial.ai_runtime import infer_embedding_dimension, infer_embedding_provider
from ai_actuarial.sqlite_schema import (
    CURRENT_SQLITE_SCHEMA_VERSION,
    has_user_schema_objects,
    storage_startup_status,
)


AGENTIC_READY_PUBLICATION_PROFILES = frozenset(
    {"general", "regulation", "formula"}
)


def agentic_ready_publication_matches_scope(
    publication: Any,
    *,
    kb_id: str,
    profile: str,
) -> bool:
    if not isinstance(publication, Mapping) or publication.get("kb_id") != kb_id:
        return False
    stored_profile = publication.get("profile")
    if not isinstance(stored_profile, str):
        return False
    normalized_stored_profile = stored_profile.strip().lower()
    normalized_requested_profile = str(profile or "").strip().lower()
    return bool(
        normalized_stored_profile in AGENTIC_READY_PUBLICATION_PROFILES
        and normalized_stored_profile == normalized_requested_profile
    )


def _is_internal_category_label(category: str) -> bool:
    value = str(category or "").strip()
    return value.startswith("(") and value.endswith(")")


def _split_visible_categories(raw_category: str | None) -> list[str]:
    raw = str(raw_category or "").strip()
    if not raw:
        return []
    return [
        part
        for part in (segment.strip() for segment in raw.split(";"))
        if part and not _is_internal_category_label(part)
    ]


class Storage:
    AGENTIC_READY_RESERVED_ATTEMPT_DISPOSITIONS = frozenset(
        {"superseded_generation"}
    )
    AGENTIC_READY_FUTURE_EXECUTION_POLICY = {
        "quiet_debounce_seconds": 60,
        "polling_seconds": 15,
        "sqlite_global_max_concurrency": 1,
        "single_flight_scope": "kb_id_profile",
        "automatic_retry": False,
        "staging_smoke_network": "none",
        "staging_smoke_timeout_seconds": 10,
        "non_empty_kb_requires_valid_reference": True,
        "empty_kb_requires_manual_publish_confirmation": True,
        "superseded_generation_minimum_age_days": 14,
        "superseded_generation_keep_latest": 2,
        "automatic_gc_enabled": False,
    }
    _AGENTIC_READY_SOURCE_EVENT_SEVERITY = {
        "membership_added": "soft_stale",
        "metadata_updated": "soft_stale",
        "builder_contract_changed": "soft_stale",
        "profile_contract_changed": "soft_stale",
        "chunk_binding_updated": "soft_stale",
        "chunk_content_updated": "soft_stale",
        "membership_removed": "hard_stale",
        "chunk_binding_removed": "hard_stale",
        "source_invalidated": "hard_stale",
        "source_deleted": "hard_stale",
        "access_scope_restricted": "hard_stale",
        "index_committed": "none",
        "embedding_index_committed": "none",
        "embedding_config_changed": "none",
    }

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
            "kb_ready_index_state",
            "kb_index_items",
            "agentic_ready_manifests",
            "agentic_ready_publications",
            "agentic_ready_publication_gc",
            "agentic_ready_slots",
            "agentic_ready_source_state",
            "agentic_ready_automation",
            "agentic_ready_automation_lock",
            "weekly_update_summaries",
            "rag_knowledge_bases",
            "users",
            "user_quotas",
            "user_activity_logs",
        }
    )

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(os.path.dirname(db_path)).mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        try:
            self._conn.execute("PRAGMA foreign_keys=ON;")
            user_version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
            if user_version > CURRENT_SQLITE_SCHEMA_VERSION:
                self._conn.close()
                raise RuntimeError("SQLite schema version is newer than this code")
            has_schema_objects = has_user_schema_objects(self._conn)
            fresh_schema = False
            if has_schema_objects:
                status = storage_startup_status(self._conn)
                state = str(status.get("state") or "")
                if state == "newer_than_code":
                    self._conn.close()
                    raise RuntimeError("SQLite schema version is newer than this code")
                if state == "needs_migration":
                    self._conn.close()
                    if user_version == 0:
                        raise RuntimeError(
                            "SQLite schema user_version=0 requires explicit schema apply before Storage startup"
                        )
                    raise RuntimeError(
                        "SQLite schema requires explicit schema apply before Storage startup"
                    )
                if state != "current":
                    self._conn.close()
                    raise RuntimeError("SQLite schema preflight failed before Storage startup")
                self._tx_depth = 0
                self._agentic_ready_publication_columns_cache = None
                self._defer_schema_commits = False
                self._seed_taxonomy_state_if_empty()
                return
            else:
                if user_version != 0:
                    self._conn.close()
                    raise RuntimeError("SQLite schema preflight failed before Storage startup")
                fresh_schema = True
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._tx_depth = 0
            self._agentic_ready_publication_columns_cache: frozenset[str] | None = None
            self._defer_schema_commits = False
            self._init_schema()
            if fresh_schema:
                self._conn.execute(f"PRAGMA user_version={CURRENT_SQLITE_SCHEMA_VERSION}")
                self._conn.commit()
            self._seed_taxonomy_state_if_empty()
        except sqlite3.Error:
            self._conn.close()
            raise

    @classmethod
    def open_read_only(cls, db_path: str) -> "Storage":
        """Load a stable checkpointed database snapshot without filesystem writes."""
        path = Path(db_path)
        if not path.is_file():
            raise ValueError("ready-data GC requires an existing database")
        before_state = cls._read_only_snapshot_state(path)
        if before_state[1][0] and before_state[1][1] > 0:
            raise ValueError(
                "ready-data GC dry-run requires a checkpointed database with an empty WAL"
            )
        instance = cls.__new__(cls)
        instance.db_path = str(path)
        uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
        instance._conn = sqlite3.connect(uri, uri=True)
        instance._conn.execute("PRAGMA foreign_keys=ON;")
        instance._conn.execute("PRAGMA query_only=ON;")
        instance._tx_depth = 0
        instance._agentic_ready_publication_columns_cache = None
        instance._defer_schema_commits = False
        instance._read_only_snapshot = before_state
        return instance

    @staticmethod
    def _read_only_snapshot_state(
        path: Path,
    ) -> tuple[tuple[bool, int, int, str], ...]:
        def file_state(candidate: Path) -> tuple[bool, int, int, str]:
            try:
                details = candidate.stat()
            except FileNotFoundError:
                return False, 0, 0, ""
            digest = hashlib.sha256()
            with candidate.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return True, int(details.st_size), int(details.st_mtime_ns), digest.hexdigest()

        return tuple(
            file_state(candidate)
            for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm"))
        )

    def assert_read_only_snapshot_unchanged(self) -> None:
        expected = getattr(self, "_read_only_snapshot", None)
        if expected is None:
            raise RuntimeError("storage is not a read-only snapshot")
        current = self._read_only_snapshot_state(Path(self.db_path))
        if current != expected or (current[1][0] and current[1][1] > 0):
            raise ValueError(
                "ready-data GC dry-run requires a stable checkpointed database snapshot"
            )

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

        # taxonomy_state: single-row marker of the last applied categories.yaml hash
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS taxonomy_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                applied_hash TEXT NOT NULL,
                applied_at TEXT
            )
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
                instance_id TEXT NOT NULL DEFAULT 'default',
                label TEXT,
                is_default INTEGER NOT NULL DEFAULT 1,
                api_key_encrypted TEXT NOT NULL,
                api_base_url TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT,
                updated_at TEXT,
                notes TEXT
            )
            """
        )
        self._ensure_columns(
            "api_tokens",
            {
                "instance_id": "TEXT DEFAULT 'default'",
                "label": "TEXT",
                "is_default": "INTEGER DEFAULT 1",
            },
        )
        self._conn.execute("UPDATE api_tokens SET instance_id = 'default' WHERE instance_id IS NULL OR instance_id = ''")
        self._conn.execute(
            "UPDATE api_tokens SET label = provider || ' (' || category || ')' WHERE label IS NULL OR label = ''"
        )
        self._conn.execute("UPDATE api_tokens SET is_default = 1 WHERE is_default IS NULL")
        self._conn.execute("DROP INDEX IF EXISTS idx_api_tokens_provider_category")
        self._conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_api_tokens_provider_category_instance
            ON api_tokens(provider, category, instance_id)
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_api_tokens_provider_category_default
            ON api_tokens(provider, category, is_default)
            """
        )
        self._schema_commit()
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
                "rag_indexed": "INTEGER DEFAULT 0",
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
        self._schema_commit()

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
                embedding_provider TEXT NOT NULL DEFAULT 'openai',
                embedding_model TEXT NOT NULL,
                embedding_dimension INTEGER,
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
            CREATE TABLE IF NOT EXISTS kb_ready_index_state (
                kb_id TEXT PRIMARY KEY,
                index_version_id TEXT NOT NULL,
                embedding_provider TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                embedding_dimension INTEGER,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE
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
            CREATE TABLE IF NOT EXISTS agentic_ready_manifests (
                manifest_id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                profile TEXT NOT NULL,
                profile_version TEXT NOT NULL,
                status TEXT NOT NULL,
                output_dir TEXT,
                artifact_files_json TEXT,
                doc_count INTEGER NOT NULL DEFAULT 0,
                section_count INTEGER NOT NULL DEFAULT 0,
                built_at TEXT,
                source_db TEXT,
                schema_versions_json TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(kb_id, profile),
                FOREIGN KEY(kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agentic_ready_publications (
                publication_id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                index_version_id TEXT,
                source_version_kind TEXT NOT NULL,
                source_version_id TEXT NOT NULL,
                profile TEXT NOT NULL,
                profile_version TEXT NOT NULL,
                status TEXT NOT NULL,
                output_dir TEXT NOT NULL,
                artifact_files_json TEXT NOT NULL DEFAULT '[]',
                doc_count INTEGER NOT NULL DEFAULT 0,
                section_count INTEGER NOT NULL DEFAULT 0,
                built_at TEXT,
                artifact_digest TEXT NOT NULL,
                source_db TEXT,
                schema_versions_json TEXT NOT NULL DEFAULT '{}',
                smoke_result_json TEXT NOT NULL DEFAULT '{}',
                error_message TEXT,
                validated_at TEXT,
                published_at TEXT,
                attempt_disposition TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agentic_ready_slots (
                kb_id TEXT NOT NULL,
                profile TEXT NOT NULL,
                active_publication_id TEXT,
                previous_publication_id TEXT,
                publication_revision INTEGER NOT NULL DEFAULT 0,
                automatic_build_enabled INTEGER NOT NULL DEFAULT 0,
                automatic_publish_enabled INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(kb_id, profile),
                FOREIGN KEY(kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE,
                FOREIGN KEY(active_publication_id) REFERENCES agentic_ready_publications(publication_id),
                FOREIGN KEY(previous_publication_id) REFERENCES agentic_ready_publications(publication_id)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agentic_ready_source_state (
                kb_id TEXT NOT NULL,
                profile TEXT NOT NULL,
                event_generation INTEGER NOT NULL DEFAULT 0,
                pending_evaluation_generation INTEGER,
                evaluated_generation INTEGER NOT NULL DEFAULT 0,
                pending_severity TEXT NOT NULL DEFAULT 'none',
                pending_reasons_json TEXT NOT NULL DEFAULT '[]',
                evaluated_severity TEXT NOT NULL DEFAULT 'none',
                evaluated_reasons_json TEXT NOT NULL DEFAULT '[]',
                evaluated_source_version_kind TEXT NOT NULL DEFAULT '',
                evaluated_source_version_id TEXT NOT NULL DEFAULT '',
                evaluated_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(kb_id, profile),
                CHECK(pending_severity IN ('none', 'soft_stale', 'hard_stale')),
                CHECK(evaluated_severity IN ('none', 'soft_stale', 'hard_stale')),
                FOREIGN KEY(kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agentic_ready_automation (
                kb_id TEXT NOT NULL,
                profile TEXT NOT NULL,
                automation_state TEXT NOT NULL DEFAULT 'idle',
                running_generation INTEGER,
                last_attempted_generation INTEGER NOT NULL DEFAULT 0,
                claim_token TEXT,
                claimed_at TEXT,
                lease_expires_at TEXT,
                last_attempt_publication_id TEXT,
                last_success_at TEXT,
                last_error TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY(kb_id, profile),
                CHECK(automation_state IN (
                    'idle', 'running', 'awaiting_publish', 'succeeded',
                    'failed', 'pending'
                )),
                FOREIGN KEY(kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE,
                FOREIGN KEY(last_attempt_publication_id)
                    REFERENCES agentic_ready_publications(publication_id) ON DELETE SET NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agentic_ready_automation_lock (
                lock_name TEXT PRIMARY KEY,
                claim_token TEXT,
                claimed_at TEXT,
                lease_expires_at TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agentic_ready_publication_gc (
                publication_id TEXT PRIMARY KEY,
                retention_class TEXT NOT NULL,
                state TEXT NOT NULL,
                marked_at TEXT NOT NULL,
                claim_token TEXT,
                quarantine_dir TEXT,
                claimed_at TEXT,
                lease_expires_at TEXT,
                deleted_at TEXT,
                last_error TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                CHECK(retention_class = 'redundant_duplicate'),
                CHECK(state IN ('eligible', 'claimed', 'deleted', 'delete_failed')),
                FOREIGN KEY(publication_id)
                    REFERENCES agentic_ready_publications(publication_id) ON DELETE CASCADE
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weekly_update_summaries (
                id TEXT PRIMARY KEY,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                file_count INTEGER NOT NULL DEFAULT 0,
                files_json TEXT NOT NULL DEFAULT '[]',
                summary_markdown TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(period_start, period_end)
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
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_agentic_ready_manifests_kb_profile
            ON agentic_ready_manifests(kb_id, profile)
            """
        )
        self._migrate_agentic_ready_publication_attempt_schema()
        self._ensure_columns(
            "agentic_ready_publications",
            {
                "attempt_disposition": "TEXT NOT NULL DEFAULT ''",
                "smoke_result_json": "TEXT NOT NULL DEFAULT '{}'",
            },
        )
        self._ensure_columns(
            "agentic_ready_slots",
            {
                "automatic_build_enabled": "INTEGER NOT NULL DEFAULT 0",
                "publication_revision": "INTEGER NOT NULL DEFAULT 0",
            },
        )
        self._conn.execute(
            """
            UPDATE agentic_ready_slots
            SET automatic_build_enabled = 1
            WHERE automatic_publish_enabled = 1
              AND automatic_build_enabled = 0
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_agentic_ready_publications_kb_profile
            ON agentic_ready_publications(kb_id, profile, created_at DESC)
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_agentic_ready_publications_identity
            ON agentic_ready_publications(
                kb_id, source_version_kind, source_version_id, profile,
                artifact_digest, created_at DESC
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_agentic_ready_publication_gc_retention
            ON agentic_ready_publication_gc(retention_class, state, marked_at, publication_id)
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_agentic_ready_automation_candidate
            ON agentic_ready_automation(automation_state, lease_expires_at, updated_at)
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_weekly_update_summaries_period
            ON weekly_update_summaries(period_start, period_end)
            """
        )
        self._ensure_columns(
            "kb_index_versions",
            {
                "embedding_provider": "TEXT NOT NULL DEFAULT 'openai'",
                "embedding_dimension": "INTEGER",
            },
        )
        rows = self._conn.execute(
            """
            SELECT index_version_id, embedding_provider, embedding_model, embedding_dimension
            FROM kb_index_versions
            """
        ).fetchall()
        for row in rows:
            index_version_id, provider, model, dimension = row
            resolved_provider = (
                str(provider or "").strip().lower()
                or infer_embedding_provider(model, fallback="openai")
                or "openai"
            )
            resolved_dimension = (
                int(dimension)
                if dimension not in (None, "")
                else infer_embedding_dimension(model)
            )
            if resolved_provider != str(provider or "").strip().lower() or resolved_dimension != dimension:
                self._conn.execute(
                    """
                    UPDATE kb_index_versions
                    SET embedding_provider = ?, embedding_dimension = ?
                    WHERE index_version_id = ?
                    """,
                    (resolved_provider, resolved_dimension, index_version_id),
                )
        if self._table_exists("rag_knowledge_bases"):
            self._conn.execute(
                """
                DELETE FROM kb_ready_index_state
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM rag_knowledge_bases AS kb
                    WHERE kb.kb_id = kb_ready_index_state.kb_id
                )
                """
            )
            kb_has_created_at = "created_at" in {
                str(row[1])
                for row in self._conn.execute(
                    "PRAGMA table_info(rag_knowledge_bases)"
                ).fetchall()
            }
            if kb_has_created_at:
                self._conn.execute(
                    """
                    DELETE FROM kb_ready_index_state
                    WHERE EXISTS (
                    SELECT 1
                    FROM rag_knowledge_bases AS kb
                    WHERE kb.kb_id = kb_ready_index_state.kb_id
                      AND julianday(kb_ready_index_state.updated_at)
                          < julianday(kb.created_at)
                    )
                    """
                )
            lifecycle_predicate = (
                "AND julianday(current.created_at) >= julianday(kb.created_at)"
                if kb_has_created_at
                else ""
            )
            self._conn.execute(
                f"""
                INSERT OR IGNORE INTO kb_ready_index_state (
                    kb_id, index_version_id, embedding_provider,
                    embedding_model, embedding_dimension, updated_at
                )
                SELECT
                    current.kb_id,
                    current.index_version_id,
                    current.embedding_provider,
                    current.embedding_model,
                    current.embedding_dimension,
                    current.created_at
                FROM kb_index_versions AS current
                JOIN rag_knowledge_bases AS kb ON kb.kb_id = current.kb_id
                WHERE current.status = 'ready'
                  {lifecycle_predicate}
                  AND NOT EXISTS (
                      SELECT 1
                      FROM kb_index_versions AS newer
                      WHERE newer.kb_id = current.kb_id
                        AND newer.status = 'ready'
                        AND (
                            newer.created_at > current.created_at
                            OR (
                                newer.created_at = current.created_at
                                AND newer.index_version_id > current.index_version_id
                            )
                        )
                  )
                """
            )
        self._ensure_columns(
            "kb_chunk_bindings",
            {
                "binding_mode": "TEXT NOT NULL DEFAULT 'pin'",
                "target_profile_id": "TEXT",
            },
        )
        self._ensure_columns(
            "agentic_ready_manifests",
            {
                "publication_id": "TEXT",
                "index_version_id": "TEXT",
                "source_version_kind": "TEXT",
                "source_version_id": "TEXT",
                "artifact_digest": "TEXT",
            },
        )
        self._ensure_rag_kb_embedding_columns()
        self._schema_commit()

    def _migrate_agentic_ready_publication_attempt_schema(self) -> None:
        """Remove the draft logical-identity UNIQUE constraint without losing slots."""
        identity_columns = {
            "kb_id",
            "source_version_kind",
            "source_version_id",
            "profile",
            "artifact_digest",
        }
        has_identity_unique = False
        for row in self._conn.execute(
            "PRAGMA index_list(agentic_ready_publications)"
        ).fetchall():
            if not bool(row[2]):
                continue
            columns = {
                str(item[2])
                for item in self._conn.execute(
                    f"PRAGMA index_info({json.dumps(str(row[1]))})"
                ).fetchall()
            }
            if columns == identity_columns:
                has_identity_unique = True
                break
        if not has_identity_unique:
            return

        replacement = "agentic_ready_publications_attempts_new"
        self._schema_commit()
        foreign_keys_enabled = bool(
            self._conn.execute("PRAGMA foreign_keys").fetchone()[0]
        )
        self._conn.execute("PRAGMA foreign_keys=OFF")
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.execute(f"DROP TABLE IF EXISTS {replacement}")
            self._conn.execute(
                f"""
                CREATE TABLE {replacement} (
                    publication_id TEXT PRIMARY KEY,
                    kb_id TEXT NOT NULL,
                    index_version_id TEXT,
                    source_version_kind TEXT NOT NULL,
                    source_version_id TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    profile_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    output_dir TEXT NOT NULL,
                    artifact_files_json TEXT NOT NULL DEFAULT '[]',
                    doc_count INTEGER NOT NULL DEFAULT 0,
                    section_count INTEGER NOT NULL DEFAULT 0,
                    built_at TEXT,
                    artifact_digest TEXT NOT NULL,
                    source_db TEXT,
                    schema_versions_json TEXT NOT NULL DEFAULT '{{}}',
                    error_message TEXT,
                    validated_at TEXT,
                    published_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE
                )
                """
            )
            columns = (
                "publication_id, kb_id, index_version_id, source_version_kind, "
                "source_version_id, profile, profile_version, status, output_dir, "
                "artifact_files_json, doc_count, section_count, built_at, "
                "artifact_digest, source_db, schema_versions_json, error_message, "
                "validated_at, published_at, created_at, updated_at"
            )
            self._conn.execute(
                f"INSERT INTO {replacement} ({columns}) "
                f"SELECT {columns} FROM agentic_ready_publications"
            )
            self._conn.execute("DROP TABLE agentic_ready_publications")
            self._conn.execute(
                f"ALTER TABLE {replacement} RENAME TO agentic_ready_publications"
            )
            violations = []
            for table in (
                "agentic_ready_publications",
                "agentic_ready_slots",
            ):
                violations.extend(
                    self._conn.execute(
                        f"PRAGMA foreign_key_check({table})"
                    ).fetchall()
                )
            if violations:
                raise RuntimeError(
                    "ready-data publication attempt migration broke foreign-key references"
                )
            self._schema_commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            self._conn.execute(
                f"PRAGMA foreign_keys={'ON' if foreign_keys_enabled else 'OFF'}"
            )
            restored = bool(
                self._conn.execute("PRAGMA foreign_keys").fetchone()[0]
            )
            if restored != foreign_keys_enabled:
                raise RuntimeError(
                    "ready-data publication migration could not restore foreign-key mode"
                )

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
        self._schema_commit()

    def _ensure_rag_kb_embedding_columns(self) -> None:
        cur = self._conn.execute("PRAGMA table_info(rag_knowledge_bases)")
        existing = {row[1] for row in cur.fetchall()}
        if not existing:
            return
        changed = False
        if "embedding_provider" not in existing:
            self._conn.execute("ALTER TABLE rag_knowledge_bases ADD COLUMN embedding_provider TEXT NOT NULL DEFAULT 'openai'")
            changed = True
        if "embedding_dimension" not in existing:
            self._conn.execute("ALTER TABLE rag_knowledge_bases ADD COLUMN embedding_dimension INTEGER")
            changed = True
        if "chunk_profile_id" not in existing:
            self._conn.execute("ALTER TABLE rag_knowledge_bases ADD COLUMN chunk_profile_id TEXT")
            changed = True
        if "index_dirty_at" not in existing:
            self._conn.execute("ALTER TABLE rag_knowledge_bases ADD COLUMN index_dirty_at TEXT")
            changed = True
        rows = self._conn.execute(
            """
            SELECT kb_id, embedding_provider, embedding_model, embedding_dimension
            FROM rag_knowledge_bases
            """
        ).fetchall()
        for kb_id, provider, model, dimension in rows:
            resolved_provider = (
                str(provider or "").strip().lower()
                or infer_embedding_provider(model, fallback="openai")
                or "openai"
            )
            resolved_dimension = (
                int(dimension)
                if dimension not in (None, "")
                else infer_embedding_dimension(model)
            )
            if resolved_provider != str(provider or "").strip().lower() or resolved_dimension != dimension:
                self._conn.execute(
                    """
                    UPDATE rag_knowledge_bases
                    SET embedding_provider = ?, embedding_dimension = ?
                    WHERE kb_id = ?
                    """,
                    (resolved_provider, resolved_dimension, kb_id),
                )
                changed = True
        if changed:
            self._schema_commit()

    def _schema_commit(self) -> None:
        if getattr(self, "_defer_schema_commits", False):
            return
        self._conn.commit()

    def _table_exists(self, table: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
            (table,),
        ).fetchone()
        return row is not None

    def _maybe_commit(self) -> None:
        if self._tx_depth == 0:
            self._conn.commit()

    @contextmanager
    def transaction(self, *, immediate: bool = False):
        sp_name = None
        if self._tx_depth == 0:
            self._conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
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
        self._schema_commit()

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
        "id", "provider", "category", "instance_id", "label", "is_default", "api_key_encrypted",
        "api_base_url", "status", "created_at", "updated_at", "notes",
    )

    def upsert_llm_provider(
        self,
        provider: str,
        api_key_encrypted: str,
        base_url: str | None = None,
        notes: str | None = None,
        category: str = "llm",
        *,
        instance_id: str = "default",
        label: str | None = None,
        is_default: bool = True,
    ) -> int:
        """Insert or update an LLM provider API token instance."""
        ts = self.now()
        normalized_instance = str(instance_id or "default").strip() or "default"
        normalized_label = str(label or "").strip() or f"{provider} ({category})"
        if is_default:
            self._conn.execute(
                "UPDATE api_tokens SET is_default = 0, updated_at = ? WHERE provider=? AND category=?",
                (ts, provider, category),
            )
        self._conn.execute(
            """
            INSERT INTO api_tokens
                (provider, category, instance_id, label, is_default, api_key_encrypted, api_base_url, status, created_at, updated_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
            ON CONFLICT(provider, category, instance_id) DO UPDATE SET
                label = excluded.label,
                is_default = excluded.is_default,
                api_key_encrypted = excluded.api_key_encrypted,
                api_base_url = excluded.api_base_url,
                notes = excluded.notes,
                updated_at = excluded.updated_at,
                status = excluded.status
            """,
            (provider, category, normalized_instance, normalized_label, 1 if is_default else 0, api_key_encrypted, base_url, ts, ts, notes),
        )
        row = self._conn.execute(
            "SELECT id FROM api_tokens WHERE provider=? AND category=? AND instance_id=?",
            (provider, category, normalized_instance),
        ).fetchone()
        self._maybe_commit()
        return int(row[0]) if row else 0

    def get_llm_provider(
        self, provider: str, category: str = "llm", instance_id: str | None = None
    ) -> dict | None:
        """Get a single LLM provider record, defaulting to the default instance."""
        if instance_id:
            cur = self._conn.execute(
                "SELECT id, provider, category, instance_id, label, is_default, api_key_encrypted, api_base_url, status, "
                "created_at, updated_at, notes FROM api_tokens WHERE provider=? AND category=? AND instance_id=?",
                (provider, category, instance_id),
            )
        else:
            cur = self._conn.execute(
                "SELECT id, provider, category, instance_id, label, is_default, api_key_encrypted, api_base_url, status, "
                "created_at, updated_at, notes FROM api_tokens WHERE provider=? AND category=? "
                "ORDER BY is_default DESC, updated_at DESC, id DESC LIMIT 1",
                (provider, category),
            )
        row = cur.fetchone()
        if row is None:
            return None
        return dict(zip(self._LLM_TOKEN_COLS, row))

    def list_llm_providers(self, category: str = "llm") -> list[dict]:
        """List all LLM provider records for the given category."""
        cur = self._conn.execute(
            "SELECT id, provider, category, instance_id, label, is_default, api_key_encrypted, api_base_url, status, "
            "created_at, updated_at, notes FROM api_tokens WHERE category=? "
            "ORDER BY provider, is_default DESC, updated_at DESC, id DESC",
            (category,),
        )
        return [dict(zip(self._LLM_TOKEN_COLS, row)) for row in cur.fetchall()]

    def delete_llm_provider(self, provider: str, category: str = "llm", instance_id: str | None = None) -> bool:
        """Delete an LLM provider record."""
        if instance_id:
            cur = self._conn.execute(
                "DELETE FROM api_tokens WHERE provider=? AND category=? AND instance_id=?",
                (provider, category, instance_id),
            )
        else:
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

    @staticmethod
    def _canonical_ready_data_keywords(raw: object) -> str:
        """Canonicalize keywords exactly as the ready-data builder consumes them."""
        text = str(raw or "").strip()
        if not text:
            values: object = []
        elif text.startswith("["):
            try:
                values = json.loads(text)
            except json.JSONDecodeError:
                values = [part.strip() for part in text.split(",") if part.strip()]
        else:
            values = [part.strip() for part in text.split(",") if part.strip()]
        return json.dumps(
            values,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def _ready_data_builder_metadata_snapshot(self, file_url: str) -> tuple[object, ...]:
        """Return one file's canonical builder-visible Catalog/file metadata."""
        row = self._conn.execute(
            """
            SELECT c.status, f.title, c.category, c.summary, c.keywords,
                   c.markdown_content, c.rag_chunk_count,
                   f.source_site, f.published_time
            FROM catalog_items c
            LEFT JOIN files f ON f.url = c.file_url
            WHERE c.file_url = ?
            LIMIT 1
            """,
            (file_url,),
        ).fetchone()
        if not row or row[0] != "ok":
            return ("inactive",)
        return (
            "ok",
            row[1] or file_url,
            row[2] or "general",
            row[3] or "",
            self._canonical_ready_data_keywords(row[4]),
            str(row[5] or ""),
            row[6] or 0,
            row[7] or "",
            row[8] or "",
        )

    def _ready_data_metadata_affected_kb_ids(self, file_url: str) -> tuple[str, ...]:
        if not self._table_exists("rag_knowledge_bases") or not self._table_exists(
            "rag_kb_files"
        ):
            return ()
        rows = self._conn.execute(
            """
            SELECT DISTINCT kb.kb_id
            FROM rag_kb_files kf
            JOIN rag_knowledge_bases kb ON kb.kb_id = kf.kb_id
            WHERE kf.file_url = ?
            ORDER BY kb.kb_id
            """,
            (file_url,),
        ).fetchall()
        return tuple(str(row[0]) for row in rows if row[0])

    def _mark_ready_data_builder_metadata_change(
        self,
        *,
        file_url: str,
        before: tuple[object, ...],
        explicit_deletion: bool = False,
    ) -> tuple[str, ...]:
        """Compare canonical snapshots and mark each affected KB at most once."""
        after = self._ready_data_builder_metadata_snapshot(file_url)
        if before == after:
            return ()
        before_ok = before[0] == "ok"
        after_ok = after[0] == "ok"
        if explicit_deletion and not after_ok:
            reason = "source_deleted"
        elif after_ok:
            reason = "metadata_updated"
        elif before_ok:
            reason = "source_invalidated"
        else:
            return ()
        kb_ids = self._ready_data_metadata_affected_kb_ids(file_url)
        for kb_id in kb_ids:
            self.mark_agentic_ready_source_event_for_kb(kb_id=kb_id, reason=reason)
        return kb_ids
    
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
        with self.transaction(immediate=True):
            before = self._ready_data_builder_metadata_snapshot(url)
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
            self._mark_ready_data_builder_metadata_change(file_url=url, before=before)

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
        with self.transaction(immediate=True):
            before = self._ready_data_builder_metadata_snapshot(url)
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
            self._mark_ready_data_builder_metadata_change(file_url=url, before=before)

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
        'first_seen': 'f.first_seen',
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
        file_url = item.get("url")
        with self.transaction(immediate=True):
            before = self._ready_data_builder_metadata_snapshot(file_url)
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
                    file_url,
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
            self._mark_ready_data_builder_metadata_change(
                file_url=file_url,
                before=before,
                explicit_deletion=str(status or "").strip().lower() == "deleted",
            )

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
            for part in _split_visible_categories(row[0]):
                categories.add(part)
        return sorted(categories, key=lambda x: x.lower())

    def get_applied_taxonomy_hash(self) -> str | None:
        """Return the last applied categories.yaml hash, or None if never applied."""
        row = self._conn.execute(
            "SELECT applied_hash FROM taxonomy_state WHERE id = 1"
        ).fetchone()
        return None if row is None else row[0]

    def set_applied_taxonomy_hash(self, applied_hash: str) -> None:
        """Record the categories.yaml hash as applied (single-row upsert)."""
        with self.transaction():
            self._conn.execute(
                """
                INSERT INTO taxonomy_state (id, applied_hash, applied_at)
                VALUES (1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    applied_hash = excluded.applied_hash,
                    applied_at = excluded.applied_at
                """,
                (applied_hash,),
            )

    def current_taxonomy_hash(self) -> str:
        """Hash of the current categories.yaml taxonomy content.

        A missing or empty config yields a stable sentinel hash rather than
        raising, so the catalog block and the reminder never crash on a
        misconfigured taxonomy file.
        """
        from ai_actuarial.shared_runtime import get_categories_config_path
        from ai_actuarial.utils import load_category_config, taxonomy_hash

        try:
            config = load_category_config(get_categories_config_path())
        except FileNotFoundError:
            config = None
        return taxonomy_hash(config if isinstance(config, dict) else {})

    def _seed_taxonomy_state_if_empty(self) -> None:
        """Establish the baseline applied hash on first run.

        Before any re-categorization has ever run, the on-disk taxonomy is what
        classified the existing catalog items, so seed applied_hash = current
        hash. This prevents catalog from being spuriously blocked while the
        taxonomy_state table is still empty after migration.
        """
        if self.db_path == ":memory:":
            return
        if self.get_applied_taxonomy_hash() is None:
            self.set_applied_taxonomy_hash(self.current_taxonomy_hash())

    def taxonomy_needs_recategory(self) -> bool:
        """True when the current categories.yaml differs from the last applied hash."""
        return self.current_taxonomy_hash() != self.get_applied_taxonomy_hash()

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
        
        # Join with catalog_items when query/category filters need catalog fields,
        # and later for result projection even without filters.
        join_clause = ""

        if query:
            join_clause = "LEFT JOIN catalog_items c ON c.file_url = f.url"
            filters.append(
                "(LOWER(IFNULL(f.title, '')) LIKE ? "
                "OR LOWER(IFNULL(f.original_filename, '')) LIKE ? "
                "OR LOWER(IFNULL(f.url, '')) LIKE ? "
                "OR LOWER(IFNULL(c.summary, '')) LIKE ? "
                "OR LOWER(IFNULL(c.keywords, '')) LIKE ? "
                "OR LOWER(IFNULL(c.category, '')) LIKE ? "
                "OR LOWER(IFNULL(c.markdown_content, '')) LIKE ?)"
            )
            search_term = f"%{query.lower()}%"
            params.extend([search_term] * 7)
        
        if source:
            filters.append("LOWER(f.source_site) LIKE ?")
            params.append(f"%{source.lower()}%")
        
        if category:
            join_clause = "LEFT JOIN catalog_items c ON c.file_url = f.url"
            if category == '__uncategorized__':
                filters.append(
                    "("
                    "c.file_url IS NULL "
                    "OR TRIM(IFNULL(c.category, '')) = '' "
                    "OR TRIM(IFNULL(c.summary, '')) = '' "
                    "OR (TRIM(IFNULL(c.category, '')) != '' AND TRIM(IFNULL(c.category, '')) LIKE '(%)')"
                    ")"
                )
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
    
    def list_files_first_seen_between(
        self,
        *,
        period_start: str,
        period_end: str,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Return non-deleted files first discovered in [period_start, period_end)."""
        safe_limit = max(1, min(int(limit or 500), 5000))
        cur = self._conn.execute(
            """
            SELECT
                f.url, f.title, f.source_site, f.source_page_url, f.original_filename,
                f.bytes, f.content_type, f.published_time, f.first_seen, f.last_seen,
                ci.summary, ci.category, ci.keywords
            FROM files f
            LEFT JOIN catalog_items ci ON ci.file_url = f.url
            WHERE f.deleted_at IS NULL
              AND f.first_seen IS NOT NULL
              AND f.first_seen >= ?
              AND f.first_seen < ?
            ORDER BY f.first_seen DESC, f.url ASC
            LIMIT ?
            """,
            (period_start, period_end, safe_limit),
        )
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]
        files = []
        for row in rows:
            item = dict(zip(columns, row))
            raw_keywords = item.get("keywords")
            if isinstance(raw_keywords, str) and raw_keywords.strip():
                try:
                    item["keywords"] = json.loads(raw_keywords)
                except json.JSONDecodeError:
                    item["keywords"] = [raw_keywords]
            elif raw_keywords in (None, ""):
                item["keywords"] = []
            files.append(item)
        return files

    def _decode_weekly_update_summary_row(self, row: sqlite3.Row | tuple[Any, ...] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        keys = [
            "id",
            "period_start",
            "period_end",
            "generated_at",
            "file_count",
            "files_json",
            "summary_markdown",
            "metadata_json",
        ]
        data = dict(zip(keys, row))
        for json_field, output_field, default in (
            ("files_json", "files", []),
            ("metadata_json", "metadata", {}),
        ):
            try:
                data[output_field] = json.loads(data.pop(json_field) or json.dumps(default))
            except json.JSONDecodeError:
                data[output_field] = default
        return data

    def upsert_weekly_update_summary(self, summary: dict[str, Any]) -> dict[str, Any]:
        period_start = str(summary.get("period_start") or "").strip()
        period_end = str(summary.get("period_end") or "").strip()
        if not period_start or not period_end:
            raise ValueError("period_start and period_end are required")
        generated_at = self.now()
        summary_id = str(summary.get("id") or f"weekly-{period_start}-{period_end}")
        files = list(summary.get("files") or [])
        metadata = dict(summary.get("metadata") or {})
        file_count = int(summary.get("file_count", len(files)) or 0)
        summary_markdown = str(summary.get("summary_markdown") or "")
        self._conn.execute(
            """
            INSERT INTO weekly_update_summaries (
                id, period_start, period_end, generated_at, file_count,
                files_json, summary_markdown, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(period_start, period_end) DO UPDATE SET
                generated_at=excluded.generated_at,
                file_count=excluded.file_count,
                files_json=excluded.files_json,
                summary_markdown=excluded.summary_markdown,
                metadata_json=excluded.metadata_json
            """,
            (
                summary_id,
                period_start,
                period_end,
                generated_at,
                file_count,
                json.dumps(files, ensure_ascii=False, sort_keys=True),
                summary_markdown,
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            ),
        )
        self._maybe_commit()
        return self.get_weekly_update_summary(period_start=period_start, period_end=period_end) or {}

    def get_weekly_update_summary(self, *, period_start: str, period_end: str) -> dict[str, Any] | None:
        cur = self._conn.execute(
            """
            SELECT id, period_start, period_end, generated_at, file_count,
                   files_json, summary_markdown, metadata_json
            FROM weekly_update_summaries
            WHERE period_start = ? AND period_end = ?
            LIMIT 1
            """,
            (period_start, period_end),
        )
        return self._decode_weekly_update_summary_row(cur.fetchone())

    def get_latest_weekly_update_summary(self) -> dict[str, Any] | None:
        cur = self._conn.execute(
            """
            SELECT id, period_start, period_end, generated_at, file_count,
                   files_json, summary_markdown, metadata_json
            FROM weekly_update_summaries
            ORDER BY period_start DESC, generated_at DESC
            LIMIT 1
            """
        )
        return self._decode_weekly_update_summary_row(cur.fetchone())

    def list_weekly_update_summaries(self, *, limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        safe_limit = max(1, min(int(limit or 20), 100))
        safe_offset = max(0, int(offset or 0))
        total = int(self._conn.execute("SELECT COUNT(*) FROM weekly_update_summaries").fetchone()[0])
        cur = self._conn.execute(
            """
            SELECT id, period_start, period_end, generated_at, file_count,
                   files_json, summary_markdown, metadata_json
            FROM weekly_update_summaries
            ORDER BY period_start DESC, generated_at DESC
            LIMIT ? OFFSET ?
            """,
            (safe_limit, safe_offset),
        )
        summaries = [self._decode_weekly_update_summary_row(row) or {} for row in cur.fetchall()]
        return summaries, total

    def mark_file_deleted(self, url: str, deleted_time: str) -> None:
        """Mark a file and its catalog item as deleted.

        Args:
            url: File URL
            deleted_time: ISO timestamp for deletion
        """
        with self.transaction(immediate=True):
            before = self._ready_data_builder_metadata_snapshot(url)
            self._conn.execute(
                "UPDATE files SET deleted_at = ? WHERE url = ?",
                (deleted_time, url),
            )
            self._conn.execute(
                "UPDATE catalog_items SET status = 'deleted' WHERE file_url = ?",
                (url,),
            )
            self._mark_ready_data_builder_metadata_change(
                file_url=url,
                before=before,
                explicit_deletion=True,
            )
    
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
    
    def update_file_metadata(
        self,
        url: str,
        *,
        title: str | None = None,
        category: str | None = None,
        summary: str | None = None,
        keywords: list | None = None,
    ) -> tuple[bool, str | None]:
        """Update builder-visible file/Catalog metadata as one source mutation."""
        with self.transaction(immediate=True):
            before = self._ready_data_builder_metadata_snapshot(url)
            file_exists = self._conn.execute(
                "SELECT 1 FROM files WHERE url = ?",
                (url,),
            ).fetchone()
            if not file_exists:
                return (False, "file_not_found")

            catalog_updates = any(
                value is not None for value in (category, summary, keywords)
            )
            if title is None and not catalog_updates:
                return (False, "no_updates")

            if title is not None:
                self._conn.execute(
                    "UPDATE files SET title = ? WHERE url = ?",
                    (title, url),
                )

            if catalog_updates:
                self._conn.execute(
                    """
                    INSERT INTO catalog_items (file_url, sha256, pipeline_version, status)
                    SELECT url, sha256, 'manual', 'ok' FROM files WHERE url = ?
                    ON CONFLICT(file_url) DO NOTHING
                    """,
                    (url,),
                )
                updates: list[str] = []
                params: list[object] = []
                if category is not None:
                    updates.append("category = ?")
                    params.append(category)
                if summary is not None:
                    updates.append("summary = ?")
                    params.append(summary)
                if keywords is not None:
                    updates.append("keywords = ?")
                    params.append(json.dumps(keywords) if keywords else "")
                updates.append("updated_at = CURRENT_TIMESTAMP")
                params.append(url)
                self._conn.execute(
                    f"UPDATE catalog_items SET {', '.join(updates)} WHERE file_url = ?",
                    tuple(params),
                )

            self._mark_ready_data_builder_metadata_change(
                file_url=url,
                before=before,
            )
            return (True, None)

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
        return self.update_file_metadata(
            url,
            category=category,
            summary=summary,
            keywords=keywords,
        )
    
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
        with self.transaction(immediate=True):
            before = self._ready_data_builder_metadata_snapshot(url)
            file_exists = self._conn.execute(
                "SELECT 1 FROM files WHERE url = ?",
                (url,),
            ).fetchone()
            if not file_exists:
                return (False, "file_not_found")
            self._conn.execute(
                """
                INSERT INTO catalog_items (file_url, sha256, pipeline_version, status)
                SELECT url, sha256, 'manual', 'ok' FROM files WHERE url = ?
                ON CONFLICT(file_url) DO NOTHING
                """,
                (url,),
            )
            self._conn.execute(
                """
                UPDATE catalog_items
                SET markdown_content = ?,
                    markdown_updated_at = CURRENT_TIMESTAMP,
                    markdown_source = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE file_url = ?
                """,
                (markdown_content, markdown_source, url),
            )
            self._mark_ready_data_builder_metadata_change(
                file_url=url,
                before=before,
            )
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

    def delete_chunk_profile(self, profile_id: str) -> dict[str, Any] | None:
        existing = self.get_chunk_profile(profile_id)
        if not existing:
            return None

        chunk_set_count = int(
            self._conn.execute(
                "SELECT COUNT(*) FROM file_chunk_sets WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()[0]
        )
        binding_count = int(
            self._conn.execute(
                """
                SELECT COUNT(*)
                FROM kb_chunk_bindings
                WHERE chunk_set_id IN (
                    SELECT chunk_set_id
                    FROM file_chunk_sets
                    WHERE profile_id = ?
                )
                """,
                (profile_id,),
            ).fetchone()[0]
        )

        self._conn.execute(
            "DELETE FROM chunk_profiles WHERE profile_id = ?",
            (profile_id,),
        )
        self._maybe_commit()

        return {
            "profile_id": profile_id,
            "name": existing["name"],
            "deleted": True,
            "deleted_chunk_sets": chunk_set_count,
            "deleted_bindings": binding_count,
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
        with self.transaction(immediate=True):
            current_rows = self._conn.execute(
                """
                SELECT chunk_index, chunk_id, content, token_count, section_hierarchy
                FROM global_chunks
                WHERE chunk_set_id = ?
                ORDER BY chunk_index, chunk_id
                """,
                (chunk_set_id,),
            ).fetchall()
            current_chunks = tuple(
                (
                    int(row[0]),
                    str(row[1]),
                    str(row[2]),
                    int(row[3] or 0),
                    row[4],
                )
                for row in current_rows
            )
            current_n = len(current_chunks)
            if current_n > 0 and not overwrite:
                return {
                    "chunk_set_id": chunk_set_id,
                    "chunk_count": current_n,
                    "replaced": False,
                    "inserted": 0,
                }

            final_chunks_by_index: dict[int, tuple[int, str, str, int, Any]] = {}
            for idx, chunk in enumerate(chunks):
                chunk_data = chunk or {}
                section_hierarchy = chunk_data.get("section_hierarchy")
                if isinstance(section_hierarchy, (int, float)):
                    section_hierarchy = self._conn.execute(
                        "SELECT CAST(? AS TEXT)",
                        (section_hierarchy,),
                    ).fetchone()[0]
                elif isinstance(section_hierarchy, (bytes, bytearray, memoryview)):
                    section_hierarchy = bytes(section_hierarchy)
                chunk_index = int(
                    chunk_data.get("chunk_index")
                    if chunk_data.get("chunk_index") is not None
                    else idx
                )
                final_chunks_by_index[chunk_index] = (
                    chunk_index,
                    f"{chunk_set_id}:{chunk_index}",
                    str(chunk_data.get("content") or ""),
                    int(chunk_data.get("token_count") or 0),
                    section_hierarchy,
                )
            final_chunks = tuple(
                final_chunks_by_index[chunk_index]
                for chunk_index in sorted(final_chunks_by_index)
            )
            if final_chunks == current_chunks:
                return {
                    "chunk_set_id": chunk_set_id,
                    "chunk_count": current_n,
                    "replaced": False,
                    "inserted": 0,
                }

            affected_kb_ids = self._ready_data_chunk_content_affected_kb_ids(
                chunk_set_id=chunk_set_id,
            )
            if current_n > 0:
                self._conn.execute("DELETE FROM global_chunks WHERE chunk_set_id = ?", (chunk_set_id,))

            now = self._utcnow_iso()
            for chunk_index, chunk_id, content, token_count, section_hierarchy in final_chunks:
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                self._conn.execute(
                    """
                    INSERT INTO global_chunks (
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

            inserted = len(final_chunks)

            self._conn.execute(
                """
                UPDATE file_chunk_sets
                SET chunk_count = ?, status = 'ready', updated_at = ?
                WHERE chunk_set_id = ?
                """,
                (inserted, now, chunk_set_id),
            )

            reason = "source_invalidated" if current_n > 0 and not final_chunks else "chunk_content_updated"
            for kb_id in affected_kb_ids:
                self.mark_agentic_ready_source_event_for_kb(
                    kb_id=kb_id,
                    reason=reason,
                )

        return {
            "chunk_set_id": chunk_set_id,
            "chunk_count": inserted,
            "replaced": current_n > 0,
            "inserted": inserted,
        }

    def _ready_data_chunk_content_affected_kb_ids(
        self,
        *,
        chunk_set_id: str,
    ) -> tuple[str, ...]:
        """Return KBs whose exact builder input includes one chunk set."""
        if not self._table_exists("rag_knowledge_bases") or not self._table_exists("rag_kb_files"):
            return ()
        rows = self._conn.execute(
            """
            SELECT DISTINCT kb.kb_id
            FROM file_chunk_sets target
            JOIN files f ON f.url = target.file_url
            JOIN catalog_items c
              ON c.file_url = target.file_url
             AND c.status = 'ok'
            JOIN rag_kb_files kf ON kf.file_url = target.file_url
            JOIN rag_knowledge_bases kb ON kb.kb_id = kf.kb_id
            WHERE target.chunk_set_id = ?
              AND (
                EXISTS (
                    SELECT 1
                    FROM kb_chunk_bindings selected
                    JOIN rag_kb_files selected_kf
                      ON selected_kf.kb_id = selected.kb_id
                     AND selected_kf.file_url = selected.file_url
                    JOIN catalog_items selected_c
                      ON selected_c.file_url = selected.file_url
                     AND selected_c.status = 'ok'
                    JOIN file_chunk_sets selected_fcs
                      ON selected_fcs.chunk_set_id = selected.chunk_set_id
                     AND selected_fcs.file_url = selected.file_url
                    WHERE selected.kb_id = kb.kb_id
                      AND selected.file_url = target.file_url
                      AND selected.chunk_set_id = target.chunk_set_id
                )
                OR NOT EXISTS (
                    SELECT 1
                    FROM kb_chunk_bindings bound
                    JOIN rag_kb_files bound_kf
                      ON bound_kf.kb_id = bound.kb_id
                     AND bound_kf.file_url = bound.file_url
                    JOIN catalog_items bound_c
                      ON bound_c.file_url = bound.file_url
                     AND bound_c.status = 'ok'
                    JOIN file_chunk_sets bound_fcs
                      ON bound_fcs.chunk_set_id = bound.chunk_set_id
                     AND bound_fcs.file_url = bound.file_url
                    WHERE bound.kb_id = kb.kb_id
                )
              )
            ORDER BY kb.kb_id
            """,
            (chunk_set_id,),
        ).fetchall()
        return tuple(str(row[0]) for row in rows if row[0])

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
        with self.transaction(immediate=True):
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
            before_has_selection = self._has_ready_data_bound_chunk_selection(kb_id)
            before_selection = self._ready_data_bound_chunk_selection(
                kb_id,
                file_url=file_url,
            )
            now = self._utcnow_iso()

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
                response = {
                    "kb_id": kb_id,
                    "file_url": file_url,
                    "chunk_set_id": chunk_set_id,
                    "binding_mode": mode,
                    "target_profile_id": target_profile_id or "",
                    "created": False,
                }
            else:
                self._conn.execute(
                    """
                    INSERT INTO kb_chunk_bindings (
                        kb_id, file_url, chunk_set_id, bound_at, bound_by, binding_mode, target_profile_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (kb_id, file_url, chunk_set_id, now, bound_by, mode, target_profile_id),
                )
                response = {
                    "kb_id": kb_id,
                    "file_url": file_url,
                    "chunk_set_id": chunk_set_id,
                    "binding_mode": mode,
                    "target_profile_id": target_profile_id or "",
                    "created": True,
                }

            after_selection = self._ready_data_bound_chunk_selection(
                kb_id,
                file_url=file_url,
            )
            self._mark_ready_data_binding_selection_change(
                kb_id=kb_id,
                before_has_selection=before_has_selection,
                before=before_selection,
                after=after_selection,
            )
        return response

    def sync_follow_latest_bindings_for_chunk_set(
        self,
        *,
        file_url: str,
        profile_id: str,
        chunk_set_id: str,
        bound_by: str = "system_follow_latest",
    ) -> dict[str, Any]:
        """Move follow_latest bindings to the newest chunk_set for same file/profile."""
        matching_rows_sql = """
            SELECT kb_id, file_url, chunk_set_id
            FROM kb_chunk_bindings
            WHERE file_url = ?
              AND binding_mode = 'follow_latest'
              AND COALESCE(target_profile_id, '') = ?
              AND chunk_set_id != ?
        """
        matching_params = (file_url, profile_id, chunk_set_id)
        noop_response = {
            "file_url": file_url,
            "profile_id": profile_id,
            "chunk_set_id": chunk_set_id,
            "synced_bindings": 0,
            "affected_kb_ids": [],
        }
        if not self._conn.execute(
            f"{matching_rows_sql} LIMIT 1",
            matching_params,
        ).fetchone():
            return noop_response

        affected_kb_ids: set[str] = set()
        synced = 0
        with self.transaction(immediate=True):
            rows = self._conn.execute(matching_rows_sql, matching_params).fetchall()
            if not rows:
                return noop_response

            target = self._conn.execute(
                """
                SELECT file_url, profile_id
                FROM file_chunk_sets
                WHERE chunk_set_id = ?
                LIMIT 1
                """,
                (chunk_set_id,),
            ).fetchone()
            if not target:
                raise ValueError("chunk_set_id not found")
            if (target[0] or "") != file_url or (target[1] or "") != profile_id:
                raise ValueError("chunk_set_id does not belong to the specified file_url/profile_id")

            candidate_kb_ids = {
                str(row[0] or "")
                for row in rows
                if str(row[0] or "")
            }
            before_has_selections = {
                kb_id: self._has_ready_data_bound_chunk_selection(kb_id)
                for kb_id in candidate_kb_ids
            }
            before_selections = {
                kb_id: self._ready_data_bound_chunk_selection(
                    kb_id,
                    file_url=file_url,
                )
                for kb_id in candidate_kb_ids
            }
            now = self._utcnow_iso()
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

            for kb_id in sorted(affected_kb_ids):
                self._mark_ready_data_binding_selection_change(
                    kb_id=kb_id,
                    before_has_selection=before_has_selections[kb_id],
                    before=before_selections[kb_id],
                    after=self._ready_data_bound_chunk_selection(
                        kb_id,
                        file_url=file_url,
                    ),
                )

        return {
            "file_url": file_url,
            "profile_id": profile_id,
            "chunk_set_id": chunk_set_id,
            "synced_bindings": synced,
            "affected_kb_ids": sorted(affected_kb_ids),
        }

    def _ready_data_bound_chunk_selection(
        self,
        kb_id: str,
        *,
        file_url: str | None = None,
    ) -> frozenset[tuple[str, str]]:
        """Return bindings that can select the builder's bound-chunk mode for one KB."""
        if not self._table_exists("rag_knowledge_bases") or not self._table_exists("rag_kb_files"):
            return frozenset()
        file_filter = " AND b.file_url = ?" if file_url is not None else ""
        params: tuple[str, ...] = (kb_id, file_url) if file_url is not None else (kb_id,)
        rows = self._conn.execute(
            f"""
            SELECT DISTINCT b.file_url, b.chunk_set_id
            FROM kb_chunk_bindings b
            JOIN rag_knowledge_bases kb ON kb.kb_id = b.kb_id
            JOIN rag_kb_files kf
              ON kf.kb_id = b.kb_id
             AND kf.file_url = b.file_url
            JOIN catalog_items c
              ON c.file_url = b.file_url
             AND c.status = 'ok'
            JOIN file_chunk_sets fcs
              ON fcs.chunk_set_id = b.chunk_set_id
             AND fcs.file_url = b.file_url
            WHERE b.kb_id = ?
            {file_filter}
            """,
            params,
        ).fetchall()
        return frozenset(
            (str(row[0] or ""), str(row[1] or ""))
            for row in rows
            if row[0] and row[1]
        )

    def _has_ready_data_bound_chunk_selection(self, kb_id: str) -> bool:
        if not self._table_exists("rag_knowledge_bases") or not self._table_exists("rag_kb_files"):
            return False
        return bool(
            self._conn.execute(
                """
                SELECT 1
                FROM kb_chunk_bindings b
                JOIN rag_knowledge_bases kb ON kb.kb_id = b.kb_id
                JOIN rag_kb_files kf
                  ON kf.kb_id = b.kb_id
                 AND kf.file_url = b.file_url
                JOIN catalog_items c
                  ON c.file_url = b.file_url
                 AND c.status = 'ok'
                JOIN file_chunk_sets fcs
                  ON fcs.chunk_set_id = b.chunk_set_id
                 AND fcs.file_url = b.file_url
                WHERE b.kb_id = ?
                LIMIT 1
                """,
                (kb_id,),
            ).fetchone()
        )

    def _mark_ready_data_binding_selection_change(
        self,
        *,
        kb_id: str,
        before_has_selection: bool,
        before: frozenset[tuple[str, str]],
        after: frozenset[tuple[str, str]],
    ) -> None:
        if before == after:
            return
        reason = (
            "access_scope_restricted"
            if not before_has_selection and after
            else "chunk_binding_updated"
        )
        self.mark_agentic_ready_source_event_for_kb(kb_id=kb_id, reason=reason)

    def list_file_index_status(self, file_url: str) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            """
            SELECT
                b.kb_id,
                COUNT(DISTINCT b.chunk_set_id) AS chunk_set_count,
                COALESCE((
                    SELECT iv.embedding_provider
                    FROM kb_index_versions iv
                    WHERE iv.kb_id = b.kb_id
                    ORDER BY COALESCE(iv.built_at, iv.created_at) DESC
                    LIMIT 1
                ), '') AS embedding_provider,
                COALESCE((
                    SELECT iv.embedding_model
                    FROM kb_index_versions iv
                    WHERE iv.kb_id = b.kb_id
                    ORDER BY COALESCE(iv.built_at, iv.created_at) DESC
                    LIMIT 1
                ), '') AS embedding_model,
                (
                    SELECT iv.embedding_dimension
                    FROM kb_index_versions iv
                    WHERE iv.kb_id = b.kb_id
                    ORDER BY COALESCE(iv.built_at, iv.created_at) DESC
                    LIMIT 1
                ) AS embedding_dimension,
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
                    "embedding_provider": row[2] or "",
                    "embedding_model": row[3] or "",
                    "embedding_dimension": row[4],
                    "indexed_at": row[5],
                    "indexed_chunk_count": row[6] or 0,
                }
            )
        return out

    def get_kb_composition_status(self, kb_id: str) -> dict[str, Any]:
        self._ensure_rag_kb_embedding_columns()
        binding_file_count = int(
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
            SELECT embedding_provider, embedding_model, embedding_dimension, index_type, status, chunk_count, built_at, created_at
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
        kb_row = self._conn.execute(
            """
            SELECT embedding_provider, embedding_model, embedding_dimension, chunk_count, file_count, updated_at, index_dirty_at
            FROM rag_knowledge_bases
            WHERE kb_id = ?
            """,
            (kb_id,),
        ).fetchone()
        kb_provider = ""
        kb_model = ""
        kb_dimension = None
        kb_chunk_count = 0
        kb_file_count = 0
        kb_updated_at = None
        index_dirty_at = None
        if kb_row:
            kb_provider = kb_row[0] or infer_embedding_provider(kb_row[1], fallback="openai") or "openai"
            kb_model = kb_row[1] or ""
            kb_dimension = kb_row[2] if kb_row[2] not in (None, "") else infer_embedding_dimension(kb_row[1])
            kb_chunk_count = int((kb_row[3] or 0) or 0)
            kb_file_count = int((kb_row[4] or 0) or 0)
            kb_updated_at = kb_row[5]
            index_dirty_at = kb_row[6]

        if self._table_exists("rag_kb_files"):
            kb_file_count_row = self._conn.execute(
                "SELECT COUNT(*) FROM rag_kb_files WHERE kb_id = ?",
                (kb_id,),
            ).fetchone()
            kb_file_count = int((kb_file_count_row[0] if kb_file_count_row else 0) or kb_file_count)

            indexed_stats = self._conn.execute(
                """
                SELECT
                    SUM(CASE WHEN indexed_at IS NOT NULL AND indexed_at != '' THEN 1 ELSE 0 END),
                    MAX(indexed_at)
                FROM rag_kb_files
                WHERE kb_id = ?
                """,
                (kb_id,),
            ).fetchone()
            indexed_file_count = int((indexed_stats[0] or 0) if indexed_stats else 0)
            legacy_index_time = indexed_stats[1] if indexed_stats else None

            pending_file_count_row = self._conn.execute(
                """
                SELECT COUNT(*)
                FROM rag_kb_files kf
                LEFT JOIN catalog_items c ON c.file_url = kf.file_url
                WHERE kf.kb_id = ?
                  AND (
                    kf.indexed_at IS NULL
                    OR kf.indexed_at = ''
                    OR (
                        c.markdown_updated_at IS NOT NULL
                        AND c.markdown_updated_at > kf.indexed_at
                    )
                  )
                """,
                (kb_id,),
            ).fetchone()
            pending_file_count = int((pending_file_count_row[0] if pending_file_count_row else 0) or 0)
        else:
            indexed_file_count = kb_file_count if kb_chunk_count > 0 else 0
            legacy_index_time = kb_updated_at
            pending_file_count = 0

        has_index = bool(latest)
        latest_index_time = (latest[6] or latest[7]) if latest else None
        if not has_index and (indexed_file_count > 0 or kb_chunk_count > 0):
            has_index = True
            latest_index_time = legacy_index_time or kb_updated_at

        effective_file_count = max(binding_file_count, kb_file_count)
        dirty_after_index = bool(
            index_dirty_at
            and (
                not latest_index_time
                or index_dirty_at > latest_index_time
            )
        )
        needs_reindex = bool(
            (
                effective_file_count > 0
                and (
                    pending_file_count > 0
                    or outdated_binding_count > 0
                    or not has_index
                    or (latest_binding_at and latest_index_time and latest_binding_at > latest_index_time)
                )
            )
            or (
                has_index
                and dirty_after_index
            )
        )
        latest_index_payload = None
        if latest:
            latest_index_payload = {
                "embedding_provider": latest[0] or infer_embedding_provider(latest[1], fallback="openai") or "openai",
                "embedding_model": latest[1],
                "embedding_dimension": latest[2] if latest[2] not in (None, "") else infer_embedding_dimension(latest[1]),
                "index_type": latest[3],
                "status": latest[4],
                "chunk_count": latest[5] or 0,
                "built_at": latest[6] or latest[7],
            }
        elif has_index:
            latest_index_payload = {
                "embedding_provider": kb_provider or "openai",
                "embedding_model": kb_model,
                "embedding_dimension": kb_dimension,
                "index_type": "Flat",
                "status": "ready",
                "chunk_count": kb_chunk_count,
                "built_at": latest_index_time,
                "source": "legacy",
            }
        return {
            "kb_id": kb_id,
            "file_count": effective_file_count,
            "binding_file_count": binding_file_count,
            "kb_file_count": kb_file_count,
            "indexed_file_count": indexed_file_count,
            "pending_file_count": pending_file_count,
            "chunk_set_count": chunk_set_count,
            "has_index": has_index,
            "latest_binding_at": latest_binding_at,
            "index_dirty_at": index_dirty_at,
            "dirty_after_index": dirty_after_index,
            "binding_mode_counts": {
                "follow_latest": follow_latest_count,
                "pin": pin_count,
            },
            "outdated_binding_count": outdated_binding_count,
            "new_chunk_versions_available": outdated_binding_count > 0,
            "needs_reindex": needs_reindex,
            "latest_index": latest_index_payload,
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

    def upsert_agentic_ready_manifest(
        self,
        *,
        kb_id: str,
        profile: str,
        profile_version: str,
        status: str,
        output_dir: str = "",
        artifact_files: list[str] | None = None,
        doc_count: int = 0,
        section_count: int = 0,
        built_at: str | None = None,
        source_db: str = "",
        schema_versions: dict[str, Any] | None = None,
        error_message: str = "",
        publication_id: str = "",
        index_version_id: str | None = None,
        source_version_kind: str = "",
        source_version_id: str = "",
        artifact_digest: str = "",
    ) -> dict[str, Any]:
        """Create or replace the latest Agentic ready-data manifest registry row."""
        normalized_profile = str(profile or "general").strip().lower() or "general"
        normalized_status = str(status or "missing").strip().lower() or "missing"
        now = self._utcnow_iso()
        existing = self._conn.execute(
            """
            SELECT manifest_id, created_at
            FROM agentic_ready_manifests
            WHERE kb_id = ? AND profile = ?
            LIMIT 1
            """,
            (kb_id, normalized_profile),
        ).fetchone()
        manifest_id = existing[0] if existing else f"arm_{uuid.uuid4().hex}"
        created_at = existing[1] if existing else now
        artifact_files_json = json.dumps(artifact_files or [], ensure_ascii=False)
        schema_versions_json = json.dumps(schema_versions or {}, ensure_ascii=False, sort_keys=True)
        self._conn.execute(
            """
            INSERT INTO agentic_ready_manifests (
                manifest_id, kb_id, profile, profile_version, status, output_dir,
                artifact_files_json, doc_count, section_count, built_at, source_db,
                schema_versions_json, error_message, created_at, updated_at,
                publication_id, index_version_id, source_version_kind,
                source_version_id, artifact_digest
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(kb_id, profile) DO UPDATE SET
                profile_version = excluded.profile_version,
                status = excluded.status,
                output_dir = excluded.output_dir,
                artifact_files_json = excluded.artifact_files_json,
                doc_count = excluded.doc_count,
                section_count = excluded.section_count,
                built_at = excluded.built_at,
                source_db = excluded.source_db,
                schema_versions_json = excluded.schema_versions_json,
                error_message = excluded.error_message,
                publication_id = excluded.publication_id,
                index_version_id = excluded.index_version_id,
                source_version_kind = excluded.source_version_kind,
                source_version_id = excluded.source_version_id,
                artifact_digest = excluded.artifact_digest,
                updated_at = excluded.updated_at
            """,
            (
                manifest_id,
                kb_id,
                normalized_profile,
                str(profile_version or "1"),
                normalized_status,
                output_dir,
                artifact_files_json,
                int(doc_count or 0),
                int(section_count or 0),
                built_at,
                source_db,
                schema_versions_json,
                error_message,
                created_at,
                now,
                publication_id,
                index_version_id,
                source_version_kind,
                source_version_id,
                artifact_digest,
            ),
        )
        self._maybe_commit()
        return self.get_agentic_ready_manifest(kb_id=kb_id, profile=normalized_profile) or {}

    def get_agentic_ready_manifest(self, *, kb_id: str, profile: str = "general") -> dict[str, Any] | None:
        normalized_profile = str(profile or "general").strip().lower() or "general"
        row = self._conn.execute(
            """
            SELECT manifest_id, kb_id, profile, profile_version, status, output_dir,
                   artifact_files_json, doc_count, section_count, built_at, source_db,
                   schema_versions_json, error_message, created_at, updated_at,
                   publication_id, index_version_id, source_version_kind,
                   source_version_id, artifact_digest
            FROM agentic_ready_manifests
            WHERE kb_id = ? AND profile = ?
            LIMIT 1
            """,
            (kb_id, normalized_profile),
        ).fetchone()
        if not row:
            return None
        return self._agentic_manifest_row_to_dict(row)

    def list_agentic_ready_manifests(self, kb_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT manifest_id, kb_id, profile, profile_version, status, output_dir,
                   artifact_files_json, doc_count, section_count, built_at, source_db,
                   schema_versions_json, error_message, created_at, updated_at,
                   publication_id, index_version_id, source_version_kind,
                   source_version_id, artifact_digest
            FROM agentic_ready_manifests
            WHERE kb_id = ?
            ORDER BY updated_at DESC
            """,
            (kb_id,),
        ).fetchall()
        return [self._agentic_manifest_row_to_dict(row) for row in rows]

    def _agentic_manifest_row_to_dict(self, row: Any) -> dict[str, Any]:
        try:
            artifact_files = json.loads(row[6] or "[]")
        except Exception:
            artifact_files = []
        try:
            schema_versions = json.loads(row[11] or "{}")
        except Exception:
            schema_versions = {}
        return {
            "manifest_id": row[0],
            "kb_id": row[1],
            "profile": row[2],
            "profile_version": row[3],
            "status": row[4],
            "output_dir": row[5] or "",
            "artifact_files": artifact_files if isinstance(artifact_files, list) else [],
            "doc_count": row[7] or 0,
            "section_count": row[8] or 0,
            "built_at": row[9],
            "source_db": row[10] or "",
            "schema_versions": schema_versions if isinstance(schema_versions, dict) else {},
            "error_message": row[12] or "",
            "created_at": row[13],
            "updated_at": row[14],
            "publication_id": row[15] or "",
            "index_version_id": row[16],
            "source_version_kind": row[17] or "",
            "source_version_id": row[18] or "",
            "artifact_digest": row[19] or "",
        }

    @staticmethod
    def _agentic_ready_path_keys(value: str | None) -> set[str]:
        raw = str(value or "").strip()
        if not raw:
            return set()
        absolute = Path(os.path.abspath(raw))
        keys = {os.path.normcase(os.path.normpath(str(absolute)))}
        try:
            keys.add(
                os.path.normcase(os.path.normpath(str(absolute.resolve(strict=False))))
            )
        except OSError:
            pass
        return keys

    @staticmethod
    def _agentic_ready_path_key_sets_overlap(
        left_keys: set[str],
        right_keys: set[str],
    ) -> bool:
        for left in left_keys:
            for right in right_keys:
                try:
                    common = os.path.commonpath((left, right))
                except ValueError:
                    continue
                if common in {left, right}:
                    return True
        return False

    def _agentic_ready_paths_conflict(
        self,
        publication_id: str,
        *paths: str,
        include_manifests: bool = True,
    ) -> bool:
        candidate_keys: set[str] = set()
        for path in paths:
            candidate_keys.update(self._agentic_ready_path_keys(path))
        if not candidate_keys:
            return False
        rows = self._conn.execute(
            """
            SELECT publication.publication_id, publication.output_dir
            FROM agentic_ready_publications AS publication
            LEFT JOIN agentic_ready_publication_gc AS gc
              ON gc.publication_id = publication.publication_id
            WHERE publication.publication_id <> ?
              AND publication.output_dir <> ''
              AND COALESCE(gc.state, '') <> 'deleted'
            """,
            (publication_id,),
        ).fetchall()
        if include_manifests:
            rows.extend(
                self._conn.execute(
                    """
                    SELECT COALESCE(publication_id, ''), output_dir
                    FROM agentic_ready_manifests
                    WHERE COALESCE(publication_id, '') <> ? AND output_dir <> ''
                    """,
                    (publication_id,),
                ).fetchall()
            )
        rows.extend(
            self._conn.execute(
                """
                SELECT publication_id, quarantine_dir
                FROM agentic_ready_publication_gc
                WHERE publication_id <> ?
                  AND quarantine_dir IS NOT NULL AND quarantine_dir <> ''
                  AND state IN ('claimed', 'delete_failed')
                """,
                (publication_id,),
            ).fetchall()
        )
        return any(
            self._agentic_ready_path_key_sets_overlap(
                candidate_keys,
                self._agentic_ready_path_keys(str(row[1] or "")),
            )
            for row in rows
        )

    def record_agentic_ready_publication(
        self,
        *,
        kb_id: str,
        index_version_id: str | None,
        source_version_kind: str,
        source_version_id: str,
        profile: str,
        profile_version: str,
        status: str,
        output_dir: str,
        artifact_digest: str,
        artifact_files: list[str] | None = None,
        doc_count: int = 0,
        section_count: int = 0,
        built_at: str | None = None,
        source_db: str = "",
        schema_versions: dict[str, Any] | None = None,
        smoke_result: dict[str, Any] | None = None,
        error_message: str = "",
    ) -> dict[str, Any]:
        """Persist one independent validated or failed ready-data build attempt."""
        normalized_profile = str(profile or "general").strip().lower() or "general"
        normalized_status = str(status or "failed").strip().lower() or "failed"
        if normalized_status not in {"failed", "validated"}:
            raise ValueError("publication status must be 'failed' or 'validated'")
        normalized_index_version_id = str(index_version_id).strip() if index_version_id else None
        normalized_source_kind = str(source_version_kind or "").strip().lower()
        normalized_source_id = str(source_version_id or "").strip()
        if not normalized_source_kind or not normalized_source_id:
            raise ValueError("source_version_kind and source_version_id are required")
        normalized_digest = str(artifact_digest or "").strip()
        if not normalized_digest:
            raise ValueError("artifact_digest is required")
        normalized_smoke_result = self._bounded_agentic_ready_smoke_result(
            smoke_result
        )

        now = self._utcnow_iso()
        publication_id = f"arp_{uuid.uuid4().hex}"
        with self.transaction():
            self._conn.execute(
                "UPDATE rag_knowledge_bases SET kb_id = kb_id WHERE kb_id = ?",
                (kb_id,),
            )
            if normalized_status == "validated" and self._agentic_ready_paths_conflict(
                publication_id,
                str(output_dir or ""),
                include_manifests=not normalized_source_kind.startswith("legacy"),
            ):
                raise ValueError("ready-data publication output path is already reserved")
            self._conn.execute(
                """
                INSERT INTO agentic_ready_publications (
                    publication_id, kb_id, index_version_id, source_version_kind,
                    source_version_id, profile, profile_version, status, output_dir,
                    artifact_files_json, doc_count, section_count, built_at,
                    artifact_digest, source_db, schema_versions_json, smoke_result_json,
                    error_message, validated_at, published_at, attempt_disposition,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, '', ?, ?)
                """,
                (
                    publication_id,
                    kb_id,
                    normalized_index_version_id,
                    normalized_source_kind,
                    normalized_source_id,
                    normalized_profile,
                    str(profile_version or "1"),
                    normalized_status,
                    str(output_dir or ""),
                    json.dumps(artifact_files or [], ensure_ascii=False),
                    int(doc_count or 0),
                    int(section_count or 0),
                    built_at,
                    normalized_digest,
                    source_db,
                    json.dumps(schema_versions or {}, ensure_ascii=False, sort_keys=True),
                    json.dumps(normalized_smoke_result, ensure_ascii=False, sort_keys=True),
                    error_message,
                    now if normalized_status == "validated" else None,
                    now,
                    now,
                ),
            )
        return self.get_agentic_ready_publication(publication_id) or {}

    @staticmethod
    def _bounded_agentic_ready_smoke_result(
        value: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}

        def text(key: str, limit: int) -> str:
            return " ".join(str(value.get(key) or "").split())[:limit].rstrip()

        def integer(key: str, *, maximum: int) -> int:
            try:
                parsed = int(value.get(key) or 0)
            except (TypeError, ValueError, OverflowError):
                return 0
            return max(0, min(parsed, maximum))

        result = {
            "contract_version": text("contract_version", 64),
            "status": text("status", 32),
            "checked_at": text("checked_at", 64),
            "elapsed_ms": integer("elapsed_ms", maximum=86_400_000),
            "query_source": text("query_source", 32),
            "query": text("query", 160),
            "query_sha256": text("query_sha256", 64),
            "matched_doc_id": text("matched_doc_id", 512),
            "matched_file_url": text("matched_file_url", 512),
            "failure_reason": text("failure_reason", 160),
            "catalog_doc_count": integer(
                "catalog_doc_count",
                maximum=2_147_483_647,
            ),
        }
        return result

    def discard_agentic_ready_publication(
        self,
        publication_id: str,
        *,
        expected_active_publication_id: str,
    ) -> bool:
        """Remove an unserved validated duplicate before its staging directory is cleaned."""
        with self.transaction():
            result = self._conn.execute(
                """
                DELETE FROM agentic_ready_publications
                WHERE publication_id = ?
                  AND status = 'validated'
                  AND COALESCE(attempt_disposition, '') = ''
                  AND NOT EXISTS (
                      SELECT 1
                      FROM agentic_ready_slots
                      WHERE active_publication_id = ? OR previous_publication_id = ?
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM agentic_ready_publication_gc
                      WHERE publication_id = agentic_ready_publications.publication_id
                  )
                  AND EXISTS (
                      SELECT 1
                      FROM agentic_ready_slots
                      WHERE kb_id = agentic_ready_publications.kb_id
                        AND profile = agentic_ready_publications.profile
                        AND active_publication_id = ?
                  )
                """,
                (
                    publication_id,
                    publication_id,
                    publication_id,
                    expected_active_publication_id,
                ),
            )
        return result.rowcount == 1

    def mark_agentic_ready_publication_redundant_duplicate(
        self,
        publication_id: str,
        *,
        expected_active_publication_id: str,
    ) -> bool:
        """Classify one validated same-identity attempt for governed retention."""
        now = self._utcnow_iso()
        with self.transaction():
            candidate_lock = self._conn.execute(
                "UPDATE agentic_ready_publications SET updated_at = updated_at WHERE publication_id = ?",
                (publication_id,),
            )
            if candidate_lock.rowcount != 1:
                return False
            candidate = self.get_agentic_ready_publication(publication_id)
            active = self.get_agentic_ready_publication(expected_active_publication_id)
            if (
                not candidate
                or not active
                or candidate["status"] != "validated"
                or bool(candidate["attempt_disposition"])
                or active["status"] != "active"
                or any(
                    candidate[field] != active[field]
                    for field in (
                        "kb_id",
                        "profile",
                        "source_version_kind",
                        "source_version_id",
                        "artifact_digest",
                    )
                )
                or self._agentic_ready_paths_conflict(
                    publication_id,
                    str(candidate["output_dir"]),
                )
            ):
                return False
            slot = self._conn.execute(
                """
                SELECT active_publication_id, previous_publication_id
                FROM agentic_ready_slots
                WHERE kb_id = ? AND profile = ?
                LIMIT 1
                """,
                (candidate["kb_id"], candidate["profile"]),
            ).fetchone()
            if (
                not slot
                or slot[0] != expected_active_publication_id
                or publication_id in {slot[0], slot[1]}
            ):
                return False
            existing = self._conn.execute(
                """
                SELECT retention_class, state
                FROM agentic_ready_publication_gc
                WHERE publication_id = ?
                """,
                (publication_id,),
            ).fetchone()
            if existing:
                return tuple(existing) == ("redundant_duplicate", "eligible")
            self._conn.execute(
                """
                INSERT INTO agentic_ready_publication_gc (
                    publication_id, retention_class, state, marked_at,
                    claim_token, quarantine_dir, claimed_at, lease_expires_at, deleted_at,
                    last_error, updated_at
                )
                VALUES (?, 'redundant_duplicate', 'eligible', ?, NULL, NULL, NULL, NULL, NULL, '', ?)
                """,
                (publication_id, now, now),
            )
        return True

    def mark_agentic_ready_publication_superseded_generation(
        self,
        publication_id: str,
    ) -> bool:
        """Reserve a non-serving validated attempt for future superseded retention."""
        now = self._utcnow_iso()
        with self.transaction(immediate=True):
            current = self.get_agentic_ready_publication(publication_id)
            if (
                not current
                or current["status"] != "validated"
                or current["attempt_disposition"]
                not in {"", "superseded_generation"}
                or self._conn.execute(
                    """
                    SELECT 1 FROM agentic_ready_slots
                    WHERE active_publication_id = ? OR previous_publication_id = ?
                    LIMIT 1
                    """,
                    (publication_id, publication_id),
                ).fetchone()
                or self._conn.execute(
                    """
                    SELECT 1 FROM agentic_ready_manifests
                    WHERE publication_id = ?
                    LIMIT 1
                    """,
                    (publication_id,),
                ).fetchone()
            ):
                return False
            if current["retention_class"]:
                if (
                    current["retention_class"] != "redundant_duplicate"
                    or current["gc_state"] != "eligible"
                ):
                    return False
                self._conn.execute(
                    "DELETE FROM agentic_ready_publication_gc WHERE publication_id = ?",
                    (publication_id,),
                )
            elif current["attempt_disposition"] == "superseded_generation":
                return True
            result = self._conn.execute(
                """
                UPDATE agentic_ready_publications
                SET attempt_disposition = 'superseded_generation', updated_at = ?
                WHERE publication_id = ?
                  AND status = 'validated'
                  AND attempt_disposition IN ('', 'superseded_generation')
                """,
                (now, publication_id),
            )
            if result.rowcount != 1:
                raise RuntimeError(
                    "ready-data superseded-generation disposition lost its guard"
                )
        return True

    def _agentic_ready_publication_columns(self) -> frozenset[str]:
        cached = self._agentic_ready_publication_columns_cache
        if cached is None:
            cached = frozenset(
                str(row[1])
                for row in self._conn.execute(
                    "PRAGMA table_info(agentic_ready_publications)"
                ).fetchall()
            )
            self._agentic_ready_publication_columns_cache = cached
        return cached

    def get_agentic_ready_publication(self, publication_id: str) -> dict[str, Any] | None:
        publication_columns = self._agentic_ready_publication_columns()
        attempt_disposition_sql = (
            "p.attempt_disposition"
            if "attempt_disposition" in publication_columns
            else "''"
        )
        smoke_result_sql = (
            "p.smoke_result_json"
            if "smoke_result_json" in publication_columns
            else "'{}'"
        )
        row = self._conn.execute(
            f"""
            SELECT p.publication_id, p.kb_id, p.index_version_id, p.profile,
                   p.profile_version, p.source_version_kind, p.source_version_id,
                   p.status, p.output_dir, p.artifact_files_json, p.doc_count,
                   p.section_count, p.built_at, p.artifact_digest, p.source_db,
                   p.schema_versions_json, p.error_message, p.validated_at,
                   p.published_at, {attempt_disposition_sql}, p.created_at, p.updated_at,
                   g.retention_class, g.state, g.marked_at, g.claim_token,
                   g.quarantine_dir, g.claimed_at, g.lease_expires_at,
                   g.deleted_at, g.last_error,
                   g.updated_at, {smoke_result_sql}
            FROM agentic_ready_publications p
            LEFT JOIN agentic_ready_publication_gc g
              ON g.publication_id = p.publication_id
            WHERE p.publication_id = ?
            LIMIT 1
            """,
            (publication_id,),
        ).fetchone()
        if not row:
            return None
        try:
            artifact_files = json.loads(row[9] or "[]")
        except Exception:
            artifact_files = []
        try:
            schema_versions = json.loads(row[15] or "{}")
        except Exception:
            schema_versions = {}
        try:
            smoke_result = json.loads(row[32] or "{}")
        except Exception:
            smoke_result = {}
        return {
            "publication_id": row[0],
            "kb_id": row[1],
            "index_version_id": row[2],
            "source_version_kind": row[5],
            "source_version_id": row[6],
            "profile": row[3],
            "profile_version": row[4],
            "status": row[7],
            "output_dir": row[8] or "",
            "artifact_files": artifact_files if isinstance(artifact_files, list) else [],
            "doc_count": row[10] or 0,
            "section_count": row[11] or 0,
            "built_at": row[12],
            "artifact_digest": row[13] or "",
            "source_db": row[14] or "",
            "schema_versions": schema_versions if isinstance(schema_versions, dict) else {},
            "smoke_result": smoke_result if isinstance(smoke_result, dict) else {},
            "error_message": row[16] or "",
            "validated_at": row[17],
            "published_at": row[18],
            "attempt_disposition": row[19] or "",
            "created_at": row[20],
            "updated_at": row[21],
            "retention_class": row[22] or "",
            "gc_state": row[23] or "",
            "gc_marked_at": row[24],
            "gc_claim_token": row[25] or "",
            "gc_quarantine_dir": row[26] or "",
            "gc_claimed_at": row[27],
            "gc_lease_expires_at": row[28],
            "gc_deleted_at": row[29],
            "gc_last_error": row[30] or "",
            "gc_updated_at": row[31],
        }

    def list_agentic_ready_publications_for_gc(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT publication_id
            FROM agentic_ready_publications
            ORDER BY kb_id, profile, publication_id
            """
        ).fetchall()
        return [
            publication
            for row in rows
            if (publication := self.get_agentic_ready_publication(str(row[0]))) is not None
        ]

    def list_agentic_ready_slots_for_gc(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT kb_id, profile, active_publication_id, previous_publication_id, updated_at
            FROM agentic_ready_slots
            ORDER BY kb_id, profile
            """
        ).fetchall()
        return [
            {
                "kb_id": row[0],
                "profile": row[1],
                "active_publication_id": row[2],
                "previous_publication_id": row[3],
                "updated_at": row[4],
            }
            for row in rows
        ]

    def claim_agentic_ready_publication_gc(
        self,
        publication_id: str,
        *,
        expected_gc_state: str,
        expected_marked_at: str,
        quarantine_dir: str,
        cutoff_at: str | None = None,
        minimum_age_days: int = 14,
        keep_latest: int = 2,
        claim_lease_seconds: int = 300,
        expected_claim_token: str = "",
    ) -> dict[str, Any] | None:
        """CAS-claim a non-serving redundant attempt before filesystem mutation."""
        normalized_state = str(expected_gc_state or "").strip().lower()
        if normalized_state not in {"eligible", "claimed", "delete_failed"}:
            return None
        now = self._utcnow_iso()
        now_dt = self._parse_iso_to_utc(now)
        cutoff_dt = self._parse_iso_to_utc(cutoff_at) if cutoff_at else now_dt
        if now_dt is None or cutoff_dt is None:
            raise ValueError("ready-data GC claim timestamps are invalid")
        if minimum_age_days < 0 or keep_latest < 0 or claim_lease_seconds <= 0:
            raise ValueError("ready-data GC claim policy is invalid")
        lease_expires_at = (now_dt + timedelta(seconds=claim_lease_seconds)).isoformat()
        with self.transaction():
            publication_lock = self._conn.execute(
                "UPDATE agentic_ready_publications SET updated_at = updated_at WHERE publication_id = ?",
                (publication_id,),
            )
            if publication_lock.rowcount != 1:
                return None
            current = self.get_agentic_ready_publication(publication_id)
            if (
                not current
                or current["status"] != "validated"
                or bool(current["attempt_disposition"])
                or current["retention_class"] != "redundant_duplicate"
                or current["gc_state"] != normalized_state
                or current["gc_marked_at"] != expected_marked_at
                or self._agentic_ready_paths_conflict(
                    publication_id,
                    str(current["output_dir"]),
                    quarantine_dir,
                )
                or self._conn.execute(
                    """
                    SELECT 1 FROM agentic_ready_slots
                    WHERE active_publication_id = ? OR previous_publication_id = ?
                    LIMIT 1
                    """,
                    (publication_id, publication_id),
                ).fetchone()
                or self._conn.execute(
                    """
                    SELECT 1 FROM agentic_ready_manifests
                    WHERE publication_id = ?
                    LIMIT 1
                    """,
                    (publication_id,),
                ).fetchone()
            ):
                return None
            if normalized_state == "claimed":
                current_lease = self._parse_iso_to_utc(current["gc_lease_expires_at"])
                if (
                    current["gc_quarantine_dir"] != quarantine_dir
                    or current["gc_claim_token"] != expected_claim_token
                    or current_lease is None
                    or current_lease > cutoff_dt
                ):
                    return None
            elif normalized_state == "eligible":
                marked_at = self._parse_iso_to_utc(current["gc_marked_at"])
                if marked_at is None or marked_at > cutoff_dt - timedelta(days=minimum_age_days):
                    return None
                cohort = self._conn.execute(
                    """
                    SELECT p.publication_id, g.marked_at
                    FROM agentic_ready_publications p
                    JOIN agentic_ready_publication_gc g
                      ON g.publication_id = p.publication_id
                    WHERE p.kb_id = ? AND p.profile = ?
                      AND p.status = 'validated'
                      AND COALESCE(p.attempt_disposition, '') = ''
                      AND g.retention_class = 'redundant_duplicate'
                      AND g.state IN ('eligible', 'claimed', 'delete_failed')
                    """,
                    (current["kb_id"], current["profile"]),
                ).fetchall()
                ranked: list[tuple[datetime, str]] = []
                for cohort_id, cohort_marked_at in cohort:
                    parsed = self._parse_iso_to_utc(cohort_marked_at)
                    if parsed is not None:
                        ranked.append((parsed, str(cohort_id)))
                ranked.sort(reverse=True)
                if publication_id in {item[1] for item in ranked[:keep_latest]}:
                    return None
            claim_token = f"argc_{uuid.uuid4().hex}"
            result = self._conn.execute(
                """
                UPDATE agentic_ready_publication_gc
                SET state = 'claimed', claim_token = ?, quarantine_dir = ?,
                    claimed_at = ?, lease_expires_at = ?, last_error = '', updated_at = ?
                WHERE publication_id = ?
                  AND retention_class = 'redundant_duplicate'
                  AND state = ?
                  AND marked_at = ?
                """,
                (
                    claim_token,
                    quarantine_dir,
                    now,
                    lease_expires_at,
                    now,
                    publication_id,
                    normalized_state,
                    expected_marked_at,
                ),
            )
            if result.rowcount != 1:
                return None
        return self.get_agentic_ready_publication(publication_id)

    def finish_agentic_ready_publication_gc(
        self,
        publication_id: str,
        *,
        claim_token: str,
        deleted: bool,
        error_message: str = "",
    ) -> dict[str, Any] | None:
        """Finalize a claimed attempt as an audit tombstone or retryable failure."""
        now = self._utcnow_iso()
        with self.transaction():
            current = self.get_agentic_ready_publication(publication_id)
            if (
                not current
                or current["status"] != "validated"
                or bool(current["attempt_disposition"])
                or current["gc_state"] != "claimed"
                or current["gc_claim_token"] != claim_token
                or self._agentic_ready_paths_conflict(
                    publication_id,
                    str(current["output_dir"]),
                    str(current["gc_quarantine_dir"]),
                )
                or self._conn.execute(
                    """
                    SELECT 1 FROM agentic_ready_slots
                    WHERE active_publication_id = ? OR previous_publication_id = ?
                    LIMIT 1
                    """,
                    (publication_id, publication_id),
                ).fetchone()
                or self._conn.execute(
                    """
                    SELECT 1 FROM agentic_ready_manifests
                    WHERE publication_id = ?
                    LIMIT 1
                    """,
                    (publication_id,),
                ).fetchone()
            ):
                return None
            if deleted:
                publication_result = self._conn.execute(
                    """
                    UPDATE agentic_ready_publications
                    SET output_dir = '', artifact_files_json = '[]', updated_at = ?
                    WHERE publication_id = ? AND status = 'validated'
                    """,
                    (now, publication_id),
                )
                gc_result = self._conn.execute(
                    """
                    UPDATE agentic_ready_publication_gc
                    SET state = 'deleted', deleted_at = ?, lease_expires_at = NULL,
                        last_error = '', updated_at = ?
                    WHERE publication_id = ? AND state = 'claimed' AND claim_token = ?
                    """,
                    (now, now, publication_id, claim_token),
                )
                if publication_result.rowcount != 1 or gc_result.rowcount != 1:
                    raise RuntimeError("ready-data GC tombstone finalization lost its claim")
            else:
                result = self._conn.execute(
                    """
                    UPDATE agentic_ready_publication_gc
                    SET state = 'delete_failed', lease_expires_at = NULL,
                        last_error = ?, updated_at = ?
                    WHERE publication_id = ? AND state = 'claimed' AND claim_token = ?
                    """,
                    (str(error_message or "ready_data deletion failed"), now, publication_id, claim_token),
                )
                if result.rowcount != 1:
                    raise RuntimeError("ready-data GC failure finalization lost its claim")
        return self.get_agentic_ready_publication(publication_id)

    @staticmethod
    def _agentic_ready_severity_max(*values: str) -> str:
        rank = {"none": 0, "soft_stale": 1, "hard_stale": 2}
        return max(
            (str(value or "none") for value in values),
            key=lambda value: rank.get(value, -1),
        )

    @staticmethod
    def _agentic_ready_json_list(value: str | None) -> list[str]:
        try:
            parsed = json.loads(value or "[]")
        except (TypeError, ValueError):
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item) for item in parsed if str(item or "").strip()]

    def set_agentic_ready_automation(
        self,
        *,
        kb_id: str,
        profile: str = "general",
        automatic_build_enabled: bool,
        automatic_publish_enabled: bool,
    ) -> dict[str, Any]:
        """Persist a valid default-off automation combination without launching work."""
        if automatic_publish_enabled and not automatic_build_enabled:
            raise ValueError("automatic publish requires automatic build")
        normalized_profile = str(profile or "general").strip().lower() or "general"
        now = self._utcnow_iso()
        with self.transaction(immediate=True):
            kb_exists = self._conn.execute(
                "SELECT 1 FROM rag_knowledge_bases WHERE kb_id = ? LIMIT 1",
                (kb_id,),
            ).fetchone()
            if not kb_exists:
                raise ValueError("knowledge base not found")
            self._conn.execute(
                """
                INSERT INTO agentic_ready_slots (
                    kb_id, profile, active_publication_id, previous_publication_id,
                    automatic_build_enabled, automatic_publish_enabled, updated_at
                )
                VALUES (?, ?, NULL, NULL, ?, ?, ?)
                ON CONFLICT(kb_id, profile) DO UPDATE SET
                    automatic_build_enabled = excluded.automatic_build_enabled,
                    automatic_publish_enabled = excluded.automatic_publish_enabled,
                    updated_at = excluded.updated_at
                """,
                (
                    kb_id,
                    normalized_profile,
                    int(bool(automatic_build_enabled)),
                    int(bool(automatic_publish_enabled)),
                    now,
                ),
            )
        return self.get_agentic_ready_publication_state(
            kb_id=kb_id,
            profile=normalized_profile,
        )

    @staticmethod
    def _agentic_ready_automation_timestamp(now: datetime | None = None) -> str:
        value = now or datetime.now(timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    def get_agentic_ready_automation_state(
        self,
        *,
        kb_id: str,
        profile: str = "general",
        include_claim_token: bool = False,
    ) -> dict[str, Any]:
        normalized_profile = str(profile or "general").strip().lower() or "general"
        row = self._conn.execute(
            """
            SELECT a.automation_state, a.running_generation,
                   a.last_attempted_generation, a.claim_token,
                   a.claimed_at, a.lease_expires_at,
                   a.last_attempt_publication_id, a.last_success_at,
                   a.last_error, a.updated_at,
                   s.automatic_build_enabled, s.automatic_publish_enabled,
                   ss.event_generation, ss.pending_evaluation_generation,
                   ss.evaluated_generation
            FROM agentic_ready_slots AS s
            LEFT JOIN agentic_ready_automation AS a
              ON a.kb_id = s.kb_id AND a.profile = s.profile
            LEFT JOIN agentic_ready_source_state AS ss
              ON ss.kb_id = s.kb_id AND ss.profile = s.profile
            WHERE s.kb_id = ? AND s.profile = ?
            LIMIT 1
            """,
            (kb_id, normalized_profile),
        ).fetchone()
        if not row:
            return {
                "kb_id": kb_id,
                "profile": normalized_profile,
                "automation_state": "disabled",
                "running_generation": None,
                "last_attempted_generation": 0,
                "claim_token": None,
                "claimed_at": None,
                "lease_expires_at": None,
                "last_attempt_publication_id": None,
                "last_success_at": None,
                "last_error": "",
                "updated_at": None,
                "automatic_build_enabled": False,
                "automatic_publish_enabled": False,
                "event_generation": 0,
                "pending_evaluation_generation": None,
                "evaluated_generation": 0,
            }
        build_enabled = bool(row[10])
        pending_generation = int(row[13]) if row[13] is not None else None
        stored_state = str(row[0] or "")
        if stored_state:
            automation_state = stored_state
        elif not build_enabled:
            automation_state = "disabled"
        elif pending_generation is not None:
            automation_state = "pending"
        else:
            automation_state = "idle"
        return {
            "kb_id": kb_id,
            "profile": normalized_profile,
            "automation_state": automation_state,
            "running_generation": int(row[1]) if row[1] is not None else None,
            "last_attempted_generation": int(row[2] or 0),
            "claim_token": str(row[3]) if include_claim_token and row[3] else None,
            "claimed_at": row[4],
            "lease_expires_at": row[5],
            "last_attempt_publication_id": str(row[6]) if row[6] else None,
            "last_success_at": row[7],
            "last_error": str(row[8] or ""),
            "updated_at": row[9],
            "automatic_build_enabled": build_enabled,
            "automatic_publish_enabled": bool(row[11]),
            "event_generation": int(row[12] or 0),
            "pending_evaluation_generation": pending_generation,
            "evaluated_generation": int(row[14] or 0),
        }

    def _select_agentic_ready_automation_candidate(
        self,
        *,
        now_iso: str,
    ) -> sqlite3.Row | tuple[Any, ...] | None:
        return self._conn.execute(
            """
            SELECT s.kb_id, s.profile, ss.pending_evaluation_generation,
                   s.automatic_publish_enabled,
                   a.automation_state, a.running_generation,
                   a.last_attempted_generation, a.lease_expires_at,
                   a.last_attempt_publication_id,
                   p.status, p.attempt_disposition,
                   g.state, s.active_publication_id
            FROM agentic_ready_slots AS s
            JOIN rag_knowledge_bases AS kb ON kb.kb_id = s.kb_id
            JOIN agentic_ready_source_state AS ss
              ON ss.kb_id = s.kb_id AND ss.profile = s.profile
            LEFT JOIN agentic_ready_automation AS a
              ON a.kb_id = s.kb_id AND a.profile = s.profile
            LEFT JOIN agentic_ready_publications AS p
              ON p.publication_id = a.last_attempt_publication_id
            LEFT JOIN agentic_ready_publication_gc AS g
              ON g.publication_id = p.publication_id
            WHERE s.automatic_build_enabled = 1
              AND ss.pending_evaluation_generation IS NOT NULL
              AND ss.pending_evaluation_generation = ss.event_generation
              AND ss.pending_evaluation_generation > ss.evaluated_generation
              AND (
                    a.kb_id IS NULL
                    OR (
                        (
                            a.automation_state != 'running'
                            OR a.lease_expires_at IS NULL
                            OR a.lease_expires_at <= ?
                        )
                        AND (
                            ss.pending_evaluation_generation
                                > IFNULL(a.last_attempted_generation, 0)
                            OR (
                                a.automation_state = 'running'
                                AND a.running_generation = ss.pending_evaluation_generation
                                AND (
                                    a.lease_expires_at IS NULL
                                    OR a.lease_expires_at <= ?
                                )
                            )
                            OR (
                                a.automation_state = 'awaiting_publish'
                                AND a.last_attempted_generation
                                    = ss.pending_evaluation_generation
                                AND s.automatic_publish_enabled = 1
                                AND p.status = 'validated'
                                AND json_extract(
                                    CASE WHEN json_valid(p.smoke_result_json)
                                        THEN p.smoke_result_json ELSE '{}'
                                    END,
                                    '$.contract_version'
                                ) = 'ready-data-staging-smoke.v1'
                                AND (
                                    (
                                        json_extract(
                                            CASE WHEN json_valid(p.smoke_result_json)
                                                THEN p.smoke_result_json ELSE '{}'
                                            END,
                                            '$.status'
                                        ) = 'passed'
                                        AND CAST(json_extract(
                                            CASE WHEN json_valid(p.smoke_result_json)
                                                THEN p.smoke_result_json ELSE '{}'
                                            END,
                                            '$.catalog_doc_count'
                                        ) AS INTEGER) > 0
                                        AND (
                                            IFNULL(TRIM(CAST(json_extract(
                                                CASE WHEN json_valid(p.smoke_result_json)
                                                    THEN p.smoke_result_json ELSE '{}'
                                                END,
                                                '$.matched_doc_id'
                                            ) AS TEXT)), '') <> ''
                                            OR IFNULL(TRIM(CAST(json_extract(
                                                CASE WHEN json_valid(p.smoke_result_json)
                                                    THEN p.smoke_result_json ELSE '{}'
                                                END,
                                                '$.matched_file_url'
                                            ) AS TEXT)), '') <> ''
                                        )
                                    )
                                    OR (
                                        json_extract(
                                            CASE WHEN json_valid(p.smoke_result_json)
                                                THEN p.smoke_result_json ELSE '{}'
                                            END,
                                            '$.status'
                                        ) = 'skipped_empty'
                                        AND COALESCE(CAST(json_extract(
                                            CASE WHEN json_valid(p.smoke_result_json)
                                                THEN p.smoke_result_json ELSE '{}'
                                            END,
                                            '$.catalog_doc_count'
                                        ) AS INTEGER), -1) = 0
                                        AND IFNULL(a.last_error, '') <>
                                            'empty ready_data requires manual publish confirmation'
                                    )
                                )
                                AND IFNULL(p.attempt_disposition, '') = ''
                                AND IFNULL(g.state, '') NOT IN (
                                    'claimed', 'delete_failed', 'deleted'
                                )
                            )
                        )
                    )
              )
            ORDER BY ss.updated_at, s.kb_id, s.profile
            LIMIT 1
            """,
            (now_iso, now_iso),
        ).fetchone()

    def claim_next_agentic_ready_automation(
        self,
        *,
        now: datetime | None = None,
        lease_seconds: int = 300,
        claim_token: str | None = None,
    ) -> dict[str, Any] | None:
        """Claim at most one latest pending generation under a durable global lease."""
        if int(lease_seconds) <= 0:
            raise ValueError("ready-data automation lease_seconds must be positive")
        now_value = now or datetime.now(timezone.utc)
        if now_value.tzinfo is None:
            now_value = now_value.replace(tzinfo=timezone.utc)
        now_value = now_value.astimezone(timezone.utc)
        now_iso = now_value.isoformat()
        lease_expires_at = (now_value + timedelta(seconds=int(lease_seconds))).isoformat()
        if self._select_agentic_ready_automation_candidate(now_iso=now_iso) is None:
            return None
        token = str(claim_token or uuid.uuid4().hex)
        with self.transaction(immediate=True):
            lock_result = self._conn.execute(
                """
                INSERT INTO agentic_ready_automation_lock (
                    lock_name, claim_token, claimed_at, lease_expires_at, updated_at
                )
                VALUES ('global', ?, ?, ?, ?)
                ON CONFLICT(lock_name) DO UPDATE SET
                    claim_token = excluded.claim_token,
                    claimed_at = excluded.claimed_at,
                    lease_expires_at = excluded.lease_expires_at,
                    updated_at = excluded.updated_at
                WHERE agentic_ready_automation_lock.claim_token IS NULL
                   OR agentic_ready_automation_lock.lease_expires_at IS NULL
                   OR agentic_ready_automation_lock.lease_expires_at <= ?
                """,
                (token, now_iso, lease_expires_at, now_iso, now_iso),
            )
            if lock_result.rowcount != 1:
                return None
            candidate = self._select_agentic_ready_automation_candidate(now_iso=now_iso)
            if candidate is None:
                self._conn.execute(
                    """
                    UPDATE agentic_ready_automation_lock
                    SET claim_token = NULL, claimed_at = NULL,
                        lease_expires_at = NULL, updated_at = ?
                    WHERE lock_name = 'global' AND claim_token = ?
                    """,
                    (now_iso, token),
                )
                return None
            kb_id = str(candidate[0])
            profile = str(candidate[1])
            generation = int(candidate[2])
            prior_state = str(candidate[4] or "")
            prior_generation = int(candidate[6] or 0)
            prior_publication_id = str(candidate[8]) if candidate[8] else None
            if (
                prior_state == "awaiting_publish"
                and prior_publication_id
                and prior_generation < generation
                and str(candidate[9] or "") == "validated"
                and not str(candidate[10] or "")
            ):
                self.mark_agentic_ready_publication_superseded_generation(
                    prior_publication_id
                )
            reusable_publication = bool(
                prior_publication_id
                and prior_generation == generation
                and bool(candidate[3])
                and str(candidate[9] or "") == "validated"
                and not str(candidate[10] or "")
                and str(candidate[11] or "")
                not in {"claimed", "delete_failed", "deleted"}
                and prior_state in {"awaiting_publish", "running"}
            )
            mode = "publish" if reusable_publication else "build"
            publication_id = prior_publication_id if reusable_publication else None
            claim_result = self._conn.execute(
                """
                INSERT INTO agentic_ready_automation (
                    kb_id, profile, automation_state, running_generation,
                    last_attempted_generation, claim_token, claimed_at,
                    lease_expires_at, last_attempt_publication_id,
                    last_success_at, last_error, updated_at
                )
                VALUES (?, ?, 'running', ?, ?, ?, ?, ?, ?, NULL, '', ?)
                ON CONFLICT(kb_id, profile) DO UPDATE SET
                    automation_state = 'running',
                    running_generation = excluded.running_generation,
                    last_attempted_generation = excluded.last_attempted_generation,
                    claim_token = excluded.claim_token,
                    claimed_at = excluded.claimed_at,
                    lease_expires_at = excluded.lease_expires_at,
                    last_attempt_publication_id = excluded.last_attempt_publication_id,
                    last_error = '',
                    updated_at = excluded.updated_at
                WHERE agentic_ready_automation.automation_state != 'running'
                   OR agentic_ready_automation.lease_expires_at IS NULL
                   OR agentic_ready_automation.lease_expires_at <= ?
                """,
                (
                    kb_id,
                    profile,
                    generation,
                    generation,
                    token,
                    now_iso,
                    lease_expires_at,
                    publication_id,
                    now_iso,
                    now_iso,
                ),
            )
            if claim_result.rowcount != 1:
                self._conn.execute(
                    """
                    UPDATE agentic_ready_automation_lock
                    SET claim_token = NULL, claimed_at = NULL,
                        lease_expires_at = NULL, updated_at = ?
                    WHERE lock_name = 'global' AND claim_token = ?
                    """,
                    (now_iso, token),
                )
                return None
        return {
            "kb_id": kb_id,
            "profile": profile,
            "generation": generation,
            "claim_token": token,
            "claimed_at": now_iso,
            "lease_expires_at": lease_expires_at,
            "mode": mode,
            "publication_id": publication_id,
            "expected_active_publication_id": str(candidate[12]) if candidate[12] else None,
            "expected_automatic_build_enabled": True,
            "expected_automatic_publish_enabled": bool(candidate[3]),
        }

    def check_agentic_ready_automation_claim(
        self,
        *,
        kb_id: str,
        profile: str,
        generation: int,
        claim_token: str,
        require_publish: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        normalized_profile = str(profile or "general").strip().lower() or "general"
        now_iso = self._agentic_ready_automation_timestamp(now)
        row = self._conn.execute(
            """
            SELECT a.automation_state, a.running_generation, a.claim_token,
                   a.lease_expires_at, l.claim_token, l.lease_expires_at,
                   s.automatic_build_enabled, s.automatic_publish_enabled,
                   ss.event_generation, ss.pending_evaluation_generation
            FROM agentic_ready_automation AS a
            JOIN agentic_ready_automation_lock AS l ON l.lock_name = 'global'
            JOIN agentic_ready_slots AS s
              ON s.kb_id = a.kb_id AND s.profile = a.profile
            JOIN agentic_ready_source_state AS ss
              ON ss.kb_id = a.kb_id AND ss.profile = a.profile
            WHERE a.kb_id = ? AND a.profile = ?
            LIMIT 1
            """,
            (kb_id, normalized_profile),
        ).fetchone()
        if not row:
            return {"claim_owned": False, "reason": "claim_missing"}
        owns_claim = bool(
            str(row[0]) == "running"
            and int(row[1] or -1) == int(generation)
            and str(row[2] or "") == claim_token
            and str(row[4] or "") == claim_token
            and str(row[3] or "") > now_iso
            and str(row[5] or "") > now_iso
        )
        if not owns_claim:
            reason = "claim_lost"
        elif int(row[8] or 0) != int(generation) or row[9] is None or int(row[9]) != int(
            generation
        ):
            reason = "generation_superseded"
        elif not bool(row[6]):
            reason = "automatic_build_disabled"
        elif require_publish and not bool(row[7]):
            reason = "automatic_publish_disabled"
        else:
            reason = "ok"
        return {
            "claim_owned": owns_claim,
            "reason": reason,
            "automatic_build_enabled": bool(row[6]),
            "automatic_publish_enabled": bool(row[7]),
            "event_generation": int(row[8] or 0),
            "pending_evaluation_generation": int(row[9]) if row[9] is not None else None,
        }

    def fence_agentic_ready_automation_prebuild(
        self,
        *,
        kb_id: str,
        profile: str,
        generation: int,
        claim_token: str,
        expected_active_publication_id: str | None,
        expected_automatic_build_enabled: bool,
        expected_automatic_publish_enabled: bool,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Fence a claimed generation immediately before artifact-producing work."""
        normalized_profile = str(profile or "general").strip().lower() or "general"
        with self.transaction(immediate=True):
            fence = self.check_agentic_ready_automation_claim(
                kb_id=kb_id,
                profile=normalized_profile,
                generation=int(generation),
                claim_token=claim_token,
                now=now,
            )
            reason = str(fence.get("reason") or "claim_lost")
            if reason != "ok":
                if fence.get("claim_owned") and reason in {
                    "generation_superseded",
                    "automatic_build_disabled",
                }:
                    finished = self.finish_agentic_ready_automation_claim(
                        kb_id=kb_id,
                        profile=normalized_profile,
                        generation=int(generation),
                        claim_token=claim_token,
                        automation_state="pending",
                        now=now,
                    )
                    return {
                        **fence,
                        "action": "superseded"
                        if reason == "generation_superseded"
                        else "pending",
                        "reason": reason,
                        "claim_owned": bool(finished),
                    }
                return {**fence, "action": "claim_lost", "reason": reason}

            flags_match = (
                bool(fence["automatic_build_enabled"])
                == bool(expected_automatic_build_enabled)
                and bool(fence["automatic_publish_enabled"])
                == bool(expected_automatic_publish_enabled)
            )
            if not flags_match:
                finished = self.finish_agentic_ready_automation_claim(
                    kb_id=kb_id,
                    profile=normalized_profile,
                    generation=int(generation),
                    claim_token=claim_token,
                    automation_state="pending",
                    now=now,
                )
                return {
                    **fence,
                    "action": "pending" if finished else "claim_lost",
                    "reason": "automation_flags_changed",
                }

            slot = self._conn.execute(
                """
                SELECT active_publication_id
                FROM agentic_ready_slots
                WHERE kb_id = ? AND profile = ?
                LIMIT 1
                """,
                (kb_id, normalized_profile),
            ).fetchone()
            actual_active_id = str(slot[0]) if slot and slot[0] else None
            if actual_active_id != expected_active_publication_id:
                error = "ready_data automation lost expected-active prebuild CAS"
                finished = self.finish_agentic_ready_automation_claim(
                    kb_id=kb_id,
                    profile=normalized_profile,
                    generation=int(generation),
                    claim_token=claim_token,
                    automation_state="failed",
                    error_message=error,
                    now=now,
                )
                return {
                    **fence,
                    "action": "failed" if finished else "claim_lost",
                    "reason": "active_publication_changed",
                    "error": error,
                }
            return {**fence, "action": "build", "reason": "ok"}

    def settle_agentic_ready_automation_up_to_date(
        self,
        *,
        kb_id: str,
        profile: str,
        generation: int,
        claim_token: str,
        expected_active_publication_id: str,
        expected_automatic_build_enabled: bool,
        expected_automatic_publish_enabled: bool,
        source_version_kind: str,
        source_version_id: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Settle a healthy matching active publication without creating a candidate."""
        normalized_profile = str(profile or "general").strip().lower() or "general"
        normalized_kind = str(source_version_kind or "").strip().lower()
        normalized_source_id = str(source_version_id or "").strip()
        if not normalized_kind or not normalized_source_id:
            raise ValueError("source_version_kind and source_version_id are required")
        with self.transaction(immediate=True):
            prebuild = self.fence_agentic_ready_automation_prebuild(
                kb_id=kb_id,
                profile=normalized_profile,
                generation=int(generation),
                claim_token=claim_token,
                expected_active_publication_id=expected_active_publication_id,
                expected_automatic_build_enabled=expected_automatic_build_enabled,
                expected_automatic_publish_enabled=expected_automatic_publish_enabled,
                now=now,
            )
            if prebuild["action"] != "build":
                return prebuild
            active = self._conn.execute(
                """
                SELECT p.source_version_kind, p.source_version_id, p.status
                FROM agentic_ready_slots AS s
                JOIN agentic_ready_publications AS p
                  ON p.publication_id = s.active_publication_id
                WHERE s.kb_id = ? AND s.profile = ?
                  AND s.active_publication_id = ?
                LIMIT 1
                """,
                (kb_id, normalized_profile, expected_active_publication_id),
            ).fetchone()
            active_matches = bool(
                active
                and str(active[2] or "") == "active"
                and str(active[0] or "").strip().lower() == normalized_kind
                and str(active[1] or "").strip() == normalized_source_id
            )
            if not active_matches:
                error = "ready_data active source identity changed before up-to-date settlement"
                finished = self.finish_agentic_ready_automation_claim(
                    kb_id=kb_id,
                    profile=normalized_profile,
                    generation=int(generation),
                    claim_token=claim_token,
                    automation_state="failed",
                    publication_id=expected_active_publication_id,
                    error_message=error,
                    now=now,
                )
                return {
                    "action": "failed" if finished else "claim_lost",
                    "reason": "active_source_identity_changed",
                    "error": error,
                }
            source_state = self.record_agentic_ready_source_evaluation(
                kb_id=kb_id,
                profile=normalized_profile,
                evaluated_generation=int(generation),
                source_version_kind=normalized_kind,
                source_version_id=normalized_source_id,
            )
            finished = self.finish_agentic_ready_automation_claim(
                kb_id=kb_id,
                profile=normalized_profile,
                generation=int(generation),
                claim_token=claim_token,
                automation_state="succeeded",
                publication_id=expected_active_publication_id,
                success=True,
                now=now,
            )
            if not finished:
                raise RuntimeError("ready-data up-to-date settlement lost its completion claim")
        return {
            "action": "up_to_date",
            "reason": "source_identity_matches_active",
            "source_state": source_state,
        }

    def heartbeat_agentic_ready_automation_claim(
        self,
        *,
        kb_id: str,
        profile: str,
        generation: int,
        claim_token: str,
        now: datetime | None = None,
        lease_seconds: int = 300,
    ) -> bool:
        if int(lease_seconds) <= 0:
            raise ValueError("ready-data automation lease_seconds must be positive")
        now_value = now or datetime.now(timezone.utc)
        if now_value.tzinfo is None:
            now_value = now_value.replace(tzinfo=timezone.utc)
        now_value = now_value.astimezone(timezone.utc)
        now_iso = now_value.isoformat()
        lease_expires_at = (now_value + timedelta(seconds=int(lease_seconds))).isoformat()
        normalized_profile = str(profile or "general").strip().lower() or "general"
        try:
            with self.transaction(immediate=True):
                pair_result = self._conn.execute(
                    """
                    UPDATE agentic_ready_automation
                    SET lease_expires_at = ?, updated_at = ?
                    WHERE kb_id = ? AND profile = ?
                      AND automation_state = 'running'
                      AND running_generation = ? AND claim_token = ?
                      AND lease_expires_at > ?
                    """,
                    (
                        lease_expires_at,
                        now_iso,
                        kb_id,
                        normalized_profile,
                        int(generation),
                        claim_token,
                        now_iso,
                    ),
                )
                lock_result = self._conn.execute(
                    """
                    UPDATE agentic_ready_automation_lock
                    SET lease_expires_at = ?, updated_at = ?
                    WHERE lock_name = 'global' AND claim_token = ?
                      AND lease_expires_at > ?
                    """,
                    (lease_expires_at, now_iso, claim_token, now_iso),
                )
                if pair_result.rowcount != 1 or lock_result.rowcount != 1:
                    raise RuntimeError("ready-data automation heartbeat lost its claim")
        except RuntimeError:
            return False
        return True

    def finish_agentic_ready_automation_claim(
        self,
        *,
        kb_id: str,
        profile: str,
        generation: int,
        claim_token: str,
        automation_state: str,
        publication_id: str | None = None,
        error_message: str = "",
        success: bool = False,
        now: datetime | None = None,
    ) -> bool:
        allowed_states = {"awaiting_publish", "succeeded", "failed", "pending"}
        if automation_state not in allowed_states:
            raise ValueError("invalid ready-data automation completion state")
        normalized_profile = str(profile or "general").strip().lower() or "general"
        now_iso = self._agentic_ready_automation_timestamp(now)
        with self.transaction(immediate=True):
            lock_row = self._conn.execute(
                """
                SELECT claim_token FROM agentic_ready_automation_lock
                WHERE lock_name = 'global'
                """
            ).fetchone()
            if not lock_row or str(lock_row[0] or "") != claim_token:
                return False
            result = self._conn.execute(
                """
                UPDATE agentic_ready_automation
                SET automation_state = ?, running_generation = NULL,
                    claim_token = NULL, claimed_at = NULL, lease_expires_at = NULL,
                    last_attempt_publication_id = ?,
                    last_success_at = CASE WHEN ? THEN ? ELSE last_success_at END,
                    last_error = ?, updated_at = ?
                WHERE kb_id = ? AND profile = ?
                  AND automation_state = 'running'
                  AND running_generation = ? AND claim_token = ?
                """,
                (
                    automation_state,
                    publication_id,
                    int(bool(success)),
                    now_iso,
                    str(error_message or ""),
                    now_iso,
                    kb_id,
                    normalized_profile,
                    int(generation),
                    claim_token,
                ),
            )
            if result.rowcount != 1:
                return False
            lock_result = self._conn.execute(
                """
                UPDATE agentic_ready_automation_lock
                SET claim_token = NULL, claimed_at = NULL,
                    lease_expires_at = NULL, updated_at = ?
                WHERE lock_name = 'global' AND claim_token = ?
                """,
                (now_iso, claim_token),
            )
            if lock_result.rowcount != 1:
                raise RuntimeError("ready-data automation completion lost its global claim")
        return True

    def finalize_agentic_ready_automation_build(
        self,
        *,
        kb_id: str,
        profile: str,
        generation: int,
        claim_token: str,
        publication_id: str,
        require_manual_publish_confirmation: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Atomically fence a validated build before waiting or moving to publish."""
        normalized_profile = str(profile or "general").strip().lower() or "general"
        with self.transaction(immediate=True):
            fence = self.check_agentic_ready_automation_claim(
                kb_id=kb_id,
                profile=normalized_profile,
                generation=int(generation),
                claim_token=claim_token,
                now=now,
            )
            reason = str(fence.get("reason") or "claim_lost")
            if reason == "generation_superseded":
                self.mark_agentic_ready_publication_superseded_generation(publication_id)
                finished = self.finish_agentic_ready_automation_claim(
                    kb_id=kb_id,
                    profile=normalized_profile,
                    generation=int(generation),
                    claim_token=claim_token,
                    automation_state="pending",
                    publication_id=publication_id,
                    now=now,
                )
                if not finished:
                    raise RuntimeError(
                        "ready-data superseded build lost its automation claim"
                    )
                return {"action": "superseded", "reason": reason, **fence}
            if not fence.get("claim_owned"):
                return {"action": "claim_lost", "reason": reason, **fence}
            if require_manual_publish_confirmation:
                error = "empty ready_data requires manual publish confirmation"
                finished = self.finish_agentic_ready_automation_claim(
                    kb_id=kb_id,
                    profile=normalized_profile,
                    generation=int(generation),
                    claim_token=claim_token,
                    automation_state="awaiting_publish",
                    publication_id=publication_id,
                    error_message=error,
                    success=True,
                    now=now,
                )
                if not finished:
                    raise RuntimeError(
                        "empty ready-data build lost its automation claim"
                    )
                return {
                    "action": "awaiting_manual_confirmation",
                    "reason": "empty_kb_requires_manual_publish_confirmation",
                    **fence,
                }
            if reason == "automatic_build_disabled" or not fence.get(
                "automatic_publish_enabled"
            ):
                finished = self.finish_agentic_ready_automation_claim(
                    kb_id=kb_id,
                    profile=normalized_profile,
                    generation=int(generation),
                    claim_token=claim_token,
                    automation_state="awaiting_publish",
                    publication_id=publication_id,
                    success=True,
                    now=now,
                )
                if not finished:
                    raise RuntimeError(
                        "ready-data validated build lost its automation claim"
                    )
                return {"action": "awaiting_publish", "reason": reason, **fence}
            return {"action": "publish", "reason": "ok", **fence}

    def mark_agentic_ready_source_event(
        self,
        *,
        kb_id: str,
        profile: str = "general",
        reason: str,
    ) -> dict[str, Any]:
        """Atomically coalesce an event, nesting via savepoint in a caller transaction."""
        normalized_profile = str(profile or "general").strip().lower() or "general"
        normalized_reason = str(reason or "").strip().lower()
        severity = self._AGENTIC_READY_SOURCE_EVENT_SEVERITY.get(normalized_reason)
        if severity is None:
            raise ValueError(f"unsupported ready-data source event reason: {normalized_reason}")
        now = self._utcnow_iso()
        with self.transaction(immediate=True):
            kb_exists = self._conn.execute(
                "SELECT 1 FROM rag_knowledge_bases WHERE kb_id = ? LIMIT 1",
                (kb_id,),
            ).fetchone()
            if not kb_exists:
                raise ValueError("knowledge base not found")
            self._conn.execute(
                """
                INSERT INTO agentic_ready_source_state (
                    kb_id, profile, event_generation,
                    pending_evaluation_generation, evaluated_generation,
                    pending_severity, pending_reasons_json,
                    evaluated_severity, evaluated_reasons_json,
                    evaluated_source_version_kind, evaluated_source_version_id,
                    evaluated_at, created_at, updated_at
                )
                VALUES (?, ?, 0, NULL, 0, 'none', '[]', 'none', '[]', '', '', NULL, ?, ?)
                ON CONFLICT(kb_id, profile) DO NOTHING
                """,
                (kb_id, normalized_profile, now, now),
            )
            row = self._conn.execute(
                """
                SELECT event_generation, pending_severity, pending_reasons_json
                FROM agentic_ready_source_state
                WHERE kb_id = ? AND profile = ?
                """,
                (kb_id, normalized_profile),
            ).fetchone()
            if not row:
                raise RuntimeError("ready-data source state could not be initialized")
            generation = int(row[0] or 0) + 1
            reasons = self._agentic_ready_json_list(row[2])
            if normalized_reason not in reasons:
                reasons.append(normalized_reason)
            pending_severity = self._agentic_ready_severity_max(
                str(row[1] or "none"),
                severity,
            )
            result = self._conn.execute(
                """
                UPDATE agentic_ready_source_state
                SET event_generation = ?, pending_evaluation_generation = ?,
                    pending_severity = ?, pending_reasons_json = ?, updated_at = ?
                WHERE kb_id = ? AND profile = ?
                """,
                (
                    generation,
                    generation,
                    pending_severity,
                    json.dumps(reasons, ensure_ascii=False),
                    now,
                    kb_id,
                    normalized_profile,
                ),
            )
            if result.rowcount != 1:
                raise RuntimeError("ready-data source event generation update failed")
        return self.get_agentic_ready_source_state(
            kb_id=kb_id,
            profile=normalized_profile,
        )

    def mark_agentic_ready_source_event_for_kb(
        self,
        *,
        kb_id: str,
        reason: str,
    ) -> list[dict[str, Any]]:
        """Mark one event for every ready-data profile known to a knowledge base."""
        with self.transaction(immediate=True):
            rows = self._conn.execute(
                """
                SELECT profile FROM agentic_ready_source_state WHERE kb_id = ?
                UNION
                SELECT profile FROM agentic_ready_slots WHERE kb_id = ?
                UNION
                SELECT profile FROM agentic_ready_manifests WHERE kb_id = ?
                UNION
                SELECT profile FROM agentic_ready_publications WHERE kb_id = ?
                UNION
                SELECT manifest_profile FROM rag_knowledge_bases WHERE kb_id = ?
                """,
                (kb_id, kb_id, kb_id, kb_id, kb_id),
            ).fetchall()
            profiles = {
                normalized
                for row in rows
                if (normalized := str(row[0] or "").strip().lower())
            }
            if not profiles:
                profiles = {"general"}
            return [
                self.mark_agentic_ready_source_event(
                    kb_id=kb_id,
                    profile=profile,
                    reason=reason,
                )
                for profile in sorted(profiles)
            ]

    def record_agentic_ready_source_evaluation(
        self,
        *,
        kb_id: str,
        profile: str = "general",
        evaluated_generation: int,
        source_version_kind: str,
        source_version_id: str,
    ) -> dict[str, Any]:
        """Record the authoritative builder source version for the latest generation."""
        normalized_profile = str(profile or "general").strip().lower() or "general"
        normalized_kind = str(source_version_kind or "").strip().lower()
        normalized_source_id = str(source_version_id or "").strip()
        if not normalized_kind or not normalized_source_id:
            raise ValueError("source_version_kind and source_version_id are required")
        generation = int(evaluated_generation)
        now = self._utcnow_iso()
        with self.transaction(immediate=True):
            row = self._conn.execute(
                """
                SELECT event_generation, pending_evaluation_generation,
                       pending_severity, pending_reasons_json,
                       evaluated_severity, evaluated_reasons_json,
                       evaluated_source_version_kind, evaluated_source_version_id
                FROM agentic_ready_source_state
                WHERE kb_id = ? AND profile = ?
                """,
                (kb_id, normalized_profile),
            ).fetchone()
            if not row:
                raise ValueError("ready-data source evaluation has no pending source event")
            current_generation = int(row[0] or 0)
            pending_generation = int(row[1]) if row[1] is not None else None
            if generation != current_generation or pending_generation != current_generation:
                raise ValueError("evaluation must target the latest event generation")

            publication_state = self.get_agentic_ready_publication_state(
                kb_id=kb_id,
                profile=normalized_profile,
            )
            active = publication_state.get("active_publication")
            manifest = self.get_agentic_ready_manifest(
                kb_id=kb_id,
                profile=normalized_profile,
            )
            serving_record = active or manifest
            active_kind = str((serving_record or {}).get("source_version_kind") or "").strip().lower()
            active_source_id = str((serving_record or {}).get("source_version_id") or "").strip()
            has_serving_record = bool(serving_record and (serving_record or {}).get("status") in {"ready", "active"})
            source_identity_comparable = bool(active_kind and active_source_id)
            source_mismatch = bool(
                has_serving_record
                and source_identity_comparable
                and (
                    active_kind != normalized_kind
                    or active_source_id != normalized_source_id
                )
            )
            pending_reasons = self._agentic_ready_json_list(row[3])
            previous_severity = str(row[4] or "none")
            previous_reasons = self._agentic_ready_json_list(row[5])
            previous_kind = str(row[6] or "").strip().lower()
            previous_source_id = str(row[7] or "").strip()
            previous_authority_unresolved = bool(
                has_serving_record
                and previous_kind
                and previous_source_id
                and (
                    active_kind != previous_kind
                    or active_source_id != previous_source_id
                )
            )
            inherited_severity = (
                previous_severity if previous_authority_unresolved else "none"
            )
            inherited_reasons = (
                previous_reasons if previous_authority_unresolved else []
            )
            source_matches = bool(
                has_serving_record
                and source_identity_comparable
                and active_kind == normalized_kind
                and active_source_id == normalized_source_id
            )
            if source_matches:
                evaluated_severity = "none"
                evaluated_reasons: list[str] = []
            elif source_mismatch:
                evaluated_severity = self._agentic_ready_severity_max(
                    inherited_severity,
                    str(row[2] or "none"),
                )
                if evaluated_severity == "none":
                    evaluated_severity = "soft_stale"
                evaluated_reasons = list(
                    dict.fromkeys([*inherited_reasons, *pending_reasons])
                )
                if not evaluated_reasons:
                    evaluated_reasons = ["source_version_changed"]
            else:
                evaluated_severity = self._agentic_ready_severity_max(
                    inherited_severity
                    if inherited_severity == "hard_stale"
                    else "none",
                    str(row[2] or "none") if str(row[2] or "none") == "hard_stale" else "none",
                )
                evaluated_reasons = (
                    list(dict.fromkeys([*inherited_reasons, *pending_reasons]))
                    if evaluated_severity == "hard_stale"
                    else []
                )
            result = self._conn.execute(
                """
                UPDATE agentic_ready_source_state
                SET pending_evaluation_generation = NULL,
                    evaluated_generation = ?, pending_severity = 'none',
                    pending_reasons_json = '[]', evaluated_severity = ?,
                    evaluated_reasons_json = ?,
                    evaluated_source_version_kind = ?,
                    evaluated_source_version_id = ?, evaluated_at = ?, updated_at = ?
                WHERE kb_id = ? AND profile = ?
                  AND event_generation = ?
                  AND pending_evaluation_generation = ?
                """,
                (
                    generation,
                    evaluated_severity,
                    json.dumps(evaluated_reasons, ensure_ascii=False),
                    normalized_kind,
                    normalized_source_id,
                    now,
                    now,
                    kb_id,
                    normalized_profile,
                    generation,
                    generation,
                ),
            )
            if result.rowcount != 1:
                raise RuntimeError("ready-data source evaluation lost its generation guard")
        return self.get_agentic_ready_source_state(
            kb_id=kb_id,
            profile=normalized_profile,
        )

    def get_agentic_ready_source_state(
        self,
        *,
        kb_id: str,
        profile: str = "general",
    ) -> dict[str, Any]:
        """Derive serving safety from durable events and authoritative source identity."""
        normalized_profile = str(profile or "general").strip().lower() or "general"
        row = self._conn.execute(
            """
            SELECT event_generation, pending_evaluation_generation,
                   evaluated_generation, pending_severity, pending_reasons_json,
                   evaluated_severity, evaluated_reasons_json,
                   evaluated_source_version_kind, evaluated_source_version_id,
                   evaluated_at, created_at, updated_at
            FROM agentic_ready_source_state
            WHERE kb_id = ? AND profile = ?
            LIMIT 1
            """,
            (kb_id, normalized_profile),
        ).fetchone()
        publication_state = self.get_agentic_ready_publication_state(
            kb_id=kb_id,
            profile=normalized_profile,
        )
        active = publication_state.get("active_publication")
        manifest = self.get_agentic_ready_manifest(
            kb_id=kb_id,
            profile=normalized_profile,
        )
        serving_record = active or manifest
        active_kind = str((serving_record or {}).get("source_version_kind") or "").strip().lower()
        active_source_id = str((serving_record or {}).get("source_version_id") or "").strip()
        source_identity_comparable = bool(active_kind and active_source_id)
        if not row:
            return {
                "kb_id": kb_id,
                "profile": normalized_profile,
                "has_source_state": False,
                "state": "legacy_fallback",
                "event_generation": 0,
                "pending_evaluation_generation": None,
                "evaluated_generation": 0,
                "pending_evaluation": False,
                "pending_severity": "none",
                "pending_reasons": [],
                "evaluated_source_version_kind": "",
                "evaluated_source_version_id": "",
                "active_source_version_kind": active_kind,
                "active_source_version_id": active_source_id,
                "source_identity_comparable": source_identity_comparable,
                "legacy_heuristic_required": not source_identity_comparable,
                "legacy_hard_gate": False,
                "stale_confirmed": False,
                "stale_severity": "none",
                "stale_reasons": [],
                "serving_stale": False,
                "serving_allowed": True,
                "automatic_build_enabled": publication_state["automatic_build_enabled"],
                "automatic_publish_enabled": publication_state["automatic_publish_enabled"],
                "evaluated_at": None,
                "updated_at": None,
            }

        event_generation = int(row[0] or 0)
        pending_generation = int(row[1]) if row[1] is not None else None
        evaluated_generation = int(row[2] or 0)
        pending_evaluation = bool(
            pending_generation is not None and pending_generation > evaluated_generation
        )
        pending_severity = str(row[3] or "none") if pending_evaluation else "none"
        pending_reasons = self._agentic_ready_json_list(row[4]) if pending_evaluation else []
        evaluated_kind = str(row[7] or "").strip().lower()
        evaluated_source_id = str(row[8] or "").strip()
        has_serving_record = bool(serving_record and (serving_record or {}).get("status") in {"ready", "active"})
        confirmed_pending_content_change = bool(
            has_serving_record
            and pending_severity == "soft_stale"
            and "chunk_content_updated" in pending_reasons
        )
        source_mismatch = bool(
            has_serving_record
            and source_identity_comparable
            and evaluated_kind
            and evaluated_source_id
            and (
                active_kind != evaluated_kind
                or active_source_id != evaluated_source_id
            )
        )
        evaluated_severity = str(row[5] or "none") if source_mismatch else "none"
        if source_mismatch and evaluated_severity == "none":
            evaluated_severity = "soft_stale"
        legacy_hard_gate = bool(
            has_serving_record
            and not source_identity_comparable
            and str(row[5] or "none") == "hard_stale"
        )
        if legacy_hard_gate:
            evaluated_severity = "hard_stale"
        effective_severity = self._agentic_ready_severity_max(
            pending_severity
            if pending_severity == "hard_stale" or confirmed_pending_content_change
            else "none",
            evaluated_severity,
        )
        stale_confirmed = bool(
            (source_mismatch and evaluated_severity != "none")
            or confirmed_pending_content_change
        )
        serving_stale = effective_severity in {"soft_stale", "hard_stale"}
        state = (
            "stale"
            if stale_confirmed
            else (
                "pending_evaluation"
                if pending_evaluation
                else ("legacy_hard_gate" if legacy_hard_gate else "fresh")
            )
        )
        reasons = (
            self._agentic_ready_json_list(row[6])
            if source_mismatch or legacy_hard_gate
            else []
        )
        if source_mismatch and not reasons:
            reasons = ["source_version_changed"]
        if pending_evaluation:
            reasons = list(dict.fromkeys([*reasons, *pending_reasons]))
        return {
            "kb_id": kb_id,
            "profile": normalized_profile,
            "has_source_state": True,
            "state": state,
            "event_generation": event_generation,
            "pending_evaluation_generation": pending_generation,
            "evaluated_generation": evaluated_generation,
            "pending_evaluation": pending_evaluation,
            "pending_severity": pending_severity,
            "pending_reasons": pending_reasons,
            "evaluated_source_version_kind": evaluated_kind,
            "evaluated_source_version_id": evaluated_source_id,
            "active_source_version_kind": active_kind,
            "active_source_version_id": active_source_id,
            "source_identity_comparable": source_identity_comparable,
            "legacy_heuristic_required": not source_identity_comparable,
            "legacy_hard_gate": legacy_hard_gate,
            "stale_confirmed": stale_confirmed,
            "stale_severity": effective_severity,
            "stale_reasons": reasons,
            "serving_stale": serving_stale,
            "serving_allowed": effective_severity != "hard_stale",
            "automatic_build_enabled": publication_state["automatic_build_enabled"],
            "automatic_publish_enabled": publication_state["automatic_publish_enabled"],
            "evaluated_at": row[9],
            "updated_at": row[11],
        }

    def get_agentic_ready_publication_state(
        self,
        *,
        kb_id: str,
        profile: str = "general",
    ) -> dict[str, Any]:
        normalized_profile = str(profile or "general").strip().lower() or "general"
        row = self._conn.execute(
            """
            SELECT active_publication_id, previous_publication_id,
                   automatic_build_enabled, automatic_publish_enabled,
                   publication_revision, updated_at
            FROM agentic_ready_slots
            WHERE kb_id = ? AND profile = ?
            LIMIT 1
            """,
            (kb_id, normalized_profile),
        ).fetchone()
        active_id = str(row[0]) if row and row[0] else None
        previous_id = str(row[1]) if row and row[1] else None
        return {
            "kb_id": kb_id,
            "profile": normalized_profile,
            "active_publication_id": active_id,
            "previous_publication_id": previous_id,
            "automatic_build_enabled": bool(row[2]) if row else False,
            "automatic_publish_enabled": bool(row[3]) if row else False,
            "publication_revision": int(row[4] or 0) if row else 0,
            "updated_at": row[5] if row else None,
            "active_publication": self.get_agentic_ready_publication(active_id) if active_id else None,
            "previous_publication": self.get_agentic_ready_publication(previous_id) if previous_id else None,
        }

    def _publish_agentic_ready_manifest_row(self, publication: dict[str, Any]) -> None:
        self.upsert_agentic_ready_manifest(
            kb_id=str(publication["kb_id"]),
            profile=str(publication["profile"]),
            profile_version=str(publication["profile_version"]),
            status="ready",
            output_dir=str(publication["output_dir"]),
            artifact_files=list(publication["artifact_files"]),
            doc_count=int(publication["doc_count"]),
            section_count=int(publication["section_count"]),
            built_at=publication.get("built_at"),
            source_db=str(publication["source_db"]),
            schema_versions=dict(publication["schema_versions"]),
            error_message="",
            publication_id=str(publication["publication_id"]),
            index_version_id=publication["index_version_id"],
            source_version_kind=str(publication["source_version_kind"]),
            source_version_id=str(publication["source_version_id"]),
            artifact_digest=str(publication["artifact_digest"]),
        )

    def publish_agentic_ready_publication(
        self,
        publication_id: str,
        *,
        expected_active_publication_id: str | None,
        preserve_expected_active_as_previous: bool = True,
        invalidated_expected_active_error: str = "",
    ) -> dict[str, Any]:
        """CAS-promote a validated attempt and optionally retain its predecessor."""
        now = self._utcnow_iso()
        with self.transaction():
            candidate_lock = self._conn.execute(
                """
                UPDATE agentic_ready_publications
                SET updated_at = updated_at
                WHERE publication_id = ?
                """,
                (publication_id,),
            )
            if candidate_lock.rowcount != 1:
                raise ValueError("ready-data publication not found")
            publication = self.get_agentic_ready_publication(publication_id)
            if not publication:
                raise ValueError("ready-data publication not found")
            if publication["attempt_disposition"]:
                raise ValueError(
                    "ready-data publication attempt disposition prevents publication"
                )
            if publication["gc_state"] in {"claimed", "delete_failed", "deleted"}:
                raise ValueError("ready-data publication is already under garbage collection")
            if self._agentic_ready_paths_conflict(
                publication_id,
                str(publication["output_dir"]),
                include_manifests=not str(publication["source_version_kind"]).startswith(
                    "legacy"
                ),
            ):
                raise ValueError("ready-data publication output path is already reserved")
            kb_id = str(publication["kb_id"])
            profile = str(publication["profile"])
            self._conn.execute(
                """
                INSERT INTO agentic_ready_slots (
                    kb_id, profile, active_publication_id, previous_publication_id,
                    automatic_build_enabled, automatic_publish_enabled, updated_at
                )
                VALUES (?, ?, NULL, NULL, 0, 0, ?)
                ON CONFLICT(kb_id, profile) DO NOTHING
                """,
                (kb_id, profile, now),
            )
            current = self.get_agentic_ready_publication_state(kb_id=kb_id, profile=profile)
            if current["active_publication_id"] == publication_id:
                self._conn.execute(
                    "DELETE FROM agentic_ready_publication_gc WHERE publication_id = ?",
                    (publication_id,),
                )
                current["idempotent"] = True
                current["cas_won"] = True
                return current

            if publication["status"] != "validated":
                raise ValueError("only validated ready-data publications can be published")

            if current["active_publication_id"] != expected_active_publication_id:
                current["idempotent"] = False
                current["cas_won"] = False
                return current

            previous_active_id = expected_active_publication_id
            old_previous_id = current["previous_publication_id"]
            next_previous_id = (
                previous_active_id if preserve_expected_active_as_previous else None
            )
            slot_update = self._conn.execute(
                """
                UPDATE agentic_ready_slots
                SET active_publication_id = ?, previous_publication_id = ?,
                    publication_revision = publication_revision + 1,
                    updated_at = ?
                WHERE kb_id = ? AND profile = ? AND active_publication_id IS ?
                """,
                (
                    publication_id,
                    next_previous_id,
                    now,
                    kb_id,
                    profile,
                    expected_active_publication_id,
                ),
            )
            if slot_update.rowcount != 1:
                current = self.get_agentic_ready_publication_state(kb_id=kb_id, profile=profile)
                current["idempotent"] = False
                current["cas_won"] = False
                return current

            if old_previous_id and old_previous_id not in {previous_active_id, publication_id}:
                self._conn.execute(
                    "UPDATE agentic_ready_publications SET status = 'validated', updated_at = ? WHERE publication_id = ?",
                    (now, old_previous_id),
                )
            if previous_active_id:
                if preserve_expected_active_as_previous:
                    self._conn.execute(
                        "UPDATE agentic_ready_publications SET status = 'previous', updated_at = ? WHERE publication_id = ?",
                        (now, previous_active_id),
                    )
                else:
                    self._conn.execute(
                        """
                        UPDATE agentic_ready_publications
                        SET status = 'failed', error_message = ?, updated_at = ?
                        WHERE publication_id = ?
                        """,
                        (
                            invalidated_expected_active_error
                            or "active ready_data failed publication validation",
                            now,
                            previous_active_id,
                        ),
                    )
            self._conn.execute(
                """
                UPDATE agentic_ready_publications
                SET status = 'active', published_at = ?, updated_at = ?
                WHERE publication_id = ?
                """,
                (now, now, publication_id),
            )
            self._conn.execute(
                "DELETE FROM agentic_ready_publication_gc WHERE publication_id = ?",
                (publication_id,),
            )
            self._publish_agentic_ready_manifest_row(publication)

        state = self.get_agentic_ready_publication_state(kb_id=kb_id, profile=profile)
        state["idempotent"] = False
        state["cas_won"] = True
        return state

    def publish_claimed_agentic_ready_publication(
        self,
        publication_id: str,
        *,
        kb_id: str,
        profile: str,
        generation: int,
        claim_token: str,
        expected_active_publication_id: str | None,
        preserve_expected_active_as_previous: bool = True,
        invalidated_expected_active_error: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Fence an automatic publish and source settlement in one SQLite transaction."""
        normalized_profile = str(profile or "general").strip().lower() or "general"
        with self.transaction(immediate=True):
            fence = self.check_agentic_ready_automation_claim(
                kb_id=kb_id,
                profile=normalized_profile,
                generation=int(generation),
                claim_token=claim_token,
                require_publish=True,
                now=now,
            )
            if fence["reason"] != "ok":
                state = self.get_agentic_ready_publication_state(
                    kb_id=kb_id,
                    profile=normalized_profile,
                )
                state["automation_fence_won"] = False
                state["automation_fence_reason"] = fence["reason"]
                state["cas_won"] = False
                return state
            publication = self.get_agentic_ready_publication(publication_id)
            if not publication:
                raise ValueError("ready-data publication not found")
            if (
                str(publication["kb_id"]) != kb_id
                or str(publication["profile"]) != normalized_profile
            ):
                raise ValueError("ready-data automation publication scope mismatch")
            state = self.publish_agentic_ready_publication(
                publication_id,
                expected_active_publication_id=expected_active_publication_id,
                preserve_expected_active_as_previous=preserve_expected_active_as_previous,
                invalidated_expected_active_error=invalidated_expected_active_error,
            )
            state["automation_fence_won"] = True
            state["automation_fence_reason"] = "ok"
            if not state.get("cas_won"):
                return state
            self.record_agentic_ready_source_evaluation(
                kb_id=kb_id,
                profile=normalized_profile,
                evaluated_generation=int(generation),
                source_version_kind=str(publication["source_version_kind"]),
                source_version_id=str(publication["source_version_id"]),
            )
            finished = self.finish_agentic_ready_automation_claim(
                kb_id=kb_id,
                profile=normalized_profile,
                generation=int(generation),
                claim_token=claim_token,
                automation_state="succeeded",
                publication_id=publication_id,
                success=True,
                now=now,
            )
            if not finished:
                raise RuntimeError("ready-data automation publish lost its completion claim")
        state = self.get_agentic_ready_publication_state(
            kb_id=kb_id,
            profile=normalized_profile,
        )
        state["automation_fence_won"] = True
        state["automation_fence_reason"] = "ok"
        state["cas_won"] = True
        return state

    def rollback_agentic_ready_publication(
        self,
        *,
        kb_id: str,
        profile: str = "general",
        expected_active_publication_id: str,
        expected_previous_publication_id: str,
        validated_previous_publication_id: str,
        validate_previous_publication: Callable[[dict[str, Any]], bool] | None = None,
    ) -> dict[str, Any]:
        """CAS-swap slots after the caller explicitly validates the previous artifact."""
        if (
            not validated_previous_publication_id
            or validated_previous_publication_id != expected_previous_publication_id
        ):
            raise ValueError("previous ready-data publication was not explicitly validated")
        normalized_profile = str(profile or "general").strip().lower() or "general"
        now = self._utcnow_iso()
        with self.transaction():
            self._conn.execute(
                """
                UPDATE agentic_ready_slots
                SET updated_at = updated_at
                WHERE kb_id = ? AND profile = ?
                """,
                (kb_id, normalized_profile),
            )
            current = self.get_agentic_ready_publication_state(kb_id=kb_id, profile=normalized_profile)
            active_id = current["active_publication_id"]
            previous_id = current["previous_publication_id"]
            if not active_id or not previous_id:
                raise ValueError("no previous validated ready-data publication is available")
            if (
                active_id != expected_active_publication_id
                or previous_id != expected_previous_publication_id
            ):
                current["rolled_back"] = False
                current["cas_won"] = False
                return current
            active = self.get_agentic_ready_publication(str(active_id))
            if (
                not active
                or not agentic_ready_publication_matches_scope(
                    active,
                    kb_id=kb_id,
                    profile=normalized_profile,
                )
                or active.get("status") != "active"
            ):
                raise ValueError("active ready-data publication scope or status is invalid")
            previous = self.get_agentic_ready_publication(str(previous_id))
            if (
                not previous
                or not agentic_ready_publication_matches_scope(
                    previous,
                    kb_id=kb_id,
                    profile=normalized_profile,
                )
                or previous.get("status") != "previous"
            ):
                raise ValueError("previous ready-data publication is not validated")
            if (
                validate_previous_publication is not None
                and not validate_previous_publication(previous)
            ):
                raise ValueError(
                    "previous ready-data publication failed integrity validation"
                )
            if previous["gc_state"] in {"claimed", "delete_failed", "deleted"}:
                raise ValueError("previous ready-data publication is under garbage collection")
            if self._agentic_ready_paths_conflict(
                str(previous_id),
                str(previous["output_dir"]),
            ):
                raise ValueError("previous ready-data publication output path is already reserved")
            slot_update = self._conn.execute(
                """
                UPDATE agentic_ready_slots
                SET active_publication_id = ?, previous_publication_id = ?,
                    publication_revision = publication_revision + 1,
                    updated_at = ?
                WHERE kb_id = ? AND profile = ?
                  AND active_publication_id = ?
                  AND previous_publication_id = ?
                """,
                (
                    previous_id,
                    active_id,
                    now,
                    kb_id,
                    normalized_profile,
                    expected_active_publication_id,
                    expected_previous_publication_id,
                ),
            )
            if slot_update.rowcount != 1:
                current = self.get_agentic_ready_publication_state(
                    kb_id=kb_id,
                    profile=normalized_profile,
                )
                current["rolled_back"] = False
                current["cas_won"] = False
                return current
            active_update = self._conn.execute(
                """
                UPDATE agentic_ready_publications
                SET status = 'previous', updated_at = ?
                WHERE publication_id = ? AND kb_id = ?
                  AND LOWER(TRIM(profile)) = ? AND status = 'active'
                """,
                (now, active_id, kb_id, normalized_profile),
            )
            if active_update.rowcount != 1:
                raise ValueError("active ready-data publication changed during rollback")
            previous_update = self._conn.execute(
                """
                UPDATE agentic_ready_publications
                SET status = 'active', published_at = ?, updated_at = ?
                WHERE publication_id = ? AND kb_id = ?
                  AND LOWER(TRIM(profile)) = ? AND status = 'previous'
                """,
                (now, now, previous_id, kb_id, normalized_profile),
            )
            if previous_update.rowcount != 1:
                raise ValueError("previous ready-data publication changed during rollback")
            self._conn.execute(
                "DELETE FROM agentic_ready_publication_gc WHERE publication_id = ?",
                (previous_id,),
            )
            self._publish_agentic_ready_manifest_row(previous)

        state = self.get_agentic_ready_publication_state(kb_id=kb_id, profile=normalized_profile)
        state["rolled_back"] = True
        state["cas_won"] = True
        return state

    def create_kb_index_version(
        self,
        *,
        kb_id: str,
        embedding_model: str,
        index_type: str,
        chunk_count: int,
        embedding_provider: str = "openai",
        embedding_dimension: int | None = None,
        status: str = "ready",
        artifact_path: str = "",
        chunk_ids: list[str] | None = None,
        built_at: str | None = None,
    ) -> dict[str, Any]:
        now = self._utcnow_iso()
        index_version_id = f"idxv_{uuid.uuid4().hex}"
        built_time = built_at or now
        normalized_provider = str(embedding_provider or "openai").strip().lower() or "openai"
        normalized_model = str(embedding_model or "").strip()
        normalized_dimension = (
            int(embedding_dimension) if embedding_dimension not in (None, "") else None
        )
        normalized_status = str(status or "").strip().lower()
        with self.transaction():
            previous_ready = self._conn.execute(
                """
                SELECT embedding_provider, embedding_model, embedding_dimension
                FROM kb_ready_index_state
                WHERE kb_id = ?
                """,
                (kb_id,),
            ).fetchone()
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
                    index_version_id, kb_id, embedding_provider, embedding_model, embedding_dimension, index_type, status,
                    artifact_path, chunk_count, built_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    index_version_id,
                    kb_id,
                    normalized_provider,
                    normalized_model,
                    normalized_dimension,
                    index_type,
                    normalized_status,
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
            if normalized_status == "ready":
                previous_embedding = (
                    (
                        str(previous_ready[0] or "openai").strip().lower() or "openai",
                        str(previous_ready[1] or "").strip(),
                        int(previous_ready[2])
                        if previous_ready[2] not in (None, "")
                        else None,
                    )
                    if previous_ready
                    else None
                )
                current_embedding = (
                    normalized_provider,
                    normalized_model,
                    normalized_dimension,
                )
                reason = (
                    "embedding_index_committed"
                    if previous_embedding is not None
                    and previous_embedding != current_embedding
                    else "index_committed"
                )
                self.mark_agentic_ready_source_event_for_kb(kb_id=kb_id, reason=reason)
                self._conn.execute(
                    """
                    INSERT INTO kb_ready_index_state (
                        kb_id, index_version_id, embedding_provider,
                        embedding_model, embedding_dimension, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(kb_id) DO UPDATE SET
                        index_version_id = excluded.index_version_id,
                        embedding_provider = excluded.embedding_provider,
                        embedding_model = excluded.embedding_model,
                        embedding_dimension = excluded.embedding_dimension,
                        updated_at = excluded.updated_at
                    """,
                    (
                        kb_id,
                        index_version_id,
                        normalized_provider,
                        normalized_model,
                        normalized_dimension,
                        now,
                    ),
                )
        return {
            "index_version_id": index_version_id,
            "kb_id": kb_id,
            "embedding_provider": normalized_provider,
            "embedding_model": normalized_model,
            "embedding_dimension": normalized_dimension,
            "index_type": index_type,
            "status": normalized_status,
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
