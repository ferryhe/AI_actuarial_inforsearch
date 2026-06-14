from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


_IGNORED_METHODS = {"HEAD", "OPTIONS"}


def _signature(path: str, method: str) -> str:
    return f"{method} {path}"


def _join_paths(prefix: str, path: str) -> str:
    if not prefix:
        return path
    if not path:
        return prefix
    return f"{prefix.rstrip('/')}/{path.lstrip('/')}"


def _iter_routes(routes: Iterable[Any], prefix: str = "", parent_include_in_schema: bool = True) -> Iterable[tuple[Any, str | None, bool]]:
    for route in routes:
        include_in_schema = parent_include_in_schema and bool(getattr(route, "include_in_schema", True))
        path = getattr(route, "path", None)
        if isinstance(path, str):
            yield route, _join_paths(prefix, path), include_in_schema

        original_router = getattr(route, "original_router", None)
        if original_router is None:
            continue

        include_context = getattr(route, "include_context", None)
        nested_prefix = _join_paths(prefix, str(getattr(include_context, "prefix", "") or ""))
        nested_include = include_in_schema and bool(getattr(include_context, "include_in_schema", True))
        yield from _iter_routes(getattr(original_router, "routes", []), nested_prefix, nested_include)


def normalize_route_signature(signature: str) -> str:
    method, path = signature.split(" ", 1)
    path = re.sub(r"<(?:[^:>]+:)?[^>]+>", "{var}", path)
    path = re.sub(r"\{[^}:]+(?::path)?\}", "{var}", path)
    return f"{method} {path}"


def collect_fastapi_api_paths(app: Any) -> list[str]:
    paths: set[str] = set()
    for _route, path, include_in_schema in _iter_routes(app.router.routes):
        if not include_in_schema:
            continue
        if isinstance(path, str) and path.startswith("/api"):
            paths.add(path)
    return sorted(paths)


def collect_fastapi_route_signatures(app: Any) -> list[str]:
    signatures: set[str] = set()
    for route, path, include_in_schema in _iter_routes(app.router.routes):
        methods = getattr(route, "methods", None)
        if not include_in_schema:
            continue
        if not isinstance(path, str) or not path.startswith("/api") or not methods:
            continue
        for method in methods:
            if method in _IGNORED_METHODS:
                continue
            signatures.add(_signature(path, method))
    return sorted(signatures)



