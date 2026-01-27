from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Iterable


@dataclass
class SearchResult:
    url: str
    source: str


def _http_get_json(url: str, headers: dict[str, str]) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    return json.loads(data.decode("utf-8", errors="ignore"))


def _filter_params(params: dict) -> dict:
    return {k: v for k, v in params.items() if v is not None and v != ""}


def brave_search(
    query: str,
    max_results: int,
    api_key: str,
    user_agent: str,
    lang: str | None = None,
    country: str | None = None,
) -> list[SearchResult]:
    params_dict = {"q": query, "count": max_results}
    if lang:
        params_dict["search_lang"] = lang
    if country:
        params_dict["country"] = country
    params = urllib.parse.urlencode(_filter_params(params_dict))
    url = f"https://api.search.brave.com/res/v1/web/search?{params}"
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json",
        "X-Subscription-Token": api_key,
    }
    data = _http_get_json(url, headers)
    results = []
    for item in data.get("web", {}).get("results", []):
        link = item.get("url")
        if link:
            results.append(SearchResult(url=link, source="Web Search (Brave)"))
    return results


def serpapi_search(
    query: str,
    max_results: int,
    api_key: str,
    user_agent: str,
    lang: str | None = None,
    country: str | None = None,
) -> list[SearchResult]:
    params_dict = {
        "q": query,
        "engine": "google_news",
        "num": max_results,
        "api_key": api_key,
        "hl": lang or "en",
        "lr": f"lang_{lang}" if lang else None,
        "gl": country or None,
        "tbs": "sbd:1",
    }
    params = urllib.parse.urlencode(_filter_params(params_dict))
    url = f"https://serpapi.com/search.json?{params}"
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    data = _http_get_json(url, headers)
    results = []
    for item in data.get("organic_results", []):
        link = item.get("link")
        if link:
            results.append(SearchResult(url=link, source="Web Search (SerpAPI)"))
    return results


def search_all(
    queries: Iterable[str],
    max_results: int,
    brave_key: str | None,
    serpapi_key: str | None,
    user_agent: str,
    languages: Iterable[str] | None = None,
    country: str | None = None,
) -> list[SearchResult]:
    all_results: list[SearchResult] = []
    lang_list = list(languages or ["en"])
    for q in queries:
        q = q.strip()
        if not q:
            continue
        for lang in lang_list:
            results: list[SearchResult] = []
            if brave_key:
                try:
                    results = brave_search(
                        q, max_results, brave_key, user_agent, lang=lang, country=country
                    )
                except Exception:
                    results = []
            if not results and serpapi_key:
                try:
                    results = serpapi_search(
                        q, max_results, serpapi_key, user_agent, lang=lang, country=country
                    )
                except Exception:
                    results = []
            all_results.extend(results)
    return all_results
