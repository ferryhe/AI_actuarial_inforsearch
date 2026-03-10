"""
Knowledge Base Manager for RAG system.

Provides CRUD operations for knowledge bases and manages the indexing pipeline.
Integrates with the existing Storage module for metadata persistence.

Features:
- KB creation, update, deletion
- File-to-KB associations
- Smart update detection (based on markdown_updated_at)
- Incremental indexing
- Statistics and monitoring
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.rag.exceptions import KnowledgeBaseException
from ai_actuarial.rag.semantic_chunking import SemanticChunker
from ai_actuarial.rag.embeddings import EmbeddingGenerator

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """
    Represents a single knowledge base with its configuration and state.
    """
    
    def __init__(
        self,
        kb_id: str,
        name: str,
        description: str = "",
        kb_mode: str = "category",  # "category" (auto-sync) or "manual" (explicit selection)
        embedding_model: str = "text-embedding-3-large",
        chunk_size: int = 800,
        chunk_overlap: int = 100,
        index_type: str = "Flat",
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        file_count: int = 0,
        chunk_count: int = 0
    ):
        """Initialize knowledge base metadata."""
        self.kb_id = kb_id
        self.name = name
        self.description = description
        self.kb_mode = kb_mode
        self.embedding_model = embedding_model
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.index_type = index_type
        self.created_at = created_at or self._get_timestamp()
        self.updated_at = updated_at or self._get_timestamp()
        self.file_count = file_count
        self.chunk_count = chunk_count
    
    @staticmethod
    def _get_timestamp() -> str:
        """Get current ISO timestamp."""
        return datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'kb_id': self.kb_id,
            'name': self.name,
            'description': self.description,
            'kb_mode': self.kb_mode,
            'embedding_model': self.embedding_model,
            'chunk_size': self.chunk_size,
            'chunk_overlap': self.chunk_overlap,
            'index_type': self.index_type,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'file_count': self.file_count,
            'chunk_count': self.chunk_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'KnowledgeBase':
        """Create from dictionary."""
        return cls(**data)


class KnowledgeBaseManager:
    """
    Manages knowledge bases and their indexing operations.
    
    High-priority features:
    - Incremental indexing (add files without full rebuild)
    - Smart update detection (track file changes)
    - Multi-KB support
    """
    
    def __init__(
        self,
        storage,  # ai_actuarial.storage.Storage instance
        config: Optional[RAGConfig] = None
    ):
        """
        Initialize KB manager.
        
        Args:
            storage: Storage instance for database operations
            config: RAG configuration
        """
        self.storage = storage
        self.config = config or RAGConfig.from_config(storage=storage)
        
        # Ensure RAG tables exist
        self._ensure_rag_tables()
        
        # Initialize components
        self.chunker = SemanticChunker(
            max_tokens=self.config.max_chunk_tokens,
            min_tokens=self.config.min_chunk_tokens,
            preserve_headers=self.config.preserve_headers,
            preserve_citations=self.config.preserve_citations,
            include_hierarchy=self.config.include_hierarchy
        )
        
        try:
            self.embedding_generator = EmbeddingGenerator(self.config)
        except Exception as exc:
            logger.warning("EmbeddingGenerator init failed: %s", exc)
            self.embedding_generator = None
    
    def _ensure_rag_tables(self) -> None:
        """Create RAG-specific tables if they don't exist."""
        conn = self.storage._conn

        def ensure_columns(table: str, columns: dict[str, str]) -> None:
            existing = {
                row[1]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for name, definition in columns.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

        # rag_knowledge_bases table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rag_knowledge_bases (
                kb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                kb_mode TEXT DEFAULT 'category',
                embedding_model TEXT NOT NULL,
                chunk_size INTEGER NOT NULL,
                chunk_overlap INTEGER NOT NULL,
                index_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                file_count INTEGER DEFAULT 0,
                chunk_count INTEGER DEFAULT 0,
                index_path TEXT,
                metadata_path TEXT
            )
        """)
        ensure_columns(
            "rag_knowledge_bases",
            {
                "description": "TEXT DEFAULT ''",
                "kb_mode": "TEXT DEFAULT 'category'",
                "embedding_model": "TEXT NOT NULL DEFAULT 'text-embedding-3-large'",
                "chunk_size": "INTEGER NOT NULL DEFAULT 800",
                "chunk_overlap": "INTEGER NOT NULL DEFAULT 100",
                "index_type": "TEXT NOT NULL DEFAULT 'Flat'",
                "created_at": "TEXT",
                "updated_at": "TEXT",
                "file_count": "INTEGER DEFAULT 0",
                "chunk_count": "INTEGER DEFAULT 0",
                "index_path": "TEXT",
                "metadata_path": "TEXT",
            },
        )

        # rag_kb_files table (tracks which files are in which KBs)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rag_kb_files (
                kb_id TEXT NOT NULL,
                file_url TEXT NOT NULL,
                added_at TEXT NOT NULL,
                chunk_count INTEGER DEFAULT 0,
                indexed_at TEXT,
                PRIMARY KEY (kb_id, file_url),
                FOREIGN KEY (kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE,
                FOREIGN KEY (file_url) REFERENCES files(url) ON DELETE CASCADE
            )
        """)
        ensure_columns(
            "rag_kb_files",
            {
                "chunk_count": "INTEGER DEFAULT 0",
                "indexed_at": "TEXT",
            },
        )

        # rag_chunks table (for debugging and granular tracking)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rag_chunks (
                chunk_id TEXT PRIMARY KEY,
                kb_id TEXT NOT NULL,
                file_url TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                token_count INTEGER NOT NULL,
                section_hierarchy TEXT,
                embedding_hash TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE,
                FOREIGN KEY (file_url) REFERENCES files(url) ON DELETE CASCADE
            )
        """)
        ensure_columns(
            "rag_chunks",
            {
                "section_hierarchy": "TEXT",
                "embedding_hash": "TEXT",
            },
        )
        
        # Create indices for performance
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rag_kb_files_kb_id 
            ON rag_kb_files(kb_id)
        """)
        
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rag_chunks_kb_file 
            ON rag_chunks(kb_id, file_url)
        """)
        
        # Add RAG columns to catalog_items if not present
        try:
            conn.execute("SELECT rag_indexed FROM catalog_items LIMIT 1")
        except Exception:
            conn.execute("""
                ALTER TABLE catalog_items 
                ADD COLUMN rag_indexed INTEGER DEFAULT 0
            """)
        
        try:
            conn.execute("SELECT rag_indexed_at FROM catalog_items LIMIT 1")
        except Exception:
            conn.execute("""
                ALTER TABLE catalog_items 
                ADD COLUMN rag_indexed_at TEXT
            """)
        
        try:
            conn.execute("SELECT rag_chunk_count FROM catalog_items LIMIT 1")
        except Exception:
            conn.execute("""
                ALTER TABLE catalog_items 
                ADD COLUMN rag_chunk_count INTEGER DEFAULT 0
            """)
        
        conn.commit()
    
    # ==================== KB CRUD Operations ====================
    
    def create_kb(
        self,
        kb_id: str,
        name: str,
        description: str = "",
        kb_mode: str = "category",
        embedding_model: Optional[str] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        index_type: Optional[str] = None
    ) -> KnowledgeBase:
        """
        Create a new knowledge base.
        
        Args:
            kb_id: Unique identifier for KB
            name: Human-readable name
            description: Optional description
            kb_mode: "category" (auto-sync) or "manual" (explicit selection)
            embedding_model: Embedding model to use
            chunk_size: Max tokens per chunk
            chunk_overlap: Overlap between chunks
            index_type: FAISS index type
            
        Returns:
            Created KnowledgeBase instance
            
        Raises:
            KnowledgeBaseException: If KB already exists or creation fails
        """
        # Check if KB already exists
        existing = self.get_kb(kb_id)
        if existing:
            raise KnowledgeBaseException(f"Knowledge base '{kb_id}' already exists")
        
        # Create KB object with defaults from config
        kb = KnowledgeBase(
            kb_id=kb_id,
            name=name,
            description=description,
            kb_mode=kb_mode,
            embedding_model=embedding_model or self.config.embedding_model,
            chunk_size=chunk_size or self.config.max_chunk_tokens,
            chunk_overlap=chunk_overlap or 100,
            index_type=index_type or self.config.index_type
        )
        
        # Create storage directories
        kb_dir = Path(self.config.data_dir) / kb_id
        kb_dir.mkdir(parents=True, exist_ok=True)
        
        # Store in database
        conn = self.storage._conn
        conn.execute("""
            INSERT INTO rag_knowledge_bases 
            (kb_id, name, description, kb_mode, embedding_model, chunk_size, chunk_overlap, 
             index_type, created_at, updated_at, file_count, chunk_count,
             index_path, metadata_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            kb.kb_id, kb.name, kb.description, kb.kb_mode, kb.embedding_model,
            kb.chunk_size, kb.chunk_overlap, kb.index_type,
            kb.created_at, kb.updated_at, kb.file_count, kb.chunk_count,
            str(kb_dir / "index.faiss"),
            str(kb_dir / "index.meta.pkl")
        ))
        conn.commit()
        
        return kb
    
    def get_kb(self, kb_id: str) -> Optional[KnowledgeBase]:
        """Get knowledge base by ID."""
        conn = self.storage._conn
        cursor = conn.execute("""
            SELECT kb_id, name, description, kb_mode, embedding_model, chunk_size, chunk_overlap,
                   index_type, created_at, updated_at, file_count, chunk_count
            FROM rag_knowledge_bases
            WHERE kb_id = ?
        """, (kb_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        return KnowledgeBase(
            kb_id=row[0], name=row[1], description=row[2],
            kb_mode=row[3] or "category",  # Default to "category" for existing KBs
            embedding_model=row[4], chunk_size=row[5], chunk_overlap=row[6],
            index_type=row[7], created_at=row[8], updated_at=row[9],
            file_count=row[10], chunk_count=row[11]
        )
    
    def list_kbs(self) -> List[KnowledgeBase]:
        """List all knowledge bases."""
        conn = self.storage._conn
        cursor = conn.execute("""
            SELECT kb_id, name, description, kb_mode, embedding_model, chunk_size, chunk_overlap,
                   index_type, created_at, updated_at, file_count, chunk_count
            FROM rag_knowledge_bases
            ORDER BY created_at DESC
        """)
        
        kbs = []
        for row in cursor.fetchall():
            kbs.append(KnowledgeBase(
                kb_id=row[0], name=row[1], description=row[2],
                kb_mode=row[3] or "category",  # Default to "category" for existing KBs
                embedding_model=row[4], chunk_size=row[5], chunk_overlap=row[6],
                index_type=row[7], created_at=row[8], updated_at=row[9],
                file_count=row[10], chunk_count=row[11]
            ))
        
        return kbs
    
    def update_kb(
        self,
        kb_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> bool:
        """Update knowledge base metadata."""
        kb = self.get_kb(kb_id)
        if not kb:
            raise KnowledgeBaseException(f"Knowledge base '{kb_id}' not found")
        
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        
        if not updates:
            return False
        
        updates.append("updated_at = ?")
        params.append(KnowledgeBase._get_timestamp())
        params.append(kb_id)
        
        conn = self.storage._conn
        conn.execute(f"""
            UPDATE rag_knowledge_bases 
            SET {', '.join(updates)}
            WHERE kb_id = ?
        """, params)
        conn.commit()
        
        return True
    
    def delete_kb(self, kb_id: str) -> bool:
        """
        Delete a knowledge base.
        
        Removes KB metadata, file associations, chunks, and index files.
        """
        kb = self.get_kb(kb_id)
        if not kb:
            return False
        
        conn = self.storage._conn
        
        # Delete from database (cascades to rag_kb_files and rag_chunks)
        conn.execute("DELETE FROM rag_knowledge_bases WHERE kb_id = ?", (kb_id,))
        conn.commit()
        
        # Delete index files
        kb_dir = Path(self.config.data_dir) / kb_id
        if kb_dir.exists():
            import shutil
            shutil.rmtree(kb_dir)
        
        return True
    
    # ==================== File Association Operations ====================
    
    def add_files_to_kb(
        self,
        kb_id: str,
        file_urls: List[str]
    ) -> Dict[str, Any]:
        """
        Add files to knowledge base (marks for indexing, doesn't index yet).
        
        Args:
            kb_id: Knowledge base ID
            file_urls: List of file URLs to add
            
        Returns:
            Dict with added_count and skipped_count
        """
        kb = self.get_kb(kb_id)
        if not kb:
            raise KnowledgeBaseException(f"Knowledge base '{kb_id}' not found")
        
        conn = self.storage._conn
        added_count = 0
        skipped_count = 0
        timestamp = KnowledgeBase._get_timestamp()
        
        for file_url in file_urls:
            # Check if already in KB
            cursor = conn.execute("""
                SELECT 1 FROM rag_kb_files 
                WHERE kb_id = ? AND file_url = ?
            """, (kb_id, file_url))
            
            if cursor.fetchone():
                skipped_count += 1
                continue
            
            # Add to KB
            conn.execute("""
                INSERT INTO rag_kb_files (kb_id, file_url, added_at)
                VALUES (?, ?, ?)
            """, (kb_id, file_url, timestamp))
            added_count += 1
        
        # Update file count
        conn.execute("""
            UPDATE rag_knowledge_bases
            SET file_count = (
                SELECT COUNT(*) FROM rag_kb_files WHERE kb_id = ?
            ),
            updated_at = ?
            WHERE kb_id = ?
        """, (kb_id, timestamp, kb_id))
        
        conn.commit()
        
        return {
            'added_count': added_count,
            'skipped_count': skipped_count,
            'total_files': kb.file_count + added_count
        }
    
    def remove_files_from_kb(
        self,
        kb_id: str,
        file_urls: List[str]
    ) -> int:
        """Remove files from knowledge base."""
        kb = self.get_kb(kb_id)
        if not kb:
            raise KnowledgeBaseException(f"Knowledge base '{kb_id}' not found")
        
        conn = self.storage._conn
        removed_count = 0
        
        for file_url in file_urls:
            cursor = conn.execute("""
                DELETE FROM rag_kb_files 
                WHERE kb_id = ? AND file_url = ?
            """, (kb_id, file_url))
            removed_count += cursor.rowcount
        
        # Update file count
        timestamp = KnowledgeBase._get_timestamp()
        conn.execute("""
            UPDATE rag_knowledge_bases
            SET file_count = (
                SELECT COUNT(*) FROM rag_kb_files WHERE kb_id = ?
            ),
            updated_at = ?
            WHERE kb_id = ?
        """, (kb_id, timestamp, kb_id))
        
        conn.commit()
        
        return removed_count
    
    def get_kb_files(self, kb_id: str) -> List[Dict[str, Any]]:
        """Get all files in a knowledge base."""
        conn = self.storage._conn
        cursor = conn.execute("""
            SELECT kf.file_url, kf.added_at, kf.chunk_count, kf.indexed_at,
                   f.title, f.source_site, c.markdown_updated_at, c.category
            FROM rag_kb_files kf
            JOIN files f ON kf.file_url = f.url
            LEFT JOIN catalog_items c ON kf.file_url = c.file_url
            WHERE kf.kb_id = ?
            ORDER BY kf.added_at DESC
        """, (kb_id,))
        
        files = []
        for row in cursor.fetchall():
            files.append({
                'file_url': row[0],
                'added_at': row[1],
                'chunk_count': row[2],
                'indexed_at': row[3],
                'title': row[4],
                'source_site': row[5],
                'markdown_updated_at': row[6],
                'category': row[7],
                'needs_reindex': row[6] and row[3] and row[6] > row[3]
            })
        
        return files
    
    def get_files_needing_index(self, kb_id: str) -> List[str]:
        """
        Get files that need indexing (new or updated).
        
        Smart update detection: files are flagged for reindex if:
        - Not yet indexed (indexed_at is NULL)
        - Markdown has been updated after last index (markdown_updated_at > indexed_at)
        """
        conn = self.storage._conn
        cursor = conn.execute("""
            SELECT kf.file_url
            FROM rag_kb_files kf
            LEFT JOIN catalog_items c ON kf.file_url = c.file_url
            WHERE kf.kb_id = ?
            AND (
                kf.indexed_at IS NULL
                OR (c.markdown_updated_at IS NOT NULL 
                    AND c.markdown_updated_at > kf.indexed_at)
            )
        """, (kb_id,))
        
        return [row[0] for row in cursor.fetchall()]
    
    def get_kb_stats(self, kb_id: str) -> Dict[str, Any]:
        """Get statistics for a knowledge base."""
        kb = self.get_kb(kb_id)
        if not kb:
            raise KnowledgeBaseException(f"Knowledge base '{kb_id}' not found")
        
        conn = self.storage._conn
        
        # Count files needing index
        cursor = conn.execute("""
            SELECT COUNT(*)
            FROM rag_kb_files kf
            LEFT JOIN catalog_items c ON kf.file_url = c.file_url
            WHERE kf.kb_id = ?
            AND (
                kf.indexed_at IS NULL
                OR (c.markdown_updated_at IS NOT NULL 
                    AND c.markdown_updated_at > kf.indexed_at)
            )
        """, (kb_id,))
        pending_count = cursor.fetchone()[0]
        
        # Count indexed files
        cursor = conn.execute("""
            SELECT COUNT(*)
            FROM rag_kb_files
            WHERE kb_id = ? AND indexed_at IS NOT NULL
        """, (kb_id,))
        indexed_count = cursor.fetchone()[0]
        
        return {
            'kb_id': kb.kb_id,
            'name': kb.name,
            'total_files': kb.file_count,
            'indexed_files': indexed_count,
            'pending_files': pending_count,
            'total_chunks': kb.chunk_count,
            'created_at': kb.created_at,
            'updated_at': kb.updated_at,
            'embedding_model': kb.embedding_model,
            'chunk_size': kb.chunk_size,
            'index_type': kb.index_type
        }

    # ========== NEW: Task Management & Category Methods ==========
    
    def get_rag_task_metadata(
        self, 
        kb_id: str,
        categories: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get metadata for RAG indexing task UI display.
        
        Shows files needing indexing with statistics for task confirmation.
        
        Args:
            kb_id: Knowledge base ID
            categories: Optional category filter for pending files
            
        Returns:
            Dictionary with task metadata for UI display
        """
        kb = self.get_kb(kb_id)
        if not kb:
            raise KnowledgeBaseException(f"Knowledge base not found: {kb_id}")
        
        # Get all files in KB
        kb_files = self.get_kb_files(kb_id)
        total_files = len(kb_files)
        
        # Get files needing indexing (new or modified)
        pending_files = self.get_files_needing_index(kb_id)
        
        # Apply category filter if provided
        if categories:
            pending_files = self._filter_files_by_categories(pending_files, categories)
        
        # Build pending details
        pending_details = []
        earliest_timestamp = None
        
        for file_url in pending_files[:20]:  # Limit to 20 for display
            # Get file info from catalog_items
            cursor = self.storage._conn.execute("""
                SELECT 
                    ci.updated_at as modified_at,
                    kf.indexed_at,
                    kf.added_at
                FROM rag_kb_files kf
                LEFT JOIN catalog_items ci ON kf.file_url = ci.file_url
                WHERE kf.kb_id = ? AND kf.file_url = ?
            """, (kb_id, file_url))
            
            row = cursor.fetchone()
            if row:
                modified_at = row[0]
                indexed_at = row[1]
                added_at = row[2]
                reason = "new" if not indexed_at else "modified"
                
                pending_details.append({
                    "file_url": file_url,
                    "reason": reason,
                    "modified_at": modified_at,
                    "indexed_at": indexed_at,
                    "added_at": added_at
                })
                
                # Track earliest
                timestamp = modified_at or added_at
                if timestamp and (not earliest_timestamp or timestamp < earliest_timestamp):
                    earliest_timestamp = timestamp
        
        # Get statistics
        stats = self.get_kb_stats(kb_id)
        
        # Estimate processing
        estimated_chunks_per_file = 15  # Average from testing
        estimated_seconds_per_file = 3  # Average: chunk + embed + index
        
        return {
            "kb_id": kb_id,
            "kb_name": kb.name,
            "total_files_in_kb": total_files,
            "indexed_files": stats['indexed_files'],
            "pending_files": len(pending_files),
            "pending_details": pending_details,
            "earliest_pending": earliest_timestamp,
            "chunk_count_current": stats['total_chunks'],
            "estimated_new_chunks": len(pending_files) * estimated_chunks_per_file,
            "estimated_time_seconds": len(pending_files) * estimated_seconds_per_file,
            "categories_filter": categories
        }
    
    def _filter_files_by_categories(
        self, 
        file_urls: List[str], 
        categories: List[str]
    ) -> List[str]:
        """
        Filter file URLs by categories (supports multi-category files).
        
        Args:
            file_urls: List of file URLs to filter
            categories: List of category names to filter by
            
        Returns:
            Filtered list of file URLs
        """
        if not file_urls or not categories:
            return file_urls
        
        # Build category filter SQL
        category_conditions = []
        params = []
        for cat in categories:
            # Match: exact, prefix, suffix, or middle (semicolon-separated)
            category_conditions.append(
                "(ci.category = ? OR ci.category LIKE ? OR ci.category LIKE ? OR ci.category LIKE ?)"
            )
            params.extend([cat, f"{cat};%", f"%; {cat}", f"%; {cat};%"])
        
        placeholders = " OR ".join(category_conditions)
        file_url_placeholders = ",".join(["?" for _ in file_urls])
        
        cursor = self.storage._conn.execute(f"""
            SELECT DISTINCT ci.file_url
            FROM catalog_items ci
            WHERE ci.file_url IN ({file_url_placeholders})
            AND ({placeholders})
        """, file_urls + params)
        
        return [row[0] for row in cursor.fetchall()]
    
    def link_kb_to_categories(
        self, 
        kb_id: str, 
        categories: List[str],
        auto_sync: bool = True
    ):
        """
        Link a KB to one or more categories for automatic file discovery.
        
        Args:
            kb_id: Knowledge base ID
            categories: List of category names
            auto_sync: Whether to auto-add files from these categories
        """
        # Ensure category mapping table exists
        self._ensure_category_mapping_table()
        
        timestamp = KnowledgeBase._get_timestamp()
        for category in categories:
            self.storage._conn.execute("""
                INSERT OR REPLACE INTO rag_kb_category_mappings 
                (kb_id, category, auto_sync, created_at)
                VALUES (?, ?, ?, ?)
            """, (kb_id, category, 1 if auto_sync else 0, timestamp))
        
        self.storage._conn.commit()
        
        # If auto_sync enabled, automatically add all matching files
        if auto_sync:
            self._sync_category_files(kb_id, categories)
    
    def _sync_category_files(self, kb_id: str, categories: List[str]):
        """
        Automatically add all files from specified categories to KB.
        
        Args:
            kb_id: Knowledge base ID
            categories: List of category names
        """
        # Build query to find all files matching categories
        category_conditions = []
        params = []
        for cat in categories:
            category_conditions.append(
                "(ci.category = ? OR ci.category LIKE ? OR ci.category LIKE ? OR ci.category LIKE ?)"
            )
            params.extend([cat, f"{cat};%", f"%; {cat}", f"%; {cat};%"])
        
        placeholders = " OR ".join(category_conditions)
        
        cursor = self.storage._conn.execute(f"""
            SELECT DISTINCT ci.file_url
            FROM catalog_items ci
            WHERE ({placeholders})
            AND ci.status = 'ok'
            AND ci.markdown_content IS NOT NULL
            AND ci.markdown_content != ''
        """, params)
        
        file_urls = [row[0] for row in cursor.fetchall()]
        
        # Add to KB (silently skip if already added)
        if file_urls:
            self.add_files_to_kb(kb_id, file_urls)
    
    def get_kb_categories(self, kb_id: str) -> List[str]:
        """
        Get categories linked to a KB.
        
        Args:
            kb_id: Knowledge base ID
            
        Returns:
            List of category names
        """
        self._ensure_category_mapping_table()
        cursor = self.storage._conn.execute("""
            SELECT category FROM rag_kb_category_mappings
            WHERE kb_id = ?
            ORDER BY category
        """, (kb_id,))
        return [row[0] for row in cursor.fetchall()]
    
    def get_category_kbs(self, category: str) -> List[str]:
        """
        Get KBs linked to a category.
        
        Args:
            category: Category name
            
        Returns:
            List of KB IDs
        """
        self._ensure_category_mapping_table()
        cursor = self.storage._conn.execute("""
            SELECT kb_id FROM rag_kb_category_mappings
            WHERE category = ?
            ORDER BY kb_id
        """, (category,))
        return [row[0] for row in cursor.fetchall()]
    
    def get_unmapped_categories(self) -> List[Dict[str, Any]]:
        """
        Get categories that have files but no associated KB.
        
        Returns:
            List of dicts with category name and file count
        """
        self._ensure_category_mapping_table()
        
        # Get all categories from catalog
        all_categories = self.storage.get_unique_categories()
        
        # Get categories with KB mappings
        cursor = self.storage._conn.execute("""
            SELECT DISTINCT category FROM rag_kb_category_mappings
        """)
        mapped_categories = {row[0] for row in cursor.fetchall()}
        
        # Find unmapped
        unmapped = []
        for cat in all_categories:
            if cat not in mapped_categories:
                # Get file count for this category
                cursor = self.storage._conn.execute("""
                    SELECT COUNT(DISTINCT file_url)
                    FROM catalog_items
                    WHERE category = ? OR category LIKE ? OR category LIKE ? OR category LIKE ?
                """, (cat, f"{cat};%", f"%; {cat}", f"%; {cat};%"))
                
                file_count = cursor.fetchone()[0]
                unmapped.append({
                    "category": cat,
                    "file_count": file_count
                })
        
        return sorted(unmapped, key=lambda x: x['file_count'], reverse=True)
    
    def create_kb_from_category(
        self,
        category: str,
        kb_name: Optional[str] = None,
        auto_sync: bool = True
    ) -> KnowledgeBase:
        """
        Convenience method: Create KB and link to category in one step.
        
        Args:
            category: Category name
            kb_name: KB name (defaults to category name)
            auto_sync: Whether to auto-sync files from category
            
        Returns:
            Created KnowledgeBase instance
        """
        # Generate KB ID from category
        kb_id = category.lower().replace(" ", "_").replace(";", "_")
        kb_name = kb_name or f"{category} Knowledge Base"
        
        # Create KB
        kb = self.create_kb(
            kb_id=kb_id,
            name=kb_name,
            description=f"Knowledge base for {category} category",
            kb_mode="category"
        )
        
        # Link to category
        self.link_kb_to_categories(kb_id, [category], auto_sync=auto_sync)
        
        return kb
    
    def create_manual_kb(
        self,
        kb_id: str,
        name: str,
        file_urls: List[str],
        description: str = ""
    ) -> KnowledgeBase:
        """
        Create a KB with manually selected files (no category binding).
        
        Args:
            kb_id: Knowledge base ID
            name: KB name
            file_urls: List of specific file URLs to include
            description: KB description
            
        Returns:
            Created KnowledgeBase instance
        """
        # Create KB in manual mode
        kb = self.create_kb(
            kb_id=kb_id,
            name=name,
            description=description,
            kb_mode="manual"
        )
        
        # Add selected files
        if file_urls:
            self.add_files_to_kb(kb_id, file_urls)
        
        return kb
    
    def _ensure_category_mapping_table(self):
        """Initialize category-to-KB mapping table."""
        self.storage._conn.execute("""
            CREATE TABLE IF NOT EXISTS rag_kb_category_mappings (
                kb_id TEXT NOT NULL,
                category TEXT NOT NULL,
                auto_sync INTEGER DEFAULT 1,
                created_at TEXT,
                PRIMARY KEY (kb_id, category),
                FOREIGN KEY (kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE
            )
        """)
        self.storage._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rag_kb_category_kb 
            ON rag_kb_category_mappings(kb_id)
        """)
        self.storage._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rag_kb_category_cat 
            ON rag_kb_category_mappings(category)
        """)
        self.storage._conn.commit()
