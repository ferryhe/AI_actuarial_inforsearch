"""Implementation of the Mistral OCR API using the official SDK."""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Callable, List, Tuple, TypeVar

from pypdf import PdfReader, PdfWriter

from config.settings import get_settings
from doc_to_md.utils.tokens import count_tokens
from doc_to_md.engines.base import Engine, EngineAsset, EngineResponse

T = TypeVar("T")


@dataclass(slots=True)
class _DocumentChunk:
    data: bytes
    label: str
    page_range: tuple[int, int] | None = None


class MistralEngine(Engine):
    name = "mistral"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        include_images: bool = False,
        extract_footer: bool | None = None,
        extract_header: bool | None = None,
        **_kwargs,
    ) -> None:
        settings = get_settings()
        resolved_api_key = api_key or settings.mistral_api_key
        if not resolved_api_key:
            raise RuntimeError("MISTRAL_API_KEY missing")

        try:
            from mistralai import Mistral  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Mistral engine requires `mistralai`. Install via `pip install mistralai`.") from exc

        self.api_key = resolved_api_key
        self.model = model or settings.mistral_default_model
        self.include_images = include_images
        self.timeout_ms = int(settings.mistral_timeout_seconds * 1000)
        self.retry_attempts = settings.mistral_retry_attempts
        self.max_pdf_tokens = settings.mistral_max_pdf_tokens
        self.max_pages_per_chunk = settings.mistral_max_pages_per_chunk
        default_extract_footer = bool(getattr(settings, "mistral_extract_footer", True))
        default_extract_header = bool(getattr(settings, "mistral_extract_header", True))
        self.extract_footer = default_extract_footer if extract_footer is None else bool(extract_footer)
        self.extract_header = default_extract_header if extract_header is None else bool(extract_header)
        self._retry_backoff = 1.5
        self.client = Mistral(api_key=self.api_key, timeout_ms=self.timeout_ms)

    def convert(self, path: Path) -> EngineResponse:  # pragma: no cover - network call
        # Import types lazily (SDK optional)
        from mistralai.models.file import File  # type: ignore
        from mistralai.models.filechunk import FileChunk  # type: ignore
        from mistralai.models.ocrresponse import OCRResponse  # type: ignore

        chunks = self._prepare_chunks(path)
        all_pages = []
        base_response: OCRResponse | None = None

        for index, chunk in enumerate(chunks, start=1):
            response = self._process_chunk(chunk, index, File=File, FileChunk=FileChunk)
            if base_response is None:
                base_response = response
            page_offset = (chunk.page_range[0] - 1) if chunk.page_range else len(all_pages)
            for page in response.pages:
                page.index = page_offset + page.index
                all_pages.append(page)

        if base_response is None:
            raise RuntimeError("Mistral OCR returned no pages")

        combined_response = OCRResponse(
            model=base_response.model,
            pages=sorted(all_pages, key=lambda page: page.index),
            usage_info=base_response.usage_info,
            document_annotation=base_response.document_annotation,
        )

        markdown, assets = self._render_markdown_and_assets(path.stem, combined_response)

        if len(chunks) > 1:
            ranges = ", ".join(self._format_range(chunk) for chunk in chunks if chunk.page_range)
            notice = (
                f"_Note: Source document was split into {len(chunks)} OCR chunks "
                f"({ranges}) to stay within token limits._"
            )
            markdown = f"{notice}\n\n{markdown}"

        return EngineResponse(markdown=markdown, model=combined_response.model, assets=assets)

    def _prepare_chunks(self, path: Path) -> List[_DocumentChunk]:
        suffix = path.suffix.lower()
        original_bytes = path.read_bytes()
        if suffix != ".pdf":
            return [_DocumentChunk(data=original_bytes, label=path.name)]

        reader = PdfReader(str(path))
        total_pages = len(reader.pages)
        if total_pages == 0:
            return [_DocumentChunk(data=original_bytes, label=path.name)]

        tokens_per_page: list[int] = []
        for page in reader.pages:
            try:
                page_text = page.extract_text() or ""
            except Exception:  # noqa: BLE001
                page_text = ""
            tokens_per_page.append(count_tokens(page_text))

        if total_pages <= self.max_pages_per_chunk and sum(tokens_per_page) <= self.max_pdf_tokens:
            return [_DocumentChunk(data=original_bytes, label=path.name, page_range=(1, total_pages))]

        chunks: list[_DocumentChunk] = []
        start = 0
        while start < total_pages:
            end = start
            token_budget = 0
            while end < total_pages and (end - start) < self.max_pages_per_chunk:
                token_budget += tokens_per_page[end]
                end += 1
                if token_budget >= self.max_pdf_tokens:
                    break
            page_indices = list(range(start, end))
            chunk_data = self._write_pdf_chunk(reader, page_indices)
            page_range = (page_indices[0] + 1, page_indices[-1] + 1)
            label = f"{path.stem}_p{page_range[0]:03d}-{page_range[1]:03d}.pdf"
            chunks.append(_DocumentChunk(data=chunk_data, label=label, page_range=page_range))
            start = end

        return chunks or [_DocumentChunk(data=original_bytes, label=path.name)]

    def _write_pdf_chunk(self, reader: PdfReader, page_indices: List[int]) -> bytes:
        writer = PdfWriter()
        for page_index in page_indices:
            writer.add_page(reader.pages[page_index])
        buffer = BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    def _process_chunk(self, chunk: _DocumentChunk, index: int, *, File, FileChunk):
        upload = self._request_with_retry(
            lambda: self.client.files.upload(
                file=File(file_name=chunk.label, content=chunk.data),
                purpose="ocr",
            ),
            operation=f"mistral_upload_{index}",
        )

        try:
            process_kwargs = {
                "model": self.model,
                "document": FileChunk(file_id=upload.id),
                "include_image_base64": self.include_images,
                "extract_footer": self.extract_footer,
                "extract_header": self.extract_header,
            }
            try:
                response = self._request_with_retry(
                    lambda: self.client.ocr.process(**process_kwargs),
                    operation=f"mistral_process_{index}",
                )
            except RuntimeError as exc:
                # Backward compatibility: older mistralai SDK versions may not support
                # extract_footer/extract_header parameters yet.
                cause = exc.__cause__
                msg = str(cause or exc).lower()
                unsupported_param = (
                    isinstance(cause, TypeError)
                    and "unexpected keyword argument" in msg
                    and ("extract_footer" in msg or "extract_header" in msg)
                )
                if not unsupported_param:
                    raise
                fallback_kwargs = {
                    "model": self.model,
                    "document": FileChunk(file_id=upload.id),
                    "include_image_base64": self.include_images,
                }
                response = self._request_with_retry(
                    lambda: self.client.ocr.process(**fallback_kwargs),
                    operation=f"mistral_process_{index}_legacy",
                )
            return response
        finally:
            try:
                self.client.files.delete(file_id=upload.id)
            except Exception:
                pass

    @staticmethod
    def _format_range(chunk: _DocumentChunk) -> str:
        if not chunk.page_range:
            return chunk.label
        start, end = chunk.page_range
        if start == end:
            return f"page {start}"
        return f"pages {start}-{end}"

    def _request_with_retry(self, func: Callable[[], T], operation: str) -> T:
        delay = self._retry_backoff
        last_exc: Exception | None = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                return func()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt == self.retry_attempts:
                    break
                time.sleep(delay)
                delay *= 2
        assert last_exc is not None
        raise RuntimeError(f"Operation '{operation}' failed after {self.retry_attempts} attempts") from last_exc

    def _render_markdown_and_assets(self, title: str, response) -> Tuple[str, List[EngineAsset]]:
        sections: List[str] = [f"# {title}", ""]
        pages = sorted(response.pages, key=lambda page: page.index)
        assets: List[EngineAsset] = []
        normalized_stem = self._normalize_stem(title)

        for page in pages:
            cleaned_page = self._strip_placeholder_images(getattr(page, "markdown", "") or "")
            sections.append(cleaned_page or "_No text extracted on this page._")

            image_snippets, page_assets = self._render_images(normalized_stem, getattr(page, "images", []), page.index)
            if image_snippets:
                sections.extend(image_snippets)
            assets.extend(page_assets)

            sections.append("")

        return "\n".join(sections).strip(), assets

    def _render_images(self, normalized_stem: str, images, page_index: int) -> Tuple[List[str], List[EngineAsset]]:
        if not self.include_images or not images:
            return [], []

        snippets: List[str] = []
        assets: List[EngineAsset] = []
        assets_subdir = f"{normalized_stem}_assets"
        for idx, image in enumerate(images, start=1):
            image_base64 = getattr(image, "image_base64", None)
            if not image_base64:
                continue
            binary, extension = self._decode_image(image_base64)
            filename = f"{normalized_stem}_p{page_index + 1:02d}_img{idx}.{extension}"
            assets.append(EngineAsset(filename=filename, data=binary, subdir=assets_subdir))
            alt = f"Page {page_index + 1} Image {idx}"
            snippets.append(f"![{alt}]({assets_subdir}/{filename})")
        return snippets, assets

    @staticmethod
    def _normalize_stem(stem: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("_") or "document"

    @staticmethod
    def _resolve_extension(binary: bytes) -> str:
        if binary.startswith(b"\xff\xd8\xff"):
            return "jpg"
        if binary.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        if binary.startswith(b"GIF87a") or binary.startswith(b"GIF89a"):
            return "gif"
        if binary.startswith(b"RIFF") and binary[8:12] == b"WEBP":
            return "webp"
        if binary.startswith(b"BM"):
            return "bmp"
        return "bin"

    @staticmethod
    def _strip_placeholder_images(markdown: str) -> str:
        lines = []
        for line in (markdown or "").splitlines():
            if "](img-" in line:
                continue
            lines.append(line)
        return "\n".join(lines).strip()

    def _decode_image(self, payload: str) -> Tuple[bytes, str]:
        data_str = payload
        mime: str | None = None
        if payload.startswith("data:"):
            header, _, rest = payload.partition(",")
            data_str = rest
            if ";" in header:
                mime = header.split(";", 1)[0][5:]
            else:
                mime = header[5:]
        binary = base64.b64decode(data_str)
        extension = self._extension_from_mime(mime) or self._resolve_extension(binary)
        return binary, extension

    @staticmethod
    def _extension_from_mime(mime: str | None) -> str | None:
        if not mime:
            return None
        mapping = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
        return mapping.get(mime.lower())
