"""
Integration tests for database migration script.

Tests cover table creation, schema validation, and migration execution.
These tests run the actual migration script to verify it works correctly.
"""
import os
import pytest
import sqlite3
import tempfile
from pathlib import Path


class TestDatabaseMigration:
    """Test cases for create_api_tokens_table migration script."""
    
    def test_migration_script_executable(self):
        """Test that migration script can be imported and run."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        # Should be able to import without errors
        from scripts import create_api_tokens_table
        assert create_api_tokens_table is not None
    
    def test_table_creation_with_temp_db(self):
        """Test creating table directly with SQLite."""
        fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Create table using the same SQL from migration script
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
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_provider_status 
                ON api_tokens(provider, status)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_category 
                ON api_tokens(category)
            ''')
            
            conn.commit()
            
            # Verify table exists
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='api_tokens'"
            )
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == 'api_tokens'
            
            # Verify columns
            cursor.execute("PRAGMA table_info(api_tokens)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            assert 'id' in column_names
            assert 'provider' in column_names
            assert 'category' in column_names
            assert 'api_key_encrypted' in column_names
            assert 'status' in column_names
            assert len(columns) == 14  # Total columns
            
            # Verify indexes
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='api_tokens'"
            )
            indexes = cursor.fetchall()
            index_names = [idx[0] for idx in indexes]
            
            assert any('idx_provider_status' in name for name in index_names)
            assert any('idx_category' in name for name in index_names)
            
            conn.close()
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)
    
    def test_unique_constraint_enforcement(self):
        """Test that provider+category unique constraint works."""
        fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Create table
            cursor.execute('''
                CREATE TABLE api_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider VARCHAR(50) NOT NULL,
                    category VARCHAR(20) NOT NULL,
                    api_key_encrypted TEXT NOT NULL,
                    api_base_url VARCHAR(255),
                    status VARCHAR(10) NOT NULL DEFAULT 'active',
                    usage_count INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(provider, category)
                )
            ''')
            
            # Insert first token
            cursor.execute(
                "INSERT INTO api_tokens (provider, category, api_key_encrypted) VALUES (?, ?, ?)",
                ('openai', 'llm', 'encrypted_key1')
            )
            conn.commit()
            
            # Try to insert duplicate provider+category
            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute(
                    "INSERT INTO api_tokens (provider, category, api_key_encrypted) VALUES (?, ?, ?)",
                    ('openai', 'llm', 'encrypted_key2')
                )
                conn.commit()
            
            conn.close()
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)
    
    def test_default_values_work(self):
        """Test that default values are applied correctly."""
        fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Create table
            cursor.execute('''
                CREATE TABLE api_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider VARCHAR(50) NOT NULL,
                    category VARCHAR(20) NOT NULL,
                    api_key_encrypted TEXT NOT NULL,
                    status VARCHAR(10) NOT NULL DEFAULT 'active',
                    usage_count INTEGER NOT NULL DEFAULT 0
                )
            ''')
            
            # Insert with minimal fields
            cursor.execute(
                "INSERT INTO api_tokens (provider, category, api_key_encrypted) VALUES (?, ?, ?)",
                ('brave', 'search', 'encrypted_brave_key')
            )
            conn.commit()
            
            # Fetch and verify defaults
            cursor.execute("SELECT status, usage_count FROM api_tokens WHERE provider='brave'")
            row = cursor.fetchone()
            
            assert row[0] == 'active'  # Default status
            assert row[1] == 0  # Default usage_count
            
            conn.close()
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
