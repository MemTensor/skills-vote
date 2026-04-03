from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

ClientName = Literal[
    "codex",
    "codex-app",
    "claude-code",
    "cursor",
    "gemini-cli",
    "openclaw-cli",
    "opencode",
]
EnvironmentOS = Literal["linux", "macos", "windows"]
WriteScope = Literal["read", "workspace", "system"]
Privilege = Literal["rootless", "sudo"]
Externalty = Literal["offline", "online", "secured"]
Outcome = Literal["success", "partial", "fail"]


class RecommendRequest(BaseModel):
    query: str = Field(min_length=1)
    client_name: ClientName | None = None
    client_version: str | None = None


class RecommendInput(RecommendRequest):
    download_dir: str | None = None


class RecommendSkill(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    repo_url: str = Field(min_length=1)


class RecommendResponse(BaseModel):
    skills: list[RecommendSkill]
    reason: str = ""
    session_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_skills(self) -> RecommendResponse:
        if len({skill.name for skill in self.skills}) != len(self.skills):
            raise ValueError("server returned duplicate skill names")
        if len({skill.repo_url for skill in self.skills}) != len(self.skills):
            raise ValueError("server returned duplicate repo_url values")
        return self


class Subtask(BaseModel):
    goal: str
    summary: str
    skills_used: list[str]
    outcome: Outcome | None
    reason: str


class FeedbackRequest(BaseModel):
    session_id: str = Field(min_length=1)
    os: list[EnvironmentOS]
    write_scope: WriteScope | None = None
    privilege: Privilege | None = None
    externalty: Externalty | None = None
    envs: list[str]
    bins: list[str]
    mcps: list[str]
    environment_reason: str = Field(min_length=1)
    subtasks: list[Subtask]


class FeedbackResponse(BaseModel):
    accepted: Literal[True]
