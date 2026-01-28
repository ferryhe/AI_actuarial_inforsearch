# Processors Module

This module contains document processing components for cleaning and categorizing collected files.

## Overview

The processors module provides tools for:
- Document cleaning and validation
- Document categorization
- Content filtering

## Components

### DocumentCleaner

Validates and filters collected documents.

**Features:**
- AI-related content detection
- File validation (size, type, existence)
- Text cleaning and normalization
- Configurable keyword-based filtering

**Usage:**

```python
from ai_actuarial.processors import DocumentCleaner

cleaner = DocumentCleaner(ai_filter_keywords=["AI", "machine learning"])

# Check if document is AI-related
is_ai = cleaner.is_ai_related(
    text="This document discusses machine learning...",
    title="ML in Insurance",
    filename="ml-insurance.pdf"
)

# Check if file should be kept
should_keep, reason = cleaner.should_keep(
    file_path="/path/to/file.pdf",
    title="Document Title",
    ai_only=True
)

# Clean text
clean_text = cleaner.clean_text(raw_text)
```

### DocumentCategorizer

Categorizes documents based on content and keywords.

**Features:**
- Single or multi-category assignment
- Keyword-based scoring
- Category filtering
- Configurable category rules

**Usage:**

```python
from ai_actuarial.processors import DocumentCategorizer
from ai_actuarial.utils import load_category_config

# Load category configuration
config = load_category_config("config/categories.yaml")
categories = config["categories"]

# Create categorizer
categorizer = DocumentCategorizer(categories)

# Categorize a document
category = categorizer.categorize(
    text="This document discusses artificial intelligence in actuarial work...",
    title="AI in Actuarial Science",
    keywords=["AI", "machine learning", "insurance"]
)
# Returns: "AI"

# Get multiple categories
categories = categorizer.categorize_multi(
    text="Risk management using machine learning models...",
    title="ML Risk Models",
    min_score=2
)
# Returns: ["AI", "Risk & Capital", "Data & Analytics"]

# Filter documents by category
filtered = categorizer.filter_by_category(
    documents=[
        {"title": "Doc 1", "category": "AI"},
        {"title": "Doc 2", "category": "Pricing"},
        {"title": "Doc 3", "category": "AI"},
    ],
    categories=["AI"]
)
# Returns: [{"title": "Doc 1", ...}, {"title": "Doc 3", ...}]
```

## Category Configuration

Categories are defined in `config/categories.yaml` with keyword lists for each category.

Example:
```yaml
categories:
  AI:
    - artificial intelligence
    - machine learning
    - deep learning
  
  "Risk & Capital":
    - risk
    - capital
    - stress testing
```

## Integration with Catalog Pipeline

The processors integrate with the catalog generation pipeline:

1. **Collection**: Files are collected using collectors
2. **Cleaning**: DocumentCleaner validates and filters files
3. **Categorization**: DocumentCategorizer assigns categories
4. **Storage**: Results are stored in the database

The catalog pipeline automatically uses these processors when `ai_only` filtering is enabled.
