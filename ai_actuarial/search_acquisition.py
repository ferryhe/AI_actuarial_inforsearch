from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, unquote_plus, urlencode, urlsplit, urlunsplit


ACQUISITION_DISPOSITIONS = (
    "downloaded_new",
    "already_exists",
    "filtered",
    "access_blocked",
    "redirect_or_content_type_mismatch",
    "download_failed",
    "storage_failed",
    "stopped_or_timeout",
    "no_eligible_file_found",
)

_ALLOWED_SUBREASONS = {
    "url",
    "normalized_url",
    "content_hash",
    "domain",
    "path",
    "extension",
    "keyword",
    "collection_disabled",
    "http_status",
    "challenge",
    "login",
    "cookie",
    "javascript",
    "redirect",
    "content_type",
    "network",
    "storage",
    "stopped",
    "timeout",
    "empty",
    "other",
}

MAX_OUTCOME_URL_LENGTH = 512
MAX_OUTCOME_REASON_LENGTH = 160
_REDACTED = "[REDACTED]"
_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_QUERY_PART_PATTERN = re.compile(r"(^|[&;])([^=&;]+)(=)([^&;]*)")
_SENSITIVE_QUERY_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "key",
    "password",
    "passwd",
    "secret",
    "signature",
    "sig",
    "auth",
    "authorization",
    "credential",
    "code",
    "policy",
    "awsaccesskeyid",
    "googleaccessid",
    "key-pair-id",
    "api-key",
    "x-api-key",
    "subscription-key",
    "cookie",
    "session",
    "sessionid",
}


@dataclass(slots=True)
class SearchAcquisitionReport:
    items: list[dict]
    outcome: dict[str, Any]


def _bounded(text: str, limit: int) -> str:
    value = str(text or "")
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def _is_sensitive_query_key(raw_key: str) -> bool:
    key = unquote_plus(str(raw_key or "")).strip().lower()
    if key in _SENSITIVE_QUERY_KEYS:
        return True
    if key.startswith(("x-amz-", "x-goog-")):
        return True
    return key.endswith(
        (
            "_token",
            "-token",
            "_signature",
            "-signature",
            "_credential",
            "-credential",
            "_secret",
            "-secret",
            "_password",
            "-password",
            "_key",
            "-key",
        )
    )


def safe_outcome_url(url: str | None) -> str | None:
    if url is None:
        return None
    raw = str(url or "")
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return "[REDACTED_URL]"

    netloc = parsed.netloc
    if "@" in netloc:
        _, _, host = netloc.rpartition("@")
        netloc = f"{_REDACTED}@{host}"

    def redact_query_value(match: re.Match[str]) -> str:
        prefix, key, separator, value = match.groups()
        if _is_sensitive_query_key(key):
            value = _REDACTED
        return f"{prefix}{key}{separator}{value}"

    query = _QUERY_PART_PATTERN.sub(redact_query_value, parsed.query)
    fragment = _QUERY_PART_PATTERN.sub(redact_query_value, parsed.fragment)
    safe = urlunsplit((parsed.scheme, netloc, parsed.path, query, fragment))
    return _bounded(safe, MAX_OUTCOME_URL_LENGTH)


def safe_outcome_reason(reason: str) -> str:
    safe = _URL_PATTERN.sub(lambda match: safe_outcome_url(match.group(0)) or "", str(reason or ""))
    safe = re.sub(
        r"(?i)\b(token|api[_-]?key|password|secret|signature|credential|authorization|cookie|session)\s*[=:]\s*[^\s,;]+",
        lambda match: f"{match.group(1)}={_REDACTED}",
        safe,
    )
    return _bounded(safe, MAX_OUTCOME_REASON_LENGTH)


def normalize_acquisition_url(url: str) -> str:
    """Return a stable URL variant used only for duplicate checks."""
    try:
        parsed = urlsplit(str(url or "").strip())
        scheme = parsed.scheme.lower()
        hostname = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return str(url or "").strip()
    if not scheme or not hostname:
        return str(url or "").strip()
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    host = hostname if port is None or default_port else f"{hostname}:{port}"
    path = parsed.path or "/"
    try:
        query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)), doseq=True)
    except ValueError:
        query = parsed.query
    return urlunsplit((scheme, host, path, query, ""))


def make_acquisition_outcome(
    disposition: str,
    *,
    url: str,
    final_url: str | None = None,
    http_status: int | None = None,
    subreason: str | None = None,
    reason: str,
    downloaded: int = 0,
    skipped: int = 0,
    failed: int = 0,
) -> dict[str, Any]:
    if disposition not in ACQUISITION_DISPOSITIONS:
        raise ValueError(f"Unsupported acquisition disposition: {disposition}")
    bounded_subreason = str(subreason or "").strip().lower() or None
    if bounded_subreason is not None and bounded_subreason not in _ALLOWED_SUBREASONS:
        bounded_subreason = "other"
    bounded_status = None
    if http_status is not None:
        try:
            candidate = int(http_status)
        except (TypeError, ValueError):
            candidate = 0
        if 100 <= candidate <= 599:
            bounded_status = candidate
    return {
        "disposition": disposition,
        "url": safe_outcome_url(url) or "",
        "final_url": safe_outcome_url(final_url),
        "http_status": bounded_status,
        "subreason": bounded_subreason,
        "reason": safe_outcome_reason(reason),
        "downloaded": max(0, int(downloaded or 0)),
        "skipped": max(0, int(skipped or 0)),
        "failed": max(0, int(failed or 0)),
    }


def summarize_acquisition_outcomes(outcomes: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    rows = list(outcomes)
    summary = {name: 0 for name in ACQUISITION_DISPOSITIONS}
    downloaded = skipped = failed = 0
    for row in rows:
        disposition = str(row.get("disposition") or "")
        if disposition in summary:
            summary[disposition] += 1
        downloaded += max(0, int(row.get("downloaded") or 0))
        skipped += max(0, int(row.get("skipped") or 0))
        failed += max(0, int(row.get("failed") or 0))
    return {
        "total": len(rows),
        "outcome_count": len(rows),
        "downloaded": downloaded,
        "skipped": skipped,
        "failed": failed,
        **summary,
    }


def format_acquisition_outcome(index: int, total: int, outcome: Mapping[str, Any]) -> str:
    parts = [
        f"Search acquisition result {index}/{total}:",
        f"disposition={outcome.get('disposition')}",
        f"url={safe_outcome_url(str(outcome.get('url') or ''))}",
    ]
    if outcome.get("final_url") and outcome.get("final_url") != outcome.get("url"):
        parts.append(f"final_url={safe_outcome_url(str(outcome.get('final_url') or ''))}")
    if outcome.get("http_status") is not None:
        parts.append(f"http_status={int(outcome['http_status'])}")
    if outcome.get("subreason"):
        parts.append(f"subreason={outcome.get('subreason')}")
    parts.extend(
        (
            f"downloaded={max(0, int(outcome.get('downloaded') or 0))}",
            f"skipped={max(0, int(outcome.get('skipped') or 0))}",
            f"failed={max(0, int(outcome.get('failed') or 0))}",
            f"reason={safe_outcome_reason(str(outcome.get('reason') or ''))}",
        )
    )
    return " ".join(parts)


def format_acquisition_summary(summary: Mapping[str, Any]) -> str:
    ordered = (
        "total",
        "downloaded",
        "skipped",
        "failed",
        *ACQUISITION_DISPOSITIONS,
    )
    return " ".join(f"{key}={max(0, int(summary.get(key) or 0))}" for key in ordered)
