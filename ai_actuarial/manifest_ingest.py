"""Strict ingestion for the legacy web-listening manifest contract."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit

SUPPORTED_MANIFEST_SCHEMA = "web-listening-manifest.v1"
_ASSET_PATH_FIELDS = ("canonical_blob_path", "tracked_path", "local_path")
_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}")


class ManifestIngestError(ValueError):
    """A stable, value-free manifest parsing or contract error."""

    def __init__(self, code: str, field: str) -> None:
        super().__init__(f"{code}: {field}")
        self.code = code
        self.field = field
        self.details = {"field": field}


def content_kind_for(media_type: str | None) -> str:
    """Classify a downloaded asset as a file or a web page."""
    if media_type and "html" in media_type.lower():
        return "web_page"
    return "file"


def parse_manifest_json(raw_text: str) -> dict[str, Any]:
    """Parse a manifest JSON string while rejecting duplicate object keys."""

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ManifestIngestError("manifest_json_duplicate_key", "json")
            result[key] = value
        return result

    def reject_non_json_constant(_value: str) -> None:
        raise ManifestIngestError("manifest_json_invalid", "json")

    try:
        value = json.loads(
            raw_text,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_non_json_constant,
        )
    except (json.JSONDecodeError, TypeError):
        raise ManifestIngestError("manifest_json_invalid", "json") from None
    if not isinstance(value, dict):
        raise ManifestIngestError("invalid_manifest_contract", "manifest")
    return value


def _same_json_value(left: Any, right: Any) -> bool:
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _same_json_value(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _same_json_value(left_item, right_item) for left_item, right_item in zip(left, right)
        )
    return type(left) is type(right) and left == right


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestIngestError("invalid_manifest_contract", field)
    return value


def _required_url(value: Any, field: str) -> str:
    url = _required_string(value, field)
    try:
        parsed = urlsplit(url)
        valid_port = parsed.port is None or parsed.port >= 0
    except ValueError:
        raise ManifestIngestError("invalid_manifest_contract", field) from None
    if "\\" in url:
        raise ManifestIngestError("invalid_manifest_contract", field)
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or not parsed.hostname
        or not valid_port
        or any(character.isspace() for character in url)
    ):
        raise ManifestIngestError("invalid_manifest_contract", field)
    return url


def _validate_asset(asset: Any, index: int) -> dict[str, Any]:
    prefix = f"downloaded_assets[{index}]"
    if not isinstance(asset, dict):
        raise ManifestIngestError("invalid_manifest_contract", prefix)

    _required_string(asset.get("asset_id"), f"{prefix}.asset_id")
    url = _required_url(asset.get("url"), f"{prefix}.url")

    checksum = asset.get("checksum")
    if not isinstance(checksum, dict):
        raise ManifestIngestError("invalid_manifest_contract", f"{prefix}.checksum")
    algorithm = _required_string(checksum.get("algorithm"), f"{prefix}.checksum.algorithm")
    if algorithm.lower() not in {"sha256", "sha-256"}:
        raise ManifestIngestError("invalid_manifest_contract", f"{prefix}.checksum.algorithm")
    sha256 = _required_string(checksum.get("value"), f"{prefix}.checksum.value")
    if _SHA256_RE.fullmatch(sha256) is None:
        raise ManifestIngestError("invalid_manifest_contract", f"{prefix}.checksum.value")

    media_type = _required_string(asset.get("media_type"), f"{prefix}.media_type")
    bytes_size = asset.get("bytes")
    if isinstance(bytes_size, bool) or not isinstance(bytes_size, int) or bytes_size < 0:
        raise ManifestIngestError("invalid_manifest_contract", f"{prefix}.bytes")
    filename = _required_string(asset.get("filename"), f"{prefix}.filename")

    paths: dict[str, str] = {}
    for path_field in _ASSET_PATH_FIELDS:
        if path_field in asset:
            paths[path_field] = _required_string(asset[path_field], f"{prefix}.{path_field}")
    local_path = next((paths[field] for field in _ASSET_PATH_FIELDS if field in paths), None)
    if local_path is None:
        raise ManifestIngestError("invalid_manifest_contract", f"{prefix}.local_path")

    return {
        "url": url,
        "sha256": sha256,
        "media_type": media_type,
        "bytes": bytes_size,
        "filename": filename,
        "local_path": local_path,
    }


def validate_manifest(manifest: Any) -> dict[str, Any]:
    """Validate every importer-consumed field without opening a transaction."""
    if not isinstance(manifest, dict):
        raise ManifestIngestError("invalid_manifest_contract", "manifest")

    schema_version = manifest.get("schema_version")
    if not isinstance(schema_version, str) or schema_version != SUPPORTED_MANIFEST_SCHEMA:
        raise ManifestIngestError("unsupported_manifest_contract", "schema_version")

    manifest_id = _required_string(manifest.get("manifest_id"), "manifest_id")
    run = manifest.get("run")
    if not isinstance(run, dict):
        raise ManifestIngestError("invalid_manifest_contract", "run")
    run_id = _required_string(run.get("run_id"), "run.run_id")

    source = manifest.get("source")
    if not isinstance(source, dict):
        raise ManifestIngestError("invalid_manifest_contract", "source")
    source_id = _required_string(source.get("source_id"), "source.source_id")
    site_name = _required_string(source.get("site_name"), "source.site_name")
    site_url = _required_url(source.get("site_url"), "source.site_url")

    assets = manifest.get("downloaded_assets")
    if not isinstance(assets, list):
        raise ManifestIngestError("invalid_manifest_contract", "downloaded_assets")
    validated_assets = [_validate_asset(asset, index) for index, asset in enumerate(assets)]

    return {
        "schema_version": schema_version,
        "manifest_id": manifest_id,
        "run_id": run_id,
        "source_id": source_id,
        "site_name": site_name,
        "site_url": site_url,
        "assets": validated_assets,
    }


def _prepare_manifest(manifest: Any, raw_text: str | None) -> tuple[dict[str, Any], str]:
    if raw_text is not None:
        parsed = parse_manifest_json(raw_text)
        if not _same_json_value(manifest, parsed):
            raise ManifestIngestError("invalid_manifest_contract", "raw_text")
        archive_text = raw_text
    else:
        if not isinstance(manifest, dict):
            raise ManifestIngestError("invalid_manifest_contract", "manifest")
        try:
            archive_text = json.dumps(manifest, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError):
            raise ManifestIngestError("invalid_manifest_contract", "manifest") from None
        parsed = parse_manifest_json(archive_text)
        if not _same_json_value(manifest, parsed):
            raise ManifestIngestError("invalid_manifest_contract", "manifest")
    return validate_manifest(parsed), archive_text


def ingest_manifest(
    storage: Any,
    manifest: dict[str, Any],
    *,
    raw_text: str | None = None,
) -> dict[str, Any]:
    """Validate then atomically archive and ingest one legacy manifest."""
    validated, archive_text = _prepare_manifest(manifest, raw_text)

    with storage.transaction(immediate=True):
        storage.save_manifest_raw(
            manifest_id=validated["manifest_id"],
            schema_version=validated["schema_version"],
            source_id=validated["source_id"],
            run_id=validated["run_id"],
            manifest_json=archive_text,
        )
        for asset in validated["assets"]:
            storage.upsert_file(
                url=asset["url"],
                sha256=asset["sha256"],
                title=asset["filename"],
                source_site=validated["site_name"],
                source_page_url=validated["site_url"],
                original_filename=asset["filename"],
                local_path=asset["local_path"],
                bytes_size=asset["bytes"],
                content_type=asset["media_type"],
                last_modified=None,
                etag=None,
                published_time=None,
                content_kind=content_kind_for(asset["media_type"]),
            )

    return {
        "manifest_id": validated["manifest_id"],
        "schema_version": validated["schema_version"],
        "source_id": validated["source_id"],
        "run_id": validated["run_id"],
        "imported": len(validated["assets"]),
    }
