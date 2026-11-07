"""An independent two-tool skill for runtime contract tests."""

from pydantic import BaseModel, ConfigDict, Field

from ai_actuarial.agent_runtime import Registry


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    term: str = Field(min_length=1, max_length=80)


class DetailArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    item_id: str = Field(min_length=1, max_length=80)


ARGUMENT_MODELS = {"SearchArgs": SearchArgs, "DetailArgs": DetailArgs}
MANIFEST = Registry.load_skill(__package__, ARGUMENT_MODELS)
