"""Hermetic runtime proof that the image ships every supported tokenizer."""

import os
from pathlib import Path

import tiktoken

from ai_actuarial.rag.semantic_chunking import SemanticChunker

ENCODING_NAMES = (
    "cl100k_base",
    "p50k_base",
    "p50k_edit",
    "o200k_base",
    "o200k_harmony",
    "gpt2",
    "r50k_base",
)
MODEL_NAMES = (
    "gpt-4",
    "gpt-4o",
    "gpt-4.1",
    "gpt-5",
    "o1",
    "o3",
    "o4-mini",
    "text-embedding-3-large",
    "text-embedding-3-small",
    "text-embedding-ada-002",
)


def main() -> None:
    cache_dir = Path(os.environ["TIKTOKEN_CACHE_DIR"])
    assert cache_dir.is_dir(), f"missing tokenizer cache directory: {cache_dir}"
    assert any(cache_dir.iterdir()), f"empty tokenizer cache directory: {cache_dir}"

    encodings = {name: tiktoken.get_encoding(name) for name in ENCODING_NAMES}
    model_encodings = {model: tiktoken.encoding_for_model(model) for model in MODEL_NAMES}
    assert model_encodings["gpt-4"].name == encodings["cl100k_base"].name
    assert {encoding.name for encoding in model_encodings.values()} <= {
        encoding.name for encoding in encodings.values()
    }

    chunks = SemanticChunker(max_tokens=30, min_tokens=1).chunk_document(
        "# Introduction\n\nA short actuarial introduction."
    )
    assert chunks and chunks[0].token_count > 0
    print(
        "offline tokenizer smoke OK: "
        f"tiktoken={tiktoken.__version__} "
        f"encodings={','.join(encodings)} models={','.join(model_encodings)}"
    )


if __name__ == "__main__":
    main()
