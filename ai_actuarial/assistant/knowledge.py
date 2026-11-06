"""Read-only, bounded evidence for directory and permitted KB questions."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from itertools import zip_longest
from typing import Literal
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict

from ai_actuarial.api.deps import public_permissions_for_request
from ai_actuarial.assistant.help import _EN_STOPWORDS, _tokens


class SourceCitation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_type: Literal["catalog", "kb"]
    file_id: str
    section_id: str = ""
    kb_id: str | None = None
    title: str
    link: str
    source_version: str | None = None
    source_date: str | None = None
    stale: bool = False


@dataclass
class Evidence:
    citation: SourceCitation
    content: str


def permitted_kbs(request, auth) -> list[str]:
    state = request.app.state
    allowed = list(getattr(state, "assistant_public_kb_ids", []))
    if auth.token and "assistant.internal" in auth.permissions:
        allowed.extend(getattr(state, "assistant_staff_kb_ids", []))
    return list(dict.fromkeys(allowed))


def can_read_catalog(request, auth) -> bool:
    permissions = auth.permissions if auth.token else public_permissions_for_request(request)
    return "catalog.read" in permissions and "files.read" in permissions


def _citation(row: dict, *, source_type: str, **metadata) -> SourceCitation:
    file_url = row["file_url"]
    return SourceCitation(
        source_type=source_type,
        file_id=file_url,
        title=str(row.get("title") or row.get("filename") or file_url),
        link="/file-detail?" + urlencode({"url": file_url}),
        **metadata,
    )


def catalog_evidence(storage, message: str, *, zh: bool) -> list[Evidence]:
    # Only subject terms search the fixed public projection, never Markdown.
    stop = set(
        "a all an and are about available can could do does document documents file files find for from have how i in is list materials me of on or please related show tell the there to we what which with would you".split()
    )
    terms = [word for word in re.findall(r"[a-z0-9]+", message.lower()) if word not in stop]
    subject = re.sub(r"有哪些|什么|资料|文件|可用|列出|显示|相关|关于|请|的", " ", message)
    for run in re.findall(r"[\u3400-\u9fff]+", subject):
        terms.extend(
            run[i : i + 2]
            for i in range(len(run) - 1)
            if run[i : i + 2] not in {"哪些", "有哪", "资料", "文件", "相关", "关于"}
        )
    rows = storage.search_catalog_projection(list(dict.fromkeys(terms))[:24])
    evidence = []
    for row in rows:
        bilingual = row.get("bilingual_metadata") or {}
        if isinstance(bilingual, str):
            bilingual = json.loads(bilingual)
        local = bilingual.get("zh" if zh else "en", {}) if isinstance(bilingual, dict) else {}
        if not isinstance(local, dict):
            local = {}
        public = {
            "title": str(
                local.get("title") or row.get("title") or row.get("filename") or row["file_url"]
            ),
            "summary": str(local.get("summary") or row.get("summary") or ""),
            "organization": str(row.get("organization_zh" if zh else "organization") or ""),
            "date": str(row.get("date") or ""),
            "category": str(row.get("category") or ""),
        }
        citation = _citation(
            {**row, "title": public["title"]},
            source_type="catalog",
            source_version=str(row.get("version") or "") or None,
            source_date=str(row.get("date") or row.get("updated_at") or "") or None,
        )
        evidence.append(Evidence(citation, json.dumps(public, ensure_ascii=False)[:4000]))
    return evidence


def body_evidence(
    storage, message: str, kb_ids: list[str], *, config, deadline: float, on_embedding
) -> tuple[list[Evidence], str | None]:
    from ai_actuarial.agentic_rag.ready_data_tools import search_sections
    from ai_actuarial.api.services.ready_data_publication import read_public_ready_data_snapshot
    from ai_actuarial.chatbot.exceptions import (
        EmbeddingConfigurationMismatchException,
        NoResultsException,
    )
    from ai_actuarial.chatbot.retrieval import RAGRetriever

    evidence: list[Evidence] = []
    failure = None
    retriever = None
    try:
        for kb_id in kb_ids:
            if time.monotonic() >= deadline:
                raise TimeoutError()
            kb = storage._conn.execute(
                "SELECT manifest_profile, index_path FROM rag_knowledge_bases WHERE kb_id = ?",
                (kb_id,),
            ).fetchone()
            if not kb:
                failure = "KNOWLEDGE_UNAVAILABLE"
                continue
            members = storage._conn.execute(
                """SELECT f.url, f.title, f.published_time FROM rag_kb_files k
                   JOIN files f ON f.url = k.file_url
                   WHERE k.kb_id = ? AND f.deleted_at IS NULL""",
                (kb_id,),
            ).fetchall()
            files = {
                row[0]: {"file_url": row[0], "title": row[1], "date": row[2]} for row in members
            }
            if not files:
                continue
            snapshot = read_public_ready_data_snapshot(
                storage, kb_id=kb_id, profile=kb[0] or "general"
            )
            manifest = snapshot["manifest"]
            if manifest["usable"]:
                rows = search_sections(
                    message,
                    output_dir=manifest["output_dir"],
                    limit=min(5, max(1, config.top_k)),
                    excerpt_terms=_tokens(message) - _EN_STOPWORDS,
                    file_urls=set(files),
                )
                for row in rows:
                    file_url = row.get("file_url") or row.get("doc_id")
                    if (
                        file_url not in files
                        or not row.get("text_snippet")
                        or not row.get("section_id")
                    ):
                        continue
                    citation = _citation(
                        files[file_url],
                        source_type="kb",
                        kb_id=kb_id,
                        section_id=row["section_id"],
                        source_version=str(
                            manifest.get("publication_id")
                            or manifest.get("source_version_id")
                            or manifest.get("artifact_digest")
                            or ""
                        )
                        or None,
                        source_date=str(manifest.get("built_at") or files[file_url]["date"] or "")
                        or None,
                        stale=bool(manifest.get("serving_stale")),
                    )
                    evidence.append(Evidence(citation, row["text_snippet"]))
                continue
            if not kb[1]:
                failure = "KNOWLEDGE_UNAVAILABLE"
                continue
            try:
                if retriever is None:
                    retriever = RAGRetriever(
                        storage, config, embedding_deadline=deadline, embedding_attempt=on_embedding
                    )
                # Missing or corrupt indexes fail before a query embedding is sent.
                retriever._get_vector_store(kb_id)
                rows = retriever.retrieve(
                    message,
                    kb_ids=[kb_id],
                    top_k=min(5, max(1, config.top_k)),
                    file_urls=set(files),
                )
            except EmbeddingConfigurationMismatchException:
                failure = "INDEX_MISMATCH"
                continue
            except NoResultsException:
                continue
            except TimeoutError:
                raise
            except Exception as exc:
                if isinstance(exc.__cause__, TimeoutError):
                    raise TimeoutError() from exc
                failure = "KNOWLEDGE_UNAVAILABLE"
                continue
            for row in rows:
                metadata = row["metadata"]
                file_url = metadata.get("file_url")
                if file_url not in files or not row.get("content") or not metadata.get("chunk_id"):
                    continue
                citation = _citation(
                    files[file_url],
                    source_type="kb",
                    kb_id=kb_id,
                    section_id=str(metadata["chunk_id"]),
                    source_version=metadata.get("index_version_id"),
                    source_date=str(metadata.get("index_built_at") or files[file_url]["date"] or "")
                    or None,
                    stale=bool(metadata.get("index_stale")),
                )
                evidence.append(Evidence(citation, row["content"][:4000]))
        by_kb: dict[str | None, list[Evidence]] = {}
        query_terms = _tokens(message) - _EN_STOPWORDS
        for item in sorted(
            evidence,
            key=lambda item: (
                -len(query_terms & _tokens(item.content)),
                item.citation.kb_id or "",
            ),
        ):
            by_kb.setdefault(item.citation.kb_id, []).append(item)
        # Shared excerpt coverage avoids comparing keyword and vector score scales; ties keep KB rank.
        selected = [
            item for rank in zip_longest(*by_kb.values()) for item in rank if item is not None
        ]
        return selected[:5], failure
    finally:
        if retriever is not None and retriever.embedding_generator.openai_client is not None:
            retriever.embedding_generator.openai_client.close()
