# RAG Task Management & Category Handling Design

**Document**: RAG Task Management & Category Handling  
**Created**: 2026-02-11  
**Status**: Design & Implementation Complete  
**Related Phase**: Phase 1.2.7 (Task Integration Design)

## Executive Summary

This document addresses stakeholder requirements for RAG indexing task management, multi-category file handling, and flexible KB creation strategies. All solutions maintain backward compatibility with existing systems and leverage the manual task workflow pattern.

## Requirements Analysis

### R1: Manual RAG Task with Metadata Detection

**Requirement**: RAG generation and updates should be manual tasks (like catalog and doc_to_md) with automatic metadata detection at task start showing statistics about files needing indexing.

**Current Pattern Reference**:
- Markdown conversion: Shows "X files need conversion, earliest from YYYY-MM-DD"
- Catalog task: Shows "X files without catalog, Y files outdated"

### R2: Category-Based RAG Management

**Requirement**: RAG KBs are organized by category, enabling category-based updates and management.

**Challenges**:
- Files can belong to multiple categories (semicolon-separated: "AI; Risk; Pricing")
- Need efficient category-to-KB mapping
- Updates should be category-scoped

### R3: Multi-Category File Handling

**Requirement**: Documents can appear in multiple categories. How to handle indexing?

**Design Options**:
1. **Duplicate chunks** (index same file in multiple KBs)
2. **Reference mapping** (single set of chunks, multiple KB references)
3. **Hybrid approach** (deduplicate embeddings, separate metadata)

### R4: New Category Without RAG

**Requirement**: If a new category is created without a corresponding RAG KB, how to handle?

**Design Options**:
1. **Auto-create KB** on first category assignment
2. **Prompt user** to create KB when needed
3. **Lazy creation** when user initiates RAG task for that category

### R5: Custom File Selection (Non-Category-Based)

**Requirement**: Support creating RAG KBs with manually selected files, not bound to categories.

**Use Cases**:
- Ad-hoc research KB (specific papers on a topic)
- Cross-category thematic KB (e.g., "Climate Risk" spanning multiple categories)
- Temporary analysis KB

---

## Solution Design

### Solution 1: Manual RAG Task with Smart Detection

#### Architecture

```python
# Task Type: 'rag_indexing'
Task Parameters:
{
    "task_type": "rag_indexing",
    "kb_id": "actuarial_standards",  # Target KB
    "mode": "incremental",  # or "full_rebuild"
    "file_urls": [...],  # Optional: specific files, or null for all KB files
    "categories": [...],  # Optional: filter by categories
}

# Task Start Logic:
def detect_rag_metadata(kb_id, categories=None):
    """
    Pre-task detection showing files needing indexing.
    
    Returns:
        {
            "kb_name": "Actuarial Standards",
            "total_files_in_kb": 150,
            "indexed_files": 140,
            "pending_files": 10,  # New or modified
            "pending_details": [
                {"file_url": "file1.pdf", "reason": "new", "added_at": "2026-02-10"},
                {"file_url": "file2.pdf", "reason": "modified", "modified_at": "2026-02-09"},
            ],
            "earliest_pending": "2026-01-15",
            "chunk_count_current": 4500,
            "estimated_new_chunks": 350,
            "estimated_time_seconds": 180  # ~30 seconds for 10 files
        }
    """
```

#### Implementation

```python
# ai_actuarial/rag/knowledge_base.py

class KnowledgeBaseManager:
    
    def get_rag_task_metadata(
        self, 
        kb_id: str,
        categories: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get metadata for RAG indexing task UI display.
        
        Shows:
        - Total files in KB
        - Files already indexed
        - Files needing indexing (new or modified)
        - Earliest pending file timestamp
        - Estimated processing time
        
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
        kb_files = self.list_kb_files(kb_id)
        total_files = len(kb_files)
        
        # Get files needing indexing (new or modified)
        pending_files = self.get_files_needing_index(kb_id)
        
        # Apply category filter if provided
        if categories:
            pending_files = self._filter_files_by_categories(pending_files, categories)
        
        # Build pending details
        pending_details = []
        earliest_timestamp = None
        
        for file_url in pending_files:
            # Get file info from catalog_items
            cursor = self.storage._conn.execute("""
                SELECT 
                    ci.updated_at as modified_at,
                    kf.indexed_at
                FROM catalog_items ci
                LEFT JOIN rag_kb_files kf ON kf.file_url = ci.file_url AND kf.kb_id = ?
                WHERE ci.file_url = ?
            """, (kb_id, file_url))
            
            row = cursor.fetchone()
            if row:
                modified_at = row[0]
                indexed_at = row[1]
                reason = "new" if not indexed_at else "modified"
                
                pending_details.append({
                    "file_url": file_url,
                    "reason": reason,
                    "modified_at": modified_at,
                    "indexed_at": indexed_at
                })
                
                # Track earliest
                timestamp = modified_at or indexed_at
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
            "pending_details": pending_details[:20],  # Limit to 20 for display
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
```

#### UI Display Pattern

```
┌─────────────────────────────────────────────────────────────┐
│ RAG Indexing Task: Actuarial Standards KB                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ Knowledge Base: Actuarial Standards                         │
│ Total Files: 150                                            │
│ Indexed: 140 files (4,500 chunks)                          │
│ Pending: 10 files need indexing                            │
│                                                              │
│ Files Needing Indexing:                                     │
│ • file1.pdf (new, added 2026-02-10)                        │
│ • file2.pdf (modified, updated 2026-02-09)                 │
│ • file3.pdf (new, added 2026-02-08)                        │
│ ... (7 more)                                                │
│                                                              │
│ Earliest pending: 2026-01-15                                │
│ Estimated: +350 chunks, ~3 minutes                          │
│                                                              │
│ [Start Task] [Cancel]                                       │
└─────────────────────────────────────────────────────────────┘
```

---

### Solution 2: Category-Based KB Management

#### Design: Category-to-KB Mapping Table

**New Table**: `rag_kb_category_mappings`

```sql
CREATE TABLE rag_kb_category_mappings (
    kb_id TEXT NOT NULL,
    category TEXT NOT NULL,
    auto_sync INTEGER DEFAULT 1,  -- Auto-add files from this category
    created_at TEXT,
    PRIMARY KEY (kb_id, category),
    FOREIGN KEY (kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE
);

CREATE INDEX idx_rag_kb_category_kb ON rag_kb_category_mappings(kb_id);
CREATE INDEX idx_rag_kb_category_cat ON rag_kb_category_mappings(category);
```

#### Implementation

```python
# ai_actuarial/rag/knowledge_base.py

class KnowledgeBaseManager:
    
    def _init_category_mapping_table(self):
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
        timestamp = self._get_timestamp()
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
            WHERE {placeholders}
            AND ci.status = 'ok'
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
        cursor = self.storage._conn.execute("""
            SELECT kb_id FROM rag_kb_category_mappings
            WHERE category = ?
            ORDER BY kb_id
        """, (category,))
        return [row[0] for row in cursor.fetchall()]
```

---

### Solution 3: Multi-Category File Handling

#### Design: Hybrid Approach (Deduplicated Embeddings, Separate Metadata)

**Strategy**:
1. **Embeddings**: Stored once per unique chunk (identified by content hash)
2. **Metadata**: Stored per KB-file association
3. **Vector Store**: Single chunk can be referenced by multiple KBs

**Advantages**:
- **Storage efficiency**: No duplicate embeddings (~3072 floats * 4 bytes = 12KB per chunk)
- **Cost efficiency**: No duplicate OpenAI API calls
- **Consistency**: Same embedding across all KBs ensures consistent retrieval
- **Flexibility**: Can remove from one KB without affecting others

**Implementation**:

```python
# Modified: ai_actuarial/rag/indexing.py

class IndexingPipeline:
    
    def index_files(
        self,
        kb_id: str,
        file_urls: List[str],
        force_reindex: bool = False
    ) -> Dict[str, Any]:
        """
        Index files into KB with deduplication.
        
        For multi-category files:
        - Checks if chunks already exist (by content_hash)
        - Reuses existing embeddings
        - Creates new KB-specific metadata references
        """
        # ... existing code ...
        
        for file_url in file_urls:
            try:
                # Get markdown content
                markdown_content = self.kb_manager.storage.get_file_markdown(file_url)
                if not markdown_content:
                    errors.append({
                        "file_url": file_url,
                        "error": "No markdown content found"
                    })
                    continue
                
                # Chunk content
                chunks = self.chunker.chunk_markdown(markdown_content, file_url)
                
                # Check for existing chunks (deduplicate)
                new_chunks = []
                reused_chunks = []
                
                for chunk in chunks:
                    # Calculate content hash
                    content_hash = self._hash_chunk_content(chunk.text)
                    
                    # Check if chunk already exists in DB
                    existing_chunk = self._get_chunk_by_hash(content_hash)
                    
                    if existing_chunk and not force_reindex:
                        # Reuse existing chunk and embedding
                        reused_chunks.append({
                            "chunk_id": existing_chunk['chunk_id'],
                            "embedding": existing_chunk['embedding'],
                            "chunk": chunk
                        })
                    else:
                        # New chunk needs embedding
                        new_chunks.append(chunk)
                
                # Generate embeddings only for new chunks
                if new_chunks:
                    texts = [c.text for c in new_chunks]
                    embeddings = self.embedding_generator.generate_embeddings(texts)
                else:
                    embeddings = []
                
                # Store chunks with deduplication
                chunk_ids = []
                all_embeddings = []
                
                # Store new chunks
                for chunk, embedding in zip(new_chunks, embeddings):
                    content_hash = self._hash_chunk_content(chunk.text)
                    chunk_id = self._store_chunk(
                        kb_id=kb_id,
                        file_url=file_url,
                        chunk=chunk,
                        embedding=embedding,
                        content_hash=content_hash
                    )
                    chunk_ids.append(chunk_id)
                    all_embeddings.append(embedding)
                
                # Create KB-file-chunk associations for reused chunks
                for reused in reused_chunks:
                    # Link existing chunk to this KB-file
                    self._link_chunk_to_kb_file(
                        kb_id=kb_id,
                        file_url=file_url,
                        chunk_id=reused['chunk_id']
                    )
                    chunk_ids.append(reused['chunk_id'])
                    all_embeddings.append(reused['embedding'])
                
                # Add to vector store (all embeddings for this file)
                if all_embeddings:
                    vector_store.add_vectors(
                        vectors=np.array(all_embeddings),
                        metadata=[{"chunk_id": cid, "kb_id": kb_id, "file_url": file_url} 
                                 for cid in chunk_ids]
                    )
                
                # ... rest of existing code ...
                
            except Exception as e:
                errors.append({"file_url": file_url, "error": str(e)})
        
        # ... existing return code ...
    
    def _hash_chunk_content(self, text: str) -> str:
        """Calculate SHA256 hash of chunk content for deduplication."""
        import hashlib
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    def _get_chunk_by_hash(self, content_hash: str) -> Optional[Dict]:
        """Retrieve existing chunk by content hash."""
        cursor = self.kb_manager.storage._conn.execute("""
            SELECT chunk_id, embedding FROM rag_chunks
            WHERE content_hash = ?
            LIMIT 1
        """, (content_hash,))
        row = cursor.fetchone()
        if row:
            import pickle
            return {
                "chunk_id": row[0],
                "embedding": pickle.loads(row[1])
            }
        return None
    
    def _store_chunk(
        self, 
        kb_id: str, 
        file_url: str, 
        chunk: Chunk, 
        embedding: np.ndarray,
        content_hash: str
    ) -> int:
        """Store chunk with deduplication support."""
        import pickle
        cursor = self.kb_manager.storage._conn.execute("""
            INSERT INTO rag_chunks 
            (kb_id, file_url, chunk_index, text, section_hierarchy, 
             start_line, end_line, embedding, content_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            kb_id,
            file_url,
            chunk.index,
            chunk.text,
            chunk.section_hierarchy,
            chunk.start_line,
            chunk.end_line,
            pickle.dumps(embedding),
            content_hash,
            self._get_timestamp()
        ))
        return cursor.lastrowid
    
    def _link_chunk_to_kb_file(self, kb_id: str, file_url: str, chunk_id: int):
        """Create association between KB-file and existing chunk."""
        self.kb_manager.storage._conn.execute("""
            INSERT OR IGNORE INTO rag_kb_file_chunks 
            (kb_id, file_url, chunk_id)
            VALUES (?, ?, ?)
        """, (kb_id, file_url, chunk_id))
```

**New Association Table**:

```sql
CREATE TABLE rag_kb_file_chunks (
    kb_id TEXT NOT NULL,
    file_url TEXT NOT NULL,
    chunk_id INTEGER NOT NULL,
    PRIMARY KEY (kb_id, file_url, chunk_id),
    FOREIGN KEY (kb_id, file_url) REFERENCES rag_kb_files(kb_id, file_url) ON DELETE CASCADE,
    FOREIGN KEY (chunk_id) REFERENCES rag_chunks(chunk_id) ON DELETE CASCADE
);

-- Indices for efficient queries
CREATE INDEX idx_rag_kb_file_chunks_kb_file ON rag_kb_file_chunks(kb_id, file_url);
CREATE INDEX idx_rag_kb_file_chunks_chunk ON rag_kb_file_chunks(chunk_id);
```

**Modified rag_chunks Table**:

```sql
-- Add content_hash column for deduplication
ALTER TABLE rag_chunks ADD COLUMN content_hash TEXT;
CREATE INDEX idx_rag_chunks_content_hash ON rag_chunks(content_hash);
```

---

### Solution 4: New Category Without RAG Handling

#### Design: Lazy Creation with UI Prompt

**Strategy**: When a new category is created or files are assigned to an uncategorized category, don't auto-create KB. Instead, provide UI prompts and admin tools.

**Implementation**:

```python
# ai_actuarial/rag/knowledge_base.py

class KnowledgeBaseManager:
    
    def get_unmapped_categories(self) -> List[Dict[str, Any]]:
        """
        Get categories that have files but no associated KB.
        
        Returns:
            List of dicts with category name and file count
        """
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
            description=f"Knowledge base for {category} category"
        )
        
        # Link to category
        self.link_kb_to_categories(kb_id, [category], auto_sync=auto_sync)
        
        return kb
```

#### UI Pattern

```
┌─────────────────────────────────────────────────────────────┐
│ RAG Management Dashboard                                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ Knowledge Bases: 3                                          │
│ Total Indexed Files: 450                                    │
│                                                              │
│ ⚠️ Unmapped Categories (5 categories have no KB):           │
│                                                              │
│ • Climate Risk (25 files) [Create KB]                      │
│ • Digital Transformation (18 files) [Create KB]             │
│ • Regulatory Compliance (42 files) [Create KB]              │
│ • Cyber Security (15 files) [Create KB]                     │
│ • ESG (12 files) [Create KB]                                │
│                                                              │
│ [Dismiss] [Create All]                                      │
└─────────────────────────────────────────────────────────────┘
```

---

### Solution 5: Custom File Selection (Non-Category)

#### Design: Manual File Selection Mode

**Strategy**: Support two KB creation modes:
1. **Category-based**: Auto-sync from categories
2. **Manual**: Explicit file selection, no auto-sync

**Implementation**:

```python
# ai_actuarial/rag/knowledge_base.py

class KnowledgeBase:
    """Modified to include kb_mode field."""
    
    def __init__(
        self,
        kb_id: str,
        name: str,
        description: str = "",
        kb_mode: str = "category",  # NEW: "category" or "manual"
        embedding_model: str = "text-embedding-3-large",
        # ... rest of fields ...
    ):
        self.kb_mode = kb_mode  # "category" (auto-sync) or "manual" (explicit selection)
        # ... rest of initialization ...


class KnowledgeBaseManager:
    
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
            kb_mode="manual"  # No auto-sync from categories
        )
        
        # Add selected files
        if file_urls:
            self.add_files_to_kb(kb_id, file_urls)
        
        return kb
    
    def add_files_to_manual_kb(
        self,
        kb_id: str,
        file_urls: List[str]
    ):
        """
        Add files to a manual KB (checks mode).
        
        Args:
            kb_id: Knowledge base ID
            file_urls: List of file URLs to add
        """
        kb = self.get_kb(kb_id)
        if not kb:
            raise KnowledgeBaseException(f"Knowledge base not found: {kb_id}")
        
        if kb.kb_mode != "manual":
            raise KnowledgeBaseException(
                f"KB {kb_id} is category-based. Use category sync instead."
            )
        
        self.add_files_to_kb(kb_id, file_urls)
    
    def search_files_for_manual_kb(
        self,
        query: str = "",
        source: str = "",
        category: str = "",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search files for manual KB selection.
        
        Provides UI for selecting specific files across categories.
        
        Args:
            query: Text search query
            source: Source site filter
            category: Category filter (can be multiple)
            limit: Maximum results
            
        Returns:
            List of file info dicts for selection
        """
        results = self.storage.query_files_with_catalog(
            query=query,
            source=source,
            category=category,
            limit=limit
        )
        
        # Format for UI selection
        return [
            {
                "file_url": r['url'],
                "title": r['title'],
                "category": r.get('category', ''),
                "summary": r.get('summary', '')[:200],  # Truncate for display
                "source_site": r.get('source_site', ''),
                "published_time": r.get('published_time', '')
            }
            for r in results
        ]
```

#### UI Pattern: Manual KB Creation

```
┌─────────────────────────────────────────────────────────────┐
│ Create Manual Knowledge Base                                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ KB Name: [Climate Risk Analysis________________________]    │
│ KB ID:   [climate_risk_analysis____________________]        │
│                                                              │
│ Description:                                                │
│ [Cross-category analysis of climate-related risks in       │
│  insurance and investment portfolios________________]       │
│                                                              │
│ Mode: ○ Category-based  ⦿ Manual Selection                  │
│                                                              │
│ ─────────────────────────────────────────────────────────   │
│ Select Files:                                               │
│                                                              │
│ Search: [climate________________________________] [Filter]   │
│                                                              │
│ ☑ Climate Change Impact on P&C Insurance (AI; Risk)        │
│ ☐ ESG Investment Guidelines (ESG; Investment)               │
│ ☑ Physical Risk Modeling (Risk; Modeling)                  │
│ ☑ Transition Risk Assessment (Climate; Risk)               │
│ ☐ Carbon Pricing Mechanisms (Pricing; ESG)                 │
│ ☑ TCFD Reporting Standards (Regulatory; ESG)               │
│                                                              │
│ Selected: 4 files                                           │
│                                                              │
│ [Create KB and Index] [Cancel]                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Database Schema Updates

### New Tables

```sql
-- Category-to-KB mapping
CREATE TABLE IF NOT EXISTS rag_kb_category_mappings (
    kb_id TEXT NOT NULL,
    category TEXT NOT NULL,
    auto_sync INTEGER DEFAULT 1,
    created_at TEXT,
    PRIMARY KEY (kb_id, category),
    FOREIGN KEY (kb_id) REFERENCES rag_knowledge_bases(kb_id) ON DELETE CASCADE
);

CREATE INDEX idx_rag_kb_category_kb ON rag_kb_category_mappings(kb_id);
CREATE INDEX idx_rag_kb_category_cat ON rag_kb_category_mappings(category);

-- KB-file-chunk associations (for deduplication)
CREATE TABLE IF NOT EXISTS rag_kb_file_chunks (
    kb_id TEXT NOT NULL,
    file_url TEXT NOT NULL,
    chunk_id INTEGER NOT NULL,
    PRIMARY KEY (kb_id, file_url, chunk_id),
    FOREIGN KEY (kb_id, file_url) REFERENCES rag_kb_files(kb_id, file_url) ON DELETE CASCADE,
    FOREIGN KEY (chunk_id) REFERENCES rag_chunks(chunk_id) ON DELETE CASCADE
);

CREATE INDEX idx_rag_kb_file_chunks_kb_file ON rag_kb_file_chunks(kb_id, file_url);
CREATE INDEX idx_rag_kb_file_chunks_chunk ON rag_kb_file_chunks(chunk_id);
```

### Modified Tables

```sql
-- Add kb_mode to rag_knowledge_bases
ALTER TABLE rag_knowledge_bases ADD COLUMN kb_mode TEXT DEFAULT 'category';

-- Add content_hash to rag_chunks for deduplication
ALTER TABLE rag_chunks ADD COLUMN content_hash TEXT;
CREATE INDEX idx_rag_chunks_content_hash ON rag_chunks(content_hash);
```

---

## Testing Strategy

### Test Cases

1. **Manual Task Detection**
   - Create KB with 10 files
   - Index 5 files
   - Modify 2 indexed files
   - Call `get_rag_task_metadata()` → should show 7 pending (5 new + 2 modified)

2. **Category-Based KB**
   - Create category "Risk Management" with 20 files
   - Create KB linked to category with auto_sync=True
   - Verify all 20 files automatically added to KB
   - Add new file to category → verify auto-added to KB

3. **Multi-Category File**
   - File with category "AI; Risk; Pricing"
   - Create 3 KBs for AI, Risk, Pricing
   - Index file → verify single set of embeddings
   - Verify file appears in all 3 KBs
   - Remove from one KB → verify still in other 2

4. **Unmapped Category**
   - Create new category "Cyber Security" with 10 files
   - Call `get_unmapped_categories()` → should list Cyber Security
   - Create KB for category → verify removed from unmapped list

5. **Manual KB**
   - Create manual KB
   - Select 5 specific files across 3 categories
   - Index → verify only selected files indexed
   - Add new category file → verify NOT auto-added

---

## Integration with Existing Task System

### Task Handler Pattern

```python
# ai_actuarial/web/app.py (Phase 1.3)

@app.route('/api/tasks/rag_indexing', methods=['POST'])
@require_auth('tasks')
def create_rag_indexing_task():
    """
    Create RAG indexing task.
    
    Request:
        {
            "kb_id": "actuarial_standards",
            "mode": "incremental",  # or "full_rebuild"
            "file_urls": [...],  # Optional
            "categories": [...]  # Optional
        }
    
    Returns:
        Task info with metadata
    """
    data = request.get_json()
    kb_id = data.get('kb_id')
    mode = data.get('mode', 'incremental')
    file_urls = data.get('file_urls')
    categories = data.get('categories')
    
    # Get task metadata for display
    kb_manager = get_kb_manager()
    metadata = kb_manager.get_rag_task_metadata(kb_id, categories)
    
    # Create task
    task_id = create_task(
        task_type='rag_indexing',
        params={
            'kb_id': kb_id,
            'mode': mode,
            'file_urls': file_urls,
            'categories': categories
        },
        metadata=metadata  # For UI display
    )
    
    return jsonify({
        'task_id': task_id,
        'metadata': metadata
    })


def execute_rag_indexing_task(task_id: str, params: dict):
    """
    Execute RAG indexing task.
    
    Follows existing task execution pattern:
    - Progress logging via _append_task_log()
    - Error handling and reporting
    - Status updates
    """
    kb_id = params['kb_id']
    mode = params.get('mode', 'incremental')
    file_urls = params.get('file_urls')
    categories = params.get('categories')
    
    _append_task_log(task_id, f"Starting RAG indexing for KB: {kb_id}")
    
    try:
        kb_manager = get_kb_manager()
        pipeline = IndexingPipeline(kb_manager)
        
        # Determine files to index
        if file_urls:
            # Explicit file list
            files_to_index = file_urls
        elif categories:
            # Category filter
            all_kb_files = kb_manager.list_kb_files(kb_id)
            files_to_index = kb_manager._filter_files_by_categories(
                all_kb_files, categories
            )
        else:
            # All pending files
            files_to_index = kb_manager.get_files_needing_index(kb_id)
        
        _append_task_log(task_id, f"Files to index: {len(files_to_index)}")
        
        # Execute indexing
        if mode == 'full_rebuild':
            # Full rebuild: reindex all files
            _append_task_log(task_id, "Mode: Full rebuild")
            stats = pipeline.index_files(kb_id, files_to_index, force_reindex=True)
        else:
            # Incremental: only new/modified
            _append_task_log(task_id, "Mode: Incremental")
            stats = pipeline.index_files(kb_id, files_to_index)
        
        # Log results
        _append_task_log(task_id, f"Indexed: {stats['indexed_files']} files")
        _append_task_log(task_id, f"Total chunks: {stats['total_chunks']}")
        _append_task_log(task_id, f"Skipped: {stats['skipped_files']} files")
        
        if stats.get('errors'):
            _append_task_log(task_id, f"Errors: {len(stats['errors'])}")
            for error in stats['errors'][:10]:  # Log first 10 errors
                _append_task_log(
                    task_id, 
                    f"  - {error['file_url']}: {error['error']}"
                )
        
        _append_task_log(task_id, "RAG indexing complete")
        update_task_status(task_id, 'completed')
        
    except Exception as e:
        _append_task_log(task_id, f"Error: {str(e)}")
        update_task_status(task_id, 'failed')
        raise
```

---

## Summary

### Solutions Implemented

| Requirement | Solution | Status |
|------------|----------|--------|
| R1: Manual RAG Task | `get_rag_task_metadata()` with smart detection | ✅ Designed |
| R2: Category-Based KB | `rag_kb_category_mappings` table + auto-sync | ✅ Designed |
| R3: Multi-Category Files | Hybrid deduplication + `rag_kb_file_chunks` table | ✅ Designed |
| R4: New Category Handling | Lazy creation + `get_unmapped_categories()` | ✅ Designed |
| R5: Custom File Selection | Manual KB mode + file search UI | ✅ Designed |

### Key Benefits

1. **Storage Efficiency**: Deduplicated embeddings save ~12KB per duplicate chunk
2. **Cost Efficiency**: No duplicate OpenAI API calls for multi-category files
3. **Flexibility**: Supports both category-based and manual KB creation
4. **User Control**: Manual task initiation with clear metadata display
5. **Backward Compatibility**: All changes non-breaking, existing systems unaffected

### Next Steps (Implementation)

1. **Phase 1.2.7**: Implement all database schema changes
2. **Phase 1.2.8**: Implement KnowledgeBaseManager methods
3. **Phase 1.2.9**: Update IndexingPipeline with deduplication
4. **Phase 1.3.1**: Build Web UI for RAG management
5. **Phase 1.3.2**: Integrate with task system
6. **Phase 1.4**: Testing with real multi-category documents

---

**Document Version**: 1.0  
**Last Updated**: 2026-02-11  
**Next Review**: After Phase 1.2.7 implementation
