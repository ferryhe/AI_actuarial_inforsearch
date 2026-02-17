# AI Chatbot and RAG Database Implementation Plan

**Issue**: AI chatbot with RAG knowledge base  
**Date**: 2026-02-11  
**Status**: Planning Phase  
**Reference Project**: https://github.com/ferryhe/AI_Knowledge_Base  
**Last Updated**: 2026-02-11 (Revised based on stakeholder feedback)

---

## 📌 IMPORTANT: Revised Priorities (Feb 11, 2026)

Based on stakeholder feedback, the following adjustments have been made:

### Critical Changes
1. **✅ Semantic Chunking (HIGH PRIORITY)**: Changed from simple token-based (500/80) to structure-aware semantic chunking that preserves document hierarchy, sections, and citations. Ideal for legal/academic documents.

2. **✅ Incremental Updates (HIGH PRIORITY)**: Emphasized as critical feature - ability to add new files to existing knowledge bases without full rebuild. FAISS supports this natively.

3. **✅ Multi-KB Query (MOVED UP)**: Moved from Phase 2.4 to Phase 2.3 due to high stakeholder interest in cross-document queries.

4. **⚠️ GraphRAG (DEFERRED)**: Moved from Phase 2+ to Phase 4+ (optional enhancement only). Not suitable for MVP given project's well-structured documents.

5. **✅ Embedding Model Clarified**: OpenAI text-embedding-3-large confirmed as primary choice for technical/multilingual content quality.

### See Also
- **Detailed Clarifications**: `docs/20260211_RAG_IMPLEMENTATION_CLARIFICATIONS.md`
- **Original Roadmap**: `AI_CHATBOT_PROJECT_ROADMAP.md`

---

## Executive Summary

This document outlines a comprehensive implementation plan for building an AI chatbot system with Retrieval-Augmented Generation (RAG) capabilities. The system will leverage the existing markdown conversion infrastructure and add intelligent question-answering capabilities with knowledge base management.

### Key Objectives
1. Design and implement a RAG-based knowledge base using converted markdown files
2. Create a management interface for the knowledge base (CRUD operations)
3. Build an agentic AI chatbot that can intelligently query the knowledge base
4. Provide flexible configuration for embeddings, chunking strategies, and AI models

---

## Part 1: Database (RAG Knowledge Base)

### Phase 1.1: RAG Architecture Research and Design

**Goal**: Study RAG architectures and select the best approach for actuarial document Q&A

#### Subtasks

- [ ] **1.1.1 Research RAG Architectures**
  - [ ] Study traditional RAG (vector similarity search)
  - [ ] Research GraphRAG (Microsoft's graph-based approach)
  - [ ] Evaluate hybrid approaches (vector + keyword search)
  - [ ] Review LlamaIndex, LangChain, and custom implementations
  - [ ] Document pros/cons of each approach for actuarial documents
  
- [ ] **1.1.2 Analyze Reference Project (AI_Knowledge_Base)**
  - [ ] Review FAISS-based vector store implementation
  - [ ] Analyze chunking strategy (500 tokens, 80 token overlap)
  - [ ] Study similarity threshold and hallucination prevention
  - [ ] Evaluate OpenAI embeddings (text-embedding-3-large)
  - [ ] Review retrieval and citation mechanisms
  
- [ ] **1.1.3 Select RAG Architecture**
  - [ ] Choose primary RAG approach: Traditional FAISS-based vector search (recommended for MVP)
  - [ ] Select embedding model: OpenAI text-embedding-3-large (best for technical/multilingual content)
  - [ ] Define chunking strategy: **Semantic structure-aware** (section/paragraph-based, NOT just token-based)
  - [ ] Plan for future GraphRAG experimentation (Phase 4+ only, NOT MVP priority)
  
- [ ] **1.1.4 Design Database Schema**
  - [ ] Extend `catalog_items` table with RAG-specific fields:
    - `rag_indexed` (BOOLEAN) - whether file is indexed in RAG
    - `rag_indexed_at` (TEXT) - timestamp of last indexing
    - `rag_chunk_count` (INTEGER) - number of chunks created
    - `rag_index_version` (TEXT) - version of indexing pipeline used
  - [ ] Create new table: `rag_knowledge_bases`
    - `id` (TEXT PRIMARY KEY) - unique identifier (e.g., "actuarial_general")
    - `name` (TEXT) - human-readable name
    - `description` (TEXT) - purpose and scope
    - `index_type` (TEXT) - "faiss", "graphrag", etc.
    - `embedding_model` (TEXT) - embedding model used
    - `chunk_size` (INTEGER) - tokens per chunk
    - `chunk_overlap` (INTEGER) - overlap between chunks
    - `created_at` (TEXT) - creation timestamp
    - `updated_at` (TEXT) - last update timestamp
    - `file_count` (INTEGER) - number of indexed files
    - `chunk_count` (INTEGER) - total chunks
    - `index_path` (TEXT) - path to FAISS index file
    - `metadata_path` (TEXT) - path to metadata pickle file
  - [ ] Create new table: `rag_kb_files`
    - `kb_id` (TEXT) - foreign key to rag_knowledge_bases
    - `file_url` (TEXT) - foreign key to files
    - `added_at` (TEXT) - when file was added to KB
    - PRIMARY KEY (kb_id, file_url)
  - [ ] Create new table: `rag_chunks`
    - `chunk_id` (TEXT PRIMARY KEY) - unique chunk identifier
    - `kb_id` (TEXT) - foreign key to rag_knowledge_bases
    - `file_url` (TEXT) - source file
    - `chunk_index` (INTEGER) - position in file
    - `content` (TEXT) - chunk text content
    - `token_count` (INTEGER) - number of tokens
    - `embedding_hash` (TEXT) - detect if chunk changed (for incremental updates)
    - `section_hierarchy` (TEXT) - document structure context (e.g., "Article 5 > Section 2.1")
    - `created_at` (TEXT) - indexing timestamp
    - INDEX on (kb_id, file_url)

**Output**: Architecture Decision Document (ADD) with selected approach and rationale

---

### Phase 1.2: Core RAG Infrastructure

**Goal**: Implement the core RAG indexing and retrieval engine

#### Subtasks

- [ ] **1.2.1 Create RAG Module Structure**
  - [ ] Create `ai_actuarial/rag/` directory
  - [ ] Create `__init__.py` with module exports
  - [ ] Create `config.py` for RAG configuration
  - [ ] Create `exceptions.py` for RAG-specific exceptions
  
- [ ] **1.2.2 Implement Semantic Chunking Engine** ⭐ HIGH PRIORITY
  - [ ] Create `ai_actuarial/rag/semantic_chunking.py`
  - [ ] **Primary: Section-based chunking** (preserve markdown headers ##, ###, ####)
  - [ ] **Secondary: Paragraph-based chunking** (for long sections, maintain semantic boundaries)
  - [ ] **Fallback: Sentence-based splitting** (only when paragraphs exceed limits)
  - [ ] **Metadata enrichment**: track document hierarchy, citations, page numbers
  - [ ] Preserve document structure: tables, lists, citation blocks, cross-references
  - [ ] Token-based splitting as last resort only (with tiktoken)
  - [ ] Add validation: min 100 tokens, max 800 tokens per chunk
  - [ ] Write unit tests with real actuarial document examples
  
- [ ] **1.2.3 Implement Embedding Engine**
  - [ ] Create `ai_actuarial/rag/embeddings.py`
  - [ ] Support multiple embedding providers:
    - OpenAI (text-embedding-3-large, text-embedding-3-small)
    - Local models via sentence-transformers (fallback)
  - [ ] Implement batch embedding with configurable batch size (default 64)
  - [ ] Add retry logic with exponential backoff
  - [ ] Add rate limiting for API calls
  - [ ] Cache embeddings to avoid recomputation
  - [ ] Write unit tests for embedding generation
  
- [ ] **1.2.4 Implement Vector Store**
  - [ ] Create `ai_actuarial/rag/vector_store.py`
  - [ ] Implement FAISS index management
  - [ ] Support index creation, loading, and saving
  - [ ] Implement similarity search with configurable k
  - [ ] Add similarity threshold filtering
  - [ ] Implement metadata storage with pickle
  - [ ] Add index versioning and migration support
  - [ ] Write unit tests for vector store operations
  
- [ ] **1.2.5 Implement Knowledge Base Manager** ⭐ HIGH PRIORITY
  - [ ] Create `ai_actuarial/rag/knowledge_base.py`
  - [ ] Implement KB CRUD operations (create, read, update, delete)
  - [ ] Add file-to-KB association management
  - [ ] **Implement incremental indexing** (add files without full rebuild) - CRITICAL FEATURE
  - [ ] **Smart update detection** (detect when files need reindexing based on markdown_updated_at)
  - [ ] **Partial updates** (remove old chunks, add new chunks for modified files)
  - [ ] Add KB statistics (file count, chunk count, last updated, pending files)
  - [ ] Implement KB export/import for backup
  - [ ] Write unit tests for KB management and incremental updates
  
- [ ] **1.2.6 Implement Indexing Pipeline**
  - [ ] Create `ai_actuarial/rag/indexing.py`
  - [ ] Build pipeline: markdown → chunks → embeddings → FAISS index
  - [ ] Add progress tracking and logging
  - [ ] Implement error handling and retry logic
  - [ ] Add validation for markdown content
  - [ ] Support batch indexing with category filters
  - [ ] Write integration tests for full pipeline

**Output**: Functional RAG core library with comprehensive tests

---

### Phase 1.3: RAG Management Interface

**Goal**: Create web UI for managing knowledge bases

#### Subtasks

- [ ] **1.3.1 Design UI/UX for KB Management**
  - [ ] Wireframe KB list page (view all knowledge bases)
  - [ ] Wireframe KB detail page (view/edit KB settings)
  - [ ] Wireframe KB file management (add/remove files)
  - [ ] Wireframe indexing task interface (similar to markdown conversion)
  - [ ] Wireframe KB statistics dashboard
  
- [ ] **1.3.2 Implement Backend API Endpoints**
  - [ ] `GET /api/rag/knowledge-bases` - list all KBs
  - [ ] `POST /api/rag/knowledge-bases` - create new KB
  - [ ] `GET /api/rag/knowledge-bases/<kb_id>` - get KB details
  - [ ] `PUT /api/rag/knowledge-bases/<kb_id>` - update KB settings
  - [ ] `DELETE /api/rag/knowledge-bases/<kb_id>` - delete KB
  - [ ] `GET /api/rag/knowledge-bases/<kb_id>/files` - list KB files
  - [ ] `POST /api/rag/knowledge-bases/<kb_id>/files` - add files to KB
  - [ ] `DELETE /api/rag/knowledge-bases/<kb_id>/files/<file_url>` - remove file
  - [ ] `POST /api/rag/knowledge-bases/<kb_id>/index` - trigger indexing task
  - [ ] `GET /api/rag/knowledge-bases/<kb_id>/stats` - get KB statistics
  - [ ] Add authentication checks (require CONFIG_WRITE_AUTH_TOKEN for writes)
  
- [ ] **1.3.3 Implement KB List Page**
  - [ ] Create `/rag` route in Flask app
  - [ ] Create `templates/rag_management.html`
  - [ ] Display table of all knowledge bases
  - [ ] Show KB name, type, files count, chunks count, last updated
  - [ ] Add "Create New KB" button
  - [ ] Add actions: View, Edit, Delete, Reindex
  - [ ] Add category filter for file selection
  - [ ] Integrate with existing navigation
  
- [ ] **1.3.4 Implement KB Detail/Edit Page**
  - [ ] Create `/rag/<kb_id>` route
  - [ ] Create `templates/rag_detail.html`
  - [ ] Display KB metadata (name, description, settings)
  - [ ] Show list of indexed files with removal option
  - [ ] Add file selector with category filter
  - [ ] Show indexing job history and logs
  - [ ] Display KB statistics (file count, chunk count, index size)
  - [ ] Add "Reindex All" and "Add Files" buttons
  
- [ ] **1.3.5 Implement Indexing Task Integration**
  - [ ] Create new task type `rag_indexing` in task system
  - [ ] Add to task execution logic in `execute_collection_task`
  - [ ] Implement task progress tracking
  - [ ] Add per-task logging for indexing operations
  - [ ] Show real-time progress in Task Center
  - [ ] Handle errors gracefully with informative messages
  
- [ ] **1.3.6 Add KB Creation/Edit Modal**
  - [ ] Create modal dialog for KB creation
  - [ ] Form fields: name, description, embedding model, chunk size, chunk overlap
  - [ ] Validation for required fields
  - [ ] Default values from reference project (500 tokens, 80 overlap)
  - [ ] Success/error feedback

**Output**: Complete web interface for RAG knowledge base management

---

### Phase 1.4: Testing and Optimization

**Goal**: Ensure RAG system is reliable and performant

#### Subtasks

- [ ] **1.4.1 Unit Tests**
  - [ ] Test chunking with various markdown formats
  - [ ] Test embedding generation and caching
  - [ ] Test FAISS index operations
  - [ ] Test KB CRUD operations
  - [ ] Test file association management
  - [ ] Achieve >80% code coverage for RAG module
  
- [ ] **1.4.2 Integration Tests**
  - [ ] Test full indexing pipeline (markdown → FAISS)
  - [ ] Test incremental updates (add files to existing KB)
  - [ ] Test KB deletion and cleanup
  - [ ] Test error recovery and retry logic
  - [ ] Test concurrent operations
  
- [ ] **1.4.3 Performance Testing**
  - [ ] Benchmark indexing speed (files/minute)
  - [ ] Test with large document sets (1000+ files)
  - [ ] Measure query latency (target: <1 second)
  - [ ] Profile memory usage during indexing
  - [ ] Optimize bottlenecks
  
- [ ] **1.4.4 Data Validation**
  - [ ] Test with real actuarial documents
  - [ ] Verify chunk quality and coherence
  - [ ] Test retrieval accuracy with known queries
  - [ ] Validate citation tracking
  - [ ] Test hallucination prevention

**Output**: Comprehensive test suite and performance report

---

## Part 2: AI Chatbot

### Phase 2.1: Chatbot Architecture Design

**Goal**: Design an agentic chatbot with intelligent routing

#### Subtasks

- [ ] **2.1.1 Research Chatbot Architectures**
  - [ ] Study agentic frameworks (LangGraph, AutoGPT, BabyAGI)
  - [ ] Review multi-agent patterns
  - [ ] Evaluate routing strategies (semantic routing, rule-based)
  - [ ] Research tone adaptation techniques
  - [ ] Study prompt engineering best practices
  
- [ ] **2.1.2 Define Chatbot Personas/Modes**
  - [ ] **Expert Mode**: Technical, detailed, with citations
  - [ ] **Summary Mode**: Concise, high-level overviews
  - [ ] **Tutorial Mode**: Step-by-step, educational
  - [ ] **Comparison Mode**: Analyze similarities/differences
  - [ ] Define system prompts for each mode
  
- [ ] **2.1.3 Design KB Selection Logic**
  - [ ] Automatic KB selection based on query analysis
  - [ ] Manual KB selection by user
  - [ ] Support querying multiple KBs simultaneously
  - [ ] Implement fallback to default KB
  
- [ ] **2.1.4 Design Conversation Management**
  - [ ] Multi-turn conversation support
  - [ ] Context window management (e.g., last 10 messages)
  - [ ] Conversation history persistence
  - [ ] Session management (per-user conversations)

**Output**: Chatbot Architecture Design Document

---

### Phase 2.2: Core Chatbot Engine

**Goal**: Implement the chatbot inference and retrieval logic

#### Subtasks

- [ ] **2.2.1 Create Chatbot Module Structure**
  - [ ] Create `ai_actuarial/chatbot/` directory
  - [ ] Create `__init__.py` with module exports
  - [ ] Create `config.py` for chatbot configuration
  - [ ] Create `prompts.py` for system prompts
  
- [ ] **2.2.2 Implement RAG Retrieval Integration**
  - [ ] Create `ai_actuarial/chatbot/retrieval.py`
  - [ ] Implement query → embedding → FAISS search
  - [ ] Add similarity threshold filtering (default 0.4)
  - [ ] Implement result ranking and deduplication
  - [ ] Add citation generation from retrieved chunks
  - [ ] Support multi-KB retrieval
  
- [ ] **2.2.3 Implement LLM Integration**
  - [ ] Create `ai_actuarial/chatbot/llm.py`
  - [ ] Support multiple LLM providers:
    - OpenAI (GPT-4, GPT-4-turbo, GPT-3.5-turbo)
    - Anthropic Claude (optional)
    - Local models via Ollama (optional)
  - [ ] Implement streaming responses
  - [ ] Add retry logic with exponential backoff
  - [ ] Add rate limiting
  - [ ] Handle API errors gracefully
  
- [ ] **2.2.4 Implement Prompt Engineering**
  - [ ] Create system prompts for each chatbot mode
  - [ ] Implement context injection (retrieved chunks)
  - [ ] Add hallucination prevention instructions
  - [ ] Add citation requirement enforcement
  - [ ] Implement "I don't know" responses for low-confidence cases
  
- [ ] **2.2.5 Implement Conversation Manager**
  - [ ] Create `ai_actuarial/chatbot/conversation.py`
  - [ ] Implement conversation state management
  - [ ] Add message history tracking (in-memory + DB)
  - [ ] Implement context window trimming
  - [ ] Add conversation summarization for long threads
  
- [ ] **2.2.6 Implement Query Router**
  - [ ] Create `ai_actuarial/chatbot/router.py`
  - [ ] Implement semantic query analysis
  - [ ] Route query to appropriate KB(s)
  - [ ] Select appropriate chatbot mode based on query type
  - [ ] Add logging for routing decisions

**Output**: Functional chatbot engine with RAG integration

---

### Phase 2.3: Chatbot Web Interface

**Goal**: Create user-friendly chat interface

#### Subtasks

- [ ] **2.3.1 Design Chat UI/UX**
  - [ ] Wireframe chat page layout
  - [ ] Design message bubbles (user vs. assistant)
  - [ ] Design citation display and linking
  - [ ] Design KB/mode selector
  - [ ] Design conversation history sidebar
  - [ ] Design mobile-responsive layout
  
- [ ] **2.3.2 Implement Backend API Endpoints**
  - [ ] `POST /api/chat/query` - submit chat query
  - [ ] `GET /api/chat/conversations` - list user conversations
  - [ ] `GET /api/chat/conversations/<conv_id>` - get conversation history
  - [ ] `DELETE /api/chat/conversations/<conv_id>` - delete conversation
  - [ ] `POST /api/chat/conversations` - create new conversation
  - [ ] Add WebSocket support for streaming responses (optional)
  
- [ ] **2.3.3 Implement Chat Page**
  - [ ] Create `/chat` route in Flask app
  - [ ] Create `templates/chat.html`
  - [ ] Implement chat message display area
  - [ ] Add message input box with auto-resize
  - [ ] Add "Send" button and Enter key support
  - [ ] Show typing indicator during response generation
  - [ ] Display citations as clickable links
  
- [ ] **2.3.4 Implement Chat Controls**
  - [ ] Add KB selector dropdown (with "Auto" option)
  - [ ] Add chatbot mode selector (Expert, Summary, Tutorial, etc.)
  - [ ] Add "New Conversation" button
  - [ ] Add "Clear History" button with confirmation
  - [ ] Add conversation export (JSON/Markdown)
  
- [ ] **2.3.5 Implement Conversation History**
  - [ ] Create database table for conversations:
    - `conversation_id` (TEXT PRIMARY KEY)
    - `user_id` (TEXT) - for multi-user support
    - `title` (TEXT) - auto-generated from first query
    - `kb_id` (TEXT) - knowledge base used
    - `mode` (TEXT) - chatbot mode
    - `created_at` (TEXT)
    - `updated_at` (TEXT)
  - [ ] Create table for messages:
    - `message_id` (TEXT PRIMARY KEY)
    - `conversation_id` (TEXT)
    - `role` (TEXT) - "user" or "assistant"
    - `content` (TEXT)
    - `citations` (TEXT) - JSON array
    - `created_at` (TEXT)
  - [ ] Implement conversation list sidebar
  - [ ] Auto-save messages to database
  - [ ] Load conversation on selection
  
- [ ] **2.3.6 Add Citation Linking**
  - [ ] Parse citations from assistant responses
  - [ ] Generate links to source files
  - [ ] Add citation preview on hover
  - [ ] Link to specific file detail page
  - [ ] Highlight cited section in source document

**Output**: Complete chat interface with conversation management

---

### Phase 2.4: Advanced Features

**Goal**: Add intelligent capabilities and optimizations

#### Subtasks

- [ ] **2.4.1 Implement Semantic Query Analysis**
  - [ ] Classify query intent (factual, comparison, explanation, etc.)
  - [ ] Extract key entities from query
  - [ ] Identify query scope (single document vs. broad topic)
  - [ ] Use intent to optimize retrieval and generation
  
- [ ] **2.4.2 Implement Multi-KB Query** ⭐ MOVE TO PHASE 2.3 (HIGH PRIORITY)
  - [ ] Support querying multiple KBs in single request
  - [ ] Merge and rank results from multiple KBs
  - [ ] Track source KB in citations (color-coded badges)
  - [ ] Add conflict resolution for contradictory information
  - [ ] UI: Multi-select KB dropdown, "Query All KBs" option
  - [ ] Diversify results to ensure representation from each KB
  
- [ ] **2.4.3 Implement Response Quality Checks**
  - [ ] Detect potential hallucinations
  - [ ] Verify citations are valid
  - [ ] Check answer relevance to query
  - [ ] Add confidence scores to responses
  - [ ] Implement answer validation pipeline
  
- [ ] **2.4.4 Add Follow-up Suggestions**
  - [ ] Generate related questions based on response
  - [ ] Suggest deeper dives into topics
  - [ ] Recommend related documents
  - [ ] Add one-click follow-up buttons
  
- [ ] **2.4.5 Implement Query Suggestions**
  - [ ] Pre-populate example queries for new users
  - [ ] Suggest queries based on KB content
  - [ ] Show popular/recent queries
  - [ ] Add query autocomplete

**Output**: Enhanced chatbot with intelligent features

---

## Part 3: Integration and Deployment

### Phase 3.1: System Integration

**Goal**: Integrate RAG and chatbot with existing system

#### Subtasks

- [ ] **3.1.1 Update Navigation**
  - [ ] Add "Knowledge Bases" menu item
  - [ ] Add "AI Chat" menu item
  - [ ] Update dashboard with KB statistics widget
  - [ ] Add quick links to chat from file detail pages
  
- [ ] **3.1.2 Link Markdown Conversion to RAG**
  - [ ] Add "Index in Knowledge Base" option on file detail page
  - [ ] Add bulk "Index to KB" action in database browser
  - [ ] Auto-index option in markdown conversion task
  - [ ] Add KB selection in conversion task form
  
- [ ] **3.1.3 Add KB Status to File Details**
  - [ ] Show which KBs contain each file
  - [ ] Display indexing status and date
  - [ ] Add "Ask about this document" button (opens chat)
  - [ ] Show chunk count and token statistics
  
- [ ] **3.1.4 Implement Permissions**
  - [ ] KB management requires CONFIG_WRITE_AUTH_TOKEN
  - [ ] Chat access based on REQUIRE_AUTH setting
  - [ ] Guest users can chat in read-only mode
  - [ ] Admin-only features (delete KB, view usage stats)

**Output**: Fully integrated system with seamless workflows

---

### Phase 3.2: Documentation

**Goal**: Provide comprehensive documentation

#### Subtasks

- [ ] **3.2.1 User Documentation**
  - [ ] Write RAG_KNOWLEDGE_BASE_GUIDE.md
    - What is RAG and how it works
    - How to create and manage knowledge bases
    - Best practices for indexing documents
    - Troubleshooting common issues
  - [ ] Write AI_CHATBOT_USER_GUIDE.md
    - How to use the chatbot
    - Understanding different modes
    - How to interpret citations
    - Tips for effective queries
  
- [ ] **3.2.2 Developer Documentation**
  - [ ] Write RAG_DEVELOPER_GUIDE.md
    - RAG module architecture
    - Extending with new embedding models
    - Custom chunking strategies
    - Performance tuning
  - [ ] Write CHATBOT_DEVELOPER_GUIDE.md
    - Chatbot module architecture
    - Adding new LLM providers
    - Customizing prompts
    - Implementing new chatbot modes
  
- [ ] **3.2.3 API Documentation**
  - [ ] Document RAG API endpoints
  - [ ] Document chatbot API endpoints
  - [ ] Provide example requests/responses
  - [ ] Add OpenAPI/Swagger specification
  
- [ ] **3.2.4 Configuration Guide**
  - [ ] Document environment variables
  - [ ] Explain configuration options
  - [ ] Provide deployment configurations
  - [ ] Add troubleshooting section

**Output**: Complete documentation suite

---

### Phase 3.3: Testing and Quality Assurance

**Goal**: Ensure system quality and reliability

#### Subtasks

- [ ] **3.3.1 End-to-End Testing**
  - [ ] Test full workflow: markdown conversion → indexing → chat
  - [ ] Test multi-KB scenarios
  - [ ] Test different chatbot modes
  - [ ] Test conversation history
  - [ ] Test citation accuracy
  
- [ ] **3.3.2 User Acceptance Testing**
  - [ ] Create test scenarios for end users
  - [ ] Gather feedback on UI/UX
  - [ ] Test with real actuarial queries
  - [ ] Measure user satisfaction
  
- [ ] **3.3.3 Performance Testing**
  - [ ] Load test chatbot API (concurrent users)
  - [ ] Benchmark query latency at scale
  - [ ] Test with large knowledge bases (10,000+ files)
  - [ ] Measure memory and CPU usage
  
- [ ] **3.3.4 Security Testing**
  - [ ] Test authentication and authorization
  - [ ] Verify input sanitization (XSS, injection)
  - [ ] Test rate limiting
  - [ ] Review API key handling
  - [ ] Run CodeQL security scan

**Output**: Validated, production-ready system

---

### Phase 3.4: Deployment

**Goal**: Deploy to production with monitoring

#### Subtasks

- [ ] **3.4.1 Docker Configuration**
  - [ ] Create Dockerfile for RAG/chatbot dependencies
  - [ ] Update docker-compose.yml
  - [ ] Add environment variable configuration
  - [ ] Test containerized deployment
  
- [ ] **3.4.2 Database Migration**
  - [ ] Create migration scripts for new tables
  - [ ] Test migration on staging database
  - [ ] Implement rollback procedures
  - [ ] Document migration process
  
- [ ] **3.4.3 Monitoring and Logging**
  - [ ] Add metrics for RAG operations (indexing time, query latency)
  - [ ] Add metrics for chatbot (queries/min, response time, error rate)
  - [ ] Set up alerting for failures
  - [ ] Create monitoring dashboard
  
- [ ] **3.4.4 Production Deployment**
  - [ ] Deploy to staging environment
  - [ ] Run smoke tests
  - [ ] Deploy to production
  - [ ] Monitor for issues
  - [ ] Communicate to users

**Output**: Production deployment with monitoring

---

## Part 4: Optional Enhancements (Future Phases)

### Phase 4.1: GraphRAG Implementation

- [ ] Research Microsoft GraphRAG architecture
- [ ] Implement entity extraction from documents
- [ ] Build knowledge graph representation
- [ ] Integrate graph queries with vector search
- [ ] Compare performance vs. traditional RAG

### Phase 4.2: Advanced Embeddings

- [ ] Support custom fine-tuned embedding models
- [ ] Implement multi-language embeddings
- [ ] Add domain-specific embedding models
- [ ] Implement hybrid embeddings (dense + sparse)

### Phase 4.3: Chatbot Improvements

- [ ] Add voice input/output
- [ ] Implement proactive suggestions
- [ ] Add image/diagram understanding
- [ ] Implement multi-modal responses
- [ ] Add conversational analytics

### Phase 4.4: Collaboration Features

- [ ] Share conversations with team members
- [ ] Collaborative knowledge base curation
- [ ] Feedback mechanism for improving responses
- [ ] Usage analytics and insights

---

## Technical Stack Summary

### Core Technologies
- **Vector Database**: FAISS (Facebook AI Similarity Search)
- **Embeddings**: OpenAI text-embedding-3-large
- **LLM**: OpenAI GPT-4 / GPT-4-turbo
- **Chunking**: tiktoken (OpenAI tokenizer)
- **Backend**: Python 3.10+, Flask
- **Frontend**: HTML/CSS/JavaScript (vanilla JS)
- **Database**: SQLite (local) / PostgreSQL (production)
- **Storage**: Filesystem for FAISS indices

### Python Dependencies (to add)
```
faiss-cpu>=1.7.4
tiktoken>=0.5.0
openai>=1.10.0
sentence-transformers>=2.3.0  # optional, for local embeddings
langchain>=0.1.0  # optional, if using LangChain
numpy>=1.24.0
```

### Configuration
```env
# RAG Settings
RAG_EMBEDDING_MODEL=text-embedding-3-large
RAG_CHUNK_SIZE=500
RAG_CHUNK_OVERLAP=80
RAG_SIMILARITY_THRESHOLD=0.4
RAG_INDEX_BATCH_SIZE=64

# Chatbot Settings
CHATBOT_MODEL=gpt-4-turbo
CHATBOT_MAX_CONTEXT_MESSAGES=10
CHATBOT_TEMPERATURE=0.7
CHATBOT_MAX_TOKENS=1000

# API Keys
OPENAI_API_KEY=sk-...
```

---

## Success Metrics

### Phase 1 (RAG Database)
- [ ] Successfully index 100+ markdown documents
- [ ] Achieve <5 seconds indexing time per document
- [ ] Maintain >95% chunking quality (no broken chunks)
- [ ] Support 10+ concurrent indexing operations

### Phase 2 (Chatbot)
- [ ] Achieve <2 seconds average query latency
- [ ] Maintain >90% citation accuracy
- [ ] Achieve <5% hallucination rate
- [ ] Support 50+ concurrent chat sessions
- [ ] Achieve >80% user satisfaction score

### Phase 3 (Integration)
- [ ] Zero downtime deployment
- [ ] <1% error rate in production
- [ ] Complete documentation coverage
- [ ] >80% test coverage

---

## Risk Management

### Technical Risks
1. **Risk**: FAISS index becomes too large (>10GB)
   - **Mitigation**: Implement index sharding, compression, or move to Pinecone/Weaviate
   
2. **Risk**: OpenAI API rate limits or costs
   - **Mitigation**: Implement caching, batching, and fallback to local models
   
3. **Risk**: Poor retrieval quality (irrelevant results)
   - **Mitigation**: Fine-tune similarity threshold, implement hybrid search, add relevance feedback

4. **Risk**: Hallucinations in chatbot responses
   - **Mitigation**: Strong system prompts, citation requirements, confidence thresholds

### Operational Risks
1. **Risk**: High operational costs (API usage)
   - **Mitigation**: Monitor usage, set budgets, optimize queries
   
2. **Risk**: Poor user adoption
   - **Mitigation**: User training, clear documentation, intuitive UI
   
3. **Risk**: Data privacy concerns
   - **Mitigation**: Clear data handling policies, option for local-only models

---

## Timeline Estimate

### Conservative Estimate (Full-time developer)
- **Phase 1.1-1.2**: 2-3 weeks (RAG core)
- **Phase 1.3-1.4**: 1-2 weeks (UI and testing)
- **Phase 2.1-2.2**: 2-3 weeks (Chatbot core)
- **Phase 2.3-2.4**: 1-2 weeks (Chat UI)
- **Phase 3**: 1-2 weeks (Integration, docs, deployment)

**Total**: 8-12 weeks for MVP

### Phased Rollout (Recommended)
- **MVP (4-6 weeks)**: Basic RAG + Simple chatbot
  - Single KB, basic chunking, OpenAI embeddings
  - Simple chat interface, no multi-turn conversations
  - Essential documentation
- **Phase 2 (3-4 weeks)**: Enhanced features
  - Multiple KBs, advanced UI, conversation history
  - Multiple chatbot modes, better prompts
- **Phase 3 (2-3 weeks)**: Advanced features
  - GraphRAG experimentation, analytics, optimizations

---

## Next Steps

1. **Review this plan** with stakeholders and get approval
2. **Set up development environment** with required dependencies
3. **Create project board** in GitHub with all subtasks
4. **Start with Phase 1.1** (RAG architecture research)
5. **Weekly status updates** and plan adjustments as needed

---

## References

1. **AI_Knowledge_Base**: https://github.com/ferryhe/AI_Knowledge_Base
   - Reference implementation for FAISS-based RAG
   - Proven chunking and retrieval strategies
   
2. **Microsoft GraphRAG**: https://github.com/microsoft/graphrag
   - Advanced RAG with knowledge graphs
   - Future enhancement consideration
   
3. **LangChain Documentation**: https://python.langchain.com/
   - Optional framework for RAG and chatbot
   
4. **FAISS Documentation**: https://github.com/facebookresearch/faiss
   - Vector similarity search library

5. **OpenAI Embeddings Guide**: https://platform.openai.com/docs/guides/embeddings
   - Best practices for embeddings

---

**Document Version**: 1.0  
**Last Updated**: 2026-02-11  
**Status**: Draft - Awaiting Review
