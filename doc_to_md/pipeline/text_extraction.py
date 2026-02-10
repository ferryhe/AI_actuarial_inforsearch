"""Helpers for extracting plain text from various document types."""

from __future__ import annotations

import html
from pathlib import Path

from pypdf import PdfReader

from doc_to_md.utils.validation import (
    is_likely_corrupted_docx,
    is_likely_corrupted_pdf,
    validate_file,
)

try:  # Optional dependency for DOCX parsing
    from docx import Document  # type: ignore
except ImportError:  # pragma: no cover
    Document = None  # type: ignore[assignment]

try:  # Optional dependency for image OCR
    from PIL import Image  # type: ignore
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]

try:  # Optional dependency for image OCR
    import pytesseract  # type: ignore
except ImportError:  # pragma: no cover
    pytesseract = None  # type: ignore[assignment]


def extract_text(path: Path) -> str:
    """Extract text from various document formats with validation and error handling."""

    validate_file(path)

    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            return _extract_pdf(path)
        if suffix == ".docx":
            return _extract_docx(path)
        if suffix in {".png", ".jpg", ".jpeg"}:
            return _extract_image(path)
        return _extract_text_file(path)
    except Exception as exc:
        raise RuntimeError(f"Failed to extract text from {path.name}: {exc}") from exc


def _extract_pdf(path: Path) -> str:
    if is_likely_corrupted_pdf(path):
        return "[PDF file appears to be corrupted or invalid]"

    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # noqa: BLE001
        return f"[PDF reading failed: {exc}]"

    if len(reader.pages) == 0:
        return "[PDF contains no pages]"

    parts: list[str] = []
    failed_pages = 0

    for index, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            page_text = f"[Page {index} extraction failed: {exc}]"
            failed_pages += 1

        if page_text.strip():
            parts.append(_escape_markdown_special_chars(page_text.strip()))

    if not parts:
        return "[No textual content could be extracted from PDF]"

    result = "\n\n".join(parts)
    if failed_pages > 0:
        warning = f"\n\n_Note: {failed_pages} page(s) failed to extract._"
        result = warning + "\n\n" + result
    return result


def _escape_markdown_special_chars(text: str) -> str:
    replacements = {
        "\\": "\\\\",
        "`": "\\`",
        "*": "\\*",
        "_": "\\_",
        "{": "\\{",
        "}": "\\}",
        "[": "\\[",
        "]": "\\]",
        "(": "\\(",
        ")": "\\)",
        "#": "\\#",
        "+": "\\+",
        "-": "\\-",
        ".": "\\.",
        "!": "\\!",
        "|": "\\|",
    }

    escaped = text
    for char, replacement in replacements.items():
        escaped = escaped.replace(char, replacement)
    return escaped


def _extract_docx(path: Path) -> str:
    if is_likely_corrupted_docx(path):
        return "[DOCX file appears to be corrupted or invalid]"

    if Document is None:  # pragma: no cover
        raise RuntimeError("DOCX extraction requires `python-docx`. Install it via `pip install python-docx`.")

    doc = Document(str(path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    if not paragraphs:
        return "[No text found in DOCX document]"
    return "\n\n".join(paragraphs)


def _extract_image(path: Path) -> str:
    if Image is None or pytesseract is None:  # pragma: no cover
        raise RuntimeError("Image OCR requires `Pillow` and `pytesseract`.")

    image = Image.open(path)
    try:
        grayscale = image.convert("L")
        text = pytesseract.image_to_string(grayscale)
        return text.strip() or "[No text detected in image]"
    finally:
        image.close()


def _extract_text_file(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() in {".html", ".htm"}:
        raw = html.unescape(raw)
    return raw.strip()

