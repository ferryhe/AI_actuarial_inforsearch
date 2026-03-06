"""
Token encryption service using Fernet symmetric encryption.

This module provides encryption/decryption functionality for API tokens using
the cryptography library's Fernet implementation (symmetric encryption).
Based on RAGFlow best practices for secure token storage.
"""
import os
import logging
import threading
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
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern to ensure one encryption instance (thread-safe)."""
        if cls._instance is None:
            with cls._lock:
                # Double-check pattern for thread safety
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
        Get encryption key from environment, persistent key file, or create one.

        Priority:
          1. TOKEN_ENCRYPTION_KEY env var (highest — set this in production)
          2. Persistent key file (TOKEN_ENCRYPTION_KEY_FILE env var, or
             data/token_encryption.key relative to CWD)
          3. Generate a new key and save it to the key file so it survives restarts

        Returns:
            Encryption key as bytes
        """
        # 1. Explicit env var
        key_str = os.getenv('TOKEN_ENCRYPTION_KEY')
        if key_str:
            return key_str.encode()

        # 2. Persistent key file
        key_file = self._get_key_file_path()
        if key_file and os.path.exists(key_file):
            try:
                with open(key_file, 'rb') as f:
                    key = f.read().strip()
                if key:
                    logger.info("Token encryption key loaded from key file: %s", key_file)
                    return key
            except Exception as exc:
                logger.warning("Failed to read encryption key file %s: %s", key_file, exc)

        # 3. Generate new key and persist it so the next restart can reuse it
        logger.warning(
            "TOKEN_ENCRYPTION_KEY is not set. Generating a new key. "
            "For production, set TOKEN_ENCRYPTION_KEY in your .env file."
        )
        key = Fernet.generate_key()
        if key_file:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(key_file)), exist_ok=True)
                with open(key_file, 'wb') as f:
                    f.write(key)
                logger.warning(
                    "Encryption key saved to %s so it persists across restarts. "
                    "For production, copy this value and set TOKEN_ENCRYPTION_KEY "
                    "in your .env file instead.", key_file
                )
            except Exception as exc:
                logger.error(
                    "Could not persist encryption key to %s: %s. "
                    "All stored API keys will become unreadable on the next restart! "
                    "Set TOKEN_ENCRYPTION_KEY in your .env file to fix this.", key_file, exc
                )
        return key

    def _get_key_file_path(self) -> Optional[str]:
        """Return the path to use for the persistent key file."""
        explicit = os.getenv('TOKEN_ENCRYPTION_KEY_FILE')
        if explicit:
            return explicit
        # Default: data/token_encryption.key (data/ is already gitignored)
        return os.path.join(os.getcwd(), 'data', 'token_encryption.key')
    
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
