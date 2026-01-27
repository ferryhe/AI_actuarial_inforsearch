# AI Actuarial Info Search

This tool crawls actuarial organization sites, finds AI-related pages and files,
downloads files, and maintains a local file index. It is designed for scheduled
runs (manual or cron/Task Scheduler).

## Quick start

1) Edit `config/sites.yaml` to adjust sites, limits, and keywords.
2) Run:
```bash
python -m ai_actuarial update
```

## Output

- Downloads: `data/files/`
- Index database: `data/index.db`
- Last run new files: `data/last_run_new.json`
- Export: `python -m ai_actuarial export --format md --output data/files.md`
- Timestamped updates: `data/updates/update_YYYYMMDD_HHMMSSZ.(json|md)`

Downloaded files keep their original filenames. If a name conflicts, a suffix
like `_1`, `_2` is appended.

## Web search

Set API keys via environment variables or `.env`:

`.env` sample:

```
BRAVE_API_KEY=your_brave_key
SERPAPI_API_KEY=your_serpapi_key
```

Search runs via Brave first, then SerpAPI if Brave returns no results or fails.

## Metadata extraction

The crawler uses `trafilatura` (if installed) to improve title/date extraction, and
falls back to basic HTML meta parsing if needed.

## Search sorting

SerpAPI uses the Google News engine with `tbs=sbd:1` to return results sorted by
date. Brave remains standard web search without time sorting.

## Scheduling

- Windows Task Scheduler: run `python -m ai_actuarial update` daily/weekly.
- Linux cron: `0 3 * * 1 python -m ai_actuarial update`

## Notes

Some sites may block aggressive crawling. Tune `max_pages`, `delay_seconds`,
and `user_agent` in `config/sites.yaml`.

## Keywords

Keyword filtering is configured in `config/sites.yaml`:
- Global defaults: `defaults.keywords`
- Per-site overrides: each entry under `sites` can set `keywords`
- Per-site exclusions: each entry under `sites` can set `exclude_keywords`
 - Per-site filename prefixes: each entry under `sites` can set `exclude_prefixes`

The crawler uses these keywords to keep results AI-related and to decide which
pages to follow. Exclusion keywords are applied to URLs to skip
unwanted content (e.g., SOA exam materials).

## Stable Runbook (Scheduled + Manual)

### Scheduled run (recommended weekly)

1) Ensure `.env` contains your API keys (optional for search):
```
BRAVE_API_KEY=your_brave_key
SERPAPI_API_KEY=your_serpapi_key
```
2) Run the crawler:
```
python -m ai_actuarial update
```
3) Export the review list:
```
python -m ai_actuarial export --format md --output data/files.md
```
4) (Optional) Verify consistency:
   - DB count should match `files.md` rows
   - No missing files under `data/files/`

### Manual focused run (ad-hoc)

Use this when you want to re-crawl a specific site or topic page.

1) Target a site by name or URL fragment:
```
python -m ai_actuarial --site "SOA AI" update --no-search
```
2) Limit scope for faster checks:
```
python -m ai_actuarial --site "SOA AI Bulletin" --max-pages 10 --max-depth 1 update --no-search
```
3) Export for review:
```
python -m ai_actuarial export --format md --output data/files.md
```
