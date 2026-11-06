from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .app import create_app, run_server

__all__ = ["create_app", "run_server"]


def __getattr__(name: str):
    # Importing a business module must not recursively assemble every API router.
    if name in __all__:
        return getattr(import_module(".app", __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
