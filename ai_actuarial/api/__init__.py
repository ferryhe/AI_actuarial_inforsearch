from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .app import create_app, run_server

__all__ = ["create_app", "run_server"]


def __getattr__(name: str):
    if name in __all__:
        from .app import create_app, run_server

        return {"create_app": create_app, "run_server": run_server}[name]
    raise AttributeError(name)
