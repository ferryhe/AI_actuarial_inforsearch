"""
Unit tests for TokenEncryption service.

Tests cover encryption, decryption, masking, singleton pattern,
and error handling.
"""
import os
import pytest
from cryptography.fernet import Fernet
from ai_actuarial.services.token_encryption import TokenEncryption


class TestTokenEncryption:
    """Test cases for TokenEncryption service."""
    
    def setup_method(self):
        """Set up test fixtures before each test."""
        # Generate a test encryption key
        self.test_key = Fernet.generate_key().decode()
        os.environ['TOKEN_ENCRYPTION_KEY'] = self.test_key
        
        # Reset singleton instance for each test
        TokenEncryption._instance = None
    
    def teardown_method(self):
        """Clean up after each test."""
        # Remove test key from environment
        if 'TOKEN_ENCRYPTION_KEY' in os.environ:
            del os.environ['TOKEN_ENCRYPTION_KEY']
        
        # Reset singleton
        TokenEncryption._instance = None
    
    def test_singleton_pattern(self):
        """Test that TokenEncryption uses singleton pattern."""
        instance1 = TokenEncryption()
        instance2 = TokenEncryption()
        
        assert instance1 is instance2
        assert id(instance1) == id(instance2)
    
    def test_encrypt_decrypt_basic(self):
        """Test basic encryption and decryption."""
        encryption = TokenEncryption()
        
        plaintext = "sk-1234567890abcdef"
        encrypted = encryption.encrypt(plaintext)
        decrypted = encryption.decrypt(encrypted)
        
        assert decrypted == plaintext
        assert encrypted != plaintext
    
    def test_encrypt_different_inputs(self):
        """Test encryption produces different outputs for different inputs."""
        encryption = TokenEncryption()
        
        encrypted1 = encryption.encrypt("api-key-1")
        encrypted2 = encryption.encrypt("api-key-2")
        
        assert encrypted1 != encrypted2
    
    def test_encrypt_same_input_different_outputs(self):
        """Test that encrypting the same input twice produces different ciphertext."""
        encryption = TokenEncryption()
        
        plaintext = "same-api-key"
        encrypted1 = encryption.encrypt(plaintext)
        encrypted2 = encryption.encrypt(plaintext)
        
        # Fernet includes timestamp and random IV, so ciphertext differs
        # but both should decrypt to the same plaintext
        assert encrypted1 != encrypted2
        assert encryption.decrypt(encrypted1) == plaintext
        assert encryption.decrypt(encrypted2) == plaintext
    
    def test_encrypt_empty_string_raises_error(self):
        """Test that encrypting empty string raises ValueError."""
        encryption = TokenEncryption()
        
        with pytest.raises(ValueError, match="Cannot encrypt empty string"):
            encryption.encrypt("")
    
    def test_decrypt_empty_string_raises_error(self):
        """Test that decrypting empty string raises ValueError."""
        encryption = TokenEncryption()
        
        with pytest.raises(ValueError, match="Cannot decrypt empty string"):
            encryption.decrypt("")
    
    def test_decrypt_invalid_ciphertext(self):
        """Test that decrypting invalid ciphertext raises ValueError."""
        encryption = TokenEncryption()
        
        with pytest.raises(ValueError, match="Failed to decrypt token"):
            encryption.decrypt("invalid-ciphertext")
    
    def test_decrypt_with_different_key_fails(self):
        """Test that decryption fails when encryption key changes."""
        encryption1 = TokenEncryption()
        plaintext = "test-key"
        encrypted = encryption1.encrypt(plaintext)
        
        # Change the encryption key
        new_key = Fernet.generate_key().decode()
        os.environ['TOKEN_ENCRYPTION_KEY'] = new_key
        TokenEncryption._instance = None
        
        encryption2 = TokenEncryption()
        
        with pytest.raises(ValueError, match="Failed to decrypt token"):
            encryption2.decrypt(encrypted)
    
    def test_mask_key_standard(self):
        """Test standard key masking with default parameters."""
        api_key = "sk-1234567890abcdef"
        masked = TokenEncryption.mask_key(api_key)
        
        assert masked == "sk-1...cdef"
        assert len(masked) < len(api_key)
    
    def test_mask_key_custom_chars(self):
        """Test key masking with custom number of characters."""
        api_key = "sk-1234567890abcdef"
        masked = TokenEncryption.mask_key(api_key, show_chars=6)
        
        assert masked == "sk-123...abcdef"
    
    def test_mask_key_short_key(self):
        """Test masking of short keys returns ****."""
        short_key = "abc"
        masked = TokenEncryption.mask_key(short_key)
        
        assert masked == "****"
    
    def test_mask_key_empty_string(self):
        """Test masking of empty string returns ****."""
        masked = TokenEncryption.mask_key("")
        
        assert masked == "****"
    
    def test_mask_key_none(self):
        """Test masking of None returns ****."""
        masked = TokenEncryption.mask_key(None)
        
        assert masked == "****"
    
    def test_initialization_with_missing_key_generates_new(self, caplog, tmp_path):
        """Test that missing TOKEN_ENCRYPTION_KEY still works (uses/creates key file)."""
        import importlib
        import ai_actuarial.services.token_encryption as te_mod

        # Remove the env var
        if 'TOKEN_ENCRYPTION_KEY' in os.environ:
            del os.environ['TOKEN_ENCRYPTION_KEY']

        # Point key file to a temp location so we don't interfere with real data
        os.environ['TOKEN_ENCRYPTION_KEY_FILE'] = str(tmp_path / 'test.key')

        TokenEncryption._instance = None

        try:
            encryption = TokenEncryption()

            # Should still work with a generated key
            plaintext = "test-api-key"
            encrypted = encryption.encrypt(plaintext)
            decrypted = encryption.decrypt(encrypted)

            assert decrypted == plaintext

            # Key file should have been created
            assert (tmp_path / 'test.key').exists()
        finally:
            os.environ.pop('TOKEN_ENCRYPTION_KEY_FILE', None)
            TokenEncryption._instance = None
    
    def test_encrypt_decrypt_special_characters(self):
        """Test encryption/decryption with special characters."""
        encryption = TokenEncryption()
        
        special_chars = "!@#$%^&*()_+-=[]{}|;:',.<>?/~`"
        plaintext = f"api-key-{special_chars}"
        
        encrypted = encryption.encrypt(plaintext)
        decrypted = encryption.decrypt(encrypted)
        
        assert decrypted == plaintext
    
    def test_encrypt_decrypt_unicode(self):
        """Test encryption/decryption with unicode characters."""
        encryption = TokenEncryption()
        
        unicode_text = "api-密钥-🔑"
        encrypted = encryption.encrypt(unicode_text)
        decrypted = encryption.decrypt(encrypted)
        
        assert decrypted == unicode_text
    
    def test_encrypt_decrypt_long_string(self):
        """Test encryption/decryption with very long string."""
        encryption = TokenEncryption()
        
        long_string = "x" * 10000
        encrypted = encryption.encrypt(long_string)
        decrypted = encryption.decrypt(encrypted)
        
        assert decrypted == long_string
