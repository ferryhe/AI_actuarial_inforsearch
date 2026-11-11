from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_actuarial.agent_runtime import Registry
from ai_actuarial.skills.document_research.manifest import FindArgs, TargetArgs


class EmptyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RecentArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: str | None = Field(default=None, max_length=128)
    window_days: Literal[7] | None = None


class CatalogArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=4000)


ARGUMENT_MODELS = {
    "EmptyArgs": EmptyArgs,
    "RecentArgs": RecentArgs,
    "FindArgs": FindArgs,
    "TargetArgs": TargetArgs,
    "CatalogArgs": CatalogArgs,
}
MANIFEST = Registry.load_skill(__package__, ARGUMENT_MODELS)
