# AI Actuarial Info Search

A Python tool for discovering, downloading, and cataloging AI-related documents from actuarial organization websites worldwide.

## Features

- **Web Crawling**: Automatically crawls actuarial organization websites to find AI-related content
- **File Downloads**: Downloads PDFs, Word documents, PowerPoints, and Excel files
- **Smart Filtering**: Keyword-based filtering to keep only AI/ML-related content
- **Web Search Integration**: Optional Brave and SerpAPI search for broader discovery
- **Catalog Generation**: Extracts keywords, summaries, and categories from downloaded files
- **Multi-language Support**: Supports keywords in English, Chinese, French, German, Italian, Spanish, Korean, and Japanese
- **Database Flexibility**: Supports both SQLite (local development) and PostgreSQL (production) backends
- **Enhanced Web Interface**:
    - **Site Management**: Add/Edit/Search collection sites with advanced exclusion rules (keywords/prefixes).
    - **Advanced Data Search**: Filter by Uncategorized, sort by Oldest/Newest, and auto-refresh results.
    - **Web Search Discovery**: Search globally or within specific sites using Brave/Google APIs to find new documents.
    - **Task Management**: Monitor active tasks, view execution history (persisted), and stop running collections.
    - **Global Logs**: Monitor system activity and debugging information.
    - **Smart Import**: "Browse Folder" support for easy local file ingestion.
    - **Strict Deduplication**: SHA256-based content matching to prevent duplicate downloads.

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

## Database Configuration

The application supports both SQLite (default) and PostgreSQL:

### SQLite (Default - No Setup Required)
```yaml
# config/sites.yaml
paths:
  db: data/index.db
```

### PostgreSQL (Production)
```yaml
# config/sites.yaml
database:
  type: postgresql
  host: localhost
  port: 5432
  database: ai_actuarial
  username: postgres
  password: your_password
```

For detailed database configuration options, see [DATABASE_BACKEND_GUIDE.md](DATABASE_BACKEND_GUIDE.md).

## Project Structure

```
AI_actuarial_inforsearch/
├── ai_actuarial/              # Main package
│   ├── __init__.py
│   ├── __main__.py            # Entry point
│   ├── cli.py                 # Command-line interface
│   ├── crawler.py             # Web crawler logic
│   ├── search.py              # Web search API integration
│   ├── storage.py             # SQLite database storage (legacy)
│   ├── storage_v2.py          # SQLAlchemy-based storage (NEW)
│   ├── storage_factory.py     # Database backend factory (NEW)
│   ├── db_backend.py          # Database abstraction layer (NEW)
│   ├── db_models.py           # SQLAlchemy ORM models (NEW)
│   ├── catalog.py             # Keyword/summary extraction
│   ├── utils.py               # Utility functions
│   ├── collectors/            # Collection workflows
│   │   ├── base.py            # Base collector interface
│   │   ├── scheduled.py       # Scheduled collection
│   │   ├── adhoc.py           # Ad-hoc collection
│   │   ├── url.py             # URL-based collection
│   │   └── file.py            # File import
│   ├── processors/            # Document processing
│   │   ├── cleaner.py         # Document cleaning/validation
│   │   └── categorizer.py     # Document categorization
│   └── web/                   # Web interface
│       └── app.py             # Flask application
├── config/
│   ├── sites.yaml             # Site configuration
│   └── categories.yaml        # Category definitions
├── scripts/
│   └── catalog_resume.py      # Resumable catalog generation
├── requirements.txt
├── pyproject.toml
├── DATABASE_BACKEND_GUIDE.md  # Database configuration guide (NEW)
└── README.md
```

## Output

- **Downloads**: `data/files/` - Downloaded files organized by domain
- **Index database**: `data/index.db` - SQLite database with file metadata and catalog state
- **Last run**: `data/last_run_new.json` - New files from the most recent run
- **Updates**: `data/updates/update_YYYYMMDD_HHMMSSZ.(json|md)` - Timestamped update logs
- **Catalog**: `data/catalog.jsonl` - Incremental catalog (JSONL format, append-only)
- **Catalog MD**: `data/catalog.md` - Markdown table with keywords and summaries
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

Generate keyword and summary catalogs using incremental processing (storage-backed by default):

```bash
# Default incremental pipeline (storage-backed)
python -m ai_actuarial catalog

# Legacy incremental pipeline
python -m ai_actuarial catalog --legacy-incremental

# AI-only filtering
python -m ai_actuarial catalog --ai-only

# Force reprocessing by changing catalog version
python -m ai_actuarial catalog --version catalog_v2

# Retry files that previously failed
python -m ai_actuarial catalog --retry-errors

# Use TF-IDF fallback (faster, no model download)
KEYBERT_DISABLE=1 python -m ai_actuarial catalog
```

**Incremental mode**:
- Tracks processed files in SQLite `catalog_items` table
- Only processes new files or files with changed sha256/version
- Appends to output files (no full rewrites)
- Outputs:
  - `data/catalog.jsonl` - JSON Lines format (one record per line, append-only)
  - `data/catalog.md` - Markdown table (append-only)

**Legacy mode** (for backward compatibility):
```bash
# Full rewrite to JSON format
python -m ai_actuarial catalog --legacy --limit 100

# With append
python -m ai_actuarial catalog --legacy --limit 100 --append
```
- Outputs: `data/catalog.json` (full JSON array, rewrites entire file)

### Verification (Incremental Repeatability)

Run incremental twice with the same version. The second run should process ~0 files
when nothing has changed.

```bash
# First run (requires files already downloaded via update)
python -m ai_actuarial catalog --version catalog_v2

# Second run (should be near-zero processed)
python -m ai_actuarial catalog --version catalog_v2
```

### Collection Workflows (NEW)

The modular collection system supports different workflows:

#### URL Collection

Collect files from specific URLs:

```bash
# Single URL
python -m ai_actuarial collect url https://www.soa.org/research/report.pdf

# Multiple URLs
python -m ai_actuarial collect url https://example.com/doc1.pdf https://example.com/doc2.pdf

# With custom name
python -m ai_actuarial collect url https://example.com/doc.pdf --name "My Collection"

# Skip database duplicate check
python -m ai_actuarial collect url https://example.com/doc.pdf --no-db-check
```

#### File Import

Import files from local filesystem:

```bash
# Single file
python -m ai_actuarial collect file /path/to/document.pdf

# Multiple files
python -m ai_actuarial collect file /path/to/doc1.pdf /path/to/doc2.docx

# Custom subdirectory
python -m ai_actuarial collect file /path/to/doc.pdf --subdir my_imports

# Skip database duplicate check
python -m ai_actuarial collect file /path/to/doc.pdf --no-db-check
```

**Features:**
- Automatic duplicate detection (by URL and SHA256)
- Metadata extraction and database integration
- File copying to organized download directory
- Support for all configured file types

### Web Interface (NEW)

Start a web interface for managing collections:

```bash
# Start with defaults (localhost:5000)
python -m ai_actuarial web

# Custom host and port
python -m ai_actuarial web --host 0.0.0.0 --port 8080

# Debug mode
python -m ai_actuarial web --debug
```

Then open http://localhost:5000 in your browser.

**Note:** Web interface requires Flask: `pip install flask`

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

### config/categories.yaml (NEW)

Define categories for document classification:

```yaml
categories:
  AI:
    - artificial intelligence
    - machine learning
    - deep learning
    - llm
  
  "Risk & Capital":
    - risk
    - capital
    - stress
    - scenario
  
  Pricing:
    - pricing
    - rate
    - premium

ai_filter_keywords:
  - artificial intelligence
  - machine learning
  - deep learning
  - neural
  - llm

ai_keywords:
  - artificial intelligence
  - machine learning
  - large language model
  - generative ai
```

**Category System Features:**
- Centralized category definitions
- Keyword-based classification
- Used by catalog generation and document processors
- Supports multi-language keywords
- Easy to extend with new categories

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

## Production Deployment

### Deploying on AWS EC2 with Docker and PostgreSQL

This guide shows how to deploy the application on an AWS EC2 instance (e.g., t3.medium) with Docker containers and PostgreSQL database.

#### Prerequisites

- AWS EC2 instance (Ubuntu/Amazon Linux)
- Docker and Docker Compose installed
- Caddy reverse proxy for HTTPS
- PostgreSQL container for database

#### 1. Prepare the Application

Create a `Dockerfile` for the application:

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy application files
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create data directory
RUN mkdir -p /app/data

# Expose port for web interface
EXPOSE 5000

# Run the application
CMD ["python", "-m", "ai_actuarial", "web", "--host", "0.0.0.0", "--port", "5000"]
```

#### 2. Configure PostgreSQL Connection

Update `config/sites.yaml` to use PostgreSQL:

```yaml
# config/sites.yaml
database:
  type: postgresql
  host: postgres-container-name  # Your PostgreSQL container name
  port: 5432
  database: ai_actuarial
  username: ai_user
  password: ${DB_PASSWORD}  # Set via environment variable

# ... rest of configuration
```

Or use environment variables (recommended for production):

```bash
export DB_TYPE=postgresql
export DB_HOST=postgres-container-name
export DB_PORT=5432
export DB_NAME=ai_actuarial
export DB_USER=ai_user
export DB_PASSWORD=your_secure_password
```

Then use `get_database_config_from_env()` in your application startup.

#### 3. Docker Compose Setup

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  ai-actuarial:
    build: .
    container_name: ai-actuarial-app
    ports:
      - "5000:5000"
    environment:
      - DB_TYPE=postgresql
      - DB_HOST=ai-actuarial-db
      - DB_PORT=5432
      - DB_NAME=ai_actuarial
      - DB_USER=ai_user
      - DB_PASSWORD=${DB_PASSWORD}
      - BRAVE_API_KEY=${BRAVE_API_KEY}
      - SERPAPI_API_KEY=${SERPAPI_API_KEY}
    volumes:
      - ./data:/app/data
      - ./config:/app/config
    depends_on:
      - db
    restart: unless-stopped
    networks:
      - app-network

  db:
    image: postgres:16-alpine
    container_name: ai-actuarial-db
    environment:
      - POSTGRES_DB=ai_actuarial
      - POSTGRES_USER=ai_user
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: unless-stopped
    networks:
      - app-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ai_user -d ai_actuarial"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:

networks:
  app-network:
    driver: bridge
```

#### 4. Caddy Reverse Proxy Configuration

Add to your Caddyfile (e.g., `/etc/caddy/Caddyfile`):

```caddyfile
# AI Actuarial Info Search
actuarial.aixintelligence.com {
    reverse_proxy ai-actuarial-app:5000
    encode gzip
    
    # Optional: Add authentication
    # basicauth {
    #     admin $2a$14$...hashed_password...
    # }
}
```

Reload Caddy:
```bash
sudo systemctl reload caddy
```

#### 5. Deploy the Application

```bash
# On your EC2 instance
cd /home/ec2-user/ai-actuarial-inforsearch

# Set environment variables
export DB_PASSWORD="your_secure_password"
export BRAVE_API_KEY="your_brave_api_key"
export SERPAPI_API_KEY="your_serpapi_key"

# Build and start containers
docker-compose up -d

# Check logs
docker-compose logs -f ai-actuarial

# Verify containers are running
docker ps
```

#### 6. Initialize the Database

The application will automatically create tables on first run. To manually initialize:

```bash
# Enter the container
docker exec -it ai-actuarial-app bash

# Run initial update
python -m ai_actuarial update

# Generate catalog
python -m ai_actuarial catalog
```

#### 7. Set Up Scheduled Runs

Create a cron job on the EC2 instance:

```bash
# Edit crontab
crontab -e

# Add weekly run at 3 AM on Mondays
0 3 * * 1 cd /home/ec2-user/ai-actuarial-inforsearch && docker-compose exec -T ai-actuarial python -m ai_actuarial update && docker-compose exec -T ai-actuarial python -m ai_actuarial catalog
```

#### 8. Monitoring and Maintenance

```bash
# View logs
docker-compose logs -f ai-actuarial

# Restart application
docker-compose restart ai-actuarial

# Update application
git pull
docker-compose build
docker-compose up -d

# Backup PostgreSQL database
docker exec ai-actuarial-db pg_dump -U ai_user ai_actuarial > backup_$(date +%Y%m%d).sql

# Check disk usage
du -sh data/
```

#### 9. Security Considerations

1. **Use strong passwords** for PostgreSQL
2. **Enable firewall** on EC2:
   ```bash
   # Only allow necessary ports
   sudo ufw allow 22    # SSH
   sudo ufw allow 80    # HTTP
   sudo ufw allow 443   # HTTPS
   sudo ufw enable
   ```
3. **Use AWS Security Groups** to restrict access
4. **Keep secrets in environment variables** or AWS Secrets Manager
5. **Enable SSL/TLS** for PostgreSQL connections (Caddy handles HTTPS automatically)
6. **Regular backups** of both database and downloaded files

#### 10. Example EC2 Setup

Based on your current setup with Caddy managing multiple services:

```bash
# Your existing containers
docker ps
# meal_score-app (port 5000)
# animal_talk-app (port 5000) 
# stock-kanban-app (port 3000)
# PostgreSQL (port 5432) - can be shared
# Caddy (ports 80, 443)
```

The AI Actuarial app can:
- **Share the PostgreSQL container** (create separate database)
- **Use Caddy for routing** (add to existing Caddyfile)
- **Run alongside existing apps** (different port/subdomain)

Example Caddyfile addition:
```caddyfile
# Add to existing /etc/caddy/Caddyfile
actuarial.aixintelligence.com {
    reverse_proxy ai-actuarial-app:5000
    encode gzip
}

# Or as a subpath
aixintelligence.com {
    # ... existing config ...
    
    @actuarial {
        path /actuarial*
    }
    handle @actuarial {
        reverse_proxy ai-actuarial-app:5000
    }
}
```

### Alternative Deployment Options

#### Option 1: Standalone Server (No Docker)

```bash
# On EC2 instance
cd /home/ec2-user
git clone https://github.com/ferryhe/AI_actuarial_inforsearch.git
cd AI_actuarial_inforsearch

# Install dependencies
pip3 install -r requirements.txt

# Configure database
export DB_TYPE=postgresql
export DB_HOST=localhost
export DB_NAME=ai_actuarial
export DB_USER=ai_user
export DB_PASSWORD=your_password

# Run web interface
python3 -m ai_actuarial web --host 0.0.0.0 --port 5000
```

#### Option 2: Background Worker (Scheduled Updates Only)

If you don't need the web interface, run updates via cron:

```bash
# Crontab entry for weekly updates
0 3 * * 1 cd /home/ec2-user/AI_actuarial_inforsearch && /usr/bin/python3 -m ai_actuarial update >> /var/log/ai-actuarial.log 2>&1
```

## License

MIT License
