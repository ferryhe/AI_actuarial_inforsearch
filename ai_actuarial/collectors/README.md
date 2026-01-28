# Collectors Module

This module contains different collection workflows for gathering documents from various sources.

## Overview

The collectors module provides a modular approach to data collection with the following components:

### Base Classes

- **BaseCollector**: Abstract base class defining the collector interface
- **CollectionConfig**: Configuration object for collection operations
- **CollectionResult**: Result object containing collection statistics

### Collector Implementations

#### ScheduledCollector
For regular, periodic crawling of configured sites.
- Integrates with the existing crawler
- Follows site configurations from `config/sites.yaml`
- Automatic database duplicate detection

#### AdhocCollector
For one-time, manual collection operations.
- Lower page limits for quick checks
- Can target specific sites
- Automatic database duplicate detection

#### URLCollector
For collecting files from specific URLs.
- Single URL or list of URLs
- Minimal crawling (single page)
- Automatic database duplicate detection

#### FileCollector
For importing files from the local filesystem.
- SHA256-based duplicate detection
- Copies files to download directory
- Adds metadata to database

## Usage

### Via CLI

```bash
# Collect from specific URLs
python -m ai_actuarial collect url https://example.com/file.pdf

# Import local files
python -m ai_actuarial collect file /path/to/file.pdf /path/to/another.docx

# With options
python -m ai_actuarial collect url https://example.com/file.pdf --name "My Collection" --no-db-check
python -m ai_actuarial collect file /path/to/file.pdf --subdir my_imports
```

### Programmatic

```python
from ai_actuarial.storage import Storage
from ai_actuarial.crawler import Crawler
from ai_actuarial.collectors import CollectionConfig
from ai_actuarial.collectors.url import URLCollector

# Setup
storage = Storage("data/index.db")
crawler = Crawler(storage, "data/files", "MyAgent/1.0")

# Create collector
collector = URLCollector(storage, crawler)

# Configure collection
config = CollectionConfig(
    name="My Collection",
    source_type="url",
    check_database=True,
    metadata={"urls": ["https://example.com/file.pdf"]}
)

# Run collection
result = collector.collect(config)
print(f"Downloaded: {result.items_downloaded}")
```

## Database Duplicate Detection

All collectors support automatic duplicate detection using:
- URL matching: Check if the same URL has been downloaded before
- SHA256 matching: Check if the same content (by hash) exists
- Skip downloads if duplicates are found (configurable)

This helps avoid:
- Re-downloading the same file
- Storing duplicate content
- Wasting bandwidth and storage
