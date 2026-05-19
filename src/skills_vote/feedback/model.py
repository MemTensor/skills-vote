from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Judge = Literal["environment", "human", "unknown"]

Attribution = Literal[
    "success_viewed_skill_but_not_used",
    "success_no_skill_seen",
    "success_skill_used_with_extra_exploration",
    "fail_skill_issue",
    "fail_agent_limit",
    "fail_client_env",
    "fail_external_env",
    "fail_unknown_env",
    "uncertain_human_judge_required",
    "uncertain_environment_judge_inconclusive",
    "uncertain_no_judge",
]


class SkillRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_path: str = Field(min_length=1)
    start_line: int | None
    end_line: int | None
    capability: str = Field(min_length=1)
    used_for: str = Field(min_length=1)


class FeedbackOutputSubtask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    exploration: str | None = Field(min_length=1)
    exploration_reason: str = Field(min_length=1)
    judge: Judge
    judge_reason: str = Field(min_length=1)
    attribution: Attribution
    attribution_reason: str = Field(min_length=1)
    skill_linked: str | None = Field(min_length=1)
    skill_refs: list[SkillRef]


class Subtask(FeedbackOutputSubtask):
    ground_truth_path: str | None = Field(default=None, min_length=1)


class FeedbackOutputPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtasks: list[FeedbackOutputSubtask] = Field(min_length=1)


class FeedbackPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtasks: list[Subtask] = Field(min_length=1)
