# Modular Collection System Guide

## Overview

This guide explains the new modular collection system and how it addresses the requirements for different collection workflows, categorization, and preparation for web interface integration.

## Key Changes

### 1. Category Configuration Extraction

**File:** `config/categories.yaml`

Categories have been extracted into a separate configuration file, making it easy to:
- Add new categories without modifying code
- Maintain category definitions in one place
- Share category configurations across projects
- Update keywords for better classification

**Usage:**
```python
from ai_actuarial.utils import load_category_config

config = load_category_config()
categories = config["categories"]
ai_keywords = config["ai_keywords"]
```

### 2. Modular Collection Structure

**New Modules:**

#### `ai_actuarial/collectors/`
Different collection workflows organized by source type:

- **ScheduledCollector**: Regular periodic crawling (existing `update` command)
- **AdhocCollector**: One-time manual collections
- **URLCollector**: Collect from specific URLs
- **FileCollector**: Import files from local filesystem

**Benefits:**
- Separation of concerns
- Easy to add new collection types
- Consistent interface via `BaseCollector`
- Built-in duplicate detection

#### `ai_actuarial/processors/`
Document processing and filtering:

- **DocumentCleaner**: Validates files, checks AI-relevance, cleans text
- **DocumentCategorizer**: Assigns categories based on content

**Benefits:**
- Reusable across different workflows
- Consistent categorization logic
- Easy to extend with new rules

#### `ai_actuarial/web/`
Web interface foundation:

- Flask application for managing collections
- API endpoints for collection operations
- Placeholder for future web UI

### 3. Database Duplicate Detection

All collectors implement automatic duplicate detection:

```python
def should_download(self, url: str, sha256: str | None = None) -> bool:
    # Check if URL already exists
    if self.storage.get_file_by_url(url):
        return False
    
    # Check if content already exists (by hash)
    if sha256 and self.storage.get_file_by_sha256(sha256):
        return False
    
    return True
```

This ensures:
- No duplicate downloads
- Efficient use of bandwidth
- Content deduplication across different sources

### 4. New CLI Commands

#### URL Collection
```bash
# Collect from specific URLs
python -m ai_actuarial collect url https://example.com/doc.pdf

# Multiple URLs
python -m ai_actuarial collect url https://example.com/doc1.pdf https://example.com/doc2.pdf
```

#### File Import
```bash
# Import local files
python -m ai_actuarial collect file /path/to/document.pdf

# Multiple files with custom subdirectory
python -m ai_actuarial collect file doc1.pdf doc2.pdf --subdir my_imports
```

#### Web Interface
```bash
# Start web server
python -m ai_actuarial web

# Custom host/port
python -m ai_actuarial web --host 0.0.0.0 --port 8080
```

## Workflow Examples

### Regular Scheduled Collection

For weekly automated runs:

```bash
# Traditional approach (still works)
python -m ai_actuarial update

# Or using the collector directly
python -m ai_actuarial update --site "SOA"
```

### Ad-hoc Collection from Specific Sites

For manual one-time collections:

```bash
# Target specific site with reduced limits
python -m ai_actuarial --site "SOA AI Topic" --max-pages 50 update --no-search
```

### Collecting Specific Documents

When you have specific URLs:

```bash
# Collect from URLs (with automatic duplicate detection)
python -m ai_actuarial collect url \
  https://www.soa.org/research/report1.pdf \
  https://www.soa.org/research/report2.pdf
```

### Importing External Documents

When you have files from email, downloads, etc:

```bash
# Import files from local disk
python -m ai_actuarial collect file \
  ~/Downloads/actuarial-report.pdf \
  ~/Desktop/research-paper.docx \
  --subdir external_sources
```

### Processing and Categorization

After collection, process files:

```bash
# Generate catalog with categorization
python -m ai_actuarial catalog

# AI-only filtering
python -m ai_actuarial catalog --ai-only

# Retry failed files
python -m ai_actuarial catalog --retry-errors
```

### Filtering by Category

Using the processors programmatically:

```python
from ai_actuarial.processors import DocumentCategorizer
from ai_actuarial.utils import load_category_config

# Load categories
config = load_category_config()
categorizer = DocumentCategorizer(config["categories"])

# Filter documents for a specific project
ai_docs = categorizer.filter_by_category(
    all_documents,
    categories=["AI", "Data & Analytics"]
)

# Process only AI-related documents for further analysis
for doc in ai_docs:
    process_document(doc)
```

## Future Web Interface Integration

The web interface foundation supports:

1. **Collection Management**
   - Start/stop collections
   - Monitor progress
   - View results

2. **Database Browser**
   - Search collected files
   - Filter by category
   - View metadata

3. **Scheduled Tasks**
   - Configure periodic collections
   - Manage schedules
   - View history

4. **Category Management**
   - Edit category definitions
   - Test categorization
   - View category statistics

## Migration Path

For existing users:

1. **Existing commands still work**: `update`, `catalog`, `export` are unchanged
2. **New commands are optional**: Use them when you need the functionality
3. **Categories are backward compatible**: Fallback to hardcoded values if config file is missing
4. **Gradual adoption**: You can use new features incrementally

## Next Steps for Future Enhancements

1. **Web Interface**
   - Create HTML templates
   - Add JavaScript frontend
   - Implement real-time progress updates
   - Add authentication

2. **Advanced Features**
   - Scheduled collections via web UI
   - Email notifications
   - API for external integrations
   - Bulk import from cloud storage

3. **AI Enhancements**
   - Better categorization using ML models
   - Automatic summary generation
   - Relevance scoring
   - Duplicate detection by content similarity

4. **Monitoring**
   - Collection metrics dashboard
   - Error tracking and alerts
   - Storage usage monitoring
   - Performance analytics

## Configuration Examples

### Adding Custom Categories

Edit `config/categories.yaml`:

```yaml
categories:
  # Add your custom category
  "Custom Category":
    - keyword1
    - keyword2
    - phrase three
  
  # Existing categories...
  AI:
    - artificial intelligence
    - machine learning
```

### Creating Custom Collection Workflow

```python
from ai_actuarial.collectors.base import BaseCollector, CollectionConfig, CollectionResult

class CustomCollector(BaseCollector):
    def collect(self, config: CollectionConfig) -> CollectionResult:
        # Your custom logic here
        pass
    
    def should_download(self, url: str, sha256: str | None = None) -> bool:
        # Your custom duplicate detection
        pass
```

## Troubleshooting

### Category Config Not Loading
```python
# Check if file exists
from pathlib import Path
Path("config/categories.yaml").exists()

# Try loading manually
from ai_actuarial.utils import load_category_config
config = load_category_config()
```

### Web Interface Not Starting
```bash
# Install Flask if missing
pip install flask

# Check if it works
python -m ai_actuarial web --help
```

### Duplicate Detection Not Working
```python
# Verify storage methods
from ai_actuarial.storage import Storage
storage = Storage("data/index.db")

# Test queries
file = storage.get_file_by_url("https://example.com/file.pdf")
file = storage.get_file_by_sha256("abc123...")
```
