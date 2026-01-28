# Quick Start Guide for New Features

## Overview

This guide shows you how to use the new collection workflows and features that have been added to the project.

## 1. Using the Category Configuration

The categories are now in a separate configuration file that you can easily modify:

```bash
# View the category configuration
cat config/categories.yaml

# Categories are automatically loaded by the system
python -m ai_actuarial catalog
```

### Adding Custom Categories

Edit `config/categories.yaml`:

```yaml
categories:
  "My Custom Category":
    - keyword1
    - keyword2
    - "multi word phrase"
```

## 2. Collecting from Specific URLs

Quickly collect documents from known URLs:

```bash
# Single URL
python -m ai_actuarial collect url https://www.soa.org/research/my-report.pdf

# Multiple URLs
python -m ai_actuarial collect url \
  https://www.soa.org/research/report1.pdf \
  https://www.soa.org/research/report2.pdf \
  https://www.casact.org/article.pdf

# With custom name
python -m ai_actuarial collect url https://example.com/doc.pdf --name "Important Research"

# Skip duplicate detection (force download)
python -m ai_actuarial collect url https://example.com/doc.pdf --no-db-check
```

### What happens:
- ✅ Checks database for duplicates (by URL and SHA256)
- ✅ Downloads only new files
- ✅ Adds metadata to database
- ✅ Organizes files in `data/files/`

## 3. Importing Local Files

Import files from your computer (from emails, downloads, etc):

```bash
# Import a single file
python -m ai_actuarial collect file ~/Downloads/research-paper.pdf

# Import multiple files
python -m ai_actuarial collect file \
  ~/Downloads/paper1.pdf \
  ~/Desktop/report.docx \
  /path/to/presentation.pptx

# Organize into specific subdirectory
python -m ai_actuarial collect file ~/Downloads/*.pdf --subdir downloaded_papers

# With custom collection name
python -m ai_actuarial collect file ~/Downloads/paper.pdf --name "Email Attachments"
```

### What happens:
- ✅ Calculates SHA256 hash
- ✅ Checks for duplicates
- ✅ Copies files to `data/files/imported/` (or custom subdir)
- ✅ Adds to database with metadata

## 4. Starting the Web Interface

Launch a web interface for managing collections (requires Flask):

```bash
# Install Flask if needed
pip install flask

# Start web server (localhost only)
python -m ai_actuarial web

# Start on all interfaces (WARNING: use only in trusted networks)
python -m ai_actuarial web --host 0.0.0.0 --port 8080

# Debug mode (auto-reload on code changes)
python -m ai_actuarial web --debug
```

Then open http://localhost:5000 in your browser.

### Current features:
- View collection types
- API endpoints for automation
- Ready for future UI development

## 5. Using Document Processors

Process and filter documents programmatically:

```python
from ai_actuarial.processors import DocumentCleaner, DocumentCategorizer
from ai_actuarial.utils import load_category_config

# Load configuration
config = load_category_config()

# Check if document is AI-related
cleaner = DocumentCleaner(config['ai_filter_keywords'])
is_ai = cleaner.is_ai_related(
    text="Document discussing machine learning...",
    title="ML in Insurance",
    filename="ml-report.pdf"
)
print(f"Is AI-related: {is_ai}")

# Categorize a document
categorizer = DocumentCategorizer(config['categories'])
category = categorizer.categorize(
    text="This document discusses risk management and capital allocation...",
    title="ERM Framework"
)
print(f"Category: {category}")  # Output: "Risk & Capital"

# Get multiple categories
categories = categorizer.categorize_multi(
    text="AI-driven risk models for pricing...",
    min_score=2
)
print(f"Categories: {categories}")  # Output: ["AI", "Risk & Capital", "Pricing"]
```

## 6. Filtering by Category

Filter documents for specific projects:

```python
from ai_actuarial.storage import Storage
from ai_actuarial.processors import DocumentCategorizer
from ai_actuarial.utils import load_category_config

# Setup
storage = Storage("data/index.db")
config = load_category_config()
categorizer = DocumentCategorizer(config["categories"])

# Get all documents
all_docs = storage.export_files()

# Assign categories (if not already done)
for doc in all_docs:
    if not doc.get("category"):
        # Extract text from file and categorize
        # (simplified example)
        category = categorizer.categorize(
            text="",  # Would extract from file
            title=doc.get("title", "")
        )
        doc["category"] = category

# Filter for AI-related documents only
ai_docs = categorizer.filter_by_category(all_docs, ["AI", "Data & Analytics"])

print(f"Total documents: {len(all_docs)}")
print(f"AI documents: {len(ai_docs)}")

# Process AI documents with another tool
for doc in ai_docs:
    print(f"- {doc['title']} [{doc['category']}]")
```

## 7. Complete Workflow Example

Here's a complete workflow combining multiple features:

```bash
# Step 1: Collect from specific URLs
python -m ai_actuarial collect url \
  https://www.soa.org/research/ai-report.pdf \
  https://www.casact.org/ml-study.pdf \
  --name "Quarterly Research"

# Step 2: Import files from downloads
python -m ai_actuarial collect file \
  ~/Downloads/*.pdf \
  --subdir quarterly_import

# Step 3: Generate catalog with categorization
python -m ai_actuarial catalog --ai-only

# Step 4: Export results
python -m ai_actuarial export --format md --output data/quarterly_report.md

# Step 5: View in web interface
python -m ai_actuarial web
```

## 8. Scheduled Automation

Set up automated collections:

### Linux/Mac (cron)
```bash
# Edit crontab
crontab -e

# Add weekly collection (Mondays at 3 AM)
0 3 * * 1 cd /path/to/project && python -m ai_actuarial update

# Add daily URL collection
0 2 * * * cd /path/to/project && python -m ai_actuarial collect url https://example.com/daily.pdf
```

### Windows (Task Scheduler)
Create a batch file `collect.bat`:
```batch
@echo off
cd C:\path\to\project
python -m ai_actuarial update
python -m ai_actuarial catalog
```

Schedule it to run weekly using Task Scheduler.

## 9. Troubleshooting

### Category config not loading
```bash
# Check if file exists
ls -la config/categories.yaml

# Test loading
python -c "from ai_actuarial.utils import load_category_config; print(load_category_config())"
```

### Web interface not starting
```bash
# Install Flask
pip install flask

# Test Flask
python -c "import flask; print('Flask installed')"
```

### Duplicates not being detected
```python
# Check storage methods
from ai_actuarial.storage import Storage
storage = Storage("data/index.db")

# Query by URL
file = storage.get_file_by_url("https://example.com/file.pdf")
print(f"Found: {file is not None}")

# Query by hash
file = storage.get_file_by_sha256("abc123...")
print(f"Found: {file is not None}")
```

## 10. Migration from Existing Setup

If you're already using the project:

1. **All existing commands still work**:
   ```bash
   python -m ai_actuarial update  # Still works!
   python -m ai_actuarial catalog  # Still works!
   ```

2. **Add the category configuration**:
   - The file is already created: `config/categories.yaml`
   - Modify it to match your needs
   - If missing, system uses default values

3. **Try new features gradually**:
   - Start with `collect url` for quick tests
   - Then try `collect file` for imports
   - Use `web` interface when ready

4. **No data migration needed**:
   - Existing database works as-is
   - New features add functionality, don't replace

## Need Help?

- **Comprehensive Guide**: See `MODULAR_SYSTEM_GUIDE.md`
- **Implementation Details**: See `IMPLEMENTATION_SUMMARY.md`
- **API Documentation**: Check module READMEs in `ai_actuarial/collectors/` and `ai_actuarial/processors/`

## Summary

The new modular structure gives you:
- ✅ More flexibility in how you collect documents
- ✅ Better organization with category configuration
- ✅ Automatic duplicate detection
- ✅ Foundation for web-based management
- ✅ All existing features preserved

Start with simple commands and gradually explore more features as needed!
