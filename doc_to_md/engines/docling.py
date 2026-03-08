"""Engine adapter for IBM's Docling converter."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from config.settings import get_settings, PROJECT_ROOT
from doc_to_md.utils.hardware import ensure_docling_accelerator_env
from doc_to_md.engines.base import Engine, EngineResponse


class DoclingEngine(Engine):
    name = "docling"

    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        self.model = model or "docling"
        self._max_pages = settings.docling_max_pages
        self._raises_on_error = settings.docling_raise_on_error
        self._converter: Any | None = None

    def _ensure_converter(self) -> Any:
        if self._converter is not None:
            return self._converter

        # On headless/server environments (no display), prevent Qt/xcb from being loaded
        # by telling Qt to use the offscreen platform plugin instead of xcb.
        # This avoids "libxcb.so.1: cannot open shared object file" errors.
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        # Ensure HF models are stored in persistent data volume
        if "HF_HOME" not in os.environ:
            model_dir = PROJECT_ROOT / "data" / "models" / "huggingface"
            model_dir.mkdir(parents=True, exist_ok=True)
            os.environ["HF_HOME"] = str(model_dir)

        try:
            from docling.document_converter import DocumentConverter  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Docling engine requires the `docling` package. Install it with `pip install docling`."
            ) from exc

        # HF Hub tries to create symlinks when caching models. On Windows without developer
        # privileges this can fail, so force the hub to fall back to copy semantics.
        try:  # pragma: no cover
            from huggingface_hub import file_download as hf_file_download  # type: ignore
        except Exception:  # noqa: BLE001
            pass
        else:
            hf_file_download.are_symlinks_supported = lambda cache_dir=None: False  # type: ignore[assignment]

        ensure_docling_accelerator_env()
        self._converter = DocumentConverter()
        return self._converter

    def convert(self, path: Path) -> EngineResponse:  # pragma: no cover - heavy dependency
        converter = self._ensure_converter()
        kwargs: dict[str, Any] = {"raises_on_error": self._raises_on_error}
        if self._max_pages is not None:
            kwargs["max_num_pages"] = self._max_pages
        result = converter.convert(str(path), **kwargs)
        document = getattr(result, "document", None)
        if document is None:
            raise RuntimeError("Docling did not return a document object.")
        markdown = document.export_to_markdown()
        return EngineResponse(markdown=markdown, model=self.model)

