from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skills_vote.feedback.model import FeedbackPayload, Subtask

ActionType = Literal[
    "error_fix",
    "knowledge_addition",
    "prerequisite_addition",
    "create_skill",
    "skip",
]

EDIT_ACTION_TYPES = {
    "error_fix",
    "knowledge_addition",
    "prerequisite_addition",
}
EVOLVABLE_ATTRIBUTIONS = {
    "success_viewed_skill_but_not_used",
    "success_no_skill_seen",
    "success_skill_used_with_extra_exploration",
}
EVOLVE_EDIT_ATTRIBUTIONS = {"success_skill_used_with_extra_exploration"}


class EvolveRequest(BaseModel):
    request_dir_name: str
    target_skill_name: str | None = None
    subtasks: list[Subtask]


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: ActionType
    rationale: str = Field(min_length=1)
    summary: str | None = Field(min_length=1)
    skill_dir_path: str | None = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_consistency(self) -> Action:
        if not self.rationale:
            raise ValueError(f"{self.action_type} requires non-empty rationale")
        if self.action_type in EDIT_ACTION_TYPES and not self.summary:
            raise ValueError(f"{self.action_type} requires non-empty summary")
        if self.action_type == "create_skill" and not self.skill_dir_path:
            raise ValueError("create_skill requires non-empty skill_dir_path")
        return self


class EvolveOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actions: list[Action] = Field(min_length=1)


def feedback_to_evolve_requests(
    feedback_payload: FeedbackPayload,
) -> list[EvolveRequest]:
    edit_subtasks: dict[str, list[Subtask]] = {}
    create_subtasks: list[Subtask] = []
    for subtask in feedback_payload.subtasks:
        if subtask.exploration is None:
            continue
        if subtask.attribution not in EVOLVABLE_ATTRIBUTIONS:
            continue
        if (
            subtask.skill_linked is not None
            and subtask.attribution in EVOLVE_EDIT_ATTRIBUTIONS
        ):
            edit_subtasks.setdefault(subtask.skill_linked, []).append(subtask)
            continue
        create_subtasks.append(subtask)

    requests: list[EvolveRequest] = []
    if create_subtasks:
        requests.append(
            EvolveRequest(
                request_dir_name="create_request",
                subtasks=create_subtasks,
            )
        )

    for skill_name, subtasks in edit_subtasks.items():
        requests.append(
            EvolveRequest(
                request_dir_name=f"edit_request_{skill_name}",
                target_skill_name=skill_name,
                subtasks=subtasks,
            )
        )
    return requests


def aggregate_feedback_payloads(
    feedback_payloads: list[FeedbackPayload],
) -> FeedbackPayload:
    return FeedbackPayload(
        subtasks=[
            subtask
            for feedback_payload in feedback_payloads
            for subtask in feedback_payload.subtasks
        ]
    )
