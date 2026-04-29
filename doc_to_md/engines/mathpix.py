"""Mathpix OCR engine backed by the official HTTP API."""

from __future__ import annotations

import json
import mimetypes
import time
from pathlib import Path
from typing import Any

import requests

from config.settings import get_settings
from doc_to_md.engines.base import Engine, EngineResponse, RetryableRequestMixin


class MathpixEngine(RetryableRequestMixin, Engine):
    name = "mathpix"
    _REPORTED_MODEL = "mathpix"
    _BASE_URL = "https://api.mathpix.com/v3"
    _DOCUMENT_SUFFIXES = {".pdf", ".docx", ".pptx"}
    _IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    _TERMINAL_ERROR_STATUSES = {"error", "failed", "canceled", "cancelled"}

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        if model not in {None, self._REPORTED_MODEL}:
            raise ValueError("MathpixEngine does not support model overrides.")
        settings = get_settings()
        if not settings.mathpix_app_id:
            raise RuntimeError("MATHPIX_APP_ID missing")
        app_key = api_key or settings.mathpix_app_key
        if not app_key:
            raise RuntimeError("MATHPIX_APP_KEY missing")
        super().__init__(retry_attempts=settings.mathpix_retry_attempts)
        self.app_id = settings.mathpix_app_id
        self.app_key = app_key
        self.model = self._REPORTED_MODEL
        self.base_url = (base_url or settings.mathpix_base_url or self._BASE_URL).rstrip("/")
        self.timeout_seconds = settings.mathpix_timeout_seconds
        self.poll_interval_seconds = settings.mathpix_poll_interval_seconds
        self.output_format = settings.mathpix_output_format.lower()
        self.headers = {"app_id": self.app_id, "app_key": self.app_key}

    def convert(self, path: Path) -> EngineResponse:  # pragma: no cover - network call
        suffix = path.suffix.lower()
        if suffix in self._DOCUMENT_SUFFIXES:
            return EngineResponse(markdown=self._process_document(path), model=self.model)
        if suffix in self._IMAGE_SUFFIXES:
            return EngineResponse(markdown=self._process_image(path), model=self.model)
        raise RuntimeError(
            "Mathpix supports PDFs, DOCX, PPTX, and common image formats. "
            f"Got '{suffix or 'unknown'}'."
        )

    def _process_document(self, path: Path) -> str:
        payload = self._submit_document(path)
        pdf_id = str(payload.get("pdf_id") or "").strip()
        if not pdf_id:
            raise RuntimeError(f"Mathpix document submission did not return a pdf_id: {payload}")
        self._wait_for_completion(pdf_id)
        return self._download_document_result(pdf_id).strip() or "_No content returned by Mathpix._"

    def _submit_document(self, path: Path) -> dict[str, Any]:
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        options = {"conversion_formats": {self.output_format: True}}

        def send_request() -> dict[str, Any]:
            with path.open("rb") as handle:
                response = requests.post(
                    f"{self.base_url}/pdf",
                    headers=self.headers,
                    files={"file": (path.name, handle, mime_type)},
                    data={"options_json": json.dumps(options)},
                    timeout=self.timeout_seconds,
                )
            return self._parse_json_response(response, operation="mathpix_submit_document")

        return self._request_with_retry(send_request, operation="mathpix_submit_document")

    def _wait_for_completion(self, pdf_id: str) -> dict[str, Any]:
        started_at = time.perf_counter()
        last_status = "unknown"
        while True:
            payload = self._request_with_retry(lambda: self._fetch_status(pdf_id), operation=f"mathpix_status_{pdf_id}")
            status = str(payload.get("status") or "").strip().lower()
            if status:
                last_status = status
            if status == "completed":
                return payload
            if status in self._TERMINAL_ERROR_STATUSES or payload.get("error"):
                detail = payload.get("error") or payload.get("error_info") or payload
                raise RuntimeError(f"Mathpix job {pdf_id} failed with status '{status or 'unknown'}': {detail}")
            if time.perf_counter() - started_at >= self.timeout_seconds:
                raise TimeoutError(
                    f"Mathpix job {pdf_id} did not complete within {self.timeout_seconds:.0f}s "
                    f"(last status: {last_status})."
                )
            time.sleep(self.poll_interval_seconds)

    def _fetch_status(self, pdf_id: str) -> dict[str, Any]:
        response = requests.get(f"{self.base_url}/pdf/{pdf_id}", headers=self.headers, timeout=self.timeout_seconds)
        return self._parse_json_response(response, operation=f"mathpix_fetch_status_{pdf_id}")

    def _download_document_result(self, pdf_id: str) -> str:
        return self._request_with_retry(
            lambda: self._fetch_document_result(pdf_id),
            operation=f"mathpix_download_{self.output_format}_{pdf_id}",
        )

    def _fetch_document_result(self, pdf_id: str) -> str:
        response = requests.get(
            f"{self.base_url}/pdf/{pdf_id}.{self.output_format}",
            headers=self.headers,
            timeout=self.timeout_seconds,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"Mathpix result download failed with HTTP {response.status_code}: {response.text[:300]}"
            ) from exc
        return response.text

    def _process_image(self, path: Path) -> str:
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        options = {"formats": ["text"]}

        def send_request() -> str:
            with path.open("rb") as handle:
                response = requests.post(
                    f"{self.base_url}/text",
                    headers=self.headers,
                    files={"file": (path.name, handle, mime_type)},
                    data={"options_json": json.dumps(options)},
                    timeout=self.timeout_seconds,
                )
            payload = self._parse_json_response(response, operation="mathpix_image_ocr")
            text = payload.get("text")
            if not isinstance(text, str):
                if payload.get("error"):
                    raise RuntimeError(f"Mathpix image OCR failed: {payload['error']}")
                raise RuntimeError(f"Mathpix image OCR returned no text field: {payload}")
            return text

        return self._request_with_retry(send_request, operation="mathpix_image_ocr").strip() or "_No content returned by Mathpix._"

    @staticmethod
    def _parse_json_response(response: requests.Response, *, operation: str) -> dict[str, Any]:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f"{operation} failed with HTTP {response.status_code}: {response.text[:300]}") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError(f"{operation} returned non-JSON response: {response.text[:300]}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"{operation} returned an unexpected payload: {payload!r}")
        return payload
