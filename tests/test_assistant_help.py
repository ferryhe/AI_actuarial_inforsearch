from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_actuarial.assistant.help import HelpIndexError, load_help_sections, search_help

_FIXTURE = Path(__file__).parent / "fixtures" / "assistant_help_questions.json"


def _write_doc(root: Path, filename: str, doc_id: str, sections: str) -> Path:
    path = root / filename
    path.write_text(
        f"---\ndoc_id: {doc_id}\nlanguage: en\ntitle: Test guide\nsource_version: 1.0\n---\n\n{sections}",
        encoding="utf-8",
    )
    return path


def test_fixed_bilingual_questions_map_exact_section_within_top_three():
    questions = json.loads(_FIXTURE.read_text(encoding="utf-8"))["questions"]
    assert len(questions) == 18
    assert sum(item["expected"] is not None for item in questions) == 14
    assert sum(item["expected"] is None for item in questions) == 4
    for item in questions:
        results = search_help(item["question"], language=item["language"], limit=3)
        if item["expected"] is None:
            assert results == [], item["id"]
        else:
            assert any(
                item["expected"] == {"doc_id": result["doc_id"], "section_id": result["section_id"]}
                for result in results
            ), item["id"]


@pytest.mark.parametrize(
    ("query", "language", "section_id"),
    [
        ("Common failures", "en", "common-failures"),
        ("Browsing", "en", "browse-search"),
        ("reading", "en", "file-details"),
        ("常见问题处理", "zh", "common-failures"),
    ],
)
def test_section_heading_only_queries_find_their_section(query, language, section_id):
    results = search_help(query, language=language, limit=3)
    assert results
    assert results[0]["section_id"] == section_id


def test_reload_picks_up_edits_and_removed_sections(tmp_path):
    english = tmp_path / "user-guide.en.md"
    _write_doc(tmp_path, english.name, "guide", "## Search {#search}\n\nalpha beta")
    before = load_help_sections(tmp_path)[0]
    assert search_help("alpha", limit=10, root=tmp_path)[0]["content_hash"] != ""

    _write_doc(tmp_path, english.name, "guide", "## Search {#search}\n\nnew content only")
    after = load_help_sections(tmp_path)[0]
    assert before.content_hash != after.content_hash
    assert search_help("alpha", limit=10, root=tmp_path) == []

    english.unlink()
    assert load_help_sections(tmp_path) == []


def test_only_explicit_help_markdown_allowlist_is_loaded(tmp_path):
    _write_doc(tmp_path, "user-guide.en.md", "guide", "## Search {#search}\n\napproved phrase")
    (tmp_path / "README.md").write_text("private README phrase", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("private instructions phrase", encoding="utf-8")
    (tmp_path / "sites.yaml").write_text("private configuration phrase", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("private note phrase", encoding="utf-8")
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "old.md").write_text("archive phrase", encoding="utf-8")
    (tmp_path / "notes.md").write_text("archive phrase", encoding="utf-8")
    sections = load_help_sections(tmp_path)
    assert [(item.doc_id, item.section_id) for item in sections] == [("guide", "search")]


def test_duplicate_document_and_section_ids_are_rejected(tmp_path):
    _write_doc(tmp_path, "user-guide.en.md", "same", "## A {#a}\n\ntext")
    _write_doc(tmp_path, "user-guide.zh.md", "same", "## B {#b}\n\ntext")
    with pytest.raises(HelpIndexError, match="Duplicate help doc_id"):
        load_help_sections(tmp_path)

    _write_doc(tmp_path, "user-guide.en.md", "guide", "## A {#same}\n\none\n\n## B {#same}\n\ntwo")
    (tmp_path / "user-guide.zh.md").unlink()
    with pytest.raises(HelpIndexError, match="Duplicate help section"):
        load_help_sections(tmp_path)


def test_empty_or_malformed_help_document_is_rejected(tmp_path):
    (tmp_path / "user-guide.en.md").write_text("", encoding="utf-8")
    with pytest.raises(HelpIndexError, match="Malformed help metadata"):
        load_help_sections(tmp_path)

    _write_doc(tmp_path, "user-guide.en.md", "guide", "## Empty {#empty}\n\n")
    with pytest.raises(HelpIndexError, match="no content"):
        load_help_sections(tmp_path)

    _write_doc(tmp_path, "user-guide.en.md", "guide", "## Missing stable id\n\ncontent")
    with pytest.raises(HelpIndexError, match="Malformed help section heading"):
        load_help_sections(tmp_path)


def test_overlong_section_id_is_rejected(tmp_path):
    _write_doc(tmp_path, "user-guide.en.md", "guide", f"## Search {{#{'a' * 65}}}\n\ncontent")
    with pytest.raises(HelpIndexError, match="Invalid help section ID"):
        load_help_sections(tmp_path)
