"""Thin Skill adapters for the independent research facade."""

import hashlib
import json

from ai_actuarial.agent_runtime import ToolResult
from ai_actuarial.assistant.document_research import SelectedTarget


def _target(args):
    return SelectedTarget(kb_id=args["kb_id"], file_id=args["file_id"])


def _catalog_id(target):
    return (
        "document_research:catalog:"
        + hashlib.sha256(f"{target.kb_id}\0{target.file_id}".encode()).hexdigest()[:24]
    )


def find_documents(facade, args: dict) -> ToolResult:
    documents = facade.find_documents(args["query"], kb_id=args.get("kb_id"))[:3]
    return ToolResult(
        "ok" if documents else "not_found",
        {"documents": [doc.model_dump() | {"summary": doc.summary[:200]} for doc in documents]},
        tuple(_catalog_id(doc.target) for doc in documents),
    )


def readiness(facade, args: dict) -> ToolResult:
    target = _target(args)
    data = facade.readiness(target)
    document = facade._document(target)
    if document:
        data["document"] = document.model_dump()
    return ToolResult(
        "ok" if document else "not_found",
        data,
        (_catalog_id(target),) if document else (),
    )


def read_document_sections(facade, args: dict) -> ToolResult:
    target = _target(args)
    evidence, status = facade.read_document_sections(
        target, query=args["query"], section=args.get("section")
    )
    if not evidence:
        document = facade._document(target)
        if document:
            return ToolResult(
                "ok",
                {"status": status, "document": document.model_dump()},
                (_catalog_id(target),),
            )
        return ToolResult("not_found", {"status": status})
    return _sections(evidence, status)


def _sections(evidence, status: str, *, limit: int = 2, excerpt_chars: int = 1200) -> ToolResult:
    sections = []
    identifiers = []
    data = {"status": status, "sections": sections}
    for item in evidence[:limit]:
        section = item.model_dump() | {"excerpt": item.excerpt[:excerpt_chars]}
        sections.append(section)
        excess = len(json.dumps(data, ensure_ascii=False)) - 4000
        if excess > 0:
            if len(section["excerpt"]) - excess < 200:
                sections.pop()
                break
            section["excerpt"] = section["excerpt"][: len(section["excerpt"]) - excess]
        identifiers.append(
            "document_research:"
            + hashlib.sha256(
                f"{item.target.kb_id}\0{item.target.file_id}\0{item.section_id}\0{item.excerpt}".encode()
            ).hexdigest()[:24]
        )
    if not sections:
        return ToolResult("unavailable", {"status": "body_unavailable"})
    return ToolResult("ok", data, tuple(identifiers))


def search_knowledge(facade, args: dict) -> ToolResult:
    return read_document_sections(facade, args)


def search_topic(facade, args: dict) -> ToolResult:
    sections, status = facade.search_topic(
        args["query"], kb_id=args.get("kb_id"), exclude_file_url=args.get("exclude_file_url")
    )
    if not sections:
        return ToolResult(
            "not_found" if status == "not_found" else "unavailable", {"status": status}
        )
    return _sections(sections, status, limit=3, excerpt_chars=950)
