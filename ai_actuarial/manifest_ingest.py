"""Manifest ingestion: consume a web-listening-manifest.v1 JSON into Storage.

Archives the manifest for provenance/replay and maps each downloaded asset into
the existing ``files`` table, reusing the existing ``url`` + ``sha256`` dedup so
re-ingesting the same manifest is naturally idempotent.
"""

from __future__ import annotations

import json
from typing import Any


def content_kind_for(media_type: str | None) -> str:
    """Classify a downloaded asset as a file or a web page."""
    if media_type and "html" in media_type.lower():
        return "web_page"
    return "file"


def ingest_manifest(
    storage: Any,
    manifest: dict[str, Any],
    *,
    raw_text: str | None = None,
) -> dict[str, Any]:
    """Ingest a ``web-listening-manifest.v1`` manifest into ``storage``.

    ``raw_text``, when provided, is archived byte-for-byte for provenance;
    otherwise the parsed manifest is re-serialized as a JSON snapshot.

    Returns a small summary dict with the manifest id and imported-asset count.
    """
    schema_version = str(manifest.get("schema_version") or "")
    manifest_id = str(manifest.get("manifest_id") or "")
    run = manifest.get("run") or {}
    source = manifest.get("source") or {}

    run_id = str(run.get("run_id") or "")
    source_id = str(source.get("source_id") or "")
    site_name = str(source.get("site_name") or "")
    site_url = str(source.get("site_url") or "")

    archive_text = raw_text if raw_text is not None else json.dumps(manifest, ensure_ascii=False)

    with storage.transaction(immediate=True):
        # 1. Store the manifest (never lost). A manifest without an id is
        # malformed, so skip archiving rather than colliding on an empty key.
        if manifest_id:
            storage.save_manifest_raw(
                manifest_id=manifest_id,
                schema_version=schema_version,
                source_id=source_id,
                run_id=run_id,
                manifest_json=archive_text,
            )

        # 2. Map each downloaded asset into the files table.
        imported = 0
        assets = manifest.get("downloaded_assets")
        if not isinstance(assets, list):
            assets = []
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            url = str(asset.get("url") or "")
            if not url:
                continue
            checksum = asset.get("checksum") or {}
            sha256 = ""
            if isinstance(checksum, dict):
                algorithm = str(checksum.get("algorithm") or "").lower()
                if algorithm in ("", "sha256", "sha-256"):
                    sha256 = str(checksum.get("value") or "")
            media_type = asset.get("media_type")
            if not isinstance(media_type, str):
                media_type = None
            local_path = str(
                asset.get("canonical_blob_path")
                or asset.get("tracked_path")
                or asset.get("local_path")
                or ""
            )
            filename = asset.get("filename") or None
            storage.upsert_file(
                url=url,
                sha256=sha256,
                title=filename,
                source_site=site_name,
                source_page_url=site_url,
                original_filename=filename,
                local_path=local_path,
                bytes_size=asset.get("bytes"),
                content_type=media_type,
                last_modified=None,
                etag=None,
                published_time=None,
                content_kind=content_kind_for(media_type),
            )
            imported += 1

    return {
        "manifest_id": manifest_id,
        "schema_version": schema_version,
        "source_id": source_id,
        "run_id": run_id,
        "imported": imported,
    }
