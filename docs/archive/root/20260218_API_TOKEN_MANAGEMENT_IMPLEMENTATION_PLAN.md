# API Token管理功能实现计划 / API Token Management Implementation Plan

**日期 / Date**: 2026-02-18  
**基于 / Based on**: RAGFlow API Token Management Research Report  
**版本 / Version**: 1.0

---

## 项目概述 / Project Overview

### 目标 / Objectives

基于RAGFlow的API token管理最佳实践，为AI_actuarial_inforsearch项目添加统一的API token管理功能，包括：

1. ✅ 数据库加密存储API密钥
2. ✅ Web UI配置界面
3. ✅ 实时API验证
4. ✅ 多提供商支持（LLM、搜索引擎等）
5. ✅ 向后兼容.env配置

### 核心原则 / Core Principles

1. **安全第一** - 使用加密存储，最小权限原则
2. **渐进式迁移** - 保持.env向后兼容，平滑过渡
3. **用户友好** - 提供直观的UI，降低配置门槛
4. **可扩展性** - 易于添加新的API提供商
5. **最小化修改** - 利用现有架构，避免大规模重构

---

## 技术架构 / Technical Architecture

### 架构图 / Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│                   Frontend (Web UI)                  │
│  Settings Page → API Tokens Tab                      │
│  - LLM Providers (OpenAI, Mistral, etc.)            │
│  - Search APIs (Brave, SerpAPI)                     │
│  - Document APIs (future)                            │
└────────────────────┬────────────────────────────────┘
                     │ HTTP/JSON
┌────────────────────▼────────────────────────────────┐
│              Flask REST API Endpoints                │
│  /api/tokens [GET]       - List all tokens          │
│  /api/tokens [POST]      - Add/update token         │
│  /api/tokens/:id [DELETE] - Delete token            │
│  /api/tokens/:id/verify [POST] - Verify token       │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│              Service Layer                           │
│  TokenService                                        │
│  - get_all_tokens()                                 │
│  - get_token(provider, category)                    │
│  - save_token(...)                                  │
│  - delete_token(id)                                 │
│  - verify_token(id)                                 │
│                                                      │
│  TokenEncryption                                     │
│  - encrypt(plaintext) → ciphertext                  │
│  - decrypt(ciphertext) → plaintext                  │
│                                                      │
│  ApiKeyProvider (统一接口)                           │
│  - get_api_key(provider, category)                  │
│    Priority: DB → sites.yaml → .env                │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│              Data Layer (SQLAlchemy)                 │
│  ApiToken Model                                      │
│  - id, provider, category                           │
│  - api_key_encrypted, api_base_url                  │
│  - status, verification_status                      │
│  - created_at, updated_at, last_verified_at         │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│              Storage (SQLite/PostgreSQL)             │
└─────────────────────────────────────────────────────┘
```

---

## Phase 1: 基础设施 / Infrastructure (Week 1)

### 1.1 数据库模型 / Database Model

**文件**: `ai_actuarial/models/api_token.py` (新建)

```python
"""
API Token database model for encrypted storage of API credentials.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Text, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class ApiToken(Base):
    """API Token model with encrypted storage."""
    
    __tablename__ = 'api_tokens'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Provider and category (unique combination)
    provider = Column(String(50), nullable=False, index=True)
    category = Column(String(20), nullable=False, index=True)
    
    # Encrypted credentials
    api_key_encrypted = Column(Text, nullable=False)
    api_base_url = Column(String(255), nullable=True)
    
    # Additional configuration (JSON format)
    config_json = Column(Text, nullable=True)
    
    # Status tracking
    status = Column(String(10), nullable=False, default='active', index=True)
    verification_status = Column(String(20), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_verified_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    
    # Usage statistics
    usage_count = Column(Integer, nullable=False, default=0)
    
    # Notes
    notes = Column(Text, nullable=True)
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_provider_category', 'provider', 'category', unique=True),
        Index('idx_provider_status', 'provider', 'status'),
    )
    
    def to_dict(self, mask_key: bool = True) -> dict:
        """
        Convert to dictionary representation.
        
        Args:
            mask_key: If True, only show first/last 4 chars of API key
            
        Returns:
            Dictionary with token information
        """
        result = {
            'id': self.id,
            'provider': self.provider,
            'category': self.category,
            'api_base_url': self.api_base_url,
            'status': self.status,
            'verification_status': self.verification_status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_verified_at': self.last_verified_at.isoformat() if self.last_verified_at else None,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'usage_count': self.usage_count,
            'notes': self.notes,
        }
        
        # Add masked or full key
        if mask_key:
            result['api_key'] = '****'  # Will be populated by service
        
        return result
```

### 1.2 加密服务 / Encryption Service

**文件**: `ai_actuarial/services/token_encryption.py` (新建)

```python
"""
Token encryption service using Fernet symmetric encryption.
"""
import os
import logging
from cryptography.fernet import Fernet
from typing import Optional

logger = logging.getLogger(__name__)


class TokenEncryption:
    """Service for encrypting and decrypting API tokens."""
    
    _instance: Optional['TokenEncryption'] = None
    _cipher: Optional[Fernet] = None
    
    def __new__(cls):
        """Singleton pattern to ensure one encryption instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize the encryption cipher."""
        key = self._get_or_create_encryption_key()
        self._cipher = Fernet(key)
        logger.info("Token encryption service initialized")
    
    def _get_or_create_encryption_key(self) -> bytes:
        """
        Get encryption key from environment or create new one.
        
        Returns:
            Encryption key as bytes
        """
        key_str = os.getenv('TOKEN_ENCRYPTION_KEY')
        
        if key_str:
            # Use existing key
            return key_str.encode()
        
        # Generate new key (should only happen in development)
        logger.warning(
            "TOKEN_ENCRYPTION_KEY not found in environment. "
            "Generating new key. This should only happen in development!"
        )
        key = Fernet.generate_key()
        
        # Log instruction for production
        logger.warning(
            f"Add this to your .env file:\n"
            f"TOKEN_ENCRYPTION_KEY={key.decode()}"
        )
        
        return key
    
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a plaintext API key.
        
        Args:
            plaintext: The plaintext API key
            
        Returns:
            Encrypted string (base64 encoded)
        """
        if not plaintext:
            raise ValueError("Cannot encrypt empty string")
        
        encrypted_bytes = self._cipher.encrypt(plaintext.encode())
        return encrypted_bytes.decode()
    
    def decrypt(self, encrypted: str) -> str:
        """
        Decrypt an encrypted API key.
        
        Args:
            encrypted: The encrypted API key
            
        Returns:
            Decrypted plaintext string
        """
        if not encrypted:
            raise ValueError("Cannot decrypt empty string")
        
        try:
            decrypted_bytes = self._cipher.decrypt(encrypted.encode())
            return decrypted_bytes.decode()
        except Exception as e:
            logger.error(f"Failed to decrypt token: {e}")
            raise ValueError("Failed to decrypt token. Key may be corrupted or encryption key changed.")
    
    @staticmethod
    def mask_key(api_key: str, show_chars: int = 4) -> str:
        """
        Mask an API key for display.
        
        Args:
            api_key: The API key to mask
            show_chars: Number of characters to show at start/end
            
        Returns:
            Masked key like "sk-1234...wxyz"
        """
        if not api_key or len(api_key) < show_chars * 2:
            return '****'
        
        return f"{api_key[:show_chars]}...{api_key[-show_chars:]}"
```

### 1.3 数据库迁移 / Database Migration

**文件**: `scripts/create_api_tokens_table.py` (新建)

```python
"""
Database migration script to create api_tokens table.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
from config.yaml_config import load_database_config

def create_api_tokens_table():
    """Create api_tokens table in the database."""
    
    # Get database configuration
    db_config = load_database_config()
    db_path = db_config.get('path', 'data/index.db')
    
    print(f"Creating api_tokens table in {db_path}...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider VARCHAR(50) NOT NULL,
            category VARCHAR(20) NOT NULL,
            api_key_encrypted TEXT NOT NULL,
            api_base_url VARCHAR(255),
            config_json TEXT,
            status VARCHAR(10) NOT NULL DEFAULT 'active',
            verification_status VARCHAR(20),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_verified_at TIMESTAMP,
            last_used_at TIMESTAMP,
            usage_count INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            UNIQUE(provider, category)
        )
    ''')
    
    # Create indexes
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_provider_status 
        ON api_tokens(provider, status)
    ''')
    
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_category 
        ON api_tokens(category)
    ''')
    
    conn.commit()
    conn.close()
    
    print("✅ api_tokens table created successfully")


if __name__ == '__main__':
    create_api_tokens_table()
```

**任务清单 / Task Checklist:**
- [ ] 创建 `ai_actuarial/models/api_token.py`
- [ ] 创建 `ai_actuarial/services/token_encryption.py`
- [ ] 创建 `scripts/create_api_tokens_table.py`
- [ ] 生成并保存 `TOKEN_ENCRYPTION_KEY` 到 `.env.example`
- [ ] 运行迁移脚本创建表
- [ ] 编写单元测试

---

## Phase 2: Backend服务层 / Backend Service Layer (Week 2)

### 2.1 Token服务 / Token Service

**文件**: `ai_actuarial/services/token_service.py` (新建)

```python
"""
Token service for managing API tokens.
"""
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
import sqlite3
from pathlib import Path

from ai_actuarial.services.token_encryption import TokenEncryption
from config.yaml_config import load_database_config

logger = logging.getLogger(__name__)


class TokenService:
    """Service for managing API tokens."""
    
    def __init__(self):
        self.encryption = TokenEncryption()
        self.db_path = self._get_db_path()
    
    def _get_db_path(self) -> str:
        """Get database path from configuration."""
        db_config = load_database_config()
        return db_config.get('path', 'data/index.db')
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_all_tokens(self, category: Optional[str] = None, mask_keys: bool = True) -> List[Dict[str, Any]]:
        """
        Get all API tokens, optionally filtered by category.
        
        Args:
            category: Optional category filter (llm, search, etc.)
            mask_keys: If True, mask API keys for display
            
        Returns:
            List of token dictionaries
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if category:
            cursor.execute(
                'SELECT * FROM api_tokens WHERE category = ? AND status = ? ORDER BY provider',
                (category, 'active')
            )
        else:
            cursor.execute(
                'SELECT * FROM api_tokens WHERE status = ? ORDER BY category, provider',
                ('active',)
            )
        
        rows = cursor.fetchall()
        conn.close()
        
        tokens = []
        for row in rows:
            token_dict = dict(row)
            
            # Decrypt and mask key if needed
            if mask_keys:
                decrypted = self.encryption.decrypt(token_dict['api_key_encrypted'])
                token_dict['api_key'] = TokenEncryption.mask_key(decrypted)
            else:
                token_dict['api_key'] = self.encryption.decrypt(token_dict['api_key_encrypted'])
            
            # Remove encrypted version
            del token_dict['api_key_encrypted']
            
            tokens.append(token_dict)
        
        return tokens
    
    def get_token(self, provider: str, category: str) -> Optional[str]:
        """
        Get decrypted API key for a provider/category.
        
        Args:
            provider: Provider name (openai, brave, etc.)
            category: Category (llm, search, etc.)
            
        Returns:
            Decrypted API key or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT api_key_encrypted FROM api_tokens WHERE provider = ? AND category = ? AND status = ?',
            (provider, category, 'active')
        )
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            # Update last_used_at and usage_count
            self._update_usage(provider, category)
            return self.encryption.decrypt(row['api_key_encrypted'])
        
        return None
    
    def save_token(
        self,
        provider: str,
        category: str,
        api_key: str,
        api_base_url: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None
    ) -> int:
        """
        Save or update an API token.
        
        Args:
            provider: Provider name
            category: Category
            api_key: Plaintext API key (will be encrypted)
            api_base_url: Optional base URL
            config: Optional configuration dict
            notes: Optional notes
            
        Returns:
            Token ID
        """
        encrypted_key = self.encryption.encrypt(api_key)
        config_json = json.dumps(config) if config else None
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Check if exists
        cursor.execute(
            'SELECT id FROM api_tokens WHERE provider = ? AND category = ?',
            (provider, category)
        )
        existing = cursor.fetchone()
        
        if existing:
            # Update existing
            cursor.execute('''
                UPDATE api_tokens
                SET api_key_encrypted = ?,
                    api_base_url = ?,
                    config_json = ?,
                    notes = ?,
                    updated_at = ?
                WHERE id = ?
            ''', (encrypted_key, api_base_url, config_json, notes, datetime.utcnow(), existing['id']))
            token_id = existing['id']
        else:
            # Insert new
            cursor.execute('''
                INSERT INTO api_tokens 
                (provider, category, api_key_encrypted, api_base_url, config_json, notes, status)
                VALUES (?, ?, ?, ?, ?, ?, 'active')
            ''', (provider, category, encrypted_key, api_base_url, config_json, notes))
            token_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        logger.info(f"Saved API token for {provider}/{category}")
        return token_id
    
    def delete_token(self, token_id: int) -> bool:
        """
        Delete (soft delete) an API token.
        
        Args:
            token_id: Token ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'UPDATE api_tokens SET status = ? WHERE id = ?',
            ('deleted', token_id)
        )
        
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        if deleted:
            logger.info(f"Deleted API token {token_id}")
        
        return deleted
    
    def update_verification_status(
        self,
        token_id: int,
        status: str,
        message: Optional[str] = None
    ):
        """
        Update verification status for a token.
        
        Args:
            token_id: Token ID
            status: Verification status (success, failed, pending)
            message: Optional verification message
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE api_tokens
            SET verification_status = ?,
                last_verified_at = ?,
                notes = ?
            WHERE id = ?
        ''', (status, datetime.utcnow(), message, token_id))
        
        conn.commit()
        conn.close()
    
    def _update_usage(self, provider: str, category: str):
        """Update usage statistics for a token."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE api_tokens
            SET usage_count = usage_count + 1,
                last_used_at = ?
            WHERE provider = ? AND category = ?
        ''', (datetime.utcnow(), provider, category))
        
        conn.commit()
        conn.close()
```

### 2.2 API密钥提供者 / API Key Provider

**文件**: `ai_actuarial/services/api_key_provider.py` (新建)

```python
"""
Unified API key provider with fallback support.
"""
import os
import logging
from typing import Optional

from ai_actuarial.services.token_service import TokenService
from config.yaml_config import load_yaml_config

logger = logging.getLogger(__name__)


class ApiKeyProvider:
    """
    Unified API key provider with multi-source fallback.
    
    Priority order:
    1. Database (encrypted storage)
    2. sites.yaml configuration
    3. Environment variables (.env)
    """
    
    def __init__(self):
        self.token_service = TokenService()
    
    def get_api_key(self, provider: str, category: str = 'llm') -> Optional[str]:
        """
        Get API key from multiple sources with fallback.
        
        Args:
            provider: Provider name (openai, brave, etc.)
            category: API category (llm, search, etc.)
            
        Returns:
            API key or None if not found
        """
        # 1. Try database first
        db_key = self.token_service.get_token(provider, category)
        if db_key:
            logger.debug(f"Got {provider} API key from database")
            return db_key
        
        # 2. Try sites.yaml
        yaml_key = self._get_from_yaml(provider, category)
        if yaml_key:
            logger.debug(f"Got {provider} API key from sites.yaml")
            return yaml_key
        
        # 3. Fallback to environment variables
        env_key = self._get_from_env(provider, category)
        if env_key:
            logger.debug(f"Got {provider} API key from environment")
            return env_key
        
        logger.warning(f"No API key found for {provider}/{category}")
        return None
    
    def _get_from_yaml(self, provider: str, category: str) -> Optional[str]:
        """Get API key from sites.yaml configuration."""
        try:
            config = load_yaml_config()
            
            # Try api_tokens section
            if 'api_tokens' in config:
                tokens = config['api_tokens']
                key = f"{provider}_{category}"
                if key in tokens:
                    return tokens[key].get('api_key')
            
            return None
        except Exception as e:
            logger.error(f"Error reading from sites.yaml: {e}")
            return None
    
    def _get_from_env(self, provider: str, category: str) -> Optional[str]:
        """Get API key from environment variables."""
        # Standard naming: PROVIDER_API_KEY
        env_var = f"{provider.upper()}_API_KEY"
        return os.getenv(env_var)
    
    def get_base_url(self, provider: str, category: str = 'llm') -> Optional[str]:
        """
        Get API base URL if configured.
        
        Args:
            provider: Provider name
            category: API category
            
        Returns:
            Base URL or None
        """
        # Try database first
        conn = self.token_service._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT api_base_url FROM api_tokens WHERE provider = ? AND category = ? AND status = ?',
            (provider, category, 'active')
        )
        row = cursor.fetchone()
        conn.close()
        
        if row and row['api_base_url']:
            return row['api_base_url']
        
        # Fallback to environment
        env_var = f"{provider.upper()}_BASE_URL"
        return os.getenv(env_var)


# Global instance
_api_key_provider = ApiKeyProvider()


def get_api_key(provider: str, category: str = 'llm') -> Optional[str]:
    """
    Convenience function to get API key.
    
    Args:
        provider: Provider name
        category: API category
        
    Returns:
        API key or None
    """
    return _api_key_provider.get_api_key(provider, category)


def get_base_url(provider: str, category: str = 'llm') -> Optional[str]:
    """
    Convenience function to get base URL.
    
    Args:
        provider: Provider name
        category: API category
        
    Returns:
        Base URL or None
    """
    return _api_key_provider.get_base_url(provider, category)
```

**任务清单 / Task Checklist:**
- [ ] 创建 `ai_actuarial/services/token_service.py`
- [ ] 创建 `ai_actuarial/services/api_key_provider.py`
- [ ] 编写服务层单元测试
- [ ] 更新现有代码使用新的API key provider

---

## Phase 3: REST API端点 / REST API Endpoints (Week 3)

### 3.1 Token管理端点 / Token Management Endpoints

**文件**: `ai_actuarial/web/token_routes.py` (新建)

```python
"""
REST API endpoints for token management.
"""
import logging
from flask import Blueprint, request, jsonify
from typing import Dict, Any

from ai_actuarial.services.token_service import TokenService
from ai_actuarial.services.token_verification import verify_api_token

logger = logging.getLogger(__name__)

# Create blueprint
token_bp = Blueprint('tokens', __name__, url_prefix='/api/tokens')

# Initialize services
token_service = TokenService()


@token_bp.route('', methods=['GET'])
def list_tokens():
    """
    List all API tokens (masked).
    
    Query params:
        category: Optional filter by category (llm, search, etc.)
    
    Returns:
        {
            "tokens": [...]
        }
    """
    try:
        category = request.args.get('category')
        tokens = token_service.get_all_tokens(category=category, mask_keys=True)
        
        return jsonify({
            'success': True,
            'tokens': tokens
        })
    except Exception as e:
        logger.error(f"Error listing tokens: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@token_bp.route('', methods=['POST'])
def add_or_update_token():
    """
    Add or update an API token.
    
    Request body:
        {
            "provider": "openai",
            "category": "llm",
            "api_key": "sk-...",
            "api_base_url": "https://...",  // optional
            "config": {...},                 // optional
            "notes": "...",                  // optional
            "verify": true                   // optional, default true
        }
    
    Returns:
        {
            "success": true,
            "token_id": 1,
            "verification": {...}
        }
    """
    try:
        data = request.get_json()
        
        # Validate required fields
        required = ['provider', 'category', 'api_key']
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({
                'success': False,
                'error': f"Missing required fields: {', '.join(missing)}"
            }), 400
        
        # Save token
        token_id = token_service.save_token(
            provider=data['provider'],
            category=data['category'],
            api_key=data['api_key'],
            api_base_url=data.get('api_base_url'),
            config=data.get('config'),
            notes=data.get('notes')
        )
        
        # Verify if requested
        verification_result = None
        if data.get('verify', True):
            verification_result = verify_api_token(
                provider=data['provider'],
                category=data['category'],
                api_key=data['api_key'],
                api_base_url=data.get('api_base_url')
            )
            
            # Update verification status
            token_service.update_verification_status(
                token_id=token_id,
                status=verification_result['status'],
                message=verification_result.get('message')
            )
        
        return jsonify({
            'success': True,
            'token_id': token_id,
            'verification': verification_result
        })
        
    except Exception as e:
        logger.error(f"Error adding/updating token: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@token_bp.route('/<int:token_id>', methods=['DELETE'])
def delete_token(token_id: int):
    """
    Delete an API token.
    
    Returns:
        {
            "success": true
        }
    """
    try:
        deleted = token_service.delete_token(token_id)
        
        if not deleted:
            return jsonify({
                'success': False,
                'error': 'Token not found'
            }), 404
        
        return jsonify({
            'success': True
        })
        
    except Exception as e:
        logger.error(f"Error deleting token: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@token_bp.route('/<int:token_id>/verify', methods=['POST'])
def verify_token_endpoint(token_id: int):
    """
    Verify an API token.
    
    Returns:
        {
            "success": true,
            "status": "success",
            "message": "..."
        }
    """
    try:
        # Get token info
        conn = token_service._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM api_tokens WHERE id = ?', (token_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return jsonify({
                'success': False,
                'error': 'Token not found'
            }), 404
        
        # Decrypt and verify
        api_key = token_service.encryption.decrypt(row['api_key_encrypted'])
        
        result = verify_api_token(
            provider=row['provider'],
            category=row['category'],
            api_key=api_key,
            api_base_url=row['api_base_url']
        )
        
        # Update verification status
        token_service.update_verification_status(
            token_id=token_id,
            status=result['status'],
            message=result.get('message')
        )
        
        return jsonify({
            'success': True,
            **result
        })
        
    except Exception as e:
        logger.error(f"Error verifying token: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
```

### 3.2 API验证服务 / API Verification Service

**文件**: `ai_actuarial/services/token_verification.py` (新建)

```python
"""
API token verification service.
"""
import logging
import asyncio
from typing import Dict, Any

logger = logging.getLogger(__name__)


def verify_api_token(
    provider: str,
    category: str,
    api_key: str,
    api_base_url: str = None
) -> Dict[str, Any]:
    """
    Verify an API token by making a test call.
    
    Args:
        provider: Provider name
        category: API category
        api_key: API key to verify
        api_base_url: Optional base URL
        
    Returns:
        {
            "status": "success" | "failed",
            "message": "...",
            "details": {...}
        }
    """
    try:
        if category == 'llm':
            return _verify_llm_token(provider, api_key, api_base_url)
        elif category == 'search':
            return _verify_search_token(provider, api_key)
        else:
            return {
                'status': 'failed',
                'message': f'Unknown category: {category}'
            }
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        return {
            'status': 'failed',
            'message': str(e)
        }


def _verify_llm_token(provider: str, api_key: str, base_url: str = None) -> Dict[str, Any]:
    """Verify LLM provider token."""
    
    if provider == 'openai':
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=api_key,
                base_url=base_url or "https://api.openai.com/v1"
            )
            
            # Test with cheapest model
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5
            )
            
            return {
                'status': 'success',
                'message': 'OpenAI API key verified successfully',
                'details': {
                    'model': response.model
                }
            }
        except Exception as e:
            return {
                'status': 'failed',
                'message': f'OpenAI verification failed: {str(e)}'
            }
    
    elif provider == 'mistral':
        try:
            from mistralai import Mistral
            client = Mistral(api_key=api_key)
            
            # Test with list models
            models = client.models.list()
            
            return {
                'status': 'success',
                'message': 'Mistral API key verified successfully',
                'details': {
                    'models_count': len(models.data)
                }
            }
        except Exception as e:
            return {
                'status': 'failed',
                'message': f'Mistral verification failed: {str(e)}'
            }
    
    # Add more providers...
    
    return {
        'status': 'failed',
        'message': f'Verification not implemented for provider: {provider}'
    }


def _verify_search_token(provider: str, api_key: str) -> Dict[str, Any]:
    """Verify search API token."""
    
    if provider == 'brave':
        try:
            import urllib.request
            import urllib.parse
            import json
            
            params = urllib.parse.urlencode({'q': 'test', 'count': 1})
            url = f"https://api.search.brave.com/res/v1/web/search?{params}"
            
            req = urllib.request.Request(url, headers={
                'X-Subscription-Token': api_key,
                'Accept': 'application/json'
            })
            
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            
            return {
                'status': 'success',
                'message': 'Brave API key verified successfully'
            }
        except Exception as e:
            return {
                'status': 'failed',
                'message': f'Brave verification failed: {str(e)}'
            }
    
    elif provider == 'serpapi':
        try:
            import urllib.request
            import urllib.parse
            import json
            
            params = urllib.parse.urlencode({
                'q': 'test',
                'engine': 'google',
                'api_key': api_key,
                'num': 1
            })
            url = f"https://serpapi.com/search.json?{params}"
            
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            
            return {
                'status': 'success',
                'message': 'SerpAPI key verified successfully'
            }
        except Exception as e:
            return {
                'status': 'failed',
                'message': f'SerpAPI verification failed: {str(e)}'
            }
    
    return {
        'status': 'failed',
        'message': f'Verification not implemented for provider: {provider}'
    }
```

**任务清单 / Task Checklist:**
- [ ] 创建 `ai_actuarial/web/token_routes.py`
- [ ] 创建 `ai_actuarial/services/token_verification.py`
- [ ] 在 `ai_actuarial/web/app.py` 中注册blueprint
- [ ] 编写API端点测试
- [ ] 更新API文档

---

## Phase 4-6: 前端UI、测试和文档 (Weeks 4-6)

由于篇幅限制，详细内容参见后续文档。主要任务：

### Phase 4: Frontend UI
- Settings页面添加API Tokens标签
- 实现Token列表展示
- 实现添加/编辑/删除操作
- 实现验证功能

### Phase 5: 测试
- 单元测试
- 集成测试
- 安全测试
- UI/UX测试

### Phase 6: 文档
- 用户文档
- API文档
- 迁移指南
- 最佳实践

---

## 安全检查清单 / Security Checklist

- [ ] API密钥在数据库中加密存储
- [ ] TOKEN_ENCRYPTION_KEY安全保管
- [ ] API密钥不在日志中泄露
- [ ] 严格的权限控制
- [ ] SQL注入防护
- [ ] CSRF保护
- [ ] 安全的前端-后端通信
- [ ] 备份和恢复方案

---

## 下一步 / Next Steps

1. ✅ 完成研究报告和实现计划
2. 📋 获取团队评审和反馈
3. 🚀 开始Phase 1实现
4. 🔄 迭代开发和测试
5. 📝 持续更新文档

---

**计划完成日期 / Plan Completed**: 2026-02-18  
**版本 / Version**: 1.0  
**状态 / Status**: ✅ Ready for Implementation
