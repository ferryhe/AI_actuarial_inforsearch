#!/usr/bin/env python3
"""Test script for database backend abstraction.

This script demonstrates how to use both SQLite and PostgreSQL backends.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from ai_actuarial.storage import Storage
from ai_actuarial.storage_v2 import StorageV2
from ai_actuarial.storage_factory import create_storage_from_config, get_database_config_from_env


def test_legacy_storage():
    """Test original Storage class (SQLite only)."""
    print("=" * 60)
    print("Testing Legacy Storage (SQLite)")
    print("=" * 60)
    
    storage = Storage("/tmp/test_legacy.db")
    
    # Insert a test file
    storage.insert_file(
        url="http://example.com/legacy_test.pdf",
        sha256="legacy_hash_123",
        title="Legacy Test File",
        source_site="example.com",
        source_page_url="http://example.com/page",
        original_filename="legacy_test.pdf",
        local_path="/tmp/legacy_test.pdf",
        bytes=1024,
        content_type="application/pdf",
    )
    
    # Verify
    exists = storage.file_exists("http://example.com/legacy_test.pdf")
    file_data = storage.get_file_by_url("http://example.com/legacy_test.pdf")
    
    print(f"✓ File exists: {exists}")
    print(f"✓ File title: {file_data['title'] if file_data else None}")
    
    storage.close()
    print("✓ Legacy Storage test passed!\n")


def test_storagev2_sqlite():
    """Test StorageV2 with SQLite backend."""
    print("=" * 60)
    print("Testing StorageV2 with SQLite Backend")
    print("=" * 60)
    
    db_config = {
        "type": "sqlite",
        "path": "/tmp/test_storagev2_sqlite.db"
    }
    
    storage = StorageV2(db_config=db_config)
    
    # Insert a test file
    storage.insert_file(
        url="http://example.com/v2_sqlite_test.pdf",
        sha256="v2_sqlite_hash_456",
        title="StorageV2 SQLite Test",
        source_site="example.com",
        source_page_url="http://example.com/page",
        original_filename="v2_test.pdf",
        local_path="/tmp/v2_test.pdf",
        bytes=2048,
        content_type="application/pdf",
    )
    
    # Verify
    exists = storage.file_exists("http://example.com/v2_sqlite_test.pdf")
    file_data = storage.get_file_by_url("http://example.com/v2_sqlite_test.pdf")
    
    print(f"✓ File exists: {exists}")
    print(f"✓ File title: {file_data['title'] if file_data else None}")
    
    # Test upsert
    storage.upsert_file(
        url="http://example.com/v2_sqlite_test.pdf",
        sha256="v2_sqlite_hash_456_updated",
        title="StorageV2 SQLite Test (Updated)",
        source_site="example.com",
        source_page_url="http://example.com/page",
        original_filename="v2_test_updated.pdf",
        local_path="/tmp/v2_test_updated.pdf",
        bytes_size=3072,
        content_type="application/pdf",
        last_modified=None,
        etag=None,
        published_time=None,
    )
    
    file_data = storage.get_file_by_url("http://example.com/v2_sqlite_test.pdf")
    print(f"✓ Updated title: {file_data['title'] if file_data else None}")
    
    storage.close()
    print("✓ StorageV2 SQLite test passed!\n")


def test_storagev2_postgresql():
    """Test StorageV2 with PostgreSQL backend (requires PostgreSQL server)."""
    print("=" * 60)
    print("Testing StorageV2 with PostgreSQL Backend")
    print("=" * 60)
    
    # Check if PostgreSQL credentials are available
    if not os.getenv("POSTGRES_HOST"):
        print("⚠ PostgreSQL test skipped (no POSTGRES_HOST environment variable)")
        print("  To run this test, set:")
        print("    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB,")
        print("    POSTGRES_USER, POSTGRES_PASSWORD")
        print()
        return
    
    db_config = {
        "type": "postgresql",
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "database": os.getenv("POSTGRES_DB", "ai_actuarial_test"),
        "username": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
    }
    
    try:
        storage = StorageV2(db_config=db_config)
        
        # Insert a test file
        storage.insert_file(
            url="http://example.com/v2_pg_test.pdf",
            sha256="v2_pg_hash_789",
            title="StorageV2 PostgreSQL Test",
            source_site="example.com",
            source_page_url="http://example.com/page",
            original_filename="v2_pg_test.pdf",
            local_path="/tmp/v2_pg_test.pdf",
            bytes=4096,
            content_type="application/pdf",
        )
        
        # Verify
        exists = storage.file_exists("http://example.com/v2_pg_test.pdf")
        file_data = storage.get_file_by_url("http://example.com/v2_pg_test.pdf")
        
        print(f"✓ File exists: {exists}")
        print(f"✓ File title: {file_data['title'] if file_data else None}")
        
        storage.close()
        print("✓ StorageV2 PostgreSQL test passed!\n")
    except Exception as e:
        print(f"✗ PostgreSQL test failed: {e}")
        print("  Make sure PostgreSQL server is running and credentials are correct\n")


def test_factory():
    """Test storage factory."""
    print("=" * 60)
    print("Testing Storage Factory")
    print("=" * 60)
    
    # Test legacy config
    config1 = {"paths": {"db": "/tmp/test_factory_legacy.db"}}
    storage1 = create_storage_from_config(config1)
    print(f"✓ Legacy config created: {type(storage1).__name__}")
    storage1.close()
    
    # Test new SQLite config
    config2 = {"database": {"type": "sqlite", "path": "/tmp/test_factory_new.db"}}
    storage2 = create_storage_from_config(config2)
    print(f"✓ New SQLite config created: {type(storage2).__name__}")
    storage2.close()
    
    print("✓ Storage factory test passed!\n")


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("DATABASE BACKEND TESTS")
    print("=" * 60 + "\n")
    
    try:
        test_legacy_storage()
        test_storagev2_sqlite()
        test_factory()
        test_storagev2_postgresql()
        
        print("=" * 60)
        print("ALL TESTS COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
