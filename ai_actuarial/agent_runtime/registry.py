"""Manifest validation and the only skill/tool extension point."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field

# Built-in descriptions are trusted fallbacks except where the copy routes to another tool.
_STANDALONE_DESCRIPTIONS = {
    "document_research.read_document_sections": (
        "For findings, read current exact sections of one permitted report with Ready-first/Standard fallback."
    ),
    "resources_updates.find_documents": "Locate a permitted KB report by title, organization, alias or summary.",
}
_RESOURCE_RESEARCH_DEPENDENCIES = frozenset(
    {
        "document_research.find_documents",
        "document_research.read_document_sections",
        "document_research.search_knowledge",
        "document_research.readiness",
    }
)


def _guidance_dependencies(skill_id: str, *, published: bool = False) -> frozenset[str]:
    if skill_id == "resources_updates":
        return _RESOURCE_RESEARCH_DEPENDENCIES
    if published and skill_id == "document_research":
        return frozenset({"resources_updates.document_dates"})
    return frozenset()


class _ToolManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    tool_id: str
    description: str
    executor: str
    arguments_model: str
    required_scopes: list[str] = Field(default_factory=lambda: ["chat.query"])
    result_kind: Literal["generic", "catalog_discovery"] = "generic"


class _SkillManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    skill_id: str
    version: str
    description: str
    enabled: bool
    tools: list[_ToolManifest]


@dataclass(frozen=True)
class Tool:
    tool_id: str
    description: str
    executor: str
    arguments: type[BaseModel]
    required_scopes: frozenset[str] = frozenset({"chat.query"})
    result_kind: Literal["generic", "catalog_discovery"] = "generic"
    standalone_description: str = ""


@dataclass(frozen=True)
class Skill:
    skill_id: str
    version: str
    description: str
    tools: tuple[Tool, ...]
    enabled: bool = True
    expected_tool_ids: frozenset[str] = frozenset()
    guidance_dependencies: frozenset[str] = frozenset()


class Registry:
    @staticmethod
    def load_skill(package: str, argument_models: Mapping[str, type[BaseModel]]) -> Skill:
        root = files(package)
        data = _SkillManifest.model_validate_json(root.joinpath("skill.json").read_text("utf-8"))
        instructions = root.joinpath("SKILL.md").read_text("utf-8").strip()
        if not instructions:
            raise ValueError(f"Missing skill instructions: {data.skill_id}")
        try:
            tools = tuple(
                Tool(
                    item.tool_id,
                    item.description,
                    item.executor,
                    argument_models[item.arguments_model],
                    frozenset(item.required_scopes),
                    item.result_kind,
                    standalone_description=_STANDALONE_DESCRIPTIONS.get(
                        item.tool_id, item.description
                    ),
                )
                for item in data.tools
            )
        except KeyError as exc:
            raise ValueError(f"Unknown arguments model: {exc.args[0]}") from exc
        return Skill(
            data.skill_id,
            data.version,
            data.description + "\n" + instructions,
            tools,
            data.enabled,
            guidance_dependencies=_guidance_dependencies(data.skill_id),
        )

    def __init__(self, skills: tuple[Skill, ...], executors: frozenset[str]):
        self.skills: dict[str, Skill] = {}
        tool_ids: set[str] = set()
        for skill in skills:
            if skill.skill_id in self.skills:
                raise ValueError(f"Duplicate skill ID: {skill.skill_id}")
            if skill.version.split(".", 1)[0] != "1":
                raise ValueError(f"Incompatible skill version: {skill.skill_id}")
            self.skills[skill.skill_id] = skill
            for tool in skill.tools:
                if tool.tool_id in tool_ids:
                    raise ValueError(f"Duplicate tool ID: {tool.tool_id}")
                if tool.executor not in executors:
                    raise ValueError(f"Unknown executor: {tool.executor}")
                if not isinstance(tool.arguments, type) or not issubclass(
                    tool.arguments, BaseModel
                ):
                    raise ValueError(f"Invalid arguments model: {tool.tool_id}")
                tool_ids.add(tool.tool_id)

    def tool(self, skill_id: str, tool_id: str) -> Tool:
        skill = self.skills.get(skill_id)
        if skill is None or not skill.enabled:
            raise ValueError("Unknown or disabled skill")
        for tool in skill.tools:
            if tool.tool_id == tool_id:
                return tool
        raise ValueError("Unknown tool")

    def descriptions(self, scopes: frozenset[str] | None = None) -> list[dict]:
        available = {
            skill.skill_id: {
                tool.tool_id: tool
                for tool in skill.tools
                if scopes is None or tool.required_scopes <= scopes
            }
            for skill in self.skills.values()
            if skill.enabled
        }
        descriptions = []
        for skill_id, tools in available.items():
            if scopes is not None and not tools:
                continue
            skill = self.skills[skill_id]
            expected = skill.expected_tool_ids | {tool.tool_id for tool in skill.tools}
            full_guidance = scopes is None or (
                expected <= tools.keys()
                and all(
                    dependency in available.get(dependency.partition(".")[0], {})
                    for dependency in skill.guidance_dependencies
                )
            )
            descriptions.append(
                {
                    "skill_id": skill_id,
                    "description": skill.description if full_guidance else "",
                    "tools": [
                        {
                            "tool_id": tool.tool_id,
                            "description": (
                                tool.description if full_guidance else tool.standalone_description
                            ),
                            "arguments": tool.arguments.model_json_schema(),
                        }
                        for tool in tools.values()
                    ],
                }
            )
        return descriptions
