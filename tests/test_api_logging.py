from __future__ import annotations

import io
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from ai_actuarial.api import logging_config
from ai_actuarial.api.logging_config import configure_application_logging


@pytest.fixture(autouse=True)
def restore_logging_state():
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    original_handler_state = {
        handler: (handler.level, handler.formatter) for handler in original_handlers
    }
    uvicorn_loggers = [
        logging.getLogger(name) for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
    ]
    original_uvicorn_state = [
        (logger, logger.handlers[:], logger.level, logger.propagate) for logger in uvicorn_loggers
    ]
    for logger in uvicorn_loggers:
        logger.handlers.clear()

    try:
        yield
    finally:
        for handler in root.handlers:
            if handler not in original_handlers:
                handler.close()
        root.handlers[:] = original_handlers
        root.setLevel(original_level)
        for handler, (level, formatter) in original_handler_state.items():
            handler.setLevel(level)
            handler.setFormatter(formatter)
        for logger, handlers, level, propagate in original_uvicorn_state:
            logger.handlers[:] = handlers
            logger.setLevel(level)
            logger.propagate = propagate


def _flush_root_handlers() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


def test_logging_setup_writes_file_and_keeps_stream_handler(tmp_path: Path) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    log_file = tmp_path / "mounted-data" / "app.log"

    configure_application_logging(log_file=log_file, level="INFO")
    configure_application_logging(log_file=log_file, level="INFO")

    logging.getLogger("ai_actuarial.test").info("global-log-file-record")
    logging.getLogger("uvicorn.error").info("uvicorn-log-file-record")
    _flush_root_handlers()

    contents = log_file.read_text(encoding="utf-8")
    assert contents.count("global-log-file-record") == 1
    assert contents.count("uvicorn-log-file-record") == 1
    rotating_handlers = [
        handler for handler in root.handlers if isinstance(handler, RotatingFileHandler)
    ]
    assert len(rotating_handlers) == 1
    assert rotating_handlers[0].maxBytes == 10 * 1024 * 1024
    assert rotating_handlers[0].backupCount == 5
    assert any(
        isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)
        for handler in root.handlers
    )
    assert logging.getLogger("uvicorn.error").propagate is True
    assert logging.getLogger("uvicorn.access").propagate is True
    assert logging.getLogger("uvicorn.error").handlers == []
    assert logging.getLogger("uvicorn.access").handlers == []


def test_logging_setup_keeps_one_console_handler_and_closes_extras(tmp_path: Path) -> None:
    root = logging.getLogger()
    first_output = io.StringIO()
    extra_output = io.StringIO()

    class TrackingStreamHandler(logging.StreamHandler):
        close_count = 0

        def close(self) -> None:
            self.close_count += 1
            super().close()

    primary = TrackingStreamHandler(first_output)
    extra = TrackingStreamHandler(extra_output)
    root.handlers[:] = [primary, extra]

    configure_application_logging(log_file=tmp_path / "app.log", level="INFO")
    logging.getLogger("uvicorn.access").info("single-console-record")
    _flush_root_handlers()

    assert primary in root.handlers
    assert extra not in root.handlers
    assert extra.close_count == 1
    assert first_output.getvalue().count("single-console-record") == 1
    assert "single-console-record" not in extra_output.getvalue()


def test_logging_reconfiguration_updates_managed_destinations_info_to_debug(tmp_path: Path) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    log_file = tmp_path / "app.log"

    configure_application_logging(log_file=log_file, level="INFO")
    configure_application_logging(log_file=log_file, level="DEBUG")

    logging.getLogger("ai_actuarial.test").debug("debug-after-reconfigure")
    _flush_root_handlers()

    assert "debug-after-reconfigure" in log_file.read_text(encoding="utf-8")
    assert root.level == logging.DEBUG
    assert all(handler.level == logging.DEBUG for handler in root.handlers)
    assert all(
        handler.formatter is not None
        and handler.formatter._fmt == "%(asctime)s %(levelname)s %(name)s %(message)s"
        for handler in root.handlers
    )


def test_uvicorn_loggers_honor_debug_and_error_reconfiguration(tmp_path: Path) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    log_file = tmp_path / "app.log"

    configure_application_logging(log_file=log_file, level="DEBUG")
    logging.getLogger("uvicorn.access").debug("uvicorn-debug-visible")
    configure_application_logging(log_file=log_file, level="ERROR")
    logging.getLogger("uvicorn.error").info("uvicorn-info-hidden")
    logging.getLogger("uvicorn.error").error("uvicorn-error-visible")
    _flush_root_handlers()

    contents = log_file.read_text(encoding="utf-8")
    assert "uvicorn-debug-visible" in contents
    assert "uvicorn-info-hidden" not in contents
    assert "uvicorn-error-visible" in contents
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        assert logger.level == logging.ERROR
        assert logger.propagate is True


def test_detached_uvicorn_file_handler_is_closed_without_duplicate_output(
    tmp_path: Path,
) -> None:
    root = logging.getLogger()
    console_output = io.StringIO()
    root.handlers[:] = [logging.StreamHandler(console_output)]
    log_file = tmp_path / "app.log"

    class TrackingFileHandler(logging.FileHandler):
        close_count = 0

        def close(self) -> None:
            self.close_count += 1
            super().close()

    replaced = TrackingFileHandler(log_file, encoding="utf-8")
    logging.getLogger("uvicorn").addHandler(replaced)
    logging.getLogger("uvicorn.error").addHandler(replaced)

    configure_application_logging(log_file=log_file, level="INFO")
    logging.getLogger("uvicorn.error").info("single-uvicorn-output")
    _flush_root_handlers()

    assert replaced.close_count == 1
    assert replaced.stream is None
    assert console_output.getvalue().count("single-uvicorn-output") == 1
    assert log_file.read_text(encoding="utf-8").count("single-uvicorn-output") == 1


def test_uvicorn_handler_also_attached_to_root_is_not_closed(tmp_path: Path) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    shared = logging.FileHandler(tmp_path / "shared.log", encoding="utf-8")
    root.addHandler(shared)
    logging.getLogger("uvicorn.access").addHandler(shared)

    configure_application_logging(log_file=tmp_path / "app.log", level="INFO")

    assert shared in root.handlers
    assert shared.stream is not None


def test_same_target_unmarked_file_handler_is_replaced_without_duplicate_writes(
    tmp_path: Path,
) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    log_file = tmp_path / "app.log"
    other_log_file = tmp_path / "other.log"
    same_target = logging.FileHandler(log_file, encoding="utf-8")
    unrelated = logging.FileHandler(other_log_file, encoding="utf-8")
    root.addHandler(same_target)
    root.addHandler(unrelated)

    configure_application_logging(log_file=log_file, level="INFO")
    logging.getLogger("ai_actuarial.test").info("single-target-write")
    _flush_root_handlers()

    assert log_file.read_text(encoding="utf-8").count("single-target-write") == 1
    matching = [
        handler
        for handler in root.handlers
        if isinstance(handler, logging.FileHandler)
        and Path(handler.baseFilename).resolve() == log_file.resolve()
    ]
    assert len(matching) == 1
    assert isinstance(matching[0], RotatingFileHandler)
    assert same_target not in root.handlers
    assert unrelated in root.handlers


def test_console_and_file_logs_redact_sensitive_url_parts(tmp_path: Path) -> None:
    root = logging.getLogger()
    console_output = io.StringIO()
    root.handlers[:] = [logging.StreamHandler(console_output)]
    log_file = tmp_path / "app.log"
    sensitive_url = (
        "https://alice:super-secret@example.com/api/items?keep=yes&token=abc123"
        "&signature=signed-value&API_KEY=key-value#result"
    )
    control_url = "https://example.com/api/items?keep=yes&mode=full#result"
    request_target = "/api/health?keep=yes&access_token=request-secret"
    path_relative = "items?token=path-secret"
    query_relative = "?token=query-secret"
    scheme_relative = "//bob:scheme-secret@example.com/path"

    configure_application_logging(log_file=log_file, level="INFO")
    logging.getLogger("ai_actuarial.test").info(
        "request %s control %s target %s path %s query %s scheme %s unrelated=%s",
        sensitive_url,
        control_url,
        request_target,
        path_relative,
        query_relative,
        scheme_relative,
        "super-secret",
    )
    _flush_root_handlers()

    for output in (console_output.getvalue(), log_file.read_text(encoding="utf-8")):
        assert (
            "https://[REDACTED]@example.com/api/items?keep=yes&token=[REDACTED]"
            "&signature=[REDACTED]&API_KEY=[REDACTED]#result"
        ) in output
        assert control_url in output
        assert "/api/health?keep=yes&access_token=[REDACTED]" in output
        assert "items?token=[REDACTED]" in output
        assert "?token=[REDACTED]" in output
        assert "//[REDACTED]@example.com/path" in output
        assert "unrelated=super-secret" in output
        assert "alice:super-secret" not in output
        assert "abc123" not in output
        assert "signed-value" not in output
        assert "key-value" not in output
        assert "request-secret" not in output
        assert "path-secret" not in output
        assert "query-secret" not in output
        assert "scheme-secret" not in output


def test_console_and_file_logs_redact_urls_in_exception_tracebacks(tmp_path: Path) -> None:
    root = logging.getLogger()
    console_output = io.StringIO()
    root.handlers[:] = [logging.StreamHandler(console_output)]
    log_file = tmp_path / "app.log"

    configure_application_logging(log_file=log_file, level="INFO")
    try:
        raise RuntimeError(
            "failed https://alice:exception-pass@example.com/path?token=exception-token"
        )
    except RuntimeError:
        logging.getLogger("ai_actuarial.test").exception("exception-path")
    _flush_root_handlers()

    for output in (console_output.getvalue(), log_file.read_text(encoding="utf-8")):
        assert "exception-path" in output
        assert "https://[REDACTED]@example.com/path?token=[REDACTED]" in output
        assert "exception-pass" not in output
        assert "exception-token" not in output


def test_malformed_url_is_safely_redacted_without_dropping_log_record(tmp_path: Path) -> None:
    root = logging.getLogger()
    console_output = io.StringIO()
    root.handlers[:] = [logging.StreamHandler(console_output)]

    configure_application_logging(log_file=tmp_path / "app.log", level="INFO")
    logging.getLogger("ai_actuarial.test").info(
        "malformed https://alice:secret@[invalid/?token=abc after"
    )
    _flush_root_handlers()

    contents = console_output.getvalue()
    assert "malformed [REDACTED_URL] after" in contents
    assert "alice:secret" not in contents
    assert "token=abc" not in contents


def test_file_handler_failure_keeps_console_and_uvicorn_logging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = logging.getLogger()
    output = io.StringIO()
    stream = logging.StreamHandler(output)
    root.handlers[:] = [stream]

    def fail_file_handler(*args, **kwargs):
        raise OSError("read-only log directory")

    monkeypatch.setattr(logging_config, "RotatingFileHandler", fail_file_handler)

    configure_application_logging(log_file=tmp_path / "app.log", level="INFO")
    logging.getLogger("uvicorn.error").error("uvicorn-console-fallback")
    _flush_root_handlers()

    contents = output.getvalue()
    assert "Unable to configure application log file" in contents
    assert contents.count("uvicorn-console-fallback") == 1
    assert root.handlers == [stream]
    assert logging.getLogger("uvicorn.error").handlers == []
    assert logging.getLogger("uvicorn.error").propagate is True
