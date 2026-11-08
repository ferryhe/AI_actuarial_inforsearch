"""Agent-only limits loaded from the authoritative sites configuration."""

from collections.abc import Mapping

from ai_actuarial.agent_runtime.contracts import AgentBudget
from config.yaml_config import load_ai_config


def load_agent_budget() -> AgentBudget:
    section = load_ai_config().get("assistant_agent") or {}
    if not isinstance(section, Mapping):
        raise ValueError("ai_config.assistant_agent must be a mapping")
    return AgentBudget.from_config(section)
