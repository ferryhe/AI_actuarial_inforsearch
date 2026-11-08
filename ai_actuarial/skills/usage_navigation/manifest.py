from pydantic import BaseModel, ConfigDict, Field

from ai_actuarial.agent_runtime import Registry


class GuideArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=4000)
    language: str = Field(pattern="^(en|zh)$")


ARGUMENT_MODELS = {"GuideArgs": GuideArgs}
MANIFEST = Registry.load_skill(__package__, ARGUMENT_MODELS)
