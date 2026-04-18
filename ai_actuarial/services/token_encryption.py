"""
Token encryption service using Fernet symmetric encryption.

This module provides encryption/decryption functionality for API tokens using
the cryptography library's Fernet implementation (symmetric encryption).
Based on RAGFlow best practices for secure token storage.
"""
import os
import logging
import shlex
import threading
from pathlib import Path
from cryptography.fernet import Fernet
from typing import Optional

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


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
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern to ensure one encryption instance (thread-safe)."""
        if cls._instance is None:
            with cls._lock:
                # Double-check pattern for thread safety
                if cls._instance is None:
                    instance = super().__new__(cls)
                    try:
                        instance._initialize()
                    except Exception:
                        cls._instance = None
                        raise
                    cls._instance = instance
        return cls._instance
    
    def _initialize(self):
        """Initialize the encryption cipher with key from environment."""
        key = self._get_or_create_encryption_key()
        self._cipher = Fernet(key)
        logger.info("Token encryption service initialized")
    
    def _get_or_create_encryption_key(self) -> bytes:
        """Get the encryption key from process env or project .env only."""
        key_str = self._get_env_or_dotenv_value('TOKEN_ENCRYPTION_KEY')
        if key_str:
            return key_str.encode()

        raise ValueError(
            'TOKEN_ENCRYPTION_KEY is required. Set it in the process environment '
            'or in the project .env file before starting the service.'
        )

    def _get_env_or_dotenv_value(self, key_name: str) -> Optional[str]:
        """Return a config value from process env first, then project .env."""
        env_value = os.getenv(key_name)
        if env_value:
            return env_value

        dotenv_path = PROJECT_ROOT / '.env'
        if not dotenv_path.exists():
            return None

        try:
            for raw_line in dotenv_path.read_text(encoding='utf-8').splitlines():
                line = raw_line.strip()
                if line.startswith('export '):
                    line = line[len('export '):].strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                current_key, current_value = line.split('=', 1)
                if current_key.strip() != key_name:
                    continue
                value = current_value.strip()
                if value:
                    parsed = shlex.split(value, comments=True, posix=True)
                    value = parsed[0] if parsed else ''
                return value or None
        except Exception as exc:
            logger.warning('Failed to read project .env for %s: %s', key_name, exc)

        return None
    
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
            logger.exception("Failed to decrypt token")
            raise ValueError(
                "Failed to decrypt token. Key may be corrupted or encryption key changed."
            ) from e
    
    @staticmethod
    def mask_key(api_key: Optional[str], show_chars: int = 4) -> str:
        """
        Mask an API key for display purposes.
        
        Args:
            api_key: The API key to mask (or None)
            show_chars: Number of characters to show at start and end (default: 4)
            
        Returns:
            Masked key in format "sk-1234...wxyz" or "****" for short/empty keys
            
        Examples:
            >>> TokenEncryption.mask_key("sk-1234567890abcdef")
            'sk-1...cdef'
            >>> TokenEncryption.mask_key("short")
            '****'
            >>> TokenEncryption.mask_key(None)
            '****'
        """
        if not api_key or len(api_key) < show_chars * 2:
            return '****'
        
        return f"{api_key[:show_chars]}...{api_key[-show_chars:]}"
