from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from skills_vote.query import structured_output_claude_agent_stream


class SkillEvaluationRubric(BaseModel):
    os: list[Literal["linux", "macos", "windows"]]
    write_scope: Literal["read", "workspace", "system"] | None
    privilege: Literal["rootless", "sudo"] | None
    externalty: Literal["offline", "online", "secured"] | None
    envs: list[str]
    bins: list[str]
    mcps: list[str]
    environment_reason: str
    consistency: bool | None
    consistency_reason: str
    completeness: bool | None
    completeness_reason: str
    orientation: bool | None
    orientation_reason: str
    success_verifiability: bool | None
    success_verifiability_reason: str
    environment_controllability: bool | None
    environment_controllability_reason: str
    task_constructability: bool | None
    task_constructability_reason: str


async def evaluate_skill(
    *,
    skill_dir: Path,
    system_prompt: str,
    user_prompt: str,
    model: str,
    tools: list[str] | None = None,
    max_turns: int | None = None,
) -> SkillEvaluationRubric:
    rubric = None
    async for message in structured_output_claude_agent_stream(
        response_format=SkillEvaluationRubric,
        system_prompt=system_prompt,
        user_prompt=user_prompt.strip().format(skill_dir=skill_dir),
        cwd=skill_dir,
        model=model,
        tools=tools,
        max_turns=max_turns,
        read_roots=[skill_dir],
    ):
        if getattr(message, "structured_output", None) is not None:
            rubric = SkillEvaluationRubric.model_validate(message.structured_output)
    if rubric is None:
        raise RuntimeError("Agent finished without structured output.")
    return rubric
