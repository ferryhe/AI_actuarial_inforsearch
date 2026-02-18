"""
Database migration script to create api_tokens table.

This script creates the api_tokens table with proper schema and indexes
for storing encrypted API tokens. It uses the database path from the
application configuration.

Usage:
    python scripts/create_api_tokens_table.py
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
from config.yaml_config import load_database_config


def create_api_tokens_table():
    """Create api_tokens table in the database.
    
    Creates the table with all necessary columns and indexes for efficient
    querying. The provider+category combination is enforced as unique.
    """
    
    # Get database configuration
    try:
        db_config = load_database_config()
        db_path = db_config.get('path', 'data/index.db')
    except Exception as e:
        print(f"Warning: Could not load database config: {e}")
        db_path = 'data/index.db'
    
    print(f"Creating api_tokens table in {db_path}...")
    
    # Ensure directory exists
    db_dir = Path(db_path).parent
    db_dir.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
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
        
        # Create indexes for performance
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_provider_status 
            ON api_tokens(provider, status)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_category 
            ON api_tokens(category)
        ''')
        
        conn.commit()
        print("✅ api_tokens table created successfully")
        
        # Verify table structure
        cursor.execute("PRAGMA table_info(api_tokens)")
        columns = cursor.fetchall()
        print(f"\nTable structure ({len(columns)} columns):")
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error creating table: {e}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    create_api_tokens_table()
