from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from ai_actuarial.api.hub_read import HubReader, _file_summary, _unresolved_evidence
from ai_actuarial.api.local_hub import _loopback_host, create_app


class _Column:
    def __init__(self, name: str):
        self.name = name

    def __getitem__(self, index: int) -> str:
        return self.name


class _Cursor:
    def __init__(self, result: list[tuple[Any, ...]] | None = None):
        self.result = result or []
        self.description: list[_Column] = []
        self.statements: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def execute(self, statement: str, params: tuple[Any, ...] = ()) -> None:
        self.statements.append((statement, params))
        if "SET TRANSACTION READ ONLY" in statement:
            return
        if "COUNT(DISTINCT cv.content_version_id)" in statement:
            self.result = [(1,)]
            return
        if "SELECT cv.content_version_id" in statement:
            selected = dict(_ROW)
            if "AS markdown_json" not in statement:
                selected.pop("markdown_json")
                selected.pop("markdown_payload_sha256")
            self.description = [_Column(name) for name in selected]
            self.result = [tuple(selected.values())]
            return
        if "SELECT DISTINCT COALESCE" in statement:
            self.result = [("Sample Society",)]
            return
        if "SELECT item->>'key'" in statement:
            self.result = [("AI", 1)]
            return

    def fetchone(self) -> tuple[Any, ...]:
        return self.result[0]

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.result


_ROW = {
    "content_version_id": 135,
    "url_value_json": json.dumps("https://example.org/report"),
    "raw_sha256": "a" * 64,
    "source_primary_category": "AI",
    "categories_json": [
        {"key": "AI", "evidence": ["Source says AI"]},
        {"key": "Risk & Capital", "evidence": []},
    ],
    "date_facts_json": {"publication_date": {"value": "2025", "precision": "year"}},
    "date_review_status": "candidate_limit_gap",
    "date_review_reason": "The source date only identifies a year.",
    "date_review_unresolved_json": {},
    "source_text_variant_id": 991,
    "source_markdown_sha256": "b" * 64,
    "source_signature": "c" * 64,
    "result_sha256": "d" * 64,
    "recipe": "recipe-v1",
    "run_id": "run-1",
    "annotated_at": None,
    "title_en": "AI report",
    "summary_en": "An English summary.",
    "category_en": "AI",
    "keywords_en": ["AI", "risk"],
    "title_zh": "人工智能报告",
    "summary_zh": "中文摘要。",
    "category_zh": "AI",
    "keywords_zh": ["AI", "风险"],
    "legacy_file_id": "original-1",
    "source_snapshot_id": 8,
    "availability": "present",
    "observation_sha256": "a" * 64,
    "verified_sha256": "a" * 64,
    "legacy_metadata_json": json.dumps(
        {"source_site": "Sample Society", "original_filename": "report.md"}
    ),
    "has_markdown": True,
    "markdown_variant_id": 991,
    "markdown_json": json.dumps("# Source\n\nOriginal\u0001 text"),
    "markdown_payload_sha256": "e" * 64,
}


class _Connection:
    def __init__(self):
        self.cursor_obj = _Cursor()
        self.rolled_back = False
        self.closed = False

    def cursor(self, **_: Any) -> _Cursor:
        return self.cursor_obj

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def test_viewer_import_does_not_load_product_app_or_task_runtime() -> None:
    code = (
        "import sys; import ai_actuarial.api.local_hub; "
        "assert 'ai_actuarial.api.app' not in sys.modules; "
        "assert 'ai_actuarial.task_runtime' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True, cwd=Path(__file__).parents[1])


def test_existing_api_package_exports_remain_available() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from ai_actuarial.api import create_app, run_server; "
            "assert callable(create_app) and callable(run_server)",
        ],
        check=True,
        cwd=Path(__file__).parents[1],
    )


def test_sources_use_one_deterministic_observation_scan() -> None:
    connection = _Connection()
    sources = HubReader(lambda: connection).sources()
    query = connection.cursor_obj.statements[-1][0]

    assert sources == ["Sample Society"]
    assert "DISTINCT ON (o.content_version_id)" in query
    assert "ORDER BY o.content_version_id, o.source_snapshot_id, o.legacy_file_id" in query
    assert "LEFT JOIN LATERAL" not in query


def test_readonly_repository_keeps_version_identity_dates_and_bound_markdown() -> None:
    connection = _Connection()
    reader = HubReader(lambda: connection)
    result = reader.list_files(query="report", category="AI", order_by="title", order_dir="asc")

    assert result["total"] == 1
    file = result["files"][0]
    assert file["content_version_id"] == 135
    assert file["url"] == "https://example.org/report"
    assert [item["key"] for item in file["hub_categories"]] == ["AI", "Risk & Capital"]
    assert file["hub_dates"]["publication_date"]["value"] == "2025"
    assert file["hub_dates"]["publication_date"]["precision"] == "year"
    list_query, params = connection.cursor_obj.statements[-1]
    assert "NOT EXISTS" in list_query and "content_hub.excluded_urls" in list_query
    assert "jsonb_array_elements" in list_query
    assert "ORDER BY COALESCE(en.title" in list_query
    assert "LIMIT %s OFFSET %s" in list_query
    assert "payload_value_json" not in list_query
    count_query = connection.cursor_obj.statements[1][0]
    assert "source_file_observations" in count_query
    default_connection = _Connection()
    HubReader(lambda: default_connection).list_files()
    default_count_query = default_connection.cursor_obj.statements[1][0]
    assert "source_file_observations" not in default_count_query
    assert "AI" in params
    assert connection.cursor_obj.statements[0][0] == "SET TRANSACTION READ ONLY"
    assert connection.rolled_back and connection.closed

    detail_connection = _Connection()
    detail = HubReader(lambda: detail_connection).file_detail(135)
    assert detail is not None
    assert detail["markdown"] == "# Source\n\nOriginal\x01 text"
    assert detail["annotation"]["source_text_variant_id"] == 991
    detail_query = detail_connection.cursor_obj.statements[-1][0]
    assert "tv.payload_value_json AS markdown_json" in detail_query
    assert "tv.content_version_id = cv.content_version_id" in detail_query
    assert "tv.field_name = 'markdown_content'" in detail_query


def test_missing_annotation_has_no_fake_date_and_unresolved_values_are_not_returned() -> None:
    row = dict(_ROW)
    row.update(
        source_primary_category=None,
        categories_json=None,
        date_facts_json=None,
        date_review_status=None,
        source_text_variant_id=None,
        has_markdown=False,
    )
    file = _file_summary(row)
    assert file["hub_categories"] == []
    assert file["hub_dates"] == {}
    assert file["hub_date_review_status"] == "unannotated"
    assert file["has_markdown"] is False

    unresolved = _unresolved_evidence(
        {
            "publication_date": {
                "value": "2025-01-01",
                "status": "unresolved",
                "reason": "The source identifies only a year.",
                "evidence": ["Published in 2025"],
            }
        }
    )
    assert unresolved == [
        {
            "kind": "publication_date",
            "status": "unresolved",
            "reason": "The source identifies only a year.",
            "evidence": ["Published in 2025"],
        }
    ]
    assert "value" not in unresolved[0]


def test_viewer_api_has_only_get_routes_and_rejects_non_loopback_binding() -> None:
    app = create_app(connection_factory=lambda: _Connection())
    app.state.hub_reader = type(
        "ViewerFixture",
        (),
        {
            "sources": lambda self: ["Sample Society"],
            "categories": lambda self: [{"name": "AI", "count": 1}],
            "list_files": lambda self, **kwargs: {
                "files": [],
                "total": 0,
                "limit": kwargs["limit"],
                "offset": kwargs["offset"],
            },
            "file_detail": lambda self, content_version_id: None,
        },
    )()
    assert all(route.methods == {"GET"} for route in app.routes if getattr(route, "methods", None))

    with TestClient(app) as client:
        response = client.get("/api/auth/me")
        assert response.json()["data"]["read_only"] is True
        assert response.json()["data"]["permissions"] == ["files.read"]
        assert client.get("/api/hub/sources").json() == {"sources": ["Sample Society"]}
        assert client.post("/api/hub/files").status_code == 405

    assert _loopback_host("127.0.0.1") == "127.0.0.1"
    try:
        _loopback_host("0.0.0.0")
    except Exception as exc:
        assert "loopback" in str(exc)
    else:
        raise AssertionError("non-loopback binding was accepted")
