"""Centralized app settings loaded from `.env`.

This module is intentionally copied/adapted from `ferryhe/doc_to_md` so the
document-to-markdown engines can be integrated into this project with minimal
drift. It uses pydantic-settings to read values directly from the project's
`.env` file (no need to export them into the shell environment).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "input"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "output"

EngineName = Literal[
    "mistral",
    "deepseekocr",
    "local",
    "docling",
    "marker",
]


class Settings(BaseSettings):
    # API keys
    mistral_api_key: str | None = Field(default=None, alias="MISTRAL_API_KEY")
    siliconflow_api_key: str | None = Field(default=None, alias="SILICONFLOW_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    # Engine defaults
    default_engine: EngineName = Field(default="local", alias="DEFAULT_ENGINE")
    mistral_default_model: str = Field(default="mistral-ocr-latest", alias="MISTRAL_DEFAULT_MODEL")
    siliconflow_default_model: str = Field(default="deepseek-ai/DeepSeek-OCR", alias="SILICONFLOW_DEFAULT_MODEL")
    siliconflow_base_url: str = Field(default="https://api.siliconflow.cn/v1", alias="SILICONFLOW_BASE_URL")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_default_model: str = Field(default="gpt-4o-mini", alias="OPENAI_DEFAULT_MODEL")
    openai_timeout_seconds: float = Field(default=60.0, alias="OPENAI_TIMEOUT_SECONDS")

    # Chatbot configuration (for future AI chatbot feature)
    chatbot_model: str = Field(default="gpt-4-turbo", alias="CHATBOT_MODEL")
    chatbot_temperature: float = Field(default=0.7, alias="CHATBOT_TEMPERATURE")
    chatbot_max_tokens: int = Field(default=1000, alias="CHATBOT_MAX_TOKENS")
    chatbot_streaming_enabled: bool = Field(default=True, alias="CHATBOT_STREAMING_ENABLED")
    chatbot_max_context_messages: int = Field(default=10, alias="CHATBOT_MAX_CONTEXT_MESSAGES")
    chatbot_default_mode: str = Field(default="expert", alias="CHATBOT_DEFAULT_MODE")

    # Mistral OCR tuning
    mistral_timeout_seconds: float = Field(default=60.0, alias="MISTRAL_TIMEOUT_SECONDS")
    mistral_retry_attempts: int = Field(default=3, alias="MISTRAL_RETRY_ATTEMPTS")
    mistral_max_pdf_tokens: int = Field(default=9000, alias="MISTRAL_MAX_PDF_TOKENS")
    mistral_max_pages_per_chunk: int = Field(default=25, alias="MISTRAL_MAX_PAGES_PER_CHUNK")
    mistral_extract_footer: bool = Field(default=True, alias="MISTRAL_EXTRACT_FOOTER")
    mistral_extract_header: bool = Field(default=True, alias="MISTRAL_EXTRACT_HEADER")

    # SiliconFlow (DeepSeek OCR) tuning
    siliconflow_timeout_seconds: float = Field(default=60.0, alias="SILICONFLOW_TIMEOUT_SECONDS")
    siliconflow_retry_attempts: int = Field(default=3, alias="SILICONFLOW_RETRY_ATTEMPTS")
    siliconflow_max_input_tokens: int = Field(default=3500, alias="SILICONFLOW_MAX_INPUT_TOKENS")
    siliconflow_chunk_overlap_tokens: int = Field(default=200, alias="SILICONFLOW_CHUNK_OVERLAP_TOKENS")

    # Docling tuning
    docling_max_pages: int | None = Field(default=None, alias="DOCLING_MAX_PAGES")
    docling_raise_on_error: bool = Field(default=True, alias="DOCLING_RAISE_ON_ERROR")

    # Marker tuning
    marker_use_llm: bool = Field(default=False, alias="MARKER_USE_LLM")
    marker_processors: str | None = Field(default=None, alias="MARKER_PROCESSORS")
    marker_page_range: str | None = Field(default=None, alias="MARKER_PAGE_RANGE")
    marker_extract_images: bool = Field(default=False, alias="MARKER_EXTRACT_IMAGES")
    marker_llm_service: str | None = Field(default=None, alias="MARKER_LLM_SERVICE")

    # Optional dirs (kept for compatibility with upstream doc_to_md structure)
    input_dir: Path = Field(default=DEFAULT_INPUT_DIR)
    output_dir: Path = Field(default=DEFAULT_OUTPUT_DIR)

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",  # Allow unrelated keys in .env (project-wide env file)
    )

    @field_validator("input_dir", "output_dir", mode="before")
    def _coerce_path(cls, value: str | Path) -> Path:  # noqa: D401
        """Ensure directories are stored as Path objects."""
        return Path(value)

    @model_validator(mode="after")
    def _validate_environment(self) -> "Settings":
        for directory in (self.input_dir, self.output_dir):
            directory.mkdir(parents=True, exist_ok=True)

        if self.siliconflow_chunk_overlap_tokens >= self.siliconflow_max_input_tokens:
            raise ValueError("SILICONFLOW_CHUNK_OVERLAP_TOKENS must be smaller than SILICONFLOW_MAX_INPUT_TOKENS")

        for field_name in ("mistral_retry_attempts", "siliconflow_retry_attempts"):
            value = getattr(self, field_name)
            if value < 1:
                raise ValueError(f"{field_name.upper()} must be at least 1")

        if self.docling_max_pages is not None and self.docling_max_pages < 1:
            raise ValueError("DOCLING_MAX_PAGES must be at least 1 when provided")

        # Validate chatbot settings
        if not 0.0 <= self.chatbot_temperature <= 2.0:
            raise ValueError("CHATBOT_TEMPERATURE must be between 0.0 and 2.0")
        
        if self.chatbot_max_tokens < 1:
            raise ValueError("CHATBOT_MAX_TOKENS must be at least 1")
        
        if self.chatbot_max_context_messages < 1:
            raise ValueError("CHATBOT_MAX_CONTEXT_MESSAGES must be at least 1")
        
        valid_chatbot_modes = ["expert", "summary", "tutorial", "comparison"]
        if self.chatbot_default_mode not in valid_chatbot_modes:
            raise ValueError(f"CHATBOT_DEFAULT_MODE must be one of {valid_chatbot_modes}")

        return self

    @field_validator("docling_max_pages", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance so imports stay cheap."""
    return Settings()
