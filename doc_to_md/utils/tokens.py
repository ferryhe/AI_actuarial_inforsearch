"""Lightweight helpers around token counting and chunking.

Prefer exact token counts via `tiktoken` when available, otherwise fall back to
rough character-based splitting so the feature still works without extra deps.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

DEFAULT_ENCODING = "cl100k_base"


@lru_cache
def _get_encoding(name: str = DEFAULT_ENCODING):
    try:
        import tiktoken  # type: ignore
    except ImportError:  # pragma: no cover
        return None
    return tiktoken.get_encoding(name)


def count_tokens(text: str, encoding_name: str = DEFAULT_ENCODING) -> int:
    if not text:
        return 0
    enc = _get_encoding(encoding_name)
    if enc is None:
        return max(1, len(text) // 4)
    return len(enc.encode(text))


def split_by_tokens(
    text: str,
    max_tokens: int,
    overlap_tokens: int = 0,
    encoding_name: str = DEFAULT_ENCODING,
) -> List[str]:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens cannot be negative")
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be smaller than max_tokens")

    enc = _get_encoding(encoding_name)
    if enc is None:
        approx_chars_per_token = 4
        max_chars = max_tokens * approx_chars_per_token
        overlap_chars = overlap_tokens * approx_chars_per_token
        if len(text) <= max_chars:
            return [text]
        segments: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            segments.append(text[start:end])
            if end == len(text):
                break
            start = max(0, end - overlap_chars)
        return segments

    tokens = enc.encode(text or "")
    if len(tokens) <= max_tokens:
        return [text]

    segments: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        segments.append(enc.decode(chunk_tokens))
        if end == len(tokens):
            break
        start = end - overlap_tokens
    return segments

