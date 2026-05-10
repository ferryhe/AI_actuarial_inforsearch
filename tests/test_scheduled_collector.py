from unittest.mock import MagicMock

from ai_actuarial.collectors.base import CollectionConfig
from ai_actuarial.collectors.scheduled import ScheduledCollector
from ai_actuarial.crawler import SiteConfig


def test_scheduled_collector_records_site_outcome_metadata_for_zero_and_blocked_results() -> None:
    storage = MagicMock()
    crawler = MagicMock()
    crawler.crawl_site.side_effect = [
        [],
        RuntimeError("0 pages visited"),
        RuntimeError("403 Forbidden by Cloudflare"),
    ]
    collector = ScheduledCollector(storage, crawler)

    result = collector.collect(
        CollectionConfig(
            name="Scheduled",
            source_type="adhoc",
            metadata={
                "site_configs": [
                    SiteConfig(name="Empty Site", url="https://empty.example"),
                    SiteConfig(name="No Pages Site", url="https://nopages.example"),
                    SiteConfig(name="Blocked Site", url="https://blocked.example"),
                ]
            },
        )
    )

    site_results = result.metadata["site_results"]
    assert site_results[0]["name"] == "Empty Site"
    assert site_results[0]["items_found"] == 0
    assert site_results[0]["success"] is True
    assert site_results[0]["failed"] is False
    assert site_results[0]["fallback_reason"] == "zero_results"

    assert site_results[1]["name"] == "No Pages Site"
    assert site_results[1]["items_found"] == 0
    assert site_results[1]["success"] is False
    assert site_results[1]["failed"] is True
    assert site_results[1]["blocked"] is True
    assert site_results[1]["fallback_reason"] == "zero_pages_visited"
    assert "0 pages visited" in site_results[1]["error_text"]

    assert site_results[2]["name"] == "Blocked Site"
    assert site_results[2]["items_found"] == 0
    assert site_results[2]["success"] is False
    assert site_results[2]["failed"] is True
    assert site_results[2]["blocked"] is True
    assert site_results[2]["fallback_reason"] == "http_403"
    assert "403 Forbidden" in site_results[2]["error_text"]


def test_scheduled_collector_preserves_crawler_diagnostic_for_swallowed_empty_failure() -> None:
    storage = MagicMock()
    crawler = MagicMock()
    crawler.crawl_site.return_value = []
    crawler.get_last_crawl_diagnostic.return_value = {
        "pages_visited": 0,
        "request_errors": ["https://blocked.example: HTTP Error 429: Too Many Requests"],
        "error_text": "https://blocked.example: HTTP Error 429: Too Many Requests",
    }
    collector = ScheduledCollector(storage, crawler)

    result = collector.collect(
        CollectionConfig(
            name="Scheduled",
            source_type="scheduled",
            metadata={"site_configs": [SiteConfig(name="Blocked Empty", url="https://blocked.example")]},
        )
    )

    site_result = result.metadata["site_results"][0]
    assert result.success is False
    assert any("HTTP Error 429" in error for error in result.errors)
    assert site_result["items_found"] == 0
    assert site_result["success"] is False
    assert site_result["failed"] is True
    assert site_result["blocked"] is True
    assert site_result["fallback_reason"] == "http_429"
    assert "HTTP Error 429" in site_result["error_text"]


def test_scheduled_collector_marks_generic_diagnostic_error_failed() -> None:
    storage = MagicMock()
    crawler = MagicMock()
    crawler.crawl_site.return_value = []
    crawler.get_last_crawl_diagnostic.return_value = {
        "pages_visited": 0,
        "request_errors": ["https://error.example: connection reset by peer"],
        "error_text": "https://error.example: connection reset by peer",
    }
    collector = ScheduledCollector(storage, crawler)

    result = collector.collect(
        CollectionConfig(
            name="Scheduled",
            source_type="scheduled",
            metadata={"site_configs": [SiteConfig(name="Errored Empty", url="https://error.example")]},
        )
    )

    site_result = result.metadata["site_results"][0]
    assert result.success is False
    assert any("connection reset" in error for error in result.errors)
    assert site_result["items_found"] == 0
    assert site_result["success"] is False
    assert site_result["failed"] is True
    assert site_result["blocked"] is False
    assert site_result["fallback_reason"] == "error"
    assert "connection reset" in site_result["error_text"]
