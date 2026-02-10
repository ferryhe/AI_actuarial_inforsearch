"""Helpers for detecting local accelerator capabilities and configuring engines."""

from __future__ import annotations

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def detect_torch_device() -> str:
    """Return 'cuda:0', 'mps', or 'cpu' based on availability."""
    torch = _safe_import_torch()
    if torch is None:
        return "cpu"
    try:  # pragma: no cover - hardware specific
        if torch.cuda.is_available():
            idx = torch.cuda.current_device()
            return f"cuda:{idx}"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:  # noqa: BLE001
        return "cpu"
    return "cpu"


def ensure_docling_accelerator_env() -> None:
    device = detect_torch_device()
    if device == "cpu":
        return
    os.environ.setdefault("DOCLING_ACCELERATOR_DEVICE", device)


def ensure_marker_accelerator_env() -> None:
    device = detect_torch_device()
    if device == "cpu":
        return
    norm_device = "cuda" if device.startswith("cuda") else device
    os.environ.setdefault("TORCH_DEVICE", norm_device)


def _safe_import_torch():
    try:
        import torch  # type: ignore

        return torch
    except Exception:  # noqa: BLE001
        return None

