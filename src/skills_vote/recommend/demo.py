from pathlib import Path

from pydantic import BaseModel

from skills_vote.query import structured_output_claude_agent_stream


class RecommendResponse(BaseModel):
    skill_names: list[str]
    optimization_context: str


async def recommend(
    *,
    task: str,
    skills_dir: Path,
    system_prompt: str,
    user_prompt: str,
    max_skills: int,
    model: str,
    tools: list[str] | None = None,
    max_turns: int | None = None,
) -> RecommendResponse:
    response = None
    async for message in structured_output_claude_agent_stream(
        response_format=RecommendResponse,
        system_prompt=system_prompt.strip().format(max_skills=max_skills),
        user_prompt=user_prompt.strip().format(task=task),
        cwd=skills_dir,
        model=model,
        tools=tools,
        max_turns=max_turns,
        read_roots=[skills_dir],
    ):
        if getattr(message, "structured_output", None) is not None:
            response = RecommendResponse.model_validate(message.structured_output)
    if response is None:
        raise RuntimeError("Agent finished without structured output.")
    return response
