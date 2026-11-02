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
                (fields, fields | {"request_scope"}) if name == "observations" else (fields,)
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
    for url, scope, sha, _kind in observations:
        current_by_scope.setdefault((url, scope), set()).add(sha)
    for run in sorted(
        previous,
        key=lambda run: (
            dt.datetime.fromisoformat(run["captured_at"].replace("Z", "+00:00")),
            run["run_id"],
        ),
    ):
        for item in run["observations"]:
            previous_urls.add(item["url"])
            previous_by_scope[(item["url"], _observation_scope(item))] = item["raw_sha256"]
    newly_observed = len({url for url, _scope in current_by_scope} - previous_urls)
    changed = len(
        {
            url
            for (url, scope), shas in current_by_scope.items()
            if scope is not None
            and (
                len(shas) > 1
                or bool(
                    previous_by_scope.get((url, scope)) and shas - {previous_by_scope[(url, scope)]}
                )
            )
        }
    )
    pages = sum(kind == "page" for _url, _scope, _sha, kind in observations)
    files = sum(kind == "file" for _url, _scope, _sha, kind in observations)
    observed_files = {(url, sha) for url, _scope, sha, _kind in observations}
    hub: dict[tuple[str, str], str] = {}
    for run in evidence:
        for item in run["hub_results"]:
            key = (item["url"], item["raw_sha256"])
            if hub.get(key) != "new":
                hub[key] = item["status"]
    imported = sum(status == "new" and key in observed_files for key, status in hub.items())
    backlog = sum(status == "new" and key not in observed_files for key, status in hub.items())
    reused = sum(status == "existing" for status in hub.values())
    zh = f"本日实际读取{pages}个页面/接口响应、{files}份文件；首次纳入每日观察记录的网址{newly_observed}个；在可比较的请求范围内，{changed}个网址的原始响应内容有变化。"
    en = f"Today's observed reads cover {pages} page/API responses and {files} files; {newly_observed} URLs were first recorded in daily observation history, and raw response content differed at {changed} URLs within comparable request scopes."
    titles = sorted(
        {item["title"].strip() for item in observations.values() if item["title"].strip()}
    )
    if titles:
        title = " ".join(titles[0].split())[:120]
        zh += f" 本次读到的资料例如「{title}」。"
        en += f" An observed example is “{title}”."
    zh += f" Hub首次入库：本日读到的内容{imported}份、历史积压{backlog}份；复用既有版本{reused}份。这些数量不代表原站今日发布。"
    en += f" Hub first imports: {imported} observed today and {backlog} from historical backlog; {reused} existing versions reused. These counts do not establish a site publication date."
    requests = sum(run["limits"]["request_count"] for run in evidence)
    zh += f" 仅覆盖本日{len(evidence)}次有界采集（{requests}次请求），不代表全站扫描，不据此推断移除或全站无变化。"
    en += f" Coverage is limited to {len(evidence)} bounded collection attempts today ({requests} requests); it is not a full-site scan and cannot establish removals or no change across the site."
    if any(run["limits"]["budget_exhausted"] for run in evidence):
        zh += " 访问预算用完，下次继续。"
        en += " The request budget was exhausted; continue next time."
    if any(
        run["limits"]["source_error_count"] or not run["limits"]["finished"] for run in evidence
    ):
        zh += " 部分读取失败或运行中断；摘要只计已验证的观察。"
        en += " Some reads failed or an attempt was interrupted; only verified observations are counted."
    if directory_description:
        zh = "完整目录快照（仅限该目录范围）：" + directory_description[0][:600] + " " + zh
        en = (
            "Complete directory snapshot (that directory's scope only): "
            + directory_description[1][:600]
            + " "
            + en
        )
    return zh, en
