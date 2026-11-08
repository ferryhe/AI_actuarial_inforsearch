import hashlib

from ai_actuarial.agent_runtime import ToolResult


def draft(args):
    text = args["text"]
    return ToolResult(
        "ok",
        {
            "draft": text,
            "status": "not_submitted",
            "next_step": "Review, edit and confirm in the existing feedback form.",
        },
        ("feedback:" + hashlib.sha256(text.encode()).hexdigest()[:24],),
    )
