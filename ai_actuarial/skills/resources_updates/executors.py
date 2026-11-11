import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from ai_actuarial.agent_runtime import ToolResult
from ai_actuarial.assistant.document_research import SelectedTarget
from ai_actuarial.skills.document_research.executors import find_documents as _find_documents
from ai_actuarial.source_portals import SOURCE_PORTAL_URLS


def _id(value):
    return "resources_updates:" + hashlib.sha256(str(value).encode()).hexdigest()[:24]


def sources(facade, _args):
    options = facade.storage.get_source_options(exclude_urls=SOURCE_PORTAL_URLS)
    items = [
        {key: row.get(key) for key in ("source_key", "source_name_en", "source_name_zh", "count")}
        for row in options[:12]
    ]
    return ToolResult(
        "ok",
        {
            "sources": items,
            "total": len(options),
            "truncated": len(options) > len(items),
            "action": "/source-portals",
        },
        (_id("sources" + str(items)),),
    )


def _first_seen_window(args):
    if args.get("window_days") != 7:
        return {}
    now = datetime.now(timezone.utc)
    return {
        "first_seen_from": (now - timedelta(days=7)).isoformat(),
        "first_seen_before": now.isoformat(),
    }


def recent(facade, args):
    source = args.get("source") or ""
    window = _first_seen_window(args)
    rows, total = facade.storage.query_files_with_catalog(
        limit=3,
        order_by="first_seen",
        order_dir="desc",
        source=source,
        exclude_urls=SOURCE_PORTAL_URLS,
        **window,
    )
    items = [
        {
            "title": row.get("title"),
            "source": row.get("source_name_en") or row.get("source_site"),
            "source_url": row.get("url"),
            "published_time": row.get("published_time"),
            "first_seen": row.get("first_seen"),
            "link": "/file-detail?" + urlencode({"url": row["url"]}),
        }
        for row in rows
    ]
    if window:
        names = facade.storage.get_source_options(
            source=source, exclude_urls=SOURCE_PORTAL_URLS, **window
        )
        window["source_names"] = [(row["source_name_zh"], row["source_name_en"]) for row in names]
    return ToolResult(
        "ok",
        {
            "files": items,
            "total": total,
            "source_filter": source,
            "date_meaning": "first_seen is system first collection; content revisions are not recorded",
            "action": "/database",
            **window,
        },
        (_id("recent" + source + str(total) + str(items) + (str(window) if window else "")),),
    )


def catalog_search(facade, args):
    window = _first_seen_window(args)
    rows, total = facade.storage.query_files_with_catalog(
        query=args["query"], limit=3, exclude_urls=SOURCE_PORTAL_URLS, **window
    )
    items = [
        {
            "title": row.get("title"),
            "source": row.get("source_name_en") or row.get("source_site"),
            "summary": str(row.get("summary") or "")[:250],
            "source_url": row.get("url"),
            "publication_date": row.get("published_time"),
            "system_first_seen": row.get("first_seen"),
            "link": "/file-detail?" + urlencode({"url": row["url"]}),
        }
        for row in rows
    ]
    return ToolResult(
        "ok" if items or window else "not_found",
        {
            "files": items,
            "total": total,
            "action": "/database",
            "note": "Catalog metadata is not body evidence; content revision history is not recorded.",
            **window,
        },
        (_id("catalog" + str(items) + (str(window) if window else "")),) if items or window else (),
    )


def weekly(facade, _args):
    snapshot = facade.storage.get_latest_weekly_snapshot(now=datetime.now(timezone.utc).isoformat())
    if snapshot is None:
        return ToolResult(
            "ok",
            {
                "snapshot": None,
                "message": "No complete published weekly snapshot is available yet.",
                "action": "/weekly",
            },
            (_id("weekly:none"),),
        )
    rows, total = facade.storage.list_weekly_snapshot_files(snapshot_id=snapshot["id"], limit=5)
    items = [
        {
            "title": row.get("title"),
            "source_url": row.get("url"),
            "first_seen": row.get("first_seen"),
        }
        for row in rows
    ]
    return ToolResult(
        "ok",
        {
            "snapshot": {
                key: snapshot.get(key) for key in ("id", "period_start", "period_end", "file_count")
            },
            "files": items,
            "total": total,
            "message": (
                "No newly first-collected files in this published period."
                if total == 0
                else "New means first_seen during this period; content changes are not tracked."
            ),
            "action": "/weekly",
        },
        (_id("weekly" + str(snapshot["id"])),),
    )


def find_documents(facade, args):
    return _find_documents(facade, args)


def document_dates(facade, args):
    target = SelectedTarget(kb_id=args["kb_id"], file_id=args["file_id"])
    document = facade._document(target)
    if document is None:
        return ToolResult("not_found")
    row = facade.storage._conn.execute(
        "SELECT added_at FROM rag_kb_files WHERE kb_id = ? AND file_url = ?",
        (target.kb_id, target.file_id),
    ).fetchone()
    if row is None:
        return ToolResult("not_found")
    return ToolResult(
        "ok",
        {
            "document": document.model_dump(),
            "publication_date": document.publication_date,
            "system_first_seen": document.system_first_seen,
            "kb_added_at": row[0] if row else None,
            "content_revision": "not recorded",
        },
        (_id("dates" + target.kb_id + target.file_id),),
    )


def grounded_answer(tool_id, data, locale):
    zh = locale.startswith("zh")
    if tool_id == "resources_updates.sources":
        lines = [
            (
                f"当前有 {data.get('total', 0)} 个来源机构。"
                if zh
                else f"{data.get('total', 0)} current source organizations."
            )
        ]
        lines.extend(
            (
                f"- {row.get('source_name_zh') or row.get('source_name_en')}: {row.get('count', 0)} 份资料"
                if zh
                else f"- {row.get('source_name_en') or row.get('source_name_zh')}: {row.get('count', 0)} files"
            )
            for row in data.get("sources", [])
        )
        if data.get("truncated"):
            shown = len(data.get("sources", []))
            total = data.get("total", shown)
            action = data.get("action", "/source-portals")
            lines.append(
                f"仅列出 {shown}/{total} 个来源；查看完整[来源门户]({action})。"
                if zh
                else f"Showing {shown} of {total} sources; open [Source Portals]({action}) for the complete list."
            )
        return "\n".join(lines)
    if tool_id in {"resources_updates.recent", "resources_updates.catalog_search"}:
        recent = tool_id.endswith("recent")
        source = data.get("source_filter") if recent else None
        lines = [
            (
                (
                    f"按系统首次收录时间找到 {data.get('total', 0)} 份资料。"
                    if zh
                    else f"{data.get('total', 0)} files by system first collection date."
                )
                if recent
                else (
                    f"目录检索找到 {data.get('total', 0)} 份资料。"
                    if zh
                    else f"{data.get('total', 0)} catalog matches."
                )
            )
        ]
        if source:
            lines[0] += f"（{source}）" if zh else f" Source: {source}."
        if (start := data.get("first_seen_from")) and (end := data.get("first_seen_before")):
            lines.append(
                f"过去七天的系统首次收录时间（UTC）：自 {start}（含）至 {end}（不含）。"
                if zh
                else f"System first collection in the past seven days (UTC): "
                f"from {start} (inclusive) to {end} (exclusive)."
            )
        if source_names := data.get("source_names"):
            names = ("、" if zh else ", ").join(name[0 if zh else 1] for name in source_names)
            lines.append(
                f"这段时间收录的来源机构：{names}。" if zh else f"Source organizations: {names}."
            )
            shown = len(data.get("files", []))
            if shown < data["total"]:
                lines.append(
                    f"以下列出其中 {shown} 份资料。" if zh else f"Showing {shown} sample files."
                )
        for row in data.get("files", []):
            lines.append(
                f"- {row.get('title') or 'Untitled'} — {row.get('source') or 'Unknown source'}"
            )
            if row.get("source_url"):
                lines.append(f"  {row['source_url']}")
            if row.get("publication_date") or row.get("published_time"):
                lines.append(
                    f"  {'发布日期' if zh else 'Publication date'}: {row.get('publication_date') or row.get('published_time')}"
                )
            if row.get("system_first_seen") or row.get("first_seen"):
                lines.append(
                    f"  {'系统首次收录' if zh else 'System first collected'}: {row.get('system_first_seen') or row.get('first_seen')}"
                )
            if not recent and row.get("summary"):
                lines.append(f"  {'目录摘要' if zh else 'Catalog summary'}: {row['summary']}")
        lines.append(
            "系统首次收录不代表内容修订；修订记录未保存。"
            if zh
            else "First collection is not a content revision; revision history is not recorded."
        )
        if not recent:
            lines.append(
                "目录摘要不能证明正文内容。" if zh else "Catalog summaries are not body evidence."
            )
        return "\n".join(lines)
    if tool_id == "resources_updates.weekly":
        snapshot = data.get("snapshot")
        if snapshot is None:
            return (
                "目前没有完整已发布的周报快照。"
                if zh
                else "No complete published weekly snapshot is available yet."
            )
        if data.get("total") == 0:
            return (
                "最近一期已发布周报按系统首次收录时间统计，没有新增资料。"
                if zh
                else "The latest published weekly period has no newly first-collected files."
            )
        lines = [
            (
                f"已发布周报 {snapshot.get('period_start')} 至 {snapshot.get('period_end')}：{data.get('total', 0)} 份首次收录资料。"
                if zh
                else f"Published weekly period {snapshot.get('period_start')} to {snapshot.get('period_end')}: {data.get('total', 0)} newly first-collected files."
            )
        ]
        lines.extend(
            f"- {row.get('title') or 'Untitled'} ({row.get('first_seen') or 'date unavailable'})"
            for row in data.get("files", [])
        )
        lines.append("内容修订记录未保存。" if zh else "Content revision history is not recorded.")
        return "\n".join(lines)
    if tool_id == "resources_updates.document_dates":
        document = data.get("document") or {}
        return "\n".join(
            [
                str(document.get("title") or "Document"),
                f"{'发布日期' if zh else 'Publication date'}: {data.get('publication_date') or 'unknown'}",
                f"{'系统首次收录' if zh else 'System first collected'}: {data.get('system_first_seen') or 'unknown'}",
                f"{'知识库收录' if zh else 'Added to knowledge base'}: {data.get('kb_added_at') or 'unknown'}",
                "内容修订记录未保存。" if zh else "Content revision history is not recorded.",
            ]
        )
    return None
