from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Callable, Iterator

CATEGORY_KEYS = (
    "Accounting & Financial Reporting",
    "AI",
    "Climate & ESG",
    "Cyber Risk & Insurance",
    "Data & Analytics",
    "Education / Events",
    "Exam",
    "Fintech & InsurTech",
    "Health",
    "Investment / ALM",
    "Life",
    "LTC / DI / CI",
    "Mortality & Longevity",
    "Operations / Automation",
    "Other",
    "P&C",
    "Pension & Retirement",
    "Pricing",
    "Product Development & Profitability",
    "Professional Practice & Ethics",
    "Regulation & Standards",
    "Reinsurance",
    "Reserving",
    "Risk & Capital",
    "Underwriting & Claims",
)

_FROM_JOINS = """
FROM content_hub.content_versions cv
LEFT JOIN content_hub.article_enrichment_annotations a
       ON a.content_version_id = cv.content_version_id
LEFT JOIN content_hub.bilingual_metadata en
       ON en.content_version_id = cv.content_version_id AND en.language_code = 'en'
LEFT JOIN content_hub.bilingual_metadata zh
       ON zh.content_version_id = cv.content_version_id AND zh.language_code = 'zh'
LEFT JOIN LATERAL (
    SELECT o.legacy_file_id, o.source_snapshot_id, o.availability, o.raw_sha256,
           o.verified_sha256, o.legacy_metadata_json,
           o.legacy_metadata_json::jsonb AS meta
    FROM content_hub.source_file_observations o
    WHERE o.content_version_id = cv.content_version_id
    ORDER BY o.source_snapshot_id, o.legacy_file_id
    LIMIT 1
) obs ON TRUE
LEFT JOIN content_hub.text_variants tv
       ON tv.text_variant_id = a.source_text_variant_id
      AND tv.content_version_id = cv.content_version_id
      AND tv.field_name = 'markdown_content'
"""

_BASE_SELECT = """
SELECT cv.content_version_id, cv.url_value_json, cv.raw_sha256,
       a.source_primary_category, a.categories_json, a.date_facts_json,
       a.date_review_status, a.date_review_reason, a.date_review_unresolved_json,
       a.source_text_variant_id, a.source_markdown_sha256, a.source_signature,
       a.result_sha256, a.recipe, a.run_id, a.annotated_at,
       en.title AS title_en, en.summary AS summary_en, en.category AS category_en,
       en.keywords_json AS keywords_en,
       zh.title AS title_zh, zh.summary AS summary_zh, zh.category AS category_zh,
       zh.keywords_json AS keywords_zh,
       obs.legacy_file_id, obs.source_snapshot_id, obs.availability,
       obs.raw_sha256 AS observation_sha256, obs.verified_sha256,
       obs.legacy_metadata_json,
       (tv.text_variant_id IS NOT NULL AND NOT tv.payload_is_null) AS has_markdown,
        tv.text_variant_id AS markdown_variant_id
"""


def _json_value(value: Any, fallback: Any = None) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return fallback
    return value if value is not None else fallback


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _metadata(value: Any) -> dict[str, Any]:
    parsed = _json_value(value, {})
    return parsed if isinstance(parsed, dict) else {}


def _keywords(value: Any) -> list[str]:
    parsed = _json_value(value, [])
    if not isinstance(parsed, list):
        return []
    return [item.strip() for item in parsed if isinstance(item, str) and item.strip()]


def _quotes(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [quote for item in value for quote in _quotes(item)]
    if isinstance(value, dict):
        return [
            quote
            for key, item in value.items()
            if key.lower() in {"quote", "text", "excerpt"}
            for quote in _quotes(item)
        ]
    return []


def _unresolved_evidence(value: Any) -> list[dict[str, Any]]:
    parsed = _json_value(value, {})
    proposals: list[dict[str, Any]] = []
    date_kinds = {"publication_date", "revision_date", "document_version_date"}
    hidden_values = {
        "value",
        "candidate",
        "normalized_date",
        "normalized_value",
        "proposed_value",
        "suggested_value",
    }

    def visit(item: Any, kind: str = "") -> None:
        if isinstance(item, list):
            for child in item:
                visit(child, kind)
            return
        if not isinstance(item, dict):
            return
        for key in item:
            if key in date_kinds and isinstance(item[key], (dict, list)):
                visit(item[key], key)
        evidence = []
        for key in ("evidence", "quote", "quotes", "excerpt"):
            if key in item:
                evidence.extend(_quotes(item[key]))
        if evidence:
            proposal = {
                "kind": kind or _text(item.get("kind")),
                "status": _text(item.get("status")),
                "reason": _text(item.get("reason")),
                "evidence": list(dict.fromkeys(evidence)),
            }
            if proposal not in proposals:
                proposals.append(proposal)
        for key, child in item.items():
            if (
                key.lower() not in hidden_values
                and key not in date_kinds
                and key not in {"evidence", "quote", "quotes", "excerpt"}
            ):
                visit(child, kind)

    visit(parsed)
    return proposals


def _dict_rows(cursor: Any) -> list[dict[str, Any]]:
    columns = [getattr(column, "name", column[0]) for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _url(value: Any) -> str:
    parsed = _json_value(value)
    return parsed if isinstance(parsed, str) else ""


def _localized_metadata(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "en": {
            "title": _text(row.get("title_en")),
            "summary": _text(row.get("summary_en")),
            "category": _text(row.get("category_en")),
            "keywords": _keywords(row.get("keywords_en")),
        },
        "zh": {
            "title": _text(row.get("title_zh")),
            "summary": _text(row.get("summary_zh")),
            "category": _text(row.get("category_zh")),
            "keywords": _keywords(row.get("keywords_zh")),
        },
    }


def _file_summary(row: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata(row.get("legacy_metadata_json"))
    bilingual = _localized_metadata(row)
    url = _url(row.get("url_value_json"))
    title = bilingual["en"]["title"] or bilingual["zh"]["title"]
    filename = _text(metadata.get("original_filename"))
    if not filename and url:
        filename = url.rsplit("/", 1)[-1] or url
    categories = row.get("categories_json")
    if not isinstance(categories, list):
        categories = []
    return {
        "content_version_id": int(row["content_version_id"]),
        "url": url,
        "title": title or filename or f"Content version {row['content_version_id']}",
        "original_filename": filename,
        "source_site": _text(metadata.get("source_site")),
        "content_type": _text(metadata.get("content_type")),
        "first_seen": "",
        "last_seen": "",
        "bytes": None,
        "deleted_at": None,
        "category": _text(row.get("source_primary_category")) or None,
        "hub_categories": categories,
        "bilingual_metadata": bilingual,
        "summary": bilingual["en"]["summary"] or bilingual["zh"]["summary"] or None,
        "keywords": bilingual["en"]["keywords"] or bilingual["zh"]["keywords"],
        "has_markdown": bool(row.get("has_markdown")),
        "hub_dates": (
            row.get("date_facts_json") if isinstance(row.get("date_facts_json"), dict) else {}
        ),
        "hub_date_review_status": _text(row.get("date_review_status")) or "unannotated",
        "hub_date_review_reason": _text(row.get("date_review_reason")),
    }


class HubReader:
    """Read only queries over the dedicated Content Hub database."""

    def __init__(self, connection_factory: Callable[[], Any]):
        self._connection_factory = connection_factory

    @contextmanager
    def _read_connection(self) -> Iterator[Any]:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
            yield connection
        finally:
            connection.rollback()
            connection.close()

    def sources(self) -> list[str]:
        query = """
        WITH first_observation AS (
            SELECT DISTINCT ON (o.content_version_id)
                   o.content_version_id, o.legacy_metadata_json::jsonb AS meta
            FROM content_hub.source_file_observations o
            ORDER BY o.content_version_id, o.source_snapshot_id, o.legacy_file_id
        )
        SELECT DISTINCT COALESCE(NULLIF(meta->>'source_site', ''), 'Unknown') AS source_site
        FROM content_hub.content_versions cv
        LEFT JOIN first_observation obs ON obs.content_version_id = cv.content_version_id
        WHERE NOT EXISTS (
            SELECT 1 FROM content_hub.excluded_urls x
            WHERE x.url_identity_sha256 = cv.url_identity_sha256
        )
        ORDER BY source_site
        """
        with self._read_connection() as connection, connection.cursor() as cursor:
            cursor.execute(query)
            return [str(row[0]) for row in cursor.fetchall()]

    def categories(self) -> list[dict[str, Any]]:
        query = """
        SELECT item->>'key' AS name, COUNT(DISTINCT cv.content_version_id) AS count
        FROM content_hub.content_versions cv
        JOIN content_hub.article_enrichment_annotations a
          ON a.content_version_id = cv.content_version_id
        CROSS JOIN LATERAL jsonb_array_elements(COALESCE(a.categories_json, '[]'::jsonb)) item
        WHERE NOT EXISTS (
            SELECT 1 FROM content_hub.excluded_urls x
            WHERE x.url_identity_sha256 = cv.url_identity_sha256
        )
        GROUP BY item->>'key'
        """
        with self._read_connection() as connection, connection.cursor() as cursor:
            cursor.execute(query)
            counts = {str(row[0]): int(row[1]) for row in cursor.fetchall() if row[0]}
        return [{"name": key, "count": counts.get(key, 0)} for key in CATEGORY_KEYS]

    def list_files(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        query: str = "",
        source: str = "",
        category: str = "",
        order_by: str = "last_seen",
        order_dir: str = "desc",
    ) -> dict[str, Any]:
        limit = min(max(int(limit), 1), 100)
        offset = min(max(int(offset), 0), 1_000_000)
        clauses = [
            "NOT EXISTS (SELECT 1 FROM content_hub.excluded_urls x "
            "WHERE x.url_identity_sha256 = cv.url_identity_sha256)"
        ]
        params: list[Any] = []
        if query.strip():
            pattern = f"%{query.strip()}%"
            clauses.append(
                "(cv.url_value_json ILIKE %s OR COALESCE(obs.meta->>'original_filename','') ILIKE %s "
                "OR COALESCE(obs.meta->>'source_site','') ILIKE %s "
                "OR COALESCE(en.title,'') ILIKE %s OR COALESCE(zh.title,'') ILIKE %s "
                "OR COALESCE(en.summary,'') ILIKE %s OR COALESCE(zh.summary,'') ILIKE %s "
                "OR COALESCE(a.categories_json::text,'') ILIKE %s)"
            )
            params.extend([pattern] * 8)
        if source:
            clauses.append("COALESCE(NULLIF(obs.meta->>'source_site',''), 'Unknown') = %s")
            params.append(source)
        if category == "__uncategorized__":
            clauses.append(
                "(a.content_version_id IS NULL OR "
                "COALESCE(jsonb_array_length(COALESCE(a.categories_json, '[]'::jsonb)), 0) = 0)"
            )
        elif category:
            clauses.append(
                "EXISTS (SELECT 1 FROM jsonb_array_elements(COALESCE(a.categories_json, '[]'::jsonb)) item "
                "WHERE item->>'key' = %s)"
            )
            params.append(category)
        where_sql = " AND ".join(clauses)
        sort_fields = {
            "title": "COALESCE(en.title, zh.title, obs.meta->>'original_filename', cv.url_value_json)",
            "source_site": "COALESCE(obs.meta->>'source_site', '')",
            "first_seen": "cv.content_version_id",
            "last_seen": "cv.content_version_id",
            "bytes": "cv.content_version_id",
        }
        sort_column = sort_fields.get(order_by, sort_fields["last_seen"])
        sort_direction = "ASC" if order_dir == "asc" else "DESC"
        count_joins = "FROM content_hub.content_versions cv"
        if query.strip():
            count_joins += """
            LEFT JOIN content_hub.article_enrichment_annotations a
                   ON a.content_version_id = cv.content_version_id
            LEFT JOIN content_hub.bilingual_metadata en
                   ON en.content_version_id = cv.content_version_id AND en.language_code = 'en'
            LEFT JOIN content_hub.bilingual_metadata zh
                   ON zh.content_version_id = cv.content_version_id AND zh.language_code = 'zh'
            """
        elif category:
            count_joins += """
            LEFT JOIN content_hub.article_enrichment_annotations a
                   ON a.content_version_id = cv.content_version_id
            """
        if query.strip() or source:
            count_joins += """
            LEFT JOIN LATERAL (
                SELECT o.legacy_metadata_json::jsonb AS meta
                FROM content_hub.source_file_observations o
                WHERE o.content_version_id = cv.content_version_id
                ORDER BY o.source_snapshot_id, o.legacy_file_id
                LIMIT 1
            ) obs ON TRUE
            """
        count_sql = f"SELECT COUNT(DISTINCT cv.content_version_id) {count_joins} WHERE {where_sql}"
        rows_sql = (
            f"{_BASE_SELECT} {_FROM_JOINS} WHERE {where_sql} ORDER BY {sort_column} {sort_direction}, "
            f"cv.content_version_id DESC LIMIT %s OFFSET %s"
        )
        with self._read_connection() as connection, connection.cursor() as cursor:
            cursor.execute(count_sql, params)
            total = int(cursor.fetchone()[0])
            cursor.execute(rows_sql, [*params, limit, offset])
            files = [_file_summary(row) for row in _dict_rows(cursor)]
        return {"files": files, "total": total, "limit": limit, "offset": offset}

    def file_detail(self, content_version_id: int) -> dict[str, Any] | None:
        select = _BASE_SELECT.replace(
            "SELECT cv.content_version_id,",
            "SELECT cv.content_version_id, tv.payload_value_json AS markdown_json,",
        )
        query = select + _FROM_JOINS + """
        WHERE cv.content_version_id = %s
          AND NOT EXISTS (
              SELECT 1 FROM content_hub.excluded_urls x
              WHERE x.url_identity_sha256 = cv.url_identity_sha256
          )
        """
        with self._read_connection() as connection, connection.cursor() as cursor:
            cursor.execute(query, (content_version_id,))
            rows = _dict_rows(cursor)
        if not rows:
            return None
        row = rows[0]
        file_data = _file_summary(row)
        markdown = _json_value(row.get("markdown_json")) if row.get("has_markdown") else None
        file_data.update(
            {
                "raw_sha256": _text(row.get("raw_sha256")),
                "source_record": {
                    "legacy_file_id": _text(row.get("legacy_file_id")),
                    "source_snapshot_id": row.get("source_snapshot_id"),
                    "availability": _text(row.get("availability")),
                    "raw_sha256": _text(row.get("observation_sha256")),
                    "verified_sha256": _text(row.get("verified_sha256")),
                },
                "annotation": {
                    "source_primary_category": _text(row.get("source_primary_category")),
                    "source_text_variant_id": row.get("source_text_variant_id"),
                    "source_markdown_sha256": _text(row.get("source_markdown_sha256")),
                    "source_signature": _text(row.get("source_signature")),
                    "result_sha256": _text(row.get("result_sha256")),
                    "recipe": _text(row.get("recipe")),
                    "run_id": _text(row.get("run_id")),
                    "annotated_at": (
                        row.get("annotated_at").isoformat() if row.get("annotated_at") else None
                    ),
                    "date_review_unresolved": _unresolved_evidence(
                        row.get("date_review_unresolved_json")
                    ),
                },
                "markdown": markdown if isinstance(markdown, str) and markdown.strip() else None,
            }
        )
        return file_data
