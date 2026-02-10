"""Thin registry for document-to-markdown conversion engines.

Imports are intentionally lazy so the main web app can run without heavyweight
optional dependencies installed (docling, marker-pdf, OCR SDKs, etc.). Missing
dependencies are surfaced only when a user selects that engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

EngineName = Literal["auto", "marker", "docling", "mistral", "deepseekocr", "local"]


@dataclass(slots=True)
class ConversionOutput:
    markdown: str
    engine: str
    model: str


def _import_engine(engine: str):
    engine = engine.lower()
    if engine == "marker":
        from doc_to_md.engines.marker import MarkerEngine

        return MarkerEngine
    if engine == "docling":
        from doc_to_md.engines.docling import DoclingEngine

        return DoclingEngine
    if engine == "mistral":
        from doc_to_md.engines.mistral import MistralEngine

        return MistralEngine
    if engine == "deepseekocr":
        from doc_to_md.engines.deepseekocr import DeepSeekOCREngine

        return DeepSeekOCREngine
    if engine == "local":
        from doc_to_md.engines.local import LocalEngine

        return LocalEngine
    raise ValueError(f"Unknown engine: {engine}")


def pick_auto_engine(path: Path) -> str:
    """Pick a reasonable default engine based on extension.

Conservative default: prefer local tools first to avoid unexpected paid API calls.
"""

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "marker"
    if suffix in {".docx", ".pptx"}:
        return "docling"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        return "deepseekocr"
    return "docling"


def _auto_candidates(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        # Prefer local tools first; fall back to API engines if configured.
        return ["marker", "docling", "mistral", "deepseekocr", "local"]
    if suffix in {".docx", ".pptx"}:
        return ["docling", "mistral", "deepseekocr", "local"]
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        return ["deepseekocr", "mistral", "local"]
    return ["docling", "mistral", "deepseekocr", "local"]


def convert_path(
    path: Path,
    *,
    engine: EngineName = "auto",
    model: Optional[str] = None,
) -> ConversionOutput:
    if engine == "auto":
        last_exc: Exception | None = None
        for candidate in _auto_candidates(path):
            try:
                return convert_path(path, engine=candidate, model=model)
            except Exception as exc:  # noqa: BLE001 - auto mode tries fallbacks
                last_exc = exc
                continue
        raise RuntimeError(f"Auto conversion failed for {path.name}") from last_exc

    engine_cls = _import_engine(engine)
    try:
        engine_instance = engine_cls(model=model) if model is not None else engine_cls()
    except TypeError:
        engine_instance = engine_cls()

    response = engine_instance.convert(path)
    return ConversionOutput(markdown=response.markdown, engine=str(engine_instance.name), model=str(response.model))
