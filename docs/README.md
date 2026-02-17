# Documentation Structure

This directory contains all project documentation, organized by category for easy navigation.

## Directory Organization

### 📋 `/plans/` - Planning & Design Documents
Planning documents and design specifications created before implementation:
- AI Chatbot RAG implementation plan
- Configuration migration plan
- Security hardening plans
- Feature design documents
- UI/UX planning documents

**Key Files:**
- [20260211_AI_CHATBOT_RAG_IMPLEMENTATION_PLAN.md](plans/20260211_AI_CHATBOT_RAG_IMPLEMENTATION_PLAN.md) - Comprehensive RAG chatbot implementation plan
- [20260215_CONFIG_MIGRATION_PLAN.md](plans/20260215_CONFIG_MIGRATION_PLAN.md) - Configuration migration from .env to YAML
- [20260214_MULTI_AI_PROVIDER_DESIGN.md](plans/20260214_MULTI_AI_PROVIDER_DESIGN.md) - Multi-AI provider architecture
- [20260216_FUTURE_DYNAMIC_MODEL_FETCHING.md](plans/20260216_FUTURE_DYNAMIC_MODEL_FETCHING.md) - Future enhancement plans

### ✅ `/implementation/` - Implementation Reports
Reports and summaries of completed implementation work:
- Phase completion summaries
- Feature implementation reports
- Integration summaries
- Progress reports
- PR summaries

**Key Files:**
- [20260212_PHASE2_COMPLETION_SUMMARY.md](implementation/20260212_PHASE2_COMPLETION_SUMMARY.md) - Phase 2 AI Chatbot completion
- [20260213_PHASE2_CHATBOT_INTEGRATION_SUMMARY.md](implementation/20260213_PHASE2_CHATBOT_INTEGRATION_SUMMARY.md) - Chatbot integration summary
- [20260215_CONFIG_MIGRATION_IMPLEMENTATION_REPORT.md](implementation/20260215_CONFIG_MIGRATION_IMPLEMENTATION_REPORT.md) - Config migration report
- [20260216_PR_SUMMARY_CONFIG_MIGRATION.md](implementation/20260216_PR_SUMMARY_CONFIG_MIGRATION.md) - Pull request summary

### 🏗️ `/architecture/` - Architecture & Technical Design
Technical architecture documentation and design specifications:
- System architecture diagrams
- Database design notes
- RAG implementation clarifications
- Component interface specifications

**Key Files:**
- [20260212_PHASE2_1_CHATBOT_ARCHITECTURE_DESIGN.md](architecture/20260212_PHASE2_1_CHATBOT_ARCHITECTURE_DESIGN.md) - Chatbot architecture
- [20260208_IMPLEMENTATION_NOTES_DATABASE_BACKEND.md](architecture/20260208_IMPLEMENTATION_NOTES_DATABASE_BACKEND.md) - Database backend design
- [20260211_RAG_IMPLEMENTATION_CLARIFICATIONS.md](architecture/20260211_RAG_IMPLEMENTATION_CLARIFICATIONS.md) - RAG design details
- [FILE_PREVIEW_ARCHITECTURE_DIAGRAM.md](architecture/FILE_PREVIEW_ARCHITECTURE_DIAGRAM.md) - File preview system

### 🔒 `/security/` - Security Documentation
Security analysis, hardening reports, and security summaries:
- Security summaries for each phase
- Security hardening reports
- CodeQL analysis results

**Key Files:**
- [20260213_PHASE2_SECURITY_SUMMARY.md](security/20260213_PHASE2_SECURITY_SUMMARY.md) - Phase 2 security summary
- [20260208_SECURITY_SUMMARY_PHASE3.md](security/20260208_SECURITY_SUMMARY_PHASE3.md) - Phase 3 security summary

### 🧪 `/testing/` - Testing Documentation
Testing guides, checklists, and test reports:
- Manual testing guides
- Testing checklists
- Test coverage reports

**Key Files:**
- [20260215_MANUAL_TESTING_GUIDE.md](testing/20260215_MANUAL_TESTING_GUIDE.md) - Comprehensive testing guide
- [MANUAL_TESTING_CHECKLIST.md](testing/MANUAL_TESTING_CHECKLIST.md) - Testing checklist

### 🇨🇳 `/zh-cn/` - Chinese Documentation
Chinese language documentation (中文文档):
- API documentation
- User guides
- Implementation reports

**Key Files:**
- [20260212_API_CHATBOT_API_REFERENCE.md](zh-cn/20260212_API_CHATBOT_API_REFERENCE.md) - 聊天机器人API接口说明
- [20260212_USER_GUIDE_CHATBOT.md](zh-cn/20260212_USER_GUIDE_CHATBOT.md) - AI聊天机器人使用说明
- [20260212_IMPLEMENTATION_PHASE2_CHATBOT_COMPLETE.md](zh-cn/20260212_IMPLEMENTATION_PHASE2_CHATBOT_COMPLETE.md) - Phase 2实现完成报告

### 📚 `/guides/` - User & Developer Guides
Operational guides and quick reference materials:
- Quick start guides
- Service start guides
- System guides
- Quick reference cards

**Key Files:**
- [QUICK_START_NEW_FEATURES.md](guides/QUICK_START_NEW_FEATURES.md)
- [SERVICE_START_GUIDE.md](guides/SERVICE_START_GUIDE.md)
- [AI_CHATBOT_QUICK_START.md](guides/AI_CHATBOT_QUICK_START.md)
- [DATABASE_BACKEND_GUIDE.md](guides/DATABASE_BACKEND_GUIDE.md)

### 📦 `/archive/` - Historical Documentation
Deprecated or historical documentation kept for reference:
- Old UI improvement plans
- Deprecated guides
- Historical implementation notes

## Root-Level Documents

- [20260208_HOW_TO_USE_DEV_WORKFLOW_SKILL.md](20260208_HOW_TO_USE_DEV_WORKFLOW_SKILL.md) - Development workflow guide

## File Naming Convention

All documentation files follow a consistent naming pattern:

```
YYYYMMDD_CATEGORY_DESCRIPTION.md
```

- **YYYYMMDD**: Date (e.g., 20260215)
- **CATEGORY**: Brief category identifier (e.g., PHASE2, CONFIG, SECURITY)
- **DESCRIPTION**: Descriptive name in UPPER_SNAKE_CASE

### Examples:
- `20260215_CONFIG_MIGRATION_PLAN.md`
- `20260212_PHASE2_COMPLETION_SUMMARY.md`
- `20260213_PHASE2_SECURITY_SUMMARY.md`

## Quick Navigation by Topic

### AI Chatbot & RAG
- Planning: [plans/20260211_AI_CHATBOT_RAG_IMPLEMENTATION_PLAN.md](plans/20260211_AI_CHATBOT_RAG_IMPLEMENTATION_PLAN.md)
- Architecture: [architecture/20260212_PHASE2_1_CHATBOT_ARCHITECTURE_DESIGN.md](architecture/20260212_PHASE2_1_CHATBOT_ARCHITECTURE_DESIGN.md)
- Implementation: [implementation/20260212_PHASE2_COMPLETION_SUMMARY.md](implementation/20260212_PHASE2_COMPLETION_SUMMARY.md)
- User Guide (CN): [zh-cn/20260212_USER_GUIDE_CHATBOT.md](zh-cn/20260212_USER_GUIDE_CHATBOT.md)

### Configuration Migration
- Planning: [plans/20260215_CONFIG_MIGRATION_PLAN.md](plans/20260215_CONFIG_MIGRATION_PLAN.md)
- Implementation: [implementation/20260215_CONFIG_MIGRATION_IMPLEMENTATION_REPORT.md](implementation/20260215_CONFIG_MIGRATION_IMPLEMENTATION_REPORT.md)
- PR Summary: [implementation/20260216_PR_SUMMARY_CONFIG_MIGRATION.md](implementation/20260216_PR_SUMMARY_CONFIG_MIGRATION.md)

### Security
- Phase 2: [security/20260213_PHASE2_SECURITY_SUMMARY.md](security/20260213_PHASE2_SECURITY_SUMMARY.md)
- Phase 3: [security/20260208_SECURITY_SUMMARY_PHASE3.md](security/20260208_SECURITY_SUMMARY_PHASE3.md)

### Testing
- Testing Guide: [testing/20260215_MANUAL_TESTING_GUIDE.md](testing/20260215_MANUAL_TESTING_GUIDE.md)
- Checklist: [testing/MANUAL_TESTING_CHECKLIST.md](testing/MANUAL_TESTING_CHECKLIST.md)

## Document Status

- ✅ **Implemented**: Features/plans that have been completed
- 📋 **Planning**: Documents describing future work
- 🔒 **Security**: Security-related documentation
- 🧪 **Testing**: Testing and validation documentation
- 📚 **Guide**: User and developer guides
- 🗄️ **Archive**: Historical/deprecated documentation

## Contributing

When adding new documentation:
1. Use the standard naming convention: `YYYYMMDD_CATEGORY_DESCRIPTION.md`
2. Place in the appropriate category directory
3. Update this README if adding a significant new document
4. Include proper markdown structure with headers and sections

---

**Last Updated**: 2026-02-17
