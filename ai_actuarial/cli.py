from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .crawler import Crawler, SiteConfig
from .catalog import (
    CATALOG_VERSION,
    CatalogItem,
    build_catalog,
    build_catalog_incremental,
    write_catalog_jsonl,
    write_catalog_md,
)
from .catalog_incremental import run_incremental_catalog
from .search import search_all
from .storage import Storage
from .collectors import CollectionConfig
from .collectors.scheduled import ScheduledCollector
from .collectors.adhoc import AdhocCollector
from .collectors.url import URLCollector
from .collectors.file import FileCollector


def _load_dotenv(path: str) -> None:
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw or raw.startswith("#") or "=" not in raw:
                    continue
                key, value = raw.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        return


def _load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _site_configs(cfg: dict) -> list[SiteConfig]:
    sites = []
    defaults = cfg.get("defaults", {})
    
    # Pre-calculated merged defaults for efficiency
    def_excl_kw = defaults.get("exclude_keywords", [])
    def_excl_pfx = defaults.get("exclude_prefixes", [])

    for s in cfg.get("sites", []):
        # Merge exclusions
        excl_kw = list(set(def_excl_kw + s.get("exclude_keywords", [])))
        excl_pfx = list(set(def_excl_pfx + s.get("exclude_prefixes", [])))

        sites.append(
            SiteConfig(
                name=s["name"],
                url=s["url"],
                max_pages=s.get("max_pages", defaults.get("max_pages", 200)),
                max_depth=s.get("max_depth", defaults.get("max_depth", 2)),
                delay_seconds=s.get("delay_seconds", defaults.get("delay_seconds", 0.5)),
                keywords=s.get("keywords", defaults.get("keywords", [])),
                file_exts=s.get("file_exts", defaults.get("file_exts", [])),
                exclude_keywords=excl_kw,
                exclude_prefixes=excl_pfx,
            )
        )
    return sites


def cmd_update(args: argparse.Namespace) -> int:
    cfg = _load_config(args.config)
    storage = Storage(cfg["paths"]["db"])
    crawler = Crawler(storage, cfg["paths"]["download_dir"], cfg["defaults"]["user_agent"])

    all_new: list[dict] = []
    sites = _site_configs(cfg)
    if args.site:
        key = args.site.lower()
        sites = [s for s in sites if key in s.name.lower() or key in s.url.lower()]
    if args.max_pages is not None:
        for s in sites:
            s.max_pages = args.max_pages
    if args.max_depth is not None:
        for s in sites:
            s.max_depth = args.max_depth
    for site in sites:
        new_items = crawler.crawl_site(site)
        all_new.extend(new_items)

    search_cfg = cfg.get("search", {})
    if not args.no_search and search_cfg.get("enabled", False):
        brave_key = os.getenv("BRAVE_API_KEY")
        serpapi_key = os.getenv("SERPAPI_API_KEY")
        queries = search_cfg.get("queries", [])
        max_results = int(search_cfg.get("max_results", 5))
        languages = search_cfg.get("languages", ["en"])
        country = search_cfg.get("country")
        search_exclude = search_cfg.get("exclude_keywords", [])
        results = search_all(
            queries,
            max_results,
            brave_key,
            serpapi_key,
            cfg["defaults"]["user_agent"],
            languages=languages,
            country=country,
        )
        for result in results:
            items = crawler.scan_page_for_files(
                result.url,
                SiteConfig(
                    name="Web Search",
                    url=result.url,
                    max_pages=1,
                    max_depth=1,
                    delay_seconds=search_cfg.get("delay_seconds", 0.5),
                    keywords=cfg["defaults"].get("keywords", []),
                    file_exts=cfg["defaults"].get("file_exts", []),
                    exclude_keywords=search_exclude,
                ),
                source_site=result.source,
            )
            all_new.extend(items)

    storage.write_last_run(cfg["paths"]["last_run_new"], all_new)
    _write_timestamped_updates(cfg, all_new)
    storage.close()

    print(f"New files: {len(all_new)}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    cfg = _load_config(args.config)
    storage = Storage(cfg["paths"]["db"])
    rows = storage.export_files()
    rows = [r for r in rows if r.get("local_path")]
    storage.close()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.format == "json":
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
    elif args.format == "md":
        _write_markdown(out_path, rows)
    else:
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "url",
                    "sha256",
                    "title",
                    "source_site",
                    "source_page_url",
                    "original_filename",
                    "local_path",
                    "bytes",
                    "content_type",
                    "last_modified",
                    "etag",
                    "published_time",
                    "first_seen",
                    "last_seen",
                    "crawl_time",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
    return 0


def cmd_catalog(args: argparse.Namespace) -> int:
    cfg = _load_config(args.config)
    db_path = cfg["paths"]["db"]
    
    if args.legacy:
        # Legacy mode: full rewrite to JSON
        storage = Storage(db_path)
        items = build_catalog(
            storage,
            site_filter=args.site,
            limit=args.limit,
            offset=args.offset,
            ai_only=args.ai_only,
        )
        storage.close()

        out_md = Path(args.output_md)
        out_json = Path(args.output_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        if args.append and out_json.exists():
            with open(out_json, "r", encoding="utf-8") as f:
                existing = json.load(f)
        else:
            existing = []
        existing.extend([item.__dict__ for item in items])
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        write_catalog_md(out_md, items, append=args.append)
        print(f"[legacy] Catalog items: {len(items)}")
        return 0
    
    if args.legacy_incremental:
        out_jsonl = Path(args.output_jsonl)
        out_md = Path(args.output_md)

        stats = run_incremental_catalog(
            db_path=db_path,
            out_jsonl=out_jsonl,
            out_md=out_md,
            batch=args.batch,
            site_filter=args.site,
            ai_only=args.ai_only,
            catalog_version=args.version,
            max_chars=args.max_chars,
            retry_errors=args.retry_errors,
        )

        print(
            f"Catalog done: scanned={stats['scanned']} processed={stats['processed']} "
            f"written={stats['written']} skipped_ai={stats['skipped_ai']} "
            f"errors={stats['errors']} (missing_files={stats.get('missing_files', 0)})"
        )
        return 0

    # Storage-backed incremental mode (default)
    storage = Storage(db_path)
    items = build_catalog_incremental(
        storage,
        site_filter=args.site,
        limit=args.limit,
        offset=args.offset,
        ai_only=args.ai_only,
        pipeline_version=args.version,
        retry_errors=args.retry_errors,
    )
    storage.close()

    out_jsonl = Path(args.output_jsonl)
    out_md = Path(args.output_md)
    write_catalog_jsonl(out_jsonl, items)
    md_items = [
        CatalogItem(
            source_site=i.get("source_site"),
            title=i.get("title"),
            original_filename=i.get("original_filename"),
            url=i.get("url"),
            local_path=i.get("local_path"),
            keywords=i.get("keywords") or [],
            summary=i.get("summary") or "",
            category=i.get("category") or "",
        )
        for i in items
    ]
    write_catalog_md(out_md, md_items, append=True)
    print(f"[incremental] Catalog items: {len(items)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ai-actuarial")
    p.add_argument(
        "--config",
        default="config/sites.yaml",
        help="Path to config file",
    )
    p.add_argument(
        "--site",
        default=None,
        help="Only crawl sites whose name or URL contains this text",
    )
    p.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Override max pages per site for this run",
    )
    p.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Override max crawl depth per site for this run",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_update = sub.add_parser("update", help="Crawl and download new files")
    p_update.set_defaults(func=cmd_update)
    p_update.add_argument(
        "--no-search",
        action="store_true",
        help="Disable web search for this run",
    )

    p_export = sub.add_parser("export", help="Export file index")
    p_export.add_argument("--format", choices=["json", "csv", "md"], default="csv")
    p_export.add_argument("--output", default="data/files.csv")
    p_export.set_defaults(func=cmd_export)

    p_catalog = sub.add_parser("catalog", help="Generate catalog with keywords and summaries")
    p_catalog.add_argument("--site", default=None, help="Only include sites matching this text")
    p_catalog.add_argument("--ai-only", action="store_true", help="Only keep AI-related items")
    p_catalog.add_argument(
        "--legacy-incremental",
        action="store_true",
        help="Use legacy incremental pipeline (catalog_incremental.py)",
    )
    p_catalog.add_argument("--output-md", default="data/catalog.md", help="Markdown output path")
    # Incremental mode options (default)
    p_catalog.add_argument(
        "--batch", type=int,
        default=int(os.getenv("CATALOG_BATCH", "200")),
        help="Batch size for incremental processing (default: 200)"
    )
    p_catalog.add_argument(
        "--version",
        "--catalog-version",
        dest="version",
        default=CATALOG_VERSION,
        help="Version string for catalog (change to force reprocessing)"
    )
    p_catalog.add_argument(
        "--max-chars", type=int,
        default=int(os.getenv("CATALOG_MAX_CHARS", "20000")),
        help="Max characters to extract per file (default: 20000)"
    )
    p_catalog.add_argument(
        "--output-jsonl", default="data/catalog.jsonl",
        help="JSONL output path for incremental mode"
    )
    p_catalog.add_argument(
        "--retry-errors", action="store_true",
        help="Retry files that previously failed (e.g., Excel, corrupt PDFs)"
    )
    # Legacy mode options
    p_catalog.add_argument(
        "--legacy", action="store_true",
        help="Use legacy mode: full rewrite to JSON instead of incremental JSONL"
    )
    p_catalog.add_argument("--limit", type=int, default=100, help="[legacy] Max files to process")
    p_catalog.add_argument("--offset", type=int, default=0, help="[legacy] Skip the first N files")
    p_catalog.add_argument("--output-json", default="data/catalog.json", help="[legacy] JSON output path")
    p_catalog.add_argument("--append", action="store_true", help="[legacy] Append to existing outputs")
    p_catalog.set_defaults(func=cmd_catalog)

    # Collection commands using new modular structure
    p_collect = sub.add_parser("collect", help="Run specific collection workflow")
    p_collect_sub = p_collect.add_subparsers(dest="collect_type", required=True)
    
    # URL collection
    p_collect_url = p_collect_sub.add_parser("url", help="Collect from specific URLs")
    p_collect_url.add_argument("urls", nargs="+", help="URLs to collect from")
    p_collect_url.add_argument("--name", default="URL Collection", help="Collection name")
    p_collect_url.add_argument("--no-db-check", action="store_true", help="Skip database duplicate check")
    p_collect_url.set_defaults(func=cmd_collect_url)
    
    # File import
    p_collect_file = p_collect_sub.add_parser("file", help="Import files from local filesystem")
    p_collect_file.add_argument("files", nargs="+", help="File paths to import")
    p_collect_file.add_argument("--name", default="File Import", help="Collection name")
    p_collect_file.add_argument("--subdir", default="imported", help="Target subdirectory in data/files")
    p_collect_file.add_argument("--no-db-check", action="store_true", help="Skip database duplicate check")
    p_collect_file.set_defaults(func=cmd_collect_file)
    
    # Web interface
    p_web = sub.add_parser("web", help="Start web interface for collection management")
    p_web.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    p_web.add_argument("--port", type=int, default=5000, help="Port to bind to")
    p_web.add_argument("--debug", action="store_true", help="Enable debug mode")
    p_web.set_defaults(func=cmd_web)

    return p


def cmd_collect_url(args: argparse.Namespace) -> int:
    """Collect from specific URLs."""
    cfg = _load_config(args.config)
    storage = Storage(cfg["paths"]["db"])
    crawler = Crawler(storage, cfg["paths"]["download_dir"], cfg["defaults"]["user_agent"])
    
    collector = URLCollector(storage, crawler)
    
    config = CollectionConfig(
        name=args.name,
        source_type="url",
        check_database=not args.no_db_check,
        keywords=cfg["defaults"].get("keywords", []),
        file_exts=cfg["defaults"].get("file_exts", []),
        metadata={"urls": args.urls},
    )
    
    result = collector.collect(config)
    
    storage.close()
    
    print(f"\nURL Collection Results:")
    print(f"  Found: {result.items_found}")
    print(f"  Downloaded: {result.items_downloaded}")
    print(f"  Skipped: {result.items_skipped}")
    if result.errors:
        print(f"  Errors: {len(result.errors)}")
        for error in result.errors[:5]:  # Show first 5 errors
            print(f"    - {error}")
    
    return 0 if result.success else 1


def cmd_collect_file(args: argparse.Namespace) -> int:
    """Import files from local filesystem."""
    cfg = _load_config(args.config)
    storage = Storage(cfg["paths"]["db"])
    
    collector = FileCollector(storage, cfg["paths"]["download_dir"])
    
    config = CollectionConfig(
        name=args.name,
        source_type="file",
        check_database=not args.no_db_check,
        metadata={
            "file_paths": args.files,
            "target_subdir": args.subdir,
        },
    )
    
    result = collector.collect(config)
    
    storage.close()
    
    print(f"\nFile Import Results:")
    print(f"  Found: {result.items_found}")
    print(f"  Imported: {result.items_downloaded}")
    print(f"  Skipped: {result.items_skipped}")
    if result.errors:
        print(f"  Errors: {len(result.errors)}")
        for error in result.errors[:5]:  # Show first 5 errors
            print(f"    - {error}")
    
    return 0 if result.success else 1


def cmd_web(args: argparse.Namespace) -> int:
    """Start web interface."""
    try:
        from .web.app import run_server
    except ImportError:
        print("Flask is required for the web interface.")
        print("Install it with: pip install flask")
        return 1
    
    print(f"Starting web interface on {args.host}:{args.port}")
    print("Press Ctrl+C to stop")
    
    try:
        run_server(host=args.host, port=args.port, debug=args.debug)
    except KeyboardInterrupt:
        print("\nShutting down...")
    
    return 0


def main() -> int:
    _load_dotenv(".env")
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


def _write_markdown(path: Path, rows: list[dict]) -> None:
    headers = [
        "source_site",
        "published_time",
        "title",
        "original_filename",
        "file_url",
        "source_page_url",
        "local_path",
        "bytes",
        "content_type",
        "last_modified",
        "etag",
        "crawl_time",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("| " + " | ".join(headers) + " |\n")
        f.write("| " + " | ".join(["---"] * len(headers)) + " |\n")
        for row in rows:
            values = [
                row.get("source_site") or "",
                row.get("published_time") or "",
                row.get("title") or "",
                row.get("original_filename") or "",
                row.get("url") or "",
                row.get("source_page_url") or "",
                row.get("local_path") or "",
                str(row.get("bytes") or ""),
                row.get("content_type") or "",
                row.get("last_modified") or "",
                row.get("etag") or "",
                row.get("crawl_time") or "",
            ]
            safe = [v.replace("|", " ") for v in values]
            f.write("| " + " | ".join(safe) + " |\n")


def _write_timestamped_updates(cfg: dict, rows: list[dict]) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    updates_dir = cfg.get("paths", {}).get("updates_dir", "data/updates")
    out_json = Path(updates_dir) / f"update_{ts}.json"
    out_md = Path(updates_dir) / f"update_{ts}.md"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    _write_markdown(out_md, rows)


if __name__ == "__main__":
    raise SystemExit(main())
