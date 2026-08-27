from __future__ import annotations

import copy
import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import unquote_plus, urlsplit, urlunsplit

_FILE_HANDLER_MARKER = "_ai_actuarial_application_file"
_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"']+"
    r"|//[^\s<>\"']+"
    r"|(?<![A-Za-z0-9._~%/-])(?:"
    r"/[^\s<>\"']*\?[^\s<>\"']*"
    r"|\?[^\s<>\"']+"
    r"|[A-Za-z0-9._~%-][A-Za-z0-9._~%/-]*\?[^\s<>\"']+"
    r")",
    re.IGNORECASE,
)
_SENSITIVE_QUERY_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "key",
    "password",
    "passwd",
    "secret",
    "signature",
    "sig",
    "auth",
    "authorization",
    "credential",
    "code",
}
_REDACTED = "[REDACTED]"


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return _redact_urls(super().format(copy.copy(record)))


def _redact_urls(message: str) -> str:
    return _URL_PATTERN.sub(lambda match: _redact_url(match.group(0)), message)


def _redact_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return "[REDACTED_URL]"
    netloc = parsed.netloc
    if "@" in netloc:
        _, _, host = netloc.rpartition("@")
        netloc = f"{_REDACTED}@{host}"

    def redact_query_value(match: re.Match[str]) -> str:
        prefix, key, separator, value = match.groups()
        if unquote_plus(key).lower() in _SENSITIVE_QUERY_KEYS:
            value = _REDACTED
        return f"{prefix}{key}{separator}{value}"

    query = re.sub(r"(^|[&;])([^=&;]+)(=)([^&;]*)", redact_query_value, parsed.query)
    return urlunsplit((parsed.scheme, netloc, parsed.path, query, parsed.fragment))


def configure_application_logging(*, log_file: Path, level: str) -> None:
    """Configure one console and one bounded application log destination."""
    root = logging.getLogger()
    resolved_level = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(resolved_level)

    formatter = _RedactingFormatter(_FORMAT)

    stream_handlers = [
        handler
        for handler in root.handlers
        if isinstance(handler, logging.StreamHandler)
        and not isinstance(handler, logging.FileHandler)
    ]
    if not stream_handlers:
        stream_handlers = [logging.StreamHandler()]
        root.addHandler(stream_handlers[0])
    primary_stream = stream_handlers[0]
    for extra_stream in stream_handlers[1:]:
        root.removeHandler(extra_stream)
        extra_stream.close()
    primary_stream.setLevel(resolved_level)
    primary_stream.setFormatter(formatter)

    target = Path(log_file).resolve()
    managed_handlers = [
        handler for handler in root.handlers if getattr(handler, _FILE_HANDLER_MARKER, False)
    ]
    matching_managed = next(
        (
            handler
            for handler in managed_handlers
            if isinstance(handler, logging.FileHandler)
            and Path(handler.baseFilename).resolve() == target
        ),
        None,
    )
    same_target_handlers = [
        handler
        for handler in root.handlers
        if isinstance(handler, logging.FileHandler)
        and Path(handler.baseFilename).resolve() == target
    ]

    if matching_managed is None:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            matching_managed = RotatingFileHandler(
                target,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
        except OSError as exc:
            root.warning("Unable to configure application log file %s: %s", target, exc)
            _route_uvicorn_through_root(resolved_level)
            return
        setattr(matching_managed, _FILE_HANDLER_MARKER, True)
        root.addHandler(matching_managed)

    matching_managed.setLevel(resolved_level)
    matching_managed.setFormatter(formatter)
    handlers_to_replace = [
        handler
        for handler in (*managed_handlers, *same_target_handlers)
        if handler is not matching_managed
    ]
    for handler in dict.fromkeys(handlers_to_replace):
        root.removeHandler(handler)
        handler.close()

    _route_uvicorn_through_root(resolved_level)


def _route_uvicorn_through_root(level: int) -> None:
    detached_handlers: dict[int, logging.Handler] = {}
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        detached_handlers.update((id(handler), handler) for handler in uvicorn_logger.handlers)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.setLevel(level)
        uvicorn_logger.propagate = True

    root_handler_ids = {id(handler) for handler in logging.getLogger().handlers}
    for handler_id, handler in detached_handlers.items():
        if handler_id not in root_handler_ids:
            handler.close()
