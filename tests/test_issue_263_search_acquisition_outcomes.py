from __future__ import annotations

import json
import logging
import sqlite3
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import yaml

from ai_actuarial.cli import cmd_update
from ai_actuarial.collectors.base import CollectionConfig
from ai_actuarial.collectors.url import URLCollector
from ai_actuarial.crawler import Crawler, SiteConfig
from ai_actuarial.search import SearchResult
from ai_actuarial.search_acquisition import make_acquisition_outcome
from ai_actuarial.storage import Storage
from ai_actuarial.task_runtime import NativeTaskRuntime


def _storage(*, exists: bool = False, hash_exists: bool = False) -> MagicMock:
    storage = MagicMock()
    storage.file_exists.return_value = exists
    storage.file_exists_by_hash.return_value = hash_exists
    storage.get_blob.return_value = None
    return storage


def _crawler(tmp_path: Path, storage: MagicMock | None = None, *, stopped: bool = False) -> Crawler:
    return Crawler(
        storage=storage or _storage(),
        download_dir=str(tmp_path / "files"),
        user_agent="Issue263/1.0",
        stop_check=(lambda: stopped),
        default_delay_seconds=0,
    )


def _site(url: str, **overrides) -> SiteConfig:
    values = {
        "name": "Search Result",
        "url": url,
        "max_pages": 1,
        "max_depth": 1,
        "delay_seconds": 0,
        "file_exts": [".pdf"],
        "check_database": True,
    }
    values.update(overrides)
    return SiteConfig(**values)


def _run_search(
    tmp_path: Path,
    results: list[SearchResult],
    storage: MagicMock,
    *,
    task_id: str,
    stopped: bool = False,
    task_data: dict | None = None,
):
    runtime = NativeTaskRuntime(pipeline_baton_state_path=str(tmp_path / "baton.json"))
    runtime.active_tasks[task_id] = {"stop_requested": stopped}
    config = {
        "defaults": {
            "user_agent": "Issue263/1.0",
            "delay_seconds": 0,
            "file_exts": [".pdf"],
        },
        "search": {"max_results": 5, "languages": ["en"]},
    }
    with (
        patch("ai_actuarial.task_runtime.search_all", return_value=results),
        patch("ai_actuarial.task_runtime.get_search_runtime_credentials", return_value={}),
    ):
        payload = {"query": "actuarial AI"}
        payload.update(task_data or {})
        result = runtime._run_search_task(
            task_id,
            storage,
            config,
            str(tmp_path / "files"),
            payload,
        )
    return result


def _summary_total(summary: dict) -> int:
    dispositions = (
        "downloaded_new",
        "already_exists",
        "filtered",
        "access_blocked",
        "redirect_or_content_type_mismatch",
        "download_failed",
        "storage_failed",
        "stopped_or_timeout",
        "no_eligible_file_found",
    )
    return sum(int(summary[name]) for name in dispositions)


def _run_cli_search_outcomes(
    tmp_path: Path,
    specs: list[tuple[str, int, int, int]],
    *,
    site_branch: bool = False,
) -> int:
    results = [SearchResult(f"https://example.com/result-{index}.pdf", "test") for index in range(len(specs))]
    reports = {}
    for result, (disposition, downloaded, skipped, failed) in zip(results, specs):
        subreason = {
            "already_exists": "url",
            "filtered": "keyword",
            "access_blocked": "http_status",
            "no_eligible_file_found": "empty",
        }.get(disposition)
        reports[result.url] = SimpleNamespace(
            items=([{"url": result.url, "local_path": f"files/result-{len(reports)}.pdf"}] if downloaded else []),
            outcome=make_acquisition_outcome(
                disposition,
                url=result.url,
                http_status=403 if disposition == "access_blocked" else None,
                subreason=subreason,
                reason=disposition,
                downloaded=downloaded,
                skipped=skipped,
                failed=failed,
            ),
        )

    config_path = tmp_path / "cli-status.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "defaults": {
                    "user_agent": "Issue263/1.0",
                    "delay_seconds": 0,
                    "file_exts": [".pdf"],
                },
                "paths": {
                    "db": str(tmp_path / "cli-status.db"),
                    "download_dir": str(tmp_path / "files"),
                    "last_run_new": str(tmp_path / "last-run.json"),
                    "updates_dir": str(tmp_path / "updates"),
                },
                "search": {
                    "enabled": True,
                    "queries": [] if site_branch else ["global query"],
                    "max_results": 5,
                },
                "sites": (
                    [
                        {
                            "name": "Search Only",
                            "url": "https://example.com",
                            "acquisition_tools": ["search"],
                            "queries": ["site query"],
                        }
                    ]
                    if site_branch
                    else []
                ),
            }
        ),
        encoding="utf-8",
    )

    def acquire(_crawler, url: str, _cfg: SiteConfig, source_site: str, progress_callback=None):
        return reports[url]

    search_results = [results, []] if site_branch else [results]
    args = Namespace(config=str(config_path), site=None, max_pages=None, max_depth=None, no_search=False)
    with (
        patch.object(Crawler, "scan_page_for_files", return_value=[]),
        patch.object(Crawler, "scan_page_for_files_with_outcome", create=True, new=acquire),
        patch("ai_actuarial.cli.search_all", side_effect=search_results),
        patch("ai_actuarial.cli.get_search_runtime_credentials", return_value={}),
    ):
        return cmd_update(args)


def test_five_http_403_results_are_failed_and_fully_audited(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    results = [SearchResult(f"https://blocked.example/report-{index}.pdf", "test") for index in range(5)]

    def blocked(url: str, **_kwargs):
        raise RuntimeError(f"HTTP Error 403 for {url}")

    with patch.object(Crawler, "_request", side_effect=blocked):
        result = _run_search(tmp_path, results, _storage(), task_id="task-403")

    assert result.success is False
    assert result.items_downloaded == 0
    assert result.items_skipped == 0
    assert result.errors
    assert len(result.metadata["acquisition_outcomes"]) == 5
    summary = result.metadata["acquisition_summary"]
    assert summary["total"] == summary["outcome_count"] == 5
    assert summary["access_blocked"] == summary["failed"] == 5
    assert _summary_total(summary) == summary["total"]
    assert all(row["http_status"] == 403 for row in result.metadata["acquisition_outcomes"])

    log_text = (tmp_path / "data" / "task_logs" / "task-403.log").read_text(encoding="utf-8")
    assert log_text.count("disposition=access_blocked") == 5
    assert "access_blocked=5" in log_text

    history_runtime = NativeTaskRuntime(pipeline_baton_state_path=str(tmp_path / "history-baton.json"))
    history_runtime.active_tasks["task-history-403"] = {
        "id": "task-history-403",
        "name": "Blocked search",
        "type": "search",
    }
    history_runtime._finalize_task_success("task-history-403", "search", result)
    history = history_runtime.task_history[-1]
    assert history["status"] == "error"
    assert history["items_downloaded"] == 0
    assert history["errors"]
    assert history["metadata"]["acquisition_summary"]["access_blocked"] == 5


def test_five_exact_url_duplicates_are_completed_noop_and_skipped(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    results = [SearchResult(f"https://duplicate.example/report-{index}.pdf", "test") for index in range(5)]

    def fetched(url: str, **_kwargs):
        return b"%PDF", {"content-type": "application/pdf"}, url

    with patch.object(Crawler, "_request", side_effect=fetched):
        result = _run_search(tmp_path, results, _storage(exists=True), task_id="task-duplicates")

    assert result.success is True
    assert result.items_downloaded == 0
    assert result.items_skipped == 5
    assert result.errors == []
    assert result.metadata["no_op_reason"] == "already_exists"
    assert result.metadata["acquisition_summary"]["already_exists"] == 5
    assert _summary_total(result.metadata["acquisition_summary"]) == 5


def test_every_raw_discovery_result_gets_an_outcome_including_domain_filter(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    blocked_url = "https://example.com/blocked.pdf"
    results = [
        SearchResult(blocked_url, "test"),
        SearchResult(blocked_url, "test-duplicate"),
        SearchResult("https://outside.example/report.pdf", "test"),
    ]

    with patch.object(Crawler, "_request", side_effect=RuntimeError("HTTP Error 403")) as request:
        result = _run_search(
            tmp_path,
            results,
            _storage(),
            task_id="task-all-discoveries",
            task_data={"site": "example.com"},
        )

    summary = result.metadata["acquisition_summary"]
    assert summary["total"] == summary["outcome_count"] == 3
    assert summary["access_blocked"] == 2
    assert summary["filtered"] == summary["skipped"] == 1
    assert result.metadata["acquisition_outcomes"][2]["subreason"] == "domain"
    assert _summary_total(summary) == 3
    assert request.call_count == 2


def test_filtered_result_records_a_limited_keyword_subreason(tmp_path: Path) -> None:
    page_url = "https://example.com/research"
    html = '<html><body><a href="/general.pdf">General report</a></body></html>'
    crawler = _crawler(tmp_path)

    with (
        patch.object(
            crawler,
            "_request",
            return_value=(html.encode(), {"content-type": "text/html"}, page_url),
        ),
        patch.object(crawler, "_download_file") as download,
    ):
        report = crawler.scan_page_for_files_with_outcome(
            page_url,
            _site(page_url, keywords=["actuarial"]),
            source_site="test",
        )

    assert report.items == []
    assert report.outcome["disposition"] == "filtered"
    assert report.outcome["subreason"] == "keyword"
    assert report.outcome["skipped"] == 1
    download.assert_not_called()


def test_link_download_error_is_not_silently_continued(tmp_path: Path) -> None:
    page_url = "https://example.com/research"
    html = '<html><body><a href="/report.pdf">Report</a></body></html>'
    crawler = _crawler(tmp_path)

    with (
        patch.object(
            crawler,
            "_request",
            return_value=(html.encode(), {"content-type": "text/html"}, page_url),
        ),
        patch.object(crawler, "_download_file", side_effect=OSError("network reset with response body")),
    ):
        report = crawler.scan_page_for_files_with_outcome(page_url, _site(page_url), source_site="test")

    assert report.outcome["disposition"] == "download_failed"
    assert report.outcome["failed"] == 1
    assert "response body" not in report.outcome["reason"]


def test_storage_failure_has_a_structured_terminal_outcome(tmp_path: Path) -> None:
    url = "https://example.com/report.pdf"
    tmp_file = tmp_path / "download.part"
    tmp_file.write_bytes(b"%PDF")
    crawler = _crawler(tmp_path)

    with (
        patch.object(
            crawler,
            "_request",
            return_value=(b"%PDF", {"content-type": "application/pdf"}, url),
        ),
        patch.object(
            crawler,
            "_download_file",
            return_value=(tmp_file, {"content-type": "application/pdf"}, url, "sha", 4),
        ),
        patch.object(crawler, "_handle_file", side_effect=OSError("disk full: response body")),
    ):
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    assert report.outcome["disposition"] == "storage_failed"
    assert report.outcome["failed"] == 1
    assert "response body" not in report.outcome["reason"]


def test_storage_lookup_failure_has_a_structured_terminal_outcome(tmp_path: Path) -> None:
    url = "https://example.com/report.pdf"
    storage = _storage()
    storage.file_exists.side_effect = OSError("database unavailable: response body")
    crawler = _crawler(tmp_path, storage)

    with patch.object(
        crawler,
        "_request",
        return_value=(b"%PDF", {"content-type": "application/pdf"}, url),
    ):
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    assert report.outcome["disposition"] == "storage_failed"
    assert report.outcome["failed"] == 1
    assert "response body" not in report.outcome["reason"]


@pytest.mark.parametrize("legacy", [False, True], ids=["outcome", "legacy-rethrow"])
@pytest.mark.parametrize(
    "lookup_error",
    [
        pytest.param(OSError, id="os-error"),
        pytest.param(sqlite3.OperationalError, id="sqlite-operational-error"),
    ],
)
def test_direct_content_hash_lookup_failure_is_reported_and_cleans_staging(
    tmp_path: Path,
    legacy: bool,
    lookup_error: type[Exception],
) -> None:
    url = "https://example.com/report.pdf"
    final_url = "https://cdn.example.com/final-report.pdf"
    staged = tmp_path / "direct-hash-lookup.part"
    staged.write_bytes(b"%PDF")
    storage = _storage()
    storage.file_exists_by_hash.side_effect = lookup_error("content-hash lookup unavailable")
    crawler = _crawler(tmp_path, storage)

    with (
        patch.object(
            crawler,
            "_request",
            return_value=(b"%PDF", {"content-type": "application/pdf"}, url),
        ),
        patch.object(
            crawler,
            "_download_file",
            return_value=(staged, {"content-type": "application/pdf"}, final_url, "sha", 4),
        ),
        patch.object(crawler, "_handle_file") as handle,
    ):
        if legacy:
            with pytest.raises(lookup_error, match="content-hash lookup unavailable"):
                crawler.scan_page_for_files(url, _site(url), source_site="test")
            report = None
        else:
            report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    if report is not None:
        assert report.items == []
        assert report.outcome["disposition"] == "storage_failed"
        assert report.outcome["subreason"] == "storage"
        assert report.outcome["final_url"] == final_url
        assert report.outcome["downloaded"] == 0
        assert report.outcome["failed"] == 1
    assert not staged.exists()
    handle.assert_not_called()


def test_downloaded_filename_keyword_filter_has_a_structured_subreason(tmp_path: Path) -> None:
    url = "https://example.com/report.pdf"
    tmp_file = tmp_path / "download.part"
    tmp_file.write_bytes(b"%PDF")
    crawler = _crawler(tmp_path)

    with (
        patch.object(
            crawler,
            "_request",
            return_value=(b"%PDF", {"content-type": "application/pdf"}, url),
        ),
        patch.object(
            crawler,
            "_download_file",
            return_value=(
                tmp_file,
                {
                    "content-type": "application/pdf",
                    "content-disposition": 'attachment; filename="internal-report.pdf"',
                },
                url,
                "sha",
                4,
            ),
        ),
        patch.object(crawler, "_handle_file") as handle,
    ):
        report = crawler.scan_page_for_files_with_outcome(
            url,
            _site(url, exclude_keywords=["internal"]),
            source_site="test",
        )

    assert report.outcome["disposition"] == "filtered"
    assert report.outcome["subreason"] == "keyword"
    assert report.outcome["skipped"] == 1
    handle.assert_not_called()


def test_mixed_success_and_blocked_result_keeps_success_with_warning(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    ok_url = "https://example.com/new.pdf"
    blocked_url = "https://blocked.example/report.pdf"
    results = [SearchResult(ok_url, "test"), SearchResult(blocked_url, "test")]
    tmp_file = tmp_path / "download.part"
    tmp_file.write_bytes(b"%PDF")

    def request(url: str, **_kwargs):
        if url == blocked_url:
            raise RuntimeError(f"HTTP Error 403 for {url}")
        return b"%PDF", {"content-type": "application/pdf"}, url

    def download(url: str, _target: Path, **_kwargs):
        return tmp_file, {"content-type": "application/pdf"}, url, "sha", 4

    item = {"url": ok_url, "local_path": "files/new.pdf"}
    with (
        patch.object(Crawler, "_request", side_effect=request),
        patch.object(Crawler, "_download_file", side_effect=download),
        patch.object(Crawler, "_handle_file", return_value=item),
    ):
        result = _run_search(tmp_path, results, _storage(), task_id="task-mixed")

    assert result.success is True
    assert result.items_downloaded == 1
    assert result.metadata["acquisition_summary"]["downloaded_new"] == 1
    assert result.metadata["acquisition_summary"]["access_blocked"] == 1
    assert result.metadata["acquisition_summary"]["failed"] == 1
    assert result.metadata["warnings"]
    assert result.errors
    log_text = (tmp_path / "data" / "task_logs" / "task-mixed.log").read_text(encoding="utf-8")
    assert "[WARNING] Search acquisition completed with 1 failed result" in log_text


def test_zero_search_results_is_an_explicit_successful_noop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = _run_search(tmp_path, [], _storage(), task_id="task-empty")

    assert result.success is True
    assert result.errors == []
    assert result.metadata["search_no_results"] is True
    assert result.metadata["no_op_reason"] == "search_no_results"
    assert result.metadata["acquisition_outcomes"] == []
    assert result.metadata["acquisition_summary"]["total"] == 0


def test_page_without_candidates_is_no_eligible_file_found(tmp_path: Path) -> None:
    page_url = "https://example.com/research"
    crawler = _crawler(tmp_path)
    with patch.object(
        crawler,
        "_request",
        return_value=(b"<html><body>No reports</body></html>", {"content-type": "text/html"}, page_url),
    ):
        report = crawler.scan_page_for_files_with_outcome(page_url, _site(page_url), source_site="test")

    assert report.outcome["disposition"] == "no_eligible_file_found"
    assert report.outcome["skipped"] == 1


def test_ordinary_navigation_link_does_not_count_as_extension_filter(tmp_path: Path) -> None:
    page_url = "https://example.com/research"
    crawler = _crawler(tmp_path)
    html = b'<html><body><a href="/about">About</a></body></html>'
    with patch.object(
        crawler,
        "_request",
        return_value=(html, {"content-type": "text/html"}, page_url),
    ):
        report = crawler.scan_page_for_files_with_outcome(page_url, _site(page_url), source_site="test")

    assert report.outcome["disposition"] == "no_eligible_file_found"
    assert report.outcome["subreason"] == "empty"


@pytest.mark.parametrize("duplicate_subreason", ["normalized_url", "content_hash"])
def test_navigation_link_does_not_override_linked_duplicate_subreason(
    tmp_path: Path,
    duplicate_subreason: str,
) -> None:
    page_url = "https://example.com/research"
    raw_link = "HTTPS://Example.COM:443/report.pdf?b=2&a=1#section"
    normalized_link = "https://example.com/report.pdf?a=1&b=2"
    storage = _storage(hash_exists=duplicate_subreason == "content_hash")
    if duplicate_subreason == "normalized_url":
        storage.file_exists.side_effect = lambda candidate: candidate == normalized_link
    crawler = _crawler(tmp_path, storage)
    staged = tmp_path / f"{duplicate_subreason}.part"
    staged.write_bytes(b"same")
    html = (
        f'<html><body><a href="/about">About</a><a href="{raw_link}">Report</a></body></html>'.encode()
    )
    with (
        patch.object(crawler, "_request", return_value=(html, {"content-type": "text/html"}, page_url)),
        patch.object(
            crawler,
            "_download_file",
            return_value=(staged, {"content-type": "application/pdf"}, raw_link, "same-sha", 4),
        ) as download,
        patch.object(crawler, "_handle_file") as handle,
    ):
        report = crawler.scan_page_for_files_with_outcome(page_url, _site(page_url), source_site="test")

    assert report.outcome["disposition"] == "already_exists"
    assert report.outcome["subreason"] == duplicate_subreason
    handle.assert_not_called()
    if duplicate_subreason == "normalized_url":
        download.assert_not_called()


def test_recognized_disallowed_document_extension_is_still_filtered(tmp_path: Path) -> None:
    page_url = "https://example.com/research"
    crawler = _crawler(tmp_path)
    html = b'<html><body><a href="/report.docx">Report</a></body></html>'
    with patch.object(
        crawler,
        "_request",
        return_value=(html, {"content-type": "text/html"}, page_url),
    ):
        report = crawler.scan_page_for_files_with_outcome(page_url, _site(page_url), source_site="test")

    assert report.outcome["disposition"] == "filtered"
    assert report.outcome["subreason"] == "extension"


@pytest.mark.parametrize(
    ("url", "final_url"),
    [
        pytest.param(
            "https://example.com/report.docx",
            "https://example.com/report.docx",
            id="direct-url",
        ),
        pytest.param(
            "https://example.com/download",
            "https://example.com/report.docx",
            id="redirect-final-url",
        ),
    ],
)
def test_direct_disallowed_document_extension_is_filtered(
    tmp_path: Path,
    url: str,
    final_url: str,
) -> None:
    crawler = _crawler(tmp_path)
    with patch.object(
        crawler,
        "_request",
        return_value=(
            b"PK\x03\x04docx",
            {
                "content-type": (
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
            },
            final_url,
        ),
    ):
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    assert report.items == []
    assert report.outcome["disposition"] == "filtered"
    assert report.outcome["subreason"] == "extension"
    assert report.outcome["skipped"] == 1


def test_raw_disallowed_document_extension_is_filtered_before_403_request(tmp_path: Path) -> None:
    url = "https://example.com/report.docx"
    crawler = _crawler(tmp_path)
    with patch.object(
        crawler,
        "_request",
        side_effect=RuntimeError("HTTP Error 403 for report.docx"),
    ) as request:
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    request.assert_not_called()
    assert report.items == []
    assert report.outcome["disposition"] == "filtered"
    assert report.outcome["subreason"] == "extension"
    assert report.outcome["skipped"] == 1
    assert report.outcome["failed"] == 0


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("https://example.com/download", id="unknown-raw-extension"),
        pytest.param("https://example.com/report.pdf", id="allowed-raw-extension"),
    ],
)
def test_final_disallowed_document_extension_precedes_login_wall(
    tmp_path: Path,
    url: str,
) -> None:
    final_url = "https://example.com/report.docx"
    crawler = _crawler(tmp_path)
    with patch.object(
        crawler,
        "_request",
        return_value=(
            b"<html><title>Login required</title><body>Login required</body></html>",
            {"content-type": "text/html"},
            final_url,
        ),
    ):
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    assert report.items == []
    assert report.outcome["disposition"] == "filtered"
    assert report.outcome["subreason"] == "extension"
    assert report.outcome["skipped"] == 1
    assert report.outcome["failed"] == 0


def test_allowed_document_url_preserves_access_wall_priority(tmp_path: Path) -> None:
    url = "https://example.com/report.pdf"
    crawler = _crawler(tmp_path)
    with patch.object(
        crawler,
        "_request",
        return_value=(
            b"<html><title>Login required</title><body>Login required</body></html>",
            {"content-type": "text/html"},
            url,
        ),
    ):
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    assert report.outcome["disposition"] == "access_blocked"
    assert report.outcome["subreason"] == "login"
    assert report.outcome["failed"] == 1


def test_unknown_final_extension_preserves_redirect_mismatch(tmp_path: Path) -> None:
    url = "https://example.com/report.pdf"
    final_url = "https://example.com/archive.zip"
    crawler = _crawler(tmp_path)
    with patch.object(
        crawler,
        "_request",
        return_value=(b"PK\x03\x04zip", {"content-type": "application/zip"}, final_url),
    ):
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    assert report.outcome["disposition"] == "redirect_or_content_type_mismatch"
    assert report.outcome["subreason"] == "redirect"
    assert report.outcome["failed"] == 1


def test_unknown_direct_extension_is_not_misclassified_as_filtered(tmp_path: Path) -> None:
    url = "https://example.com/archive.zip"
    crawler = _crawler(tmp_path)
    with patch.object(
        crawler,
        "_request",
        return_value=(b"PK\x03\x04zip", {"content-type": "application/zip"}, url),
    ):
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    assert report.outcome["disposition"] == "no_eligible_file_found"
    assert report.outcome["subreason"] == "empty"


def test_outcome_and_task_log_redact_and_bound_sensitive_urls(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    secret = "do-not-leak"
    fragment_secret = "fragment-only-secret"
    url = (
        "https://blocked.example/report.pdf?token="
        f"{secret}&X-Amz-Signature={secret}&X-Amz-Credential={secret}"
        f"#access_token={fragment_secret}&padding="
        + ("x" * 900)
    )
    results = [SearchResult(url, "test")]

    def blocked(raw_url: str, **_kwargs):
        raise RuntimeError(f"HTTP Error 403 for {raw_url}; body={secret}")

    with patch.object(Crawler, "_request", side_effect=blocked):
        result = _run_search(tmp_path, results, _storage(), task_id="task-redaction")

    outcome = result.metadata["acquisition_outcomes"][0]
    serialized = json.dumps(outcome)
    assert secret not in serialized
    assert fragment_secret not in serialized
    assert "[REDACTED]" in outcome["url"]
    assert len(outcome["url"]) <= 512
    assert len(outcome["reason"]) <= 160
    log_text = (tmp_path / "data" / "task_logs" / "task-redaction.log").read_text(encoding="utf-8")
    assert secret not in log_text
    assert fragment_secret not in log_text
    assert "[REDACTED]" in log_text


def test_api_and_cli_search_use_the_same_shared_summary(tmp_path: Path, caplog, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    results = [
        SearchResult("https://example.com/new.pdf", "test"),
        SearchResult("https://example.com/blocked.pdf", "test"),
    ]
    reports = {
        results[0].url: SimpleNamespace(
            items=[{"url": results[0].url, "local_path": "files/new.pdf"}],
            outcome={
                "disposition": "downloaded_new",
                "url": results[0].url,
                "final_url": results[0].url,
                "http_status": None,
                "subreason": None,
                "reason": "downloaded 1 new file",
                "downloaded": 1,
                "skipped": 0,
                "failed": 0,
            },
        ),
        results[1].url: SimpleNamespace(
            items=[],
            outcome={
                "disposition": "access_blocked",
                "url": results[1].url,
                "final_url": None,
                "http_status": 403,
                "subreason": "http_status",
                "reason": "HTTP 403 access blocked",
                "downloaded": 0,
                "skipped": 0,
                "failed": 1,
            },
        ),
    }

    def acquire(_crawler, url: str, _cfg: SiteConfig, source_site: str, progress_callback=None):
        return reports[url]

    config_path = tmp_path / "sites.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "defaults": {
                    "user_agent": "Issue263/1.0",
                    "delay_seconds": 0,
                    "file_exts": [".pdf"],
                    "keywords": [],
                },
                "paths": {
                    "db": str(tmp_path / "index.db"),
                    "download_dir": str(tmp_path / "files"),
                    "last_run_new": str(tmp_path / "last-run.json"),
                    "updates_dir": str(tmp_path / "updates"),
                },
                "search": {"enabled": True, "queries": ["actuarial AI"], "max_results": 5},
                "sites": [],
            }
        ),
        encoding="utf-8",
    )
    args = Namespace(config=str(config_path), site=None, max_pages=None, max_depth=None, no_search=False)

    with (
        patch.object(Crawler, "scan_page_for_files", return_value=[]),
        patch.object(Crawler, "scan_page_for_files_with_outcome", create=True, new=acquire),
        patch("ai_actuarial.task_runtime.search_all", return_value=results),
        patch("ai_actuarial.task_runtime.get_search_runtime_credentials", return_value={}),
    ):
        api_result = _run_search(tmp_path, results, _storage(), task_id="task-api-cli")

    caplog.set_level(logging.INFO, logger="ai_actuarial.cli")
    with (
        patch.object(Crawler, "scan_page_for_files", return_value=[]),
        patch.object(Crawler, "scan_page_for_files_with_outcome", create=True, new=acquire),
        patch("ai_actuarial.cli.search_all", return_value=results),
        patch("ai_actuarial.cli.get_search_runtime_credentials", return_value={}),
    ):
        assert cmd_update(args) == 0

    summary_record = next(
        record for record in caplog.records if record.getMessage().startswith("Search acquisition summary: ")
    )
    cli_summary = json.loads(summary_record.getMessage().split(": ", 1)[1])
    assert cli_summary == api_result.metadata["acquisition_summary"]


@pytest.mark.parametrize("site_branch", [False, True], ids=["global-search", "site-search"])
def test_cli_all_failed_search_returns_nonzero(tmp_path: Path, monkeypatch, site_branch: bool) -> None:
    monkeypatch.chdir(tmp_path)
    assert _run_cli_search_outcomes(
        tmp_path,
        [("access_blocked", 0, 0, 1)],
        site_branch=site_branch,
    ) != 0


@pytest.mark.parametrize(
    "specs",
    [
        pytest.param([], id="zero-discovery"),
        pytest.param([("already_exists", 0, 1, 0)], id="duplicate-noop"),
        pytest.param([("filtered", 0, 1, 0)], id="filtered-noop"),
        pytest.param([("no_eligible_file_found", 0, 1, 0)], id="no-eligible-noop"),
        pytest.param(
            [("downloaded_new", 1, 0, 0), ("access_blocked", 0, 0, 1)],
            id="mixed-success-warning",
        ),
    ],
)
def test_cli_success_exit_status_for_non_operational_outcomes(
    tmp_path: Path,
    monkeypatch,
    specs: list[tuple[str, int, int, int]],
) -> None:
    monkeypatch.chdir(tmp_path)
    assert _run_cli_search_outcomes(tmp_path, specs) == 0


def test_cli_both_search_branches_consume_outcomes_without_legacy_scans(
    tmp_path: Path, caplog, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    site_result = SearchResult("https://site.example/filtered.pdf", "site-search")
    global_result = SearchResult("https://global.example/filtered.pdf", "global-search")

    def acquire(_crawler, url: str, _cfg: SiteConfig, source_site: str, progress_callback=None):
        return SimpleNamespace(
            items=[],
            outcome={
                "disposition": "filtered",
                "url": url,
                "final_url": url,
                "http_status": None,
                "subreason": "keyword",
                "reason": "filtered by keyword rule",
                "downloaded": 0,
                "skipped": 1,
                "failed": 0,
            },
        )

    config_path = tmp_path / "sites-both-branches.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "defaults": {"user_agent": "Issue263/1.0", "delay_seconds": 0},
                "paths": {
                    "db": str(tmp_path / "both-branches.db"),
                    "download_dir": str(tmp_path / "files"),
                    "last_run_new": str(tmp_path / "last-run-both.json"),
                    "updates_dir": str(tmp_path / "updates-both"),
                },
                "search": {"enabled": True, "queries": ["global query"], "max_results": 5},
                "sites": [
                    {
                        "name": "Search Only",
                        "url": "https://site.example",
                        "acquisition_tools": ["search"],
                        "queries": ["site query"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    args = Namespace(config=str(config_path), site=None, max_pages=None, max_depth=None, no_search=False)
    caplog.set_level(logging.INFO, logger="ai_actuarial.cli")

    with (
        patch.object(Crawler, "scan_page_for_files") as legacy_scan,
        patch.object(
            Crawler,
            "scan_page_for_files_with_outcome",
            autospec=True,
            side_effect=acquire,
        ) as outcome_scan,
        patch("ai_actuarial.cli.search_all", side_effect=[[site_result], [global_result]]) as search,
        patch("ai_actuarial.cli.get_search_runtime_credentials", return_value={}),
    ):
        assert cmd_update(args) == 0

    assert search.call_count == 2
    assert outcome_scan.call_count == 2
    legacy_scan.assert_not_called()
    summary_record = next(
        record for record in caplog.records if record.getMessage().startswith("Search acquisition summary: ")
    )
    summary = json.loads(summary_record.getMessage().split(": ", 1)[1])
    assert summary["total"] == summary["outcome_count"] == 2
    assert summary["filtered"] == summary["skipped"] == 2
    result_messages = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("Search acquisition result ")
    ]
    assert len(result_messages) == 2
    assert "result 1/2" in result_messages[0]
    assert "result 2/2" in result_messages[1]


def test_stop_produces_one_terminal_outcome_per_discovery_result(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    results = [
        SearchResult("https://example.com/one.pdf", "test"),
        SearchResult("https://example.com/two.pdf", "test"),
    ]
    with patch.object(Crawler, "_request") as request:
        result = _run_search(tmp_path, results, _storage(), task_id="task-stop", stopped=True)

    assert result.metadata["stopped"] is True
    assert len(result.metadata["acquisition_outcomes"]) == 2
    assert result.metadata["acquisition_summary"]["stopped_or_timeout"] == 2
    assert all(row["subreason"] == "stopped" for row in result.metadata["acquisition_outcomes"])
    request.assert_not_called()


def test_content_hash_duplicate_and_redirect_mismatch_are_distinct(tmp_path: Path) -> None:
    direct_url = "https://example.com/report.pdf"
    tmp_file = tmp_path / "download.part"
    tmp_file.write_bytes(b"same")
    duplicate_crawler = _crawler(tmp_path, _storage(hash_exists=True))
    with (
        patch.object(
            duplicate_crawler,
            "_request",
            return_value=(b"same", {"content-type": "application/pdf"}, direct_url),
        ),
        patch.object(
            duplicate_crawler,
            "_download_file",
            return_value=(tmp_file, {"content-type": "application/pdf"}, direct_url, "same-sha", 4),
        ),
        patch.object(duplicate_crawler, "_handle_file") as handle,
    ):
        duplicate = duplicate_crawler.scan_page_for_files_with_outcome(
            direct_url, _site(direct_url), source_site="test"
        )

    assert duplicate.outcome["disposition"] == "already_exists"
    assert duplicate.outcome["subreason"] == "content_hash"
    handle.assert_not_called()

    mismatch_crawler = _crawler(tmp_path)
    with patch.object(
        mismatch_crawler,
        "_request",
        return_value=(
            b"<html><body>Sign in</body></html>",
            {"content-type": "text/html"},
            "https://example.com/login",
        ),
    ):
        mismatch = mismatch_crawler.scan_page_for_files_with_outcome(
            direct_url, _site(direct_url), source_site="test"
        )

    assert mismatch.outcome["disposition"] == "redirect_or_content_type_mismatch"
    assert mismatch.outcome["failed"] == 1


@pytest.mark.parametrize("content_type", ["text/plain", "image/png"])
def test_file_like_url_rejects_incompatible_mime(tmp_path: Path, content_type: str) -> None:
    url = "https://example.com/report.pdf"
    staged = tmp_path / "mismatch.part"
    staged.write_bytes(b"not a pdf")
    crawler = _crawler(tmp_path)
    with (
        patch.object(crawler, "_request", return_value=(b"not a pdf", {"content-type": content_type}, url)),
        patch.object(
            crawler,
            "_download_file",
            return_value=(staged, {"content-type": content_type}, url, "sha", 9),
        ) as download,
        patch.object(crawler, "_handle_file", return_value={"url": url}) as handle,
    ):
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    assert report.outcome["disposition"] == "redirect_or_content_type_mismatch"
    assert report.outcome["subreason"] == "content_type"
    assert report.outcome["failed"] == 1
    download.assert_not_called()
    handle.assert_not_called()


@pytest.mark.parametrize("headers", [{}, {"content-type": "application/octet-stream"}])
def test_file_like_url_allows_uninformative_mime(tmp_path: Path, headers: dict[str, str]) -> None:
    url = "https://example.com/report.pdf"
    staged = tmp_path / "allowed-mime.part"
    staged.write_bytes(b"%PDF")
    item = {"url": url, "local_path": "files/report.pdf"}
    crawler = _crawler(tmp_path)
    with (
        patch.object(crawler, "_request", return_value=(b"%PDF", headers, url)),
        patch.object(crawler, "_download_file", return_value=(staged, headers, url, "sha", 4)),
        patch.object(crawler, "_handle_file", return_value=item),
    ):
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    assert report.items == [item]
    assert report.outcome["disposition"] == "downloaded_new"


def test_normalized_url_duplicate_is_distinct_from_exact_url_duplicate(tmp_path: Path) -> None:
    raw_url = "HTTPS://Example.COM:443/report.pdf?b=2&a=1#section"
    normalized_url = "https://example.com/report.pdf?a=1&b=2"
    storage = _storage()
    storage.file_exists.side_effect = lambda candidate: candidate == normalized_url
    crawler = _crawler(tmp_path, storage)

    with (
        patch.object(
            crawler,
            "_request",
            return_value=(b"%PDF", {"content-type": "application/pdf"}, raw_url),
        ),
        patch.object(crawler, "_download_file") as download,
    ):
        report = crawler.scan_page_for_files_with_outcome(raw_url, _site(raw_url), source_site="test")

    assert report.outcome["disposition"] == "already_exists"
    assert report.outcome["subreason"] == "normalized_url"
    download.assert_not_called()


def test_legacy_scan_page_list_caller_remains_compatible(tmp_path: Path) -> None:
    url = "https://example.com/report.pdf"
    item = {"url": url, "local_path": "files/report.pdf"}
    tmp_file = tmp_path / "download.part"
    tmp_file.write_bytes(b"%PDF")
    crawler = _crawler(tmp_path)
    with (
        patch.object(
            crawler,
            "_request",
            return_value=(b"%PDF", {"content-type": "application/pdf"}, url),
        ),
        patch.object(
            crawler,
            "_download_file",
            return_value=(tmp_file, {"content-type": "application/pdf"}, url, "sha", 4),
        ),
        patch.object(crawler, "_handle_file", return_value=item),
    ):
        assert crawler.scan_page_for_files(url, _site(url), source_site="test") == [item]


def test_url_collector_keeps_legacy_storage_exception_semantics(tmp_path: Path) -> None:
    url = "https://example.com/report.pdf"
    storage = _storage()
    storage.get_file_by_url.return_value = None
    crawler = _crawler(tmp_path, storage)
    tmp_file = tmp_path / "download.part"
    tmp_file.write_bytes(b"%PDF")
    with (
        patch.object(
            crawler,
            "_request",
            return_value=(b"%PDF", {"content-type": "application/pdf"}, url),
        ),
        patch.object(
            crawler,
            "_download_file",
            return_value=(tmp_file, {"content-type": "application/pdf"}, url, "sha", 4),
        ),
        patch.object(crawler, "_handle_file", side_effect=OSError("database unavailable")),
    ):
        result = URLCollector(storage, crawler).collect(
            CollectionConfig(
                name="URL regression",
                source_type="url",
                file_exts=[".pdf"],
                metadata={"urls": [url]},
            )
        )

    assert result.success is False
    assert result.items_found == 0
    assert result.errors and "database unavailable" in result.errors[0]


def test_legacy_list_preserves_direct_vs_linked_download_exception_semantics(tmp_path: Path) -> None:
    direct_url = "https://example.com/direct.pdf"
    direct = _crawler(tmp_path)
    with (
        patch.object(
            direct,
            "_request",
            return_value=(b"%PDF", {"content-type": "application/pdf"}, direct_url),
        ),
        patch.object(direct, "_download_file", side_effect=OSError("direct download failed")),
        pytest.raises(OSError, match="direct download failed"),
    ):
        direct.scan_page_for_files(direct_url, _site(direct_url), source_site="test")

    page_url = "https://example.com/research"
    linked = _crawler(tmp_path)
    with (
        patch.object(
            linked,
            "_request",
            return_value=(
                b'<html><body><a href="/linked.pdf">Report</a></body></html>',
                {"content-type": "text/html"},
                page_url,
            ),
        ),
        patch.object(linked, "_download_file", side_effect=OSError("linked download failed")),
    ):
        assert linked.scan_page_for_files(page_url, _site(page_url), source_site="test") == []


def test_legacy_list_propagates_linked_handler_and_page_content_failures(tmp_path: Path) -> None:
    page_url = "https://example.com/research"
    linked_url = "https://example.com/linked.pdf"
    tmp_file = tmp_path / "linked.part"
    tmp_file.write_bytes(b"%PDF")
    linked = _crawler(tmp_path)
    with (
        patch.object(
            linked,
            "_request",
            return_value=(
                f'<html><body><a href="{linked_url}">Report</a></body></html>'.encode(),
                {"content-type": "text/html"},
                page_url,
            ),
        ),
        patch.object(
            linked,
            "_download_file",
            return_value=(tmp_file, {"content-type": "application/pdf"}, linked_url, "sha", 4),
        ),
        patch.object(linked, "_handle_file", side_effect=OSError("linked handler failed")),
        pytest.raises(OSError, match="linked handler failed"),
    ):
        linked.scan_page_for_files(page_url, _site(page_url), source_site="test")

    page_content = _crawler(tmp_path)
    with (
        patch.object(
            page_content,
            "_request",
            return_value=(b"<html><body>Actuarial content</body></html>", {"content-type": "text/html"}, page_url),
        ),
        patch.object(page_content, "_handle_page_content", side_effect=OSError("page storage failed")),
        pytest.raises(OSError, match="page storage failed"),
    ):
        page_content.scan_page_for_files(
            page_url,
            _site(page_url, collect_page_content=True),
            source_site="test",
        )


def test_legacy_list_still_swallows_initial_request_failure(tmp_path: Path) -> None:
    url = "https://example.com/report.pdf"
    crawler = _crawler(tmp_path)
    with patch.object(crawler, "_request", side_effect=OSError("initial request failed")):
        assert crawler.scan_page_for_files(url, _site(url), source_site="test") == []


def test_linked_normalized_url_duplicate_keeps_its_subreason(tmp_path: Path) -> None:
    page_url = "https://example.com/research"
    raw_link = "HTTPS://Example.COM:443/report.pdf?b=2&a=1#section"
    normalized_link = "https://example.com/report.pdf?a=1&b=2"
    storage = _storage()
    storage.file_exists.side_effect = lambda candidate: candidate == normalized_link
    crawler = _crawler(tmp_path, storage)
    html = f'<html><body><a href="{raw_link}">Report</a></body></html>'
    with (
        patch.object(
            crawler,
            "_request",
            return_value=(html.encode(), {"content-type": "text/html"}, page_url),
        ),
        patch.object(crawler, "_download_file") as download,
    ):
        report = crawler.scan_page_for_files_with_outcome(page_url, _site(page_url), source_site="test")

    assert report.outcome["disposition"] == "already_exists"
    assert report.outcome["subreason"] == "normalized_url"
    download.assert_not_called()


def test_linked_content_hash_duplicate_keeps_its_subreason(tmp_path: Path) -> None:
    page_url = "https://example.com/research"
    linked_url = "https://example.com/report.pdf"
    tmp_file = tmp_path / "linked-hash.part"
    tmp_file.write_bytes(b"same")
    crawler = _crawler(tmp_path, _storage(hash_exists=True))
    with (
        patch.object(
            crawler,
            "_request",
            return_value=(
                f'<html><body><a href="{linked_url}">Report</a></body></html>'.encode(),
                {"content-type": "text/html"},
                page_url,
            ),
        ),
        patch.object(
            crawler,
            "_download_file",
            return_value=(tmp_file, {"content-type": "application/pdf"}, linked_url, "same-sha", 4),
        ),
        patch.object(crawler, "_handle_file") as handle,
    ):
        report = crawler.scan_page_for_files_with_outcome(page_url, _site(page_url), source_site="test")

    assert report.outcome["disposition"] == "already_exists"
    assert report.outcome["subreason"] == "content_hash"
    handle.assert_not_called()


def test_page_content_hash_duplicate_keeps_its_subreason(tmp_path: Path) -> None:
    page_url = "https://example.com/research"
    crawler = _crawler(tmp_path, _storage(hash_exists=True))
    with (
        patch.object(
            crawler,
            "_request",
            return_value=(b"<html><body>Research</body></html>", {"content-type": "text/html"}, page_url),
        ),
        patch.object(crawler, "_extract_text_from_html", return_value="x" * 200),
    ):
        report = crawler.scan_page_for_files_with_outcome(
            page_url,
            _site(page_url, collect_page_content=True),
            source_site="test",
        )

    assert report.outcome["disposition"] == "already_exists"
    assert report.outcome["subreason"] == "content_hash"


@pytest.mark.parametrize(
    ("page_url", "existing_url", "expected_subreason"),
    [
        (
            "https://example.com/research?a=1&b=2",
            "https://example.com/research?a=1&b=2",
            "url",
        ),
        (
            "HTTPS://Example.COM:443/research?b=2&a=1#section",
            "https://example.com/research?a=1&b=2",
            "normalized_url",
        ),
    ],
    ids=["exact-url", "normalized-url"],
)
def test_page_content_url_duplicate_preserves_exact_or_normalized_subreason(
    tmp_path: Path,
    page_url: str,
    existing_url: str,
    expected_subreason: str,
) -> None:
    storage = _storage()
    storage.file_exists.side_effect = lambda candidate: candidate == existing_url
    crawler = _crawler(tmp_path, storage)
    changed_content = "Changed actuarial page content. " * 10
    with (
        patch.object(
            crawler,
            "_request",
            return_value=(b"<html><body>Changed content</body></html>", {"content-type": "text/html"}, page_url),
        ),
        patch.object(crawler, "_extract_text_from_html", return_value=changed_content) as extract,
    ):
        report = crawler.scan_page_for_files_with_outcome(
            page_url,
            _site(page_url, collect_page_content=True),
            source_site="test",
        )

    assert report.outcome["disposition"] == "already_exists"
    assert report.outcome["subreason"] == expected_subreason
    storage.file_exists_by_hash.assert_not_called()
    extract.assert_not_called()


def test_staging_mkdir_failure_is_storage_failed(tmp_path: Path) -> None:
    url = "https://example.com/report.pdf"
    crawler = _crawler(tmp_path)
    with (
        patch.object(
            crawler,
            "_request",
            return_value=(b"%PDF", {"content-type": "application/pdf"}, url),
        ),
        patch.object(Path, "mkdir", side_effect=OSError("read-only staging directory")),
    ):
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    assert report.outcome["disposition"] == "storage_failed"
    assert report.outcome["subreason"] == "storage"


def test_staging_write_failure_is_storage_failed(tmp_path: Path) -> None:
    url = "https://example.com/report.pdf"
    crawler = _crawler(tmp_path)
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = 200
    response.headers = {"content-type": "application/pdf"}
    response.geturl.return_value = url
    response.read.side_effect = [b"%PDF", b""]
    staging_file = MagicMock()
    staging_file.__enter__.return_value = staging_file
    staging_file.write.side_effect = OSError("disk full")
    with (
        patch.object(
            crawler,
            "_request",
            return_value=(b"%PDF", {"content-type": "application/pdf"}, url),
        ),
        patch("ai_actuarial.crawler.resolve_safe_http_url", return_value=MagicMock()),
        patch.object(crawler, "_open_pinned_http", return_value=response),
        patch("builtins.open", return_value=staging_file),
    ):
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    assert report.outcome["disposition"] == "storage_failed"
    assert report.outcome["subreason"] == "storage"


def test_linked_html_access_walls_are_classified_before_mismatch(tmp_path: Path) -> None:
    page_url = "https://example.com/research"
    linked_url = "https://example.com/report.pdf"
    cases = (
        (b'<html><div id="cf-chl-widget">Verify you are human</div></html>', "challenge"),
        (b"<html><title>Login required</title><body>Login required</body></html>", "login"),
    )
    for index, (body, expected_subreason) in enumerate(cases):
        staged = tmp_path / f"access-wall-{index}.part"
        staged.write_bytes(body)
        crawler = _crawler(tmp_path)
        with (
            patch.object(
                crawler,
                "_request",
                return_value=(
                    f'<html><body><a href="{linked_url}">Report</a></body></html>'.encode(),
                    {"content-type": "text/html"},
                    page_url,
                ),
            ),
            patch.object(
                crawler,
                "_download_file",
                return_value=(staged, {"content-type": "text/html"}, linked_url, "sha", len(body)),
            ),
        ):
            report = crawler.scan_page_for_files_with_outcome(page_url, _site(page_url), source_site="test")

        assert report.outcome["disposition"] == "access_blocked"
        assert report.outcome["subreason"] == expected_subreason


def test_direct_staged_access_wall_uses_a_bounded_sample(tmp_path: Path) -> None:
    url = "https://example.com/report.pdf"
    staged = tmp_path / "direct-access-wall.part"
    staged.write_bytes(b"placeholder")
    crawler = _crawler(tmp_path)
    reader = MagicMock()
    reader.__enter__.return_value = reader
    reader.read.return_value = b"<html><body>Enable JavaScript to continue</body></html>"
    with (
        patch.object(
            crawler,
            "_request",
            return_value=(b"%PDF", {"content-type": "application/pdf"}, url),
        ),
        patch.object(
            crawler,
            "_download_file",
            return_value=(staged, {"content-type": "text/html"}, url, "sha", 11),
        ),
        patch.object(Path, "open", return_value=reader),
    ):
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    assert report.outcome["disposition"] == "access_blocked"
    assert report.outcome["subreason"] == "javascript"
    reader.read.assert_called_once_with(16384)


def test_stop_after_initial_request_prevents_direct_download(tmp_path: Path) -> None:
    url = "https://example.com/report.pdf"
    stop_check = MagicMock(side_effect=[False, True])
    crawler = Crawler(_storage(), str(tmp_path / "files"), "Issue263/1.0", stop_check=stop_check)
    with (
        patch.object(
            crawler,
            "_request",
            return_value=(b"%PDF", {"content-type": "application/pdf"}, url),
        ),
        patch.object(crawler, "_download_file") as download,
    ):
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    assert report.outcome["disposition"] == "stopped_or_timeout"
    assert report.outcome["subreason"] == "stopped"
    download.assert_not_called()


def test_stop_during_streaming_cleans_tmp_and_prevents_save(tmp_path: Path) -> None:
    url = "https://example.com/report.pdf"
    state = {"stopped": False, "reads": 0}

    def stop_check() -> bool:
        return state["stopped"]

    def read(_size: int = -1) -> bytes:
        state["reads"] += 1
        if state["reads"] == 1:
            state["stopped"] = True
            return b"%PDF streaming body"
        return b""

    crawler = Crawler(_storage(), str(tmp_path / "files"), "Issue263/1.0", stop_check=stop_check)
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = 200
    response.headers = {"content-type": "application/pdf"}
    response.geturl.return_value = url
    response.read.side_effect = read
    with (
        patch.object(
            crawler,
            "_request",
            return_value=(b"%PDF", {"content-type": "application/pdf"}, url),
        ),
        patch("ai_actuarial.crawler.resolve_safe_http_url", return_value=MagicMock()),
        patch.object(crawler, "_open_pinned_http", return_value=response),
        patch.object(crawler, "_handle_file") as handle,
    ):
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    assert report.outcome["disposition"] == "stopped_or_timeout"
    assert report.outcome["subreason"] == "stopped"
    assert not list((tmp_path / "files").rglob("*.part"))
    handle.assert_not_called()


def test_stop_after_direct_download_cleans_tmp_before_handler(tmp_path: Path) -> None:
    url = "https://example.com/report.pdf"
    staged = tmp_path / "stop-before-save.part"
    staged.write_bytes(b"%PDF")
    state = {"stopped": False}
    crawler = Crawler(
        _storage(),
        str(tmp_path / "files"),
        "Issue263/1.0",
        stop_check=lambda: state["stopped"],
    )

    def download(*_args, **_kwargs):
        state["stopped"] = True
        return staged, {"content-type": "application/pdf"}, url, "sha", 4

    with (
        patch.object(
            crawler,
            "_request",
            return_value=(b"%PDF", {"content-type": "application/pdf"}, url),
        ),
        patch.object(crawler, "_download_file", side_effect=download),
        patch.object(crawler, "_handle_file") as handle,
    ):
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    assert report.outcome["disposition"] == "stopped_or_timeout"
    assert report.outcome["subreason"] == "stopped"
    assert not staged.exists()
    handle.assert_not_called()


def test_quoted_site_search_flags_produce_same_real_api_and_cli_summary(
    tmp_path: Path, caplog, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result_url = "https://site.example/blocked-report.pdf"
    result = SearchResult(result_url, "site-search")
    config = {
        "defaults": {
            "user_agent": "Issue263/1.0",
            "delay_seconds": 0,
            "file_exts": [".pdf"],
            "keywords": [],
            "exclude_keywords": ["Newsletter"],
        },
        "paths": {
            "db": str(tmp_path / "parity.db"),
            "download_dir": str(tmp_path / "files"),
            "last_run_new": str(tmp_path / "last-run.json"),
            "updates_dir": str(tmp_path / "updates"),
        },
        "search": {
            "enabled": True,
            "engine": "auto",
            "max_results": 5,
            "exclude_keywords": ["blocked", "newsletter"],
        },
        "sites": [
            {
                "name": "Search Only",
                "url": "https://site.example",
                "acquisition_tools": ["search"],
                "queries": ["site query"],
                "exclude_keywords": ["internal"],
                "collect_linked_files": "false",
                "collect_page_content": "true",
            }
        ],
    }
    config_path = tmp_path / "site-parity.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    runtime = NativeTaskRuntime(pipeline_baton_state_path=str(tmp_path / "parity-baton.json"))
    site_config = runtime._site_configs_for_run(config, {})[0]
    task_data = runtime._site_query_search_task_data(site_config, "site query", config, {})
    runtime.active_tasks["task-site-parity"] = {"stop_requested": False}
    seen_configs: list[SiteConfig] = []
    seen_outcomes: list[dict] = []
    original_acquire = Crawler.scan_page_for_files_with_outcome

    def acquire(self, url: str, cfg: SiteConfig, source_site: str, progress_callback=None):
        seen_configs.append(cfg)
        report = original_acquire(self, url, cfg, source_site, progress_callback=progress_callback)
        seen_outcomes.append(report.outcome)
        return report

    with (
        patch("ai_actuarial.task_runtime.search_all", return_value=[result]),
        patch("ai_actuarial.task_runtime.get_search_runtime_credentials", return_value={}),
        patch.object(Crawler, "_request", return_value=(b"%PDF", {"content-type": "application/pdf"}, result_url)),
        patch.object(Crawler, "scan_page_for_files_with_outcome", new=acquire),
        patch.object(Crawler, "_download_file") as download,
    ):
        api_result = runtime._run_search_task(
            "task-site-parity",
            _storage(),
            config,
            str(tmp_path / "files"),
            task_data,
        )

    download.assert_not_called()
    caplog.set_level(logging.INFO, logger="ai_actuarial.cli")
    args = Namespace(config=str(config_path), site=None, max_pages=None, max_depth=None, no_search=False)
    staged = tmp_path / "cli-parity.part"
    staged.write_bytes(b"%PDF")
    with (
        patch("ai_actuarial.cli.search_all", side_effect=[[result], []]),
        patch("ai_actuarial.cli.get_search_runtime_credentials", return_value={}),
        patch.object(Crawler, "_request", return_value=(b"%PDF", {"content-type": "application/pdf"}, result_url)),
        patch.object(Crawler, "scan_page_for_files_with_outcome", new=acquire),
        patch.object(
            Crawler,
            "_download_file",
            return_value=(staged, {"content-type": "application/pdf"}, result_url, "sha", 4),
        ),
        patch.object(Crawler, "_handle_file", return_value={"url": result_url, "local_path": "files/report.pdf"}),
    ):
        assert cmd_update(args) == 0

    summary_record = next(
        record for record in reversed(caplog.records) if record.getMessage().startswith("Search acquisition summary: ")
    )
    cli_summary = json.loads(summary_record.getMessage().split(": ", 1)[1])
    assert cli_summary == api_result.metadata["acquisition_summary"]
    assert len(seen_configs) == 2
    assert all(cfg.collect_linked_files is False for cfg in seen_configs)
    assert all(cfg.collect_page_content is True for cfg in seen_configs)
    assert [outcome["subreason"] for outcome in seen_outcomes] == ["keyword", "keyword"]
    for seen_config in seen_configs:
        exclusions = [value.lower() for value in (seen_config.exclude_keywords or [])]
        assert set(exclusions) == {"newsletter", "internal", "blocked"}
        assert len(exclusions) == 3


def test_crawler_acquisition_logs_redact_success_duplicate_and_page_urls(
    tmp_path: Path, caplog
) -> None:
    secret = "crawler-log-secret"
    url = f"https://example.com/report.pdf?token={secret}"
    caplog.set_level(logging.DEBUG, logger="ai_actuarial.crawler")

    downloader = _crawler(tmp_path)
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = 200
    response.headers = {"content-type": "application/pdf"}
    response.geturl.return_value = url
    response.read.side_effect = [b"%PDF", b""]
    with (
        patch("ai_actuarial.crawler.resolve_safe_http_url", return_value=MagicMock()),
        patch.object(downloader, "_open_pinned_http", return_value=response),
    ):
        downloaded_path, *_ = downloader._download_file(url, tmp_path / "logged-download")
    downloaded_path.unlink()

    duplicate_storage = _storage(hash_exists=True)
    duplicate = _crawler(tmp_path, duplicate_storage)
    duplicate_tmp = tmp_path / "duplicate-log.part"
    duplicate_tmp.write_bytes(b"same")
    duplicate._handle_file(
        url,
        duplicate_tmp,
        {"content-type": "application/pdf"},
        "same-sha",
        4,
        _site(url),
        source_page_url=None,
    )

    page_duplicate = _crawler(tmp_path, _storage(hash_exists=True))
    with patch.object(page_duplicate, "_extract_text_from_html", return_value="x" * 200):
        page_duplicate._handle_page_content(url, "<html></html>", None, None, _site(url))

    page_saved = _crawler(tmp_path, _storage())
    with patch.object(page_saved, "_extract_text_from_html", return_value="y" * 200):
        page_saved._handle_page_content(url, "<html></html>", None, None, _site(url))

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert secret not in log_text
    assert "[REDACTED]" in log_text


def test_stop_after_html_parsing_prevents_page_content_persistence(tmp_path: Path) -> None:
    page_url = "https://example.com/research"
    state = {"stopped": False}
    crawler = Crawler(
        _storage(),
        str(tmp_path / "files"),
        "Issue263/1.0",
        stop_check=lambda: state["stopped"],
    )

    def parse_html(_html: str) -> str:
        state["stopped"] = True
        return "actuarial research"

    with (
        patch.object(
            crawler,
            "_request",
            return_value=(b"<html><body>Research</body></html>", {"content-type": "text/html"}, page_url),
        ),
        patch("ai_actuarial.crawler.html_to_text", side_effect=parse_html),
        patch.object(crawler, "_handle_page_content") as handle_page,
    ):
        report = crawler.scan_page_for_files_with_outcome(
            page_url,
            _site(page_url, collect_page_content=True),
            source_site="test",
        )

    assert report.items == []
    assert report.outcome["disposition"] == "stopped_or_timeout"
    assert report.outcome["subreason"] == "stopped"
    handle_page.assert_not_called()


def test_stop_after_direct_staging_validation_cleans_tmp_before_handler(tmp_path: Path) -> None:
    url = "https://example.com/report.pdf"
    staged = tmp_path / "direct-validated.part"
    staged.write_bytes(b"%PDF")
    state = {"stopped": False}
    crawler = Crawler(
        _storage(),
        str(tmp_path / "files"),
        "Issue263/1.0",
        stop_check=lambda: state["stopped"],
    )

    def validate_staged(*_args, **_kwargs):
        state["stopped"] = True
        return None

    with (
        patch.object(
            crawler,
            "_request",
            return_value=(b"%PDF", {"content-type": "application/pdf"}, url),
        ),
        patch.object(
            crawler,
            "_download_file",
            return_value=(staged, {"content-type": "application/pdf"}, url, "sha", 4),
        ),
        patch.object(crawler, "_staged_access_page_subreason", side_effect=validate_staged),
        patch.object(crawler, "_handle_file") as handle_file,
    ):
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    assert report.items == []
    assert report.outcome["disposition"] == "stopped_or_timeout"
    assert report.outcome["subreason"] == "stopped"
    assert not staged.exists()
    handle_file.assert_not_called()


def test_stop_after_linked_staging_validation_cleans_tmp_before_handler(tmp_path: Path) -> None:
    page_url = "https://example.com/research"
    linked_url = "https://example.com/report.pdf"
    staged = tmp_path / "linked-validated.part"
    staged.write_bytes(b"%PDF")
    state = {"stopped": False}
    crawler = Crawler(
        _storage(),
        str(tmp_path / "files"),
        "Issue263/1.0",
        stop_check=lambda: state["stopped"],
    )

    def validate_staged(*_args, **_kwargs):
        state["stopped"] = True
        return None

    html = f'<html><body><a href="{linked_url}">Report</a></body></html>'.encode()
    with (
        patch.object(crawler, "_request", return_value=(html, {"content-type": "text/html"}, page_url)),
        patch.object(
            crawler,
            "_download_file",
            return_value=(staged, {"content-type": "application/pdf"}, linked_url, "sha", 4),
        ),
        patch.object(crawler, "_staged_access_page_subreason", side_effect=validate_staged),
        patch.object(crawler, "_handle_file") as handle_file,
    ):
        report = crawler.scan_page_for_files_with_outcome(page_url, _site(page_url), source_site="test")

    assert report.items == []
    assert report.outcome["disposition"] == "stopped_or_timeout"
    assert report.outcome["subreason"] == "stopped"
    assert report.outcome["final_url"] == linked_url
    assert not staged.exists()
    handle_file.assert_not_called()


def test_staging_close_failure_is_storage_failed(tmp_path: Path) -> None:
    url = "https://example.com/report.pdf"
    crawler = _crawler(tmp_path)
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = 200
    response.headers = {"content-type": "application/pdf"}
    response.geturl.return_value = url
    response.read.side_effect = [b"%PDF", b""]
    staging_file = MagicMock()
    staging_file.__enter__.return_value = staging_file
    staging_file.__exit__.side_effect = OSError("disk full during close")
    staging_file.close.side_effect = OSError("disk full during close")
    with (
        patch.object(
            crawler,
            "_request",
            return_value=(b"%PDF", {"content-type": "application/pdf"}, url),
        ),
        patch("ai_actuarial.crawler.resolve_safe_http_url", return_value=MagicMock()),
        patch.object(crawler, "_open_pinned_http", return_value=response),
        patch("builtins.open", return_value=staging_file),
        patch.object(crawler, "_handle_file") as handle_file,
    ):
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    assert report.items == []
    assert report.outcome["disposition"] == "storage_failed"
    assert report.outcome["subreason"] == "storage"
    handle_file.assert_not_called()


def test_staging_response_read_failure_remains_download_failed(tmp_path: Path) -> None:
    url = "https://example.com/report.pdf"
    crawler = _crawler(tmp_path)
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = 200
    response.headers = {"content-type": "application/pdf"}
    response.geturl.return_value = url
    response.read.side_effect = OSError("connection reset during read")
    staging_file = MagicMock()
    staging_file.__enter__.return_value = staging_file
    with (
        patch.object(
            crawler,
            "_request",
            return_value=(b"%PDF", {"content-type": "application/pdf"}, url),
        ),
        patch("ai_actuarial.crawler.resolve_safe_http_url", return_value=MagicMock()),
        patch.object(crawler, "_open_pinned_http", return_value=response),
        patch("builtins.open", return_value=staging_file),
    ):
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    assert report.items == []
    assert report.outcome["disposition"] == "download_failed"
    assert report.outcome["subreason"] == "network"


def test_single_page_mixed_link_failure_is_auditable_in_runtime_and_cli(
    tmp_path: Path,
    caplog,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    page_url = "https://example.com/discovery"
    saved_url = "https://example.com/saved.pdf"
    secret = "linked-secret"
    blocked_url = f"https://example.com/blocked.pdf?token={secret}"
    result = SearchResult(page_url, "test")
    html = (
        f'<html><body><a href="{saved_url}">Saved</a>'
        f'<a href="{blocked_url}">Blocked</a></body></html>'
    ).encode()
    staged = tmp_path / "mixed-linked.part"
    staged.write_bytes(b"%PDF")
    item = {"url": saved_url, "local_path": "files/saved.pdf"}

    def download(url: str, _target: Path, **_kwargs):
        if url == blocked_url:
            raise RuntimeError(f"HTTP Error 403 for {url}")
        return staged, {"content-type": "application/pdf"}, url, "sha", 4

    with (
        patch.object(Crawler, "_request", return_value=(html, {"content-type": "text/html"}, page_url)),
        patch.object(Crawler, "_download_file", side_effect=download),
        patch.object(Crawler, "_handle_file", return_value=item),
    ):
        api_result = _run_search(tmp_path, [result], _storage(), task_id="task-single-page-mixed")

    outcome = api_result.metadata["acquisition_outcomes"][0]
    summary = api_result.metadata["acquisition_summary"]
    assert api_result.success is True
    assert api_result.items_downloaded == 1
    assert outcome["disposition"] == "access_blocked"
    assert outcome["subreason"] == "http_status"
    assert outcome["http_status"] == 403
    assert outcome["downloaded"] == outcome["failed"] == 1
    assert outcome["final_url"] == "https://example.com/blocked.pdf?token=[REDACTED]"
    assert secret not in json.dumps(outcome)
    assert summary["downloaded"] == summary["access_blocked"] == summary["failed"] == 1
    assert summary["downloaded_new"] == 0
    assert _summary_total(summary) == summary["total"] == 1
    assert api_result.errors and "acquisition access_blocked" in api_result.errors[0]
    assert api_result.metadata["warnings"] == api_result.errors

    config_path = tmp_path / "single-page-mixed.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "defaults": {
                    "user_agent": "Issue263/1.0",
                    "delay_seconds": 0,
                    "file_exts": [".pdf"],
                },
                "paths": {
                    "db": str(tmp_path / "single-page-mixed.db"),
                    "download_dir": str(tmp_path / "files"),
                    "last_run_new": str(tmp_path / "last-run.json"),
                    "updates_dir": str(tmp_path / "updates"),
                },
                "search": {"enabled": True, "queries": ["mixed query"], "max_results": 5},
                "sites": [],
            }
        ),
        encoding="utf-8",
    )
    args = Namespace(config=str(config_path), site=None, max_pages=None, max_depth=None, no_search=False)
    caplog.clear()
    caplog.set_level(logging.INFO, logger="ai_actuarial.cli")
    with (
        patch("ai_actuarial.cli.search_all", return_value=[result]),
        patch("ai_actuarial.cli.get_search_runtime_credentials", return_value={}),
        patch.object(Crawler, "_request", return_value=(html, {"content-type": "text/html"}, page_url)),
        patch.object(Crawler, "_download_file", side_effect=download),
        patch.object(Crawler, "_handle_file", return_value=item),
    ):
        assert cmd_update(args) == 0

    summary_record = next(
        record for record in caplog.records if record.getMessage().startswith("Search acquisition summary: ")
    )
    cli_summary = json.loads(summary_record.getMessage().split(": ", 1)[1])
    warning_record = next(
        record for record in caplog.records if record.getMessage().startswith("Search acquisition result 1/1:")
    )
    assert cli_summary == summary
    assert warning_record.levelno == logging.WARNING
    assert "disposition=access_blocked" in warning_record.getMessage()
    assert "http_status=403" in warning_record.getMessage()
    assert secret not in warning_record.getMessage()


@pytest.mark.parametrize(
    "lookup_error",
    [
        pytest.param(OSError, id="os-error"),
        pytest.param(sqlite3.OperationalError, id="sqlite-operational-error"),
    ],
)
def test_linked_storage_lookup_failure_keeps_prior_item_in_crawler_runtime_and_cli(
    tmp_path: Path,
    caplog,
    monkeypatch,
    lookup_error: type[Exception],
) -> None:
    monkeypatch.chdir(tmp_path)
    page_url = "https://example.com/discovery"
    saved_url = "https://example.com/saved.pdf"
    failed_url = "https://example.com/lookup-failed.pdf"
    result = SearchResult(page_url, "test")
    html = (
        f'<html><body><a href="{saved_url}">Saved</a>'
        f'<a href="{failed_url}">Lookup fails</a></body></html>'
    ).encode()
    staged = tmp_path / "lookup-mixed.part"
    staged.write_bytes(b"%PDF")
    item = {"url": saved_url, "local_path": "files/saved.pdf"}
    storage = _storage()

    def lookup(candidate: str) -> bool:
        if candidate == failed_url:
            raise lookup_error("database lookup unavailable")
        return False

    storage.file_exists.side_effect = lookup
    crawler = _crawler(tmp_path, storage)
    with (
        patch.object(crawler, "_request", return_value=(html, {"content-type": "text/html"}, page_url)),
        patch.object(
            crawler,
            "_download_file",
            return_value=(staged, {"content-type": "application/pdf"}, saved_url, "sha", 4),
        ),
        patch.object(crawler, "_handle_file", return_value=item),
    ):
        report = crawler.scan_page_for_files_with_outcome(page_url, _site(page_url), source_site="test")

    assert report.items == [item]
    assert report.outcome["disposition"] == "storage_failed"
    assert report.outcome["subreason"] == "storage"
    assert report.outcome["final_url"] == failed_url
    assert report.outcome["downloaded"] == report.outcome["failed"] == 1

    legacy_storage = _storage()
    legacy_storage.file_exists.side_effect = lookup
    legacy_crawler = _crawler(tmp_path, legacy_storage)
    with (
        patch.object(
            legacy_crawler,
            "_request",
            return_value=(html, {"content-type": "text/html"}, page_url),
        ),
        patch.object(
            legacy_crawler,
            "_download_file",
            return_value=(staged, {"content-type": "application/pdf"}, saved_url, "sha", 4),
        ),
        patch.object(legacy_crawler, "_handle_file", return_value=item),
        pytest.raises(lookup_error, match="database lookup unavailable"),
    ):
        legacy_crawler.scan_page_for_files(page_url, _site(page_url), source_site="test")

    with (
        patch.object(Crawler, "scan_page_for_files_with_outcome", return_value=report),
        patch("ai_actuarial.task_runtime.search_all", return_value=[result]),
        patch("ai_actuarial.task_runtime.get_search_runtime_credentials", return_value={}),
    ):
        api_result = _run_search(tmp_path, [result], _storage(), task_id="task-lookup-mixed")

    summary = api_result.metadata["acquisition_summary"]
    assert api_result.success is True
    assert api_result.items_downloaded == 1
    assert summary["downloaded"] == summary["storage_failed"] == summary["failed"] == 1
    assert _summary_total(summary) == summary["total"] == 1

    config_path = tmp_path / "lookup-mixed.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "defaults": {
                    "user_agent": "Issue263/1.0",
                    "delay_seconds": 0,
                    "file_exts": [".pdf"],
                },
                "paths": {
                    "db": str(tmp_path / "lookup-mixed.db"),
                    "download_dir": str(tmp_path / "files"),
                    "last_run_new": str(tmp_path / "last-run.json"),
                    "updates_dir": str(tmp_path / "updates"),
                },
                "search": {"enabled": True, "queries": ["lookup query"], "max_results": 5},
                "sites": [],
            }
        ),
        encoding="utf-8",
    )
    args = Namespace(config=str(config_path), site=None, max_pages=None, max_depth=None, no_search=False)
    caplog.clear()
    caplog.set_level(logging.INFO, logger="ai_actuarial.cli")
    with (
        patch.object(Crawler, "scan_page_for_files_with_outcome", return_value=report),
        patch("ai_actuarial.cli.search_all", return_value=[result]),
        patch("ai_actuarial.cli.get_search_runtime_credentials", return_value={}),
    ):
        assert cmd_update(args) == 0

    summary_record = next(
        record for record in caplog.records if record.getMessage().startswith("Search acquisition summary: ")
    )
    cli_summary = json.loads(summary_record.getMessage().split(": ", 1)[1])
    assert cli_summary == summary


@pytest.mark.parametrize("lookup_site", ["content-hash", "post-handler"])
@pytest.mark.parametrize(
    "lookup_error",
    [
        pytest.param(OSError, id="os-error"),
        pytest.param(sqlite3.OperationalError, id="sqlite-operational-error"),
    ],
)
def test_linked_staged_storage_lookup_failure_is_reported_and_cleaned(
    tmp_path: Path,
    lookup_site: str,
    lookup_error: type[Exception],
) -> None:
    page_url = "https://example.com/discovery"
    link_url = "https://example.com/report.pdf"
    html = f'<html><body><a href="{link_url}">Report</a></body></html>'.encode()
    staged = tmp_path / f"{lookup_site}.part"
    staged.write_bytes(b"%PDF")
    storage = _storage()
    storage.file_exists_by_hash.side_effect = (
        lookup_error("content-hash lookup unavailable")
        if lookup_site == "content-hash"
        else [False, lookup_error("post-handler lookup unavailable")]
    )
    crawler = _crawler(tmp_path, storage)

    with (
        patch.object(crawler, "_request", return_value=(html, {"content-type": "text/html"}, page_url)),
        patch.object(
            crawler,
            "_download_file",
            return_value=(staged, {"content-type": "application/pdf"}, link_url, "sha", 4),
        ),
        patch.object(crawler, "_handle_file", return_value=None) as handle,
    ):
        report = crawler.scan_page_for_files_with_outcome(page_url, _site(page_url), source_site="test")

    assert report.items == []
    assert report.outcome["disposition"] == "storage_failed"
    assert report.outcome["subreason"] == "storage"
    assert report.outcome["final_url"] == link_url
    assert report.outcome["downloaded"] == 0
    assert report.outcome["failed"] == 1
    assert not staged.exists()
    if lookup_site == "content-hash":
        handle.assert_not_called()
    else:
        handle.assert_called_once()


@pytest.mark.parametrize("download_path", ["direct", "linked"])
def test_staged_final_disallowed_extension_is_filtered_before_body_classification(
    tmp_path: Path,
    download_path: str,
) -> None:
    page_url = "https://example.com/discovery"
    allowed_url = "https://example.com/report.pdf"
    final_url = "https://example.com/report.docx"
    staged = tmp_path / f"{download_path}-final-docx.part"
    staged.write_bytes(b"<html><title>Login required</title><body>Login required</body></html>")
    crawler = _crawler(tmp_path)
    if download_path == "direct":
        requested_url = allowed_url
        response = (b"%PDF", {"content-type": "application/pdf"}, allowed_url)
    else:
        requested_url = page_url
        response = (
            f'<html><body><a href="{allowed_url}">Report</a></body></html>'.encode(),
            {"content-type": "text/html"},
            page_url,
        )

    with (
        patch.object(crawler, "_request", return_value=response),
        patch.object(
            crawler,
            "_download_file",
            return_value=(staged, {"content-type": "text/html"}, final_url, "sha", 68),
        ) as download,
    ):
        report = crawler.scan_page_for_files_with_outcome(
            requested_url,
            _site(requested_url),
            source_site="test",
        )

    download.assert_called_once()
    assert report.items == []
    assert report.outcome["disposition"] == "filtered"
    assert report.outcome["subreason"] == "extension"
    assert report.outcome["skipped"] == 1
    assert report.outcome["failed"] == 0
    assert not staged.exists()


def test_staged_unknown_final_extension_preserves_redirect_mismatch(tmp_path: Path) -> None:
    url = "https://example.com/report.pdf"
    final_url = "https://example.com/archive.zip"
    staged = tmp_path / "direct-final-zip.part"
    staged.write_bytes(b"PK\x03\x04zip")
    crawler = _crawler(tmp_path)

    with (
        patch.object(
            crawler,
            "_request",
            return_value=(b"%PDF", {"content-type": "application/pdf"}, url),
        ),
        patch.object(
            crawler,
            "_download_file",
            return_value=(staged, {"content-type": "application/zip"}, final_url, "sha", 7),
        ) as download,
    ):
        report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

    download.assert_called_once()
    assert report.outcome["disposition"] == "redirect_or_content_type_mismatch"
    assert report.outcome["subreason"] == "redirect"
    assert report.outcome["failed"] == 1
    assert not staged.exists()


@pytest.mark.parametrize(
    ("failure_point", "legacy"),
    [
        pytest.param("upsert_blob", False, id="blob-outcome"),
        pytest.param("upsert_file", False, id="file-outcome"),
        pytest.param("upsert_file", True, id="file-legacy-rethrow"),
    ],
)
def test_file_persistence_failure_removes_new_artifact_and_database_rows(
    tmp_path: Path,
    failure_point: str,
    legacy: bool,
) -> None:
    url = "https://example.com/report.pdf"
    storage = Storage(str(tmp_path / f"{failure_point}-{legacy}.db"))
    staged = tmp_path / f"{failure_point}-{legacy}.part"
    staged.write_bytes(b"%PDF")
    target = tmp_path / "files" / "example.com" / "report.pdf"
    if failure_point == "upsert_file":
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"pre-existing")
    crawler = _crawler(tmp_path, storage)

    try:
        with (
            patch.object(
                crawler,
                "_request",
                return_value=(b"%PDF", {"content-type": "application/pdf"}, url),
            ),
            patch.object(
                crawler,
                "_download_file",
                return_value=(staged, {"content-type": "application/pdf"}, url, "sha", 4),
            ),
            patch.object(
                storage,
                failure_point,
                side_effect=sqlite3.OperationalError(f"{failure_point} unavailable"),
            ),
        ):
            if legacy:
                with pytest.raises(sqlite3.OperationalError, match=failure_point):
                    crawler.scan_page_for_files(url, _site(url), source_site="test")
                report = None
            else:
                report = crawler.scan_page_for_files_with_outcome(url, _site(url), source_site="test")

        if report is not None:
            assert report.items == []
            assert report.outcome["disposition"] == "storage_failed"
            assert report.outcome["subreason"] == "storage"
            assert report.outcome["downloaded"] == 0
            assert report.outcome["failed"] == 1
        assert storage._conn.execute("SELECT COUNT(*) FROM blobs").fetchone()[0] == 0
        assert storage._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
        final_files = list((tmp_path / "files").rglob("*.pdf"))
        if failure_point == "upsert_file":
            assert final_files == [target]
            assert target.read_bytes() == b"pre-existing"
        else:
            assert final_files == []
    finally:
        storage.close()


class _FailingPageInsertConnection:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def execute(self, sql: str, parameters=()):
        if "INSERT OR IGNORE INTO files" in sql:
            raise sqlite3.OperationalError("page content insert unavailable")
        return self._connection.execute(sql, parameters)

    def __getattr__(self, name: str):
        return getattr(self._connection, name)


@pytest.mark.parametrize("legacy", [False, True], ids=["outcome", "legacy-rethrow"])
def test_page_content_insert_failure_removes_new_markdown_and_database_row(
    tmp_path: Path,
    legacy: bool,
) -> None:
    url = "https://example.com/research"
    storage = Storage(str(tmp_path / f"page-content-{legacy}.db"))
    storage._conn = _FailingPageInsertConnection(storage._conn)
    crawler = _crawler(tmp_path, storage)
    html = b"<html><title>Research</title><body>Actuarial research page</body></html>"
    cfg = _site(url, collect_page_content=True, collect_linked_files=False)

    try:
        with (
            patch.object(crawler, "_request", return_value=(html, {"content-type": "text/html"}, url)),
            patch.object(crawler, "_extract_text_from_html", return_value="page content " * 20),
        ):
            if legacy:
                with pytest.raises(sqlite3.OperationalError, match="page content insert"):
                    crawler.scan_page_for_files(url, cfg, source_site="test")
                report = None
            else:
                report = crawler.scan_page_for_files_with_outcome(url, cfg, source_site="test")

        if report is not None:
            assert report.items == []
            assert report.outcome["disposition"] == "storage_failed"
            assert report.outcome["subreason"] == "storage"
            assert report.outcome["downloaded"] == 0
            assert report.outcome["failed"] == 1
        assert list((tmp_path / "files").rglob("*.md")) == []
        assert storage._conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
    finally:
        storage.close()
