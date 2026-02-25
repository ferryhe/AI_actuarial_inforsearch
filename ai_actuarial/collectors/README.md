# Collectors Module

This module contains different collection workflows for gathering documents from various sources.

## Overview

The collectors module provides a modular approach to data collection with the following components.

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

#### WebPageCollector
For extracting and storing readable text content directly from HTML web pages.

Inspired by [ScrapeGraphAI](https://github.com/ScrapeGraphAI/Scrapegraph-ai), this
collector treats *page content* as a first-class document rather than only downloading
files linked from pages (PDF, DOC, etc.).

- Uses **trafilatura** for high-quality article text extraction (Markdown output)
- Saves extracted content as `.md` files under `<domain>/_web_pages/`
- Registers pages in the database with the same metadata as downloaded files
- Deduplication by URL **and** SHA-256 of the extracted text
- Works out-of-the-box with the existing RAG/cataloguing pipelines

**Typical use-cases**:
- Collecting actuarial research articles and blog posts that do not provide a
  downloadable PDF
- Archiving web page content for offline RAG search
- Supplementing file-download collections with the surrounding context pages

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

### Programmatic – WebPageCollector

```python
from ai_actuarial.storage import Storage
from ai_actuarial.collectors import CollectionConfig, WebPageCollector

# Setup
storage = Storage("data/index.db")
collector = WebPageCollector(storage, "data/files", user_agent="MyBot/1.0")

# Configure collection
config = CollectionConfig(
    name="SOA AI Research",
    source_type="web_page",
    check_database=True,
    metadata={
        "urls": [
            "https://www.soa.org/resources/research-reports/2024/ai-actuarial/",
            "https://www.actuaries.org/CTTEES_TF/AIActuarial/",
        ]
    },
)

# Run collection
result = collector.collect(config)
print(f"Collected: {result.items_downloaded} pages, skipped: {result.items_skipped}")
```

### Programmatic – URLCollector

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

### Enabling page-content extraction during site crawls

Set `collect_page_content=True` in `SiteConfig` to make the crawler also save
the text content of each relevant HTML page it visits:

```python
from ai_actuarial.crawler import Crawler, SiteConfig

cfg = SiteConfig(
    name="SOA AI Topic",
    url="https://www.soa.org/research/topics/artificial-intelligence-topic-landing/",
    keywords=["artificial intelligence", "machine learning"],
    collect_page_content=True,  # extract & store HTML page text as .md
)

crawler = Crawler(storage, "data/files", user_agent="MyBot/1.0")
items = crawler.crawl_site(cfg)
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
