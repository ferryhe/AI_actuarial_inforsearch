"""
FAISS-based vector store for RAG system.

Supports:
- Index creation and management
- Incremental additions (high priority feature)
- Similarity search with threshold filtering
- Metadata storage and retrieval
- Index persistence
"""

import json
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

try:
    import faiss
except ImportError:
    raise ImportError(
        "faiss-cpu not installed. Install with: pip install faiss-cpu"
    )

from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.rag.exceptions import VectorStoreException


class VectorStore:
    """
    FAISS-based vector store with incremental update support.
    
    Critical feature: Supports adding new vectors without full rebuild.
    """
    
    def __init__(
        self,
        dimension: int,
        config: Optional[RAGConfig] = None,
        index_path: Optional[str] = None
    ):
        """
        Initialize vector store.
        
        Args:
            dimension: Embedding vector dimension
            config: RAG configuration
            index_path: Path to save/load index (optional)
        """
        self.dimension = dimension
        self.config = config or RAGConfig.from_env()
        self.index_path = Path(index_path) if index_path else None
        
        # Create or load FAISS index
        if self.index_path and self.index_path.exists():
            self.index = self.load_index()
            self.metadata = self.load_metadata()
        else:
            self.index = self._create_index()
            self.metadata = []
    
    def _create_index(self) -> faiss.Index:
        """
        Create a new FAISS index.
        
        Uses IndexFlatL2 for exact search (can be upgraded to IVF/HNSW for scale).
        """
        if self.config.index_type == "Flat":
            # Exact search with L2 distance
            index = faiss.IndexFlatL2(self.dimension)
        elif self.config.index_type == "IVF":
            # Inverted file index for faster search (approximate)
            quantizer = faiss.IndexFlatL2(self.dimension)
            n_clusters = 100  # Can be tuned
            index = faiss.IndexIVFFlat(quantizer, self.dimension, n_clusters)
        elif self.config.index_type == "HNSW":
            # Hierarchical Navigable Small World graph
            index = faiss.IndexHNSWFlat(self.dimension, 32)
        else:
            raise VectorStoreException(f"Unknown index type: {self.config.index_type}")
        
        return index
    
    def add_vectors(
        self,
        vectors: np.ndarray,
        metadata: List[Dict[str, Any]]
    ) -> None:
        """
        Add vectors to the index (INCREMENTAL OPERATION).
        
        This is a high-priority feature that enables adding new documents
        without rebuilding the entire index.
        
        Args:
            vectors: Numpy array of shape (n_vectors, dimension)
            metadata: List of metadata dicts (one per vector)
            
        Raises:
            VectorStoreException: If add operation fails
        """
        if len(vectors) != len(metadata):
            raise VectorStoreException(
                f"Vectors and metadata length mismatch: {len(vectors)} != {len(metadata)}"
            )
        
        if vectors.shape[1] != self.dimension:
            raise VectorStoreException(
                f"Vector dimension mismatch: {vectors.shape[1]} != {self.dimension}"
            )
        
        try:
            # Convert to float32 (FAISS requirement)
            vectors = vectors.astype('float32')
            
            # Train index if needed (for IVF)
            if hasattr(self.index, 'is_trained') and not self.index.is_trained:
                self.index.train(vectors)
            
            # Add vectors to index (incremental operation)
            self.index.add(vectors)
            
            # Store metadata
            self.metadata.extend(metadata)
            
        except Exception as e:
            raise VectorStoreException(f"Failed to add vectors: {e}")
    
    def search(
        self,
        query_vector: np.ndarray,
        k: int = 10,
        similarity_threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors.
        
        Args:
            query_vector: Query embedding vector
            k: Number of results to return
            similarity_threshold: Optional threshold to filter results (0-1)
            
        Returns:
            List of results with metadata and scores
        """
        if query_vector.shape[0] != self.dimension:
            raise VectorStoreException(
                f"Query vector dimension mismatch: {query_vector.shape[0]} != {self.dimension}"
            )
        
        try:
            # Reshape for FAISS
            query_vector = query_vector.reshape(1, -1).astype('float32')
            
            # Search
            distances, indices = self.index.search(query_vector, k)
            
            # Convert distances to similarity scores (L2 distance to cosine-like score)
            # Lower distance = higher similarity
            # Normalize to 0-1 range approximately
            max_distance = np.max(distances) if np.max(distances) > 0 else 1.0
            similarities = 1.0 - (distances / (max_distance + 1e-8))
            
            # Build results
            results = []
            for idx, score in zip(indices[0], similarities[0]):
                if idx < len(self.metadata):  # Valid index
                    # Apply threshold if specified
                    if similarity_threshold is None or score >= similarity_threshold:
                        result = {
                            'metadata': self.metadata[idx],
                            'score': float(score),
                            'distance': float(distances[0][len(results)]),
                            'index': int(idx)
                        }
                        results.append(result)
            
            return results
            
        except Exception as e:
            raise VectorStoreException(f"Search failed: {e}")
    
    def remove_vectors(self, indices: List[int]) -> None:
        """
        Remove vectors from index.
        
        Note: FAISS doesn't support efficient deletion. This marks metadata as deleted
        and requires index rebuild for actual removal.
        
        Args:
            indices: List of vector indices to remove
        """
        # Mark metadata as deleted
        for idx in indices:
            if idx < len(self.metadata):
                self.metadata[idx]['_deleted'] = True
    
    def rebuild_without_deleted(self) -> None:
        """
        Rebuild index excluding deleted vectors.
        
        This is needed periodically to reclaim space from deleted vectors.
        """
        # Collect non-deleted vectors and metadata
        valid_indices = [
            i for i, meta in enumerate(self.metadata)
            if not meta.get('_deleted', False)
        ]
        
        if not valid_indices:
            # All deleted, create fresh index
            self.index = self._create_index()
            self.metadata = []
            return
        
        # Extract vectors (reconstruct from index if possible)
        # For IndexFlat, can use reconstruct()
        if hasattr(self.index, 'reconstruct'):
            vectors = np.array([
                self.index.reconstruct(i) for i in valid_indices
            ])
            new_metadata = [self.metadata[i] for i in valid_indices]
            
            # Create new index
            self.index = self._create_index()
            self.metadata = []
            
            # Add valid vectors
            self.add_vectors(vectors, new_metadata)
        else:
            raise VectorStoreException(
                "Index type doesn't support reconstruction. "
                "Manual rebuild required."
            )
    
    def save_index(self, path: Optional[Path] = None) -> None:
        """
        Save FAISS index to disk.
        
        Args:
            path: Path to save index (defaults to self.index_path)
        """
        save_path = path or self.index_path
        if not save_path:
            raise VectorStoreException("No index path specified for saving")
        
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Save FAISS index
            faiss.write_index(self.index, str(save_path))
            
            # Save metadata separately
            metadata_path = save_path.with_suffix('.meta.pkl')
            with open(metadata_path, 'wb') as f:
                pickle.dump(self.metadata, f)
                
        except Exception as e:
            raise VectorStoreException(f"Failed to save index: {e}")
    
    def load_index(self, path: Optional[Path] = None) -> faiss.Index:
        """
        Load FAISS index from disk.
        
        Args:
            path: Path to load index from (defaults to self.index_path)
            
        Returns:
            Loaded FAISS index
        """
        load_path = path or self.index_path
        if not load_path:
            raise VectorStoreException("No index path specified for loading")
        
        load_path = Path(load_path)
        if not load_path.exists():
            raise VectorStoreException(f"Index file not found: {load_path}")
        
        try:
            index = faiss.read_index(str(load_path))
            return index
        except Exception as e:
            raise VectorStoreException(f"Failed to load index: {e}")
    
    def load_metadata(self, path: Optional[Path] = None) -> List[Dict[str, Any]]:
        """
        Load metadata from disk.
        
        Args:
            path: Path to load metadata from (defaults to index_path.meta.pkl)
            
        Returns:
            List of metadata dicts
        """
        if path:
            metadata_path = Path(path)
        elif self.index_path:
            metadata_path = self.index_path.with_suffix('.meta.pkl')
        else:
            raise VectorStoreException("No metadata path specified")
        
        if not metadata_path.exists():
            return []
        
        try:
            with open(metadata_path, 'rb') as f:
                metadata = pickle.load(f)
            return metadata
        except Exception as e:
            raise VectorStoreException(f"Failed to load metadata: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get vector store statistics.
        
        Returns:
            Dict with statistics
        """
        active_count = sum(
            1 for meta in self.metadata
            if not meta.get('_deleted', False)
        )
        
        return {
            'total_vectors': self.index.ntotal,
            'active_vectors': active_count,
            'deleted_vectors': len(self.metadata) - active_count,
            'dimension': self.dimension,
            'index_type': self.config.index_type,
            'is_trained': getattr(self.index, 'is_trained', True)
        }
    
    def clear(self) -> None:
        """Clear all vectors and metadata."""
        self.index = self._create_index()
        self.metadata = []


def create_vector_store(
    dimension: int,
    index_path: str,
    config: Optional[RAGConfig] = None
) -> VectorStore:
    """
    Factory function to create a vector store.
    
    Args:
        dimension: Embedding dimension
        index_path: Path for index storage
        config: Optional RAG configuration
        
    Returns:
        VectorStore instance
    """
    return VectorStore(dimension, config, index_path)
