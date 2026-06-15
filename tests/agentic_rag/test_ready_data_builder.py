"""Tests for ready_data_builder L0 MVP."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

# Import under test
import ai_actuarial.agentic_rag.ready_data_builder as builder


@pytest.fixture
def test_db_path(tmp_path):
    """Create a file-backed SQLite DB with test catalog + chunk data."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    conn.executescript(
        """
        CREATE TABLE files (
            url TEXT PRIMARY KEY,
            title TEXT,
            source_site TEXT,
            published_time TEXT
        );
        CREATE TABLE catalog_items (
            file_url TEXT PRIMARY KEY,
            status TEXT DEFAULT 'ok',
            summary TEXT,
            category TEXT,
            keywords TEXT,
            rag_chunk_count INTEGER DEFAULT 0
        );
        CREATE TABLE file_chunk_sets (
            chunk_set_id TEXT PRIMARY KEY,
            file_url TEXT NOT NULL,
            chunk_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'ready'
        );
        CREATE TABLE global_chunks (
            chunk_id TEXT PRIMARY KEY,
            chunk_set_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            token_count INTEGER DEFAULT 0,
            section_hierarchy TEXT
        );
    """
    )

    # Insert test data
    conn.execute(
        "INSERT INTO files(url,title,source_site,published_time) VALUES(?,?,?,?)",
        ("https://example.com/rule1", "偿付能力监管规则第3号", "CBIRC", "2024-01-01"),
    )
    conn.execute(
        "INSERT INTO catalog_items(file_url,status,summary,category,keywords,rag_chunk_count) VALUES(?,?,?,?,?,?)",
        (
            "https://example.com/rule1",
            "ok",
            "偿付能力监管规则摘要",
            "regulation",
            '["偿二代","偿付能力","寿险"]',
            2,
        ),
    )
    conn.execute(
        "INSERT INTO file_chunk_sets(chunk_set_id,file_url,chunk_count) VALUES(?,?,?)",
        ("cs1", "https://example.com/rule1", 2),
    )
    conn.execute(
        "INSERT INTO global_chunks(chunk_id,chunk_set_id,chunk_index,content,token_count,section_hierarchy) VALUES(?,?,?,?,?,?)",
        ("c1", "cs1", 0, "第一章 总则，第一条 为规范...", 50, "第一章 总则 > 第一条"),
    )
    conn.execute(
        "INSERT INTO global_chunks(chunk_id,chunk_set_id,chunk_index,content,token_count,section_hierarchy) VALUES(?,?,?,?,?,?)",
        ("c2", "cs1", 1, "第二章 负债评估，第十九条...", 80, "第二章 负债评估 > 第十九条"),
    )
    conn.commit()
    conn.close()
    return db_path


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
        for line in (tmp_path / "sections_structured.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert sections[0]["heading"] == "第一条"
    assert sections[0]["document_aliases"] == aliases[0]["aliases"]

    graph = json.loads((tmp_path / "relations_graph.json").read_text(encoding="utf-8"))
    relation_types = {row["relation_type"] for row in graph["relations"]}
    assert {"alias_of", "document_has_section"}.issubset(relation_types)

    validation = builder.validate(str(tmp_path))
    assert validation["valid"] is True


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


def test_build_l0_can_scope_to_knowledge_base(test_db_path, tmp_path):
    """KB scoped builds should not leak catalog rows from other KBs."""
    conn = sqlite3.connect(test_db_path)
    conn.executescript(
        """
        CREATE TABLE rag_kb_files (
            kb_id TEXT NOT NULL,
            file_url TEXT NOT NULL,
            added_at TEXT NOT NULL,
            PRIMARY KEY (kb_id, file_url)
        );
        CREATE TABLE kb_chunk_bindings (
            kb_id TEXT NOT NULL,
            file_url TEXT NOT NULL,
            chunk_set_id TEXT NOT NULL,
            bound_at TEXT NOT NULL,
            binding_mode TEXT DEFAULT 'follow_latest'
        );
        """
    )
    conn.execute(
        "INSERT INTO files(url,title,source_site,published_time) VALUES(?,?,?,?)",
        ("https://example.com/rule2", "Other Rule", "Other", "2024-02-01"),
    )
    conn.execute(
        "INSERT INTO catalog_items(file_url,status,summary,category,keywords,rag_chunk_count) VALUES(?,?,?,?,?,?)",
        (
            "https://example.com/rule2",
            "ok",
            "Other summary",
            "other",
            "other",
            1,
        ),
    )
    conn.execute(
        "INSERT INTO file_chunk_sets(chunk_set_id,file_url,chunk_count) VALUES(?,?,?)",
        ("cs2", "https://example.com/rule2", 1),
    )
    conn.execute(
        "INSERT INTO global_chunks(chunk_id,chunk_set_id,chunk_index,content,token_count,section_hierarchy) VALUES(?,?,?,?,?,?)",
        ("c3", "cs2", 0, "Other content", 20, "Other"),
    )
    conn.execute(
        "INSERT INTO file_chunk_sets(chunk_set_id,file_url,chunk_count) VALUES(?,?,?)",
        ("cs1_other_profile", "https://example.com/rule1", 1),
    )
    conn.execute(
        "INSERT INTO global_chunks(chunk_id,chunk_set_id,chunk_index,content,token_count,section_hierarchy) VALUES(?,?,?,?,?,?)",
        ("c4", "cs1_other_profile", 0, "Other profile content", 30, "Wrong Profile"),
    )
    conn.execute(
        "INSERT INTO rag_kb_files(kb_id,file_url,added_at) VALUES(?,?,?)",
        ("kb_rule_1", "https://example.com/rule1", "2026-06-14T00:00:00+00:00"),
    )
    conn.execute(
        "INSERT INTO rag_kb_files(kb_id,file_url,added_at) VALUES(?,?,?)",
        ("kb_rule_2", "https://example.com/rule2", "2026-06-14T00:00:00+00:00"),
    )
    conn.execute(
        "INSERT INTO kb_chunk_bindings(kb_id,file_url,chunk_set_id,bound_at) VALUES(?,?,?,?)",
        ("kb_rule_1", "https://example.com/rule1", "cs1", "2026-06-14T00:00:01+00:00"),
    )
    conn.execute(
        "INSERT INTO kb_chunk_bindings(kb_id,file_url,chunk_set_id,bound_at) VALUES(?,?,?,?)",
        ("kb_rule_2", "https://example.com/rule2", "cs2", "2026-06-14T00:00:01+00:00"),
    )
    conn.commit()
    conn.close()

    manifest = builder.build_l0(
        db_path=test_db_path,
        output_dir=str(tmp_path),
        profile="general",
        kb_id="kb_rule_1",
    )

    assert manifest["kb_id"] == "kb_rule_1"
    assert manifest["scope"] == "knowledge_base"
    assert manifest["output_dir"] == str(tmp_path)
    assert manifest["doc_count"] == 1
    assert manifest["section_count"] == 2
    catalog_entries = [
        json.loads(line)
        for line in (tmp_path / "doc_catalog.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [entry["file_url"] for entry in catalog_entries] == ["https://example.com/rule1"]
    section_text = (tmp_path / "sections.jsonl").read_text(encoding="utf-8")
    assert "Other profile content" not in section_text
    assert "Wrong Profile" not in section_text


def test_build_l0_empty_db(tmp_path):
    """Build with no catalog items should produce empty outputs."""
    db_path = str(tmp_path / "empty.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS files(url TEXT PRIMARY KEY, title TEXT, source_site TEXT, published_time TEXT);
        CREATE TABLE IF NOT EXISTS catalog_items(file_url TEXT PRIMARY KEY, status TEXT, summary TEXT, category TEXT, keywords TEXT, rag_chunk_count INTEGER);
        CREATE TABLE IF NOT EXISTS file_chunk_sets(chunk_set_id TEXT PRIMARY KEY, file_url TEXT, chunk_count INTEGER, status TEXT);
        CREATE TABLE IF NOT EXISTS global_chunks(chunk_id TEXT PRIMARY KEY, chunk_set_id TEXT, chunk_index INTEGER, content TEXT, token_count INTEGER, section_hierarchy TEXT);
    """
    )
    conn.commit()
    conn.close()

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
        json.dump({"artifact_files": ["doc_catalog.jsonl", "sections.jsonl", "ready_data_manifest.json"]}, f)

    result = builder.validate(str(tmp_path))
    assert result["valid"] is True
    assert result["errors"] == []


def test_validate_missing_artifact(tmp_path):
    """Validation fails when an artifact is missing."""
    with open(tmp_path / "ready_data_manifest.json", "w", encoding="utf-8") as f:
        json.dump({"artifact_files": ["doc_catalog.jsonl", "sections.jsonl", "ready_data_manifest.json"]}, f)
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
        json.dump({"artifact_files": ["doc_catalog.jsonl", "sections.jsonl", "ready_data_manifest.json"]}, f)

    result = builder.validate(str(tmp_path))
    assert result["valid"] is False
    assert any("orphan" in e.lower() or "not in catalog" in e.lower() for e in result["errors"])
