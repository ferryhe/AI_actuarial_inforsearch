"""Thin Skill adapters for the independent research facade."""

import hashlib

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
    evidence = evidence[:2]
    if not evidence:
        document = facade._document(target)
        if document:
            return ToolResult(
                "ok",
                {"status": status, "document": document.model_dump()},
                (_catalog_id(target),),
            )
        return ToolResult("not_found", {"status": status})
    return ToolResult(
        "ok",
        {
            "status": status,
            "sections": [item.model_dump() | {"excerpt": item.excerpt[:1200]} for item in evidence],
        },
        tuple(
            "document_research:"
            + hashlib.sha256(
                f"{item.target.kb_id}\0{item.target.file_id}\0{item.section_id}\0{item.excerpt}".encode()
            ).hexdigest()[:24]
            for item in evidence
        ),
    )


def search_knowledge(facade, args: dict) -> ToolResult:
    return read_document_sections(facade, args)
