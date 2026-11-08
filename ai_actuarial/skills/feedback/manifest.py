from pydantic import BaseModel, ConfigDict, Field

from ai_actuarial.agent_runtime import Registry


class DraftArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1, max_length=4000)


ARGUMENT_MODELS = {"DraftArgs": DraftArgs}
MANIFEST = Registry.load_skill(__package__, ARGUMENT_MODELS)
