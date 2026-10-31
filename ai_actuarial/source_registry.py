"""Exact publisher identities, versioned PG replicas and guarded derived corrections.

Raw collection labels and immutable Hub observations are never rewritten here.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any
from urllib.parse import urlsplit

from psycopg2.extras import Json

PENDING_KEY = "pending"
_KEY = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def normalize_alias(value: str) -> str:
    """v1: trim and lowercase only; CAS and CASA remain distinct."""
    return value.strip().lower()


def registry_digest(value: dict[str, Any]) -> str:
    content = {key: value[key] for key in ("sources", "aliases")}
    return hashlib.sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_registry(value: dict[str, Any]) -> dict[str, Any]:
    """Reject incomplete or conflicting dictionaries before touching a replica."""
    if not isinstance(value, dict):
        raise ValueError("source registry must be an object")
    if type(value.get("registry_version")) is not int or value["registry_version"] < 1:
        raise ValueError("registry_version must be a positive integer")
    sources = value.get("sources")
    aliases = value.get("aliases")
    if not isinstance(sources, list) or not isinstance(aliases, list):
        raise ValueError("registry sources and aliases must be arrays")
    keys: set[str] = set()
    for row in sources:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("source_key"), str)
            or not _KEY.fullmatch(row["source_key"])
        ):
            raise ValueError("invalid canonical source key")
        key = row["source_key"]
        if key in keys or row.get("status") not in {"active", "retired"}:
            raise ValueError("duplicate source or invalid status")
        keys.add(key)
        if any(
            not isinstance(row.get(name), str) or not row[name].strip()
            for name in ("name_zh", "name_en")
        ):
            raise ValueError("canonical sources require both display names")
        if not row.get("evidence"):
            raise ValueError("canonical source requires evidence")
    if PENDING_KEY not in keys:
        raise ValueError("registry requires the pending identity")
    verified: set[tuple[str, str]] = set()
    for row in aliases:
        if not isinstance(row, dict):
            raise ValueError("alias must be an object")
        norm = row.get("alias_norm")
        kind = row.get("alias_kind")
        status = row.get("resolution_status")
        if not isinstance(norm, str) or not norm or norm != normalize_alias(norm):
            raise ValueError("alias must use v1 exact normalization")
        if kind not in {"name", "hostname"} or status not in {"verified", "ambiguous"}:
            raise ValueError("invalid alias kind/status")
        if row.get("source_key") is not None and row["source_key"] not in keys:
            raise ValueError("alias refers to unknown canonical source")
        if not row.get("evidence"):
            raise ValueError("alias requires evidence")
        if norm == "task" and status == "verified":
            raise ValueError("task is ambiguous; use exact article or official URL evidence")
        if status == "verified":
            identity = (kind, norm)
            if row.get("source_key") is None or identity in verified:
                raise ValueError("conflicting verified alias")
            verified.add(identity)
    result = {
        "registry_version": value["registry_version"],
        "sources": sorted(
            [
                {
                    key: row.get(key)
                    for key in (
                        "source_key",
                        "name_zh",
                        "name_en",
                        "status",
                        "official_url",
                        "evidence",
                    )
                }
                for row in sources
            ],
            key=lambda row: row["source_key"],
        ),
        "aliases": sorted(
            [
                {
                    key: row.get(key)
                    for key in (
                        "alias_norm",
                        "alias_kind",
                        "source_key",
                        "resolution_status",
                        "evidence",
                    )
                }
                for row in aliases
            ],
            key=lambda row: (row["alias_kind"], row["alias_norm"], str(row.get("source_key"))),
        ),
    }
    result["registry_sha256"] = registry_digest(result)
    if value.get("registry_sha256") not in (None, result["registry_sha256"]):
        raise ValueError("source registry hash mismatch")
    return result


def registry_identity(connection: Any) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT registry_version,registry_sha256 FROM source_registry_state WHERE singleton"
        )
        row = cursor.fetchone()
    return {"registry_version": int(row[0]), "registry_sha256": str(row[1])} if row else {}


def registry_deployed_targets(connection: Any) -> list[str]:
    """Return independent targets that acknowledged the current Hub revision."""
    identity = registry_identity(connection)
    if not identity:
        return []
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT receipt_json->>'target' FROM source_registry_receipts "
            "WHERE receipt_json->>'registry_version'=%s AND receipt_json->>'registry_sha256'=%s "
            "AND receipt_json->>'status' IN ('applied','unchanged')",
            (str(identity["registry_version"]), identity["registry_sha256"]),
        )
        targets = {row[0] for row in cursor.fetchall()}
    return sorted(targets.intersection({"china", "overseas"}))


def export_registry(connection: Any) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT registry_version, registry_sha256 FROM source_registry_state WHERE singleton"
        )
        state = cursor.fetchone()
        if not state:
            raise ValueError("source registry has not been published by the Hub")
        cursor.execute(
            "SELECT source_key, name_zh, name_en, status, official_url, evidence_json FROM canonical_sources ORDER BY source_key"
        )
        sources = [
            dict(
                zip(("source_key", "name_zh", "name_en", "status", "official_url", "evidence"), row)
            )
            for row in cursor.fetchall()
        ]
        cursor.execute(
            "SELECT alias_norm, alias_kind, source_key, resolution_status, evidence_json FROM source_aliases ORDER BY alias_kind, alias_norm, source_key"
        )
        aliases = [
            dict(
                zip(
                    ("alias_norm", "alias_kind", "source_key", "resolution_status", "evidence"), row
                )
            )
            for row in cursor.fetchall()
        ]
    return validate_registry(
        {
            "registry_version": int(state[0]),
            "registry_sha256": str(state[1]),
            "sources": sources,
            "aliases": aliases,
        }
    )


def install_registry(
    connection: Any, payload: dict[str, Any], *, target: str, apply: bool
) -> dict[str, Any]:
    """Caller owns the transaction; monotonic revision and hash reject stale replay."""
    value = validate_registry(payload)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(current_schema() || ':source_registry', 0))"
        )
        cursor.execute(
            "SELECT registry_version, registry_sha256 FROM source_registry_state WHERE singleton"
            + (" FOR UPDATE" if apply else "")
        )
        old = cursor.fetchone()
        version, digest = value["registry_version"], value["registry_sha256"]
        if old and (version < int(old[0]) or (version == int(old[0]) and digest != str(old[1]))):
            raise ValueError("stale or conflicting source registry revision")
        if old and version > int(old[0]) and digest == str(old[1]):
            raise ValueError("unchanged registry must retain its existing revision")
        unchanged = bool(old and version == int(old[0]))
        if apply and not unchanged:
            cursor.execute("SELECT alias_kind, alias_norm FROM source_aliases")
            old_aliases = {tuple(row) for row in cursor.fetchall()}
            if not old_aliases.issubset(
                {(row["alias_kind"], row["alias_norm"]) for row in value["aliases"]}
            ):
                raise ValueError("retain historical aliases; mark ambiguous instead of removing")
            cursor.execute("SELECT source_key FROM canonical_sources")
            existing_keys = {row[0] for row in cursor.fetchall()}
            if not existing_keys.issubset({row["source_key"] for row in value["sources"]}):
                raise ValueError("retain historical canonical sources; retire instead of removing")
            for row in value["sources"]:
                cursor.execute(
                    "INSERT INTO canonical_sources VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(source_key) DO UPDATE SET name_zh=excluded.name_zh,name_en=excluded.name_en,status=excluded.status,official_url=excluded.official_url,evidence_json=excluded.evidence_json",
                    (
                        row["source_key"],
                        row["name_zh"],
                        row["name_en"],
                        row["status"],
                        row.get("official_url"),
                        Json(row["evidence"]),
                    ),
                )
            cursor.execute("DELETE FROM source_aliases")
            for row in value["aliases"]:
                cursor.execute(
                    "INSERT INTO source_aliases VALUES (%s,%s,%s,%s,%s)",
                    (
                        row["alias_norm"],
                        row["alias_kind"],
                        row.get("source_key"),
                        row["resolution_status"],
                        Json(row["evidence"]),
                    ),
                )
            cursor.execute(
                "INSERT INTO source_registry_state(singleton,registry_version,registry_sha256) VALUES(TRUE,%s,%s) ON CONFLICT(singleton) DO UPDATE SET registry_version=excluded.registry_version,registry_sha256=excluded.registry_sha256,updated_at=CURRENT_TIMESTAMP",
                (version, digest),
            )
        receipt = {
            "receipt_id": uuid.uuid4().hex,
            "target": target,
            "registry_version": version,
            "registry_sha256": digest,
            "source_count": len(value["sources"]),
            "alias_count": len(value["aliases"]),
            "status": "unchanged" if unchanged else ("applied" if apply else "dry_run"),
        }
        if apply:
            cursor.execute(
                "INSERT INTO source_registry_receipts(receipt_id,receipt_json) VALUES (%s,%s)",
                (receipt["receipt_id"], Json(receipt)),
            )
    return receipt


def source_override_key(connection: Any, *, url: str, raw_sha256: str | None) -> str | None:
    """None means no exact override; an explicit pending remains authoritative."""
    if not raw_sha256:
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT source_key FROM source_projection WHERE url=%s AND raw_sha256=%s",
            (url, raw_sha256),
        )
        row = cursor.fetchone()
    return (row[0] or PENDING_KEY) if row else None


def resolve_source(
    connection: Any, *, url: str, raw_source: str | None, raw_sha256: str | None = None
) -> str:
    """An external/CDN URL cannot inherit the association of its discovery page."""
    override = source_override_key(connection, url=url, raw_sha256=raw_sha256)
    if override is not None:
        return override
    with connection.cursor() as cursor:
        try:
            parsed = urlsplit(url)
        except ValueError:
            return PENDING_KEY
        if parsed.username or parsed.password:
            return PENDING_KEY
        if parsed.scheme.lower() in {"http", "https"}:
            kind, token = "hostname", (parsed.hostname or "").lower()
        else:
            kind, token = "name", normalize_alias(raw_source or "")
        cursor.execute(
            "SELECT source_key FROM source_aliases WHERE alias_kind=%s AND alias_norm=%s AND resolution_status='verified'",
            (kind, token),
        )
        row = cursor.fetchone()
        return str(row[0]) if row else PENDING_KEY


def resolve_bookmark(connection: Any, value: str) -> tuple[str | None, str]:
    token = normalize_alias(value)
    if token == PENDING_KEY:
        return PENDING_KEY, "exact_key"
    with connection.cursor() as cursor:
        cursor.execute("SELECT source_key FROM canonical_sources WHERE source_key=%s", (token,))
        row = cursor.fetchone()
        if row:
            return str(row[0]), "exact_key"
        cursor.execute(
            "SELECT source_key, resolution_status FROM source_aliases WHERE alias_kind='name' AND alias_norm=%s",
            (token,),
        )
        rows = cursor.fetchall()
        verified = {row[0] for row in rows if row[1] == "verified"}
        if len(verified) == 1 and all(row[1] == "verified" for row in rows):
            return str(next(iter(verified))), "exact_alias"
        cursor.execute(
            "SELECT source_key FROM canonical_sources WHERE lower(name_zh)=%s OR lower(name_en)=%s",
            (token, token),
        )
        names = {row[0] for row in cursor.fetchall()}
        if not rows and len(names) == 1:
            return str(next(iter(names))), "exact_name"
        return None, "ambiguous" if rows or len(names) > 1 else "unknown"


def source_fields(connection: Any, key: str) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT name_zh, name_en FROM canonical_sources WHERE source_key=%s", (key,))
        row = cursor.fetchone()
    return {
        "source_key": key,
        "source_name_zh": row[0] if row else "来源待确认",
        "source_name_en": row[1] if row else "Source pending confirmation",
    }


def source_sql() -> str:
    """Equivalent to resolve_source for the app's exact SQL filtering/counting."""
    return """COALESCE(
        (SELECT COALESCE(p.source_key, 'pending') FROM source_projection p WHERE p.url=f.url AND p.raw_sha256=f.sha256),
        (SELECT a.source_key FROM source_aliases a
         WHERE a.resolution_status='verified' AND (
           (a.alias_kind='hostname' AND lower(split_part(f.url, '://', 1)) IN ('http','https')
            AND a.alias_norm=lower(substring(f.url from '(?i)^https?://([^/?#:@]+)')))
           OR (a.alias_kind='name' AND lower(split_part(f.url, '://', 1)) NOT IN ('http','https')
               AND a.alias_norm=lower(trim(COALESCE(f.source_site,'')))))), 'pending')"""


def correct_sources(
    connection: Any,
    records: list[dict[str, Any]],
    *,
    hub: bool,
    apply: bool,
    rollback: str | None = None,
    request_id: str | None = None,
    reconfirm_same_key: bool | None = None,
) -> dict[str, Any]:
    """Apply exact overrides with receipt identity, idempotency and pointer-safe rollback."""
    explicit_request = request_id is not None
    receipt_id = request_id or uuid.uuid4().hex
    if (
        not isinstance(receipt_id, str)
        or not receipt_id.strip()
        or receipt_id != receipt_id.strip()
        or len(receipt_id) > 128
    ):
        raise ValueError("request_id must be a nonempty identifier of at most 128 characters")
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError("correction records must be an array of objects")
    input_fields = (
        "url",
        "raw_sha256",
        "raw_source_site",
        "old_source_key",
        "new_source_key",
        "reason",
        "evidence",
        "old_override",
        "upstream_receipt_id",
    )
    intent = reconfirm_same_key if apply and not rollback else explicit_request and not rollback
    request_body = {
        "hub": hub,
        "rollback_of": rollback,
        "reconfirm_same_key": intent,
        "records": [{key: row[key] for key in input_fields if key in row} for row in records],
    }
    if apply and not rollback:
        if not explicit_request or type(intent) is not bool:
            raise ValueError(
                "apply requires the saved dry-run request_id and reconfirm_same_key intent"
            )
        for row in records:
            state = row.get("old_override")
            if (
                not isinstance(state, dict)
                or set(state) != {"exists", "source_key", "correction_receipt_id"}
                or type(state.get("exists")) is not bool
                or (
                    state["exists"]
                    and (
                        not isinstance(state["source_key"], str)
                        or not _KEY.fullmatch(state["source_key"])
                    )
                )
                or (
                    not state["exists"]
                    and any(
                        state[key] is not None for key in ("source_key", "correction_receipt_id")
                    )
                )
                or (
                    state["correction_receipt_id"] is not None
                    and (
                        not isinstance(state["correction_receipt_id"], str)
                        or not state["correction_receipt_id"].strip()
                    )
                )
            ):
                raise ValueError(
                    "apply requires each complete old_override snapshot from the saved dry-run"
                )
    results = []
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(current_schema() || ':source_registry', 0))"
        )
        registry = export_registry(connection)
        valid_keys = {row["source_key"] for row in registry["sources"]}
        cursor.execute(
            "SELECT receipt_json FROM source_correction_receipts WHERE receipt_id=%s", (receipt_id,)
        )
        existing = cursor.fetchone()
        replay = existing[0] if existing else None
        if replay:
            if (
                replay.get("overlay_state_version") != 2
                or replay.get("request_body") != request_body
            ):
                raise ValueError(
                    "request_id conflict: receipt body differs; rerun reviewed dry-run"
                )
            records = replay["records"]
        elif rollback:
            cursor.execute(
                "SELECT receipt_json FROM source_correction_receipts WHERE receipt_id=%s",
                (rollback,),
            )
            original = cursor.fetchone()
            if not original:
                raise ValueError("unknown correction receipt")
            previous = original[0]
            if (
                previous.get("hub") != hub
                or previous.get("rollback_of")
                or previous.get("apply") is not True
            ):
                raise ValueError("receipt belongs to another correction mode")
            if previous.get("overlay_state_version") != 2:
                raise ValueError("unknown correction receipt overlay state; rerun reviewed dry-run")
            records = [
                {
                    **row,
                    "old_source_key": row["new_source_key"],
                    "new_source_key": row["old_override"]["source_key"],
                    "expected_override": row["new_override"],
                    "restore_override": row["old_override"],
                }
                for row in previous["records"]
                if row["status"] == "applied"
            ]
        for record in records:
            row = dict(record)
            required = {
                "url",
                "raw_sha256",
                "raw_source_site",
                "old_source_key",
                "new_source_key",
                "reason",
                "evidence",
            }
            if (
                not required.issubset(row)
                or not row["reason"]
                or not row["evidence"]
                or not re.fullmatch(r"[0-9a-f]{64}", str(row["raw_sha256"]))
            ):
                raise ValueError(
                    "correction requires exact identity, expected values, reason and evidence"
                )
            new_key = row["new_source_key"]
            if new_key is not None and new_key not in valid_keys:
                raise ValueError("correction refers to unknown canonical source")
            if hub:
                cursor.execute(
                    "SELECT v.content_version_id FROM content_versions v WHERE v.url_value_json=%s AND v.raw_sha256=%s"
                    + (" FOR UPDATE OF v" if apply else ""),
                    (json.dumps(row["url"], ensure_ascii=False, sort_keys=True), row["raw_sha256"]),
                )
                identity = cursor.fetchone()
                if identity:
                    cursor.execute(
                        "SELECT source_metadata_json FROM source_record_map WHERE content_version_id=%s ORDER BY source_snapshot_id",
                        (identity[0],),
                    )
                    raw_matches = row["raw_source_site"] in [
                        json.loads(item[0]).get("source_site") for item in cursor.fetchall()
                    ]
                else:
                    raw_matches = False
            else:
                if apply:
                    cursor.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        (f"file:{row['url']}",),
                    )
                cursor.execute(
                    "SELECT source_site FROM files WHERE url=%s AND sha256=%s"
                    + (" FOR UPDATE" if apply else ""),
                    (row["url"], row["raw_sha256"]),
                )
                identity = cursor.fetchone()
                raw_matches = bool(identity and identity[0] == row["raw_source_site"])
            cursor.execute(
                "SELECT source_key,correction_receipt_id FROM source_projection WHERE url=%s AND raw_sha256=%s"
                + (" FOR UPDATE" if apply else ""),
                (row["url"], row["raw_sha256"]),
            )
            projected = cursor.fetchone()
            before = {
                "exists": projected is not None,
                "source_key": (projected[0] or PENDING_KEY) if projected else None,
                "correction_receipt_id": projected[1] if projected else None,
            }
            if replay:
                if row["status"] not in {"applied", "unchanged"}:
                    row["status"] = "skipped" if row["status"] == "skipped" else "conflict"
                elif not identity:
                    row["status"] = "skipped"
                elif not raw_matches or before != row["new_override"]:
                    row["status"] = "conflict"
                else:
                    row["status"] = "unchanged"
                results.append(row)
                continue
            desired = (
                row["restore_override"]
                if rollback
                else {
                    "exists": new_key is not None,
                    "source_key": new_key,
                    "correction_receipt_id": receipt_id if new_key is not None else None,
                }
            )
            current = (
                before["source_key"]
                if hub
                else resolve_source(
                    connection,
                    url=row["url"],
                    raw_source=row["raw_source_site"],
                    raw_sha256=row["raw_sha256"],
                )
            )
            expected = row.get("expected_override") if rollback else row.get("old_override")
            same_value = (
                before["exists"] == desired["exists"]
                and before["source_key"] == desired["source_key"]
            )
            if not identity:
                row["status"] = "skipped"
            elif not raw_matches:
                row["status"] = "conflict"
            elif rollback and before == desired:
                row["status"] = "unchanged"
            elif expected is not None and before != expected:
                row["status"] = "conflict"
            elif before == desired or (not rollback and not intent and same_value):
                row["status"] = "unchanged"
                desired = before
            elif not rollback and current != row["old_source_key"]:
                row["status"] = "conflict"
            else:
                row["status"] = "applied" if apply else "would_apply"
                if apply:
                    if desired["exists"]:
                        cursor.execute(
                            "INSERT INTO source_projection(url,raw_sha256,source_key,correction_receipt_id) VALUES (%s,%s,%s,%s) ON CONFLICT(url,raw_sha256) DO UPDATE SET source_key=excluded.source_key,correction_receipt_id=excluded.correction_receipt_id",
                            (
                                row["url"],
                                row["raw_sha256"],
                                desired["source_key"],
                                desired["correction_receipt_id"],
                            ),
                        )
                    else:
                        cursor.execute(
                            "DELETE FROM source_projection WHERE url=%s AND raw_sha256=%s",
                            (row["url"], row["raw_sha256"]),
                        )
                    if not hub:
                        effective = resolve_source(
                            connection,
                            url=row["url"],
                            raw_source=row["raw_source_site"],
                            raw_sha256=row["raw_sha256"],
                        )
                        cursor.execute(
                            "UPDATE files SET source_key=%s WHERE url=%s AND sha256=%s",
                            (effective, row["url"], row["raw_sha256"]),
                        )
            row["old_override"] = before
            row["new_override"] = (
                desired if row["status"] in {"applied", "would_apply", "unchanged"} else before
            )
            results.append(row)
        if replay:
            return {**replay, "records": results, "apply": apply, "replay": True}
        if not apply and not rollback:
            request_body["records"] = [
                {key: row[key] for key in input_fields if key in row} for row in results
            ]
        receipt = {
            "receipt_id": receipt_id,
            "request_id": receipt_id,
            "hub": hub,
            "rollback_of": rollback,
            "registry_version": registry["registry_version"],
            "registry_sha256": registry["registry_sha256"],
            "apply": apply,
            "overlay_state_version": 2,
            "request_body": request_body,
            "records": results,
        }
        if apply:
            cursor.execute(
                "INSERT INTO source_correction_receipts(receipt_id,receipt_json) VALUES(%s,%s)",
                (receipt_id, Json(receipt)),
            )
    return receipt
