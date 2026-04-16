from __future__ import annotations

from collections.abc import Iterable
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


def collect_flask_route_inventory(flask_app: Any) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for rule in flask_app.url_map.iter_rules():
        path = str(rule)
        if path.startswith("/static"):
            continue
        methods = sorted(method for method in rule.methods if method not in _IGNORED_METHODS)
        inventory.append(
            {
                "path": path,
                "methods": methods,
                "is_api": path.startswith("/api"),
                "endpoint": rule.endpoint,
            }
        )
    inventory.sort(key=lambda item: item["path"])
    return inventory


def collect_route_signatures(route_inventory: Iterable[dict[str, Any]], *, api_only: bool) -> list[str]:
    signatures: set[str] = set()
    for item in route_inventory:
        if api_only and not item.get("is_api"):
            continue
        path = str(item["path"])
        for method in item.get("methods", []):
            signatures.add(_signature(path, str(method)))
    return sorted(signatures)


def collect_legacy_only_route_signatures(
    legacy_signatures: Iterable[str],
    native_signatures: Iterable[str],
) -> list[str]:
    native_normalized = {normalize_route_signature(signature) for signature in native_signatures}
    return sorted(
        signature for signature in legacy_signatures if normalize_route_signature(signature) not in native_normalized
    )


def collect_native_override_signatures(
    legacy_signatures: Iterable[str],
    native_signatures: Iterable[str],
) -> list[str]:
    legacy_by_normalized: dict[str, list[str]] = {}
    for signature in legacy_signatures:
        legacy_by_normalized.setdefault(normalize_route_signature(signature), []).append(signature)

    matched: set[str] = set()
    for signature in native_signatures:
        matched.update(legacy_by_normalized.get(normalize_route_signature(signature), []))
    return sorted(matched)


def summarize_legacy_api_routes(
    flask_app: Any,
    *,
    native_signatures: Iterable[str] = (),
    limit: int = 25,
) -> dict[str, Any]:
    inventory = collect_flask_route_inventory(flask_app)
    legacy_api_paths = [item["path"] for item in inventory if item["is_api"]]
    legacy_non_api_paths = [item["path"] for item in inventory if not item["is_api"]]
    legacy_api_signatures = collect_route_signatures(inventory, api_only=True)
    native_signatures = list(native_signatures)
    legacy_flask_only_signatures = collect_legacy_only_route_signatures(legacy_api_signatures, native_signatures)
    native_override_signatures = collect_native_override_signatures(legacy_api_signatures, native_signatures)
    return {
        "legacy_route_inventory": inventory,
        "legacy_api_paths": legacy_api_paths,
        "legacy_api_signatures": legacy_api_signatures,
        "legacy_api_route_count": len(legacy_api_paths),
        "legacy_api_sample_paths": legacy_api_paths[:limit],
        "legacy_non_api_route_count": len(legacy_non_api_paths),
        "legacy_flask_only_signatures": legacy_flask_only_signatures,
        "legacy_flask_only_route_count": len(legacy_flask_only_signatures),
        "legacy_flask_only_sample_signatures": legacy_flask_only_signatures[:limit],
        "native_override_signatures": native_override_signatures,
        "native_override_route_count": len(native_override_signatures),
    }
