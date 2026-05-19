from __future__ import annotations

from skills_vote.recommend.model import RecommendOutput


def append_recommendation_to_instruction(
    instruction: str,
    recommendation: RecommendOutput,
) -> str:
    return (
        f"{instruction.rstrip()}\n\n"
        "Here is the usage of skills:\n"
        f"{recommendation.optimized_context.strip()}"
    )
