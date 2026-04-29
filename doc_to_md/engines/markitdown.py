"""Engine adapter for Microsoft's MarkItDown converter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config.settings import get_settings
from doc_to_md.engines.base import Engine, EngineResponse


class MarkItDownEngine(Engine):
    name = "markitdown"

    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        self.model = model or "markitdown"
        self._converter = self._build_converter(
            enable_plugins=settings.markitdown_enable_plugins,
            enable_builtins=settings.markitdown_enable_builtins,
        )

    @staticmethod
    def _build_converter(**options: Any) -> Any:
        try:
            from markitdown import MarkItDown  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "MarkItDown engine requires the `markitdown` package. Install it with `pip install markitdown`."
            ) from exc

        sanitized = {key: value for key, value in options.items() if value is not None}
        return MarkItDown(**sanitized)

    def convert(self, path: Path) -> EngineResponse:  # pragma: no cover - optional dependency
        result = self._converter.convert(str(path))
        markdown = getattr(result, "markdown", None) or getattr(result, "text_content", "")
        if not markdown.strip():
            markdown = "_MarkItDown returned an empty response._"
        return EngineResponse(markdown=markdown, model=self.model)
