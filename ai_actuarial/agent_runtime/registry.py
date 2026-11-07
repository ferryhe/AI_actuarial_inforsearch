"""Manifest validation and the only skill/tool extension point."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field


class _ToolManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    tool_id: str
    description: str
    executor: str
    arguments_model: str
    required_scopes: list[str] = Field(default_factory=lambda: ["chat.query"])


class _SkillManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
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


@dataclass(frozen=True)
class Skill:
    skill_id: str
    version: str
    description: str
    tools: tuple[Tool, ...]
    enabled: bool = True


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
                )
                for item in data.tools
            )
        except KeyError as exc:
            raise ValueError(f"Unknown arguments model: {exc.args[0]}") from exc
        return Skill(
            data.skill_id, data.version, data.description + "\n" + instructions, tools, data.enabled
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

    def descriptions(self) -> list[dict]:
        return [
            {
                "skill_id": skill.skill_id,
                "description": skill.description,
                "tools": [
                    {
                        "tool_id": tool.tool_id,
                        "description": tool.description,
                        "arguments": tool.arguments.model_json_schema(),
                    }
                    for tool in skill.tools
                ],
            }
            for skill in self.skills.values()
            if skill.enabled
        ]
