#!/usr/bin/env python3
"""
One-time migration script to move configuration from .env to sites.yaml

This script extracts non-sensitive configuration from environment variables
and writes them to sites.yaml. Sensitive credentials (API keys, tokens)
remain in .env file.

Usage:
    python scripts/migrate_env_to_yaml.py [--dry-run] [--backup]

Options:
    --dry-run    Show what would be migrated without making changes
    --backup     Create backup of sites.yaml before modifying (default: yes)
    --no-backup  Skip backup creation
"""

import os
import sys
import yaml
import argparse
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv


def get_bool_env(key: str, default: str = "false") -> bool:
    """Get boolean value from environment."""
    return os.getenv(key, default).lower() == "true"


def get_int_env(key: str, default: str) -> int:
    """Get integer value from environment."""
    try:
        return int(os.getenv(key, default))
    except ValueError:
        return int(default)


def get_float_env(key: str, default: str) -> float:
    """Get float value from environment."""
    try:
        return float(os.getenv(key, default))
    except ValueError:
        return float(default)


def extract_ai_config() -> dict:
    """
    Extract AI configuration from environment variables.
    
    Raises:
        ValueError: If environment variables contain invalid values with context about which section failed
    """
    try:
        return {
            "catalog": {
                "provider": "openai",
                "model": os.getenv("OPENAI_DEFAULT_MODEL", "gpt-4o-mini"),
                "temperature": get_float_env("CATALOG_TEMPERATURE", "0.7"),
                "timeout_seconds": get_int_env("OPENAI_TIMEOUT_SECONDS", "60"),
            },
            "embeddings": {
                "provider": os.getenv("RAG_EMBEDDING_PROVIDER", "openai"),
                "model": os.getenv("RAG_EMBEDDING_MODEL", "text-embedding-3-large"),
                "batch_size": get_int_env("RAG_EMBEDDING_BATCH_SIZE", "64"),
                "similarity_threshold": get_float_env("RAG_SIMILARITY_THRESHOLD", "0.4"),
                "cache_enabled": get_bool_env("RAG_EMBEDDING_CACHE_ENABLED", "true"),
            },
            "chatbot": {
                "provider": "openai",
                "model": os.getenv("CHATBOT_MODEL", "gpt-4-turbo"),
                "temperature": get_float_env("CHATBOT_TEMPERATURE", "0.7"),
                "max_tokens": get_int_env("CHATBOT_MAX_TOKENS", "1000"),
                "streaming_enabled": get_bool_env("CHATBOT_STREAMING_ENABLED", "true"),
                "max_context_messages": get_int_env("CHATBOT_MAX_CONTEXT_MESSAGES", "10"),
                "default_mode": os.getenv("CHATBOT_DEFAULT_MODE", "expert"),
                "enable_citation": get_bool_env("CHATBOT_ENABLE_CITATION", "true"),
                "min_citation_score": get_float_env("CHATBOT_MIN_CITATION_SCORE", "0.4"),
                "max_citations_per_response": get_int_env("CHATBOT_MAX_CITATIONS_PER_RESPONSE", "5"),
                "enable_query_validation": get_bool_env("CHATBOT_ENABLE_QUERY_VALIDATION", "true"),
                "enable_response_validation": get_bool_env("CHATBOT_ENABLE_RESPONSE_VALIDATION", "true"),
                "max_query_length": get_int_env("CHATBOT_MAX_QUERY_LENGTH", "1000"),
            },
            "ocr": {
                "provider": os.getenv("DEFAULT_ENGINE", "local"),
                "model": "docling",
                "mistral": {
                    "max_pdf_tokens": get_int_env("MISTRAL_MAX_PDF_TOKENS", "9000"),
                    "max_pages_per_chunk": get_int_env("MISTRAL_MAX_PAGES_PER_CHUNK", "10"),
                    "timeout_seconds": get_int_env("MISTRAL_TIMEOUT_SECONDS", "60"),
                    "retry_attempts": get_int_env("MISTRAL_RETRY_ATTEMPTS", "3"),
                    "extract_header": get_bool_env("MISTRAL_EXTRACT_HEADER", "true"),
                    "extract_footer": get_bool_env("MISTRAL_EXTRACT_FOOTER", "true"),
                },
                "siliconflow": {
                    "max_input_tokens": get_int_env("SILICONFLOW_MAX_INPUT_TOKENS", "3500"),
                    "chunk_overlap_tokens": get_int_env("SILICONFLOW_CHUNK_OVERLAP_TOKENS", "200"),
                    "timeout_seconds": get_int_env("SILICONFLOW_TIMEOUT_SECONDS", "60"),
                    "retry_attempts": get_int_env("SILICONFLOW_RETRY_ATTEMPTS", "3"),
                },
            },
        }
    except ValueError as e:
        raise ValueError(f"Error extracting AI configuration from environment variables: {e}") from e


def extract_rag_config() -> dict:
    """
    Extract RAG configuration from environment variables.
    
    Raises:
        ValueError: If environment variables contain invalid values
    """
    try:
        return {
            "chunk_strategy": os.getenv("RAG_CHUNK_STRATEGY", "semantic_structure"),
            "max_chunk_tokens": get_int_env("RAG_MAX_CHUNK_TOKENS", "800"),
            "min_chunk_tokens": get_int_env("RAG_MIN_CHUNK_TOKENS", "100"),
            "preserve_headers": get_bool_env("RAG_PRESERVE_HEADERS", "true"),
            "preserve_citations": get_bool_env("RAG_PRESERVE_CITATIONS", "true"),
            "include_hierarchy": get_bool_env("RAG_INCLUDE_HIERARCHY", "true"),
            "index_type": os.getenv("RAG_INDEX_TYPE", "Flat"),
        }
    except ValueError as e:
        raise ValueError(f"Error extracting RAG configuration from environment variables: {e}") from e


def extract_features() -> dict:
    """
    Extract feature flags from environment variables.
    
    Raises:
        ValueError: If environment variables contain invalid values
    """
    try:
        return {
            "enable_file_deletion": get_bool_env("ENABLE_FILE_DELETION", "false"),
            "require_auth": get_bool_env("REQUIRE_AUTH", "false"),
            "enable_csrf": get_bool_env("ENABLE_CSRF", "false"),
            "enable_security_headers": get_bool_env("ENABLE_SECURITY_HEADERS", "true"),
            "expose_error_details": get_bool_env("EXPOSE_ERROR_DETAILS", "false"),
            "enable_global_logs_api": get_bool_env("ENABLE_GLOBAL_LOGS_API", "false"),
            "enable_rate_limiting": get_bool_env("ENABLE_RATE_LIMITING", "false"),
            "rate_limit_defaults": os.getenv("RATE_LIMIT_DEFAULTS", "200 per hour, 50 per minute"),
            "rate_limit_storage_uri": os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),
            "content_security_policy": os.getenv("CONTENT_SECURITY_POLICY", ""),
        }
    except ValueError as e:
        raise ValueError(f"Error extracting feature flags from environment variables: {e}") from e


def extract_server_config() -> dict:
    """
    Extract server configuration from environment variables.
    
    Raises:
        ValueError: If environment variables contain invalid values
    """
    try:
        return {
            "host": os.getenv("FLASK_HOST", "0.0.0.0"),
            "port": get_int_env("FLASK_PORT", "5000"),
            "max_content_length": get_int_env("MAX_CONTENT_LENGTH", "52428800"),
            "flask_env": os.getenv("FLASK_ENV", "production"),
            "flask_debug": get_bool_env("FLASK_DEBUG", "false"),
        }
    except ValueError as e:
        raise ValueError(f"Error extracting server configuration from environment variables: {e}") from e


def extract_database_config() -> dict:
    """
    Extract database configuration from environment variables.
    
    Raises:
        ValueError: If environment variables contain invalid values
    """
    try:
        db_type = os.getenv("DB_TYPE", "sqlite")
        
        config = {
            "type": db_type,
        }
        
        if db_type == "sqlite":
            config["path"] = os.getenv("DB_PATH", "data/index.db")
        elif db_type == "postgresql":
            config["host"] = os.getenv("DB_HOST", "localhost")
            config["port"] = get_int_env("DB_PORT", "5432")
            config["database"] = os.getenv("DB_NAME", "ai_actuarial")
            config["username"] = os.getenv("DB_USER", "postgres")
            # Password remains in .env
        
        return config
    except ValueError as e:
        raise ValueError(f"Error extracting database configuration from environment variables: {e}") from e


def migrate(dry_run: bool = False, create_backup: bool = True) -> None:
    """
    Migrate configuration from .env to sites.yaml.
    
    Args:
        dry_run: If True, show what would be done without making changes
        create_backup: If True, create backup before modifying
    """
    # Load environment variables
    load_dotenv()
    
    # Determine sites.yaml path
    sites_path = Path("config/sites.yaml")
    if not sites_path.exists():
        print(f"❌ Error: {sites_path} not found")
        sys.exit(1)
    
    # Load current sites.yaml
    with open(sites_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}
    
    print("🔍 Analyzing current configuration...")
    print(f"   sites.yaml path: {sites_path.absolute()}")
    
    # Check what's already in sites.yaml
    has_ai_config = "ai_config" in config
    has_rag_config = "rag_config" in config
    has_features = "features" in config
    has_server = "server" in config
    has_database = "database" in config
    
    print(f"   Existing sections:")
    print(f"     - ai_config: {'✓' if has_ai_config else '✗'}")
    print(f"     - rag_config: {'✓' if has_rag_config else '✗'}")
    print(f"     - features: {'✓' if has_features else '✗'}")
    print(f"     - server: {'✓' if has_server else '✗'}")
    print(f"     - database: {'✓' if has_database else '✗'}")
    print()
    
    # Extract configuration from environment
    print("📦 Extracting configuration from environment variables...")
    
    new_sections = {}
    
    if not has_ai_config:
        new_sections["ai_config"] = extract_ai_config()
        print("   ✓ ai_config extracted")
    else:
        print("   ⊘ ai_config already exists (skipping)")
    
    if not has_rag_config:
        new_sections["rag_config"] = extract_rag_config()
        print("   ✓ rag_config extracted")
    else:
        print("   ⊘ rag_config already exists (skipping)")
    
    if not has_features:
        new_sections["features"] = extract_features()
        print("   ✓ features extracted")
    else:
        print("   ⊘ features already exists (skipping)")
    
    if not has_server:
        new_sections["server"] = extract_server_config()
        print("   ✓ server extracted")
    else:
        print("   ⊘ server already exists (skipping)")
    
    if not has_database:
        new_sections["database"] = extract_database_config()
        print("   ✓ database extracted")
    else:
        print("   ⊘ database already exists (skipping)")
    
    if not new_sections:
        print("\n✅ All configuration sections already exist in sites.yaml")
        print("   No migration needed!")
        return
    
    print()
    
    if dry_run:
        print("🔎 DRY RUN - Would add the following sections to sites.yaml:")
        print()
        for section, content in new_sections.items():
            print(f"  {section}:")
            print(yaml.dump({section: content}, default_flow_style=False, allow_unicode=True, indent=2))
        print("Run without --dry-run to apply changes")
        return
    
    # Create backup if requested
    if create_backup:
        backup_path = sites_path.with_suffix(f'.yaml.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        with open(backup_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, indent=2)
        print(f"💾 Backup created: {backup_path}")
    
    # Update configuration
    config.update(new_sections)
    
    # Write back to sites.yaml
    with open(sites_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, indent=2)
    
    print(f"\n✅ Migration complete!")
    print(f"   Added {len(new_sections)} section(s) to {sites_path}")
    print()
    print("📝 Next steps:")
    print("   1. Review the changes in config/sites.yaml")
    print("   2. Update your .env file to remove non-sensitive configuration")
    print("   3. Use the new .env.example as a reference")
    print("   4. Restart the application to use the new configuration")
    print()
    print("💡 Tip: Changes to sites.yaml take effect immediately (no restart needed)")
    print("   Only API keys and tokens need to stay in .env")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate configuration from .env to sites.yaml",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview what would be migrated
  python scripts/migrate_env_to_yaml.py --dry-run
  
  # Migrate with backup (default)
  python scripts/migrate_env_to_yaml.py
  
  # Migrate without backup
  python scripts/migrate_env_to_yaml.py --no-backup
        """
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes"
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        default=True,
        help="Create backup of sites.yaml before modifying (default)"
    )
    parser.add_argument(
        "--no-backup",
        action="store_false",
        dest="backup",
        help="Skip backup creation"
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("Configuration Migration: .env → sites.yaml")
    print("=" * 70)
    print()
    
    try:
        migrate(dry_run=args.dry_run, create_backup=args.backup)
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during migration: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
