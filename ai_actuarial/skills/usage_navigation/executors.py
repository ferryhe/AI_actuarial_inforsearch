import hashlib
from urllib.parse import urlencode

from ai_actuarial.agent_runtime import ToolResult
from ai_actuarial.assistant.help import load_help_sections, search_help


def guide(args):
    hits = search_help(args["query"], language=args["language"], limit=3)
    if not hits:
        return ToolResult(
            "not_found",
            {"message": "No matching guide section; open the user guide or clarify the feature."},
        )
    sections = {(item.doc_id, item.section_id): item for item in load_help_sections()}
    items = []
    for hit in hits:
        section = sections[(hit["doc_id"], hit["section_id"])]
        reference = {
            key: hit[key]
            for key in ("doc_id", "section_id", "language", "source_version", "content_hash")
        }
        items.append(
            {
                "title": section.section_title,
                "document_title": section.title,
                "content": section.content[:900],
                "reference": reference,
                "link": "/api/assistant/help/section?" + urlencode(reference),
                "action": "/weekly" if section.section_id == "weekly-reports" else None,
            }
        )
    return ToolResult(
        "ok",
        {"sections": items},
        tuple(
            "usage_navigation:"
            + hashlib.sha256(
                (
                    item["reference"]["doc_id"]
                    + item["reference"]["section_id"]
                    + item["reference"]["content_hash"]
                ).encode()
            ).hexdigest()[:24]
            for item in items
        ),
    )
