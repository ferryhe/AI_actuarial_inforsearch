#!/usr/bin/env python3
"""Tests for the i18n (internationalisation) feature.

Covers:
  - i18n.js has balanced braces and contains required translation keys in both EN and ZH
  - All EN keys have a matching ZH key (parity check)
  - base.html loads i18n.js and carries expected data-i18n attributes
  - index.html carries expected data-i18n attributes
  - Flask routes render pages that include the i18n script tag (integration)
"""

from __future__ import annotations

import os
import re
import sys
import types
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Stub external dependencies that may not be installed in the CI environment
# ---------------------------------------------------------------------------
for _mod in ["schedule"]:
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
I18N_JS = REPO_ROOT / "ai_actuarial" / "web" / "static" / "js" / "i18n.js"
BASE_HTML = REPO_ROOT / "ai_actuarial" / "web" / "templates" / "base.html"
INDEX_HTML = REPO_ROOT / "ai_actuarial" / "web" / "templates" / "index.html"


# ---------------------------------------------------------------------------
# Helper: parse the translation dictionaries from i18n.js source text
# ---------------------------------------------------------------------------
_KEY_PATTERN = re.compile(r"'([a-z][a-z0-9_.]+)':\s*'", re.ASCII)


def _extract_keys_from_dict_block(block: str) -> set[str]:
    """Return all translation keys found inside a JS object literal block."""
    return set(_KEY_PATTERN.findall(block))


class TestI18nJsStructure(unittest.TestCase):
    """Structural / syntax checks on i18n.js."""

    def setUp(self):
        self.assertTrue(I18N_JS.exists(), f"i18n.js not found at {I18N_JS}")
        self.src = I18N_JS.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    def test_brace_balance(self):
        """Open and close curly braces must be balanced (no syntax error)."""
        opens = self.src.count("{")
        closes = self.src.count("}")
        self.assertEqual(opens, closes, "Unbalanced braces in i18n.js")

    def test_global_i18n_api_exposed(self):
        """i18n.js must expose window.I18n with all required methods."""
        for method in ("t", "setLang", "toggleLang", "getCurrentLang", "applyTranslations"):
            self.assertIn(method, self.src, f"Missing I18n.{method} in i18n.js")
        self.assertIn("global.I18n", self.src, "window.I18n assignment not found")

    def test_both_languages_present(self):
        """Source must define both 'en' and 'zh' translation dictionaries."""
        self.assertIn("en:", self.src, "English dict ('en:') not found in i18n.js")
        self.assertIn("zh:", self.src, "Chinese dict ('zh:') not found in i18n.js")

    def test_localStorage_key_used(self):
        """Language preference should be persisted via localStorage."""
        self.assertIn("localStorage", self.src, "localStorage not used in i18n.js")
        self.assertIn("'lang'", self.src, "Storage key 'lang' not found in i18n.js")

    def test_browser_language_detection(self):
        """Auto-detection must read navigator.language."""
        self.assertIn("navigator.language", self.src)
        # zh-* should map to 'zh'
        self.assertIn("startsWith('zh')", self.src)

    def test_langchange_event_dispatched(self):
        """A 'langchange' CustomEvent should be dispatched on language change."""
        self.assertIn("langchange", self.src)
        self.assertIn("CustomEvent", self.src)

    def test_required_en_keys_present(self):
        """Core navigation keys must exist in the EN dictionary."""
        required = [
            "nav.dashboard",
            "nav.database",
            "nav.chat",
            "nav.tasks",
            "nav.knowledge_bases",
            "nav.settings",
            "nav.login",
            "nav.logout",
            "nav.lang_toggle",
            "modal.confirm_title",
            "modal.cancel",
            "modal.confirm_ok",
            "modal.auth_title",
            "footer.copyright",
            "index.welcome_title",
            "index.welcome_subtitle",
            "index.total_files",
            "index.cataloged_files",
            "index.sources",
            "index.active_tasks",
            "index.quick_actions",
            "index.recent_files",
            "table.title",
            "table.source",
            "table.date",
        ]
        for key in required:
            self.assertIn(f"'{key}'", self.src, f"Translation key '{key}' missing from i18n.js")

    def test_key_parity_en_zh(self):
        """Every key in the English dict should also exist in the Chinese dict.

        We do a simple check: split the source into two halves at the 'zh: {' marker
        and compare the key sets.
        """
        # Locate the split between en and zh blocks using the pattern `en: {` and `zh: {`
        en_start = self.src.find("en: {")
        zh_start = self.src.find("zh: {")
        self.assertGreater(en_start, 0, "'en: {' marker not found")
        self.assertGreater(zh_start, 0, "'zh: {' marker not found")

        en_block = self.src[en_start:zh_start]
        zh_block = self.src[zh_start:]

        en_keys = _extract_keys_from_dict_block(en_block)
        zh_keys = _extract_keys_from_dict_block(zh_block)

        missing_in_zh = en_keys - zh_keys
        self.assertFalse(
            missing_in_zh,
            f"The following EN keys are missing from the ZH dictionary: {sorted(missing_in_zh)}",
        )


# ---------------------------------------------------------------------------
class TestBaseHtmlI18n(unittest.TestCase):
    """Checks that base.html contains the expected i18n integration."""

    def setUp(self):
        self.assertTrue(BASE_HTML.exists(), f"base.html not found at {BASE_HTML}")
        self.src = BASE_HTML.read_text(encoding="utf-8")

    def test_i18n_js_loaded(self):
        """base.html must load i18n.js."""
        self.assertIn("i18n.js", self.src, "i18n.js not referenced in base.html")

    def test_i18n_js_loaded_before_main_js(self):
        """i18n.js script tag must appear before main.js to avoid text flash."""
        # Search for the actual script src= patterns (not comments)
        pos_i18n = self.src.find("filename='js/i18n.js'")
        pos_main = self.src.find("filename='js/main.js'")
        self.assertGreater(pos_i18n, 0, "i18n.js script tag missing in base.html")
        self.assertGreater(pos_main, 0, "main.js script tag missing in base.html")
        self.assertGreater(pos_main, pos_i18n, "i18n.js must be included before main.js")

    def test_lang_toggle_button_present(self):
        """A language toggle button (#lang-toggle-btn) must be in the navbar."""
        self.assertIn("lang-toggle-btn", self.src)
        self.assertIn("I18n.toggleLang()", self.src)

    def test_nav_links_have_i18n_attrs(self):
        """Navigation links must carry data-i18n attributes."""
        for key in ("nav.dashboard", "nav.database"):
            self.assertIn(f'data-i18n="{key}"', self.src, f"data-i18n=\"{key}\" missing")

    def test_modal_buttons_have_i18n_attrs(self):
        """Confirm modal buttons must carry data-i18n attributes."""
        for key in ("modal.cancel", "modal.confirm_ok", "modal.auth_back", "modal.auth_login"):
            self.assertIn(f'data-i18n="{key}"', self.src)

    def test_footer_has_i18n_attr(self):
        """Footer copyright paragraph must carry data-i18n attribute."""
        self.assertIn('data-i18n="footer.copyright"', self.src)

    def test_brand_has_i18n_attr(self):
        """The navbar brand must carry data-i18n attribute."""
        self.assertIn('data-i18n="nav.brand"', self.src)

    def test_reapply_on_domcontentloaded(self):
        """Translations should be re-applied after DOMContentLoaded."""
        self.assertIn("applyTranslations", self.src)
        self.assertIn("DOMContentLoaded", self.src)


# ---------------------------------------------------------------------------
class TestIndexHtmlI18n(unittest.TestCase):
    """Checks that index.html carries the expected data-i18n attributes."""

    def setUp(self):
        self.assertTrue(INDEX_HTML.exists(), f"index.html not found at {INDEX_HTML}")
        self.src = INDEX_HTML.read_text(encoding="utf-8")

    def test_hero_title_attr(self):
        self.assertIn('data-i18n="index.welcome_title"', self.src)

    def test_hero_subtitle_attr(self):
        self.assertIn('data-i18n="index.welcome_subtitle"', self.src)

    def test_stat_labels_attrs(self):
        for key in ("index.total_files", "index.cataloged_files", "index.sources", "index.active_tasks"):
            self.assertIn(f'data-i18n="{key}"', self.src, f"Missing data-i18n for {key}")

    def test_quick_actions_heading_attr(self):
        self.assertIn('data-i18n="index.quick_actions"', self.src)

    def test_action_cards_attrs(self):
        for key in ("index.browse_db", "index.browse_db_desc", "index.task_center"):
            self.assertIn(f'data-i18n="{key}"', self.src)

    def test_recent_files_heading_attr(self):
        self.assertIn('data-i18n="index.recent_files"', self.src)

    def test_dynamic_table_uses_i18n_t(self):
        """Dynamic JS-rendered table headers should use I18n.t()."""
        self.assertIn("I18n.t('table.title')", self.src)
        self.assertIn("I18n.t('table.source')", self.src)
        self.assertIn("I18n.t('table.date')", self.src)

    def test_dynamic_messages_use_i18n_t(self):
        self.assertIn("I18n.t('index.no_files')", self.src)
        self.assertIn("I18n.t('index.load_error')", self.src)


# ---------------------------------------------------------------------------
class TestI18nFlaskIntegration(unittest.TestCase):
    """Integration tests: Flask test client renders pages with i18n support."""

    def setUp(self):
        try:
            from ai_actuarial.web.app import FLASK_AVAILABLE, create_app
        except ImportError:
            self.skipTest("Flask app cannot be imported")

        from ai_actuarial.web.app import FLASK_AVAILABLE

        if not FLASK_AVAILABLE:
            self.skipTest("Flask is not installed")

        import tempfile

        self.temp_dir = tempfile.mkdtemp()

        sites_config = {
            "defaults": {
                "user_agent": "test/1.0",
                "max_pages": 1,
                "max_depth": 1,
                "delay_seconds": 0,
                "file_exts": [".pdf"],
                "keywords": [],
            },
            "paths": {
                "db": os.path.join(self.temp_dir, "test.db"),
                "download_dir": os.path.join(self.temp_dir, "files"),
                "updates_dir": os.path.join(self.temp_dir, "updates"),
                "last_run_new": os.path.join(self.temp_dir, "last_run.json"),
            },
            "search": {"enabled": False, "max_results": 0, "delay_seconds": 0,
                       "languages": ["en"], "country": "us", "exclude_keywords": [], "queries": []},
            "sites": [],
        }

        import yaml
        sites_path = os.path.join(self.temp_dir, "sites.yaml")
        cats_path = os.path.join(self.temp_dir, "categories.yaml")
        with open(sites_path, "w") as f:
            yaml.dump(sites_config, f)
        with open(cats_path, "w") as f:
            yaml.dump({"categories": {}, "ai_filter_keywords": []}, f)

        from ai_actuarial.web.app import create_app
        app = create_app(
            config={
                "TESTING": True,
                "SITES_CONFIG_PATH": sites_path,
                "CATEGORIES_CONFIG_PATH": cats_path,
                "AUTH_ENABLED": False,
                "SECRET_KEY": "test-secret",
                "WTF_CSRF_ENABLED": False,
            }
        )
        self.client = app.test_client()

    def test_index_page_loads_i18n_js(self):
        """GET / should return HTML that includes the i18n.js <script> tag."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("i18n.js", html, "i18n.js not found in rendered index page")

    def test_index_page_has_lang_toggle(self):
        """Rendered index page should contain the language toggle button."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("lang-toggle-btn", html)

    def test_index_page_has_data_i18n_attrs(self):
        """Rendered index page should contain data-i18n attributes."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn('data-i18n="nav.dashboard"', html)
        self.assertIn('data-i18n="index.welcome_title"', html)

    def test_database_page_loads_i18n_js(self):
        """GET /database should also serve i18n.js."""
        resp = self.client.get("/database")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode("utf-8")
        self.assertIn("i18n.js", html)


# ---------------------------------------------------------------------------
TASKS_HTML = REPO_ROOT / "ai_actuarial" / "web" / "templates" / "tasks.html"
FILE_VIEW_HTML = REPO_ROOT / "ai_actuarial" / "web" / "templates" / "file_view.html"
CHAT_HTML = REPO_ROOT / "ai_actuarial" / "web" / "templates" / "chat.html"


class TestTasksPageI18n(unittest.TestCase):
    """Verify tasks.html carries data-i18n attributes for all sections."""

    def setUp(self):
        self.assertTrue(TASKS_HTML.exists(), f"tasks.html not found at {TASKS_HTML}")
        self.src = TASKS_HTML.read_text(encoding="utf-8")

    def test_page_title_attr(self):
        self.assertIn('data-i18n="tasks.title"', self.src)

    def test_task_card_attrs(self):
        for key in (
            "tasks.url_col", "tasks.url_col_desc",
            "tasks.file_import", "tasks.file_import_desc",
            "tasks.web_search", "tasks.web_search_desc",
            "tasks.quick_check", "tasks.quick_check_desc",
            "tasks.cataloging", "tasks.cataloging_desc",
            "tasks.md_convert", "tasks.md_convert_desc",
            "tasks.gen_chunks", "tasks.gen_chunks_desc",
            "tasks.build_idx", "tasks.build_idx_desc",
        ):
            self.assertIn(f'data-i18n="{key}"', self.src, f"Missing data-i18n for {key}")

    def test_active_history_section_attrs(self):
        for key in ("tasks.active", "tasks.loading_active", "tasks.history", "tasks.loading_history"):
            self.assertIn(f'data-i18n="{key}"', self.src)

    def test_web_search_modal_attrs(self):
        for key in (
            "tasks.web_search_modal_title", "tasks.search_query",
            "tasks.search_engine", "tasks.max_results",
            "tasks.site_filter", "tasks.use_defaults",
            "tasks.language_opt", "tasks.country_opt",
            "tasks.excl_kw_opt", "tasks.file_formats", "tasks.start_search",
        ):
            self.assertIn(f'data-i18n="{key}"', self.src, f"Missing data-i18n for {key}")

    def test_quick_check_modal_attrs(self):
        for key in (
            "tasks.quick_check_hint", "tasks.site_url",
            "tasks.keywords_opt", "tasks.max_pages", "tasks.depth",
            "tasks.start_quick_scan",
        ):
            self.assertIn(f'data-i18n="{key}"', self.src, f"Missing data-i18n for {key}")

    def test_catalog_modal_attrs(self):
        for key in (
            "tasks.catalog_title", "tasks.catalog_hint",
            "tasks.task_scope", "tasks.by_index", "tasks.by_category",
            "tasks.start_index", "tasks.scan_count", "tasks.retry_errors",
            "tasks.overwrite_existing", "tasks.ai_provider", "tasks.start_cataloging",
        ):
            self.assertIn(f'data-i18n="{key}"', self.src, f"Missing data-i18n for {key}")

    def test_url_collection_modal_attrs(self):
        for key in (
            "tasks.url_col_hint", "tasks.urls_label",
            "tasks.check_db", "tasks.start_url_col",
        ):
            self.assertIn(f'data-i18n="{key}"', self.src, f"Missing data-i18n for {key}")

    def test_file_import_modal_attrs(self):
        for key in (
            "tasks.file_import_hint", "tasks.dir_path",
            "tasks.recursive", "tasks.start_import",
        ):
            self.assertIn(f'data-i18n="{key}"', self.src, f"Missing data-i18n for {key}")

    def test_markdown_conversion_modal_attrs(self):
        for key in (
            "tasks.md_convert_hint", "tasks.conv_tool",
            "tasks.overwrite_md", "tasks.convert_files",
        ):
            self.assertIn(f'data-i18n="{key}"', self.src, f"Missing data-i18n for {key}")

    def test_chunk_generation_modal_attrs(self):
        for key in (
            "tasks.gen_chunks_hint", "tasks.chunk_profile",
            "tasks.chunk_model", "tasks.profile_name",
            "tasks.chunk_size", "tasks.chunk_overlap",
            "tasks.splitter", "tasks.tokenizer", "tasks.profile_version",
            "tasks.bind_to_kb", "tasks.no_bind", "tasks.binding_mode",
            "tasks.overwrite_profile",
        ):
            self.assertIn(f'data-i18n="{key}"', self.src, f"Missing data-i18n for {key}")

    def test_kb_index_build_modal_attrs(self):
        for key in (
            "tasks.build_idx_hint", "tasks.kb_label",
            "tasks.file_urls_opt", "tasks.incremental",
            "tasks.force_reindex", "tasks.submit_kb_idx",
        ):
            self.assertIn(f'data-i18n="{key}"', self.src, f"Missing data-i18n for {key}")


class TestFileViewI18n(unittest.TestCase):
    """Verify file_view.html carries data-i18n attributes."""

    def setUp(self):
        self.assertTrue(FILE_VIEW_HTML.exists(), f"file_view.html not found at {FILE_VIEW_HTML}")
        self.src = FILE_VIEW_HTML.read_text(encoding="utf-8")

    def test_page_header_attrs(self):
        self.assertIn('data-i18n="fv.back"', self.src)
        self.assertIn('data-i18n="fv.title"', self.src)

    def test_table_header_attrs(self):
        for key in (
            "fv.source_site", "fv.orig_url", "fv.source_page",
            "fv.content_type", "fv.file_size", "fv.local_path",
            "fv.collected_date", "fv.category", "fv.status",
            "fv.deletion_time",
        ):
            self.assertIn(f'data-i18n="{key}"', self.src, f"Missing data-i18n for {key}")

    def test_category_editor_attrs(self):
        self.assertIn('data-i18n="fv.choose_cat"', self.src)
        self.assertIn('data-i18n="fv.cat_hint"', self.src)

    def test_summary_keywords_attrs(self):
        for key in ("fv.summary", "fv.no_summary", "fv.keywords", "fv.no_keywords"):
            self.assertIn(f'data-i18n="{key}"', self.src, f"Missing data-i18n for {key}")

    def test_action_button_attrs(self):
        for key in (
            "fv.edit", "fv.save", "fv.cancel",
            "fv.catalog", "fv.download", "fv.delete",
            "fv.ai_explain", "fv.preview",
        ):
            self.assertIn(f'data-i18n="{key}"', self.src, f"Missing data-i18n for {key}")

    def test_markdown_section_attrs(self):
        for key in (
            "fv.md_content", "fv.view", "fv.md_edit", "fv.expand",
            "fv.no_md", "fv.convert_engine", "fv.overwrite_md",
            "fv.convert_btn", "fv.save_md",
        ):
            self.assertIn(f'data-i18n="{key}"', self.src, f"Missing data-i18n for {key}")

    def test_catalog_modal_attrs(self):
        for key in (
            "fv.catalog_modal_title", "fv.catalog_hint",
            "fv.catalog_from", "fv.overwrite_recompute",
            "fv.ai_provider", "fv.submit_catalog",
        ):
            self.assertIn(f'data-i18n="{key}"', self.src, f"Missing data-i18n for {key}")

    def test_chunk_modal_attrs(self):
        for key in (
            "fv.chunk_modal_title", "fv.chunk_hint",
            "fv.chunk_profile", "fv.bind_kb", "fv.no_bind",
            "fv.binding_mode", "fv.follow_latest", "fv.pin",
            "fv.overwrite_same", "fv.submit_chunk",
        ):
            self.assertIn(f'data-i18n="{key}"', self.src, f"Missing data-i18n for {key}")

    def test_delete_modal_uses_i18n_t(self):
        """JS-generated delete modal must use I18n.t()."""
        for key in ("fv.confirm_delete", "fv.confirm_delete_msg", "fv.confirm_delete_type"):
            self.assertIn(f"I18n.t('{key}')", self.src, f"Missing I18n.t for {key}")


class TestChatPageI18n(unittest.TestCase):
    """Verify chat.html carries data-i18n attributes."""

    def setUp(self):
        self.assertTrue(CHAT_HTML.exists(), f"chat.html not found at {CHAT_HTML}")
        self.src = CHAT_HTML.read_text(encoding="utf-8")

    def test_page_header_attrs(self):
        self.assertIn('data-i18n="chat.title"', self.src)
        self.assertIn('data-i18n="chat.subtitle"', self.src)

    def test_doc_explorer_attrs(self):
        for key in (
            "chat.explain_doc", "chat.filter_cat", "chat.all_cats",
            "chat.search_kw", "chat.select_doc", "chat.load_docs",
            "chat.click_load", "chat.click_load2", "chat.explain_sel",
        ):
            self.assertIn(f'data-i18n="{key}"', self.src, f"Missing data-i18n for {key}")

    def test_sidebar_attrs(self):
        self.assertIn('data-i18n="chat.conversations"', self.src)
        self.assertIn('data-i18n="chat.loading_convs"', self.src)

    def test_chat_controls_attrs(self):
        for key in (
            "chat.kb_select", "chat.auto_smart", "chat.all_kbs",
            "chat.model_sel", "chat.expert_mode", "chat.summary_mode",
            "chat.tutorial_mode", "chat.compare_mode",
        ):
            self.assertIn(f'data-i18n="{key}"', self.src, f"Missing data-i18n for {key}")

    def test_empty_state_attrs(self):
        self.assertIn('data-i18n="chat.start_title"', self.src)
        self.assertIn('data-i18n="chat.start_hint"', self.src)

    def test_input_send_attrs(self):
        self.assertIn('data-i18n-placeholder="chat.input_ph"', self.src)
        self.assertIn('data-i18n="chat.send"', self.src)

    def test_js_empty_states_use_i18n_t(self):
        """JS-generated empty state messages must use I18n.t()."""
        for key in ("chat.start_title", "chat.start_hint"):
            self.assertIn(f"I18n.t('{key}')", self.src, f"Missing I18n.t for {key}")

    def test_js_title_subtitle_use_i18n_t(self):
        """JS that sets chat-title textContent should use I18n.t."""
        for key in ("chat.new_conv", "chat.select_kb_hint"):
            self.assertIn(f"I18n.t('{key}')", self.src, f"Missing I18n.t for {key}")


class TestNewI18nKeysInJs(unittest.TestCase):
    """Verify specific new keys are present in both EN and ZH blocks."""

    def setUp(self):
        self.assertTrue(I18N_JS.exists())
        src = I18N_JS.read_text(encoding="utf-8")
        en_start = src.find("en: {")
        zh_start = src.find("zh: {")
        self.en_block = src[en_start:zh_start]
        self.zh_block = src[zh_start:]

    def _assert_in_both(self, key: str):
        self.assertIn(f"'{key}'", self.en_block, f"EN key '{key}' missing from i18n.js")
        self.assertIn(f"'{key}'", self.zh_block, f"ZH key '{key}' missing from i18n.js")

    def test_tasks_modal_keys(self):
        for key in (
            "tasks.web_search_modal_title", "tasks.search_query", "tasks.search_engine",
            "tasks.max_results", "tasks.start_search", "tasks.quick_check_hint",
            "tasks.start_quick_scan", "tasks.catalog_title", "tasks.catalog_hint",
            "tasks.start_cataloging", "tasks.url_col_hint", "tasks.start_url_col",
            "tasks.file_import_hint", "tasks.start_import", "tasks.md_convert_hint",
            "tasks.convert_files", "tasks.gen_chunks_hint", "tasks.submit_kb_idx",
        ):
            self._assert_in_both(key)

    def test_file_view_modal_keys(self):
        for key in (
            "fv.catalog_modal_title", "fv.catalog_hint", "fv.chunk_modal_title",
            "fv.chunk_hint", "fv.confirm_delete", "fv.overwrite_md",
            "fv.save_md", "fv.convert_btn",
        ):
            self._assert_in_both(key)

    def test_chat_new_keys(self):
        for key in (
            "chat.select_kb_hint", "chat.input_ph", "chat.type_search",
            "chat.kb_select_title", "chat.mode_sel_title",
        ):
            self._assert_in_both(key)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    unittest.main()
