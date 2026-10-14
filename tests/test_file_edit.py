#!/usr/bin/env python3
"""Unit tests for file edit functionality."""

import os
import tempfile
import unittest
from pathlib import Path

from ai_actuarial.catalog import CatalogItem
from ai_actuarial.catalog_incremental import (
    _count_candidates,
    _ensure_catalog_schema,
    _fetch_candidates,
    _upsert_catalog_row,
    run_catalog_for_urls,
)
from ai_actuarial.storage import Storage
from tests.postgres_helpers import postgres_url_for_path


class TestFileEdit(unittest.TestCase):
    """Test file catalog update functionality."""

    def setUp(self):
        """Create a temporary database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.storage = Storage(postgres_url_for_path(self.db_path))

        # Insert a test file using the public Storage API
        self.test_url = "http://test.com/file.pdf"
        self.storage.insert_file(
            url=self.test_url,
            sha256="test_hash",
            title="Test File",
            source_site="test_site",
            source_page_url="http://test.com",
            original_filename="file.pdf",
            local_path="/tmp/file.pdf",
            bytes=1024,
            content_type="application/pdf",
        )

    def tearDown(self):
        """Clean up temporary files."""
        import shutil

        self.storage.close()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_update_category(self):
        """Test updating category."""
        success, error = self.storage.update_file_catalog(self.test_url, category="Test Category")
        self.assertTrue(success)
        self.assertIsNone(error)

        # Verify the update
        file_data = self.storage.get_file_with_catalog(self.test_url)
        self.assertEqual(file_data["category"], "Test Category")

    def test_update_summary(self):
        """Test updating summary."""
        success, error = self.storage.update_file_catalog(
            self.test_url, summary="Test summary text"
        )
        self.assertTrue(success)
        self.assertIsNone(error)

        # Verify the update
        file_data = self.storage.get_file_with_catalog(self.test_url)
        self.assertEqual(file_data["summary"], "Test summary text")

    def test_update_keywords(self):
        """Test updating keywords."""
        keywords = ["keyword1", "keyword2", "keyword3"]
        success, error = self.storage.update_file_catalog(self.test_url, keywords=keywords)
        self.assertTrue(success)
        self.assertIsNone(error)

        # Verify the update
        file_data = self.storage.get_file_with_catalog(self.test_url)
        self.assertEqual(file_data["keywords"], keywords)

    def test_update_all_fields(self):
        """Test updating all fields at once."""
        keywords = ["test", "keywords"]
        success, error = self.storage.update_file_catalog(
            self.test_url, category="New Category", summary="New summary", keywords=keywords
        )
        self.assertTrue(success)
        self.assertIsNone(error)

        # Verify all updates
        file_data = self.storage.get_file_with_catalog(self.test_url)
        self.assertEqual(file_data["category"], "New Category")
        self.assertEqual(file_data["summary"], "New summary")
        self.assertEqual(file_data["keywords"], keywords)

    def test_hub_bilingual_merge_is_fill_only_canonical_and_idempotent(self):
        import json

        file_sha = "a" * 64
        self.storage._conn.execute(
            "UPDATE files SET sha256 = ? WHERE url = ?", (file_sha, self.test_url)
        )
        self.storage._conn.execute(
            "INSERT INTO catalog_items (file_url, sha256, pipeline_version, status, keywords, "
            "category, bilingual_metadata_json) VALUES (?, ?, 'manual', 'ok', ?, ?, ?)",
            (
                self.test_url,
                file_sha,
                json.dumps(["legacy-keyword"]),
                "Other",
                json.dumps(
                    {
                        "zh": {
                            "title": "Kept Chinese title",
                            "keywords": ["kept-keyword"],
                            "category": "Other",
                        },
                        "en": {},
                    }
                ),
            ),
        )
        self.storage._conn.commit()
        metadata = {
            language: {
                "title": f"Hub {language} title",
                "summary": f"Hub {language} summary",
                "category": "Life",
                "keywords": [f"Hub {language} keyword"],
                "hub_binding": {
                    "content_version_id": 5,
                    "markdown_text_variant_id": 8,
                    "markdown_sha256": "b" * 64,
                },
            }
            for language in ("zh", "en")
        }

        disposition, filled = self.storage.merge_hub_bilingual_metadata(
            url=self.test_url,
            file_sha256=file_sha,
            metadata_by_language=metadata,
        )
        self.assertEqual(disposition, "updated")
        self.assertGreater(filled, 0)
        result = self.storage.get_file_with_catalog(self.test_url)
        self.assertEqual(result["category"], "Other")
        package = result["bilingual_metadata"]
        self.assertEqual(package["zh"]["title"], "Kept Chinese title")
        self.assertEqual(package["zh"]["keywords"], ["kept-keyword"])
        self.assertEqual(package["zh"]["category"], "Other")
        self.assertEqual(package["en"]["category"], "Other")
        self.assertEqual(package["en"]["title"], "Hub en title")
        self.assertEqual(package["en"]["hub_binding"], metadata["en"]["hub_binding"])
        self.assertEqual(result["keywords"], ["legacy-keyword"])

        disposition, filled = self.storage.merge_hub_bilingual_metadata(
            url=self.test_url,
            file_sha256=file_sha,
            metadata_by_language=metadata,
        )
        self.assertEqual((disposition, filled), ("unchanged", 0))

        changed_binding = {
            **metadata,
            "zh": {
                **metadata["zh"],
                "hub_binding": {**metadata["zh"]["hub_binding"], "markdown_text_variant_id": 9},
            },
        }
        disposition, filled = self.storage.merge_hub_bilingual_metadata(
            url=self.test_url,
            file_sha256=file_sha,
            metadata_by_language=changed_binding,
        )
        self.assertEqual((disposition, filled), ("conflict", 0))

    def test_local_catalog_upserts_keep_shared_category_aligned(self):
        bilingual = {
            "zh": {
                "title": "中文标题",
                "summary": "中文摘要",
                "category": "Life",
                "keywords": ["中文"],
            },
            "en": {
                "title": "English title",
                "summary": "English summary",
                "category": "Life",
                "keywords": ["english"],
            },
        }

        def save_bilingual() -> None:
            self.storage.upsert_catalog_item(
                item={
                    "url": self.test_url,
                    "sha256": "test_hash",
                    "keywords": ["legacy"],
                    "summary": "Legacy summary",
                    "category": "Life",
                    "bilingual_metadata": bilingual,
                },
                pipeline_version="v1",
                status="ok",
            )

        save_bilingual()
        self.storage.upsert_catalog_item(
            item={
                "url": self.test_url,
                "sha256": "test_hash",
                "keywords": ["local"],
                "summary": "Local summary",
                "category": "Other",
            },
            pipeline_version="v1",
            status="ok",
        )
        file_data = self.storage.get_file_with_catalog(self.test_url)
        self.assertEqual(file_data["category"], "Other")
        self.assertEqual(file_data["bilingual_metadata"]["zh"]["category"], "Other")
        self.assertEqual(file_data["bilingual_metadata"]["en"]["category"], "Other")
        self.assertEqual(file_data["bilingual_metadata"]["zh"]["title"], "中文标题")
        self.assertEqual(file_data["bilingual_metadata"]["en"]["keywords"], ["english"])

        save_bilingual()
        _upsert_catalog_row(
            self.storage._conn,
            item=CatalogItem(
                source_site="test_site",
                title="Test File",
                original_filename="file.pdf",
                url=self.test_url,
                local_path="/tmp/file.pdf",
                keywords=["local"],
                summary="Local summary",
                category="Other",
            ),
            file_sha256="test_hash",
            catalog_version="v1",
            status="ok",
            processed_at="2026-10-14T00:00:00Z",
            storage=self.storage,
        )
        file_data = self.storage.get_file_with_catalog(self.test_url)
        self.assertEqual(file_data["category"], "Other")
        self.assertEqual(file_data["bilingual_metadata"]["zh"]["category"], "Other")
        self.assertEqual(file_data["bilingual_metadata"]["en"]["category"], "Other")
        self.assertEqual(file_data["bilingual_metadata"]["zh"]["summary"], "中文摘要")
        self.assertEqual(file_data["bilingual_metadata"]["en"]["title"], "English title")

    def test_failed_or_empty_catalog_upserts_preserve_saved_bilingual_metadata(self):
        import json

        bilingual = {
            "zh": {
                "title": "中文标题",
                "summary": "中文摘要",
                "category": "Life",
                "keywords": ["中文关键词"],
            },
            "en": {
                "title": "English title",
                "summary": "English summary",
                "category": "Life",
                "keywords": ["english keyword"],
            },
        }

        def write_catalog(path: str, *, status: str, error: str | None = None) -> None:
            item = CatalogItem(
                source_site="test_site",
                title="Test File",
                original_filename="file.pdf",
                url=self.test_url,
                local_path="/tmp/file.pdf",
                keywords=["legacy"],
                summary="Legacy summary",
                category="Life",
                bilingual_metadata=bilingual,
            )
            if path == "incremental":
                _upsert_catalog_row(
                    self.storage._conn,
                    item=item,
                    file_sha256="test_hash",
                    catalog_version="v1",
                    status=status,
                    processed_at="2026-10-14T00:00:00Z",
                    error=error,
                    storage=self.storage,
                )
            else:
                self.storage.upsert_catalog_item(
                    item={
                        "url": item.url,
                        "sha256": "test_hash",
                        "keywords": item.keywords,
                        "summary": item.summary,
                        "category": item.category,
                        "bilingual_metadata": item.bilingual_metadata,
                    },
                    pipeline_version="v1",
                    status=status,
                    error=error,
                    processed_at="2026-10-14T00:00:00Z",
                )

        for path in ("storage", "incremental"):
            for status, category, error in (
                ("error", "", "catalog_failed"),
                ("skipped", "", None),
                ("ok", "", None),
            ):
                with self.subTest(path=path, status=status):
                    write_catalog(path, status="ok")
                    failure_item = CatalogItem(
                        source_site="test_site",
                        title="Test File",
                        original_filename="file.pdf",
                        url=self.test_url,
                        local_path="/tmp/file.pdf",
                        keywords=[],
                        summary="",
                        category=category,
                    )
                    if path == "incremental":
                        _upsert_catalog_row(
                            self.storage._conn,
                            item=failure_item,
                            file_sha256="test_hash",
                            catalog_version="v1",
                            status=status,
                            processed_at="2026-10-14T00:01:00Z",
                            error=error,
                            storage=self.storage,
                        )
                    else:
                        self.storage.upsert_catalog_item(
                            item={
                                "url": self.test_url,
                                "sha256": "test_hash",
                                "keywords": [],
                                "summary": "",
                                "category": category,
                            },
                            pipeline_version="v1",
                            status=status,
                            error=error,
                            processed_at="2026-10-14T00:01:00Z",
                        )
                    row = self.storage._conn.execute(
                        "SELECT status, error, category, summary, keywords, "
                        "bilingual_metadata_json FROM catalog_items WHERE file_url = ?",
                        (self.test_url,),
                    ).fetchone()
                    self.assertEqual(row[0], status)
                    self.assertEqual(row[1], error)
                    self.assertEqual(row[2], "Life")
                    self.assertEqual(json.loads(row[5]), bilingual)
                    if status in {"error", "skipped"}:
                        self.assertEqual(row[3], "Legacy summary")
                        self.assertEqual(json.loads(row[4]), ["legacy"])

    def test_hub_bilingual_merge_conflicts_on_existing_category_disagreement(self):
        import json

        file_sha = "c" * 64
        self.storage._conn.execute(
            "UPDATE files SET sha256 = ? WHERE url = ?", (file_sha, self.test_url)
        )
        hub_metadata = {
            language: {
                "title": f"Hub {language} title",
                "summary": f"Hub {language} summary",
                "category": "Life",
                "keywords": [f"Hub {language} keyword"],
            }
            for language in ("zh", "en")
        }
        inconsistent_targets = (
            ("Other", "Life", "Life"),
            ("", "Life", "Other"),
        )
        for legacy, zh_category, en_category in inconsistent_targets:
            with self.subTest(legacy=legacy, zh=zh_category, en=en_category):
                package = {
                    "zh": {"title": "kept zh", "category": zh_category},
                    "en": {"title": "kept en", "category": en_category},
                }
                self.storage._conn.execute(
                    "INSERT INTO catalog_items (file_url, sha256, pipeline_version, status, "
                    "category, bilingual_metadata_json) VALUES (?, ?, 'manual', 'ok', ?, ?) "
                    "ON CONFLICT(file_url) DO UPDATE SET category=excluded.category, "
                    "bilingual_metadata_json=excluded.bilingual_metadata_json",
                    (self.test_url, file_sha, legacy, json.dumps(package)),
                )
                self.storage._conn.commit()

                disposition, filled = self.storage.merge_hub_bilingual_metadata(
                    url=self.test_url,
                    file_sha256=file_sha,
                    metadata_by_language=hub_metadata,
                )
                self.assertEqual((disposition, filled), ("conflict", 0))
                result = self.storage.get_file_with_catalog(self.test_url)
                self.assertEqual(result["category"], legacy)
                self.assertEqual(result["bilingual_metadata"], package)

    def test_update_nonexistent_file(self):
        """Test updating a nonexistent file returns file_not_found error."""
        nonexistent_url = "http://test.com/nonexistent.pdf"
        success, error = self.storage.update_file_catalog(nonexistent_url, category="Test")
        self.assertFalse(success)
        self.assertEqual(error, "file_not_found")

    def test_update_with_empty_values(self):
        """Test updating with empty strings."""
        success, error = self.storage.update_file_catalog(
            self.test_url, category="", summary="", keywords=[]
        )
        self.assertTrue(success)
        self.assertIsNone(error)

        # Verify the empty values
        file_data = self.storage.get_file_with_catalog(self.test_url)
        self.assertEqual(file_data["category"], "")
        self.assertEqual(file_data["summary"], "")
        self.assertEqual(file_data["keywords"], [])

    def test_language_edit_preserves_other_language_and_shares_category(self):
        self.storage.upsert_catalog_item(
            item={
                "url": self.test_url,
                "sha256": "test_hash",
                "keywords": ["legacy"],
                "summary": "Legacy summary",
                "category": "Other",
                "bilingual_metadata": {
                    "zh": {
                        "title": "中文标题",
                        "summary": "中文摘要",
                        "category": "Other",
                        "keywords": ["中文"],
                    },
                    "en": {
                        "title": "English title",
                        "summary": "English summary",
                        "category": "Other",
                        "keywords": ["english"],
                    },
                },
            },
            pipeline_version="v1",
            status="ok",
        )

        success, error = self.storage.update_file_metadata(
            self.test_url,
            title="Updated English title",
            category="Life",
            summary="Updated English summary",
            keywords=["updated"],
            lang="en",
        )
        self.assertTrue(success)
        self.assertIsNone(error)
        metadata = self.storage.get_file_with_catalog(self.test_url)["bilingual_metadata"]
        self.assertEqual(
            metadata["en"],
            {
                "title": "Updated English title",
                "summary": "Updated English summary",
                "category": "Life",
                "keywords": ["updated"],
            },
        )
        self.assertEqual(
            metadata["zh"],
            {
                "title": "中文标题",
                "summary": "中文摘要",
                "category": "Life",
                "keywords": ["中文"],
            },
        )

    def test_legacy_edit_does_not_fill_incomplete_language_packages(self):
        self.storage.upsert_catalog_item(
            item={
                "url": self.test_url,
                "sha256": "test_hash",
                "keywords": ["legacy"],
                "summary": "Legacy summary",
                "category": "Other",
                "bilingual_metadata": {"zh": {"title": "中文标题"}},
            },
            pipeline_version="v1",
            status="ok",
        )

        success, error = self.storage.update_file_metadata(
            self.test_url,
            title="Updated legacy title",
            category="Life",
        )
        self.assertTrue(success)
        self.assertIsNone(error)
        file_data = self.storage.get_file_with_catalog(self.test_url)
        self.assertEqual(file_data["title"], "Updated legacy title")
        self.assertEqual(
            file_data["bilingual_metadata"]["zh"], {"title": "中文标题", "category": "Life"}
        )
        self.assertEqual(file_data["bilingual_metadata"]["en"], {"category": "Life"})

    def test_search_matches_each_bilingual_text_field(self):
        metadata = {
            "zh": {
                "title": "中文标题",
                "summary": "中文摘要",
                "category": "Life",
                "keywords": ["中文关键词"],
            },
            "en": {
                "title": "English title",
                "summary": "English summary",
                "category": "Life",
                "keywords": ["englishkeyword"],
            },
        }
        self.storage.upsert_catalog_item(
            item={
                "url": self.test_url,
                "sha256": "test_hash",
                "keywords": ["legacy-only"],
                "summary": "legacy summary",
                "category": "Life",
                "bilingual_metadata": metadata,
            },
            pipeline_version="v1",
            status="ok",
        )

        for term in (
            "中文标题",
            "中文摘要",
            "中文关键词",
            "English title",
            "English summary",
            "englishkeyword",
        ):
            files, total = self.storage.query_files_with_catalog(query=term)
            self.assertEqual(total, 1, term)
            self.assertEqual(files[0]["bilingual_metadata"], metadata)

    def test_ai_candidates_require_both_language_packages_but_local_contract_does_not(self):
        _ensure_catalog_schema(self.storage._conn)
        self.storage.upsert_catalog_item(
            item={
                "url": self.test_url,
                "sha256": "test_hash",
                "keywords": ["legacy"],
                "summary": "Existing summary",
                "category": "Other",
            },
            pipeline_version="v1",
            status="ok",
        )
        args = {
            "site_filter": None,
            "category_filter": None,
            "catalog_version": "v1",
            "retry_errors": False,
            "skip_existing": True,
        }
        self.assertEqual(_count_candidates(self.storage._conn, **args), 0)
        self.assertEqual(_count_candidates(self.storage._conn, **args, require_bilingual=True), 1)
        fetch_args = {
            "batch": 10,
            "site_filter": None,
            "category_filter": None,
            "catalog_version": "v1",
            "retry_errors": False,
            "skip_existing": True,
        }
        self.assertEqual(_fetch_candidates(self.storage._conn, **fetch_args), [])
        bilingual_candidates = _fetch_candidates(
            self.storage._conn, **fetch_args, require_bilingual=True
        )
        self.assertEqual(len(bilingual_candidates), 1)
        url_stats = run_catalog_for_urls(
            db_path=self.storage.database,
            file_urls=[self.test_url],
            out_jsonl=Path(self.temp_dir) / "catalog.jsonl",
            out_md=Path(self.temp_dir) / "catalog.md",
            catalog_version="v1",
            provider="local",
        )
        self.assertEqual(url_stats["scanned"], 0)

        self.storage.upsert_catalog_item(
            item={
                "url": self.test_url,
                "sha256": "test_hash",
                "keywords": ["legacy"],
                "summary": "Existing summary",
                "category": "Other",
                "bilingual_metadata": {
                    "zh": {
                        "title": "标题",
                        "summary": "摘要",
                        "category": "Other",
                        "keywords": ["词"],
                    },
                    "en": {
                        "title": "Title",
                        "summary": "Summary",
                        "category": "Other",
                        "keywords": ["keyword"],
                    },
                },
            },
            pipeline_version="v1",
            status="ok",
        )
        self.assertEqual(_count_candidates(self.storage._conn, **args, require_bilingual=True), 0)

    def test_frontend_bilingual_request_rejects_local_catalog_provider(self):
        with self.assertRaisesRegex(RuntimeError, "non-local AI provider"):
            run_catalog_for_urls(
                db_path="unused",
                file_urls=[],
                out_jsonl=Path("unused.jsonl"),
                out_md=Path("unused.md"),
                provider="local",
                require_bilingual=True,
            )


if __name__ == "__main__":
    unittest.main()
