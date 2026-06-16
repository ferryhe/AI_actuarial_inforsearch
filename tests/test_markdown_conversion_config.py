import os
from pathlib import Path

import pytest
import yaml

from ai_actuarial.markdown_conversion_config import (
    candidate_chain_for_path,
    get_markdown_conversion_options,
    list_conversion_tools,
    load_markdown_conversion_config,
    normalize_markdown_conversion_config,
    write_markdown_conversion_config,
)
from ai_actuarial.ai_runtime import OCRRuntime, apply_ocr_runtime_environment, resolve_ocr_runtime
from doc_to_md.registry import pick_auto_engine


def test_default_config_uses_auto_and_local_only_auto_chains(monkeypatch, tmp_path):
    missing = tmp_path / "missing-markdown.yaml"
    monkeypatch.setenv("MARKDOWN_CONVERSION_CONFIG_PATH", str(missing))

    cfg = load_markdown_conversion_config()

    assert cfg["default_tool"] == "auto"
    assert candidate_chain_for_path(Path("example.pdf"), cfg) == ["opendataloader", "markitdown", "docling", "local"]
    assert candidate_chain_for_path(Path("example.png"), cfg) == ["local"]
    for api_tool in ("mistral", "deepseekocr", "mathpix"):
        assert cfg["tools"][api_tool]["paid_or_api"] is True
        assert cfg["tools"][api_tool]["auto_enabled"] is False
        assert api_tool not in candidate_chain_for_path(Path("example.pdf"), cfg)


def test_configured_candidate_order_is_preserved_but_paid_tools_skip_auto_by_default():
    cfg = normalize_markdown_conversion_config(
        {
            "default_tool": "auto",
            "formats": {"pdf": {"candidate_chain": ["mistral", "markitdown", "mathpix", "local"]}},
        }
    )

    assert candidate_chain_for_path(Path("example.pdf"), cfg, auto_only=False) == ["mistral", "markitdown", "mathpix", "local"]
    assert candidate_chain_for_path(Path("example.pdf"), cfg, auto_only=True) == ["markitdown", "local"]


def test_paid_tool_can_join_auto_only_when_explicitly_enabled():
    cfg = normalize_markdown_conversion_config(
        {
            "tools": {"mistral": {"auto_enabled": True}},
            "formats": {"pdf": {"candidate_chain": ["mistral", "markitdown"]}},
        }
    )

    assert candidate_chain_for_path(Path("example.pdf"), cfg) == ["mistral", "markitdown"]


def test_conversion_tools_are_returned_in_config_order():
    cfg = normalize_markdown_conversion_config(
        {
            "default_tool": "auto",
            "formats": {"pdf": {"candidate_chain": ["markitdown", "docling", "local"]}},
        }
    )

    names = [tool["name"] for tool in list_conversion_tools(cfg)]

    assert names[:4] == ["auto", "markitdown", "docling", "local"]


def test_write_and_read_markdown_conversion_config(monkeypatch, tmp_path):
    target = tmp_path / "markdown_conversion.yaml"
    monkeypatch.setenv("MARKDOWN_CONVERSION_CONFIG_PATH", str(target))

    written = write_markdown_conversion_config(
        {
            "default_tool": "markitdown",
            "formats": {"default": {"candidate_chain": ["local"]}},
        }
    )
    loaded = load_markdown_conversion_config()
    raw_file = yaml.safe_load(target.read_text())

    assert written["default_tool"] == "markitdown"
    assert loaded["default_tool"] == "markitdown"
    assert raw_file["default_tool"] == "markitdown"
    assert get_markdown_conversion_options()["default_tool"] == "markitdown"


def test_registry_auto_picker_uses_config_without_paid_api(monkeypatch, tmp_path):
    target = tmp_path / "markdown_conversion.yaml"
    target.write_text(
        yaml.safe_dump(
            {
                "formats": {"pdf": {"candidate_chain": ["mistral", "local"]}},
            }
        )
    )
    monkeypatch.setenv("MARKDOWN_CONVERSION_CONFIG_PATH", str(target))

    assert pick_auto_engine(Path("example.pdf")) == "local"


def test_registry_auto_picker_does_not_fallback_when_config_disables_chain(monkeypatch, tmp_path):
    target = tmp_path / "markdown_conversion.yaml"
    target.write_text(
        yaml.safe_dump(
            {
                "tools": {"opendataloader": {"enabled": False}},
                "formats": {"pdf": {"candidate_chain": ["opendataloader"]}},
            }
        )
    )
    monkeypatch.setenv("MARKDOWN_CONVERSION_CONFIG_PATH", str(target))

    with pytest.raises(RuntimeError, match="No auto conversion candidates"):
        pick_auto_engine(Path("example.pdf"))
    assert candidate_chain_for_path(Path("example.pdf")) == []


def test_scan_count_limits_are_capped_to_safe_maximum():
    cfg = normalize_markdown_conversion_config(
        {
            "limits": {
                "default_scan_count": 999999999,
                "max_scan_count": 999999999,
            }
        }
    )

    assert cfg["limits"]["default_scan_count"] == 10000
    assert cfg["limits"]["max_scan_count"] == 10000


def test_resolve_ocr_runtime_auto_does_not_become_docling(monkeypatch):
    monkeypatch.delenv("DEFAULT_ENGINE", raising=False)

    runtime = resolve_ocr_runtime(engine_override="auto", yaml_config={"ai_config": {"ocr": {"provider": "local", "model": "docling"}}})

    assert runtime.engine == "auto"


def test_apply_ocr_runtime_environment_reuses_markdown_config_cache(monkeypatch, tmp_path):
    target = tmp_path / "markdown_conversion.yaml"
    target.write_text(yaml.safe_dump({"tools": {"markitdown": {"tuning": {"max_pages": 3}}}}), encoding="utf-8")
    monkeypatch.setenv("MARKDOWN_CONVERSION_CONFIG_PATH", str(target))

    import ai_actuarial.ai_runtime as ai_runtime
    import ai_actuarial.markdown_conversion_config as markdown_config

    ai_runtime._MARKDOWN_CONVERSION_TUNING_CACHE.clear()
    calls = []
    real_loader = markdown_config.load_markdown_conversion_config

    def counting_loader(path=None):
        calls.append(path)
        return real_loader(path)

    monkeypatch.setattr(markdown_config, "load_markdown_conversion_config", counting_loader)
    runtime = OCRRuntime(
        engine="markitdown",
        provider="local",
        model="markitdown",
        api_key=None,
        base_url=None,
        credential_source="test",
        raw_config={},
    )

    apply_ocr_runtime_environment(runtime)
    apply_ocr_runtime_environment(runtime)

    assert len(calls) == 1
