"""
Token encryption service using Fernet symmetric encryption.

This module provides encryption/decryption functionality for API tokens using
the cryptography library's Fernet implementation (symmetric encryption).
Based on RAGFlow best practices for secure token storage.
"""
import os
import logging
from cryptography.fernet import Fernet
from typing import Optional

logger = logging.getLogger(__name__)


class TokenEncryption:
    """Service for encrypting and decrypting API tokens.
    
    This class implements the singleton pattern to ensure only one encryption
    instance exists. It uses Fernet symmetric encryption from the cryptography
    library to encrypt/decrypt API tokens.
    
    The encryption key is read from the TOKEN_ENCRYPTION_KEY environment variable.
    If not found, a new key is generated (development only - not for production).
    
    Usage:
        encryption = TokenEncryption()
        encrypted = encryption.encrypt("my-api-key")
        decrypted = encryption.decrypt(encrypted)
        masked = TokenEncryption.mask_key("my-api-key")
    """
    
    _instance: Optional['TokenEncryption'] = None
    _cipher: Optional[Fernet] = None
    
    def __new__(cls):
        """Singleton pattern to ensure one encryption instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize the encryption cipher with key from environment."""
        key = self._get_or_create_encryption_key()
        self._cipher = Fernet(key)
        logger.info("Token encryption service initialized")
    
    def _get_or_create_encryption_key(self) -> bytes:
        """
        Get encryption key from environment or create new one.
        
        In production, TOKEN_ENCRYPTION_KEY should always be set in the environment.
        If not found, a new key is generated (development mode only).
        
        Returns:
            Encryption key as bytes
        """
        key_str = os.getenv('TOKEN_ENCRYPTION_KEY')
        
        if key_str:
            # Use existing key from environment
            return key_str.encode()
        
        # Generate new key (development mode only)
        logger.warning(
            "TOKEN_ENCRYPTION_KEY not found in environment. "
            "Generating new key. This should only happen in development!"
        )
        key = Fernet.generate_key()
        
        # Log instruction for production setup
        logger.warning(
            f"Add this to your .env file:\n"
            f"TOKEN_ENCRYPTION_KEY={key.decode()}"
        )
        
        return key
    
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a plaintext API key.
        
        Args:
            plaintext: The plaintext API key to encrypt
            
        Returns:
            Encrypted string (base64 encoded)
            
        Raises:
            ValueError: If plaintext is empty
        """
        if not plaintext:
            raise ValueError("Cannot encrypt empty string")
        
        encrypted_bytes = self._cipher.encrypt(plaintext.encode())
        return encrypted_bytes.decode()
    
    def decrypt(self, encrypted: str) -> str:
        """
        Decrypt an encrypted API key.
        
        Args:
            encrypted: The encrypted API key (base64 encoded)
            
        Returns:
            Decrypted plaintext string
            
        Raises:
            ValueError: If encrypted string is empty or decryption fails
        """
        if not encrypted:
            raise ValueError("Cannot decrypt empty string")
        
        try:
            decrypted_bytes = self._cipher.decrypt(encrypted.encode())
            return decrypted_bytes.decode()
        except Exception as e:
            logger.error(f"Failed to decrypt token: {e}")
            raise ValueError(
                "Failed to decrypt token. Key may be corrupted or encryption key changed."
            )
    
    @staticmethod
    def mask_key(api_key: str, show_chars: int = 4) -> str:
        """
        Mask an API key for display purposes.
        
        Args:
            api_key: The API key to mask
            show_chars: Number of characters to show at start and end (default: 4)
            
        Returns:
            Masked key in format "sk-1234...wxyz" or "****" for short keys
            
        Examples:
            >>> TokenEncryption.mask_key("sk-1234567890abcdef")
            'sk-1...cdef'
            >>> TokenEncryption.mask_key("short")
            '****'
        """
        if not api_key or len(api_key) < show_chars * 2:
            return '****'
        
        return f"{api_key[:show_chars]}...{api_key[-show_chars:]}"
