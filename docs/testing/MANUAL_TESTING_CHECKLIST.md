# Manual Testing Checklist - AI Configuration

**Purpose**: Items requiring manual testing for AI configuration implementation  
**Date**: 2026-02-15

---

## Overview

The AI configuration implementation has passed all automated tests (21 unit tests) and security scans (CodeQL). However, certain aspects require manual testing to verify real-world deployment scenarios.

---

## Manual Testing Items

### ✅ Completed - Automated Tests
- [x] Configuration default values
- [x] Environment variable parsing
- [x] Type conversion (string → int/float/bool)
- [x] All validation rules
- [x] Error messages
- [x] Integration with module system
- [x] Security scan (CodeQL: 0 alerts)

### ⚠️ Required - Manual Testing

#### 1. Real Environment File Loading
**Priority**: High  
**Why**: Automated tests use in-memory environment; need to verify actual .env file

**Test Steps**:
1. Copy `.env.example` to `.env`
2. Set OPENAI_API_KEY to a test value
3. Modify chatbot settings (e.g., CHATBOT_TEMPERATURE=0.8)
4. Run: `python3 -c "from config.settings import get_settings; print(get_settings().chatbot_temperature)"`
5. Verify output matches .env value

**Expected**: Should print "0.8"

**Reference**: `docs/20260215_MANUAL_TESTING_GUIDE.md` - Test 1

---

#### 2. Application Startup Integration
**Priority**: High  
**Why**: Verify settings load during full application initialization

**Test Steps**:
1. Start the web application: `python -m ai_actuarial.web.app`
2. Check startup logs for any configuration errors
3. Verify application starts successfully
4. Check that chatbot settings are accessible

**Expected**: Application starts without errors

**Reference**: `docs/20260215_MANUAL_TESTING_GUIDE.md` - Test 3

---

#### 3. Settings Validation on Startup
**Priority**: Medium  
**Why**: Verify invalid configuration is caught during application startup

**Test Steps**:
1. Set invalid value in .env: `CHATBOT_TEMPERATURE=5.0`
2. Try to start application
3. Verify clear error message is shown
4. Correct the value and verify startup succeeds

**Expected**: Application should fail to start with clear error message about temperature range

**Reference**: `docs/20260215_MANUAL_TESTING_GUIDE.md` - Test 2

---

#### 4. Shared OpenAI Key Access
**Priority**: High  
**Why**: Verify chatbot and RAG can both access the same API key

**Test Steps**:
1. Set `OPENAI_API_KEY=test-key-123` in .env
2. Run test script:
```python
from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.chatbot.config import ChatbotConfig

rag = RAGConfig.from_env()
chatbot = ChatbotConfig.from_env()

print(f"RAG key: {rag.openai_api_key}")
print(f"Chatbot key: {chatbot.openai_api_key}")
assert rag.openai_api_key == chatbot.openai_api_key
print("✓ Keys match!")
```
3. Verify both configs use the same key

**Expected**: Both should print the same API key

**Reference**: `docs/20260215_MANUAL_TESTING_GUIDE.md` - Test 6

---

#### 5. All Chatbot Modes Validation
**Priority**: Medium  
**Why**: Verify all four chatbot modes are accepted

**Test Steps**:
1. Test each mode in .env:
   - CHATBOT_DEFAULT_MODE=expert
   - CHATBOT_DEFAULT_MODE=summary
   - CHATBOT_DEFAULT_MODE=tutorial
   - CHATBOT_DEFAULT_MODE=comparison
2. For each, verify settings load successfully
3. Test invalid mode (e.g., "invalid") and verify error

**Expected**: Valid modes work, invalid mode raises error

**Reference**: `docs/20260215_MANUAL_TESTING_GUIDE.md` - Test 5

---

#### 6. Boolean String Parsing
**Priority**: Low  
**Why**: Verify case-insensitive boolean parsing works

**Test Steps**:
1. Test various boolean strings:
   - "true", "false"
   - "True", "False"
   - "TRUE", "FALSE"
2. Verify all parse correctly to boolean values

**Expected**: All variations parse correctly

**Reference**: `docs/20260215_MANUAL_TESTING_GUIDE.md` - Test 8

---

#### 7. Production Configuration Validation
**Priority**: High  
**Why**: Test production-ready settings work correctly

**Test Steps**:
1. Set up production-like configuration in .env:
```
OPENAI_API_KEY=sk-real-key-here
CHATBOT_MODEL=gpt-4-turbo
CHATBOT_TEMPERATURE=0.7
CHATBOT_MAX_TOKENS=1000
CHATBOT_STREAMING_ENABLED=true
CHATBOT_MAX_CONTEXT_MESSAGES=10
CHATBOT_DEFAULT_MODE=expert
```
2. Start application
3. Verify all settings load correctly
4. Check no warnings or errors

**Expected**: Application starts successfully with production config

**Reference**: `docs/20260215_MANUAL_TESTING_GUIDE.md` - Test 7

---

#### 8. Docker Container Environment (Optional)
**Priority**: Medium  
**Why**: Verify configuration works in containerized deployments

**Test Steps**:
1. Build Docker image (if available)
2. Pass environment variables to container
3. Start container and check logs
4. Verify settings load correctly

**Expected**: Configuration works in Docker environment

**Reference**: Deployment documentation

---

## Testing Priority Summary

### Must Test Before Merge
1. ✅ Automated tests (DONE)
2. ✅ Security scan (DONE)
3. ⚠️ Real .env file loading
4. ⚠️ Application startup integration
5. ⚠️ Shared OpenAI key access
6. ⚠️ Production configuration

### Should Test Before Production
7. Settings validation on startup
8. All chatbot modes
9. Boolean parsing
10. Docker environment (if applicable)

---

## Quick Test Script

Run this script to perform basic manual verification:

```bash
#!/bin/bash
# Quick test script for AI configuration

echo "=== AI Configuration Manual Test ==="

# Test 1: Environment loading
echo "Test 1: Environment variable loading"
export CHATBOT_TEMPERATURE=0.8
python3 -c "from ai_actuarial.chatbot import ChatbotConfig; c = ChatbotConfig.from_env(); assert c.temperature == 0.8; print('✓ Pass')"

# Test 2: Validation
echo "Test 2: Validation"
python3 << 'EOF'
from ai_actuarial.chatbot import ChatbotConfig
try:
    c = ChatbotConfig(temperature=5.0, openai_api_key="test")
    c.validate()
    print("✗ Fail: Should have raised error")
except ValueError:
    print("✓ Pass: Validation caught error")
EOF

# Test 3: Settings integration
echo "Test 3: Settings integration"
python3 -c "from config.settings import get_settings; s = get_settings(); print(f'✓ Pass: Model={s.chatbot_model}')"

# Test 4: Shared API key
echo "Test 4: Shared API key"
export OPENAI_API_KEY=test-shared-key
python3 << 'EOF'
from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.chatbot.config import ChatbotConfig
rag = RAGConfig.from_env()
chatbot = ChatbotConfig.from_env()
assert rag.openai_api_key == chatbot.openai_api_key
print("✓ Pass: Keys match")
EOF

echo ""
echo "=== All Quick Tests Passed ==="
```

Save as `test_ai_config.sh` and run:
```bash
chmod +x test_ai_config.sh
./test_ai_config.sh
```

---

## Test Results Template

When completing manual tests, use this template:

```
Manual Testing Results - AI Configuration
Date: ___________
Tester: ___________

Test 1: Real .env loading                    [ ] Pass  [ ] Fail
Test 2: Application startup                   [ ] Pass  [ ] Fail
Test 3: Validation on startup                 [ ] Pass  [ ] Fail
Test 4: Shared OpenAI key                     [ ] Pass  [ ] Fail
Test 5: All chatbot modes                     [ ] Pass  [ ] Fail
Test 6: Boolean parsing                       [ ] Pass  [ ] Fail
Test 7: Production configuration              [ ] Pass  [ ] Fail
Test 8: Docker environment (optional)         [ ] Pass  [ ] Fail  [ ] N/A

Issues Found:
_____________________________________
_____________________________________

Additional Notes:
_____________________________________
_____________________________________

Overall Status:  [ ] Ready for Merge  [ ] Needs Fixes
```

---

## Getting Help

If you encounter issues during manual testing:

1. **Check Documentation**:
   - `docs/20260215_MANUAL_TESTING_GUIDE.md` - Detailed test procedures
   - `docs/20260215_AI_CONFIGURATION_IMPLEMENTATION.md` - Implementation details
   - `.env.example` - Configuration reference

2. **Common Issues**:
   - ModuleNotFoundError: Run `pip install -r requirements.txt`
   - Import errors: Ensure you're in project root directory
   - Validation errors: Check value ranges in documentation

3. **Test Files**:
   - Unit tests: `tests/test_chatbot_config.py`
   - Configuration: `ai_actuarial/chatbot/config.py`
   - Settings: `config/settings.py`

---

## Sign-off

After completing all required manual tests:

```
Manual Testing Sign-off

Tested by: ___________
Date: ___________
Environment: [ ] Development  [ ] Staging  [ ] Production

All required tests passed: [ ] Yes  [ ] No

Approved for:
[ ] Merge to main
[ ] Phase 2 implementation
[ ] Production deployment

Signature: ___________
```

---

**Last Updated**: 2026-02-15  
**Status**: Awaiting Manual Testing  
**Next Action**: Complete required manual tests before merge
