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
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.rag.exceptions import KnowledgeBaseException
from ai_actuarial.rag.semantic_chunking import SemanticChunker, Chunk
from ai_actuarial.rag.embeddings import EmbeddingGenerator
from ai_actuarial.rag.vector_store import VectorStore


class KnowledgeBase:
    """
    Represents a single knowledge base with its configuration and state.
    """
    
    def __init__(
        self,
        kb_id: str,
        name: str,
        description: str = "",
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
        self.config = config or RAGConfig.from_env()
        
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
        
        self.embedding_generator = EmbeddingGenerator(self.config)
    
    def _ensure_rag_tables(self) -> None:
        """Create RAG-specific tables if they don't exist."""
        conn = self.storage._conn
        
        # rag_knowledge_bases table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rag_knowledge_bases (
                kb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
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
        except:
            conn.execute("""
                ALTER TABLE catalog_items 
                ADD COLUMN rag_indexed INTEGER DEFAULT 0
            """)
        
        try:
            conn.execute("SELECT rag_indexed_at FROM catalog_items LIMIT 1")
        except:
            conn.execute("""
                ALTER TABLE catalog_items 
                ADD COLUMN rag_indexed_at TEXT
            """)
        
        try:
            conn.execute("SELECT rag_chunk_count FROM catalog_items LIMIT 1")
        except:
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
            embedding_model=embedding_model or self.config.embedding_model,
            chunk_size=chunk_size or self.config.max_chunk_tokens,
            chunk_overlap=chunk_overlap or (self.config.max_chunk_tokens - self.config.min_chunk_tokens),
            index_type=index_type or self.config.index_type
        )
        
        # Create storage directories
        kb_dir = Path(self.config.data_dir) / kb_id
        kb_dir.mkdir(parents=True, exist_ok=True)
        
        # Store in database
        conn = self.storage._conn
        conn.execute("""
            INSERT INTO rag_knowledge_bases 
            (kb_id, name, description, embedding_model, chunk_size, chunk_overlap, 
             index_type, created_at, updated_at, file_count, chunk_count,
             index_path, metadata_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            kb.kb_id, kb.name, kb.description, kb.embedding_model,
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
            SELECT kb_id, name, description, embedding_model, chunk_size, chunk_overlap,
                   index_type, created_at, updated_at, file_count, chunk_count
            FROM rag_knowledge_bases
            WHERE kb_id = ?
        """, (kb_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        return KnowledgeBase(
            kb_id=row[0], name=row[1], description=row[2],
            embedding_model=row[3], chunk_size=row[4], chunk_overlap=row[5],
            index_type=row[6], created_at=row[7], updated_at=row[8],
            file_count=row[9], chunk_count=row[10]
        )
    
    def list_kbs(self) -> List[KnowledgeBase]:
        """List all knowledge bases."""
        conn = self.storage._conn
        cursor = conn.execute("""
            SELECT kb_id, name, description, embedding_model, chunk_size, chunk_overlap,
                   index_type, created_at, updated_at, file_count, chunk_count
            FROM rag_knowledge_bases
            ORDER BY created_at DESC
        """)
        
        kbs = []
        for row in cursor.fetchall():
            kbs.append(KnowledgeBase(
                kb_id=row[0], name=row[1], description=row[2],
                embedding_model=row[3], chunk_size=row[4], chunk_overlap=row[5],
                index_type=row[6], created_at=row[7], updated_at=row[8],
                file_count=row[9], chunk_count=row[10]
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
                   f.title, f.source_site, c.markdown_updated_at
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
