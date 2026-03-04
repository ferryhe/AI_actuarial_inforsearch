"""StorageV2 Auth extension - Auth tokens and LLM provider management.

This module provides Auth token and LLM provider storage operations using SQLAlchemy,
compatible with the API from storage.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_

from .db_models import AuthToken
# Import ApiToken from existing models to avoid duplicate
try:
    from ai_actuarial.models.api_token import ApiToken
except ImportError:
    # Fallback for backward compatibility: alias AuthToken as ApiToken
    from .db_models import AuthToken as ApiToken


class StorageV2AuthMixin:
    """Mixin providing Auth token and LLM provider operations."""
    
    def __init__(self, db_config: dict[str, Any]) -> None:
        """Initialize storage with database configuration."""
        self.backend = None
        self.db_path = db_config.get("path") if db_config.get("type") == "sqlite" else None
    
    @property
    def _session(self):
        return self.backend.get_session()
    
    @property
    def _conn(self):
        return self._session.connection()
    
    def now(self) -> str:
        """Get current timestamp."""
        return datetime.now(timezone.utc).isoformat()
    
    # ---------------------------------------------------------------------------
    # Auth Token Management
    # ---------------------------------------------------------------------------
    
    def get_auth_token_by_id(self, token_id: int) -> dict | None:
        """Get auth token by ID."""
        token = self._session.query(AuthToken).filter(
            AuthToken.id == int(token_id)
        ).first()
        
        if not token:
            return None
        
        return {
            "id": token.id,
            "subject": token.subject,
            "group_name": token.group_name,
            "is_active": bool(token.is_active),
            "created_at": token.created_at,
            "last_used_at": token.last_used_at,
            "revoked_at": token.revoked_at,
            "expires_at": token.expires_at,
        }
    
    def get_auth_token_by_hash(self, token_hash: str) -> dict | None:
        """Get auth token by hash."""
        token = self._session.query(AuthToken).filter(
            AuthToken.token_hash == str(token_hash)
        ).first()
        
        if not token:
            return None
        
        return {
            "id": token.id,
            "subject": token.subject,
            "group_name": token.group_name,
            "is_active": bool(token.is_active),
            "created_at": token.created_at,
            "last_used_at": token.last_used_at,
            "revoked_at": token.revoked_at,
            "expires_at": token.expires_at,
        }
    
    def list_auth_tokens(self) -> list[dict]:
        """List all auth tokens."""
        tokens = self._session.query(AuthToken).order_by(AuthToken.id.desc()).all()
        
        return [
            {
                "id": t.id,
                "subject": t.subject,
                "group_name": t.group_name,
                "is_active": bool(t.is_active),
                "created_at": t.created_at,
                "last_used_at": t.last_used_at,
                "revoked_at": t.revoked_at,
                "expires_at": t.expires_at,
            }
            for t in tokens
        ]
    
    def create_auth_token(
        self,
        *,
        subject: str,
        group_name: str,
        token_hash: str,
        expires_at: str | None = None,
    ) -> int:
        """Create a new auth token."""
        ts = self.now()
        
        token = AuthToken(
            subject=str(subject),
            group_name=str(group_name),
            token_hash=str(token_hash),
            is_active=1,
            created_at=ts,
            expires_at=expires_at,
        )
        self._session.add(token)
        self.backend._maybe_commit()
        
        return int(token.id)
    
    def upsert_auth_token_by_hash(
        self,
        *,
        subject: str,
        group_name: str,
        token_hash: str,
        is_active: bool = True,
    ) -> int:
        """Upsert auth token by hash."""
        ts = self.now()
        
        existing = self._session.query(AuthToken).filter(
            AuthToken.token_hash == str(token_hash)
        ).first()
        
        if existing:
            existing.subject = str(subject)
            existing.group_name = str(group_name)
            existing.is_active = 1 if is_active else 0
            self.backend._maybe_commit()
            return int(existing.id)
        
        token = AuthToken(
            subject=str(subject),
            group_name=str(group_name),
            token_hash=str(token_hash),
            is_active=1 if is_active else 0,
            created_at=ts,
        )
        self._session.add(token)
        self.backend._maybe_commit()
        
        return int(token.id)
    
    def revoke_auth_token(self, token_id: int) -> bool:
        """Revoke an auth token."""
        ts = self.now()
        
        token = self._session.query(AuthToken).filter(
            AuthToken.id == int(token_id)
        ).first()
        
        if not token:
            return False
        
        token.is_active = 0
        token.revoked_at = ts
        self.backend._maybe_commit()
        
        return True
    
    def touch_auth_token_last_used(self, token_id: int) -> None:
        """Update last_used_at for an auth token."""
        ts = self.now()
        
        self._session.query(AuthToken).filter(
            AuthToken.id == int(token_id)
        ).update({"last_used_at": ts})
        self.backend._maybe_commit()
    
    # ---------------------------------------------------------------------------
    # LLM Provider API Token Management
    # ---------------------------------------------------------------------------
    
    _LLM_TOKEN_COLS = (
        "id", "provider", "category", "api_key_encrypted",
        "api_base_url", "status", "created_at", "updated_at", "notes",
    )
    
    def upsert_llm_provider(
        self,
        provider: str,
        api_key_encrypted: str,
        base_url: str | None = None,
        notes: str | None = None,
        category: str = "llm",
    ) -> None:
        """Insert or update an LLM provider API token."""
        ts = self.now()
        
        existing = self._session.query(ApiToken).filter(
            and_(
                ApiToken.provider == provider,
                ApiToken.category == category
            )
        ).first()
        
        if existing:
            existing.api_key_encrypted = api_key_encrypted
            existing.api_base_url = base_url
            existing.notes = notes
            existing.updated_at = datetime.now(timezone.utc)
        else:
            api_token = ApiToken(
                provider=provider,
                category=category,
                api_key_encrypted=api_key_encrypted,
                api_base_url=base_url,
                status="active",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                notes=notes,
            )
            self._session.add(api_token)
        
        self.backend._maybe_commit()
    
    def get_llm_provider(
        self, provider: str, category: str = "llm"
    ) -> dict | None:
        """Get a single LLM provider record."""
        token = self._session.query(ApiToken).filter(
            and_(
                ApiToken.provider == provider,
                ApiToken.category == category
            )
        ).first()
        
        if not token:
            return None
        
        return {
            "id": token.id,
            "provider": token.provider,
            "category": token.category,
            "api_key_encrypted": token.api_key_encrypted,
            "api_base_url": token.api_base_url,
            "status": token.status,
            "created_at": str(token.created_at) if token.created_at else None,
            "updated_at": str(token.updated_at) if token.updated_at else None,
            "notes": token.notes,
        }
    
    def list_llm_providers(self, category: str = "llm") -> list[dict]:
        """List all LLM provider records for the given category."""
        tokens = self._session.query(ApiToken).filter(
            ApiToken.category == category
        ).order_by(ApiToken.provider).all()
        
        return [
            {
                "id": t.id,
                "provider": t.provider,
                "category": t.category,
                "api_key_encrypted": t.api_key_encrypted,
                "api_base_url": t.api_base_url,
                "status": t.status,
                "created_at": str(t.created_at) if t.created_at else None,
                "updated_at": str(t.updated_at) if t.updated_at else None,
                "notes": t.notes,
            }
            for t in tokens
        ]
    
    def delete_llm_provider(self, provider: str, category: str = "llm") -> bool:
        """Delete an LLM provider record."""
        deleted = self._session.query(ApiToken).filter(
            and_(
                ApiToken.provider == provider,
                ApiToken.category == category
            )
        ).delete(synchronize_session=False)
        
        self.backend._maybe_commit()
        return deleted > 0
