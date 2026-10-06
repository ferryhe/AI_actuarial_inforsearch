"""Narrow OpenAI model capability checks shared by request builders."""

from __future__ import annotations

import re


_OPENAI_PROVIDERS = {"openai", "azure_openai"}
_GPT6_NAME = re.compile(r"^gpt-6(?:$|[.-])")
_AZURE_GPT6_DEPLOYMENT = re.compile(r"(?:^|-)gpt-6(?:$|[.-])")


def is_openai_gpt6_model(provider: str | None, model: str | None) -> bool:
    """Whether an OpenAI model or explicitly named Azure deployment is GPT-6."""
    if str(provider or "").strip().lower() not in _OPENAI_PROVIDERS:
        return False
    model_name = str(model or "").strip().lower().split("/")[-1]
    if _GPT6_NAME.match(model_name):
        return True
    return str(provider or "").strip().lower() == "azure_openai" and bool(
        _AZURE_GPT6_DEPLOYMENT.search(model_name.replace("_", "-"))
    )
