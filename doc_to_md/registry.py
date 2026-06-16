"""Thin registry for document-to-markdown conversion engines.

Imports are intentionally lazy so the main web app can run without heavyweight
optional dependencies installed (docling, marker-pdf, OCR SDKs, etc.). Missing
dependencies are surfaced only when a user selects that engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

EngineName = Literal[
    "auto",
    "opendataloader",
    "markitdown",
    "mistral",
    "docling",
    "mathpix",
    "marker",
    "deepseekocr",
    "local",
]


@dataclass(slots=True)
class ConversionOutput:
    markdown: str
    engine: str
    model: str


def _import_engine(engine: str):
    engine = engine.lower()
    if engine == "opendataloader":
        from doc_to_md.engines.opendataloader import OpenDataLoaderEngine

        return OpenDataLoaderEngine
    if engine == "markitdown":
        from doc_to_md.engines.markitdown import MarkItDownEngine

        return MarkItDownEngine
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
    if engine == "mathpix":
        from doc_to_md.engines.mathpix import MathpixEngine

        return MathpixEngine
    if engine == "local":
        from doc_to_md.engines.local import LocalEngine

        return LocalEngine
    raise ValueError(f"Unknown engine: {engine}")


def pick_auto_engine(path: Path) -> str:
    """Pick the first configured auto candidate without triggering paid/API tools by default."""

    candidates = _auto_candidates(path)
    if candidates:
        return candidates[0]
    try:
        from ai_actuarial.markdown_conversion_config import markdown_conversion_config_file_exists

        if markdown_conversion_config_file_exists():
            raise RuntimeError(f"No auto conversion candidates configured for {path.name}")
    except RuntimeError:
        raise
    except Exception:
        pass
    return "markitdown"


def _auto_candidates(path: Path) -> list[str]:
    try:
        from ai_actuarial.markdown_conversion_config import (
            candidate_chain_for_path,
            markdown_conversion_config_file_exists,
        )

        candidates = candidate_chain_for_path(path, auto_only=True)
        if candidates:
            return candidates
        if markdown_conversion_config_file_exists():
            return []
    except Exception:
        pass

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return ["opendataloader", "markitdown", "docling", "local"]
    if suffix in {".docx", ".pptx"}:
        return ["markitdown", "docling", "local"]
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
        return ["local"]
    return ["markitdown", "docling", "local"]


def convert_path(
    path: Path,
    *,
    engine: EngineName = "auto",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> ConversionOutput:
    if engine == "auto":
        last_exc: Exception | None = None
        for candidate in _auto_candidates(path):
            try:
                return convert_path(
                    path,
                    engine=candidate,
                    model=model,
                    api_key=api_key,
                    base_url=base_url,
                )
            except Exception as exc:  # noqa: BLE001 - auto mode tries fallbacks
                last_exc = exc
                continue
        raise RuntimeError(f"Auto conversion failed for {path.name}") from last_exc

    engine_cls = _import_engine(engine)
    init_kwargs = {}
    if model is not None:
        init_kwargs["model"] = model
    if api_key is not None:
        init_kwargs["api_key"] = api_key
    if base_url is not None:
        init_kwargs["base_url"] = base_url
    try:
        engine_instance = engine_cls(**init_kwargs)
    except TypeError:
        try:
            if model is not None:
                engine_instance = engine_cls(model=model)
            else:
                engine_instance = engine_cls()
        except TypeError:
            engine_instance = engine_cls()

    response = engine_instance.convert(path)
    return ConversionOutput(markdown=response.markdown, engine=str(engine_instance.name), model=str(response.model))
