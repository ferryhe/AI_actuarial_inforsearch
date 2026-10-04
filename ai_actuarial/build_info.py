"""Safe build identity, supplied by the builder; never inspect runtime Git."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from ai_actuarial.shared_runtime import TRACKED_SITES_CONFIG_PATH, get_sites_config_path


def _value(name: str, pattern: str) -> str:
    value = os.environ.get(name, "unknown")
    return value if re.fullmatch(pattern, value) else "unknown"


def get_build_info() -> dict[str, str]:
    return {
        "release_manifest_id": _value("BUILD_RELEASE_ID", r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"),
        "git_sha": _value("BUILD_GIT_SHA", r"[a-fA-F0-9]{7,40}"),
        "build_utc": _value("BUILD_UTC", r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"),
        "image_digest": _value("API_IMAGE_DIGEST", r"sha256:[a-f0-9]{64}"),
    }


def public_build_info() -> dict[str, str]:
    info = get_build_info()
    return {"release_manifest_id": info["release_manifest_id"], "git_sha": info["git_sha"][:7]}


def config_provenance(config_path: Path) -> dict[str, str]:
    """Hash the authoritative file without serializing its path or contents."""
    return {
        "config_source": (
            "tracked-development"
            if config_path.resolve() == TRACKED_SITES_CONFIG_PATH.resolve()
            else "external"
        ),
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
    }


def detailed_build_info() -> dict[str, str]:
    info = get_build_info()
    try:
        info.update(config_provenance(Path(get_sites_config_path())))
    except OSError:
        info.update(config_source="unavailable", config_sha256="unknown")
    return info
