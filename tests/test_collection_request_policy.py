from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from ai_actuarial.cli import _site_configs, cmd_update
from ai_actuarial.collectors.base import CollectionConfig
from ai_actuarial.collectors.url import URLCollector
from ai_actuarial.task_runtime import NativeTaskRuntime


def test_cli_site_config_preserves_acquisition_tools() -> None:
    sites = _site_configs(
        {
            "defaults": {"user_agent": "test", "max_pages": 20},
            "sites": [
                {
                    "name": "Search Only",
                    "url": "https://example.com/",
                    "acquisition_tools": ["search"],
                }
            ],
        }
    )

    assert sites[0].acquisition_tools == ["search"]


def test_cli_update_does_not_crawl_search_only_site(tmp_path: Path) -> None:
    config_path = tmp_path / "sites.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "defaults": {"user_agent": "test", "delay_seconds": 1.25},
                "paths": {
                    "db": str(tmp_path / "index.db"),
                    "download_dir": str(tmp_path / "files"),
                    "last_run_new": str(tmp_path / "last-run.json"),
                    "updates_dir": str(tmp_path / "updates"),
                },
                "search": {"enabled": False},
                "sites": [
                    {
                        "name": "Search Only",
                        "url": "https://example.com/",
                        "acquisition_tools": ["search"],
                        "queries": ["site:example.com report"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    args = Namespace(
        config=str(config_path),
        site=None,
        max_pages=None,
        max_depth=None,
        no_search=True,
    )

    with patch("ai_actuarial.cli.Crawler") as crawler_cls:
        assert cmd_update(args) == 0

    crawler_cls.return_value.crawl_site.assert_not_called()
    assert crawler_cls.call_args.kwargs["default_delay_seconds"] == 1.25


def test_ad_hoc_url_uses_crawler_default_delay() -> None:
    storage = MagicMock()
    storage.file_exists.return_value = False
    crawler = MagicMock()
    crawler.default_delay_seconds = 1.75
    crawler.scan_page_for_files.return_value = []
    collector = URLCollector(storage, crawler)

    result = collector.collect(
        CollectionConfig(
            name="Ad-hoc URL",
            source_type="url",
            check_database=False,
            metadata={"urls": ["https://example.com/report"]},
        )
    )

    assert result.success is True
    site_config = crawler.scan_page_for_files.call_args.args[1]
    assert site_config.delay_seconds == 1.75


def test_native_url_collection_preserves_zero_default_delay(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "sites.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "defaults": {"user_agent": "test", "delay_seconds": 0},
                "paths": {
                    "db": str(tmp_path / "index.db"),
                    "download_dir": str(tmp_path / "files"),
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    fake_crawler = MagicMock(default_delay_seconds=0)
    fake_crawler.scan_page_for_files.return_value = []

    with patch("ai_actuarial.task_runtime.Crawler", return_value=fake_crawler) as crawler_cls:
        result = NativeTaskRuntime()._run_collection(
            "task-url-zero-delay",
            "url",
            {
                "name": "Zero Delay URL",
                "urls": ["https://example.com/report"],
                "check_database": False,
            },
        )

    assert result.success is True
    assert crawler_cls.call_args.kwargs["default_delay_seconds"] == 0
    site_config = fake_crawler.scan_page_for_files.call_args.args[1]
    assert site_config.delay_seconds == 0


def test_canonical_soa_profiles_have_one_search_and_thirty_crawl_attempts() -> None:
    config = yaml.safe_load(Path("config/sites.yaml").read_text(encoding="utf-8"))
    sites = {site["name"]: site for site in config["sites"]}
    main = sites["Society of Actuaries (SOA)"]
    topic = sites["SOA AI Topic Landing (Focused)"]
    bulletin = sites["SOA AI Bulletin (Focused)"]

    assert main["acquisition_tools"] == ["search"]
    assert len(main["queries"]) == 4
    assert topic["url"].endswith("/artificial-intelligence-topic-landing/")
    assert topic["max_pages"] == 25
    assert bulletin["max_pages"] == 5
    assert topic["max_pages"] + bulletin["max_pages"] == 30
    assert topic["delay_seconds"] == bulletin["delay_seconds"] == 2.0
    assert all(
        pattern.startswith("^https://www\\.soa\\.org/") for pattern in topic["allow_url_patterns"]
    )
    assert all(
        pattern.startswith("^https://www\\.soa\\.org/")
        for pattern in bulletin["allow_url_patterns"]
    )
