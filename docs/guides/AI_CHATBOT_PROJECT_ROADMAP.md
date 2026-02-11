# AI Chatbot Project Roadmap - Quick Reference

**Status**: Planning Phase  
**Full Details**: See `docs/20260211_AI_CHATBOT_RAG_IMPLEMENTATION_PLAN.md`

---

## Project Overview

Building an AI-powered chatbot with RAG (Retrieval-Augmented Generation) capabilities for answering questions from actuarial documents. The system will:

1. **Convert documents to searchable knowledge bases** using vector embeddings
2. **Intelligently answer questions** with citations from source documents  
3. **Support multiple knowledge bases** for different document categories
4. **Provide a user-friendly chat interface** with conversation history

**Reference Project**: https://github.com/ferryhe/AI_Knowledge_Base

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Web Interface                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   KB Mgmt    │  │  Chat UI     │  │ File Browser │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                     Backend Services                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ RAG Engine   │  │  Chatbot     │  │   Storage    │     │
│  │ (FAISS)      │  │  (GPT-4)     │  │  (SQLite/PG) │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                  External Services                          │
│  ┌──────────────┐  ┌──────────────┐                        │
│  │   OpenAI     │  │   Markdown   │                        │
│  │  Embeddings  │  │  Conversion  │                        │
│  └──────────────┘  └──────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Checklist

### Phase 1: RAG Database (4-5 weeks)

#### Week 1-2: Core RAG Infrastructure
- [ ] Research and select RAG architecture (FAISS-based recommended)
- [ ] Design database schema for knowledge bases and chunks
- [ ] Create `ai_actuarial/rag/` module structure
- [ ] Implement token-based chunking (500 tokens, 80 overlap)
- [ ] Implement OpenAI embedding integration
- [ ] Build FAISS vector store manager
- [ ] Write unit tests for core components

#### Week 3-4: Management Interface
- [ ] Design UI for KB management
- [ ] Implement backend API endpoints
- [ ] Create KB list and detail pages
- [ ] Add file selection with category filters
- [ ] Integrate with existing task system
- [ ] Add indexing task execution
- [ ] Write integration tests

#### Week 5: Testing & Optimization
- [ ] Test with real actuarial documents
- [ ] Performance benchmarking
- [ ] Optimize indexing speed
- [ ] Validate retrieval quality
- [ ] Document Phase 1 results

**Milestone**: Users can create knowledge bases and index markdown files

---

### Phase 2: AI Chatbot (4-5 weeks)

#### Week 6-7: Core Chatbot Engine
- [ ] Design chatbot architecture and modes
- [ ] Create `ai_actuarial/chatbot/` module
- [ ] Implement RAG retrieval integration
- [ ] Integrate OpenAI GPT-4 API
- [ ] Develop system prompts for different modes
- [ ] Implement conversation manager
- [ ] Add query routing logic
- [ ] Write unit tests

#### Week 8-9: Chat Interface
- [ ] Design chat UI/UX
- [ ] Implement backend chat API
- [ ] Create chat page with message display
- [ ] Add KB and mode selectors
- [ ] Implement conversation history
- [ ] Add citation display and linking
- [ ] Test multi-turn conversations

#### Week 10: Advanced Features
- [ ] Implement semantic query analysis
- [ ] Add multi-KB query support
- [ ] Implement response quality checks
- [ ] Add follow-up suggestions
- [ ] Performance optimization
- [ ] Write end-to-end tests

**Milestone**: Users can ask questions and get cited answers from knowledge bases

---

### Phase 3: Integration & Deployment (2-3 weeks)

#### Week 11: System Integration
- [ ] Update navigation with RAG and Chat links
- [ ] Link markdown conversion to RAG indexing
- [ ] Add KB status to file detail pages
- [ ] Implement permissions and access control
- [ ] Test complete workflow end-to-end

#### Week 12-13: Documentation & Deployment
- [ ] Write user documentation
- [ ] Write developer documentation
- [ ] Create API documentation
- [ ] Update Docker configuration
- [ ] Create database migration scripts
- [ ] Set up monitoring and logging
- [ ] Deploy to staging
- [ ] Deploy to production
- [ ] User training and rollout

**Milestone**: Production-ready AI chatbot system with full documentation

---

## Technology Stack

### Core Components
| Component | Technology | Purpose |
|-----------|-----------|---------|
| Vector Store | FAISS | Fast similarity search |
| Embeddings | OpenAI text-embedding-3-large | Document vectorization |
| LLM | OpenAI GPT-4 / GPT-4-turbo | Question answering |
| Chunking | tiktoken | Token-based text splitting |
| Backend | Flask + Python 3.10+ | Web API |
| Database | SQLite / PostgreSQL | Metadata storage |
| Frontend | HTML/CSS/JavaScript | User interface |

### Required Dependencies
```bash
# Add to requirements.txt
faiss-cpu>=1.7.4
tiktoken>=0.5.0
openai>=1.10.0
numpy>=1.24.0
sentence-transformers>=2.3.0  # optional
```

### Environment Variables
```bash
# Add to .env
RAG_EMBEDDING_MODEL=text-embedding-3-large
RAG_CHUNK_SIZE=500
RAG_CHUNK_OVERLAP=80
RAG_SIMILARITY_THRESHOLD=0.4

CHATBOT_MODEL=gpt-4-turbo
CHATBOT_TEMPERATURE=0.7
CHATBOT_MAX_TOKENS=1000

OPENAI_API_KEY=sk-...
```

---

## Key Features

### RAG Knowledge Base Management
- ✅ Create multiple knowledge bases for different categories
- ✅ Select files by category for indexing
- ✅ View indexing status and statistics
- ✅ Incremental updates (add files without full rebuild)
- ✅ Monitor indexing jobs in Task Center
- ✅ Track chunks, tokens, and index size

### AI Chatbot
- ✅ Multiple chatbot modes (Expert, Summary, Tutorial)
- ✅ Automatic KB selection based on query
- ✅ Manual KB and mode selection
- ✅ Multi-turn conversations with context
- ✅ Citations with links to source documents
- ✅ Conversation history and persistence
- ✅ Hallucination prevention
- ✅ Streaming responses (optional)

### Integration
- ✅ Seamless workflow: Convert → Index → Chat
- ✅ Direct chat from file detail pages
- ✅ Bulk operations from database browser
- ✅ Role-based access control
- ✅ Audit logging

---

## Success Criteria

### Phase 1 (RAG)
- [ ] Successfully index 100+ documents
- [ ] Indexing speed: <5 seconds per document
- [ ] Chunk quality: >95% (no broken chunks)
- [ ] Support 10+ concurrent operations

### Phase 2 (Chatbot)
- [ ] Query latency: <2 seconds average
- [ ] Citation accuracy: >90%
- [ ] Hallucination rate: <5%
- [ ] Concurrent users: 50+
- [ ] User satisfaction: >80%

### Phase 3 (Production)
- [ ] Zero downtime deployment
- [ ] Error rate: <1%
- [ ] Test coverage: >80%
- [ ] Complete documentation

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Large FAISS indices (>10GB) | High | Index sharding, compression, cloud vector DB |
| OpenAI API costs/limits | High | Caching, batching, local model fallback |
| Poor retrieval quality | Medium | Fine-tune threshold, hybrid search, feedback |
| Hallucinations | Medium | Strong prompts, citations, confidence scores |
| High operational costs | Medium | Usage monitoring, budgets, optimization |
| Low user adoption | Medium | Training, docs, intuitive UI |

---

## Comparison with Reference Project

### Similarities (Adopting Best Practices)
- ✅ FAISS-based vector store
- ✅ OpenAI embeddings (text-embedding-3-large)
- ✅ Token-based chunking (500 tokens, 80 overlap)
- ✅ Hallucination prevention in prompts
- ✅ Citation tracking and display
- ✅ Similarity threshold filtering

### Differences (Our Enhancements)
- 🔵 **Multiple knowledge bases** (vs. single KB)
- 🔵 **Web-based management UI** (vs. CLI scripts)
- 🔵 **Integrated with existing system** (seamless workflow)
- 🔵 **Category-based file selection** (leverage existing taxonomy)
- 🔵 **Multi-mode chatbot** (Expert, Summary, Tutorial)
- 🔵 **Conversation history** (persistent, searchable)
- 🔵 **Task system integration** (background jobs, logging)
- 🔵 **Role-based access control** (auth integration)

---

## Development Setup

### Prerequisites
```bash
# Python 3.10+
python --version

# Install dependencies
cd /path/to/AI_actuarial_inforsearch
pip install -r requirements.txt

# Add new dependencies for RAG/chatbot
pip install faiss-cpu tiktoken openai
```

### Environment Configuration
```bash
# Copy .env.example to .env
cp .env.example .env

# Add OpenAI API key
echo "OPENAI_API_KEY=sk-..." >> .env

# Add RAG settings
echo "RAG_CHUNK_SIZE=500" >> .env
echo "RAG_CHUNK_OVERLAP=80" >> .env
```

### Running Tests
```bash
# Run existing tests
pytest test_markdown.py -v

# Run RAG tests (after implementation)
pytest tests/test_rag.py -v

# Run chatbot tests (after implementation)
pytest tests/test_chatbot.py -v
```

---

## Next Steps

1. **Review this roadmap** and detailed plan with team
2. **Get stakeholder approval** for approach and timeline
3. **Set up project board** in GitHub Issues/Projects
4. **Assign team members** to different phases
5. **Start Phase 1.1** - RAG architecture research
6. **Weekly check-ins** to track progress and adjust plan

---

## Resources

### Documentation
- 📄 Detailed Plan: `docs/20260211_AI_CHATBOT_RAG_IMPLEMENTATION_PLAN.md`
- 📄 Reference Project: https://github.com/ferryhe/AI_Knowledge_Base
- 📄 Reference README: https://github.com/ferryhe/AI_Knowledge_Base/blob/main/AI_Agent/README.md
- 📄 RAG Improvements: https://github.com/ferryhe/AI_Knowledge_Base/blob/main/AI_Agent/IMPROVEMENTS.md

### Technical References
- 🔗 FAISS: https://github.com/facebookresearch/faiss
- 🔗 OpenAI Embeddings: https://platform.openai.com/docs/guides/embeddings
- 🔗 LangChain: https://python.langchain.com/
- 🔗 Microsoft GraphRAG: https://github.com/microsoft/graphrag

### Project Files
- 📁 Current codebase: `ai_actuarial/`
- 📁 Web interface: `ai_actuarial/web/`
- 📁 Markdown conversion: `doc_to_md/`
- 📁 Configuration: `config/`

---

## Questions & Support

For questions or clarifications about this roadmap:

1. **Review detailed plan**: See `docs/20260211_AI_CHATBOT_RAG_IMPLEMENTATION_PLAN.md` for comprehensive details
2. **Check reference project**: Review AI_Knowledge_Base implementation
3. **Consult existing code**: Look at markdown conversion feature for similar patterns
4. **Create GitHub issue**: For specific technical questions or concerns

---

**Last Updated**: 2026-02-11  
**Status**: Ready for Review  
**Estimated Timeline**: 10-13 weeks for full implementation
