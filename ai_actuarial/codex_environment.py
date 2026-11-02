"""Environment allowlist for local Codex CLI subprocesses."""

from __future__ import annotations

import os

CODEX_ENVIRONMENT_KEYS = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "CODEX_HOME",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
    }
)


def codex_environment() -> dict[str, str]:
    return {
        key: value for key, value in os.environ.items() if key.upper() in CODEX_ENVIRONMENT_KEYS
    }
