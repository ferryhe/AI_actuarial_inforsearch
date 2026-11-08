"""Read-only document research over current permitted KB membership."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field

from ai_actuarial.api.services.ready_data_publication import read_public_ready_data_snapshot

_STOP = set(
    "a an and about for from give how in is me of on please report the this to what which with"
    " you your its latest recent findings summary".split()
)


class SelectedTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kb_id: str = Field(min_length=1, max_length=128)
    file_id: str = Field(min_length=1, max_length=1024)


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    target: SelectedTarget
    title: str
    organization: str = ""
    summary: str = ""
    publication_date: str | None = None
    system_first_seen: str | None = None
    source_url: str
    internal_link: str


class SectionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    target: SelectedTarget
    section_id: str
    heading: str = ""
    excerpt: str
    source_url: str
    retrieval: str
    source_version: str | None = None
    index_version: str | None = None
    serving_stale: bool = False
    stale_severity: str = "none"
    index_stale: bool = False


def _terms(query: str) -> list[str]:
    words = [word for word in re.findall(r"[a-z0-9]+", query.casefold()) if word not in _STOP]
    aliases = {
        "精算": "soa",
        "会员": "member",
        "成员": "member",
        "人工智能": "ai",
        "调查": "survey",
        "问卷": "survey",
        "春季": "spring",
        "主要发现": "findings",
    }
    words.extend(value for key, value in aliases.items() if key in query)
    return list(dict.fromkeys(words))[:12]


def _body_query(query: str, section: str | None) -> tuple[str, set[str]]:
    if section:
        return section, set(re.findall(r"[a-z0-9]+", section.casefold()))
    if any(term in query.casefold() for term in ("limitation", "局限", "限制")):
        return "limitations", {"limitations", "limitation"}
    if any(term in query.casefold() for term in ("sample", "样本")):
        return "sample respondents", {"sample", "respondents"}
    if any(
        term in query.casefold()
        for term in ("findings", "summary", "survey", "要点", "发现", "结论", "总结", "调查")
    ):
        return "Key Findings", {"key", "findings"}
    return query, set(_terms(query))


def _section_excerpt(content: str, heading: str) -> str | None:
    lines = content.splitlines()
    headings = []
    fence = None
    for index, line in enumerate(lines):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = (token[0], len(token))
            elif token[0] == fence[0] and len(token) >= fence[1]:
                fence = None
            continue
        if fence:
            continue
        match = re.match(r"^ {0,3}(#{1,6})[ \t]+(.+?)\s*$", line)
        if match:
            title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2)).strip()
            headings.append((index, len(match.group(1)), title))
    matches = [
        (index, level) for index, level, title in headings if title.casefold() == heading.casefold()
    ]
    if len(matches) != 1:
        return None
    start, level = matches[0]
    end = next(
        (index for index, depth, _ in headings if index > start and depth <= level), len(lines)
    )
    if not "\n".join(lines[start + 1 : end]).strip():
        return None
    return "\n".join(lines[start:end]).strip()


class DocumentResearch:
    """The caller supplies a trusted *live* KB policy, evaluated on every operation."""

    def __init__(
        self,
        storage,
        *,
        authorized_kbs: Callable[[], list[str]],
        config=None,
        deadline: float | None = None,
        on_embedding: Callable[[], None] | None = None,
    ):
        self.storage = storage
        self.authorized_kbs = authorized_kbs
        self.config = config
        self.deadline = deadline or time.monotonic() + 30
        self.on_embedding = on_embedding or (lambda: None)

    def _check(self) -> None:
        if time.monotonic() >= self.deadline:
            raise TimeoutError("document research deadline")

    def _member(self, target: SelectedTarget):
        self._check()
        if target.kb_id not in self.authorized_kbs():
            raise PermissionError("KB target is outside current scope")
        return self.storage._conn.execute(
            """SELECT f.url, f.title, f.published_time, f.first_seen
               FROM rag_kb_files k JOIN files f ON f.url = k.file_url
               WHERE k.kb_id = ? AND k.file_url = ? AND f.deleted_at IS NULL""",
            (target.kb_id, target.file_id),
        ).fetchone()

    def _document(self, target: SelectedTarget, row=None) -> Document | None:
        member = self._member(target)
        if not member:
            return None
        return Document(
            target=target,
            title=str((row or {}).get("title") or member[1] or member[0]),
            organization=str((row or {}).get("organization") or ""),
            summary=str((row or {}).get("summary") or "")[:1200],
            publication_date=str(member[2]) if member[2] else None,
            system_first_seen=str(member[3]) if member[3] else None,
            source_url=member[0],
            internal_link="/file-detail?" + urlencode({"url": member[0]}),
        )

    def find_documents(self, query: str, *, kb_id: str | None = None) -> list[Document]:
        self._check()
        allowed = self.authorized_kbs()
        if kb_id is not None and kb_id not in allowed:
            raise PermissionError("KB target is outside current scope")
        current_kbs = [kb_id] if kb_id is not None else allowed
        terms = _terms(query)
        correction = re.search(r"(?:\bi meant\b|不是.*?(?:[，,；;]\s*是|而是))(.*)", query, re.I)
        ranking_terms = _terms(correction.group(1)) if correction else terms
        rows = {}
        for term in terms or [""]:
            for row in self.storage.search_catalog_projection(
                [term] if term else [], limit=50, kb_ids=current_kbs
            ):
                rows[row["file_url"]] = row
        found = []
        for row in rows.values():
            for current_kb in current_kbs:
                target = SelectedTarget(kb_id=current_kb, file_id=row["file_url"])
                document = self._document(target, row)
                if document:
                    found.append(document)

        def rank(doc: Document) -> tuple:
            title = doc.title.casefold()
            organization = doc.organization.casefold()
            summary = doc.summary.casefold()
            score = sum(
                6 * (term in title) + 2 * (term in organization) + (term in summary)
                for term in ranking_terms
            )
            if (
                "member ai survey" in title
                and "soa" in ranking_terms
                and "ashk" not in ranking_terms
                and "bulletin" not in ranking_terms
                and not correction
                and not re.search(r"\bnot\s+soa\b", query, re.I)
            ):
                score += 20
            return (
                -score,
                -(
                    int((doc.publication_date or "")[:4])
                    if (doc.publication_date or "")[:4].isdigit()
                    else 0
                ),
                title,
            )

        return sorted(found, key=rank)[:10]

    def readiness(self, target: SelectedTarget) -> dict:
        if not self._member(target):
            return {"status": "not_found"}
        kb = self.storage._conn.execute(
            "SELECT manifest_profile, index_path FROM rag_knowledge_bases WHERE kb_id = ?",
            (target.kb_id,),
        ).fetchone()
        if not kb:
            return {"status": "body_unavailable"}
        manifest = read_public_ready_data_snapshot(
            self.storage, kb_id=target.kb_id, profile=kb[0] or "general"
        )["manifest"]
        ready_target = False
        if manifest["usable"]:
            from ai_actuarial.agentic_rag.ready_data_tools import _load_ready_data

            ready_data = _load_ready_data(manifest["output_dir"])
            catalog_urls = (
                {
                    row.get("doc_id") or row.get("file_url"): row.get("file_url")
                    for row in ready_data["catalog"]
                }
                if ready_data
                else {}
            )
            ready_target = any(
                (row.get("file_url") or catalog_urls.get(row.get("doc_id")) or row.get("doc_id"))
                == target.file_id
                and row.get("section_id")
                and row.get("text")
                for row in (
                    (ready_data["sections_structured"] or ready_data["sections"])
                    if ready_data
                    else []
                )
            )
        return {
            "status": (
                "ready_publication_usable"
                if ready_target
                else "standard_index_present" if kb[1] else "body_unavailable"
            ),
            "publication_id": manifest.get("publication_id"),
            "index_version": manifest.get("index_version_id"),
            "serving_stale": bool(manifest.get("serving_stale")),
            "stale_severity": manifest.get("stale_severity") or "none",
        }

    def read_document_sections(
        self, target: SelectedTarget, *, query: str, section: str | None = None
    ) -> tuple[list[SectionEvidence], str]:
        from ai_actuarial.agentic_rag.ready_data_tools import search_sections
        from ai_actuarial.chatbot.exceptions import (
            EmbeddingConfigurationMismatchException,
            NoResultsException,
        )
        from ai_actuarial.chatbot.retrieval import RAGRetriever

        document = self._document(target)
        if not document:
            return [], "not_found"
        kb = self.storage._conn.execute(
            "SELECT manifest_profile, index_path FROM rag_knowledge_bases WHERE kb_id = ?",
            (target.kb_id,),
        ).fetchone()
        if not kb:
            return [], "body_unavailable"
        manifest = read_public_ready_data_snapshot(
            self.storage, kb_id=target.kb_id, profile=kb[0] or "general"
        )["manifest"]
        body_query, excerpt_terms = _body_query(query, section)
        required_heading = section or ("Key Findings" if body_query == "Key Findings" else None)
        required_body_terms = (
            ("sample", "respond", "participant", "response")
            if body_query == "sample respondents"
            else ("limit", "caution", "constraint") if body_query == "limitations" else ()
        )
        evidence = []
        if manifest["usable"]:
            rows = search_sections(
                body_query,
                output_dir=manifest["output_dir"],
                limit=5,
                excerpt_terms=excerpt_terms,
                file_urls={target.file_id},
            )
            for row in rows:
                if (
                    row.get("file_url") != target.file_id
                    or not row.get("section_id")
                    or not row.get("text_snippet")
                ):
                    continue
                heading = " ".join(
                    [str(row.get("heading") or ""), *map(str, row.get("heading_path") or [])]
                )
                if required_heading and required_heading.casefold() not in heading.casefold():
                    continue
                if (
                    required_heading == "Key Findings"
                    and "acknowledg" in str(row.get("heading") or "").casefold()
                ):
                    continue
                if required_body_terms and not any(
                    term in (heading + " " + str(row["text_snippet"])).casefold()
                    for term in required_body_terms
                ):
                    continue
                evidence.append(
                    SectionEvidence(
                        target=target,
                        section_id=str(row["section_id"]),
                        heading=str(row.get("heading") or ""),
                        excerpt=str(row["text_snippet"]),
                        source_url=document.source_url,
                        retrieval="ready",
                        source_version=manifest.get("publication_id")
                        or manifest.get("source_version_id"),
                        index_version=manifest.get("index_version_id"),
                        serving_stale=bool(manifest.get("serving_stale")),
                        stale_severity=manifest.get("stale_severity") or "none",
                    )
                )
        if evidence:
            return evidence, "available"
        if not kb[1]:
            return [], "body_unavailable"
        retriever = None
        try:
            retriever = RAGRetriever(
                self.storage,
                self.config,
                embedding_deadline=self.deadline,
                embedding_attempt=self.on_embedding,
            )
            retriever._get_vector_store(target.kb_id)

            def section_filter(metadata):
                return bool(
                    required_heading
                    and _section_excerpt(str(metadata.get("content") or ""), required_heading)
                )

            rows = retriever.retrieve(
                body_query,
                kb_ids=[target.kb_id],
                top_k=5,
                file_urls={target.file_id},
                candidate_filter=section_filter if required_heading else None,
            )
        except EmbeddingConfigurationMismatchException:
            return [], "index_mismatch"
        except NoResultsException:
            return [], "body_unavailable"
        except TimeoutError:
            raise
        except Exception:
            return [], "body_unavailable"
        finally:
            if retriever is not None and retriever.embedding_generator.openai_client is not None:
                retriever.embedding_generator.openai_client.close()
        for row in rows:
            metadata = row.get("metadata") or {}
            if (
                metadata.get("file_url") != target.file_id
                or not metadata.get("chunk_id")
                or not row.get("content")
            ):
                continue
            excerpt = (
                _section_excerpt(str(row["content"]), required_heading)
                if required_heading
                else str(row["content"])
            )
            if not excerpt:
                continue
            if required_body_terms and not any(
                term in excerpt.casefold() for term in required_body_terms
            ):
                continue
            evidence.append(
                SectionEvidence(
                    target=target,
                    section_id=str(metadata["chunk_id"]),
                    excerpt=excerpt[:1600],
                    source_url=document.source_url,
                    retrieval="standard",
                    source_version=metadata.get("index_version_id"),
                    index_version=metadata.get("index_version_id"),
                    index_stale=bool(metadata.get("index_stale")),
                )
            )
        return evidence, "available" if evidence else "body_unavailable"

    def search_knowledge(
        self, target: SelectedTarget, query: str
    ) -> tuple[list[SectionEvidence], str]:
        return self.read_document_sections(target, query=query)
