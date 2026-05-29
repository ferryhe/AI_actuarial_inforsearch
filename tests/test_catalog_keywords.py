from __future__ import annotations

import sys
import types

from ai_actuarial import catalog


def test_extract_keywords_uses_lightweight_deterministic_path(monkeypatch) -> None:
    class FailIfUsed:
        def __init__(self) -> None:
            raise AssertionError("KeyBERT should not be imported or instantiated")

    monkeypatch.setitem(sys.modules, "keybert", types.SimpleNamespace(KeyBERT=FailIfUsed))

    keywords = catalog.extract_keywords(
        "IFRS 17 solvency capital requirements and actuarial model governance",
        title="Capital briefing",
        top_n=4,
    )

    assert keywords
    assert "keybert" not in catalog.CATALOG_VERSION.lower()


def test_extract_keywords_filters_common_stop_words() -> None:
    keywords = catalog.extract_keywords(
        (
            "The company and the board of directors and the management of the company "
            "provide an overview of the business and the results for the year. "
            "The company and the board discussed insurance capital and solvency."
        ),
        title="Annual report",
        top_n=8,
    )

    assert "the" not in keywords
    assert "and" not in keywords
    assert "and the" not in keywords
    assert "the company" not in keywords
    assert {"company", "board", "capital", "solvency"} & set(keywords)
