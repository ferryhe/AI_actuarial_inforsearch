from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
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
from .search_acquisition import (
    format_acquisition_outcome,
    summarize_acquisition_outcomes,
)
from .shared_runtime import coerce_bool
from .ai_runtime import get_search_runtime_credentials
from .storage import Storage
from .collectors import CollectionConfig
from .collectors.url import URLCollector
from .collectors.file import FileCollector
from .sqlite_schema import (
    SchemaMigrationError,
    apply_schema,
    json_dumps,
    schema_plan,
    schema_status,
)
from .api.services.weekly_updates import (
    WeeklySnapshotNotFoundError,
    WeeklySnapshotValidationError,
    generate_weekly_update_summary,
    get_latest_weekly_update_summary,
    get_weekly_update_summary_files,
    list_weekly_update_summaries,
)

logger = logging.getLogger(__name__)

_PIPELINE_API_TIMEOUT_SECONDS = 30


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
                collect_linked_files=(
                    coerce_bool(s.get("collect_linked_files"), default=True)
                    if "collect_linked_files" in s
                    else None
                ),
                collect_page_content=(
                    coerce_bool(s.get("collect_page_content"), default=False)
                    if "collect_page_content" in s
                    else None
                ),
                acquisition_tools=s.get("acquisition_tools"),
                content_selector=s.get("content_selector"),
                allow_url_patterns=s.get("allow_url_patterns"),
                queries=s.get("queries"),
            )
        )
    return sites


def cmd_update(args: argparse.Namespace) -> int:
    cfg = _load_config(args.config)
    storage = Storage(cfg["paths"]["db"])
    crawler = Crawler(
        storage,
        cfg["paths"]["download_dir"],
        cfg["defaults"]["user_agent"],
        default_delay_seconds=float(cfg["defaults"].get("delay_seconds", 0.5)),
    )
    search_credentials = get_search_runtime_credentials(storage=storage)

    all_new: list[dict] = []
    search_outcomes: list[dict] = []
    search_summary: dict[str, int] | None = None

    def consume_search_result(result, site_config: SiteConfig) -> None:
        report = crawler.scan_page_for_files_with_outcome(
            result.url,
            site_config,
            source_site=result.source,
        )
        all_new.extend(report.items)
        outcome = dict(report.outcome)
        search_outcomes.append(outcome)

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
    search_cfg = cfg.get("search", {})
    run_search = not args.no_search and search_cfg.get("enabled", False)

    for site in sites:
        tools = {
            str(tool).strip().lower()
            for tool in (site.acquisition_tools or [])
            if str(tool).strip()
        }
        if not tools or "crawler" in tools:
            new_items = crawler.crawl_site(site)
            all_new.extend(new_items)

        # Run site-specific search queries immediately after crawling the site
        if run_search and site.queries and (not tools or "search" in tools):
            brave_key = search_credentials.get("brave")
            serpapi_key = search_credentials.get("google")
            serper_key = search_credentials.get("serper")
            tavily_key = search_credentials.get("tavily")
            max_results = int(search_cfg.get("max_results", 5))
            languages = search_cfg.get("languages", ["en"])
            country = search_cfg.get("country")
            search_exclude = list(
                dict.fromkeys(
                    str(keyword).strip().lower()
                    for keyword in [
                        *(site.exclude_keywords or []),
                        *(search_cfg.get("exclude_keywords", []) or []),
                    ]
                    if str(keyword).strip()
                )
            )
            site_results = search_all(
                site.queries,
                max_results,
                brave_key,
                serpapi_key,
                cfg["defaults"]["user_agent"],
                languages=languages,
                country=country,
                serper_key=serper_key,
                tavily_key=tavily_key,
            )
            for result in site_results:
                consume_search_result(
                    result,
                    SiteConfig(
                        name=site.name,
                        url=result.url,
                        max_pages=1,
                        max_depth=1,
                        delay_seconds=search_cfg.get("delay_seconds", 0.5),
                        keywords=site.keywords or cfg["defaults"].get("keywords", []),
                        file_exts=site.file_exts or cfg["defaults"].get("file_exts", []),
                        exclude_keywords=search_exclude,
                        exclude_prefixes=site.exclude_prefixes or [],
                        collect_linked_files=site.collect_linked_files,
                        collect_page_content=site.collect_page_content,
                        allowed_domain=site.url,
                    ),
                )

    if run_search:
        brave_key = search_credentials.get("brave")
        serpapi_key = search_credentials.get("google")
        serper_key = search_credentials.get("serper")
        tavily_key = search_credentials.get("tavily")
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
            serper_key=serper_key,
            tavily_key=tavily_key,
        )
        for result in results:
            consume_search_result(
                result,
                SiteConfig(
                    name="Web Search",
                    url=result.url,
                    max_pages=1,
                    max_depth=1,
                    delay_seconds=search_cfg.get("delay_seconds", 0.5),
                    keywords=cfg["defaults"].get("keywords", []),
                    file_exts=cfg["defaults"].get("file_exts", []),
                    exclude_keywords=search_exclude,
                    exclude_prefixes=cfg["defaults"].get("exclude_prefixes", []),
                ),
            )

    if run_search:
        outcome_count = len(search_outcomes)
        for index, outcome in enumerate(search_outcomes, start=1):
            log_level = logging.WARNING if int(outcome.get("failed") or 0) else logging.INFO
            logger.log(
                log_level,
                format_acquisition_outcome(index, outcome_count, outcome),
            )
        search_summary = summarize_acquisition_outcomes(search_outcomes)
        logger.info(
            "Search acquisition summary: %s",
            json.dumps(
                search_summary,
                ensure_ascii=False,
                sort_keys=True,
            ),
        )

    storage.write_last_run(cfg["paths"]["last_run_new"], all_new)
    _write_timestamped_updates(cfg, all_new)
    storage.close()

    logger.info(f"New files: {len(all_new)}")
    return 1 if search_summary and search_summary["failed"] and not search_summary["downloaded"] else 0


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

    # Re-categorization block: refuse to catalog after a taxonomy change so the
    # CLI cannot silently produce stale category data (same gate as the API task).
    guard_storage = Storage(db_path)
    try:
        if guard_storage.taxonomy_needs_recategory():
            logger.error(
                "categories.yaml taxonomy has changed; run the recategory task before catalog"
            )
            return 1
    finally:
        guard_storage.close()

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
        logger.info(f"[legacy] Catalog items: {len(items)}")
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
    logger.info(f"[incremental] Catalog items: {len(items)}")
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    if args.schema_cmd == "status":
        payload = schema_status(args.db)
    elif args.schema_cmd == "plan":
        payload = schema_plan(args.db)
    elif args.schema_cmd == "apply":
        try:
            payload = apply_schema(args.db)
        except SchemaMigrationError as exc:
            payload = {
                "success": False,
                "error": str(exc),
            }
            if args.json:
                print(json_dumps(payload))
            else:
                print(f"Schema apply failed: {exc}")
            return 2
    else:  # pragma: no cover - argparse enforces a valid subcommand
        raise AssertionError(args.schema_cmd)

    if args.json:
        print(json_dumps(payload))
    else:
        state = payload.get("state", "unknown")
        version = (payload.get("database") or {}).get("user_version")
        print(f"SQLite schema state: {state} (user_version={version})")
    return 0


def _weekly_snapshot_db_path(args: argparse.Namespace) -> str:
    if str(args.db or "").strip():
        return str(args.db).strip()
    config = _load_config(args.config)
    return str((config.get("paths") or {}).get("db") or "data/index.db")


def cmd_weekly_snapshot(args: argparse.Namespace) -> int:
    try:
        db_path = _weekly_snapshot_db_path(args)
        if args.snapshot_cmd == "generate":
            payload = generate_weekly_update_summary(
                db_path=db_path,
                period_start=args.period_start,
                period_end=args.period_end,
                relative_period=args.relative_period,
                max_files=args.preview_limit,
                force=args.force,
            )
        elif args.snapshot_cmd == "latest":
            payload = get_latest_weekly_update_summary(db_path=db_path)
        elif args.snapshot_cmd == "list":
            payload = list_weekly_update_summaries(
                db_path=db_path,
                limit=args.limit,
                offset=args.offset,
            )
        elif args.snapshot_cmd == "files":
            payload = get_weekly_update_summary_files(
                db_path=db_path,
                snapshot_id=args.snapshot_id,
                limit=args.limit,
                offset=args.offset,
            )
        else:  # pragma: no cover - argparse enforces the action
            raise AssertionError(args.snapshot_cmd)
    except (
        WeeklySnapshotNotFoundError,
        WeeklySnapshotValidationError,
        OSError,
        RuntimeError,
        sqlite3.Error,
        ValueError,
    ) as exc:
        _print_cli_payload(
            {
                "success": False,
                "error": (
                    "Weekly snapshot not found"
                    if isinstance(exc, WeeklySnapshotNotFoundError)
                    else str(exc)
                ),
            },
            as_json=args.json,
        )
        return 2
    _print_cli_payload(payload, as_json=args.json)
    return 0


def pipeline_api_request(
    api_url: str,
    action: str,
    *,
    method: str,
    token: str | None,
) -> dict:
    url = f"{api_url.rstrip('/')}/api/pipeline/{action}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method=method)
    try:
        # The API endpoint is supplied by the operator.
        with urllib.request.urlopen(
            request, timeout=_PIPELINE_API_TIMEOUT_SECONDS
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Pipeline API returned HTTP {exc.code}: {detail}") from exc


def cmd_pipeline(args: argparse.Namespace) -> int:
    action = str(args.pipeline_cmd)
    method = "GET" if action in {"status", "config"} else "POST"
    try:
        result = pipeline_api_request(
            args.api_url,
            action,
            method=method,
            token=args.token,
        )
    except (RuntimeError, OSError, json.JSONDecodeError) as exc:
        payload = {"success": False, "error": str(exc)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            print(f"Pipeline command failed: {exc}")
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _api_json_request(
    api_url: str,
    path: str,
    *,
    method: str,
    token: str | None,
    payload: dict | None = None,
    timeout: float = 30,
) -> dict:
    headers = {"Accept": "application/json"}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=max(0.1, float(timeout))) as response:
            decoded = json.loads(response.read().decode("utf-8"))
            if not isinstance(decoded, dict):
                raise RuntimeError("API returned a non-object JSON response")
            return decoded
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API returned HTTP {exc.code}: {detail}") from exc


def _print_cli_payload(payload: dict, *, as_json: bool) -> None:
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=None if as_json else 2,
        )
    )


def _wait_for_api_task(args: argparse.Namespace, job_id: str) -> dict:
    deadline = time.monotonic() + max(0.0, float(args.timeout))
    while True:
        active = _api_json_request(
            args.api_url,
            "/api/tasks/active",
            method="GET",
            token=args.token,
            timeout=args.timeout,
        )
        for task in active.get("tasks") or []:
            if str(task.get("id") or "") == job_id:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"task wait timed out after {args.timeout} seconds")
                time.sleep(0.2)
                break
        else:
            history = _api_json_request(
                args.api_url,
                "/api/tasks/history?limit=200",
                method="GET",
                token=args.token,
                timeout=args.timeout,
            )
            match = next(
                (
                    task
                    for task in history.get("tasks") or []
                    if str(task.get("id") or "") == job_id
                ),
                None,
            )
            if match is not None:
                return dict(match)
            if time.monotonic() >= deadline:
                raise TimeoutError(f"task wait timed out after {args.timeout} seconds")
            time.sleep(0.2)


def _get_api_task(args: argparse.Namespace, job_id: str) -> dict:
    active = _api_json_request(
        args.api_url,
        "/api/tasks/active",
        method="GET",
        token=args.token,
        timeout=args.timeout,
    )
    match = next(
        (
            task
            for task in active.get("tasks") or []
            if str(task.get("id") or "") == job_id
        ),
        None,
    )
    if match is None:
        history = _api_json_request(
            args.api_url,
            "/api/tasks/history?limit=500",
            method="GET",
            token=args.token,
            timeout=args.timeout,
        )
        match = next(
            (
                task
                for task in history.get("tasks") or []
                if str(task.get("id") or "") == job_id
            ),
            None,
        )
    if match is None:
        raise RuntimeError(f"task '{job_id}' was not found")
    return dict(match)


def _task_command_error(args: argparse.Namespace, exc: Exception) -> int:
    _print_cli_payload({"success": False, "error": str(exc)}, as_json=args.json)
    return 2


def cmd_task_status(args: argparse.Namespace) -> int:
    try:
        task = _get_api_task(args, args.job_id)
    except (RuntimeError, OSError, json.JSONDecodeError) as exc:
        return _task_command_error(args, exc)
    _print_cli_payload({"job_id": args.job_id, "task": task}, as_json=args.json)
    return 0


def cmd_task_log(args: argparse.Namespace) -> int:
    path = f"/api/tasks/log/{urllib.parse.quote(args.job_id, safe='')}?tail={args.tail}"
    try:
        result = _api_json_request(
            args.api_url,
            path,
            method="GET",
            token=args.token,
            timeout=args.timeout,
        )
    except (RuntimeError, OSError, json.JSONDecodeError) as exc:
        return _task_command_error(args, exc)
    _print_cli_payload(result, as_json=args.json)
    return 0


def cmd_task_stop(args: argparse.Namespace) -> int:
    path = f"/api/tasks/stop/{urllib.parse.quote(args.job_id, safe='')}"
    try:
        result = _api_json_request(
            args.api_url,
            path,
            method="POST",
            token=args.token,
            timeout=args.timeout,
        )
    except (RuntimeError, OSError, json.JSONDecodeError) as exc:
        return _task_command_error(args, exc)
    _print_cli_payload({"job_id": args.job_id, **result}, as_json=args.json)
    return 0


def cmd_task_run(args: argparse.Namespace) -> int:
    payload: dict = {}
    if args.payload_json:
        try:
            decoded = json.loads(args.payload_json)
        except json.JSONDecodeError as exc:
            _print_cli_payload({"success": False, "error": f"invalid --payload-json: {exc}"}, as_json=args.json)
            return 2
        if not isinstance(decoded, dict):
            _print_cli_payload({"success": False, "error": "--payload-json must be an object"}, as_json=args.json)
            return 2
        payload.update(decoded)
    payload["type"] = args.task_type
    if args.file_url:
        payload["file_urls"] = list(args.file_url)
    if args.chunk_set_id:
        payload["chunk_set_ids"] = list(args.chunk_set_id)
    if args.profile_id:
        payload["profile_id"] = args.profile_id
    if args.embedding_identity_key:
        payload["embedding_identity_key"] = args.embedding_identity_key
    try:
        started = _api_json_request(
            args.api_url,
            "/api/collections/run",
            method="POST",
            token=args.token,
            payload=payload,
            timeout=args.timeout,
        )
        job_id = str(started.get("job_id") or "")
        if not job_id:
            raise RuntimeError("task launch did not return a real job_id")
        if not args.wait:
            _print_cli_payload(started, as_json=args.json)
            return 0
        task = _wait_for_api_task(args, job_id)
        result = {**started, "task": task}
        _print_cli_payload(result, as_json=args.json)
        return 0 if str(task.get("status") or "") in {"completed", "success", "succeeded"} else 1
    except TimeoutError as exc:
        _print_cli_payload({"success": False, "error": str(exc)}, as_json=args.json)
        return 124
    except (RuntimeError, OSError, json.JSONDecodeError) as exc:
        _print_cli_payload({"success": False, "error": str(exc)}, as_json=args.json)
        return 2


def cmd_embedding_coverage(args: argparse.Namespace) -> int:
    params: list[tuple[str, str]] = []
    params.extend(("chunk_set_id", value) for value in args.chunk_set_id)
    params.extend(("file_url", value) for value in args.file_url)
    if args.profile_id:
        params.append(("profile_id", args.profile_id))
    if args.embedding_identity_key:
        params.append(("embedding_identity_key", args.embedding_identity_key))
    path = "/api/embeddings/coverage"
    if params:
        path += "?" + urllib.parse.urlencode(params)
    try:
        result = _api_json_request(
            args.api_url,
            path,
            method="GET",
            token=args.token,
            timeout=args.timeout,
        )
    except (RuntimeError, OSError, json.JSONDecodeError) as exc:
        _print_cli_payload({"success": False, "error": str(exc)}, as_json=args.json)
        return 2
    _print_cli_payload(result, as_json=args.json)
    return 0


def cmd_kb_binding(args: argparse.Namespace) -> int:
    path = (
        "/api/rag/knowledge-bases/"
        f"{urllib.parse.quote(args.kb_id, safe='')}/bindings"
    )
    payload = None
    method = "GET"
    if args.binding_cmd == "set":
        try:
            payload = json.loads(args.payload_json)
        except json.JSONDecodeError as exc:
            _print_cli_payload(
                {"success": False, "error": f"invalid --payload-json: {exc}"},
                as_json=args.json,
            )
            return 2
        if not isinstance(payload, dict):
            _print_cli_payload(
                {"success": False, "error": "--payload-json must be an object"},
                as_json=args.json,
            )
            return 2
        method = "POST"
    try:
        result = _api_json_request(
            args.api_url,
            path,
            method=method,
            token=args.token,
            payload=payload,
            timeout=args.timeout,
        )
    except (RuntimeError, OSError, json.JSONDecodeError) as exc:
        _print_cli_payload(
            {"success": False, "error": str(exc)},
            as_json=args.json,
        )
        return 2
    _print_cli_payload(result, as_json=args.json)
    return 0


def cmd_kb_ready_publish(args: argparse.Namespace) -> int:
    path = (
        "/api/rag/knowledge-bases/"
        f"{urllib.parse.quote(args.kb_id, safe='')}/agentic-ready-manifest/publish"
    )
    payload = {
        "profile": args.profile,
        "publication_id": args.publication_id,
        "expected_active_publication_id": args.expected_active_publication_id,
    }
    try:
        result = _api_json_request(
            args.api_url,
            path,
            method="POST",
            token=args.token,
            payload=payload,
            timeout=args.timeout,
        )
    except (RuntimeError, OSError, json.JSONDecodeError) as exc:
        _print_cli_payload({"success": False, "error": str(exc)}, as_json=args.json)
        return 2
    _print_cli_payload(result, as_json=args.json)
    return 0


def cmd_kb_ready_get(args: argparse.Namespace) -> int:
    path = (
        "/api/rag/knowledge-bases/"
        f"{urllib.parse.quote(args.kb_id, safe='')}/agentic-ready-manifest?"
        + urllib.parse.urlencode({"profile": args.profile})
    )
    try:
        result = _api_json_request(
            args.api_url,
            path,
            method="GET",
            token=args.token,
            timeout=args.timeout,
        )
    except (RuntimeError, OSError, json.JSONDecodeError) as exc:
        _print_cli_payload({"success": False, "error": str(exc)}, as_json=args.json)
        return 2
    _print_cli_payload(result, as_json=args.json)
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

    p_schema = sub.add_parser("schema", help="Inspect or apply SQLite schema migrations")
    p_schema_sub = p_schema.add_subparsers(dest="schema_cmd", required=True)
    for action in ("status", "plan", "apply"):
        p_schema_action = p_schema_sub.add_parser(action, help=f"SQLite schema {action}")
        p_schema_action.add_argument("--db", required=True, help="SQLite database path")
        p_schema_action.add_argument(
            "--json",
            action="store_true",
            help="Emit the stable machine-readable JSON contract",
        )
        p_schema_action.set_defaults(func=cmd_schema)

    p_weekly = sub.add_parser("weekly", help="Operate on weekly resources")
    p_weekly_sub = p_weekly.add_subparsers(dest="weekly_cmd", required=True)
    p_weekly_snapshot = p_weekly_sub.add_parser(
        "snapshot",
        help="Generate and read weekly file snapshots",
    )
    p_weekly_snapshot_sub = p_weekly_snapshot.add_subparsers(
        dest="snapshot_cmd",
        required=True,
    )
    p_weekly_generate = p_weekly_snapshot_sub.add_parser(
        "generate",
        help="Generate or replay one weekly snapshot",
    )
    p_weekly_generate.add_argument("--period-start")
    p_weekly_generate.add_argument("--period-end")
    p_weekly_generate.add_argument("--relative-period")
    p_weekly_generate.add_argument(
        "--preview-limit",
        type=int,
        default=500,
        help="Maximum generated preview rows (max 500)",
    )
    p_weekly_generate.add_argument(
        "--force",
        action="store_true",
        help="Explicitly rebuild an already published period",
    )
    p_weekly_latest = p_weekly_snapshot_sub.add_parser(
        "latest",
        help="Read the latest completed published snapshot",
    )
    p_weekly_list = p_weekly_snapshot_sub.add_parser(
        "list",
        help="List published snapshot summaries",
    )
    p_weekly_list.add_argument("--limit", type=int, default=20)
    p_weekly_list.add_argument("--offset", type=int, default=0)
    p_weekly_files = p_weekly_snapshot_sub.add_parser(
        "files",
        help="Page through one snapshot's files",
    )
    p_weekly_files.add_argument("snapshot_id", help="Weekly snapshot ID")
    p_weekly_files.add_argument("--limit", type=int, default=100)
    p_weekly_files.add_argument("--offset", type=int, default=0)
    for p_weekly_action in (
        p_weekly_generate,
        p_weekly_latest,
        p_weekly_list,
        p_weekly_files,
    ):
        p_weekly_action.add_argument(
            "--db",
            default=None,
            help="SQLite database path (defaults to config paths.db)",
        )
        p_weekly_action.add_argument(
            "--json",
            action="store_true",
            help="Emit the stable machine-readable JSON contract",
        )
        p_weekly_action.set_defaults(func=cmd_weekly_snapshot)

    p_pipeline = sub.add_parser("pipeline", help="Control the fixed five-step pipeline baton")
    p_pipeline_sub = p_pipeline.add_subparsers(dest="pipeline_cmd", required=True)
    for action in ("status", "start", "tick", "config"):
        action_help = "Show saved pipeline baton configuration" if action == "config" else f"Pipeline baton {action}"
        p_pipeline_action = p_pipeline_sub.add_parser(action, help=action_help)
        p_pipeline_action.add_argument(
            "--api-url",
            default=os.getenv("AI_ACTUARIAL_API_URL", "http://127.0.0.1:5000"),
            help="FastAPI base URL",
        )
        p_pipeline_action.add_argument(
            "--token",
            default=os.getenv("AI_ACTUARIAL_API_TOKEN"),
            help="Bearer token for the FastAPI gateway",
        )
        p_pipeline_action.add_argument(
            "--json",
            action="store_true",
            help="Emit the stable machine-readable JSON response",
        )
        p_pipeline_action.set_defaults(func=cmd_pipeline)

    p_task = sub.add_parser("task", help="Run a task through the FastAPI gateway")
    p_task_sub = p_task.add_subparsers(dest="task_cmd", required=True)
    p_task_run = p_task_sub.add_parser("run", help="Launch a generic background task")
    p_task_run.add_argument("--type", dest="task_type", required=True, help="Task type")
    p_task_run.add_argument("--file-url", action="append", default=[], help="Stable file URL selector (repeatable)")
    p_task_run.add_argument("--chunk-set-id", action="append", default=[], help="Stable chunk set selector (repeatable)")
    p_task_run.add_argument("--profile-id", default=None, help="Chunk profile selector")
    p_task_run.add_argument("--embedding-identity-key", default=None, help="Server-allowed embedding identity")
    p_task_run.add_argument("--payload-json", default=None, help="Additional task payload as a JSON object")
    p_task_run.add_argument("--api-url", default=os.getenv("AI_ACTUARIAL_API_URL", "http://127.0.0.1:5000"), help="FastAPI base URL")
    p_task_run.add_argument("--token", default=os.getenv("AI_ACTUARIAL_API_TOKEN"), help="Bearer token")
    p_task_run.add_argument("--wait", action="store_true", help="Wait for terminal task status")
    p_task_run.add_argument("--timeout", type=float, default=300, help="Request/wait timeout in seconds")
    p_task_run.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    p_task_run.set_defaults(func=cmd_task_run)
    for action, handler, action_help in (
        ("status", cmd_task_status, "Show one task status"),
        ("log", cmd_task_log, "Read one task log"),
        ("stop", cmd_task_stop, "Request one task to stop"),
    ):
        p_task_action = p_task_sub.add_parser(action, help=action_help)
        p_task_action.add_argument("job_id", help="Task job ID")
        p_task_action.add_argument(
            "--api-url",
            default=os.getenv("AI_ACTUARIAL_API_URL", "http://127.0.0.1:5000"),
            help="FastAPI base URL",
        )
        p_task_action.add_argument(
            "--token",
            default=os.getenv("AI_ACTUARIAL_API_TOKEN"),
            help="Bearer token",
        )
        p_task_action.add_argument(
            "--timeout",
            type=float,
            default=30,
            help="Request timeout in seconds",
        )
        p_task_action.add_argument(
            "--json",
            action="store_true",
            help="Emit machine-readable JSON",
        )
        if action == "log":
            p_task_action.add_argument(
                "--tail",
                type=int,
                default=500,
                help="Maximum log lines",
            )
        p_task_action.set_defaults(func=handler)

    p_embedding = sub.add_parser("embedding", help="Inspect persisted embedding coverage")
    p_embedding_sub = p_embedding.add_subparsers(dest="embedding_cmd", required=True)
    p_embedding_coverage = p_embedding_sub.add_parser("coverage", help="Query embedding coverage")
    p_embedding_coverage.add_argument("--chunk-set-id", action="append", default=[], help="Stable chunk set selector (repeatable)")
    p_embedding_coverage.add_argument("--file-url", action="append", default=[], help="Stable file URL selector (repeatable)")
    p_embedding_coverage.add_argument("--profile-id", default=None, help="Chunk profile selector")
    p_embedding_coverage.add_argument("--embedding-identity-key", default=None, help="Server-allowed embedding identity")
    p_embedding_coverage.add_argument("--api-url", default=os.getenv("AI_ACTUARIAL_API_URL", "http://127.0.0.1:5000"), help="FastAPI base URL")
    p_embedding_coverage.add_argument("--token", default=os.getenv("AI_ACTUARIAL_API_TOKEN"), help="Bearer token")
    p_embedding_coverage.add_argument("--timeout", type=float, default=30, help="Request timeout in seconds")
    p_embedding_coverage.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    p_embedding_coverage.set_defaults(func=cmd_embedding_coverage)

    p_kb = sub.add_parser("kb", help="Operate on knowledge-base resources")
    p_kb_sub = p_kb.add_subparsers(dest="kb_cmd", required=True)
    p_kb_binding = p_kb_sub.add_parser(
        "binding",
        help="Read or reconcile the exact KB binding resource",
    )
    p_kb_binding_sub = p_kb_binding.add_subparsers(
        dest="binding_cmd",
        required=True,
    )
    for action in ("get", "set"):
        p_kb_binding_action = p_kb_binding_sub.add_parser(
            action,
            help=(
                "Read the exact binding contract"
                if action == "get"
                else "Reconcile bindings and return the exact binding contract"
            ),
        )
        p_kb_binding_action.add_argument("kb_id", help="Knowledge-base ID")
        if action == "set":
            p_kb_binding_action.add_argument(
                "--payload-json",
                required=True,
                help="Binding POST body as a JSON object",
            )
        p_kb_binding_action.add_argument(
            "--api-url",
            default=os.getenv("AI_ACTUARIAL_API_URL", "http://127.0.0.1:5000"),
            help="FastAPI base URL",
        )
        p_kb_binding_action.add_argument(
            "--token",
            default=os.getenv("AI_ACTUARIAL_API_TOKEN"),
            help="Bearer token",
        )
        p_kb_binding_action.add_argument(
            "--timeout",
            type=float,
            default=30,
            help="Request timeout in seconds",
        )
        p_kb_binding_action.add_argument(
            "--json",
            action="store_true",
            help="Emit machine-readable JSON",
        )
        p_kb_binding_action.set_defaults(func=cmd_kb_binding)

    p_kb_ready = p_kb_sub.add_parser("ready", help="Operate on Ready Data publications")
    p_kb_ready_sub = p_kb_ready.add_subparsers(dest="ready_cmd", required=True)
    p_kb_ready_get = p_kb_ready_sub.add_parser(
        "get",
        help="Read Ready Data status and discover a validated candidate",
    )
    p_kb_ready_get.add_argument("kb_id", help="Knowledge-base ID")
    p_kb_ready_get.add_argument("--profile", required=True, help="Ready Data profile")
    p_kb_ready_get.add_argument(
        "--api-url",
        default=os.getenv("AI_ACTUARIAL_API_URL", "http://127.0.0.1:5000"),
        help="FastAPI base URL",
    )
    p_kb_ready_get.add_argument(
        "--token",
        default=os.getenv("AI_ACTUARIAL_API_TOKEN"),
        help="Bearer token",
    )
    p_kb_ready_get.add_argument("--timeout", type=float, default=30)
    p_kb_ready_get.add_argument("--json", action="store_true")
    p_kb_ready_get.set_defaults(func=cmd_kb_ready_get)
    p_kb_ready_publish = p_kb_ready_sub.add_parser(
        "publish",
        help="Publish one validated Ready Data candidate",
    )
    p_kb_ready_publish.add_argument("kb_id", help="Knowledge-base ID")
    p_kb_ready_publish.add_argument("--profile", required=True, help="Ready Data profile")
    p_kb_ready_publish.add_argument(
        "--publication-id",
        required=True,
        help="Validated Ready Data publication ID",
    )
    p_kb_ready_publish.add_argument(
        "--expected-active-publication-id",
        default=None,
        help="Expected current active publication ID; omit when none is active",
    )
    p_kb_ready_publish.add_argument(
        "--api-url",
        default=os.getenv("AI_ACTUARIAL_API_URL", "http://127.0.0.1:5000"),
        help="FastAPI base URL",
    )
    p_kb_ready_publish.add_argument(
        "--token",
        default=os.getenv("AI_ACTUARIAL_API_TOKEN"),
        help="Bearer token",
    )
    p_kb_ready_publish.add_argument("--timeout", type=float, default=30)
    p_kb_ready_publish.add_argument("--json", action="store_true")
    p_kb_ready_publish.set_defaults(func=cmd_kb_ready_publish)

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
    
    p_api = sub.add_parser("api", help="Start FastAPI gateway for the React frontend")
    p_api.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    p_api.add_argument("--port", type=int, default=5000, help="Port to bind to")
    p_api.add_argument("--reload", action="store_true", help="Enable auto reload")
    p_api.set_defaults(func=cmd_api)

    return p


def cmd_collect_url(args: argparse.Namespace) -> int:
    """Collect from specific URLs."""
    cfg = _load_config(args.config)
    storage = Storage(cfg["paths"]["db"])
    crawler = Crawler(
        storage,
        cfg["paths"]["download_dir"],
        cfg["defaults"]["user_agent"],
        default_delay_seconds=float(cfg["defaults"].get("delay_seconds", 0.5)),
    )
    
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
    
    print("\nURL Collection Results:")
    logger.info(f"  Found: {result.items_found}")
    logger.info(f"  Downloaded: {result.items_downloaded}")
    logger.info(f"  Skipped: {result.items_skipped}")
    if result.errors:
        logger.warning(f"  Errors: {len(result.errors)}")
        for error in result.errors[:5]:  # Show first 5 errors
            logger.warning(f"    - {error}")
    
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
    
    print("\nFile Import Results:")
    logger.info(f"  Found: {result.items_found}")
    logger.info(f"  Imported: {result.items_downloaded}")
    logger.info(f"  Skipped: {result.items_skipped}")
    if result.errors:
        logger.warning(f"  Errors: {len(result.errors)}")
        for error in result.errors[:5]:  # Show first 5 errors
            logger.warning(f"    - {error}")
    
    return 0 if result.success else 1


def cmd_api(args: argparse.Namespace) -> int:
    """Start FastAPI gateway for the React frontend."""
    try:
        from .api.app import run_server
    except ImportError:
        print("FastAPI is required for the API gateway.")
        print("Install it with: pip install fastapi uvicorn")
        return 1

    print(f"Starting FastAPI gateway on {args.host}:{args.port}")
    logger.info("Press Ctrl+C to stop")

    try:
        run_server(host=args.host, port=args.port, reload=args.reload)
    except KeyboardInterrupt:
        print("\nShutting down...")

    return 0


def main() -> int:
    _load_dotenv(".env")
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(message)s",
    )
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
