from __future__ import annotations

import ipaddress
from pathlib import Path
from unittest.mock import MagicMock, patch

from curl_cffi import CurlOpt

from ai_actuarial.crawler import Crawler, SiteConfig
from ai_actuarial.security import SafeUrlResolution


class _FakeCurlResponse:
    def __init__(self, body: bytes = b"ok") -> None:
        self.status_code = 200
        self.headers = {"content-type": "text/plain"}
        self.url = "https://public.example/report"
        self._body = body
        self.closed = False

    def iter_content(self, chunk_size: int | None = None):
        size = chunk_size or len(self._body)
        for offset in range(0, len(self._body), size):
            yield self._body[offset : offset + size]

    def close(self) -> None:
        self.closed = True


def _crawler(tmp_path: Path) -> Crawler:
    storage = MagicMock()
    storage.file_exists.return_value = False
    return Crawler(
        storage=storage,
        download_dir=str(tmp_path),
        user_agent="RespectfulBot/1.0",
        default_delay_seconds=2.0,
    )


def test_pinned_curl_uses_validated_ip_and_manual_redirects(tmp_path: Path) -> None:
    crawler = _crawler(tmp_path)
    response = _FakeCurlResponse(b"payload")
    session = MagicMock()
    session.get.return_value = response
    resolution = SafeUrlResolution(
        url="https://public.example/report",
        host="public.example",
        addresses=(ipaddress.ip_address("93.184.216.34"),),
    )

    with (
        patch("ai_actuarial.crawler._curl_requests.Session", return_value=session) as session_cls,
        patch.object(crawler, "_pace_request") as pace,
    ):
        with crawler._open_pinned_curl(
            resolution.url,
            resolution,
            timeout=30,
            delay_seconds=2.0,
        ) as opened:
            assert opened.read() == b"payload"

    options = session_cls.call_args.kwargs["curl_options"]
    assert options[CurlOpt.RESOLVE] == ["public.example:443:93.184.216.34"]
    assert session_cls.call_args.kwargs["impersonate"] == "chrome"
    assert session_cls.call_args.kwargs["default_headers"] is False
    assert session_cls.call_args.kwargs["trust_env"] is False
    session.get.assert_called_once_with(
        resolution.url,
        headers={"User-Agent": "RespectfulBot/1.0"},
        timeout=30,
        allow_redirects=False,
        stream=True,
    )
    pace.assert_called_once_with(resolution.url, 2.0)
    assert response.closed is True


def test_request_pacer_uses_configured_delay_as_random_minimum(tmp_path: Path) -> None:
    crawler = _crawler(tmp_path)
    crawler._next_request_at["https://example.com:443"] = 12.0

    with (
        patch("ai_actuarial.crawler.time.monotonic", side_effect=[10.0, 12.25]),
        patch("ai_actuarial.crawler.time.sleep") as sleep,
        patch("ai_actuarial.crawler.random.uniform", return_value=3.0) as uniform,
    ):
        crawler._pace_request("https://example.com/report", 2.0)

    sleep.assert_called_once_with(2.0)
    uniform.assert_called_once_with(2.0, 3.0)
    assert crawler._next_request_at["https://example.com:443"] == 15.25


def test_validated_ipv4_address_is_tried_before_ipv6(tmp_path: Path) -> None:
    crawler = _crawler(tmp_path)
    response = _FakeCurlResponse()
    session = MagicMock()
    session.get.return_value = response
    resolution = SafeUrlResolution(
        url="https://dual-stack.example/report",
        host="dual-stack.example",
        addresses=(
            ipaddress.ip_address("2606:2800:220:1:248:1893:25c8:1946"),
            ipaddress.ip_address("93.184.216.34"),
        ),
    )

    with (
        patch.object(crawler, "_curl_session_for", return_value=session) as session_for,
        patch.object(crawler, "_pace_request"),
    ):
        with crawler._open_pinned_curl(
            resolution.url,
            resolution,
            timeout=30,
            delay_seconds=2.0,
        ):
            pass

    assert session_for.call_args.args[2] == ipaddress.ip_address("93.184.216.34")


def test_max_pages_is_a_hard_page_attempt_limit(tmp_path: Path) -> None:
    crawler = _crawler(tmp_path)
    root = "https://example.com/"
    links = "".join(f'<a href="https://example.com/page-{index}">Page</a>' for index in range(10))

    def request(url: str, **_kwargs):
        if url == root:
            return f"<html><body>{links}</body></html>".encode(), {}, url
        raise TimeoutError("timed out")

    cfg = SiteConfig(
        name="Bounded Site",
        url=root,
        max_pages=3,
        max_depth=1,
        delay_seconds=0,
    )
    with (
        patch.object(crawler, "_load_sitemap", return_value=[]),
        patch.object(crawler, "_request", side_effect=request) as fetch,
    ):
        assert crawler.crawl_site(cfg) == []

    assert fetch.call_count == 3
    diagnostic = crawler.get_last_crawl_diagnostic()
    assert diagnostic["pages_attempted"] == 3
    assert diagnostic["pages_visited"] == 1


def test_scan_page_applies_site_delay_to_page_and_file_requests(tmp_path: Path) -> None:
    crawler = _crawler(tmp_path)
    page_url = "https://example.com/research"
    file_url = "https://example.com/globalassets/report.pdf"
    html = f'<html><body><a href="{file_url}">Report</a></body></html>'
    downloaded = tmp_path / "download.part"
    downloaded.write_bytes(b"%PDF fake")
    cfg = SiteConfig(
        name="Ad-hoc URL",
        url=page_url,
        delay_seconds=2.5,
        check_database=False,
    )

    with (
        patch.object(
            crawler,
            "_request",
            return_value=(html.encode(), {"content-type": "text/html"}, page_url),
        ) as request,
        patch.object(
            crawler,
            "_download_file",
            return_value=(downloaded, {}, file_url, "sha", downloaded.stat().st_size),
        ) as download,
        patch.object(crawler, "_handle_file", return_value=None),
    ):
        crawler.scan_page_for_files(page_url, cfg, source_site="manual")

    request.assert_called_once_with(page_url, delay_seconds=2.5)
    assert download.call_args.kwargs["delay_seconds"] == 2.5
