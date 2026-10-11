"""Tests for ready_data_builder L0 MVP."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Import under test
import ai_actuarial.agentic_rag.ready_data_builder as builder
from ai_actuarial.storage import Storage
from tests.postgres_helpers import postgres_url_for_path

_PROFILE_NAME = "ready-data-builder-test"


def _profile_id(storage: Storage) -> str:
    return str(
        storage._conn.execute(
            "SELECT profile_id FROM chunk_profiles WHERE name = ?", (_PROFILE_NAME,)
        ).fetchone()[0]
    )


def _seed_file_and_catalog(
    storage: Storage,
    url: str,
    *,
    title: str,
    source_site: str = "CBIRC",
    status: str = "ok",
    summary: str = "偿付能力监管规则摘要",
    category: str = "regulation",
    keywords: list[str] | None = None,
) -> None:
    storage.insert_file(
        url=url,
        sha256=f"sha-{url}",
        title=title,
        source_site=source_site,
        source_page_url="https://example.com",
        original_filename="rule.pdf",
        local_path="",
        bytes=0,
        content_type="application/pdf",
        published_time="2024-01-01",
    )
    storage.upsert_catalog_item(
        item={
            "url": url,
            "sha256": f"sha-{url}",
            "keywords": keywords or ["偿二代", "偿付能力", "寿险"],
            "summary": summary,
            "category": category,
        },
        pipeline_version="test-v1",
        status=status,
    )


def _seed_chunk_set(
    storage: Storage,
    url: str,
    chunks: list[dict[str, object]],
    *,
    markdown_hash: str,
    status: str = "building",
    profile_id: str | None = None,
) -> str:
    chunk_set = storage.get_or_create_file_chunk_set(
        file_url=url,
        profile_id=profile_id or _profile_id(storage),
        markdown_hash=markdown_hash,
        status=status,
    )
    if chunks:
        storage.replace_global_chunks(
            chunk_set_id=chunk_set["chunk_set_id"], chunks=chunks, overwrite=True
        )
    return str(chunk_set["chunk_set_id"])


def _seed_kb(storage: Storage, kb_id: str) -> None:
    profile_id = _profile_id(storage)
    storage._conn.execute(
        """
        INSERT INTO rag_knowledge_bases (
            kb_id, name, chunk_profile_id, embedding_model,
            chunk_size, chunk_overlap, index_type, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            kb_id,
            kb_id,
            profile_id,
            "test-embedding",
            800,
            100,
            "Flat",
            "2026-08-19T00:00:00+00:00",
            "2026-08-19T00:00:00+00:00",
        ),
    )


def _add_kb_member(storage: Storage, kb_id: str, file_url: str) -> None:
    storage._conn.execute(
        "INSERT INTO rag_kb_files (kb_id, file_url, added_at) VALUES (?, ?, ?)",
        (kb_id, file_url, "2026-08-19T00:00:00+00:00"),
    )


def _add_kb_binding(storage: Storage, kb_id: str, file_url: str, chunk_set_id: str) -> None:
    storage._conn.execute(
        """
        INSERT INTO kb_chunk_bindings (kb_id, file_url, chunk_set_id, bound_at)
        VALUES (?, ?, ?, ?)
        """,
        (kb_id, file_url, chunk_set_id, "2026-08-19T00:00:00+00:00"),
    )


@pytest.fixture
def test_db_path(tmp_path):
    """Create isolated PostgreSQL catalog and chunk data."""
    database_url = postgres_url_for_path(tmp_path / "test.db")
    storage = Storage(database_url)
    try:
        storage.create_chunk_profile(
            name=_PROFILE_NAME, chunk_size=800, chunk_overlap=100, upsert=True
        )
        url = "https://example.com/rule1"
        _seed_file_and_catalog(storage, url, title="偿付能力监管规则第3号")
        _seed_chunk_set(
            storage,
            url,
            [
                {
                    "chunk_id": "c1",
                    "chunk_index": 0,
                    "content": "第一章 总则，第一条 为规范...",
                    "token_count": 50,
                    "section_hierarchy": "第一章 总则 > 第一条",
                },
                {
                    "chunk_id": "c2",
                    "chunk_index": 1,
                    "content": "第二章 负债评估，第十九条...",
                    "token_count": 80,
                    "section_hierarchy": "第二章 负债评估 > 第十九条",
                },
            ],
            markdown_hash="fixture-rule1",
        )
    finally:
        storage.close()
    return database_url


def test_build_l0_basic(test_db_path, tmp_path):
    """Build L0 from test DB and verify all artifacts."""
    manifest = builder.build_l0(
        db_path=test_db_path,
        output_dir=str(tmp_path),
        profile="general",
    )

    assert manifest["doc_count"] == 1
    assert manifest["section_count"] == 2
    assert manifest["profile"] == "general"
    assert manifest["source_version_kind"] == "catalog_chunks_snapshot"
    assert manifest["source_version_id"].startswith("rdsnap_")

    # Check doc_catalog.jsonl
    catalog_path = tmp_path / "doc_catalog.jsonl"
    assert catalog_path.exists()
    entries = []
    with open(catalog_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    assert len(entries) == 1
    doc = entries[0]
    assert doc["doc_id"] == "https://example.com/rule1"
    assert doc["title"] == "偿付能力监管规则第3号"
    assert doc["category"] == "regulation"
    assert "偿二代" in doc["keywords"]
    assert "第一章 总则" in doc["headings"]
    assert doc["rag_chunk_count"] == 2

    # Check sections.jsonl
    sec_path = tmp_path / "sections.jsonl"
    assert sec_path.exists()
    sections = []
    with open(sec_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                sections.append(json.loads(line))

    assert len(sections) == 2
    assert all(s["doc_id"] == "https://example.com/rule1" for s in sections)
    assert sections[0]["token_count"] == 50
    assert sections[1]["token_count"] == 80

    # Check manifest.json
    manifest_path = tmp_path / "ready_data_manifest.json"
    assert manifest_path.exists()
    with open(manifest_path, "r", encoding="utf-8") as f:
        m = json.load(f)
    assert "built_at" in m
    assert m["artifact_files"] == [
        "doc_catalog.jsonl",
        "sections.jsonl",
        "ready_data_manifest.json",
    ]
    assert m["source_version_kind"] == manifest["source_version_kind"]
    assert m["source_version_id"] == manifest["source_version_id"]


def test_build_l0_source_version_is_stable_and_tracks_consumed_inputs(test_db_path, tmp_path):
    first = builder.build_l0(
        db_path=test_db_path,
        output_dir=str(tmp_path / "first"),
        profile="general",
    )
    same = builder.build_l0(
        db_path=test_db_path,
        output_dir=str(tmp_path / "same"),
        profile="general",
    )
    assert same["source_version_id"] == first["source_version_id"]

    conn = Storage(test_db_path)
    conn._conn.execute(
        "UPDATE global_chunks SET content = ? WHERE chunk_index = ?",
        ("Changed source chunk", 0),
    )
    conn._conn.commit()
    conn.close()
    changed = builder.build_l0(
        db_path=test_db_path,
        output_dir=str(tmp_path / "changed"),
        profile="general",
    )
    assert changed["source_version_id"] != first["source_version_id"]


def test_build_l0_kb_scope_requires_persisted_composition(test_db_path, tmp_path):
    storage = Storage(test_db_path)
    try:
        _seed_kb(storage, "kb-ready")
        _add_kb_member(storage, "kb-ready", "https://example.com/rule1")
    finally:
        storage.close()

    with pytest.raises(ValueError, match="one binding for every KB member"):
        builder.build_l0(
            db_path=test_db_path,
            output_dir=str(tmp_path / "without-index"),
            profile="general",
            kb_id="kb-ready",
        )


def test_build_l0_closes_database_connection_when_build_fails(test_db_path, monkeypatch):
    real_connect = builder.PostgresConnection
    tracked = []

    class TrackingConnection:
        def __init__(self, *args, **kwargs):
            self.inner = real_connect(*args, **kwargs)
            self.closed = False

        def close(self):
            self.closed = True
            self.inner.close()

        def __getattr__(self, name: str):
            return getattr(self.inner, name)

    def tracked_connect(*args, **kwargs):
        connection = TrackingConnection(*args, **kwargs)
        tracked.append(connection)
        return connection

    monkeypatch.setattr(builder, "PostgresConnection", tracked_connect)
    with pytest.raises(ValueError, match="Unknown profile"):
        builder.build_l0(db_path=test_db_path, profile="unknown")

    assert len(tracked) == 1
    assert tracked[0].closed is True


def test_build_regulation_profile_emits_l1_alias_and_relation_artifacts(test_db_path, tmp_path):
    """Build L1 regulation artifacts without changing the L0 catalog contract."""
    manifest = builder.build_l0(
        db_path=test_db_path,
        output_dir=str(tmp_path),
        profile="regulation",
    )

    assert manifest["profile"] == "regulation"
    assert manifest["doc_count"] == 1
    assert manifest["section_count"] == 2
    assert manifest["artifact_files"] == [
        "doc_catalog.jsonl",
        "title_aliases.jsonl",
        "doc_summaries.jsonl",
        "sections_structured.jsonl",
        "relations_graph.json",
        "ready_data_manifest.json",
    ]

    catalog = [
        json.loads(line)
        for line in (tmp_path / "doc_catalog.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert catalog[0]["title"] == "偿付能力监管规则第3号"
    assert "headings" in catalog[0]

    aliases = [
        json.loads(line)
        for line in (tmp_path / "title_aliases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert aliases[0]["doc_id"] == "https://example.com/rule1"
    assert "偿付能力监管规则第3号" in aliases[0]["aliases"]
    assert "3" in aliases[0]["identifiers"]
    assert aliases[0]["document_numbers"] == ["3"]
    assert aliases[0]["rule_numbers"] == []

    sections = [
        json.loads(line)
        for line in (tmp_path / "sections_structured.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert sections[0]["heading"] == "第一条"
    assert sections[0]["document_aliases"] == aliases[0]["aliases"]

    graph = json.loads((tmp_path / "relations_graph.json").read_text(encoding="utf-8"))
    relation_types = {row["relation_type"] for row in graph["relations"]}
    assert {"alias_of", "document_has_section"}.issubset(relation_types)

    validation = builder.validate(str(tmp_path))
    assert validation["valid"] is True


def test_build_formula_profile_emits_l2_formula_table_and_term_artifacts(test_db_path, tmp_path):
    """Build L2 formula artifacts from deterministic section text."""
    conn = Storage(test_db_path)
    conn._conn.execute(
        """
        UPDATE global_chunks
        SET content = ?, section_hierarchy = ?
        WHERE chunk_index = ?
        """,
        (
            "\n".join(
                [
                    "Net Premium = PV Benefits / PV Premiums.",
                    "| Term | Description |",
                    "| q_x | mortality rate |",
                    "| v | discount factor |",
                    "The reserve calculation uses mortality rate and discount rate assumptions.",
                ]
            ),
            "Actuarial formulas > Net premium",
            1,
        ),
    )
    conn._conn.commit()
    conn.close()

    manifest = builder.build_l0(
        db_path=test_db_path,
        output_dir=str(tmp_path),
        profile="formula",
    )

    assert manifest["profile"] == "formula"
    assert manifest["artifact_files"] == [
        "doc_catalog.jsonl",
        "title_aliases.jsonl",
        "doc_summaries.jsonl",
        "sections_structured.jsonl",
        "formula_cards.jsonl",
        "tables_structured.jsonl",
        "calculation_terms.jsonl",
        "relations_graph.json",
        "ready_data_manifest.json",
    ]
    assert manifest["formula_card_count"] == 1
    assert manifest["table_count"] == 1
    assert manifest["calculation_term_count"] >= 3

    formula_cards = [
        json.loads(line)
        for line in (tmp_path / "formula_cards.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert formula_cards[0]["doc_id"] == "https://example.com/rule1"
    assert formula_cards[0]["heading"] == "Net premium"
    assert formula_cards[0]["formula_text"] == "Net Premium = PV Benefits / PV Premiums."
    assert "Net Premium" in formula_cards[0]["terms"]

    tables = [
        json.loads(line)
        for line in (tmp_path / "tables_structured.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert tables[0]["headers"] == ["Term", "Description"]
    assert tables[0]["rows"][0] == {"Term": "q_x", "Description": "mortality rate"}

    terms = [
        json.loads(line)
        for line in (tmp_path / "calculation_terms.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    term_names = {row["term"] for row in terms}
    assert {"Net Premium", "mortality rate", "discount rate"}.issubset(term_names)

    validation = builder.validate(str(tmp_path))
    assert validation["valid"] is True


def test_build_formula_profile_preserves_duplicate_and_blank_table_headers(test_db_path, tmp_path):
    conn = Storage(test_db_path)
    conn._conn.execute(
        """
        UPDATE global_chunks
        SET content = ?, section_hierarchy = ?
        WHERE chunk_index = ?
        """,
        (
            "\n".join(
                [
                    "Reserve Factor = Premium / Benefit.",
                    "| Value | Value | |",
                    "| 2024 | 2025 | notes |",
                ]
            ),
            "Actuarial formulas > Duplicate table headers",
            1,
        ),
    )
    conn._conn.commit()
    conn.close()

    builder.build_l0(db_path=test_db_path, output_dir=str(tmp_path), profile="formula")

    tables = [
        json.loads(line)
        for line in (tmp_path / "tables_structured.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert tables[0]["headers"] == ["Value", "Value_2", "column_3"]
    assert tables[0]["rows"][0] == {"Value": "2024", "Value_2": "2025", "column_3": "notes"}


def test_ready_data_builder_cli_accepts_formula_profile(test_db_path, tmp_path):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_actuarial.agentic_rag.ready_data_builder",
            "--database-url-env",
            "DATABASE_URL",
            "--output-dir",
            str(tmp_path),
            "--profile",
            "formula",
            "--validate",
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads((tmp_path / "ready_data_manifest.json").read_text(encoding="utf-8"))
    assert manifest["profile"] == "formula"
    assert (tmp_path / "formula_cards.jsonl").is_file()


def test_validate_rejects_manifest_artifact_paths_that_escape_output_dir(tmp_path):
    outside = tmp_path / "outside.jsonl"
    outside.write_text("{}\n", encoding="utf-8")
    with open(tmp_path / "ready_data_manifest.json", "w", encoding="utf-8") as f:
        json.dump({"artifact_files": ["../outside.jsonl"]}, f)

    result = builder.validate(str(tmp_path))

    assert result["valid"] is False
    assert any("escapes output_dir" in error for error in result["errors"])


def test_validate_rejects_orphan_l1_structured_sections_and_relations(tmp_path):
    doc = {
        "doc_id": "doc-a",
        "file_url": "doc-a",
        "title": "Rule A",
        "category": "regulation",
        "source_site": "",
        "publish_date": "",
        "summary": "",
        "keywords": [],
        "headings": [],
        "rag_chunk_count": 1,
    }
    section = {
        "section_id": "doc-a#s1",
        "doc_id": "doc-a",
        "heading_path": ["Article 1"],
        "text": "hello",
        "token_count": 1,
    }
    structured = {
        "section_id": "doc-missing#s1",
        "doc_id": "doc-missing",
        "heading_path": ["Article 1"],
        "text": "orphan",
        "token_count": 1,
    }
    graph = {
        "relations": [
            {
                "relation_type": "document_has_section",
                "doc_id": "doc-missing",
                "target_type": "section",
                "target_id": "doc-missing#s2",
            }
        ]
    }
    with open(tmp_path / "doc_catalog.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False) + "\n")
    with open(tmp_path / "sections.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(section, ensure_ascii=False) + "\n")
    with open(tmp_path / "sections_structured.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(structured, ensure_ascii=False) + "\n")
    with open(tmp_path / "relations_graph.json", "w", encoding="utf-8") as f:
        json.dump(graph, f)
    with open(tmp_path / "ready_data_manifest.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "artifact_files": [
                    "doc_catalog.jsonl",
                    "sections.jsonl",
                    "sections_structured.jsonl",
                    "relations_graph.json",
                    "ready_data_manifest.json",
                ]
            },
            f,
        )

    result = builder.validate(str(tmp_path))

    assert result["valid"] is False
    assert any("structured section doc_ids not in catalog" in error for error in result["errors"])
    assert any("relation doc_ids not in catalog" in error for error in result["errors"])
    assert any("relation section targets not in sections" in error for error in result["errors"])


def test_validate_rejects_orphan_l2_relation_targets(tmp_path):
    def write_jsonl(name: str, rows: list[dict[str, object]]) -> None:
        with open(tmp_path / name, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    doc = {
        "doc_id": "doc-a",
        "file_url": "doc-a",
        "title": "Formula Doc",
        "category": "formula",
        "source_site": "",
        "publish_date": "",
        "summary": "",
        "keywords": [],
        "headings": [],
        "rag_chunk_count": 1,
    }
    section = {
        "section_id": "doc-a#s1",
        "doc_id": "doc-a",
        "heading_path": ["Formula"],
        "text": "Net Premium = PV Benefits / PV Premiums.",
        "token_count": 6,
    }
    structured = {
        **section,
        "file_url": "doc-a",
        "title": "Formula Doc",
        "heading": "Formula",
        "document_aliases": ["Formula Doc"],
    }
    write_jsonl("doc_catalog.jsonl", [doc])
    write_jsonl("sections.jsonl", [section])
    write_jsonl("sections_structured.jsonl", [structured])
    write_jsonl(
        "formula_cards.jsonl",
        [
            {
                "formula_id": "doc-a#s1#formula-1",
                "doc_id": "doc-a",
                "section_id": "doc-a#s1",
                "formula_text": "Net Premium = PV Benefits / PV Premiums.",
            }
        ],
    )
    write_jsonl(
        "tables_structured.jsonl",
        [
            {
                "table_id": "doc-a#s1#table-1",
                "doc_id": "doc-a",
                "section_id": "doc-a#s1",
                "headers": ["Term"],
                "rows": [{"Term": "q_x"}],
            }
        ],
    )
    write_jsonl(
        "calculation_terms.jsonl",
        [
            {
                "term_id": "doc-a#s1#term-net-premium",
                "doc_id": "doc-a",
                "section_id": "doc-a#s1",
                "term": "Net Premium",
            }
        ],
    )
    with open(tmp_path / "relations_graph.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "relations": [
                    {
                        "relation_type": "document_has_formula",
                        "doc_id": "doc-a",
                        "section_id": "doc-a#s1",
                        "target_type": "formula",
                        "target_id": "doc-a#s1#missing-formula",
                    },
                    {
                        "relation_type": "document_has_table",
                        "doc_id": "doc-a",
                        "section_id": "doc-a#s1",
                        "target_type": "table",
                        "target_id": "doc-a#s1#missing-table",
                    },
                    {
                        "relation_type": "document_has_calculation_term",
                        "doc_id": "doc-a",
                        "section_id": "doc-a#s1",
                        "target_type": "calculation_term",
                        "target_id": "doc-a#s1#missing-term",
                    },
                ]
            },
            f,
        )
    with open(tmp_path / "ready_data_manifest.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "artifact_files": [
                    "doc_catalog.jsonl",
                    "sections.jsonl",
                    "sections_structured.jsonl",
                    "formula_cards.jsonl",
                    "tables_structured.jsonl",
                    "calculation_terms.jsonl",
                    "relations_graph.json",
                    "ready_data_manifest.json",
                ]
            },
            f,
        )

    result = builder.validate(str(tmp_path))

    assert result["valid"] is False
    assert any(
        "relation formula targets not in L2 artifacts" in error for error in result["errors"]
    )
    assert any("relation table targets not in L2 artifacts" in error for error in result["errors"])
    assert any(
        "relation calculation_term targets not in L2 artifacts" in error
        for error in result["errors"]
    )


def test_validate_resolves_dict_mapped_l2_artifact_paths(tmp_path):
    mapped_dir = tmp_path / "mapped"
    mapped_dir.mkdir()

    def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    doc = {"doc_id": "doc-a", "file_url": "doc-a", "title": "Formula Doc", "category": "formula"}
    section = {
        "section_id": "doc-a#s1",
        "doc_id": "doc-a",
        "heading_path": ["Formula"],
        "text": "A = B",
    }
    structured = {**section, "file_url": "doc-a", "title": "Formula Doc", "heading": "Formula"}
    write_jsonl(mapped_dir / "catalog.jsonl", [doc])
    write_jsonl(mapped_dir / "sections.jsonl", [section])
    write_jsonl(mapped_dir / "structured.jsonl", [structured])
    write_jsonl(
        mapped_dir / "formulas.jsonl",
        [{"formula_id": "doc-a#s1#formula-1", "doc_id": "doc-a", "section_id": "doc-a#s1"}],
    )
    write_jsonl(
        mapped_dir / "tables.jsonl",
        [{"table_id": "doc-a#s1#table-1", "doc_id": "doc-a", "section_id": "doc-a#s1"}],
    )
    write_jsonl(
        mapped_dir / "terms.jsonl",
        [{"term_id": "doc-a#s1#term-a", "doc_id": "doc-a", "section_id": "doc-a#s1"}],
    )
    with open(mapped_dir / "relations.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "relations": [
                    {
                        "relation_type": "document_has_formula",
                        "doc_id": "doc-a",
                        "section_id": "doc-a#s1",
                        "target_type": "formula",
                        "target_id": "doc-a#s1#missing-formula",
                    }
                ]
            },
            f,
        )
    with open(tmp_path / "ready_data_manifest.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "artifact_files": {
                    "doc_catalog.jsonl": "mapped/catalog.jsonl",
                    "sections.jsonl": "mapped/sections.jsonl",
                    "sections_structured.jsonl": "mapped/structured.jsonl",
                    "formula_cards.jsonl": "mapped/formulas.jsonl",
                    "tables_structured.jsonl": "mapped/tables.jsonl",
                    "calculation_terms.jsonl": "mapped/terms.jsonl",
                    "relations_graph.json": "mapped/relations.json",
                    "ready_data_manifest.json": "ready_data_manifest.json",
                }
            },
            f,
        )

    result = builder.validate(str(tmp_path))

    assert result["valid"] is False
    assert not any("artifact missing" in error for error in result["errors"])
    assert any(
        "relation formula targets not in L2 artifacts" in error for error in result["errors"]
    )


def test_build_l0_kb_scope_does_not_fallback_to_partial_legacy_tables(test_db_path, tmp_path):
    """An exact KB binding must use its persisted chunk profile."""
    storage = Storage(test_db_path)
    try:
        url_one = "https://example.com/rule1"
        url_two = "https://example.com/rule2"
        _seed_file_and_catalog(storage, url_two, title="Other Rule", category="other")
        other_profile = storage.create_chunk_profile(
            name="other-ready-data-profile", chunk_size=300, chunk_overlap=40
        )
        other_set_id = _seed_chunk_set(
            storage,
            url_one,
            [
                {
                    "chunk_id": "c4",
                    "chunk_index": 0,
                    "content": "Other profile content",
                    "token_count": 30,
                    "section_hierarchy": "Wrong Profile",
                }
            ],
            markdown_hash="other-profile-rule1",
            profile_id=other_profile["profile_id"],
        )
        second_set_id = _seed_chunk_set(
            storage,
            url_two,
            [
                {
                    "chunk_id": "c3",
                    "chunk_index": 0,
                    "content": "Other content",
                    "token_count": 20,
                    "section_hierarchy": "Other",
                }
            ],
            markdown_hash="profile-rule2",
        )
        _seed_kb(storage, "kb_rule_1")
        _seed_kb(storage, "kb_rule_2")
        _add_kb_member(storage, "kb_rule_1", url_one)
        _add_kb_member(storage, "kb_rule_2", url_two)
        _add_kb_binding(storage, "kb_rule_1", url_one, other_set_id)
        _add_kb_binding(storage, "kb_rule_2", url_two, second_set_id)
    finally:
        storage.close()

    with pytest.raises(ValueError, match="wrong chunk profile"):
        builder.build_l0(
            db_path=test_db_path,
            output_dir=str(tmp_path),
            profile="general",
            kb_id="kb_rule_1",
        )


def test_build_l0_rejects_historical_orphan_binding_without_exact_kb(test_db_path, tmp_path):
    storage = Storage(test_db_path)
    try:
        _seed_kb(storage, "kb_rule_1")
        _add_kb_member(storage, "kb_rule_1", "https://example.com/rule1")
        orphan_url = "https://example.com/orphan"
        _seed_file_and_catalog(storage, orphan_url, title="Orphan", status="error")
        orphan_set_id = _seed_chunk_set(
            storage,
            orphan_url,
            [
                {
                    "chunk_id": "c-orphan",
                    "chunk_index": 0,
                    "content": "Orphan content",
                    "token_count": 10,
                    "section_hierarchy": "Orphan",
                }
            ],
            markdown_hash="orphan",
        )
        _add_kb_binding(storage, "kb_rule_1", orphan_url, orphan_set_id)
    finally:
        storage.close()

    with pytest.raises(ValueError, match="one binding for every KB member"):
        builder.build_l0(
            db_path=test_db_path,
            output_dir=str(tmp_path / "orphan-binding"),
            profile="general",
            kb_id="kb_rule_1",
        )


def test_build_l0_rejects_non_ready_binding_without_exact_kb(test_db_path, tmp_path):
    storage = Storage(test_db_path)
    invalid_url = "https://example.com/not-ready"
    try:
        _seed_kb(storage, "kb_rule_1")
        _add_kb_member(storage, "kb_rule_1", "https://example.com/rule1")
        _seed_file_and_catalog(storage, invalid_url, title="Not Ready")
        _add_kb_member(storage, "kb_rule_1", invalid_url)
        valid_set_id = storage._conn.execute(
            "SELECT chunk_set_id FROM file_chunk_sets WHERE file_url = ?",
            ("https://example.com/rule1",),
        ).fetchone()[0]
        pending_set_id = _seed_chunk_set(
            storage, invalid_url, [], markdown_hash="not-ready", status="building"
        )
        _add_kb_binding(storage, "kb_rule_1", "https://example.com/rule1", valid_set_id)
        _add_kb_binding(storage, "kb_rule_1", invalid_url, pending_set_id)
    finally:
        storage.close()

    with pytest.raises(ValueError, match="ready chunk set"):
        builder.build_l0(
            db_path=test_db_path,
            output_dir=str(tmp_path / "invalid-catalog-binding"),
            profile="general",
            kb_id="kb_rule_1",
        )


def test_build_l0_empty_db(tmp_path):
    """Build with no catalog items should produce empty outputs."""
    db_path = postgres_url_for_path(tmp_path / "empty.db")
    Storage(db_path).close()

    manifest = builder.build_l0(
        db_path=db_path,
        output_dir=str(tmp_path),
        profile="general",
    )

    assert manifest["doc_count"] == 0
    assert manifest["section_count"] == 0


def test_validate(tmp_path):
    """Validation returns valid=True for correct outputs."""
    # Write minimal valid outputs
    doc = {
        "doc_id": "test.md",
        "file_url": "test.md",
        "title": "Test",
        "category": "general",
        "source_site": "",
        "publish_date": "",
        "summary": "",
        "keywords": [],
        "headings": ["H1"],
        "rag_chunk_count": 1,
    }
    section = {
        "section_id": "test.md#c1",
        "doc_id": "test.md",
        "heading_path": ["H1"],
        "text": "hello",
        "token_count": 5,
    }

    with open(tmp_path / "doc_catalog.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False) + "\n")
    with open(tmp_path / "sections.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(section, ensure_ascii=False) + "\n")
    with open(tmp_path / "ready_data_manifest.json", "w", encoding="utf-8") as f:
        json.dump(
            {"artifact_files": ["doc_catalog.jsonl", "sections.jsonl", "ready_data_manifest.json"]},
            f,
        )

    result = builder.validate(str(tmp_path))
    assert result["valid"] is True
    assert result["errors"] == []


def test_validate_missing_artifact(tmp_path):
    """Validation fails when an artifact is missing."""
    with open(tmp_path / "ready_data_manifest.json", "w", encoding="utf-8") as f:
        json.dump(
            {"artifact_files": ["doc_catalog.jsonl", "sections.jsonl", "ready_data_manifest.json"]},
            f,
        )
    # doc_catalog.jsonl and sections.jsonl are missing

    result = builder.validate(str(tmp_path))
    assert result["valid"] is False
    assert any("doc_catalog" in e for e in result["errors"])


def test_validate_orphan_sections(tmp_path):
    """Validation catches sections referencing non-existent doc_ids."""
    doc = {
        "doc_id": "a.md",
        "file_url": "a.md",
        "title": "A",
        "category": "general",
        "source_site": "",
        "publish_date": "",
        "summary": "",
        "keywords": [],
        "headings": [],
        "rag_chunk_count": 0,
    }
    section = {
        "section_id": "b.md#c1",
        "doc_id": "b.md",  # orphan
        "heading_path": [],
        "text": "",
        "token_count": 0,
    }
    with open(tmp_path / "doc_catalog.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(doc, ensure_ascii=False) + "\n")
    with open(tmp_path / "sections.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(section, ensure_ascii=False) + "\n")
    with open(tmp_path / "ready_data_manifest.json", "w", encoding="utf-8") as f:
        json.dump(
            {"artifact_files": ["doc_catalog.jsonl", "sections.jsonl", "ready_data_manifest.json"]},
            f,
        )

    result = builder.validate(str(tmp_path))
    assert result["valid"] is False
    assert any("orphan" in e.lower() or "not in catalog" in e.lower() for e in result["errors"])
