"""Bounded daily observations and factual bilingual prose, without source/model requests."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .source_portals import source_portal_for_observation

_GENERIC_MATERIAL_LABEL = re.compile(
    r"(?:download(?:\s+(?:(?:the|this|full|complete|entire|free|latest|current)\s+)*(?:paper|report|file|document|pdf|publication))?|click here|read more|view|下载(?:附件|文件)?|点击下载)",
    re.IGNORECASE,
)


def is_generic_material_label(title: str) -> bool:
    """Return whether a title is a generic action label rather than a material name."""
    return bool(_GENERIC_MATERIAL_LABEL.fullmatch(" ".join(str(title).split()).strip()))


def _observation_scope(item: dict[str, Any]) -> str | None:
    # Legacy pages lack request provenance; file downloads are always comparable GETs.
    return item.get("request_scope", "" if item["kind"] == "file" else None)


def validate_daily_evidence(evidence: dict[str, Any]) -> tuple[dt.datetime, dt.date, str]:
    if not isinstance(evidence, dict) or set(evidence) != {
        "schema_version",
        "portal_key",
        "site_id",
        "run_id",
        "captured_at",
        "acquired_on",
        "observations",
        "hub_results",
        "limits",
    }:
        raise ValueError("daily evidence has an invalid shape")
    if (
        type(evidence["schema_version"]) is not int
        or evidence["schema_version"] != 1
        or not isinstance(evidence["run_id"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", evidence["run_id"])
        or not isinstance(evidence["portal_key"], str)
        or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", evidence["portal_key"])
        or not isinstance(evidence["site_id"], str)
    ):
        raise ValueError("daily evidence identity is invalid")
    captured_at = dt.datetime.fromisoformat(evidence["captured_at"].replace("Z", "+00:00"))
    acquired_on = dt.date.fromisoformat(evidence["acquired_on"])
    if (
        captured_at.tzinfo is None
        or acquired_on != captured_at.astimezone(ZoneInfo("America/New_York")).date()
    ):
        raise ValueError("daily evidence date does not match its acquisition")

    def validate_items(name: str, maximum: int) -> None:
        items = evidence[name]
        if not isinstance(items, list) or len(items) > maximum:
            raise ValueError("daily evidence exceeds its item limit")
        seen = set()
        for item in items:
            fields = (
                {"url", "raw_sha256", "source_page_url", "title", "kind"}
                if name == "observations"
                else {"url", "raw_sha256", "source_page_url", "content_version_id", "status"}
            )
            allowed_shapes = (
                (
                    fields,
                    fields | {"request_scope"},
                    fields | {"is_article"},
                    fields | {"request_scope", "is_article"},
                )
                if name == "observations"
                else (fields,)
            )
            if not isinstance(item, dict) or set(item) not in allowed_shapes:
                raise ValueError("daily evidence item has an invalid shape")
            if "request_scope" in item and (
                not isinstance(item["request_scope"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", item["request_scope"])
            ):
                raise ValueError("daily evidence request scope is invalid")
            for field in ("url", "source_page_url"):
                value = item[field]
                if field == "source_page_url" and value == "":
                    continue
                parsed = urlsplit(value) if isinstance(value, str) else None
                if (
                    parsed is None
                    or len(value) > 2048
                    or value != value.strip()
                    or parsed.scheme not in {"http", "https"}
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                ):
                    raise ValueError("daily evidence URL is invalid")
            if not isinstance(item["raw_sha256"], str) or not re.fullmatch(
                r"[0-9a-f]{64}", item["raw_sha256"]
            ):
                raise ValueError("daily evidence SHA is invalid")
            if (
                source_portal_for_observation(
                    evidence["site_id"], item["url"], item["source_page_url"]
                )
                != evidence["portal_key"]
            ):
                raise ValueError("daily evidence belongs to another source portal")
            if name == "observations":
                if (
                    item["kind"] not in {"page", "file"}
                    or not isinstance(item["title"], str)
                    or len(item["title"]) > 500
                ):
                    raise ValueError("daily observation text is invalid")
                if "is_article" in item and (
                    type(item["is_article"]) is not bool or item["kind"] != "page"
                ):
                    raise ValueError("daily article observation is invalid")
            elif (
                item["status"] not in {"new", "existing"}
                or not isinstance(item["content_version_id"], str)
                or not re.fullmatch(r"[1-9][0-9]*", item["content_version_id"])
            ):
                raise ValueError("daily Hub result is invalid")
            identity = (
                item["url"],
                item["raw_sha256"],
                item.get("kind"),
                item.get("request_scope"),
            )
            if identity in seen:
                raise ValueError("daily evidence contains duplicate items")
            seen.add(identity)

    validate_items("observations", 60)
    validate_items("hub_results", 32)
    if not evidence["observations"]:
        raise ValueError("daily digest requires a successful source observation")
    limits = evidence["limits"]
    if (
        not isinstance(limits, dict)
        or set(limits)
        != {
            "request_count",
            "request_limit",
            "budget_exhausted",
            "frontier_remaining",
            "source_error_count",
            "finished",
        }
        or any(
            type(limits[name]) is not int or limits[name] < 0
            for name in (
                "request_count",
                "request_limit",
                "frontier_remaining",
                "source_error_count",
            )
        )
        or not 1
        <= limits["request_limit"]
        <= (60 if evidence["site_id"] == "swiss-association-of-actuaries" else 30)
        or limits["request_count"] < 1
        or limits["request_count"] > limits["request_limit"]
        or any(type(limits[name]) is not bool for name in ("budget_exhausted", "finished"))
    ):
        raise ValueError("daily evidence request limits are invalid")
    encoded = json.dumps(
        evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if len(encoded) > 512_000:
        raise ValueError("daily evidence exceeds its byte limit")
    return captured_at.astimezone(dt.timezone.utc), acquired_on, hashlib.sha256(encoded).hexdigest()


def daily_description(
    evidence: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    directory_description: tuple[str, str] | None = None,
) -> tuple[str, str]:
    observations = {
        (item["url"], _observation_scope(item), item["raw_sha256"], item["kind"]): item
        for run in evidence
        for item in run["observations"]
    }
    current_by_scope: dict[tuple[str, str | None], set[str]] = {}
    previous_by_scope: dict[tuple[str, str | None], str] = {}
    previous_urls: set[str] = set()
    page_urls = {item["url"] for item in observations.values() if item["kind"] == "page"}

    def run_sort_key(run: dict[str, Any]) -> tuple[dt.datetime, str]:
        return (
            dt.datetime.fromisoformat(run["captured_at"].replace("Z", "+00:00")),
            run["run_id"],
        )

    ordered_evidence = sorted(evidence, key=run_sort_key)
    for url, scope, sha, _kind in observations:
        current_by_scope.setdefault((url, scope), set()).add(sha)
    for run in sorted(previous, key=run_sort_key):
        for item in run["observations"]:
            previous_urls.add(item["url"])
            previous_by_scope[(item["url"], _observation_scope(item))] = item["raw_sha256"]
        previous_urls.update(item["url"] for item in run["hub_results"])
    changed_pages = len(
        {
            url
            for (url, scope), shas in current_by_scope.items()
            if url in page_urls
            and scope is not None
            and (
                len(shas) > 1
                or bool(
                    previous_by_scope.get((url, scope)) and shas - {previous_by_scope[(url, scope)]}
                )
            )
        }
    )
    pages = {url for url, _scope, _sha, kind in observations if kind == "page"}
    known_urls = set(previous_urls)
    first_files: dict[str, tuple[dict[str, Any], str | None, bool]] = {}
    for run in ordered_evidence:
        hub = {(item["url"], item["raw_sha256"]): item["status"] for item in run["hub_results"]}
        material_pairs = {
            (item["url"], item["raw_sha256"])
            for item in run["observations"]
            if item["kind"] == "file" or item.get("is_article") is True
        }
        known_urls.update(
            item["url"]
            for item in run["hub_results"]
            if (item["url"], item["raw_sha256"]) not in material_pairs
        )
        for item in run["observations"]:
            if item["kind"] == "file" or item.get("is_article") is True:
                first_files.setdefault(
                    item["url"],
                    (
                        item,
                        hub.get((item["url"], item["raw_sha256"])),
                        item["url"] in known_urls,
                    ),
                )
                known_urls.add(item["url"])
        known_urls.update(item["url"] for item in run["hub_results"])
    new_files = {
        item["url"]: (
            (
                (
                    ""
                    if is_generic_material_label(item["title"])
                    else " ".join(item["title"].split())
                )
                or urlsplit(item["url"]).path.rstrip("/").rsplit("/", 1)[-1]
                or "untitled material"
            )[:120]
        )
        for item, status, previously_known in first_files.values()
        if not previously_known and status != "existing"
    }
    titles = sorted({title for title in new_files.values() if title})
    page_word = "page" if len(pages) == 1 else "pages"
    changed_word = "page" if changed_pages == 1 else "pages"
    file_word = "file" if len(new_files) == 1 else "files"
    zh = f"今天查看了{len(pages)}个网页，其中{changed_pages}个网页有变化；新发现{len(new_files)}份资料。"
    en = f"Today, we checked {len(pages)} web {page_word}; {changed_pages} {changed_word} changed, and found {len(new_files)} new {file_word}."
    if new_files:
        shown_titles = titles[:8]
        listing_zh = "、".join(f"「{title}」" for title in shown_titles)
        listing_en = "; ".join(f"“{title}”" for title in shown_titles)
        remaining = max(0, len(titles) - len(shown_titles))
        if listing_zh:
            if remaining:
                listing_zh += f"，另有{remaining}份资料"
                listing_en += f" and {remaining} more"
            zh += " 新发现的资料：" + listing_zh + "。"
            en += " Newly found: " + listing_en + "."
    if any(
        run["limits"]["source_error_count"] or not run["limits"]["finished"] for run in evidence
    ):
        zh += " 部分内容暂时无法查看；本次汇报只包含已成功查看的内容。"
        en += " Some content could not be checked; this report covers only successful reads."
    if directory_description:
        zh = directory_description[0][:600] + " " + zh
        en = directory_description[1][:600] + " " + en
    return zh, en
