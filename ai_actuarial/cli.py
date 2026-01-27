from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

import yaml

from .crawler import Crawler, SiteConfig
from .search import search_all
from .storage import Storage


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
    for s in cfg.get("sites", []):
        sites.append(
            SiteConfig(
                name=s["name"],
                url=s["url"],
                max_pages=s.get("max_pages", cfg["defaults"].get("max_pages", 200)),
                max_depth=s.get("max_depth", cfg["defaults"].get("max_depth", 2)),
                delay_seconds=s.get("delay_seconds", cfg["defaults"].get("delay_seconds", 0.5)),
                keywords=s.get("keywords", cfg["defaults"].get("keywords", [])),
                file_exts=s.get("file_exts", cfg["defaults"].get("file_exts", [])),
                exclude_keywords=s.get("exclude_keywords", []),
                exclude_prefixes=s.get("exclude_prefixes", []),
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
                ),
                source_site=result.source,
            )
            all_new.extend(items)

    storage.write_last_run(cfg["paths"]["last_run_new"], all_new)
    storage.close()

    print(f"New files: {len(all_new)}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    cfg = _load_config(args.config)
    storage = Storage(cfg["paths"]["db"])
    rows = storage.export_files()
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

    return p


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


if __name__ == "__main__":
    raise SystemExit(main())
