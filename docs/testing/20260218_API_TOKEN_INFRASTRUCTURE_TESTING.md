# API Token Management Infrastructure Testing Guide
# API Token管理基础设施测试指南

**Date / 日期**: 2026-02-18  
**Phase / 阶段**: Phase 1 - Infrastructure (Week 1)  
**Status / 状态**: ✅ Complete

---

## Overview / 概述

This document describes testing procedures for the API Token Management infrastructure implementation, including database models, encryption service, and migration scripts.

本文档描述API Token管理基础设施实现的测试程序，包括数据库模型、加密服务和迁移脚本。

---

## Test Files / 测试文件

### 1. Token Encryption Tests
**File / 文件**: `tests/test_token_encryption.py`  
**Coverage / 覆盖**: TokenEncryption service (ai_actuarial/services/token_encryption.py)

#### Test Cases / 测试用例 (17 tests)

- **Singleton pattern** - Verifies only one encryption instance exists
- **Basic encryption/decryption** - Round-trip encrypt/decrypt works correctly
- **Different inputs** - Different inputs produce different encrypted outputs
- **Same input variations** - Same input produces different ciphertext (Fernet includes IV)
- **Error handling** - Empty strings and invalid ciphertext raise proper errors
- **Key rotation** - Decryption fails when encryption key changes
- **Key masking** - API keys masked correctly for display (sk-1234...wxyz)
- **Special characters** - Unicode and special chars encrypt/decrypt correctly
- **Long strings** - Very long strings (10,000 chars) work correctly

#### Run Tests / 运行测试

```bash
# Run all encryption tests
python -m pytest tests/test_token_encryption.py -v

# Run specific test
python -m pytest tests/test_token_encryption.py::TestTokenEncryption::test_encrypt_decrypt_basic -v

# With coverage
python -m pytest tests/test_token_encryption.py --cov=ai_actuarial.services.token_encryption
```

#### Expected Results / 预期结果

```
✅ 17 passed - All tests should pass
⚠️  Warnings about TOKEN_ENCRYPTION_KEY generation are expected in development
```

---

### 2. API Token Model Tests
**File / 文件**: `tests/test_api_token_model.py`  
**Coverage / 覆盖**: ApiToken model (ai_actuarial/models/api_token.py)

#### Test Cases / 测试用例 (13 tests)

- **Model creation** - Create ApiToken with all fields
- **Default values** - status='active', usage_count=0, timestamps set
- **Unique constraint** - provider+category must be unique
- **Multiple categories** - Same provider with different categories allowed
- **to_dict conversion** - Model converts to dict with key masking
- **Timestamp serialization** - Timestamps serialize to ISO format
- **String representation** - __repr__ includes provider, category, id
- **Optional fields** - api_base_url, config_json, notes can be None
- **Querying** - Query by provider, category, status
- **Database constraints** - NOT NULL constraints enforced

#### Run Tests / 运行测试

```bash
# Run all model tests
python -m pytest tests/test_api_token_model.py -v

# Run specific test
python -m pytest tests/test_api_token_model.py::TestApiToken::test_unique_provider_category_constraint -v

# With coverage
python -m pytest tests/test_api_token_model.py --cov=ai_actuarial.models.api_token
```

#### Expected Results / 预期结果

```
✅ 13 passed - All tests should pass
⚠️  Warnings about SQLAlchemy 2.0 deprecations are expected
```

---

### 3. Database Migration Tests
**File / 文件**: `tests/test_database_migration.py`  
**Coverage / 覆盖**: Migration script (scripts/create_api_tokens_table.py)

#### Test Cases / 测试用例 (4 tests)

- **Script importable** - Migration script can be imported without errors
- **Table creation** - Table created with correct schema (14 columns)
- **Unique constraint** - provider+category uniqueness enforced
- **Default values** - status='active', usage_count=0 applied correctly

#### Run Tests / 运行测试

```bash
# Run all migration tests
python -m pytest tests/test_database_migration.py -v

# Run specific test
python -m pytest tests/test_database_migration.py::TestDatabaseMigration::test_table_creation_with_temp_db -v
```

#### Expected Results / 预期结果

```
✅ 4 passed - All tests should pass
```

---

## Manual Testing / 手动测试

### 1. Run Migration Script / 运行迁移脚本

```bash
# Execute migration to create api_tokens table
python scripts/create_api_tokens_table.py
```

**Expected Output / 预期输出:**
```
Creating api_tokens table in data/index.db...
✅ api_tokens table created successfully

Table structure (14 columns):
  - id (INTEGER)
  - provider (VARCHAR(50))
  - category (VARCHAR(20))
  - api_key_encrypted (TEXT)
  - api_base_url (VARCHAR(255))
  - config_json (TEXT)
  - status (VARCHAR(10))
  - verification_status (VARCHAR(20))
  - created_at (TIMESTAMP)
  - updated_at (TIMESTAMP)
  - last_verified_at (TIMESTAMP)
  - last_used_at (TIMESTAMP)
  - usage_count (INTEGER)
  - notes (TEXT)
```

### 2. Verify Table in Database / 验证数据库表

```bash
# Open SQLite database
sqlite3 data/index.db

# List tables
.tables

# Check api_tokens schema
.schema api_tokens

# List indexes
SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='api_tokens';

# Exit
.quit
```

**Expected / 预期:**
- Table `api_tokens` exists
- Indexes: idx_provider_status, idx_category, unique index on provider+category
- 14 columns with correct types

### 3. Test Encryption Service / 测试加密服务

```python
# Interactive Python test
python

from ai_actuarial.services.token_encryption import TokenEncryption

# Create encryption instance
encryption = TokenEncryption()

# Test encryption
plaintext = "sk-1234567890abcdef"
encrypted = encryption.encrypt(plaintext)
print(f"Encrypted: {encrypted}")

# Test decryption
decrypted = encryption.decrypt(encrypted)
print(f"Decrypted: {decrypted}")
assert decrypted == plaintext

# Test masking
masked = TokenEncryption.mask_key(plaintext)
print(f"Masked: {masked}")  # Should be "sk-1...cdef"
```

### 4. Test Database Model / 测试数据库模型

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ai_actuarial.models.api_token import ApiToken, Base

# Create engine
engine = create_engine('sqlite:///data/index.db')
Base.metadata.create_all(engine)

# Create session
Session = sessionmaker(bind=engine)
session = Session()

# Create test token
from ai_actuarial.services.token_encryption import TokenEncryption
encryption = TokenEncryption()

token = ApiToken(
    provider='test_provider',
    category='test',
    api_key_encrypted=encryption.encrypt('test-api-key'),
    api_base_url='https://api.test.com',
    status='active'
)

session.add(token)
session.commit()

# Query token
result = session.query(ApiToken).filter_by(provider='test_provider').first()
print(f"Token: {result}")
print(f"Dict: {result.to_dict()}")

# Cleanup
session.delete(result)
session.commit()
session.close()
```

---

## Test Coverage Summary / 测试覆盖总结

| Component / 组件 | Tests / 测试数 | Status / 状态 |
|-----------------|------------|------------|
| TokenEncryption service | 17 | ✅ Pass |
| ApiToken model | 13 | ✅ Pass |
| Database migration | 4 | ✅ Pass |
| **Total** | **34** | **✅ All Pass** |

---

## Running All Tests / 运行所有测试

```bash
# Run all infrastructure tests
python -m pytest tests/test_token_encryption.py tests/test_api_token_model.py tests/test_database_migration.py -v

# With coverage report
python -m pytest tests/test_token_encryption.py tests/test_api_token_model.py tests/test_database_migration.py -v --cov=ai_actuarial.services.token_encryption --cov=ai_actuarial.models.api_token

# Quick test (no verbose)
python -m pytest tests/test_token_encryption.py tests/test_api_token_model.py tests/test_database_migration.py
```

---

## Test Locations for Users / 用户测试位置

### Where to Test / 在哪里测试

1. **Unit Tests / 单元测试**
   - Location: `tests/test_token_encryption.py`, `tests/test_api_token_model.py`
   - Run: `python -m pytest tests/test_token_encryption.py tests/test_api_token_model.py -v`

2. **Integration Tests / 集成测试**
   - Location: `tests/test_database_migration.py`
   - Run: `python -m pytest tests/test_database_migration.py -v`

3. **Migration Script / 迁移脚本**
   - Location: `scripts/create_api_tokens_table.py`
   - Run: `python scripts/create_api_tokens_table.py`

4. **Database Verification / 数据库验证**
   - Location: `data/index.db`
   - Verify: `sqlite3 data/index.db` then `.schema api_tokens`

---

## Dependencies / 依赖项

Ensure these packages are installed / 确保安装这些包:

```bash
pip install cryptography>=41.0.0
pip install sqlalchemy>=2.0.0
pip install pytest>=7.0.0
```

Or install from requirements / 或从需求文件安装:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

---

## Troubleshooting / 故障排除

### Issue: TOKEN_ENCRYPTION_KEY not found
**Solution / 解决方案**: 
- Set in .env: `TOKEN_ENCRYPTION_KEY=<generated-key>`
- Generate key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

### Issue: ModuleNotFoundError: No module named 'cryptography'
**Solution / 解决方案**:
```bash
pip install cryptography
```

### Issue: Table already exists
**Solution / 解决方案**:
- Migration script uses `CREATE TABLE IF NOT EXISTS` - safe to run multiple times
- Or drop table first: `sqlite3 data/index.db "DROP TABLE IF EXISTS api_tokens;"`

### Issue: SQLAlchemy deprecation warnings
**Solution / 解决方案**:
- These are warnings, not errors
- Will be fixed in future updates to use sqlalchemy.orm.declarative_base()

---

## Next Steps / 后续步骤

After verifying Phase 1 infrastructure tests pass:

1. ✅ All 34 tests passing
2. ✅ Migration script creates table successfully
3. ✅ Encryption service works correctly
4. ✅ Database model supports CRUD operations

Ready for **Phase 2**: Backend Service Layer implementation.

---

## Contact / 联系

For questions or issues with testing:
- Review test files in `tests/` directory
- Check implementation in `ai_actuarial/models/` and `ai_actuarial/services/`
- Verify migration script in `scripts/create_api_tokens_table.py`
