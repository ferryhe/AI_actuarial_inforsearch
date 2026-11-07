"""Deterministic test data with no production resource access."""

from ai_actuarial.agent_runtime import ToolResult

_ITEMS = {"sample": "A local assistant runtime sample."}


def search(args: dict) -> ToolResult:
    matches = [item for item in _ITEMS if args["term"].lower() in item]
    return ToolResult("ok", {"item_ids": matches})


def detail(args: dict) -> ToolResult:
    item_id = args["item_id"]
    if item_id not in _ITEMS:
        return ToolResult("not_found", error_code="TEST_ITEM_NOT_FOUND")
    return ToolResult("ok", {"text": _ITEMS[item_id]}, (f"test_lookup:{item_id}",))
