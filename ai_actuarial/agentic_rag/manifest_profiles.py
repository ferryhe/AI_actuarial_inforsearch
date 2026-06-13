"""Manifest profiles defining ready_data artifact schemas per level.

Three tiers:

- L0 (general):   Basic doc_catalog + sections for general/research/internal docs.
- L1 (regulation): Professional structure with aliases, summaries, relations.
- L2 (formula):    L1 + formula_cards, tables, calculation terms.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ManifestProfile:
    profile: str  # "general", "regulation", "formula"
    version: str
    artifacts: list[str]
    description: str


L0_GENERAL = ManifestProfile(
    profile="general",
    version="1",
    artifacts=[
        "doc_catalog.jsonl",
        "sections.jsonl",
        "ready_data_manifest.json",
    ],
    description="Basic semi-structured manifest for general/research/internal documents",
)

L1_REGULATION = ManifestProfile(
    profile="regulation",
    version="1",
    artifacts=[
        "doc_catalog.jsonl",
        "title_aliases.jsonl",
        "doc_summaries.jsonl",
        "sections_structured.jsonl",
        "relations_graph.json",
        "ready_data_manifest.json",
    ],
    description="Professional structured manifest for regulation/standard/compliance documents",
)

L2_FORMULA = ManifestProfile(
    profile="formula",
    version="1",
    artifacts=[
        "doc_catalog.jsonl",
        "title_aliases.jsonl",
        "doc_summaries.jsonl",
        "sections_structured.jsonl",
        "formula_cards.jsonl",
        "tables_structured.jsonl",
        "calculation_terms.jsonl",
        "relations_graph.json",
        "ready_data_manifest.json",
    ],
    description="Formula/actuarial professional manifest with formula cards and tables",
)

PROFILES: dict[str, ManifestProfile] = {
    "general": L0_GENERAL,
    "regulation": L1_REGULATION,
    "formula": L2_FORMULA,
}
