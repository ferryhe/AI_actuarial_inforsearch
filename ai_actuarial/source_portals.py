"""Reviewed source entry cards and their reader-facing history of real observations."""

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
        ("soa", "soa-ai-topic-landing", "soa-ai-bulletin-focused"),
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
    SourcePortal(
        "iaa-papers",
        "https://actuaries.org/publications/papers/",
        ("iaa",),
        ("https://actuaries.org/publications/papers/",),
        "研究论文",
        "Papers",
        "国际精算协会（IAA）",
        "International Actuarial Association (IAA)",
        "国际精算协会公开发布的精算研究论文。",
        "Public actuarial papers from the International Actuarial Association.",
    ),
    SourcePortal(
        "aaa-resource-center",
        "https://actuary.org/resource-center/",
        ("aaa",),
        ("https://actuary.org/resource-center/",),
        "资料中心",
        "Resource Center",
        "美国精算学会（AAA）",
        "American Academy of Actuaries (AAA)",
        "美国精算学会的政策、研究和专业资料目录。",
        "Policy, research, and professional resources from the American Academy of Actuaries.",
    ),
    SourcePortal(
        "dav-knowledge",
        "https://aktuar.de/de/wissen/",
        ("dav",),
        ("https://aktuar.de/de/wissen/",),
        "精算知识",
        "Actuarial Knowledge",
        "德国精算师协会（DAV）",
        "German Association of Actuaries (DAV)",
        "德国精算师协会的专业知识、研究和出版物入口。",
        "Professional knowledge, research, and publications from the DAV.",
    ),
    SourcePortal(
        "swiss-downloads",
        "https://www.actuaries.ch/de/download",
        ("swiss-association-of-actuaries",),
        ("https://www.actuaries.ch/de/download",),
        "资料下载",
        "Downloads",
        "瑞士精算师协会（SAV）",
        "Swiss Association of Actuaries (SAV)",
        "瑞士精算师协会的出版物、公告和专业资料。",
        "Publications, statements, and professional materials from Swiss actuaries.",
    ),
    SourcePortal(
        "spain-papers",
        "https://actuarios.org/category/papers/",
        ("spain",),
        ("https://actuarios.org/category/papers/",),
        "研究论文",
        "Papers",
        "西班牙精算师协会（IAE）",
        "Institute of Spanish Actuaries (IAE)",
        "西班牙精算师协会发布的研究与专业论文。",
        "Research and professional papers from the Institute of Spanish Actuaries.",
    ),
    SourcePortal(
        "india-magazine",
        "https://actuariesindia.org/magazine",
        ("iai",),
        ("https://actuariesindia.org/magazine",),
        "《印度精算师》杂志",
        "The Actuary India",
        "印度精算师协会（IAI）",
        "Institute of Actuaries of India (IAI)",
        "印度精算师协会的专业杂志及历期内容。",
        "The professional magazine and past issues of the Institute of Actuaries of India.",
    ),
    SourcePortal(
        "japan-library",
        "https://www.actuaries.jp/english/lib/",
        ("iaj",),
        (
            "https://www.actuaries.jp/english/lib/",
            "https://www.actuaries.jp/english/lib/index.html",
        ),
        "专业资料库",
        "Library",
        "日本精算师协会（IAJ）",
        "Institute of Actuaries of Japan (IAJ)",
        "日本精算师协会公开的英文精算资料入口。",
        "Public English-language actuarial materials from the Institute of Actuaries of Japan.",
    ),
    SourcePortal(
        "korea-public-information",
        "https://www.actuary.or.kr/regulation/infoOpen.do",
        ("institute-of-actuaries-of",),
        ("https://www.actuary.or.kr/regulation/infoOpen.do",),
        "公开资料",
        "Public Information",
        "韩国保险精算师协会",
        "Institute of Actuaries of Korea",
        "韩国保险精算师协会公开的专业资料与文件。",
        "Public professional materials and documents from the Institute of Actuaries of Korea.",
    ),
    SourcePortal(
        "taiwan-professional-rules",
        "https://www.airc.org.tw/rule/101",
        ("aict",),
        ("https://www.airc.org.tw/rule/101",),
        "专业规章",
        "Professional Rules",
        "中华民国精算学会（AIRC）",
        "Actuarial Institute of the Republic of China (AIRC)",
        "中华民国精算学会发布的会员与专业规章资料。",
        "Membership and professional rules published by the AIRC.",
    ),
    SourcePortal(
        "china-research-resources",
        "https://www.e-caa.org.cn/inforMation/about",
        ("caa",),
        ("https://www.e-caa.org.cn/inforMation/about",),
        "研究资源",
        "Research Resources",
        "中国精算师协会（CAA）",
        "China Association of Actuaries (CAA)",
        "中国精算师协会的研究、行业规范及相关资料入口。",
        "Research, industry standards, and related resources from the China Association of Actuaries.",
    ),
    SourcePortal(
        "hong-kong-magazine",
        "https://actuaries.org.hk/pages/26/Magazine/25/ASHK%20Magazine",
        ("ashk",),
        ("https://actuaries.org.hk/pages/26/Magazine/25/ASHK%20Magazine",),
        "学会杂志",
        "Actuzine",
        "香港精算学会（ASHK）",
        "Actuarial Society of Hong Kong (ASHK)",
        "香港精算学会的专业杂志和历期内容。",
        "The professional magazine and past issues of the Actuarial Society of Hong Kong.",
    ),
    SourcePortal(
        "south-africa-research",
        "https://www.actuarialsociety.org.za/public-benefits-research/",
        ("assa",),
        ("https://www.actuarialsociety.org.za/public-benefits-research/",),
        "研究与公共资源",
        "Research & Public Benefits",
        "南非精算师协会（ASSA）",
        "Actuarial Society of South Africa (ASSA)",
        "南非精算师协会的研究、期刊与公共资源入口。",
        "Research, journals, and public resources from the Actuarial Society of South Africa.",
    ),
    SourcePortal(
        "kenya-resources",
        "https://www.actuarieskenya.or.ke/resources",
        ("task",),
        ("https://www.actuarieskenya.or.ke/resources",),
        "大会资料",
        "Convention Resources",
        "肯尼亚精算师协会（TASK）",
        "Actuarial Society of Kenya (TASK)",
        "肯尼亚精算师协会公开的大会报告和演示材料。",
        "Presentations and materials from Actuarial Society of Kenya conventions.",
    ),
    SourcePortal(
        "brazil-publications",
        "https://atuarios.org.br/publicacoes/",
        ("iba-brazil",),
        ("https://atuarios.org.br/publicacoes/",),
        "出版物",
        "Publications",
        "巴西精算师协会（IBA）",
        "Brazilian Institute of Actuaries (IBA)",
        "巴西精算师协会的专业杂志与出版物。",
        "Professional magazines and publications from the Brazilian Institute of Actuaries.",
    ),
    SourcePortal(
        "mexico-publications",
        "https://www.conacmexico.org.mx/publicaciones-y-recursos",
        ("conac-mexico",),
        ("https://www.conacmexico.org.mx/publicaciones-y-recursos",),
        "出版物与资源",
        "Publications & Resources",
        "墨西哥国家精算师学会（CONAC）",
        "National College of Actuaries of Mexico (CONAC)",
        "墨西哥国家精算师学会的出版物、期刊和专业资源。",
        "Publications, journals, and professional resources from CONAC.",
    ),
    SourcePortal(
        "morocco-documents",
        "https://www.ama.ma/en/documents/",
        ("ama",),
        ("https://www.ama.ma/en/documents/",),
        "公开文档",
        "Public Documents",
        "摩洛哥精算师协会（AMA）",
        "Moroccan Association of Actuaries (AMA)",
        "摩洛哥精算师协会的公开文档入口。",
        "Public documents from the Moroccan Association of Actuaries.",
    ),
    SourcePortal(
        "iaba-official-site",
        "https://www.blackactuaries.org/",
        ("iaba",),
        ("https://www.blackactuaries.org/",),
        "官方入口（结构监测）",
        "Official Site (Structure Monitoring)",
        "国际黑人精算师协会（IABA）",
        "International Association of Black Actuaries (IABA)",
        "IABA 官方网站。目前仅监测网站结构，不执行资料采集。",
        "IABA's official website. Currently monitored for site structure only; materials are not collected.",
    ),
    SourcePortal(
        "eaa-official-site",
        "https://actuarial-academy.com/",
        ("eaa",),
        ("https://actuarial-academy.com/",),
        "官方入口（结构监测）",
        "Official Site (Structure Monitoring)",
        "欧洲精算学院（EAA）",
        "European Actuarial Academy (EAA)",
        "EAA 官方网站。目前仅监测网站结构，不执行资料采集。",
        "EAA's official website. Currently monitored for site structure only; materials are not collected.",
    ),
    SourcePortal(
        "istituto-historical-site",
        "http://www.italian-actuaries.org/",
        ("istituto-italiano-degli-attuari",),
        ("http://www.italian-actuaries.org/",),
        "历史入口（暂停）",
        "Historical Site (On Hold)",
        "意大利精算师研究所",
        "Istituto Italiano degli Attuari",
        "历史官方入口，目前暂停采集。页面为不完整网站演示，不能作为可采资料目录。",
        "Historical official entry; collection is on hold. The page is an incomplete website demo, not a verified materials directory.",
    ),
    SourcePortal(
        "colombia-official-site",
        "https://actuarios.org.co/",
        ("aca-colombia",),
        ("https://actuarios.org.co/",),
        "官方资料入口",
        "Official Resources",
        "哥伦比亚精算师协会（ACA）",
        "Colombian Association of Actuaries (ACA)",
        "哥伦比亚精算师协会官网的公开资料与活动入口。",
        "Public resources and activities on the ACA's official website.",
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


def source_portal_for_observation(site_id: str, url: str, source_page_url: str = "") -> str | None:
    """Assign each observed item once; SOA AI needs an explicit topic provenance."""
    if site_id in {"iaba", "eaa", "istituto-italiano-degli-attuari"}:
        return None
    if site_id == "soa":
        ai_roots = (
            SOURCE_PORTALS_BY_KEY["soa-artificial-intelligence"].url,
            "https://www.soa.org/resources/research-reports/2025/research-ai-bulletin/",
        )
        if any(value.startswith(root) for value in (url, source_page_url) for root in ai_roots):
            return "soa-artificial-intelligence"
        return "soa-research-topics"
    return next(
        (portal.portal_key for portal in SOURCE_PORTALS if site_id in portal.site_ids), None
    )


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
