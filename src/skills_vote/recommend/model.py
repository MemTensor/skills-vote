from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RecommendConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_path: str
    skills_dir: str
    default_top_k: int = Field(default=5)


class RecommendOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_names: list[str]
    optimized_context: str = Field(min_length=1)
