"""
API Token database model for encrypted storage of API credentials.

This module provides the SQLAlchemy model for storing API tokens with encryption.
Based on RAGFlow best practices for secure token management.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Text, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class ApiToken(Base):
    """API Token model with encrypted storage.
    
    This model stores API tokens for various providers (LLM, search engines, etc.)
    with Fernet symmetric encryption. The provider+category combination must be unique.
    
    Attributes:
        id: Primary key
        provider: Provider name (e.g., 'openai', 'brave', 'mistral')
        category: Token category (e.g., 'llm', 'search')
        api_key_encrypted: Fernet-encrypted API key
        api_base_url: Optional custom API endpoint URL
        config_json: Additional configuration as JSON string
        status: Token status ('active', 'inactive')
        verification_status: Last verification result
        created_at: Creation timestamp
        updated_at: Last update timestamp
        last_verified_at: Last verification timestamp
        last_used_at: Last usage timestamp
        usage_count: Number of times used
        notes: Optional notes
    """
    
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
            mask_key: If True, only show masked API key (default: True)
                     Note: The actual masking is done by the service layer
            
        Returns:
            Dictionary with token information (api_key will be '****' if mask_key=True)
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
        
        # Add masked or placeholder key
        # Actual masking with decrypted key is done by service layer
        if mask_key:
            result['api_key'] = '****'
        
        return result
    
    def __repr__(self) -> str:
        """String representation of the token."""
        return f"<ApiToken(id={self.id}, provider={self.provider}, category={self.category})>"
