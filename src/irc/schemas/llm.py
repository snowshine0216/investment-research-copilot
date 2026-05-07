from __future__ import annotations
from pydantic import BaseModel, Field, model_validator


REQUIRED_TASKS: tuple[str, ...] = (
    "memo_synthesis",
    "memo_audit",
)


class ProviderConfig(BaseModel):
    base_url: str
    api_key_env: str = Field(min_length=1)


class TaskRoute(BaseModel):
    provider: str
    model: str = Field(min_length=1)


class LLMConfig(BaseModel):
    providers: dict[str, ProviderConfig] = Field(min_length=1)
    tasks: dict[str, TaskRoute] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_routes(self) -> "LLMConfig":
        for task_name, route in self.tasks.items():
            if route.provider not in self.providers:
                raise ValueError(
                    f"task '{task_name}' references unknown provider '{route.provider}'"
                )
        missing = [t for t in REQUIRED_TASKS if t not in self.tasks]
        if missing:
            raise ValueError(f"required tasks missing: {missing}")
        return self
