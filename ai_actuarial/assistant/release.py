"""Assistant skill release readiness and narrow publication operations."""

from __future__ import annotations

import json
from pathlib import Path

from ai_actuarial.agent_runtime.artifacts import ArtifactError, ArtifactStore, RevisionConflict
from ai_actuarial.api.deps import PUBLIC_BROWSE_PERMISSIONS
from ai_actuarial.build_info import get_build_info

REQUIRED_SKILLS = ("usage_navigation", "resources_updates", "document_research")


def readiness(store: ArtifactStore, feature, *, feature_enabled: bool = True) -> dict:
    slots = store.slots(feature_key="assistant", site_key="default")
    try:
        registry, release_ids = store.resolve_active(feature_key="assistant", site_key="default")
    except ArtifactError:
        return {
            "feature": "assistant",
            "site": "default",
            "feature_enabled": feature_enabled,
            "state": "invalid",
            "ready": False,
            "error_code": "INVALID_SKILL_RELEASE",
            "skills": {},
            "guide": {"en": False, "zh": False},
        }

    projected = {
        item["skill_id"]: item for item in registry.descriptions(PUBLIC_BROWSE_PERMISSIONS)
    }
    skills = {}
    for skill_id in REQUIRED_SKILLS:
        skill = registry.skills.get(skill_id)
        item = projected.get(skill_id)
        visible_tools = sorted(tool["tool_id"] for tool in (item or {}).get("tools", []))
        slot = slots.get(skill_id, {})
        if skill is None:
            state = "missing"
        elif not skill.enabled:
            state = "disabled"
        else:
            expected = skill.expected_tool_ids | {tool.tool_id for tool in skill.tools}
            state = (
                "ready"
                if item and expected <= set(visible_tools) and item["description"]
                else "partial"
            )
        skills[skill_id] = {
            "state": state,
            "active_release_id": release_ids.get(skill_id),
            "previous_release_id": slot.get("previous"),
            "revision": slot.get("revision", 0),
            "visible_tools": visible_tools,
        }

    guide = {"en": False, "zh": False}
    usage = skills["usage_navigation"]
    if usage["state"] == "ready" and "usage_navigation.guide" in usage["visible_tools"]:
        for language, query in (("en", "What features are available?"), ("zh", "有哪些功能怎么用")):
            result = feature.executors["usage_navigation.guide"](
                {"query": query, "language": language}
            )
            guide[language] = result.status == "ok" and any(
                isinstance(section.get("content"), str) and section["content"].strip()
                for section in result.data.get("sections", [])
            )
        if not all(guide.values()):
            usage["state"] = "guide_unavailable"

    states = {item["state"] for item in skills.values()}
    ready = states == {"ready"} and all(guide.values())
    if not feature_enabled:
        state = "disabled"
    elif ready:
        state = "ready"
    elif states <= {"missing"}:
        state = "not_ready"
    elif states <= {"disabled"}:
        state = "disabled"
    else:
        state = "partial"
    return {
        "feature": "assistant",
        "site": "default",
        "feature_enabled": feature_enabled,
        "state": state,
        "ready": ready and feature_enabled,
        "error_code": None,
        "skills": skills,
        "guide": guide,
    }


def publish(
    store: ArtifactStore,
    *,
    feature,
    receipts: dict[str, dict],
    expected_revisions: dict[str, int],
    source_ref: str,
    code_sha: str,
    data_version: str,
    model: str,
    feature_enabled: bool = True,
) -> dict:
    if set(receipts) != set(REQUIRED_SKILLS) or set(expected_revisions) != set(REQUIRED_SKILLS):
        raise ArtifactError("Exactly three skill receipts and expected revisions are required")
    build_sha = get_build_info()["git_sha"]
    if len(build_sha) == 40 and code_sha.lower() != build_sha.lower():
        raise ArtifactError("Code SHA does not match the running build")

    slots = store.slots(feature_key="assistant", site_key="default")
    packages = Path(__file__).resolve().parents[1] / "skills"
    registry, _ = store.resolve_active(feature_key="assistant", site_key="default")
    for skill_id in REQUIRED_SKILLS:
        active = registry.skills.get(skill_id)
        source_manifest = json.loads((packages / skill_id / "skill.json").read_text("utf-8"))
        if active and not active.enabled and source_manifest.get("enabled"):
            raise ArtifactError(f"Skill is intentionally disabled: {skill_id}")
    releases = {
        skill_id: store.import_source(
            packages / skill_id,
            feature_key="assistant",
            source_ref=source_ref,
            uat=receipts[skill_id],
            code_sha=code_sha,
            data_version=data_version,
            model=model,
        )
        for skill_id in REQUIRED_SKILLS
    }
    changes = {
        skill_id: (release_id, expected_revisions[skill_id])
        for skill_id, release_id in releases.items()
        if slots.get(skill_id, {}).get("active") != release_id
    }
    unchanged_active = {
        skill_id: release_id for skill_id, release_id in releases.items() if skill_id not in changes
    }
    store.activate(
        feature_key="assistant",
        site_key="default",
        changes=changes,
        expected_active=unchanged_active,
    )
    result = readiness(store, feature, feature_enabled=feature_enabled)
    result["activated"] = sorted(changes)
    result["release_ids"] = releases
    return result


def rollback(store: ArtifactStore, *, skill_id: str, expected_revision: int) -> None:
    if skill_id not in REQUIRED_SKILLS:
        raise ArtifactError("Only required Assistant skills can be rolled back here")
    store.rollback(
        feature_key="assistant",
        site_key="default",
        skill_key=skill_id,
        expected_revision=expected_revision,
    )
