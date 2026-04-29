from pathlib import Path
from unittest.mock import patch

from config.settings import Settings
from doc_to_md import registry


def test_registry_supports_recommended_markdown_engines():
    assert registry._import_engine("opendataloader").__name__ == "OpenDataLoaderEngine"
    assert registry._import_engine("markitdown").__name__ == "MarkItDownEngine"
    assert registry._import_engine("mathpix").__name__ == "MathpixEngine"


def test_auto_pdf_candidates_start_with_recommended_default_tools():
    candidates = registry._auto_candidates(Path("sample.pdf"))

    assert candidates[:5] == ["opendataloader", "markitdown", "mistral", "docling", "mathpix"]


def test_settings_accepts_new_markdown_engine_configuration():
    with patch.dict(
        "os.environ",
        {
            "DEFAULT_ENGINE": "opendataloader",
            "MATHPIX_APP_ID": "mathpix-app",
            "MATHPIX_APP_KEY": "mathpix-key",
            "OPENDATALOADER_HYBRID": "http://127.0.0.1:5002",
            "OPENDATALOADER_USE_STRUCT_TREE": "true",
        },
        clear=False,
    ):
        settings = Settings(_env_file=None)

    assert settings.default_engine == "opendataloader"
    assert settings.mathpix_app_id == "mathpix-app"
    assert settings.mathpix_app_key == "mathpix-key"
    assert settings.opendataloader_hybrid == "http://127.0.0.1:5002"
    assert settings.opendataloader_use_struct_tree is True
