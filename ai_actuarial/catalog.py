from __future__ import annotations

import re
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Iterable

from .storage import Storage


AI_TERMS = [
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "neural",
    "llm",
    "large language model",
    "generative",
    "genai",
    "chatgpt",
    "openai",
    "transformer",
    "nlp",
]

AI_KEYWORDS = [
    "ai",
    "ml",
    "llm",
    "genai",
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "large language model",
    "generative ai",
]

CATEGORY_RULES: dict[str, list[str]] = {
    "AI": [
        "artificial intelligence",
        "machine learning",
        "deep learning",
        "generative",
        "llm",
        "large language model",
        "neural",
        "nlp",
        "ai",
    ],
    "Regulation & Standards": [
        "ifrs",
        "solvency",
        "asop",
        "ias",
        "gaap",
        "naic",
        "standard",
        "compliance",
        "regulation",
    ],
    "Risk & Capital": [
        "erm",
        "risk",
        "capital",
        "stress",
        "scenario",
        "catastrophe",
        "reinsurance",
    ],
    "Pricing": [
        "pricing",
        "rate",
        "rating",
        "premium",
        "tariff",
    ],
    "Underwriting & Claims": [
        "underwriting",
        "uw",
        "risk selection",
        "appetite",
        "claim",
        "claims",
        "loss",
        "settlement",
    ],
    "Reserving": [
        "reserve",
        "reserving",
        "ibnr",
    ],
    "P&C": [
        "property",
        "casualty",
        "p&c",
        "auto",
        "general insurance",
    ],
    "Life": [
        "life",
        "annuity",
        "mortality",
        "longevity",
    ],
    "Health": [
        "health",
        "medical",
        "morbidity",
    ],
    "LTC / DI / CI": [
        "long term care",
        "ltc",
        "disability income",
        "di",
        "critical illness",
        "ci",
    ],
    "Data & Analytics": [
        "data",
        "analytics",
        "model",
        "modeling",
        "statistics",
        "forecast",
        "predictive",
        "regression",
        "time series",
        "governance",
    ],
    "Operations / Automation": [
        "automation",
        "workflow",
        "process",
        "rpa",
        "system",
        "implementation",
        "tooling",
    ],
    "Education / Events": [
        "webinar",
        "seminar",
        "conference",
        "agenda",
        "workshop",
        "training",
        "course",
        "syllabus",
        "lecture",
        "slides",
    ],
    "Investment / ALM": [
        "investment",
        "asset",
        "liability",
        "alm",
        "portfolio",
        "interest rate",
        "yield",
        "duration",
    ],
}

_KEYBERT_MODEL = None


@dataclass
class CatalogItem:
    source_site: str | None
    title: str | None
    original_filename: str | None
    url: str | None
    local_path: str | None
    keywords: list[str]
    summary: str
    category: str


def _read_pdf(path: Path, max_chars: int) -> str:
    from pypdf import PdfReader

    text_parts: list[str] = []
    reader = PdfReader(str(path))
    for page in reader.pages[:10]:
        page_text = page.extract_text() or ""
        text_parts.append(page_text)
        if sum(len(t) for t in text_parts) >= max_chars:
            break
    return "\n".join(text_parts)[:max_chars]


def _read_docx(path: Path, max_chars: int) -> str:
    import docx

    doc = docx.Document(str(path))
    text = "\n".join(p.text for p in doc.paragraphs if p.text)
    return text[:max_chars]


def _read_pptx(path: Path, max_chars: int) -> str:
    from pptx import Presentation

    prs = Presentation(str(path))
    texts: list[str] = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if hasattr(shape, "text"):
                texts.append(shape.text)
        if sum(len(t) for t in texts) >= max_chars:
            break
    return "\n".join(texts)[:max_chars]


def extract_text(path: Path, max_chars: int = 20000) -> str:
    if not path.exists():
        return ""
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            return _read_pdf(path, max_chars)
        if suffix == ".docx":
            return _read_docx(path, max_chars)
        if suffix == ".pptx":
            return _read_pptx(path, max_chars)
    except Exception:
        return ""
    return ""


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if len(p.strip()) > 20]


def summarize(text: str, keywords: list[str], max_sentences: int = 4) -> str:
    sentences = _split_sentences(text)
    if not sentences:
        return ""
    if not keywords:
        return " ".join(sentences[:max_sentences])
    keyset = [k.lower() for k in keywords]
    scored = []
    for s in sentences:
        sl = s.lower()
        score = sum(1 for k in keyset if k in sl)
        scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    picked = [s for _, s in scored[:max_sentences]]
    return " ".join(picked)


def _ai_hit(title: str | None, keywords: list[str]) -> bool:
    hay = (title or "") + " " + " ".join(keywords)
    hay = hay.lower()
    for term in AI_KEYWORDS:
        if term in hay:
            return True
    return False


def is_ai_related(text: str, keywords: list[str], title: str | None = None) -> bool:
    # Keep broader AI detection for optional ai_only filtering
    hay = (title or "") + " " + text
    hay = hay.lower()
    for term in AI_TERMS:
        if term in hay:
            return True
    for k in keywords:
        if k.lower() in hay:
            return True
    return False


def extract_keywords(text: str, title: str | None = None, top_n: int = 8) -> list[str]:
    if not text and not title:
        return []
    if os.getenv("KEYBERT_DISABLE") == "1":
        return _light_keywords(text, title, top_n)
    global _KEYBERT_MODEL
    try:
        from keybert import KeyBERT

        if _KEYBERT_MODEL is None:
            _KEYBERT_MODEL = KeyBERT()
        base = (title or "") + "\n" + text
        kw = _KEYBERT_MODEL.extract_keywords(base, top_n=top_n, stop_words="english")
        return [k for k, _ in kw]
    except Exception:
        return _light_keywords(text, title, top_n)


def _light_keywords(text: str, title: str | None, top_n: int) -> list[str]:
    combined = ((title or "") + "\n" + (text or "")).lower()
    combined = combined.replace("\u2013", "-").replace("\u2014", "-")

    specials = []
    for pat in [r"\bifrs\s*17\b", r"\bcovid[-\s]*19\b", r"\bsolvency\s*ii\b"]:
        m = re.findall(pat, combined, flags=re.IGNORECASE)
        specials.extend(m)

    def tokens(s: str) -> list[str]:
        return re.findall(r"[a-zA-Z][a-zA-Z0-9\-]*", s.lower())

    text_tokens = tokens(text or "")
    title_tokens = tokens(title or "")

    freq: dict[str, int] = {}
    for t in text_tokens:
        if len(t) < 3:
            continue
        if t.isdigit():
            continue
        freq[t] = freq.get(t, 0) + 1

    bigrams: dict[str, int] = {}
    for a, b in zip(text_tokens, text_tokens[1:]):
        if a.isdigit() and b.isdigit():
            continue
        phrase = f"{a} {b}"
        bigrams[phrase] = bigrams.get(phrase, 0) + 1

    title_set = set(title_tokens)
    title_bigrams = set(f"{a} {b}" for a, b in zip(title_tokens, title_tokens[1:]))

    scored: dict[str, int] = {}
    for t, c in freq.items():
        scored[t] = scored.get(t, 0) + c + (3 if t in title_set else 0)
    for t, c in bigrams.items():
        scored[t] = scored.get(t, 0) + c + (4 if t in title_bigrams else 0)

    for s in specials:
        s_norm = re.sub(r"\s+", " ", s.strip().lower())
        scored[s_norm] = scored.get(s_norm, 0) + 10

    ranked = sorted(scored.items(), key=lambda x: x[1], reverse=True)
    out: list[str] = []
    for term, _ in ranked:
        if term.isdigit():
            continue
        if term not in out:
            out.append(term)
        if len(out) >= top_n:
            break
    return out


def categorize(title: str | None, text: str, keywords: list[str]) -> str:
    hay = (title or "") + " " + text + " " + " ".join(keywords)
    hay = hay.lower()
    matches: list[tuple[str, int]] = []
    for cat, terms in CATEGORY_RULES.items():
        score = sum(1 for t in terms if t in hay)
        if score > 0:
            matches.append((cat, score))
    if not matches:
        return "Other"
    matches.sort(key=lambda x: x[1], reverse=True)
    cats = [c for c, _ in matches]
    # Force AI if title/keywords contain AI/ML/LLM/GenAI terms
    if _ai_hit(title, keywords) and "AI" not in cats:
        cats = ["AI"] + cats
    return "; ".join(cats[:3])


def _fallback_keywords(text: str, top_n: int) -> list[str]:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            max_features=50,
        )
        tfidf = vectorizer.fit_transform([text])
        scores = tfidf.toarray()[0]
        terms = vectorizer.get_feature_names_out()
        ranked = sorted(zip(terms, scores), key=lambda x: x[1], reverse=True)
        return [t for t, _ in ranked[:top_n]]
    except Exception:
        return []


def build_catalog(
    storage: Storage,
    site_filter: str | None,
    limit: int,
    ai_only: bool = False,
    offset: int = 0,
) -> list[CatalogItem]:
    rows = storage.export_files()
    if offset > 0:
        rows = rows[offset:]
    if limit is not None:
        rows = rows[:limit]
    items: list[CatalogItem] = []
    filters: list[str] = []
    if site_filter:
        filters = [s.strip().lower() for s in site_filter.split(",") if s.strip()]
    for row in rows:
        site = row.get("source_site")
        if filters:
            if not site or not any(f in site.lower() for f in filters):
                continue
        path = row.get("local_path")
        if not path:
            continue
        text = extract_text(Path(path))
        if not text:
            continue
        title = row.get("title")
        keywords = extract_keywords(text, title=title)
        if ai_only and not is_ai_related(text, keywords, title=title):
            continue
        summary = summarize(text, keywords)
        category = categorize(title, text, keywords)
        items.append(
            CatalogItem(
                source_site=site,
                title=title,
                original_filename=row.get("original_filename"),
                url=row.get("url"),
                local_path=path,
                keywords=keywords,
                summary=summary,
                category=category,
            )
        )
        if limit is not None and len(items) >= limit:
            break
    return items


def write_catalog_md(path: Path, items: Iterable[CatalogItem], append: bool = False) -> None:
    headers = [
        "category",
        "source_site",
        "title",
        "original_filename",
        "keywords",
        "summary",
        "url",
        "local_path",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with open(path, mode, encoding="utf-8") as f:
        if not append:
            f.write("| " + " | ".join(headers) + " |\n")
            f.write("| " + " | ".join(["---"] * len(headers)) + " |\n")
        for item in items:
            values = [
                item.category,
                item.source_site or "",
                item.title or "",
                item.original_filename or "",
                ", ".join(item.keywords),
                item.summary,
                item.url or "",
                item.local_path or "",
            ]
            safe = [v.replace("|", " ") for v in values]
            f.write("| " + " | ".join(safe) + " |\n")
