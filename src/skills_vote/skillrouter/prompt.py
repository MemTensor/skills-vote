from __future__ import annotations

from typing import Literal

PromptFormat = Literal["flat-full", "flat-nd", "struct"]

QUERY_INSTRUCTION = (
    "Instruct: Given a coding task description, retrieve the most relevant "
    "skill document that would help an agent complete the task\nQuery:"
)

RERANK_INSTRUCTION = (
    "Given a coding task description, judge whether the skill document "
    "is relevant and useful for completing the task"
)


def format_query(raw_query: str, max_len: int = 1500) -> str:
    return f"{QUERY_INSTRUCTION}{raw_query[:max_len]}"


def format_skill(
    name: str,
    description: str,
    body: str,
    desc_max: int = 300,
    body_max: int = 2500,
) -> str:
    return f"{name} | {description[:desc_max]} | {body[:body_max]}"


def format_rerank_prompt(
    name: str,
    description: str,
    body: str,
    query_text: str,
    prompt_format: PromptFormat = "flat-full",
    desc_max: int = 500,
    body_max: int = 2000,
) -> str:
    description = description[:desc_max]
    body = body[:body_max]

    if prompt_format == "flat-nd":
        doc_text = f"{name} | {description}"
    elif prompt_format == "flat-full":
        doc_text = f"{name} | {description} | {body}"
    elif prompt_format == "struct":
        return (
            f"<Instruct>: {RERANK_INSTRUCTION}\n\n"
            f"<Query>: {query_text}\n\n"
            f"<Skill>:\n"
            f"<Name>: {name}\n"
            f"<Description>: {description}\n"
            f"<Body>: {body}"
        )
    else:
        raise ValueError(f"Unknown prompt_format: {prompt_format}")

    return (
        f"<Instruct>: {RERANK_INSTRUCTION}\n\n"
        f"<Query>: {query_text}\n\n"
        f"<Document>: {doc_text}"
    )
