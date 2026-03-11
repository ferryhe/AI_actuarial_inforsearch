"""
Indexing pipeline for RAG system.

End-to-end pipeline: markdown → chunks → embeddings → FAISS index

Features:
- Batch processing for efficiency
- Progress tracking and logging
- Error handling and recovery
- Incremental indexing support
"""

import hashlib
import logging
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
import numpy as np

from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.rag.exceptions import RAGException
from ai_actuarial.rag.semantic_chunking import Chunk
from ai_actuarial.rag.vector_store import VectorStore
from ai_actuarial.rag.knowledge_base import KnowledgeBase, KnowledgeBaseManager


logger = logging.getLogger(__name__)


class IndexingPipeline:
    """
    Orchestrates the indexing process from markdown to FAISS.
    
    Pipeline steps:
    1. Load markdown content from storage
    2. Chunk markdown using semantic chunking
    3. Generate embeddings for chunks
    4. Add vectors to FAISS index (incremental)
    5. Update metadata and tracking
    """
    
    def __init__(
        self,
        kb_manager: KnowledgeBaseManager,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        stop_check: Optional[Callable[[], bool]] = None,
    ):
        """
        Initialize indexing pipeline.
        
        Args:
            kb_manager: KnowledgeBaseManager instance
            progress_callback: Optional callback for progress updates
                              Signature: (message: str, current: int, total: int)
        """
        self.kb_manager = kb_manager
        self.storage = kb_manager.storage
        self.config = kb_manager.config
        self.progress_callback = progress_callback
        self.stop_check = stop_check
        
        # Components
        self.chunker = kb_manager.chunker
        self.embedding_generator = kb_manager.embedding_generator
    
    def index_files(
        self,
        kb_id: str,
        file_urls: List[str],
        force_reindex: bool = False
    ) -> Dict[str, Any]:
        """
        Index files into a knowledge base.
        
        Args:
            kb_id: Knowledge base ID
            file_urls: List of file URLs to index
            force_reindex: Whether to reindex files that are already indexed
            
        Returns:
            Dict with indexing statistics
        """
        kb = self.kb_manager.get_kb(kb_id)
        if not kb:
            raise RAGException(f"Knowledge base '{kb_id}' not found")

        stats = {
            'total_files': len(file_urls),
            'indexed_files': 0,
            'skipped_files': 0,
            'error_files': 0,
            'total_chunks': 0,
            'errors': [],
            'stopped': False,
        }
        
        self._log_progress(f"Starting indexing for KB '{kb.name}'", 0, len(file_urls))

        if self.stop_check and self.stop_check():
            stats['stopped'] = True
            self._log_progress(
                f"Stop requested for KB '{kb.name}' before indexing started",
                0,
                len(file_urls),
            )
            return stats
        
        # Load or create vector store
        kb_dir = Path(self.config.data_dir) / kb_id
        index_path = kb_dir / "index.faiss"
        
        # Get embedding dimension
        embedding_dim = self.embedding_generator.get_embedding_dimension()
        
        # If force_reindex is requested, ensure any existing index file is removed
        # so that the VectorStore starts from a clean state instead of appending.
        if force_reindex and index_path.exists():
            if self.stop_check and self.stop_check():
                stats['stopped'] = True
                self._log_progress(
                    f"Stop requested for KB '{kb.name}' before resetting index",
                    0,
                    len(file_urls),
                )
                return stats
            index_path.unlink()
        
        vector_store = VectorStore(
            dimension=embedding_dim,
            config=self.config,
            index_path=str(index_path)
        )
        
        for i, file_url in enumerate(file_urls):
            if self.stop_check and self.stop_check():
                stats['stopped'] = True
                self._log_progress(
                    f"Stop requested for KB '{kb.name}'",
                    i,
                    len(file_urls),
                )
                break
            try:
                self._log_progress(f"Indexing file {i+1}/{len(file_urls)}", i+1, len(file_urls))
                
                # Check if already indexed and not forcing reindex
                if not force_reindex and not self._needs_indexing(kb_id, file_url):
                    stats['skipped_files'] += 1
                    continue
                
                # Index the file
                file_stats = self._index_single_file(kb_id, file_url, vector_store)
                
                if file_stats['success']:
                    stats['indexed_files'] += 1
                    stats['total_chunks'] += file_stats['chunk_count']
                else:
                    stats['error_files'] += 1
                    stats['errors'].append({
                        'file_url': file_url,
                        'error': file_stats.get('error', 'Unknown error')
                    })
                    
            except Exception as e:
                logger.error(f"Error indexing file {file_url}: {e}")
                stats['error_files'] += 1
                stats['errors'].append({
                    'file_url': file_url,
                    'error': str(e)
                })

        if (
            stats['stopped']
            and stats['indexed_files'] == 0
            and stats['skipped_files'] == 0
            and stats['error_files'] == 0
        ):
            return stats
        
        # Save vector store
        try:
            vector_store.save_index()
            self._log_progress("Saving index to disk", len(file_urls), len(file_urls))
        except Exception as e:
            logger.error(f"Error saving index: {e}")
            raise RAGException(f"Failed to save index: {e}")
        
        # Update KB statistics
        self._update_kb_stats(kb_id)
        
        if stats['stopped']:
            self._log_progress(
                f"Indexing stopped: {stats['indexed_files']} files indexed",
                stats['indexed_files'] + stats['skipped_files'] + stats['error_files'],
                len(file_urls),
            )
        else:
            self._log_progress(
                f"Indexing complete: {stats['indexed_files']} files indexed",
                len(file_urls),
                len(file_urls),
            )
        
        return stats
    
    def _needs_indexing(self, kb_id: str, file_url: str) -> bool:
        """Check if file needs indexing."""
        conn = self.storage._conn
        cursor = conn.execute("""
            SELECT kf.indexed_at, c.markdown_updated_at
            FROM rag_kb_files kf
            LEFT JOIN catalog_items c ON kf.file_url = c.file_url
            WHERE kf.kb_id = ? AND kf.file_url = ?
        """, (kb_id, file_url))
        
        row = cursor.fetchone()
        if not row:
            return True  # Not in KB, needs indexing
        
        indexed_at, markdown_updated_at = row
        
        if not indexed_at:
            return True  # Never indexed
        
        if markdown_updated_at and markdown_updated_at > indexed_at:
            return True  # Markdown updated after last index
        
        return False
    
    def _index_single_file(
        self,
        kb_id: str,
        file_url: str,
        vector_store: VectorStore
    ) -> Dict[str, Any]:
        """
        Index a single file.
        
        Returns dict with success status and statistics.
        """
        try:
            # Get markdown content
            markdown_data = self.storage.get_file_markdown(file_url)
            if not markdown_data or not markdown_data.get('markdown_content'):
                return {
                    'success': False,
                    'error': 'No markdown content found',
                    'chunk_count': 0
                }
            
            markdown_content = markdown_data['markdown_content']
            
            # Get file metadata
            file_info = self._get_file_info(file_url)
            
            # Chunk the markdown
            metadata = {
                'file_url': file_url,
                'title': file_info.get('title', ''),
                'source_site': file_info.get('source_site', ''),
                'kb_id': kb_id
            }
            
            chunks = self.chunker.chunk_document(markdown_content, metadata)
            
            if not chunks:
                return {
                    'success': False,
                    'error': 'No chunks created',
                    'chunk_count': 0
                }
            
            # Generate embeddings
            chunk_texts = [chunk.content for chunk in chunks]
            embeddings = self.embedding_generator.generate_embeddings(chunk_texts)
            
            if len(embeddings) != len(chunks):
                return {
                    'success': False,
                    'error': f'Embedding count mismatch: {len(embeddings)} != {len(chunks)}',
                    'chunk_count': 0
                }
            
            # Prepare vectors and metadata for vector store
            vectors = np.array(embeddings, dtype='float32')
            chunk_metadata = []
            
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                # Calculate embedding hash for change detection
                embedding_hash = hashlib.sha256(
                    np.array(embedding).tobytes()
                ).hexdigest()[:16]
                
                chunk_meta = {
                    'chunk_id': f"{kb_id}:{file_url}:{i}",
                    'kb_id': kb_id,
                    'file_url': file_url,
                    'chunk_index': chunk.chunk_index,
                    'content': chunk.content,
                    'token_count': chunk.token_count,
                    'section_hierarchy': chunk.section_hierarchy,
                    'embedding_hash': embedding_hash,
                    'title': file_info.get('title', ''),
                    'source_site': file_info.get('source_site', '')
                }
                chunk_metadata.append(chunk_meta)
            
            # Add to vector store (INCREMENTAL OPERATION)
            vector_store.add_vectors(vectors, chunk_metadata)
            
            # Store chunks in database for tracking
            self._store_chunks(kb_id, file_url, chunks, embeddings)
            
            # Update file indexing status
            self._update_file_index_status(kb_id, file_url, len(chunks))
            
            return {
                'success': True,
                'chunk_count': len(chunks)
            }
            
        except Exception as e:
            logger.error(f"Error indexing file {file_url}: {e}")
            return {
                'success': False,
                'error': str(e),
                'chunk_count': 0
            }
    
    def _get_file_info(self, file_url: str) -> Dict[str, Any]:
        """Get file metadata from storage."""
        conn = self.storage._conn
        cursor = conn.execute("""
            SELECT title, source_site, content_type
            FROM files
            WHERE url = ?
        """, (file_url,))
        
        row = cursor.fetchone()
        if not row:
            return {}
        
        return {
            'title': row[0] or '',
            'source_site': row[1] or '',
            'content_type': row[2] or ''
        }
    
    def _store_chunks(
        self,
        kb_id: str,
        file_url: str,
        chunks: List[Chunk],
        embeddings: List[List[float]]
    ) -> None:
        """Store chunk metadata in database."""
        conn = self.storage._conn
        timestamp = KnowledgeBase._get_timestamp()
        
        # Delete old chunks for this file in this KB
        conn.execute("""
            DELETE FROM rag_chunks
            WHERE kb_id = ? AND file_url = ?
        """, (kb_id, file_url))
        
        # Insert new chunks
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            embedding_hash = hashlib.sha256(
                np.array(embedding).tobytes()
            ).hexdigest()[:16]
            
            chunk_id = f"{kb_id}:{file_url}:{i}"
            
            conn.execute("""
                INSERT INTO rag_chunks
                (chunk_id, kb_id, file_url, chunk_index, content, token_count,
                 section_hierarchy, embedding_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chunk_id, kb_id, file_url, chunk.chunk_index,
                chunk.content, chunk.token_count,
                chunk.section_hierarchy, embedding_hash, timestamp
            ))
        
        conn.commit()
    
    def _update_file_index_status(
        self,
        kb_id: str,
        file_url: str,
        chunk_count: int
    ) -> None:
        """Update file indexing status in rag_kb_files."""
        conn = self.storage._conn
        timestamp = KnowledgeBase._get_timestamp()
        
        conn.execute("""
            UPDATE rag_kb_files
            SET indexed_at = ?, chunk_count = ?
            WHERE kb_id = ? AND file_url = ?
        """, (timestamp, chunk_count, kb_id, file_url))
        
        # Also update catalog_items
        conn.execute("""
            UPDATE catalog_items
            SET rag_indexed = 1, rag_indexed_at = ?, rag_chunk_count = ?
            WHERE file_url = ?
        """, (timestamp, chunk_count, file_url))
        
        conn.commit()
    
    def _update_kb_stats(self, kb_id: str) -> None:
        """Update knowledge base statistics."""
        conn = self.storage._conn
        timestamp = KnowledgeBase._get_timestamp()
        
        # Count total chunks
        cursor = conn.execute("""
            SELECT COUNT(*)
            FROM rag_chunks
            WHERE kb_id = ?
        """, (kb_id,))
        total_chunks = cursor.fetchone()[0]
        
        # Update KB
        conn.execute("""
            UPDATE rag_knowledge_bases
            SET chunk_count = ?, updated_at = ?
            WHERE kb_id = ?
        """, (total_chunks, timestamp, kb_id))
        
        conn.commit()
    
    def _log_progress(self, message: str, current: int, total: int) -> None:
        """Log progress and call callback if provided."""
        logger.info(f"{message} ({current}/{total})")
        
        if self.progress_callback:
            try:
                self.progress_callback(message, current, total)
            except Exception as e:
                logger.error(f"Error in progress callback: {e}")


# Import at bottom to avoid circular dependency
from ai_actuarial.rag.knowledge_base import KnowledgeBase
