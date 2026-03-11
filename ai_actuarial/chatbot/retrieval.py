"""
RAG retrieval integration for chatbot.

Integrates with the existing RAG system to retrieve relevant chunks
from knowledge bases, generate citations, and handle multi-KB queries.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
import numpy as np

from ai_actuarial.ai_runtime import infer_embedding_dimension, infer_embedding_provider
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.rag.embeddings import EmbeddingGenerator
from ai_actuarial.rag.vector_store import VectorStore
from ai_actuarial.storage import Storage
from ai_actuarial.chatbot.config import ChatbotConfig
from ai_actuarial.chatbot.exceptions import (
    RetrievalException,
    InvalidKBException,
    NoResultsException,
    EmbeddingConfigurationMismatchException,
)

logger = logging.getLogger(__name__)


class RAGRetriever:
    """
    RAG retrieval component for chatbot.
    
    Retrieves relevant chunks from knowledge bases, generates citations,
    and supports multi-KB queries with result ranking and deduplication.
    """
    
    def __init__(
        self,
        storage: Storage,
        config: Optional[ChatbotConfig] = None
    ):
        """
        Initialize RAG retriever.
        
        Args:
            storage: Storage instance for database access
            config: Chatbot configuration
        """
        self.storage = storage
        self.config = config or ChatbotConfig.from_config(storage=storage)
        
        # Initialize RAG components
        self.kb_manager = KnowledgeBaseManager(storage)
        self.embedding_generator = EmbeddingGenerator(storage=self.storage)
        
        # Cache for loaded vector stores
        self._vector_store_cache: Dict[str, VectorStore] = {}

    def get_current_embedding_metadata(self) -> Dict[str, Any]:
        """Return the current query embedding runtime used by chat retrieval."""
        return {
            "provider": str(self.embedding_generator.provider or "openai").strip().lower() or "openai",
            "model": str(self.embedding_generator.config.embedding_model or "text-embedding-3-large").strip() or "text-embedding-3-large",
            "dimension": self.embedding_generator.get_embedding_dimension(),
        }
    
    def retrieve(
        self,
        query: str,
        kb_ids: Optional[Union[str, List[str]]] = None,
        top_k: Optional[int] = None,
        threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant chunks for a query.
        
        Args:
            query: User's question
            kb_ids: Single KB ID, list of KB IDs, or None for all KBs
            top_k: Number of results to return (default: config.top_k)
            threshold: Similarity threshold (default: config.similarity_threshold)
        
        Returns:
            List of retrieved chunks with metadata and citations
            Each chunk dict contains:
            - content: The chunk text
            - metadata: Dict with filename, kb_id, kb_name, similarity_score, etc.
        
        Raises:
            RetrievalException: If retrieval fails
            InvalidKBException: If KB ID is invalid
            NoResultsException: If no results above threshold
        """
        top_k = top_k or self.config.top_k
        threshold = threshold or self.config.similarity_threshold
        
        try:
            # Normalize KB IDs
            if kb_ids is None:
                # Get all KB IDs
                all_kbs = self.kb_manager.list_kbs()
                kb_ids = [kb.kb_id for kb in all_kbs]
                if not kb_ids:
                    raise RetrievalException("No knowledge bases available")
            elif isinstance(kb_ids, str):
                kb_ids = [kb_ids]
            
            # Validate KB IDs exist
            for kb_id in kb_ids:
                kb = self.kb_manager.get_kb(kb_id)
                if not kb:
                    raise InvalidKBException(f"Knowledge base '{kb_id}' not found")
            
            current_embedding = self.get_current_embedding_metadata()
            for kb_id in kb_ids:
                kb = self.kb_manager.get_kb(kb_id)
                if not kb:
                    raise InvalidKBException(f"Knowledge base '{kb_id}' not found")
                self._ensure_kb_embedding_compatibility(kb, current_embedding)

            # Generate query embedding
            logger.info(f"Generating embedding for query: {query[:100]}...")
            query_embedding = self.embedding_generator.generate_single(query)
            query_vector = np.array(query_embedding)
            
            # Retrieve from each KB
            if len(kb_ids) == 1:
                # Single KB query
                results = self._retrieve_from_kb(kb_ids[0], query_vector, top_k, threshold)
            else:
                # Multi-KB query with diversity enforcement
                results = self._retrieve_from_multiple_kbs(
                    kb_ids, query_vector, top_k, threshold
                )
            
            if not results:
                raise NoResultsException(
                    f"No results found above similarity threshold {threshold}"
                )
            
            logger.info(f"Retrieved {len(results)} chunks from {len(kb_ids)} KB(s)")
            return results
            
        except (InvalidKBException, NoResultsException, EmbeddingConfigurationMismatchException):
            raise
        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            raise RetrievalException(f"Retrieval failed: {e}")
    
    def _retrieve_from_kb(
        self,
        kb_id: str,
        query_vector: np.ndarray,
        top_k: int,
        threshold: float
    ) -> List[Dict[str, Any]]:
        """Retrieve chunks from a single KB."""
        # Get KB info
        kb = self.kb_manager.get_kb(kb_id)
        if not kb:
            raise InvalidKBException(f"Knowledge base '{kb_id}' not found")
        
        # Load vector store
        vector_store = self._get_vector_store(kb_id)
        
        # Search
        search_results = vector_store.search(
            query_vector,
            k=top_k,
            similarity_threshold=threshold
        )
        
        # Format results with citations
        formatted_results = []
        for result in search_results:
            metadata = result['metadata']
            
            # Skip deleted entries
            if metadata.get('_deleted', False):
                continue
            
            formatted_results.append({
                'content': metadata.get('content', ''),
                'metadata': {
                    'filename': metadata.get('filename', 'unknown'),
                    'kb_id': kb_id,
                    'kb_name': kb.name,
                    'similarity_score': result['score'],
                    'chunk_id': metadata.get('chunk_id', ''),
                    'file_url': metadata.get('file_url', ''),
                }
            })
        
        return formatted_results
    
    def _retrieve_from_multiple_kbs(
        self,
        kb_ids: List[str],
        query_vector: np.ndarray,
        top_k: int,
        threshold: float
    ) -> List[Dict[str, Any]]:
        """
        Retrieve chunks from multiple KBs with diversity enforcement.
        
        Strategy:
        1. Retrieve from each KB
        2. Deduplicate similar chunks
        3. Rank with diversity bonus
        4. Ensure minimum representation from each KB
        """
        # Retrieve from each KB (get more than top_k per KB for diversity)
        per_kb_k = max(top_k, self.config.min_results_per_kb * len(kb_ids))
        all_results: Dict[str, List[Dict[str, Any]]] = {}
        
        for kb_id in kb_ids:
            try:
                results = self._retrieve_from_kb(kb_id, query_vector, per_kb_k, threshold)
                if results:
                    all_results[kb_id] = results
            except Exception as e:
                logger.warning(f"Failed to retrieve from KB '{kb_id}': {e}")
                continue
        
        if not all_results:
            return []
        
        # Flatten all results
        flat_results = []
        for kb_id, results in all_results.items():
            flat_results.extend(results)
        
        # Deduplicate by content similarity
        unique_results = self._deduplicate_chunks(flat_results)
        
        # Re-rank with diversity bonus
        ranked_results = self._rank_with_diversity(unique_results, all_results.keys())
        
        # Ensure minimum representation from each KB
        balanced_results = self._ensure_kb_diversity(
            ranked_results,
            all_results,
            min_per_kb=self.config.min_results_per_kb
        )
        
        return balanced_results[:top_k]
    
    def _deduplicate_chunks(
        self,
        chunks: List[Dict[str, Any]],
        similarity_threshold: float = 0.95
    ) -> List[Dict[str, Any]]:
        """
        Deduplicate chunks with very similar content.
        
        Uses simple string similarity for MVP.
        """
        if not chunks:
            return []
        
        unique_chunks = []
        seen_contents = []
        
        for chunk in chunks:
            content = chunk['content']
            
            # Check if similar to any seen content
            is_duplicate = False
            for seen_content in seen_contents:
                # Simple similarity: ratio of matching characters
                if self._string_similarity(content, seen_content) > similarity_threshold:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_chunks.append(chunk)
                seen_contents.append(content)
        
        logger.info(f"Deduplicated {len(chunks)} chunks to {len(unique_chunks)}")
        return unique_chunks
    
    def _string_similarity(self, s1: str, s2: str) -> float:
        """Calculate simple string similarity (0-1)."""
        if not s1 or not s2:
            return 0.0
        
        # Simple approach: check if one is substring of other
        shorter = s1 if len(s1) < len(s2) else s2
        longer = s2 if len(s1) < len(s2) else s1
        
        if shorter in longer:
            return len(shorter) / len(longer)
        
        # Otherwise, use set-based similarity
        set1 = set(s1.split())
        set2 = set(s2.split())
        
        if not set1 or not set2:
            return 0.0
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0
    
    def _rank_with_diversity(
        self,
        chunks: List[Dict[str, Any]],
        kb_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Re-rank chunks with diversity bonus.
        
        Boosts chunks from underrepresented KBs.
        """
        # Count chunks per KB
        kb_counts = {kb_id: 0 for kb_id in kb_ids}
        for chunk in chunks:
            kb_id = chunk['metadata']['kb_id']
            kb_counts[kb_id] = kb_counts.get(kb_id, 0) + 1
        
        # Calculate diversity bonus for each chunk
        ranked_chunks = []
        for chunk in chunks:
            kb_id = chunk['metadata']['kb_id']
            base_score = chunk['metadata']['similarity_score']
            
            # Diversity bonus: boost underrepresented KBs
            kb_count = kb_counts[kb_id]
            diversity_bonus = self.config.kb_diversity_weight * (1.0 / (1.0 + kb_count))
            
            final_score = base_score + diversity_bonus
            
            # Store original and final scores
            chunk['metadata']['original_score'] = base_score
            chunk['metadata']['diversity_bonus'] = diversity_bonus
            chunk['metadata']['similarity_score'] = min(final_score, 1.0)  # Cap at 1.0
            
            ranked_chunks.append(chunk)
        
        # Sort by final score
        ranked_chunks.sort(
            key=lambda x: x['metadata']['similarity_score'],
            reverse=True
        )
        
        return ranked_chunks
    
    def _ensure_kb_diversity(
        self,
        chunks: List[Dict[str, Any]],
        results_by_kb: Dict[str, List[Dict[str, Any]]],
        min_per_kb: int
    ) -> List[Dict[str, Any]]:
        """
        Ensure minimum representation from each KB.
        
        If a KB has fewer than min_per_kb chunks in top results,
        add more from that KB.
        """
        # Count chunks per KB in current results
        kb_counts = {}
        for chunk in chunks:
            kb_id = chunk['metadata']['kb_id']
            kb_counts[kb_id] = kb_counts.get(kb_id, 0) + 1
        
        # Check each KB for minimum representation
        balanced_chunks = list(chunks)
        added_chunk_ids = {chunk['metadata'].get('chunk_id', id(chunk)) for chunk in chunks}
        
        for kb_id, kb_results in results_by_kb.items():
            current_count = kb_counts.get(kb_id, 0)
            
            if current_count < min_per_kb:
                # Add more chunks from this KB
                needed = min_per_kb - current_count
                
                for chunk in kb_results:
                    chunk_id = chunk['metadata'].get('chunk_id', id(chunk))
                    if chunk_id not in added_chunk_ids:
                        balanced_chunks.append(chunk)
                        added_chunk_ids.add(chunk_id)
                        needed -= 1
                        
                        if needed <= 0:
                            break
        
        # Re-sort by score
        balanced_chunks.sort(
            key=lambda x: x['metadata']['similarity_score'],
            reverse=True
        )
        
        return balanced_chunks
    
    def _get_vector_store(self, kb_id: str) -> VectorStore:
        """Get or load vector store for a KB."""
        if kb_id in self._vector_store_cache:
            return self._vector_store_cache[kb_id]
        
        # Get KB info
        kb = self.kb_manager.get_kb(kb_id)
        if not kb:
            raise InvalidKBException(f"Knowledge base '{kb_id}' not found")
        
        # Get index path from database
        cursor = self.storage._conn.execute("""
            SELECT index_path FROM rag_knowledge_bases WHERE kb_id = ?
        """, (kb_id,))
        row = cursor.fetchone()
        
        if not row or not row[0]:
            raise RetrievalException(f"No index found for KB '{kb_id}'")
        
        index_path = Path(row[0])
        
        if not index_path.exists():
            raise RetrievalException(
                f"Index file not found for KB '{kb_id}': {index_path}"
            )
        
        # Load vector store
        composition = self.storage.get_kb_composition_status(kb_id)
        latest_index = composition.get("latest_index") if isinstance(composition, dict) else None
        dimension = None
        if isinstance(latest_index, dict):
            dimension = latest_index.get("embedding_dimension")
        if dimension in (None, ""):
            dimension = getattr(kb, "embedding_dimension", None) or infer_embedding_dimension(kb.embedding_model)
        if dimension in (None, ""):
            raise RetrievalException(f"Unable to determine index dimension for KB '{kb_id}'")

        vector_store = VectorStore(
            dimension=int(dimension),
            index_path=str(index_path)
        )
        
        # Cache for future use
        self._vector_store_cache[kb_id] = vector_store
        
        return vector_store
    
    def _ensure_kb_embedding_compatibility(
        self,
        kb,
        current_embedding: Dict[str, Any],
    ) -> None:
        """Fail fast when a KB index was built with a different embedding runtime."""
        composition = self.storage.get_kb_composition_status(kb.kb_id)
        latest_index = composition.get("latest_index") if isinstance(composition, dict) else None

        index_provider = None
        index_model = None
        index_dimension = None
        if isinstance(latest_index, dict):
            index_provider = latest_index.get("embedding_provider")
            index_model = latest_index.get("embedding_model")
            index_dimension = latest_index.get("embedding_dimension")

        if not index_provider:
            index_provider = getattr(kb, "embedding_provider", None) or infer_embedding_provider(
                kb.embedding_model,
                fallback=current_embedding.get("provider"),
            )
        if not index_model:
            index_model = kb.embedding_model
        if index_dimension in (None, ""):
            index_dimension = getattr(kb, "embedding_dimension", None) or infer_embedding_dimension(index_model)

        current_provider = str(current_embedding.get("provider") or "").strip().lower()
        current_model = str(current_embedding.get("model") or "").strip()
        current_dimension = current_embedding.get("dimension")

        mismatch = False
        if index_provider and current_provider and str(index_provider).strip().lower() != current_provider:
            mismatch = True
        if index_model and current_model and str(index_model).strip() != current_model:
            mismatch = True
        if index_dimension not in (None, "") and current_dimension not in (None, ""):
            mismatch = mismatch or int(index_dimension) != int(current_dimension)

        if mismatch:
            raise EmbeddingConfigurationMismatchException(
                "Knowledge base index is incompatible with the current embedding configuration. Rebuild the KB index before querying it.",
                kb_id=kb.kb_id,
                current_provider=current_provider,
                current_model=current_model,
                current_dimension=int(current_dimension) if current_dimension not in (None, "") else None,
                index_provider=str(index_provider).strip().lower() if index_provider else None,
                index_model=str(index_model).strip() if index_model else None,
                index_dimension=int(index_dimension) if index_dimension not in (None, "") else None,
                needs_reindex=True,
            )
    
    def generate_citations(
        self,
        chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Generate citation information from retrieved chunks.
        
        Args:
            chunks: List of retrieved chunks
        
        Returns:
            List of citation dicts with:
            - filename: Source filename
            - kb_id: Knowledge base ID
            - kb_name: Knowledge base name
            - chunk_id: Chunk identifier
            - similarity_score: Relevance score
        """
        citations = []
        
        for chunk in chunks:
            metadata = chunk.get('metadata', {})
            
            citation = {
                'filename': metadata.get('filename', 'unknown'),
                'kb_id': metadata.get('kb_id', ''),
                'kb_name': metadata.get('kb_name', ''),
                'chunk_id': metadata.get('chunk_id', ''),
                'similarity_score': metadata.get('similarity_score', 0.0),
                'file_url': metadata.get('file_url', ''),
            }
            
            citations.append(citation)
        
        return citations
    
    def clear_cache(self):
        """Clear vector store cache."""
        self._vector_store_cache.clear()
