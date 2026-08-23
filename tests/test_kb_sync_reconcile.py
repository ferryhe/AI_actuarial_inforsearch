from __future__ import annotations

from pathlib import Path

from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.storage import Storage


def _setup_file(storage: Storage, *, file_url: str, title: str, category: str) -> None:
    storage.insert_file(
        url=file_url,
        sha256=f"sha-{title}",
        title=title,
        source_site="example.com",
        source_page_url="https://example.com",
        original_filename=f"{title}.pdf",
        local_path=f"/tmp/{title}.pdf",
        bytes=100,
        content_type="application/pdf",
    )
    storage.upsert_catalog_item(
        item={
            "url": file_url,
            "sha256": f"sha-{title}",
            "keywords": ["sync"],
            "summary": title,
            "category": category,
        },
        pipeline_version="v1",
        status="ok",
    )
    storage._conn.execute(
        "UPDATE catalog_items SET markdown_content = ? WHERE file_url = ?",
        (f"# {title}", file_url),
    )
    storage._conn.commit()


def _category_kb(tmp_path: Path) -> tuple[Storage, KnowledgeBaseManager]:
    storage = Storage(str(tmp_path / "kb.db"))
    manager = KnowledgeBaseManager(
        storage,
        config=RAGConfig(data_dir=str(tmp_path / "rag-data")),
    )
    manager.create_kb(kb_id="kb-fin", name="Finance KB", kb_mode="category")
    manager.link_kb_to_categories("kb-fin", ["Finance"], auto_sync=False)
    return storage, manager


def test_sync_category_files_adds_then_removes_stale_members(tmp_path: Path) -> None:
    storage, manager = _category_kb(tmp_path)
    try:
        f1 = "https://example.com/one.pdf"
        f2 = "https://example.com/two.pdf"
        _setup_file(storage, file_url=f1, title="one", category="Finance")
        _setup_file(storage, file_url=f2, title="two", category="Finance")

        first = manager.sync_category_files("kb-fin")
        assert first["added_count"] == 2
        assert first["removed_count"] == 0
        assert set(first["added_file_urls"]) == {f1, f2}
        assert first["total_files"] == 2

        # Move f2 out of the category — reconciliation should remove it.
        storage._conn.execute(
            "UPDATE catalog_items SET category = ? WHERE file_url = ?",
            ("Other", f2),
        )
        storage._conn.commit()

        second = manager.sync_category_files("kb-fin")
        assert second["added_count"] == 0
        assert second["removed_count"] == 1
        assert second["removed_file_urls"] == [f2]
        assert second["total_files"] == 1

        remaining = {
            row[0]
            for row in storage._conn.execute(
                "SELECT file_url FROM rag_kb_files WHERE kb_id = ?",
                ("kb-fin",),
            )
        }
        assert remaining == {f1}
    finally:
        storage.close()


def test_sync_category_files_unchanged_is_idempotent(tmp_path: Path) -> None:
    storage, manager = _category_kb(tmp_path)
    try:
        f1 = "https://example.com/one.pdf"
        _setup_file(storage, file_url=f1, title="one", category="Finance")

        first = manager.sync_category_files("kb-fin")
        assert first["added_count"] == 1
        assert first["removed_count"] == 0

        second = manager.sync_category_files("kb-fin")
        assert second["added_count"] == 0
        assert second["removed_count"] == 0
        assert second["added_file_urls"] == []
        assert second["removed_file_urls"] == []
        assert second["total_files"] == 1
    finally:
        storage.close()


def test_sync_all_files_removes_deleted_files(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "kb-all.db"))
    manager = KnowledgeBaseManager(
        storage,
        config=RAGConfig(data_dir=str(tmp_path / "rag-data")),
    )
    try:
        f1 = "https://example.com/one.pdf"
        f2 = "https://example.com/two.pdf"
        _setup_file(storage, file_url=f1, title="one", category="Any")
        _setup_file(storage, file_url=f2, title="two", category="Any")
        manager.create_kb(kb_id="kb-all", name="All KB", kb_mode="all")
        manager.add_files_to_kb("kb-all", [f1, f2])

        # Soft-delete f2 from the files table — it should drop out of the KB.
        storage._conn.execute(
            "UPDATE files SET deleted_at = ? WHERE url = ?",
            ("2026-08-23T00:00:00+00:00", f2),
        )
        storage._conn.commit()

        result = manager.sync_all_files("kb-all")
        assert result["removed_count"] == 1
        assert result["removed_file_urls"] == [f2]

        remaining = {
            row[0]
            for row in storage._conn.execute(
                "SELECT file_url FROM rag_kb_files WHERE kb_id = ?",
                ("kb-all",),
            )
        }
        assert remaining == {f1}
    finally:
        storage.close()


def test_sync_category_files_incremental_add_keeps_other_categories(tmp_path: Path) -> None:
    storage = Storage(str(tmp_path / "kb-multi.db"))
    manager = KnowledgeBaseManager(
        storage,
        config=RAGConfig(data_dir=str(tmp_path / "rag-data")),
    )
    try:
        f_finance = "https://example.com/finance.pdf"
        f_insurance = "https://example.com/insurance.pdf"
        _setup_file(storage, file_url=f_finance, title="finance", category="Finance")
        _setup_file(storage, file_url=f_insurance, title="insurance", category="Insurance")

        manager.create_kb(kb_id="kb-multi", name="Multi KB", kb_mode="category")
        manager.link_kb_to_categories("kb-multi", ["Finance"], auto_sync=True)

        # Incrementally linking a second category must add its files without
        # evicting members of the already-linked category.
        manager.link_kb_to_categories("kb-multi", ["Insurance"], auto_sync=True)

        members = {
            row[0]
            for row in storage._conn.execute(
                "SELECT file_url FROM rag_kb_files WHERE kb_id = ?",
                ("kb-multi",),
            )
        }
        assert members == {f_finance, f_insurance}
    finally:
        storage.close()


def test_sync_marks_ready_data_stale_on_add_and_remove(tmp_path: Path) -> None:
    storage, manager = _category_kb(tmp_path)
    try:
        f1 = "https://example.com/one.pdf"
        _setup_file(storage, file_url=f1, title="one", category="Finance")

        manager.sync_category_files("kb-fin")
        state = storage.get_agentic_ready_source_state(kb_id="kb-fin", profile="general")
        assert state["pending_severity"] == "soft_stale"
        assert "membership_added" in state["pending_reasons"]

        # Move the file out of the category — the removal should mark the
        # ready-data source hard_stale, mirroring the membership removal.
        storage._conn.execute(
            "UPDATE catalog_items SET category = ? WHERE file_url = ?",
            ("Other", f1),
        )
        storage._conn.commit()

        manager.sync_category_files("kb-fin")
        state = storage.get_agentic_ready_source_state(kb_id="kb-fin", profile="general")
        assert state["pending_severity"] == "hard_stale"
        assert "membership_removed" in state["pending_reasons"]
    finally:
        storage.close()
