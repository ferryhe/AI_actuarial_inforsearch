"""DeepSeek-OCR engine implemented via an OpenAI-compatible API (SiliconFlow)."""

from __future__ import annotations

import base64
from io import BytesIO
import re
from pathlib import Path
from typing import List, Sequence, Tuple, TypeVar

from config.settings import get_settings
from doc_to_md.pipeline.text_extraction import extract_text
from doc_to_md.utils.tokens import split_by_tokens
from doc_to_md.engines.base import Engine, EngineResponse, RetryableRequestMixin

T = TypeVar("T")


class DeepSeekOCREngine(RetryableRequestMixin, Engine):
    """Send documents to DeepSeek-OCR's OpenAI-compatible API for vision/text processing.

Note: DeepSeek-OCR's OpenAI-compatible API only supports one image per request.
Multi-image batching is not supported; each page must be sent in a separate call.
"""

    name = "deepseekocr"
    _PDF_RENDER_DPI = 220
    _PAGES_PER_VISION_REQUEST = 1
    _DEEPSEEK_MARKDOWN_PROMPT = "<image>\nFree OCR."
    _EXTRA_BODY = {
        "skip_special_tokens": False,
        "vllm_xargs": {
            "ngram_size": 30,
            "window_size": 90,
            "whitelist_token_ids": [128821, 128822],
        },
    }

    def __init__(self, model: str | None = None) -> None:
        settings = get_settings()
        if not settings.siliconflow_api_key:
            raise RuntimeError("SILICONFLOW_API_KEY missing (DeepSeek-OCR via SiliconFlow)")

        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("DeepSeek-OCR engine requires `openai`. Install it via `pip install openai`.") from exc

        super().__init__(retry_attempts=settings.siliconflow_retry_attempts)
        self.api_key = settings.siliconflow_api_key
        self.model = model or settings.siliconflow_default_model
        self.timeout = settings.siliconflow_timeout_seconds
        self.max_tokens = settings.siliconflow_max_input_tokens
        self.chunk_overlap = settings.siliconflow_chunk_overlap_tokens
        self.client = OpenAI(api_key=self.api_key, base_url=settings.siliconflow_base_url)

    def convert(self, path: Path) -> EngineResponse:  # pragma: no cover - network call
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            raw_text = extract_text(path)
            if self._text_is_meaningful(raw_text):
                return self._process_text(path, raw_text=raw_text)
            pdf_response = self._process_pdf(path)
            if self._looks_corrupted(pdf_response.markdown):
                return self._process_text(path, raw_text=raw_text)
            return pdf_response
        if self._is_image(path):
            return self._process_image_file(path)
        return self._process_text(path)

    def _process_pdf(self, path: Path) -> EngineResponse:
        rendered_pages = self._render_pdf_pages(path)
        if not rendered_pages:
            return self._process_text(path)

        markdown_parts: list[str] = []
        page_chunks = list(self._chunk_sequence(rendered_pages, self._PAGES_PER_VISION_REQUEST))

        for page_index, chunk in enumerate(page_chunks, start=1):
            markdown_parts.append(
                self._describe_images_with_model(
                    filename=path.name,
                    images=chunk,
                    page_index=page_index,
                    page_total=len(page_chunks),
                )
            )

        markdown = self._compose_markdown(path.name, markdown_parts, len(page_chunks))
        return EngineResponse(markdown=markdown, model=self.model)

    def _process_text(self, path: Path, raw_text: str | None = None) -> EngineResponse:
        text_to_use = raw_text if raw_text is not None else extract_text(path)
        chunks = self._chunk_text(text_to_use)
        markdown_parts: list[str] = []

        for index, chunk in enumerate(chunks, start=1):
            user_prompt = self._build_user_prompt(path.name, chunk, index, len(chunks))
            completion = self._request_with_retry(
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a meticulous technical writer. Convert provided source text into clean Markdown, "
                                "preserving headings, tables, and lists."
                            ),
                        },
                        {"role": "user", "content": user_prompt},
                    ],
                    timeout=self.timeout,
                ),
                operation=f"deepseekocr_text_chunk_{index}",
            )
            markdown_parts.append(self._extract_content(completion))

        markdown = self._compose_markdown(path.name, markdown_parts, len(chunks))
        return EngineResponse(markdown=markdown, model=self.model)

    def _process_image_file(self, path: Path) -> EngineResponse:
        base64_image = self._encode_image(path)
        markdown = self._describe_images_with_model(
            filename=path.name,
            images=[(1, base64_image)],
            page_index=1,
            page_total=1,
        )
        return EngineResponse(markdown=markdown, model=self.model)

    def _describe_images_with_model(
        self,
        filename: str,
        images: Sequence[Tuple[int, str]],
        page_index: int,
        page_total: int,
    ) -> str:
        if not images:
            raise ValueError("No images provided to DeepSeek OCR")

        page_no, base64_image = images[0]
        user_prompt = self._build_user_prompt_for_images(filename, [page_no], page_index, page_total)

        content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "high"},
            },
            {"type": "text", "text": user_prompt},
        ]

        completion = self._request_with_retry(
            lambda: self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You operate DeepSeek-OCR. Preserve document structure, tables, and lists when transcribing.",
                    },
                    {"role": "user", "content": content},
                ],
                timeout=self.timeout,
                max_tokens=4096,
                temperature=0.0,
                extra_body=self._EXTRA_BODY,
            ),
            operation=f"deepseekocr_page_{page_no}",
        )
        return self._extract_content(completion)

    @staticmethod
    def _is_image(path: Path) -> bool:
        return path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

    @staticmethod
    def _encode_image(path: Path) -> str:
        with path.open("rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def _render_pdf_pages(self, path: Path) -> List[Tuple[int, str]]:
        try:
            import pypdfium2 as pdfium  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("DeepSeek-OCR PDF rendering requires `pypdfium2`. Install via `pip install pypdfium2`.") from exc

        rendered: list[Tuple[int, str]] = []
        pdf = pdfium.PdfDocument(str(path))
        scale = self._PDF_RENDER_DPI / 72.0

        try:
            for page_index, page in enumerate(pdf, start=1):
                bitmap = page.render(scale=scale)
                try:
                    pil_image = bitmap.to_pil()
                    buffer = BytesIO()
                    pil_image.save(buffer, format="JPEG", quality=90)
                    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
                    rendered.append((page_index, encoded))
                finally:
                    bitmap.close()
        finally:
            pdf.close()

        return rendered

    def _chunk_text(self, text: str) -> List[str]:
        sanitized = (text or "").strip()
        if not sanitized:
            return [sanitized]
        return split_by_tokens(sanitized, max_tokens=self.max_tokens, overlap_tokens=self.chunk_overlap)

    def _chunk_sequence(self, items: Sequence[T], size: int) -> List[Sequence[T]]:
        if size <= 0:
            return [items]
        return [items[i : i + size] for i in range(0, len(items), size)]

    def _build_user_prompt(self, filename: str, text: str, chunk_index: int, chunk_total: int) -> str:
        chunk_context = ""
        if chunk_total > 1:
            chunk_context = (
                f"This is chunk {chunk_index} of {chunk_total} extracted from '{filename}'. "
                "Maintain heading continuity across chunks and avoid duplicating intros already provided.\n\n"
            )

        return (
            f"{chunk_context}"
            f"Source document: {filename}\n\n"
            "Convert the following content into Markdown. Maintain hierarchical headings if obvious, convert numbered "
            "lists, and format tables when the structure is clear.\n\n"
            f"{text}"
        )

    @staticmethod
    def _build_user_prompt_for_images(filename: str, page_numbers: Sequence[int], page_index: int, page_total: int) -> str:
        page_note = ""
        if page_total > 1:
            page_note = f"This is page {page_index} of {page_total} from '{filename}'. Maintain continuity across pages.\n"

        page_num = page_numbers[0] if page_numbers else "unknown"
        return (
            f"{page_note}{DeepSeekOCREngine._DEEPSEEK_MARKDOWN_PROMPT}\n"
            f"Document page: {page_num}. Produce clean Markdown, preserving headings, tables, and ordered lists."
        )

    def _compose_markdown(self, filename: str, parts: Sequence[str], page_total: int) -> str:
        cleaned_parts = [part.strip() for part in parts if part and part.strip()]
        body = "\n\n".join(cleaned_parts) if cleaned_parts else "_No content returned by DeepSeek-OCR._"
        if page_total <= 1:
            return body
        notice = (
            f"_Note: Source document '{filename}' was processed in {page_total} separate requests "
            f"(DeepSeek-OCR API limitation: one image per request)._"
        )
        return f"{notice}\n\n{body}"

    def _extract_content(self, completion) -> str:
        if not completion.choices:
            raise RuntimeError("DeepSeek-OCR response did not contain any choices")
        content = completion.choices[0].message.content
        if not isinstance(content, str):
            raise RuntimeError(f"Unexpected content type in DeepSeek-OCR response: {type(content)}")
        return self._sanitize_markdown(content)

    @staticmethod
    def _looks_corrupted(markdown: str) -> bool:
        lowered = (markdown or "").lower()
        if "width=" in lowered or "align=" in lowered or "image:" in lowered:
            return True
        if "}}}}" in markdown or "[[" in markdown:
            return True
        brace_count = markdown.count("{") + markdown.count("}")
        if brace_count > 80:
            return True
        ascii_chars = sum(1 for ch in markdown if ch.isascii())
        total_chars = max(len(markdown), 1)
        if ascii_chars / total_chars < 0.65:
            return True
        return False

    @staticmethod
    def _text_is_meaningful(text: str) -> bool:
        stripped = (text or "").strip()
        if len(stripped) < 400:
            return False
        alpha = sum(1 for ch in stripped if ch.isalpha())
        ratio = alpha / max(len(stripped), 1)
        return ratio > 0.4

    @staticmethod
    def _sanitize_markdown(text: str) -> str:
        cleaned = (text or "").strip()
        patterns = [
            (r"width\\s*=\\s*\\d+%?", ""),
            (r'align\\s*=\\s*\"(left|right|center)\"', ""),
            (r"captions?:\\\".*?\\\"", ""),
            (r"image:\\\".*?\\\"", ""),
            (r"\\|{2,}", "|"),
            (r"\\{[\\}\\{]{2,}", "\n"),
            (r"\\}+", "\n"),
            (r"\\[\\[.*?\\]\\]", ""),
        ]
        for pattern, replacement in patterns:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE | re.MULTILINE)
        cleaned = re.sub(r"\\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"[ ]{3,}", "  ", cleaned)
        return cleaned.strip()

