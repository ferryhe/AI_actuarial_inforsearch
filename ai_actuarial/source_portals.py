"""Reviewed directory pages that receive a reader-facing history of real captures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourcePortal:
    portal_key: str
    url: str
    site_ids: tuple[str, ...]
    capture_urls: tuple[str, ...]
    title_zh: str
    title_en: str
    institution_zh: str
    institution_en: str
    overview_zh: str
    overview_en: str
    extraction_site_id: str | None = None
    scope_key: str = "main-or-article-v2"

    @property
    def extraction_source_id(self) -> str:
        return self.extraction_site_id or self.site_ids[0]


SOURCE_PORTALS = (
    SourcePortal(
        "soa-research-topics",
        "https://www.soa.org/research/research-topic-list/",
        ("soa",),
        ("https://www.soa.org/research/research-topic-list/",),
        "研究主题目录",
        "Research Topics",
        "美国精算师协会（SOA）",
        "Society of Actuaries (SOA)",
        "汇集 SOA 按研究主题整理的资料入口。",
        "SOA's directory of materials organized by research topic.",
    ),
    SourcePortal(
        "soa-artificial-intelligence",
        "https://www.soa.org/research/topics/artificial-intelligence-topic-landing/",
        ("soa", "soa-ai-topic-landing"),
        ("https://www.soa.org/research/topics/artificial-intelligence-topic-landing/",),
        "人工智能专题",
        "Artificial Intelligence",
        "美国精算师协会（SOA）",
        "Society of Actuaries (SOA)",
        "汇集 SOA 人工智能专题的研究与相关资料。",
        "SOA's research and related materials on artificial intelligence.",
        extraction_site_id="soa-ai-topic-landing",
    ),
    SourcePortal(
        "cas-publications-research",
        "https://www.casact.org/publications-research/publications",
        ("cas",),
        (
            "https://www.casact.org/publications-research",
            "https://www.casact.org/publications-research/publications",
        ),
        "出版物与研究",
        "Publications & Research",
        "美国意外险精算师协会（CAS）",
        "Casualty Actuarial Society (CAS)",
        "CAS 的出版物、研究成果和专业资源入口。",
        "CAS publications, research, and professional resources.",
    ),
    SourcePortal(
        "cia-publications",
        "https://www.cia-ica.ca/publications",
        ("cia-ica", "cia-research-publications"),
        (
            "https://www.cia-ica.ca/publications",
            "https://www.cia-ica.ca/publications/",
        ),
        "出版物",
        "Publications",
        "加拿大精算师协会（CIA）",
        "Canadian Institute of Actuaries (CIA)",
        "加拿大精算师协会发布的研究与专业资料入口。",
        "Research and professional materials published by the CIA.",
    ),
    SourcePortal(
        "cca-professional-resources",
        "https://www.ccactuaries.org/professional-resources",
        ("cca",),
        ("https://www.ccactuaries.org/professional-resources",),
        "专业资源",
        "Professional Resources",
        "咨询精算师协会（CCA）",
        "Conference of Consulting Actuaries (CCA)",
        "CCA 面向咨询精算专业人士的资料入口。",
        "Resources for consulting actuarial professionals from the CCA.",
    ),
    SourcePortal(
        "ifoa-insight",
        "https://actuaries.org.uk/insight/",
        ("ifoa-uk",),
        (
            "https://www.actuaries.org.uk/insight/",
            "https://actuaries.org.uk/insight/",
        ),
        "行业洞察",
        "Insight",
        "英国精算师协会（IFoA）",
        "Institute and Faculty of Actuaries (IFoA)",
        "IFoA 的研究、观点与行业洞察入口。",
        "IFoA research, perspectives, and industry insight.",
    ),
    SourcePortal(
        "france-actuarial-memoirs",
        "https://www.institutdesactuaires.com/se-documenter/memoires/memoires-d-actuariat-4651",
        ("france",),
        ("https://www.institutdesactuaires.com/se-documenter/memoires/memoires-d-actuariat-4651",),
        "精算论文",
        "Actuarial Theses",
        "法国精算师协会",
        "Institut des Actuaires",
        "法国精算师协会收录的精算论文目录。",
        "The Institut des Actuaires directory of actuarial theses.",
    ),
    SourcePortal(
        "australia-thought-leadership",
        "https://www.actuaries.asn.au/research-analysis/thought-leadership",
        ("australia",),
        ("https://www.actuaries.asn.au/research-analysis/thought-leadership",),
        "研究与观点",
        "Research & Analysis",
        "澳大利亚精算师协会（Actuaries Institute）",
        "Actuaries Institute Australia",
        "澳大利亚精算师协会的研究分析与专业观点入口。",
        "Research, analysis, and professional perspectives from Actuaries Institute Australia.",
    ),
    SourcePortal(
        "italy-publications",
        "https://ordineattuari.it/pubblicazioni/",
        ("italy",),
        ("https://ordineattuari.it/pubblicazioni/",),
        "出版物",
        "Publications",
        "意大利精算师协会",
        "Italian National Council of Actuaries",
        "意大利精算师协会发布的资料入口。",
        "Materials published by the Italian National Council of Actuaries.",
    ),
    SourcePortal(
        "europe-papers",
        "https://actuary.eu/papers/",
        ("aae",),
        ("https://actuary.eu/papers/",),
        "研究论文",
        "Research Papers",
        "欧洲精算协会（AAE）",
        "Actuarial Association of Europe (AAE)",
        "欧洲精算协会的研究论文与相关资料入口。",
        "Research papers and related materials from the AAE.",
    ),
)

SOURCE_PORTALS_BY_URL = {}
for _portal in SOURCE_PORTALS:
    for _url in dict.fromkeys((_portal.url, *_portal.capture_urls)):
        _prior = SOURCE_PORTALS_BY_URL.get(_url)
        if _prior is not None and _prior.portal_key != _portal.portal_key:
            raise ValueError(f"Source portal URL belongs to multiple portal cards: {_url}")
        SOURCE_PORTALS_BY_URL[_url] = _portal
SOURCE_PORTALS_BY_KEY = {portal.portal_key: portal for portal in SOURCE_PORTALS}
SOURCE_PORTAL_URLS = tuple(SOURCE_PORTALS_BY_URL)


def source_portal_cards() -> list[dict[str, str | int]]:
    return [
        {
            "portal_key": portal.portal_key,
            "url": portal.url,
            "title_zh": portal.title_zh,
            "title_en": portal.title_en,
            "institution_zh": portal.institution_zh,
            "institution_en": portal.institution_en,
            "overview_zh": portal.overview_zh,
            "overview_en": portal.overview_en,
            "sort_order": index,
        }
        for index, portal in enumerate(SOURCE_PORTALS)
    ]
