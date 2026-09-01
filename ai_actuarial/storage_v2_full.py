"""StorageV2 Full - Integrated storage with RAG and Auth support."""

from sqlalchemy import inspect, text

from .storage_v2 import StorageV2
from .storage_v2_auth import StorageV2AuthMixin
from .storage_v2_rag import StorageV2RAGMixin


class StorageV2Full(StorageV2, StorageV2RAGMixin, StorageV2AuthMixin):
    """Full StorageV2 implementation with RAG and Auth capabilities."""

    def __init__(self, db_config: dict):
        # Explicitly initialize StorageV2 to ensure the backend is set up
        StorageV2.__init__(self, db_config)
        if str(db_config.get("type") or "sqlite").strip().lower() == "sqlite":
            self._migrate_sqlite_chunk_contract()

    def _migrate_sqlite_chunk_contract(self) -> None:
        engine = self.backend.engine
        if engine is None:
            raise RuntimeError("database backend is not connected")
        inspector = inspect(engine)
        if "file_chunk_sets" not in inspector.get_table_names():
            return
        columns = {column["name"] for column in inspector.get_columns("file_chunk_sets")}
        required = {
            "chunk_set_id",
            "file_url",
            "profile_id",
            "markdown_hash",
            "status",
            "chunk_count",
            "created_at",
            "updated_at",
        }
        if not required.issubset(columns):
            missing = ", ".join(sorted(required - columns))
            raise RuntimeError(f"file_chunk_sets migration missing columns: {missing}")
        unique_contracts = {
            tuple(constraint.get("column_names") or ())
            for constraint in inspector.get_unique_constraints("file_chunk_sets")
        }
        expected_unique = (
            "file_url",
            "markdown_hash",
            "profile_id",
            "profile_config_hash",
        )
        if "profile_config_hash" in columns and expected_unique in unique_contracts:
            return

        profile_columns = {column["name"] for column in inspector.get_columns("chunk_profiles")}
        if not {"profile_id", "config_hash"}.issubset(profile_columns):
            raise RuntimeError(
                "file_chunk_sets migration requires chunk_profiles.profile_id/config_hash"
            )

        session = self.backend.get_session()
        session.close()
        self.backend._session = None
        existing_hash = (
            "COALESCE(NULLIF(f.profile_config_hash, ''), p.config_hash)"
            if "profile_config_hash" in columns
            else "p.config_hash"
        )
        with engine.begin() as connection:
            orphan_count = connection.execute(text("""
                    SELECT COUNT(*)
                    FROM file_chunk_sets f
                    LEFT JOIN chunk_profiles p ON p.profile_id = f.profile_id
                    WHERE p.profile_id IS NULL OR p.config_hash IS NULL OR p.config_hash = ''
                    """)).scalar_one()
            if int(orphan_count or 0):
                raise RuntimeError(
                    "file_chunk_sets migration cannot audit one or more chunk profiles"
                )
            connection.execute(text("""
                    CREATE TABLE file_chunk_sets_issue237 (
                        chunk_set_id TEXT PRIMARY KEY,
                        file_url TEXT NOT NULL,
                        profile_id TEXT NOT NULL,
                        markdown_hash TEXT NOT NULL,
                        profile_config_hash TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'building',
                        chunk_count INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE(file_url, markdown_hash, profile_id, profile_config_hash),
                        FOREIGN KEY(file_url) REFERENCES files(url) ON DELETE CASCADE,
                        FOREIGN KEY(profile_id) REFERENCES chunk_profiles(profile_id) ON DELETE CASCADE
                    )
                    """))
            connection.execute(text(f"""
                    INSERT INTO file_chunk_sets_issue237 (
                        chunk_set_id, file_url, profile_id, markdown_hash,
                        profile_config_hash, status, chunk_count, created_at, updated_at
                    )
                    SELECT f.chunk_set_id, f.file_url, f.profile_id, f.markdown_hash,
                           {existing_hash}, f.status, f.chunk_count, f.created_at, f.updated_at
                    FROM file_chunk_sets f
                    JOIN chunk_profiles p ON p.profile_id = f.profile_id
                    """))
            connection.execute(text("DROP TABLE file_chunk_sets"))
            connection.execute(
                text("ALTER TABLE file_chunk_sets_issue237 RENAME TO file_chunk_sets")
            )
            connection.execute(
                text("CREATE INDEX idx_file_chunk_sets_file_url " "ON file_chunk_sets(file_url)")
            )
            connection.execute(
                text(
                    "CREATE INDEX idx_file_chunk_sets_profile_id " "ON file_chunk_sets(profile_id)"
                )
            )


__all__ = [
    "StorageV2Full",
    "StorageV2",
    "StorageV2RAGMixin",
    "StorageV2AuthMixin",
]
