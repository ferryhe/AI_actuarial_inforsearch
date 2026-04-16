from __future__ import annotations

import re
from pathlib import Path

from ai_actuarial.api.app import create_app
from ai_actuarial.api.route_inventory import normalize_route_signature

ROOT = Path(__file__).resolve().parents[1] / "client" / "src"
PRODUCT_SOURCE_FILES = [
    ROOT / "App.tsx",
    ROOT / "context" / "AuthContext.tsx",
    ROOT / "hooks" / "use-task-options.ts",
    ROOT / "lib" / "api.ts",
    ROOT / "pages" / "Chat.tsx",
    ROOT / "pages" / "Dashboard.tsx",
    ROOT / "pages" / "Database.tsx",
    ROOT / "pages" / "FileDetail.tsx",
    ROOT / "pages" / "FilePreview.tsx",
    ROOT / "pages" / "KBDetail.tsx",
    ROOT / "pages" / "Knowledge.tsx",
    ROOT / "pages" / "Login.tsx",
    ROOT / "pages" / "NativeLogs.tsx",
    ROOT / "pages" / "NativeSettings.tsx",
    ROOT / "pages" / "Profile.tsx",
    ROOT / "pages" / "Register.tsx",
    ROOT / "pages" / "Tasks.tsx",
    ROOT / "pages" / "Users.tsx",
]
_API_WRAPPER_PATTERN = re.compile(r'(apiGet|apiPost|apiPut|apiPatch|apiDelete)\(\s*(["\'`])(/api/[^"\'`]+)\2')
_FETCH_PATTERN = re.compile(r'fetch\(\s*(["\'`])(/api/[^"\'`]+)\1(\s*,\s*\{(?P<options>.*?)\})?', re.S)
_HREF_PATTERN = re.compile(r'(?P<target>[A-Za-z0-9_\.]+)\.href\s*=\s*(["\'`])(?P<url>/api/[^"\'`]+)\2')
_JSX_API_ATTR_PATTERN = re.compile(
    r'(?P<attr>href|src|action|formAction)\s*=\s*(?:\{\s*)?(["\'`])(?P<url>/api/[^"\'`]+)\2',
    re.S,
)
_METHOD_BY_WRAPPER = {
    "apiGet": "GET",
    "apiPost": "POST",
    "apiPut": "PUT",
    "apiPatch": "PATCH",
    "apiDelete": "DELETE",
}


def _canonicalize_client_path(path: str) -> str:
    without_query = path.split("?", 1)[0]
    return re.sub(r"\$\{[^}]+\}", "{var}", without_query)


def _collect_product_api_references() -> list[tuple[str, str, str]]:
    references: set[tuple[str, str, str]] = set()
    for path in PRODUCT_SOURCE_FILES:
        source = path.read_text(encoding="utf-8")

        for wrapper, _, url in _API_WRAPPER_PATTERN.findall(source):
            references.add((path.relative_to(ROOT).as_posix(), _METHOD_BY_WRAPPER[wrapper], _canonicalize_client_path(url)))

        for match in _FETCH_PATTERN.finditer(source):
            url = match.group(2)
            options = match.group("options") or ""
            method_match = re.search(r'method\s*:\s*["\'](GET|POST|PUT|PATCH|DELETE)["\']', options)
            method = method_match.group(1) if method_match else "GET"
            references.add((path.relative_to(ROOT).as_posix(), method, _canonicalize_client_path(url)))

        for match in _HREF_PATTERN.finditer(source):
            references.add((path.relative_to(ROOT).as_posix(), "GET", _canonicalize_client_path(match.group("url"))))

        for match in _JSX_API_ATTR_PATTERN.finditer(source):
            references.add((path.relative_to(ROOT).as_posix(), "GET", _canonicalize_client_path(match.group("url"))))

    return sorted(references)


def test_routed_react_shell_only_references_native_fastapi_endpoints() -> None:
    app = create_app()
    native_signatures = {
        normalize_route_signature(signature) for signature in app.state.native_route_signatures
    }

    unsupported: list[tuple[str, str, str]] = []
    for file_path, method, endpoint in _collect_product_api_references():
        signature = normalize_route_signature(f"{method} {endpoint}")
        if signature not in native_signatures:
            unsupported.append((file_path, method, endpoint))

    assert unsupported == []
