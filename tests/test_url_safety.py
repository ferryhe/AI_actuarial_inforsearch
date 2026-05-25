from __future__ import annotations

import ipaddress
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_actuarial.crawler import Crawler
from ai_actuarial.security.url_safety import SafeUrlResolution, UnsafeUrlError, ensure_safe_http_url
from ai_actuarial.storage import Storage


class _FakeResponse:
    def __init__(self, code: int, headers: dict[str, str] | None = None, body: bytes = b"", url: str = "") -> None:
        self.status = code
        self.headers = headers or {}
        self._body = body
        self._url = url
        self.closed = False

    def read(self, _size: int = -1) -> bytes:
        if _size is None or _size < 0:
            return self._body
        if not self._body:
            return b""
        chunk = self._body[:_size]
        self._body = self._body[_size:]
        return chunk

    def geturl(self) -> str:
        return self._url

    def getcode(self) -> int:
        return self.status

    def getheaders(self):
        return list(self.headers.items())

    def close(self) -> None:
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _resolver(host: str, _port=None, type=None, proto=None):
    mapping = {
        "public.example": [(2, type, proto, "", ("93.184.216.34", 0))],
        "safe.example": [(2, type, proto, "", ("93.184.216.34", 0))],
        "private.example": [(2, type, proto, "", ("10.0.0.8", 0))],
    }
    if host not in mapping:
        raise AssertionError(f"Unexpected host lookup: {host}")
    return mapping[host]


class TestEnsureSafeHttpUrl(unittest.TestCase):
    def test_allows_public_https_url(self) -> None:
        self.assertEqual(
            ensure_safe_http_url("https://public.example/report.pdf", resolver=_resolver),
            "https://public.example/report.pdf",
        )

    def test_blocks_local_and_private_targets(self) -> None:
        blocked_urls = [
            "file:///etc/passwd",
            "http://localhost/admin",
            "http://localhost./admin",
            "http://127.0.0.1/admin",
            "http://[::1]/admin",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.5/report.pdf",
            "http://2130706433/decimal-loopback",
        ]
        for url in blocked_urls:
            with self.subTest(url=url):
                with self.assertRaises(UnsafeUrlError):
                    ensure_safe_http_url(url, resolver=_resolver)

    def test_blocks_private_dns_resolution(self) -> None:
        with self.assertRaises(UnsafeUrlError):
            ensure_safe_http_url("https://private.example/report.pdf", resolver=_resolver)

    def test_malformed_url_raises_unsafe_url_error(self) -> None:
        with self.assertRaises(UnsafeUrlError):
            ensure_safe_http_url("http://[::1", resolver=_resolver)

    def test_invalid_port_raises_unsafe_url_error(self) -> None:
        for url in ("http://public.example:abc", "http://public.example:99999"):
            with self.subTest(url=url):
                with self.assertRaises(UnsafeUrlError):
                    ensure_safe_http_url(url, resolver=_resolver)


class TestCrawlerRedirectRevalidation(unittest.TestCase):
    def _make_crawler(self, tmp_dir: str) -> Crawler:
        storage = Storage(str(Path(tmp_dir) / "test.db"))
        self.addCleanup(storage.close)
        return Crawler(storage=storage, download_dir=tmp_dir, user_agent="TestAgent/1.0")

    def test_request_pins_validated_dns_for_connection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            crawler = self._make_crawler(tmp_dir)
            resolved_during_open: list[str] = []

            def fake_open(url, resolution, *, timeout: int):
                resolved_during_open.extend(str(address) for address in resolution.addresses)
                return _FakeResponse(200, headers={"Content-Type": "text/html"}, body=b"ok", url=url)

            with patch(
                "ai_actuarial.security.url_safety.socket.getaddrinfo",
                side_effect=_resolver,
            ), patch.object(crawler, "_open_pinned_http", side_effect=fake_open):
                body, _headers, final_url = crawler._request("https://public.example/start")

            self.assertEqual(b"ok", body)
            self.assertEqual("https://public.example/start", final_url)
            self.assertEqual(["93.184.216.34"], resolved_during_open)

    def test_request_rejects_redirect_to_private_ip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            crawler = self._make_crawler(tmp_dir)
            seen_urls: list[str] = []

            def fake_open(url, resolution, *, timeout: int):
                seen_urls.append(url)
                return _FakeResponse(
                    302,
                    headers={"Location": "http://127.0.0.1/admin"},
                    url=url,
                )

            with patch(
                "ai_actuarial.security.url_safety.socket.getaddrinfo",
                side_effect=_resolver,
            ), patch.object(crawler, "_open_pinned_http", side_effect=fake_open):
                with self.assertRaises(UnsafeUrlError):
                    crawler._request("https://public.example/start")

            self.assertEqual(["https://public.example/start"], seen_urls)

    def test_download_rejects_redirect_to_private_ip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            crawler = self._make_crawler(tmp_dir)
            seen_urls: list[str] = []
            target_dir = Path(tmp_dir) / "downloads"

            def fake_open(url, resolution, *, timeout: int):
                seen_urls.append(url)
                return _FakeResponse(
                    302,
                    headers={"Location": "http://127.0.0.1/file.pdf"},
                    url=url,
                )

            with patch(
                "ai_actuarial.security.url_safety.socket.getaddrinfo",
                side_effect=_resolver,
            ), patch.object(crawler, "_open_pinned_http", side_effect=fake_open):
                with self.assertRaises(UnsafeUrlError):
                    crawler._download_file("https://public.example/file.pdf", target_dir)

            self.assertEqual(["https://public.example/file.pdf"], seen_urls)
            self.assertFalse(any(target_dir.rglob("*.part")))

    def test_pinned_http_preserves_ipv6_literal_brackets_in_host_header(self) -> None:
        class FakeHTTPConnection:
            calls: list[dict] = []

            def __init__(self, host: str, *, port: int, timeout: int):
                self.host = host
                self.port = port
                self.timeout = timeout
                self.sock = None

            def request(self, method: str, target: str, headers: dict[str, str]):
                self.__class__.calls.append(
                    {"method": method, "target": target, "headers": headers, "host": self.host, "port": self.port}
                )

            def getresponse(self):
                return _FakeResponse(200, headers={"Content-Type": "text/plain"}, body=b"ok")

            def close(self) -> None:
                pass

        with tempfile.TemporaryDirectory() as tmp_dir:
            crawler = self._make_crawler(tmp_dir)
            resolution = SafeUrlResolution(
                url="http://[2001:4860:4860::8888]:8080/report",
                host="2001:4860:4860::8888",
                addresses=(ipaddress.ip_address("2001:4860:4860::8888"),),
            )
            with patch("ai_actuarial.crawler.http.client.HTTPConnection", FakeHTTPConnection), patch(
                "ai_actuarial.crawler.socket.create_connection", return_value=object()
            ):
                with crawler._open_pinned_http(resolution.url, resolution, timeout=30):
                    pass

        self.assertEqual("[2001:4860:4860::8888]:8080", FakeHTTPConnection.calls[0]["headers"]["Host"])


if __name__ == "__main__":
    unittest.main()
