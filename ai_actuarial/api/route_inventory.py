from __future__ import annotations

import re
from typing import Any


_IGNORED_METHODS = {"HEAD", "OPTIONS"}


def _signature(path: str, method: str) -> str:
    return f"{method} {path}"


def normalize_route_signature(signature: str) -> str:
    method, path = signature.split(" ", 1)
    path = re.sub(r"<(?:[^:>]+:)?[^>]+>", "{var}", path)
    path = re.sub(r"\{[^}:]+(?::path)?\}", "{var}", path)
    return f"{method} {path}"


def collect_fastapi_api_paths(app: Any) -> list[str]:
    paths: set[str] = set()
    for route in app.router.routes:
        path = getattr(route, "path", None)
        if getattr(route, "include_in_schema", True) is False:
            continue
        if isinstance(path, str) and path.startswith("/api"):
            paths.add(path)
    return sorted(paths)


def collect_fastapi_route_signatures(app: Any) -> list[str]:
    signatures: set[str] = set()
    for route in app.router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if getattr(route, "include_in_schema", True) is False:
            continue
        if not isinstance(path, str) or not path.startswith("/api") or not methods:
            continue
        for method in methods:
            if method in _IGNORED_METHODS:
                continue
            signatures.add(_signature(path, method))
    return sorted(signatures)



