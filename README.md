# AI Actuarial Info Search

A Python tool for discovering, downloading, and cataloging AI-related documents from actuarial organization websites worldwide.

## Features

- **Web Crawling**: Automatically crawls actuarial organization websites to find AI-related content
- **File Downloads**: Downloads PDFs, Word documents, PowerPoints, and Excel files
- **Smart Filtering**: Keyword-based filtering to keep only AI/ML-related content
- **Web Search Integration**: Optional Brave and SerpAPI search for broader discovery
- **Catalog Generation**: Extracts keywords, summaries, and categories from downloaded files
- **Multi-language Support**: Supports keywords in English, Chinese, French, German, Italian, Spanish, Korean, and Japanese

## Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`

## Installation

```bash
# Clone the repository
git clone https://github.com/ferryhe/AI_actuarial_inforsearch.git
cd AI_actuarial_inforsearch

# Install dependencies
pip install -r requirements.txt
```

## Quick Start

1. Edit `config/sites.yaml` to adjust sites, limits, and keywords.
2. Run:
```bash
python -m ai_actuarial update
```

## Project Structure

```
AI_actuarial_inforsearch/
├── ai_actuarial/           # Main package
│   ├── __init__.py
│   ├── __main__.py         # Entry point
│   ├── cli.py              # Command-line interface
│   ├── crawler.py          # Web crawler logic
│   ├── search.py           # Web search API integration
│   ├── storage.py          # SQLite database storage
│   ├── catalog.py          # Keyword/summary extraction
│   └── utils.py            # Utility functions
├── config/
│   └── sites.yaml          # Site configuration
├── scripts/
│   └── catalog_resume.py   # Resumable catalog generation
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Output

- **Downloads**: `data/files/` - Downloaded files organized by domain
- **Index database**: `data/index.db` - SQLite database with file metadata
- **Last run**: `data/last_run_new.json` - New files from the most recent run
- **Updates**: `data/updates/update_YYYYMMDD_HHMMSSZ.(json|md)` - Timestamped update logs
- **Export**: Run `python -m ai_actuarial export --format md --output data/files.md`

Downloaded files keep their original filenames. If a name conflicts, a suffix like `_1`, `_2` is appended.

## Commands

### Update (Crawl and Download)

```bash
# Full update (all configured sites)
python -m ai_actuarial update

# Target specific site
python -m ai_actuarial --site "SOA" update

# Skip web search
python -m ai_actuarial update --no-search

# Limit crawl depth and pages
python -m ai_actuarial --site "SOA" --max-pages 50 --max-depth 2 update
```

### Export

```bash
# Export to CSV
python -m ai_actuarial export --output data/files.csv

# Export to Markdown
python -m ai_actuarial export --format md --output data/files.md

# Export to JSON
python -m ai_actuarial export --format json --output data/files.json
```

### Catalog Generation

Generate keyword and summary catalogs:

```bash
# Basic catalog
python -m ai_actuarial catalog --site "SOA,CAS" --limit 100

# AI-only filtering
python -m ai_actuarial catalog --ai-only --limit 100

# Use TF-IDF fallback (faster, no model download)
KEYBERT_DISABLE=1 python -m ai_actuarial catalog --limit 100

# Resumable batch processing (for large datasets)
python scripts/catalog_resume.py
```

Outputs:
- `data/catalog.md` - Markdown table with keywords and summaries
- `data/catalog.json` - JSON format

## Web Search Integration

Set API keys via environment variables or `.env`:

```
BRAVE_API_KEY=your_brave_key
SERPAPI_API_KEY=your_serpapi_key
```

Search runs via Brave first, then SerpAPI if Brave returns no results or fails.
SerpAPI uses the Google News engine with `tbs=sbd:1` to return results sorted by date.

## Configuration

### config/sites.yaml

```yaml
defaults:
  user_agent: "AI-Actuarial-InfoSearch/0.1"
  max_pages: 200
  max_depth: 2
  delay_seconds: 0.5
  keywords:
    - "artificial intelligence"
    - "machine learning"
  file_exts:
    - ".pdf"
    - ".docx"

sites:
  - name: "Society of Actuaries (SOA)"
    url: "https://www.soa.org/"
    keywords:
      - "artificial intelligence"
      - "machine learning"
    exclude_keywords:
      - "exam"
      - "solution"
```

### Keyword Filtering

- **Global defaults**: `defaults.keywords`
- **Per-site overrides**: `sites[].keywords`
- **Per-site exclusions**: `sites[].exclude_keywords`
- **Filename prefix exclusions**: `sites[].exclude_prefixes`

## Scheduling

### Linux (cron)

```bash
# Weekly run at 3 AM on Mondays
0 3 * * 1 cd /path/to/project && python -m ai_actuarial update
```

### Windows (Task Scheduler)

Run `python -m ai_actuarial update` daily or weekly via Task Scheduler.

## Runbook

### Scheduled Run (Recommended Weekly)

1. Ensure `.env` contains your API keys:
   ```
   BRAVE_API_KEY=your_brave_key
   SERPAPI_API_KEY=your_serpapi_key
   ```
2. Run the crawler:
   ```bash
   python -m ai_actuarial update
   ```
3. Export the review list:
   ```bash
   python -m ai_actuarial export --format md --output data/files.md
   ```
4. Verify consistency:
   - Check that DB count matches `files.md` rows
   - Verify no missing files under `data/files/`

### Manual Focused Run (Ad-hoc)

1. Target a specific site:
   ```bash
   python -m ai_actuarial --site "SOA AI Topic" update --no-search
   ```
2. Limit scope for faster checks:
   ```bash
   python -m ai_actuarial --site "SOA AI Bulletin" --max-pages 10 --max-depth 1 update --no-search
   ```
3. Export for review:
   ```bash
   python -m ai_actuarial export --format md --output data/files.md
   ```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BRAVE_API_KEY` | Brave Search API key | - |
| `SERPAPI_API_KEY` | SerpAPI key | - |
| `KEYBERT_DISABLE` | Set to `1` to use TF-IDF instead of KeyBERT | `0` |
| `PDF_MAX_PAGES` | Max pages to extract from PDFs | `20` |
| `PDF_USE_MARKER` | Set to `1` to enable marker-pdf fallback | `0` |
| `CATALOG_CACHE_DIR` | Directory for extraction cache | `.cache/catalog_extract` |

## Supported Sites

The default configuration includes major actuarial organizations:

- International Actuarial Association (IAA)
- Society of Actuaries (SOA)
- Casualty Actuarial Society (CAS)
- American Academy of Actuaries (AAA)
- Institute and Faculty of Actuaries (IFoA, UK)
- Canadian Institute of Actuaries (CIA)
- China Association of Actuaries (CAA)
- And many more (see `config/sites.yaml`)

## Notes

- Some sites may block aggressive crawling. Tune `max_pages`, `delay_seconds`, and `user_agent` in `config/sites.yaml`.
- The crawler uses `trafilatura` (if installed) to improve title/date extraction.
- Files are deduplicated by URL and SHA256 hash.

## License

MIT License
