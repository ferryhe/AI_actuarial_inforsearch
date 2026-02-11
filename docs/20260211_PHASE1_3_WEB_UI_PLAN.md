# Phase 1.3: RAG Management Web UI & API - Implementation Plan

**Date**: 2026-02-11  
**Phase**: Web Interface for RAG Knowledge Base Management  
**Status**: Planning → Implementation  
**Previous Phase**: Phase 1.2.7 Complete (Task Management & Category Integration)

---

## 📋 Overview

Phase 1.3 implements the complete web user interface and REST API for managing RAG knowledge bases. This phase transforms the Python backend (Phase 1.2) into a full-featured web application integrated with the existing system.

### Objectives
1. **Web UI**: Full CRUD interface for knowledge bases
2. **REST API**: Complete API endpoints for all KB operations
3. **Task Integration**: Background indexing via existing task system
4. **Category Integration**: UI for category-based and manual KB creation
5. **Testing**: Integration testing with real documents

---

## 🗂️ Implementation Checklist

### Phase 1.3.1: REST API Endpoints ⏳

**Goal**: Implement all backend API routes for KB management

#### API Endpoints to Implement

- [ ] **KB CRUD Operations**
  - [ ] `GET /api/rag/knowledge-bases` - List all KBs (with optional filters)
  - [ ] `POST /api/rag/knowledge-bases` - Create new KB
  - [ ] `GET /api/rag/knowledge-bases/<kb_id>` - Get KB details
  - [ ] `PUT /api/rag/knowledge-bases/<kb_id>` - Update KB metadata
  - [ ] `DELETE /api/rag/knowledge-bases/<kb_id>` - Delete KB
  
- [ ] **File Association Operations**
  - [ ] `GET /api/rag/knowledge-bases/<kb_id>/files` - List files in KB
  - [ ] `POST /api/rag/knowledge-bases/<kb_id>/files` - Add files to KB
  - [ ] `DELETE /api/rag/knowledge-bases/<kb_id>/files/<file_url>` - Remove file from KB
  
- [ ] **Category Integration Operations**
  - [ ] `GET /api/rag/categories/unmapped` - List categories without RAG KB
  - [ ] `POST /api/rag/knowledge-bases/<kb_id>/categories` - Link KB to categories
  - [ ] `GET /api/rag/knowledge-bases/<kb_id>/categories` - Get linked categories
  
- [ ] **Statistics & Metadata**
  - [ ] `GET /api/rag/knowledge-bases/<kb_id>/stats` - Get KB statistics
  - [ ] `GET /api/rag/knowledge-bases/<kb_id>/files/pending` - Files needing indexing
  - [ ] `POST /api/rag/task-metadata` - Get task metadata (pre-task statistics)
  
- [ ] **Task Management**
  - [ ] `POST /api/rag/knowledge-bases/<kb_id>/index` - Create indexing task
  - [ ] `GET /api/rag/knowledge-bases/<kb_id>/tasks` - List KB tasks

#### Implementation Details

**File**: `ai_actuarial/web/app.py`

**Authentication**:
- Read operations: Public or Bearer token (based on REQUIRE_AUTH)
- Write operations: Require CONFIG_WRITE_AUTH_TOKEN via X-Auth-Token header
- Follow existing authentication patterns (markdown conversion, catalog management)

**Error Handling**:
- 200: Success with data
- 201: Created (for POST operations)
- 400: Bad request (validation errors)
- 401: Unauthorized
- 404: Not found
- 500: Server error

**Response Format**:
```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

---

### Phase 1.3.2: KB List Page ⏳

**Goal**: Main page for viewing and managing all knowledge bases

#### Page Route
- URL: `/rag` or `/knowledge-bases`
- Template: `templates/rag_management.html`

#### Features
- [ ] **KB Table Display**
  - [ ] Columns: Name, Mode (category/manual), Files, Chunks, Last Updated, Actions
  - [ ] Sortable columns (client-side)
  - [ ] Search/filter functionality
  - [ ] Color coding for KB status (indexed, pending, error)
  
- [ ] **Create New KB Button**
  - [ ] Opens modal dialog
  - [ ] Two creation modes:
    - Category-based (auto-sync with selected categories)
    - Manual (user-selected files)
  - [ ] Form validation
  
- [ ] **KB Actions Menu**
  - [ ] View Details button
  - [ ] Reindex button (creates indexing task)
  - [ ] Delete button (with confirmation)
  - [ ] Export KB metadata
  
- [ ] **Category Filter Sidebar**
  - [ ] Show all categories
  - [ ] Highlight categories without RAG
  - [ ] Quick create KB from category

- [ ] **Integration with Navigation**
  - [ ] Add "Knowledge Bases" link to main navigation
  - [ ] Add to quick actions menu

#### UI Design
- **Style**: Match existing application design (Bootstrap/custom)
- **Icons**: Font Awesome or existing icon set
- **Responsive**: Mobile-friendly layout
- **Accessibility**: ARIA labels, keyboard navigation

---

### Phase 1.3.3: KB Detail Page ⏳

**Goal**: Detailed view and management for individual knowledge base

#### Page Route
- URL: `/rag/<kb_id>` or `/knowledge-bases/<kb_id>`
- Template: `templates/rag_detail.html`

#### Sections

**1. KB Metadata Panel**
- [ ] Display: Name, Description, KB Mode, Embedding Model
- [ ] Edit button (inline editing or modal)
- [ ] Creation/update timestamps
- [ ] Configuration: Chunk size, overlap, similarity threshold

**2. Statistics Dashboard**
- [ ] Total files: XX (YY indexed, ZZ pending)
- [ ] Total chunks: XX
- [ ] Index size: XX MB
- [ ] Last indexed: timestamp
- [ ] Visual progress bar for indexing status

**3. Files Management Tab**
- [ ] Table of all associated files
- [ ] Columns: Filename, Category, Size, Chunks, Indexed At, Status
- [ ] Bulk actions: Add files, Remove selected, Reindex selected
- [ ] File search/filter
- [ ] Status indicators: ✅ Indexed, 📝 Pending, ⚠️ Error

**4. Category Mappings Tab** (for category-based KBs)
- [ ] List of linked categories
- [ ] Add/remove categories
- [ ] Auto-sync status indicator
- [ ] File count per category

**5. Indexing History Tab**
- [ ] Table of past indexing tasks
- [ ] Columns: Task ID, Date, Files Processed, Status, Duration, Logs
- [ ] Link to task detail in Task Center
- [ ] Filter by status (success/error)

**6. Actions Toolbar**
- [ ] "Add Files" button (opens file selector with category filter)
- [ ] "Reindex All" button (creates task for all pending files)
- [ ] "Delete KB" button (with confirmation dialog)
- [ ] "Export Metadata" button (download JSON)

---

### Phase 1.3.4: Indexing Task Integration ⏳

**Goal**: Integrate RAG indexing with existing task system

#### Task Type: `rag_indexing`

**Task Parameters**:
```python
{
  "task_type": "rag_indexing",
  "kb_id": "actuarial_standards",
  "file_urls": ["file1.pdf", "file2.pdf"],  # Optional: specific files
  "reindex_all": false,  # If true, reindex all pending files
  "incremental": true  # Only reindex changed files
}
```

#### Implementation Steps

- [ ] **Add to Task Execution** (`execute_collection_task`)
  - [ ] Create new case for `rag_indexing` task type
  - [ ] Call `IndexingPipeline.index_files()`
  - [ ] Log progress to task log
  - [ ] Handle errors gracefully (continue on per-file errors)
  
- [ ] **Task Metadata Pre-Check** (similar to markdown conversion)
  - [ ] Call `kb_manager.get_rag_task_metadata(kb_id)`
  - [ ] Display statistics before starting:
    - Total files to index
    - Estimated time (based on 2-3 sec/file)
    - Oldest pending file
    - Required vs available API quota
  
- [ ] **Progress Tracking**
  - [ ] Update task status in real-time
  - [ ] Log each file processed: "✅ Indexed file1.pdf (45 chunks)"
  - [ ] Report errors: "⚠️ Error indexing file2.pdf: [reason]"
  - [ ] Final summary: "Indexed X/Y files, Z chunks created"
  
- [ ] **Task Center Integration**
  - [ ] Show RAG tasks in `/tasks` page
  - [ ] Display task-specific information
  - [ ] Link back to KB detail page
  - [ ] Real-time progress updates via existing mechanism

#### Error Handling
- **API Errors**: Retry with exponential backoff (already in EmbeddingGenerator)
- **File Errors**: Log and continue with remaining files
- **Storage Errors**: Rollback transaction, mark task as failed
- **Quota Exceeded**: Pause and reschedule

---

### Phase 1.3.5: Create/Edit KB Modals ⏳

**Goal**: Modal dialogs for creating and editing knowledge bases

#### Create KB Modal

**Features**:
- [ ] **Mode Selection** (Category vs Manual)
  - [ ] Radio buttons or tabs
  - [ ] Different forms based on mode
  
- [ ] **Category Mode Form**
  - [ ] KB Name (required)
  - [ ] Description (optional)
  - [ ] Category multi-select (required, at least 1)
  - [ ] Preview: Shows file count from selected categories
  
- [ ] **Manual Mode Form**
  - [ ] KB Name (required)
  - [ ] Description (optional)
  - [ ] File selector with category filter
  - [ ] Selected files list (drag-drop reorder)
  
- [ ] **Advanced Settings** (collapsible section)
  - [ ] Embedding model: text-embedding-3-large (default) / text-embedding-3-small
  - [ ] Chunk size: 800 tokens (default)
  - [ ] Chunk overlap: 100 tokens (default)
  - [ ] Similarity threshold: 0.4 (default)
  
- [ ] **Validation**
  - [ ] KB ID uniqueness check
  - [ ] Required fields
  - [ ] Reasonable values for settings
  
- [ ] **Actions**
  - [ ] "Create" button → API call → redirect to KB detail
  - [ ] "Create & Index" button → Create + start indexing task
  - [ ] "Cancel" button

#### Edit KB Modal

**Features**:
- [ ] Load existing KB metadata
- [ ] Edit name, description
- [ ] Cannot change: kb_id, kb_mode, embedding_model (would require reindex)
- [ ] Can adjust: chunk_size, chunk_overlap (for new indexes)
- [ ] Save changes via PUT API

---

### Phase 1.3.6: Category Integration UI ⏳

**Goal**: UI components for category-based KB management

#### Unmapped Categories Alert

**Location**: Top of `/rag` page

**Features**:
- [ ] Alert banner if unmapped categories exist
- [ ] "You have X categories without knowledge bases"
- [ ] "Create KBs" button → opens modal with categories pre-selected
- [ ] Dismissible (stores preference in session)

#### Category Sidebar (on KB List Page)

**Features**:
- [ ] List all categories
- [ ] Show KB count per category (some may have 0)
- [ ] Click category → filter KB list
- [ ] "+ Create KB" icon next to unmapped categories
- [ ] Color coding:
  - Green: Has KB(s)
  - Yellow: No KB
  - Gray: Empty category

---

### Phase 1.3.7: File Selector Component ⏳

**Goal**: Reusable component for selecting files from catalog

#### Features
- [ ] **Category Filter**
  - [ ] Dropdown or sidebar with all categories
  - [ ] Multi-select support
  - [ ] "All" option
  
- [ ] **File Table**
  - [ ] Columns: Filename, Category, Size, Last Modified
  - [ ] Checkbox selection (with select all)
  - [ ] Search/filter by filename
  - [ ] Sortable columns
  - [ ] Pagination (100 files per page)
  
- [ ] **Selection Summary**
  - [ ] "X files selected from Y categories"
  - [ ] Clear selection button
  
- [ ] **Integration**
  - [ ] Used in: Create Manual KB modal, Add Files to KB

---

### Phase 1.3.8: Integration Testing ⏳

**Goal**: End-to-end testing with real documents

#### Test Scenarios

- [ ] **Scenario 1: Category-Based KB**
  1. Create KB from 2 categories
  2. Verify files auto-added
  3. Start indexing task
  4. Monitor task progress
  5. Verify all files indexed
  6. Check statistics are accurate
  
- [ ] **Scenario 2: Manual KB**
  1. Create manual KB with 10 specific files
  2. Start indexing
  3. Add 5 more files
  4. Run incremental reindex
  5. Verify only new files indexed
  
- [ ] **Scenario 3: Multi-Category File**
  1. File belongs to 2 categories
  2. Create KB from category 1
  3. Create KB from category 2
  4. Verify file appears in both KBs
  5. Verify no duplicate embedding (check rag_chunks)
  
- [ ] **Scenario 4: Unmapped Categories**
  1. Create new category with files
  2. Verify appears in unmapped alert
  3. Create KB from unmapped category
  4. Verify alert updates
  
- [ ] **Scenario 5: Error Handling**
  1. Start indexing with invalid API key
  2. Verify graceful error message
  3. Fix API key
  4. Retry indexing
  5. Verify success
  
- [ ] **Scenario 6: Incremental Updates**
  1. Index 50 files
  2. Edit 5 markdown files
  3. Run reindex
  4. Verify only 5 files reindexed
  5. Verify total time ~10-15 seconds

---

## 📁 File Structure

New files to create:

```
ai_actuarial/web/
├── app.py (extend with RAG API routes)
└── templates/
    ├── rag_management.html      # KB list page
    ├── rag_detail.html           # KB detail page
    ├── modals/
    │   ├── create_kb_modal.html  # Create KB modal
    │   └── edit_kb_modal.html    # Edit KB modal
    └── partials/
        ├── kb_stats_card.html    # Statistics card component
        ├── file_selector.html    # File selector component
        └── category_sidebar.html # Category sidebar component

ai_actuarial/web/static/
├── css/
│   └── rag.css                   # RAG-specific styles
└── js/
    └── rag.js                    # RAG-specific JavaScript
```

---

## 🎯 Success Criteria

### Functional Requirements
- ✅ All API endpoints working and tested
- ✅ KB list page displays all KBs correctly
- ✅ KB detail page shows complete information
- ✅ Can create category-based and manual KBs
- ✅ Indexing tasks run successfully in background
- ✅ File selector works with category filter
- ✅ Unmapped categories detected and displayed
- ✅ Multi-category files handled correctly
- ✅ Incremental indexing works (only changed files)

### Non-Functional Requirements
- ✅ Page load time < 2 seconds
- ✅ API response time < 500ms (except indexing operations)
- ✅ Responsive design (mobile-friendly)
- ✅ Accessible (WCAG 2.1 AA)
- ✅ Error messages are clear and actionable
- ✅ UI matches existing application style

### Integration Requirements
- ✅ Uses existing authentication system
- ✅ Integrates with existing task system
- ✅ Uses existing logging infrastructure
- ✅ Compatible with existing category taxonomy
- ✅ Works with existing markdown storage

---

## 📅 Timeline

**Estimated Duration**: 2-3 weeks

- Week 1: API endpoints + KB list page
- Week 2: KB detail page + modals + task integration
- Week 3: Testing + polish + documentation

**MVP (1 week)**: Core CRUD operations + basic UI + task integration

---

## 🔧 Technical Considerations

### Authentication
- Follow existing patterns from markdown API
- Use CONFIG_WRITE_AUTH_TOKEN for write operations
- Public read access (if REQUIRE_AUTH=false)

### Database Transactions
- Use transaction blocks for multi-step operations
- Rollback on errors to maintain consistency
- Lock tables during critical operations

### API Performance
- Paginate large result sets
- Cache expensive queries (statistics)
- Use database indices for common queries

### Error Messages
- User-friendly messages in UI
- Detailed technical info in logs
- Actionable error recovery suggestions

### Testing Strategy
- Unit tests for each API endpoint
- Integration tests for workflows
- UI tests with Selenium/Playwright (optional)
- Manual testing with real documents

---

## 📝 Documentation

### User Documentation
- [ ] "Getting Started with Knowledge Bases" guide
- [ ] "Creating Your First RAG KB" tutorial
- [ ] "Managing Knowledge Bases" reference
- [ ] FAQ for common issues

### Developer Documentation
- [ ] API endpoint reference
- [ ] Code structure overview
- [ ] Testing guide
- [ ] Troubleshooting guide

---

## 🎬 Next Steps After Phase 1.3

1. **Phase 1.4**: Final testing and optimization
2. **Phase 2**: AI Chatbot implementation (retrieval + LLM integration)
3. **Phase 3**: System integration and deployment

---

**Status**: Ready to begin implementation  
**Next Action**: Start with Phase 1.3.1 (REST API Endpoints)
