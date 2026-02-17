# Configuration Migration Plan: From Environment Variables to Centralized Configuration

**Date**: 2026-02-15  
**Purpose**: Migrate from environment variable-based configuration to centralized YAML-based configuration  
**Scope**: All application configuration except sensitive credentials (API keys, tokens, passwords)

## Executive Summary

Currently, the application stores both **configuration** (model choices, timeouts, feature flags) and **secrets** (API keys, auth tokens) in `.env` files. This creates maintenance issues:

- Configuration changes require editing `.env` and restarting the application
- No web UI for non-technical users to adjust settings
- Configuration is not version-controlled
- Architectural gap: Web UI saves to `sites.yaml` but backend loads from environment variables

**Goal**: Migrate all non-sensitive configuration to `sites.yaml` so users can manage it via the web UI. Only sensitive credentials remain in `.env`.

---

## Current Architecture

### Configuration Sources (As-Is)

1. **`.env` file** - Contains EVERYTHING:
   - API keys (sensitive) ✓ Should stay here
   - Model selections (configuration) ✗ Should move
   - Timeouts/retries (configuration) ✗ Should move
   - Feature flags (configuration) ✗ Should move
   - Thresholds (configuration) ✗ Should move

2. **`sites.yaml`** - Contains:
   - Crawler site definitions
   - Search queries
   - Default crawler settings
   - **NEW**: `ai_config` section (from web UI) - NOT YET USED BY BACKEND

3. **`categories.yaml`** - Contains:
   - Document classification rules
   - Category definitions
   - AI keywords

### Backend Modules Loading Configuration

| Module | Current Method | Loads From |
|--------|---------------|------------|
| `config/settings.py` | `BaseSettings` (pydantic-settings) | `.env` |
| `ai_actuarial/chatbot/config.py` | `ChatbotConfig.from_env()` | `.env` |
| `ai_actuarial/rag/config.py` | `RAGConfig.from_env()` | `.env` |
| `ai_actuarial/catalog_llm.py` | Direct `os.getenv()` | `.env` |
| Web UI | Reads `sites.yaml`, writes `ai_config` | `sites.yaml` (disconnected!) |

### The Problem: Architectural Disconnect

```
┌─────────────────┐           ┌──────────────────┐
│   Web UI        │ writes to │  sites.yaml      │
│  (Settings Tab) │──────────>│  ai_config:      │
│                 │           │    chatbot: {...}│
└─────────────────┘           │    embeddings:   │
                              └──────────────────┘
                                        ↓
                                        ↓ NOT READ!
                                        ↓
┌─────────────────┐           ┌──────────────────┐
│ Backend Modules │  reads    │    .env          │
│  ChatbotConfig  │<──────────│  CHATBOT_MODEL=  │
│  RAGConfig      │           │  RAG_EMBEDDING_  │
└─────────────────┘           └──────────────────┘
```

**Result**: User changes AI models in web UI, but chatbot/RAG still use `.env` values!

---

## Target Architecture

### Configuration Sources (To-Be)

1. **`.env` file** - ONLY sensitive credentials:
   ```bash
   # API Keys (KEEP)
   OPENAI_API_KEY=sk-...
   MISTRAL_API_KEY=...
   SILICONFLOW_API_KEY=...
   BRAVE_API_KEY=...
   SERPAPI_API_KEY=...
   
   # Security Tokens (KEEP)
   CONFIG_WRITE_AUTH_TOKEN=...
   FILE_DELETION_AUTH_TOKEN=...
   FLASK_SECRET_KEY=...
   BOOTSTRAP_ADMIN_TOKEN=...
   LOGS_READ_AUTH_TOKEN=...
   
   # Database Credentials (KEEP)
   DB_PASSWORD=...  # For PostgreSQL only
   ```

2. **`sites.yaml`** - ALL non-sensitive configuration:
   ```yaml
   # AI Model Configuration (NEW STRUCTURE)
   ai_config:
     catalog:
       provider: openai
       model: gpt-4o-mini
       temperature: 0.7
       timeout_seconds: 60
     
     embeddings:
       provider: openai
       model: text-embedding-3-large
       batch_size: 64
       similarity_threshold: 0.4
     
     chatbot:
       provider: openai
       model: gpt-4-turbo
       temperature: 0.7
       max_tokens: 1000
       streaming_enabled: true
       max_context_messages: 10
       default_mode: expert
       enable_citation: true
       min_citation_score: 0.4
       max_citations_per_response: 5
     
     ocr:
       provider: local
       model: docling
       # Provider-specific settings
       mistral:
         max_pdf_tokens: 9000
         max_pages_per_chunk: 25
         extract_header: true
         extract_footer: true
       siliconflow:
         max_input_tokens: 3500
         chunk_overlap_tokens: 200
   
   # RAG Configuration (NEW)
   rag_config:
     chunk_strategy: semantic_structure
     max_chunk_tokens: 800
     min_chunk_tokens: 100
     preserve_headers: true
     preserve_citations: true
     index_type: Flat
   
   # Feature Flags (NEW)
   features:
     enable_file_deletion: false
     require_auth: false
     enable_csrf: false
     enable_security_headers: true
     expose_error_details: false
     enable_global_logs_api: false
     enable_rate_limiting: false
   
   # Web Server Configuration (NEW)
   server:
     host: 0.0.0.0
     port: 5000
     max_content_length: 52428800  # 50MB
     flask_env: production
     flask_debug: false
   
   # Database Configuration (NEW)
   database:
     type: sqlite
     path: data/index.db
     # For PostgreSQL:
     # type: postgresql
     # host: localhost
     # port: 5432
     # database: ai_actuarial
     # username: postgres
     # password: from .env
   
   # Existing sections (KEEP)
   defaults: {...}
   paths: {...}
   search: {...}
   sites: [...]
   ```

3. **`categories.yaml`** - KEEP AS-IS

---

## Migration Strategy

### Phase 1: Infrastructure Setup

**Goal**: Create configuration loader that reads from `sites.yaml` with `.env` fallback

**Tasks**:
1. Create `config/yaml_config.py` - Configuration loader module
2. Add `load_ai_config()`, `load_rag_config()`, `load_features()` functions
3. Implement fallback logic: Try `sites.yaml` first, then `.env`, then defaults
4. Add validation and error handling

**Files to Create**:
- `config/yaml_config.py` (new)

**Backward Compatibility**: YES - Falls back to `.env` if `sites.yaml` section missing

---

### Phase 2: Backend Module Migration

**Goal**: Update backend modules to use new configuration loader

#### 2.1 Chatbot Configuration

**Current**:
```python
# ai_actuarial/chatbot/config.py
config = ChatbotConfig.from_env()  # Reads CHATBOT_* from .env
```

**New**:
```python
# ai_actuarial/chatbot/config.py
@classmethod
def from_yaml(cls, yaml_config: dict) -> "ChatbotConfig":
    """Load from sites.yaml ai_config.chatbot section."""
    chatbot = yaml_config.get("ai_config", {}).get("chatbot", {})
    return cls(
        model=chatbot.get("model", "gpt-4-turbo"),
        temperature=chatbot.get("temperature", 0.7),
        # ... map all fields
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),  # Still from .env!
    )

@classmethod
def from_config(cls) -> "ChatbotConfig":
    """Load from sites.yaml with .env fallback."""
    from config.yaml_config import load_yaml_config
    yaml_config = load_yaml_config()
    
    if "ai_config" in yaml_config and "chatbot" in yaml_config["ai_config"]:
        return cls.from_yaml(yaml_config)
    else:
        # Fallback to .env for backward compatibility
        return cls.from_env()
```

**Files to Modify**:
- `ai_actuarial/chatbot/config.py`

#### 2.2 RAG Configuration

**Current**:
```python
# ai_actuarial/rag/config.py
config = RAGConfig.from_env()  # Reads RAG_* from .env
```

**New**:
```python
# ai_actuarial/rag/config.py
@classmethod
def from_yaml(cls, yaml_config: dict) -> "RAGConfig":
    """Load from sites.yaml rag_config section."""
    rag_cfg = yaml_config.get("rag_config", {})
    ai_cfg = yaml_config.get("ai_config", {}).get("embeddings", {})
    
    return cls(
        chunk_strategy=rag_cfg.get("chunk_strategy", "semantic_structure"),
        max_chunk_tokens=rag_cfg.get("max_chunk_tokens", 800),
        # ... map rag_config fields
        embedding_provider=ai_cfg.get("provider", "openai"),
        embedding_model=ai_cfg.get("model", "text-embedding-3-large"),
        # ... map ai_config.embeddings fields
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),  # Still from .env!
    )

@classmethod
def from_config(cls) -> "RAGConfig":
    """Load from sites.yaml with .env fallback."""
    from config.yaml_config import load_yaml_config
    yaml_config = load_yaml_config()
    
    if "rag_config" in yaml_config or "ai_config" in yaml_config:
        return cls.from_yaml(yaml_config)
    else:
        return cls.from_env()
```

**Files to Modify**:
- `ai_actuarial/rag/config.py`

#### 2.3 Catalog LLM

**Current**:
```python
# ai_actuarial/catalog_llm.py
model = os.getenv("OPENAI_DEFAULT_MODEL", "gpt-4o-mini")
temperature = float(os.getenv("CATALOG_TEMPERATURE", "0.7"))
```

**New**:
```python
# ai_actuarial/catalog_llm.py
from config.yaml_config import load_ai_config

ai_config = load_ai_config()
catalog = ai_config.get("catalog", {})
model = catalog.get("model", "gpt-4o-mini")
temperature = catalog.get("temperature", 0.7)
```

**Files to Modify**:
- `ai_actuarial/catalog_llm.py`

#### 2.4 OCR Engines (Mistral, SiliconFlow)

**Files to Modify**:
- `doc_to_md/engines/mistral_engine.py`
- `doc_to_md/engines/siliconflow_engine.py`

---

### Phase 3: Web UI Integration

**Goal**: Remove architectural gap - web UI changes immediately affect backend

#### 3.1 Update API Endpoints

**Current**: POST to `/api/config/ai-models` saves to `sites.yaml`, but backend doesn't read it

**New**: After saving to `sites.yaml`, invalidate configuration cache so next request loads new values

```python
# ai_actuarial/web/app.py
@app.route("/api/config/ai-models", methods=["POST"])
def api_config_ai_models_update():
    # ... save to sites.yaml ...
    _write_yaml(_get_sites_config_path(), config_data)
    
    # NEW: Invalidate configuration cache
    from config.yaml_config import invalidate_config_cache
    invalidate_config_cache()
    
    return jsonify({"success": True})
```

**Files to Modify**:
- `ai_actuarial/web/app.py` - Add cache invalidation

#### 3.2 Add Web UI for Additional Settings

**Current**: Web UI only shows AI model selection

**New**: Add tabs for:
- RAG Settings (chunking, similarity threshold, index type)
- Feature Flags (enable_file_deletion, require_auth, etc.)
- Server Settings (host, port, max_content_length)

**Files to Modify**:
- `ai_actuarial/web/templates/settings.html` - Add new tabs
- `ai_actuarial/web/app.py` - Add API endpoints for new settings

---

### Phase 4: Environment Variable Cleanup

**Goal**: Remove non-sensitive configuration from `.env.example`

**Tasks**:
1. Update `.env.example` to only include sensitive credentials
2. Add migration script to extract configuration from old `.env` to `sites.yaml`
3. Update documentation

**Files to Modify**:
- `.env.example` - Remove non-sensitive config
- Add `scripts/migrate_env_to_yaml.py` - Migration script
- Update `README.md` - Document new configuration approach

**New `.env.example`**:
```bash
# ===================================
# SENSITIVE CREDENTIALS ONLY
# Copy this file to .env and fill in your actual values
# NEVER commit .env file to version control!
# ===================================

# ===================================
# API Keys
# ===================================
OPENAI_API_KEY=
MISTRAL_API_KEY=
SILICONFLOW_API_KEY=
BRAVE_API_KEY=
SERPAPI_API_KEY=

# ===================================
# Security Tokens
# ===================================
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
CONFIG_WRITE_AUTH_TOKEN=
FILE_DELETION_AUTH_TOKEN=
FLASK_SECRET_KEY=
BOOTSTRAP_ADMIN_TOKEN=
BOOTSTRAP_ADMIN_SUBJECT=bootstrap-admin
LOGS_READ_AUTH_TOKEN=

# ===================================
# Database Credentials (PostgreSQL only)
# ===================================
# DB_PASSWORD=your-strong-db-password

# ===================================
# Optional API Base URLs (override defaults)
# ===================================
# OPENAI_BASE_URL=https://api.openai.com/v1
# SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1

# ===================================
# CONFIGURATION MOVED TO sites.yaml
# Edit via Web UI Settings page or edit config/sites.yaml directly
# ===================================
# - AI model selections (catalog, embeddings, chatbot, ocr)
# - RAG settings (chunking, similarity, index type)
# - Feature flags (auth, deletion, rate limiting)
# - Server settings (host, port, max upload size)
# - Timeouts, retries, temperature, tokens, etc.
```

---

## Implementation Phases

### Phase 1: Infrastructure (Week 1)

**Priority**: HIGH  
**Effort**: 3 days  
**Risk**: LOW

1. Create `config/yaml_config.py`
2. Implement configuration loader with caching
3. Add unit tests for loader
4. Document configuration loading logic

**Deliverables**:
- `config/yaml_config.py` with functions:
  - `load_yaml_config()` - Load full sites.yaml
  - `load_ai_config()` - Load ai_config section
  - `load_rag_config()` - Load rag_config section
  - `load_features()` - Load features section
  - `invalidate_config_cache()` - Clear cache
- Unit tests in `tests/test_yaml_config.py`

---

### Phase 2: Backend Migration (Week 1-2)

**Priority**: HIGH  
**Effort**: 5 days  
**Risk**: MEDIUM (backward compatibility)

1. Update `ChatbotConfig` to support `from_yaml()` + `from_config()`
2. Update `RAGConfig` to support `from_yaml()` + `from_config()`
3. Update `catalog_llm.py` to use new loader
4. Update OCR engines to use new loader
5. Update all instantiation sites to use `from_config()`
6. Add integration tests

**Deliverables**:
- Modified configuration classes with dual loading
- Backward compatibility with `.env`
- Integration tests confirming both paths work
- Migration complete for chatbot, RAG, catalog, OCR

---

### Phase 3: Web UI Integration (Week 2)

**Priority**: HIGH  
**Effort**: 3 days  
**Risk**: LOW

1. Add cache invalidation to API endpoints
2. Add new settings tabs (RAG, Features, Server)
3. Add API endpoints for new settings sections
4. Update frontend JavaScript for new tabs
5. Test end-to-end: UI change → backend immediately uses new value

**Deliverables**:
- Cache invalidation working
- Additional settings tabs in UI
- Full web UI coverage of `sites.yaml` configuration

---

### Phase 4: Cleanup & Documentation (Week 3)

**Priority**: MEDIUM  
**Effort**: 2 days  
**Risk**: LOW

1. Clean up `.env.example`
2. Create migration script `scripts/migrate_env_to_yaml.py`
3. Update documentation (README, setup guides)
4. Add deprecation warnings for `.env` configuration

**Deliverables**:
- New `.env.example` with only sensitive credentials
- Migration script for existing deployments
- Updated documentation
- Deprecation notices in logs

---

## Backward Compatibility Strategy

### Gradual Migration Approach

1. **First Request**: Try load from `sites.yaml`
2. **Fallback**: If section missing, load from `.env`
3. **Warning**: Log deprecation warning if `.env` is used
4. **Migration**: Provide script to one-time migrate `.env` → `sites.yaml`

### Example Fallback Logic

```python
# config/yaml_config.py
def load_ai_config() -> dict:
    """Load AI configuration with fallback."""
    yaml_config = load_yaml_config()
    
    if "ai_config" in yaml_config:
        # New approach: Use sites.yaml
        return yaml_config["ai_config"]
    else:
        # Fallback: Extract from environment
        logger.warning(
            "ai_config not found in sites.yaml, using .env fallback. "
            "Run 'python scripts/migrate_env_to_yaml.py' to migrate."
        )
        return extract_ai_config_from_env()
```

### Migration Script

```python
# scripts/migrate_env_to_yaml.py
"""One-time migration script to move configuration from .env to sites.yaml"""

import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

def migrate():
    load_dotenv()
    
    # Load current sites.yaml
    sites_path = Path("config/sites.yaml")
    with open(sites_path) as f:
        config = yaml.safe_load(f)
    
    # Extract configuration from environment
    config["ai_config"] = {
        "catalog": {
            "provider": "openai",
            "model": os.getenv("OPENAI_DEFAULT_MODEL", "gpt-4o-mini"),
            "temperature": float(os.getenv("CATALOG_TEMPERATURE", "0.7")),
            "timeout_seconds": int(os.getenv("OPENAI_TIMEOUT_SECONDS", "60")),
        },
        "embeddings": {
            "provider": os.getenv("RAG_EMBEDDING_PROVIDER", "openai"),
            "model": os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-large"),
            "batch_size": int(os.getenv("RAG_EMBEDDING_BATCH_SIZE", "64")),
            "similarity_threshold": float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.4")),
        },
        "chatbot": {
            "provider": "openai",
            "model": os.getenv("CHATBOT_MODEL", "gpt-4-turbo"),
            "temperature": float(os.getenv("CHATBOT_TEMPERATURE", "0.7")),
            "max_tokens": int(os.getenv("CHATBOT_MAX_TOKENS", "1000")),
            # ... extract all chatbot settings
        },
        "ocr": {
            "provider": os.getenv("DEFAULT_ENGINE", "local"),
            "model": "docling",  # Default for local
        },
    }
    
    config["rag_config"] = {
        "chunk_strategy": os.getenv("RAG_CHUNK_STRATEGY", "semantic_structure"),
        "max_chunk_tokens": int(os.getenv("RAG_MAX_CHUNK_TOKENS", "800")),
        "min_chunk_tokens": int(os.getenv("RAG_MIN_CHUNK_TOKENS", "100")),
        "index_type": os.getenv("RAG_INDEX_TYPE", "Flat"),
    }
    
    config["features"] = {
        "enable_file_deletion": os.getenv("ENABLE_FILE_DELETION", "false") == "true",
        "require_auth": os.getenv("REQUIRE_AUTH", "false") == "true",
        "enable_csrf": os.getenv("ENABLE_CSRF", "false") == "true",
        # ... extract all feature flags
    }
    
    # Write back to sites.yaml
    with open(sites_path, "w") as f:
        yaml.dump(config, f, sort_keys=False, allow_unicode=True)
    
    print("✓ Migration complete! Configuration moved to config/sites.yaml")
    print("  You can now remove non-sensitive values from .env")

if __name__ == "__main__":
    migrate()
```

---

## Testing Strategy

### Unit Tests

**File**: `tests/test_yaml_config.py`

```python
def test_load_yaml_config():
    """Test loading full sites.yaml"""
    config = load_yaml_config()
    assert "defaults" in config
    assert "sites" in config

def test_load_ai_config():
    """Test loading ai_config section"""
    ai_config = load_ai_config()
    assert "catalog" in ai_config
    assert "embeddings" in ai_config
    assert "chatbot" in ai_config
    assert "ocr" in ai_config

def test_fallback_to_env():
    """Test fallback to .env when sites.yaml missing sections"""
    # Remove ai_config from sites.yaml
    # Verify it loads from .env
    pass

def test_cache_invalidation():
    """Test configuration cache can be invalidated"""
    config1 = load_ai_config()
    # Modify sites.yaml
    invalidate_config_cache()
    config2 = load_ai_config()
    assert config1 != config2
```

### Integration Tests

**File**: `tests/test_config_integration.py`

```python
def test_chatbot_uses_yaml_config():
    """Test ChatbotConfig loads from sites.yaml"""
    config = ChatbotConfig.from_config()
    # Verify values come from sites.yaml, not .env
    pass

def test_rag_uses_yaml_config():
    """Test RAGConfig loads from sites.yaml"""
    config = RAGConfig.from_config()
    # Verify values come from sites.yaml
    pass

def test_web_ui_updates_backend():
    """Test web UI change immediately affects backend"""
    # 1. Get current chatbot model
    # 2. Change via POST /api/config/ai-models
    # 3. Create new ChatbotConfig instance
    # 4. Verify it uses new model
    pass
```

---

## Risks and Mitigation

### Risk 1: Breaking Existing Deployments

**Impact**: HIGH  
**Likelihood**: MEDIUM

**Mitigation**:
- Implement fallback to `.env` if `sites.yaml` sections missing
- Provide clear migration guide
- Add deprecation warnings, not hard errors
- Release migration script before enforcement

### Risk 2: Configuration Cache Staleness

**Impact**: MEDIUM  
**Likelihood**: MEDIUM

**Mitigation**:
- Implement cache invalidation on config updates
- Add TTL (time-to-live) to cache
- Log when config is reloaded
- Provide manual cache clear endpoint

### Risk 3: Loss of Configuration on Deployment

**Impact**: HIGH  
**Likelihood**: LOW

**Mitigation**:
- Document that `sites.yaml` should be in version control (unlike `.env`)
- Add configuration backup/restore functionality
- Include `sites.yaml` in deployment artifacts
- Add config validation on startup

---

## Success Criteria

1. ✅ All backend modules can load from `sites.yaml`
2. ✅ Fallback to `.env` works for backward compatibility
3. ✅ Web UI changes immediately affect backend (no restart needed)
4. ✅ Only sensitive credentials remain in `.env`
5. ✅ Configuration is version-controllable
6. ✅ Migration script successfully converts existing deployments
7. ✅ All tests pass (unit + integration)
8. ✅ Documentation updated

---

## Timeline

| Phase | Duration | Completion Date |
|-------|----------|-----------------|
| Phase 1: Infrastructure | 3 days | Week 1, Day 3 |
| Phase 2: Backend Migration | 5 days | Week 2, Day 3 |
| Phase 3: Web UI Integration | 3 days | Week 2, Day 6 |
| Phase 4: Cleanup & Documentation | 2 days | Week 3, Day 2 |
| **Total** | **13 days** | **~3 weeks** |

---

## Files to Create

1. `config/yaml_config.py` - Configuration loader
2. `scripts/migrate_env_to_yaml.py` - Migration script
3. `tests/test_yaml_config.py` - Unit tests
4. `tests/test_config_integration.py` - Integration tests
5. `docs/CONFIGURATION.md` - Configuration documentation

---

## Files to Modify

1. `ai_actuarial/chatbot/config.py` - Add `from_yaml()` and `from_config()`
2. `ai_actuarial/rag/config.py` - Add `from_yaml()` and `from_config()`
3. `ai_actuarial/catalog_llm.py` - Use new configuration loader
4. `doc_to_md/engines/mistral_engine.py` - Use new loader
5. `doc_to_md/engines/siliconflow_engine.py` - Use new loader
6. `ai_actuarial/web/app.py` - Add cache invalidation to config endpoints
7. `ai_actuarial/web/templates/settings.html` - Add new settings tabs
8. `.env.example` - Remove non-sensitive configuration
9. `README.md` - Update configuration documentation

---

## Next Steps

1. **Review this plan** with the team
2. **Create Phase 1** implementation branch
3. **Implement `config/yaml_config.py`** with unit tests
4. **Test thoroughly** with both `.env` and `sites.yaml` approaches
5. **Proceed to Phase 2** after Phase 1 approval

---

## Appendix: Configuration Schema

### sites.yaml Complete Structure (After Migration)

```yaml
# AI Model Configuration
ai_config:
  catalog:
    provider: openai  # openai, mistral, siliconflow
    model: gpt-4o-mini
    temperature: 0.7
    timeout_seconds: 60
    max_retries: 3
  
  embeddings:
    provider: openai  # openai, local
    model: text-embedding-3-large
    batch_size: 64
    similarity_threshold: 0.4
    cache_enabled: true
  
  chatbot:
    provider: openai
    model: gpt-4-turbo
    temperature: 0.7
    max_tokens: 1000
    streaming_enabled: true
    max_context_messages: 10
    default_mode: expert  # expert, summary, tutorial, comparison
    enable_citation: true
    min_citation_score: 0.4
    max_citations_per_response: 5
    enable_query_validation: true
    enable_response_validation: true
    max_query_length: 1000
  
  ocr:
    provider: local  # local, mistral, siliconflow
    model: docling  # docling, marker, mistral-ocr-latest, deepseek-ai/DeepSeek-OCR
    mistral:
      max_pdf_tokens: 9000
      max_pages_per_chunk: 25
      timeout_seconds: 60
      retry_attempts: 3
      extract_header: true
      extract_footer: true
    siliconflow:
      max_input_tokens: 3500
      chunk_overlap_tokens: 200
      timeout_seconds: 60
      retry_attempts: 3
    docling:
      max_pages: null
      raise_on_error: true
    marker:
      use_llm: false
      processors: null
      page_range: null
      extract_images: false
      llm_service: null

# RAG Configuration
rag_config:
  chunk_strategy: semantic_structure  # semantic_structure, token_based
  max_chunk_tokens: 800
  min_chunk_tokens: 100
  preserve_headers: true
  preserve_citations: true
  include_hierarchy: true
  index_type: Flat  # Flat, IVF, HNSW

# Feature Flags
features:
  enable_file_deletion: false
  require_auth: false
  enable_csrf: false
  enable_security_headers: true
  expose_error_details: false
  enable_global_logs_api: false
  enable_rate_limiting: false
  rate_limit_defaults: "200 per hour, 50 per minute"
  rate_limit_storage_uri: "memory://"
  content_security_policy: ""

# Web Server Configuration
server:
  host: 0.0.0.0
  port: 5000
  max_content_length: 52428800  # 50MB in bytes
  flask_env: production
  flask_debug: false

# Database Configuration
database:
  type: sqlite  # sqlite, postgresql
  path: data/index.db
  # PostgreSQL settings (when type: postgresql)
  host: localhost
  port: 5432
  database: ai_actuarial
  username: postgres
  # password: loaded from .env DB_PASSWORD

# Existing sections (keep as-is)
defaults:
  user_agent: '...'
  max_pages: 200
  max_depth: 2
  delay_seconds: 0.5
  keywords: [...]
  file_exts: [...]

paths:
  download_dir: data/files
  db: data/index.db
  last_run_new: data/last_run_new.json
  updates_dir: data/updates

search:
  enabled: true
  max_results: 5
  delay_seconds: 0.5
  languages: [en, zh]
  country: us
  exclude_keywords: [...]
  queries: [...]

sites:
  - name: "..."
    url: "..."
    keywords: [...]
    # ... site definitions
```

---

## Questions for Review

1. **Priority**: Should we implement all phases, or stop after Phase 2 (backend migration)?
2. **Timing**: Is 3 weeks acceptable, or should we prioritize faster delivery?
3. **Scope**: Should we include database configuration in migration, or keep in `.env`?
4. **Breaking Changes**: Acceptable to deprecate `.env` configuration, or require indefinite support?
5. **Testing**: What level of integration testing is required before deployment?

---

**Document Owner**: AI Copilot  
**Last Updated**: 2026-02-15  
**Status**: DRAFT - Awaiting Review
