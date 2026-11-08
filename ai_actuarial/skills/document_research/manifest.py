"""Bounded arguments for the document research Skill."""

from pydantic import BaseModel, ConfigDict, Field

from ai_actuarial.agent_runtime import Registry


class FindArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=4000)
    kb_id: str | None = Field(default=None, max_length=128)


class TargetArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kb_id: str = Field(min_length=1, max_length=128)
    file_id: str = Field(min_length=1, max_length=1024)


class ReadArgs(TargetArgs):
    query: str = Field(min_length=1, max_length=4000)
    section: str | None = Field(default=None, max_length=120)


ARGUMENT_MODELS = {"FindArgs": FindArgs, "TargetArgs": TargetArgs, "ReadArgs": ReadArgs}
MANIFEST = Registry.load_skill(__package__, ARGUMENT_MODELS)
