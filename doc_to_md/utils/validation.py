"""Input validation utilities for document processing."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

MAX_FILE_SIZE_MB = 100
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".md", ".docx"}

FileValidationError = type("FileValidationError", (ValueError,), {})


def validate_file(path: Path) -> Literal[True]:
    if not path.exists():
        raise FileValidationError(f"File does not exist: {path}")
    if not path.is_file():
        raise FileValidationError(f"Path is not a file: {path}")

    suffix = path.suffix.lower()
    if suffix == ".doc":
        raise FileValidationError("Legacy .doc is not supported. Please convert to .docx.")
    if suffix not in SUPPORTED_EXTENSIONS:
        raise FileValidationError(
            f"Unsupported file format: {suffix}. Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    try:
        file_size = path.stat().st_size
    except OSError as exc:
        raise FileValidationError(f"Cannot read file stats: {exc}") from exc

    if file_size == 0:
        raise FileValidationError(f"File is empty: {path}")
    if file_size > MAX_FILE_SIZE_BYTES:
        size_mb = file_size / (1024 * 1024)
        raise FileValidationError(f"File too large: {size_mb:.1f}MB exceeds limit of {MAX_FILE_SIZE_MB}MB")

    try:
        with path.open("rb") as f:
            f.read(10)
    except OSError as exc:
        raise FileValidationError(f"File is not readable: {exc}") from exc

    return True


def is_likely_corrupted_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            header = f.read(5)
            if not header.startswith(b"%PDF-"):
                return True
    except Exception:  # noqa: BLE001
        return True
    return False


def is_likely_corrupted_docx(path: Path) -> bool:
    try:
        import zipfile

        if not zipfile.is_zipfile(path):
            return True
    except Exception:  # noqa: BLE001
        return True
    return False

