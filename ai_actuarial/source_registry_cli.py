"""Explicit source-registry maintenance; dry-run is the default for every mutation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json

from .source_registry import (
    correct_sources,
    export_registry,
    install_registry,
    registry_identity,
    resolve_source,
)


def inventory(connection: Any, *, hub: bool) -> dict[str, Any]:
    """Raw Hub observations and visible app articles have separate count units."""
    with connection.cursor() as cursor:
        if hub:
            cursor.execute(
                "SELECT v.url_value_json, v.raw_sha256, r.source_metadata_json FROM source_record_map r LEFT JOIN content_versions v USING(content_version_id) ORDER BY r.source_snapshot_id, r.legacy_pk_json"
            )
            rows = [
                (
                    json.loads(row[0]) if row[0] else "",
                    str(row[1] or "").strip(),
                    json.loads(row[2]).get("source_site"),
                    None,
                    None,
                )
                for row in cursor.fetchall()
            ]
        else:
            cursor.execute(
                "SELECT url, sha256, source_site, source_key, (local_path IS NOT NULL AND local_path <> '' AND deleted_at IS NULL) FROM files ORDER BY id"
            )
            rows = cursor.fetchall()
        groups: dict[str, dict[str, Any]] = {}
        for url, digest, raw, saved_key, visible in rows:
            key = resolve_source(connection, url=url or "", raw_source=raw, raw_sha256=digest)
            identity = json.dumps(raw, ensure_ascii=False)
            group = groups.setdefault(
                identity,
                {
                    "raw_source_site": raw,
                    "observations": 0,
                    "visible_articles": 0,
                    "hidden_or_deleted_articles": 0,
                    "canonical_keys": {},
                    "representatives": [],
                },
            )
            group["observations"] += 1
            if visible is not None:
                group["visible_articles" if visible else "hidden_or_deleted_articles"] += 1
            group["canonical_keys"][key] = group["canonical_keys"].get(key, 0) + 1
            if len(group["representatives"]) < 3:
                group["representatives"].append(
                    {
                        "url": url,
                        "raw_sha256": digest,
                        "source_key": key,
                        "cached_source_key": saved_key,
                    }
                )
            group["disposition"] = "pending" if "pending" in group["canonical_keys"] else "mapped"
        cursor.execute("SELECT CURRENT_TIMESTAMP")
        observed_at = cursor.fetchone()[0].isoformat()
    return {
        "read_only": True,
        "observed_at": observed_at,
        "count_unit": "raw_hub_observations" if hub else "files",
        "registry": {
            key: value
            for key, value in export_registry(connection).items()
            if key.startswith("registry_")
        },
        "raw_sources": list(groups.values()),
    }


def sync_targets(connection: Any, config: dict[str, Any], *, apply: bool) -> dict[str, Any]:
    from .local_collection_runtime import _invoke_target_worker

    registry = export_registry(connection)
    receipts = []
    failures = []
    for target in ("china", "overseas"):
        try:
            receipt = _invoke_target_worker(
                config,
                target,
                {
                    "operation": "sync_source_registry",
                    "target": target,
                    "registry": registry,
                    "apply": apply,
                },
            )
            if (
                any(
                    receipt.get(key) != registry[key]
                    for key in ("registry_version", "registry_sha256")
                )
                or receipt.get("target") != target
                or receipt.get("status")
                not in ({"applied", "unchanged"} if apply else {"dry_run", "unchanged"})
            ):
                raise ValueError(
                    "target did not acknowledge the exact source registry revision/hash"
                )
        except (ValueError, OSError, RuntimeError) as exc:
            failures.append({"target": target, "error": str(exc), "status": "pending"})
            continue
        receipts.append(receipt)
        if apply:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO source_registry_receipts(receipt_id,receipt_json) VALUES (%s,%s) ON CONFLICT(receipt_id) DO NOTHING",
                    (receipt["receipt_id"], Json(receipt)),
                )
            connection.commit()
    current = registry_identity(connection)
    requested = {key: registry[key] for key in ("registry_version", "registry_sha256")}
    status = "partial" if receipts else "failed"
    if not failures:
        status = "synchronized" if apply else "dry_run"
    if current != requested:
        status = "hub_advanced"
    return {
        **requested,
        "requested_registry": requested,
        "current_hub_registry": current,
        "status": status,
        "targets": receipts,
        "failures": failures,
        "apply": apply,
    }


def plan_corrections(connection: Any, *, hub: bool) -> dict[str, Any]:
    """Generate exact row bindings from the published dictionary without writing."""
    registry = export_registry(connection)
    with connection.cursor() as cursor:
        if hub:
            cursor.execute(
                "SELECT v.url_value_json,v.raw_sha256,r.source_metadata_json,p.source_key "
                "FROM content_versions v JOIN source_record_map r USING(content_version_id) "
                "LEFT JOIN source_projection p ON p.url=(v.url_value_json::jsonb #>> '{}') "
                "AND p.raw_sha256=v.raw_sha256 WHERE r.source_table='files' "
                "ORDER BY v.content_version_id,r.source_snapshot_id"
            )
            rows = [
                (json.loads(row[0]), row[1], json.loads(row[2]).get("source_site"), row[3])
                for row in cursor.fetchall()
            ]
        else:
            cursor.execute("SELECT url,sha256,source_site,source_key FROM files ORDER BY id")
            rows = cursor.fetchall()
    cache_differences = []
    unresolved = []
    seen = set()
    for url, digest, raw, old_key in rows:
        if not isinstance(url, str) or not isinstance(digest, str) or len(digest.strip()) != 64:
            unresolved.append({"url": url, "reason": "missing exact URL/raw SHA binding"})
            continue
        identity = (url, digest.strip())
        if identity in seen:
            continue
        seen.add(identity)
        new_key = resolve_source(connection, url=url, raw_source=raw, raw_sha256=digest.strip())
        if new_key == "pending":
            unresolved.append(
                {
                    "url": url,
                    "raw_sha256": digest.strip(),
                    "raw_source_site": raw,
                    "reason": "no verified original publication site/article evidence",
                }
            )
        if old_key == new_key:
            continue
        cache_differences.append(
            {
                "url": url,
                "raw_sha256": digest.strip(),
                "raw_source_site": raw,
                "cached_source_key": old_key,
                "source_key": new_key,
                "basis": "current_dictionary_and_exact_overlay",
            }
        )
    return {
        "registry_version": registry["registry_version"],
        "registry_sha256": registry["registry_sha256"],
        "hub": hub,
        "records": [],
        "cache_differences": cache_differences,
        "unresolved": unresolved,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("publish", "export", "inventory", "plan", "correct", "rollback", "sync")
    )
    parser.add_argument(
        "--hub",
        action="store_true",
        help="Use Hub authority/overlay; otherwise operate on an app replica",
    )
    parser.add_argument("--schema", help="Existing schema name; no schema is created")
    parser.add_argument("--manifest", type=Path, help="Reviewed registry or exact correction JSON")
    parser.add_argument("--receipt", help="Original apply receipt ID for rollback")
    parser.add_argument(
        "--request-id",
        help="Reviewed correction request ID; reuse only with identical request body",
    )
    parser.add_argument(
        "--config", type=Path, help="Existing local collection SSH/target config for sync"
    )
    parser.add_argument("--apply", action="store_true", help="Commit changes; default is dry-run")
    parser.add_argument("--json", action="store_true", help="Output JSON (also the default)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    connection = None
    try:
        url = os.environ.get("CONTENT_HUB_DATABASE_URL" if args.hub else "DATABASE_URL")
        if not url:
            raise ValueError("configure the existing database environment variable")
        if args.command in {"publish", "sync"} and not args.hub:
            raise ValueError("publish and sync must use the Hub authority")
        connection = psycopg2.connect(url)
        with connection.cursor() as cursor:
            schema = args.schema or ("content_hub" if args.hub else None)
            if schema:
                cursor.execute(
                    sql.SQL("SET search_path TO {}, pg_catalog").format(sql.Identifier(schema))
                )
            if not args.apply:
                cursor.execute("SET TRANSACTION READ ONLY")
        if args.command == "publish":
            if not args.manifest:
                raise ValueError("publish requires --manifest")
            result = install_registry(
                connection,
                json.loads(args.manifest.read_text(encoding="utf-8")),
                target="hub",
                apply=args.apply,
            )
        elif args.command == "export":
            result = export_registry(connection)
        elif args.command == "inventory":
            result = inventory(connection, hub=args.hub)
        elif args.command == "plan":
            result = plan_corrections(connection, hub=args.hub)
        elif args.command == "sync":
            from .local_collection_runtime import _load_config

            if not args.config:
                raise ValueError("sync requires the existing --config")
            result = sync_targets(connection, _load_config(args.config), apply=args.apply)
        else:
            if args.command == "rollback" and not args.receipt:
                raise ValueError("rollback requires --receipt")
            if args.command == "correct" and not args.manifest:
                raise ValueError("correct requires --manifest")
            manifest = (
                json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest else {}
            )
            if not isinstance(manifest, dict):
                raise ValueError("correction manifest must be an object")
            current = export_registry(connection)
            if any(
                key in manifest and manifest[key] != current[key]
                for key in ("registry_version", "registry_sha256")
            ):
                raise ValueError("correction plan registry revision/hash is no longer current")
            if "hub" in manifest and manifest["hub"] != args.hub:
                raise ValueError("correction plan belongs to another database mode")
            if args.command == "correct" and args.apply:
                if not manifest.get("request_id") or not isinstance(
                    manifest.get("request_body"), dict
                ):
                    raise ValueError(
                        "apply requires saved dry-run JSON; preview the original records first"
                    )
                if args.request_id is not None and args.request_id != manifest["request_id"]:
                    raise ValueError(
                        "apply cannot change the saved dry-run request_id; rerun dry-run"
                    )
            records = manifest.get("request_body", manifest).get("records", [])
            result = correct_sources(
                connection,
                records,
                hub=args.hub,
                apply=args.apply,
                rollback=args.receipt if args.command == "rollback" else None,
                request_id=(
                    (args.request_id or manifest.get("request_id"))
                    if args.apply or args.command == "rollback"
                    else args.request_id
                ),
                reconfirm_same_key=manifest.get("request_body", {}).get("reconfirm_same_key"),
            )
        if args.apply:
            connection.commit()
        else:
            connection.rollback()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return (
            2
            if (
                result.get("status") in {"hub_advanced", "partial", "failed"}
                or any(row.get("status") == "conflict" for row in result.get("records", []))
            )
            else 0
        )
    except (ValueError, OSError, RuntimeError, psycopg2.Error) as exc:
        if connection:
            connection.rollback()
        # Driver connection errors may include login material; never echo them.
        detail = "database operation failed" if isinstance(exc, psycopg2.Error) else str(exc)
        print(json.dumps({"error": detail}, ensure_ascii=False))
        return 2
    finally:
        if connection:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
