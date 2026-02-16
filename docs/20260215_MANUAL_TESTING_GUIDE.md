# AI Configuration Manual Testing Guide

**Date**: 2026-02-15  
**Purpose**: Manual testing procedures for AI chatbot configuration

---

## Overview

This guide describes the manual testing procedures required to verify the AI chatbot configuration implementation. These tests should be performed in addition to the automated unit tests.

---

## Prerequisites

Before testing:
1. Ensure you have a `.env` file (copy from `.env.example`)
2. Have access to an OpenAI API key (optional for some tests)
3. Python 3.10+ environment with dependencies installed

---

## Test 1: Environment Variable Loading

### Objective
Verify that chatbot configuration loads correctly from environment variables.

### Steps

1. **Create test .env file:**
```bash
cd /home/runner/work/AI_actuarial_inforsearch/AI_actuarial_inforsearch
cat > .env.test << 'EOF'
OPENAI_API_KEY=test-key-for-manual-testing
CHATBOT_MODEL=gpt-4
CHATBOT_TEMPERATURE=0.8
CHATBOT_MAX_TOKENS=1500
CHATBOT_STREAMING_ENABLED=true
CHATBOT_MAX_CONTEXT_MESSAGES=15
CHATBOT_DEFAULT_MODE=summary
EOF
```

2. **Load and verify configuration:**
```bash
python3 << 'EOF'
import os
os.environ.update({
    'OPENAI_API_KEY': 'test-key-for-manual-testing',
    'CHATBOT_MODEL': 'gpt-4',
    'CHATBOT_TEMPERATURE': '0.8',
    'CHATBOT_MAX_TOKENS': '1500',
    'CHATBOT_STREAMING_ENABLED': 'true',
    'CHATBOT_MAX_CONTEXT_MESSAGES': '15',
    'CHATBOT_DEFAULT_MODE': 'summary'
})

from ai_actuarial.chatbot import ChatbotConfig
config = ChatbotConfig.from_env()

print("Configuration loaded:")
print(f"  Model: {config.model}")
print(f"  Temperature: {config.temperature}")
print(f"  Max tokens: {config.max_tokens}")
print(f"  Streaming: {config.streaming_enabled}")
print(f"  Max context: {config.max_context_messages}")
print(f"  Default mode: {config.default_mode}")
print(f"  API key: {'***' + config.openai_api_key[-4:] if config.openai_api_key else 'None'}")

config.validate()
print("\n✓ Configuration validated successfully!")
EOF
```

### Expected Results
- All values should match what you set in environment
- No errors or warnings
- Validation should pass

---

## Test 2: Configuration Validation

### Objective
Verify that invalid configuration values are caught and reported clearly.

### Test 2.1: Invalid Temperature

```bash
python3 << 'EOF'
from ai_actuarial.chatbot import ChatbotConfig

# Test temperature too high
config = ChatbotConfig(
    openai_api_key="test",
    temperature=2.5  # Invalid: > 2.0
)

try:
    config.validate()
    print("❌ FAIL: Should have raised ValueError")
except ValueError as e:
    print(f"✓ PASS: Caught invalid temperature - {e}")
EOF
```

**Expected**: ValueError with message about temperature range

### Test 2.2: Invalid Mode

```bash
python3 << 'EOF'
from ai_actuarial.chatbot import ChatbotConfig

config = ChatbotConfig(
    openai_api_key="test",
    default_mode="invalid_mode"  # Invalid
)

try:
    config.validate()
    print("❌ FAIL: Should have raised ValueError")
except ValueError as e:
    print(f"✓ PASS: Caught invalid mode - {e}")
EOF
```

**Expected**: ValueError with message about valid modes

### Test 2.3: Missing API Key

```bash
python3 << 'EOF'
from ai_actuarial.chatbot import ChatbotConfig

config = ChatbotConfig(openai_api_key="")  # Empty key

try:
    config.validate()
    print("❌ FAIL: Should have raised ValueError")
except ValueError as e:
    print(f"✓ PASS: Caught missing API key - {e}")
EOF
```

**Expected**: ValueError requiring OPENAI_API_KEY

---

## Test 3: Central Settings Integration

### Objective
Verify that chatbot settings integrate with the central config/settings.py module.

### Steps

```bash
python3 << 'EOF'
from config.settings import get_settings

settings = get_settings()

print("Central Settings - Chatbot Configuration:")
print(f"  Model: {settings.chatbot_model}")
print(f"  Temperature: {settings.chatbot_temperature}")
print(f"  Max tokens: {settings.chatbot_max_tokens}")
print(f"  Streaming: {settings.chatbot_streaming_enabled}")
print(f"  Max context messages: {settings.chatbot_max_context_messages}")
print(f"  Default mode: {settings.chatbot_default_mode}")
print("\n✓ All chatbot settings accessible from central settings!")

# Verify OpenAI key is shared
print(f"\nShared OpenAI API key: {settings.openai_api_key or '(not set)'}")
EOF
```

### Expected Results
- All chatbot settings should be accessible
- Default values should match .env.example
- OpenAI API key should be the same field used by RAG and other services

---

## Test 4: Settings Validation Integration

### Objective
Verify that Settings class validates chatbot configuration.

### Test 4.1: Valid Settings

```bash
python3 << 'EOF'
import os
os.environ["CHATBOT_TEMPERATURE"] = "1.2"
os.environ["CHATBOT_DEFAULT_MODE"] = "tutorial"

from config.settings import Settings
settings = Settings()

print(f"✓ Temperature: {settings.chatbot_temperature}")
print(f"✓ Mode: {settings.chatbot_default_mode}")
print("✓ Validation passed!")
EOF
```

**Expected**: No errors, settings load correctly

### Test 4.2: Invalid Temperature in Settings

```bash
python3 << 'EOF'
import os
os.environ["CHATBOT_TEMPERATURE"] = "5.0"  # Invalid

try:
    from config.settings import Settings
    settings = Settings()
    print("❌ FAIL: Should have raised validation error")
except ValueError as e:
    print(f"✓ PASS: Settings validation caught error")
    print(f"  Error: {e}")
EOF
```

**Expected**: ValueError from Settings validation

---

## Test 5: Configuration Modes

### Objective
Test different chatbot mode configurations.

### Test All Valid Modes

```bash
python3 << 'EOF'
from ai_actuarial.chatbot import ChatbotConfig

modes = ["expert", "summary", "tutorial", "comparison"]
for mode in modes:
    config = ChatbotConfig(
        openai_api_key="test",
        default_mode=mode
    )
    config.validate()
    print(f"✓ Mode '{mode}' validated successfully")
EOF
```

**Expected**: All four modes validate successfully

---

## Test 6: Shared OpenAI Key with RAG

### Objective
Verify that chatbot and RAG can share the same OpenAI API key.

### Steps

```bash
python3 << 'EOF'
import os
os.environ["OPENAI_API_KEY"] = "shared-test-key-123"

from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.chatbot.config import ChatbotConfig

rag_config = RAGConfig.from_env()
chatbot_config = ChatbotConfig.from_env()

print("RAG OpenAI key:", rag_config.openai_api_key[-6:] + "...")
print("Chatbot OpenAI key:", chatbot_config.openai_api_key[-6:] + "...")

if rag_config.openai_api_key == chatbot_config.openai_api_key:
    print("\n✓ PASS: Both configs share the same API key")
else:
    print("\n❌ FAIL: API keys don't match")
EOF
```

**Expected**: Both configurations use the same OpenAI API key

---

## Test 7: Production Configuration

### Objective
Test a production-ready configuration.

### Steps

```bash
python3 << 'EOF'
from ai_actuarial.chatbot import ChatbotConfig

# Production-like configuration
config = ChatbotConfig(
    openai_api_key="sk-test-production-key",
    model="gpt-4-turbo",
    temperature=0.7,
    max_tokens=1000,
    streaming_enabled=True,
    max_context_messages=10,
    default_mode="expert",
    enable_citation=True,
    min_citation_score=0.4,
    max_citations_per_response=5,
    enable_query_validation=True,
    enable_response_validation=True,
    max_query_length=1000
)

config.validate()
print("✓ Production configuration validated successfully!")
print("\nProduction settings:")
print(f"  Model: {config.model}")
print(f"  Temperature: {config.temperature}")
print(f"  Streaming: {config.streaming_enabled}")
print(f"  Citations: {config.enable_citation}")
print(f"  Validation: Query={config.enable_query_validation}, Response={config.enable_response_validation}")
EOF
```

**Expected**: Configuration validates and shows appropriate production values

---

## Test 8: Boolean Parsing

### Objective
Verify that boolean environment variables parse correctly.

### Steps

```bash
python3 << 'EOF'
import os

test_cases = [
    ("true", True),
    ("false", False),
    ("True", True),
    ("False", False),
    ("TRUE", True),
    ("FALSE", False),
]

from ai_actuarial.chatbot import ChatbotConfig

for env_value, expected in test_cases:
    os.environ["CHATBOT_STREAMING_ENABLED"] = env_value
    config = ChatbotConfig.from_env()
    
    if config.streaming_enabled == expected:
        print(f"✓ '{env_value}' → {expected}")
    else:
        print(f"❌ '{env_value}' → {config.streaming_enabled} (expected {expected})")
EOF
```

**Expected**: All boolean string variations parse correctly

---

## Test Results Summary

After completing all tests, you should have verified:

- [x] Configuration loads from environment variables
- [x] Default values work when env vars not set
- [x] Validation catches invalid values
- [x] Clear error messages for validation failures
- [x] Integration with central Settings class
- [x] Settings validation catches invalid chatbot config
- [x] All four chatbot modes work
- [x] OpenAI API key shared between RAG and chatbot
- [x] Production configuration validates
- [x] Boolean parsing works correctly

---

## Common Issues and Solutions

### Issue: ModuleNotFoundError for pydantic

**Solution**: Install required dependencies
```bash
pip install pydantic pydantic-settings
```

### Issue: Cannot import ChatbotConfig

**Solution**: Ensure you're in the project root directory
```bash
cd /home/runner/work/AI_actuarial_inforsearch/AI_actuarial_inforsearch
```

### Issue: Validation passes with invalid values

**Solution**: Check that you're calling `config.validate()` after creating the config

### Issue: Settings doesn't include chatbot fields

**Solution**: Clear Python cache and reimport
```bash
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
python3 -c "from config.settings import get_settings; s = get_settings(); print(s.chatbot_model)"
```

---

## Next Steps After Manual Testing

1. ✅ Run automated unit tests: `pytest tests/test_chatbot_config.py -v`
2. ✅ Verify all manual tests pass
3. ⬜ Review configuration with stakeholders
4. ⬜ Update project documentation
5. ⬜ Begin Phase 2 chatbot implementation when ready

---

## Contact

For questions or issues with testing:
- Review documentation in `docs/20260215_AI_CONFIGURATION_IMPLEMENTATION.md`
- Check test code in `tests/test_chatbot_config.py`
- Refer to configuration module in `ai_actuarial/chatbot/config.py`
