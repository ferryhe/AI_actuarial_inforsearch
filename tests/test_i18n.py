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
if __name__ == "__main__":
    unittest.main()
