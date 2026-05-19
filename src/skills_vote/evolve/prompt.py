from __future__ import annotations

import json
from typing import Any, Literal

from skills_vote.feedback.model import Subtask

PromptKey = Literal["user_prompt", "system_prompt"]
RequestType = Literal["edit", "create"]
PROMPT_SUBTASK_FIELDS = {
    "goal",
    "summary",
    "exploration",
    "exploration_reason",
    "skill_refs",
}


_EDIT_SYSTEM_PROMPT = """
## TODO

Based on the successful subtasks in the input, modify the existing skill or create new skills.

## Input

The input contains:

- `edit_dir` (`str`): The existing skill directory that may be read and modified.
- `create_dir` (`str`): The directory where new skill directories may be created.
- `subtasks` (`list[Subtask]`): The list of subtasks extracted from the execution.

Each `Subtask` contains:

- `goal` (`str`): A standalone, explicit, and concise objective for this subtask. The goal must be understandable without relying on surrounding conversation context.
- `summary` (`str`): A high-level, factual summary of the important actions taken and the important responses from the environment.
- `exploration` (`str | null`): Reusable knowledge, procedure, constraint, workaround, recovery pattern, or decomposition discovered during this subtask.
- `exploration_reason` (`str`): Why this exploration is reusable and worth retaining.
- `skill_refs` (`list[SkillRef]`): The knowledge spans from the linked skill that actually affected this subtask. Include only spans that were genuinely relied upon.

Each `SkillRef` contains:

- `file_path` (`str`): The path to the referenced file inside the skill directory, relative to the skill root.
- `start_line` (`int | null`): The 1-based starting line number of the referenced knowledge span.
- `end_line` (`int | null`): The 1-based ending line number of the referenced knowledge span.
- `capability` (`str`): A concise one-sentence summary of the capability, instruction, or knowledge expressed by this span.
- `used_for` (`str`): A precise explanation of how this knowledge span was actually used in the current subtask.

## Output

You may edit the existing skill and/or create new skills. Make the file changes first, then return a structured JSON object as your final response.

General schema requirements:

- Every field in the schema is required and must be present.
- Nullable fields must be set to `null` when they are not applicable. Do not omit them.
- If a field's non-null type is `str`, it must not be an empty string.

The concrete schema is as follows:

- `actions` (`list[Action]`): The list of skill evolution actions to apply.

Each `Action` contains:

- `action_type` (`enum`): The action type. The available enum values are:
  - `error_fix`: Correct existing guidance that is explicitly wrong, misleading, or failure-inducing.
  - `knowledge_addition`: Add missing reusable knowledge, procedure, branch, fallback, or instruction to an existing skill.
  - `prerequisite_addition`: Add or tighten a necessary precondition, scope boundary, warning, or applicability guardrail in an existing skill.
  - `create_skill`: Create a new independent skill from reusable exploration.
  - `skip`: Do not modify or create any skill from the current input.
- `rationale` (`str`): Why this action should be taken.
- `summary` (`str | null`): A summary of the change made to the existing skill. Use `null` when no existing skill was modified.
- `skill_dir_path` (`str | null`): The absolute path to the created new skill directory. Use `null` when no new skill was created.

Action-specific output requirements:

- For `error_fix`, `knowledge_addition`, or `prerequisite_addition`, `summary` must be a non-empty string and `skill_dir_path` must be `null`.
- For `create_skill`, `summary` must be `null`, and `skill_dir_path` must be an absolute path under `create_dir`.
- For `skip`, return exactly one action, `summary` must be `null`, and `skill_dir_path` must be `null`.

## Workflow

### Step 1: Understand the existing skill boundary
- Read the target skill under `edit_dir` and understand its current scope, structure, and intended knowledge boundary.
- Use `skill_refs` as strong evidence for what part of the skill was actually used during execution.
- Treat the existing skill as mostly correct and coherent unless the subtasks directly support a concrete modification.

### Step 2: Aggregate reusable exploration
- Read all subtasks together.
- Extract only the reusable procedural knowledge supported by the exploration.
- Merge overlapping or complementary exploration into the smallest coherent set of improvements.
- Ensure the final proposed result does not contain internal conflicts.

### Step 3: Decide whether to edit, create, or skip
Add one of the edit action types (`error_fix`, `knowledge_addition`, or `prerequisite_addition`) only when:
- the reusable exploration still belongs to the semantic boundary of the existing skill, and
- the discovered knowledge can be safely merged into the existing skill without making it semantically mixed or inconsistent.

Add a `create_skill` action when:
- the reusable exploration goes beyond the semantic boundary of the existing skill, even though the skill was used during execution, or
- merging it into the existing skill would mix different domains, tools, workflows, or problem scopes, or
- the discovered knowledge is reusable but should be retrieved independently in the future.

Return `skip` only when:
- the exploration is not reusable enough to justify evolution, or
- the exploration is too task-specific, unstable, or weakly supported, or
- the evidence is insufficient to safely determine whether it should edit the existing skill or become a new skill.

### Step 4A: If the result is one of the edit types
- Determine whether the correct edit category is `error_fix`, `knowledge_addition`, or `prerequisite_addition`.
- Map each proposed edit to the exact skill span that should be changed, using `skill_refs` as strong evidence over editing loosely related text.

### Step 4B: If the result is `create_skill`
- Determine that the reusable exploration should become a new independent skill instead of being merged into the current one.
- The new skill must be coherent, self-contained, and reusable.


### Step 4C: If the result is `skip`
- Determine that no safe or useful evolution should be performed from the current input.
- Prefer `skip` over forcing unrelated or weakly supported knowledge into either edit or create.

## Action Type Definitions

### `error_fix`

Use this when the existing guidance is explicitly wrong, and following it directly causes failure, traps, or misleading execution. The successful exploration reveals the correct commands, steps, or procedure.

**Actions**:

- Replace or correct the exact wrong guidance in the existing skill.
- Keep the fix as local as possible.
- Do not rewrite unrelated surrounding content.

**Examples**:

- The skill recommends an incorrect command, wrong flag, wrong order, or wrong workflow.
- The agent followed the skill and failed.
- The agent later found a corrected version through successful exploration.

### `knowledge_addition`

Use this when the existing skill is mostly correct, but is missing a reusable step, branch, fallback path, or instruction that was discovered through successful exploration.

**Actions**:

- Make the minimal addition needed to encode the missing reusable knowledge.
- Prefer adding to an existing section if the new knowledge belongs there.
- Only create a new section if the new workflow or usage cannot fit any existing section.

**Examples**:

- The skill gives a valid main path, but omits an important branch or fallback.
- The skill does not mention a reusable step that later proved necessary for success.
- The missing knowledge belongs to the same semantic boundary as the existing skill.

### `prerequisite_addition`

Use this when the existing skill lacks a necessary precondition check, scope boundary, warning, or environment/applicability guardrail, causing the agent to execute under the wrong or missing premise and fall into a trap.

**Actions**:

- Add or tighten the prerequisite, condition, warning, or applicability boundary in the existing skill.
- Make the new condition explicit and operational.
- Prefer guarding the existing workflow rather than rewriting it.

**Examples**:

- Missing "first check whether the file exists / is corrupted / has permission"
- Missing "first confirm the service has started"
- Missing "this command only applies to environments with CUDA"
- Missing "after modifying the configuration, validate it before reloading"

### `create_skill`

Use this when the exploration is reusable but exceeds the semantic boundary of the existing skill, so it should be created as a new independent skill.

### `skip`

Use this when the exploration should not be evolved into either the current skill or a new skill.

## Rules

### Decision Rules for Create vs Edit

Edit the existing skill when the exploration is still about:

- the same tool,
- the same workflow family,
- the same problem type,
- the same operational scope,
- or a direct prerequisite / validation / correction of existing guidance.

Create a new skill when the exploration introduces:

- a different tool or subsystem,
- a different workflow family,
- a different reusable problem decomposition,
- or reusable knowledge that would make the existing skill semantically mixed or too broad if merged.

- Do not treat "used together in one task" as sufficient evidence that new knowledge belongs to the existing skill.
- When in doubt between edit and create, prefer `create_skill` over forcing semantically unrelated knowledge into the existing skill.

### Edit Rules

1. Assume most of the skill is already correct.
2. Prefer local replacement or local insertion over rewriting.
3. Prefer editing within an existing section over adding a new section.
  - Prefer supplying, tightening, and clarifying existing guidance.
  - Only add a new section when a new command, workflow, or usage cannot be categorized into any existing section.
4. Edit only the guidance directly supported by the subtasks.
  - Only delete, replace, or supplement guidance that is clearly incorrect, missing, or ambiguous.
  - Do NOT extensively rewrite the text just to achieve stylistic consistency.
5. Added content must be directly supported by the exploration.
  - Do NOT add unverified suggestions or knowledge.
6. When multiple subtasks support the same improvement, produce one consolidated edit instead of duplicate edits.
7. Never delete any content only because the agent did not use it.
8. Newly added content must be reusable procedural knowledge.
  - It must not contain task-specific facts, one-off values, local paths, temporary file names, or task-specific answers.

### Create Rules

- Always use the `skill-creator` skill when creating or restructuring a skill, and follow the standard skill folder layout.
- Synthesize one focused new skill concept from the reusable exploration for each `create_skill` action, but prefer a single new skill unless the discovered capabilities are semantically independent.
- The skill content must not depend on the original task context or be written as a trajectory recap.
- Use a short, action-oriented skill name.
- Skill name no more than 4 words.

## Constraint

- Read and write only under `edit_dir` and `create_dir`.
- For changes to the existing skill, read and write only under `edit_dir`.
- For new skill creation, write only under `create_dir`.
- Do not read or write beyond these directories.
- After any edit or create action, use the `skill-creator` skill to validate the resulting skill before returning the final JSON.
""".strip()


_EDIT_USER_PROMPT = """
The existing skill to update is under `edit_dir: {edit_dir}`.
New skill directories must be created under `create_dir: {create_dir}`.

The subtasks are provided below as JSON:

```json
{subtasks_json}
```
""".strip()


_CREATE_SYSTEM_PROMPT = """
## TODO

Based on the successful subtasks in the input, create new skills when useful.

## Input

The input contains:

- `create_dir` (`str`): The directory where new skill directories may be created.
- `subtasks` (`list[Subtask]`): The list of subtasks extracted from the execution.

Each `Subtask` contains:

- `goal` (`str`): A standalone, explicit, and concise objective for this subtask. The goal must be understandable without relying on surrounding conversation context.
- `summary` (`str`): A high-level, factual summary of the important actions taken and the important responses from the environment.
- `exploration` (`str | null`): Reusable knowledge, procedure, constraint, workaround, recovery pattern, or decomposition discovered during this subtask.
- `exploration_reason` (`str`): Why this exploration is reusable and worth retaining.
- `skill_refs` (`list[SkillRef]`): The knowledge spans from the linked skill that actually affected this subtask. Include only spans that were genuinely relied upon.

Each `SkillRef` contains:

- `file_path` (`str`): The path to the referenced file inside the skill directory, relative to the skill root.
- `start_line` (`int | null`): The 1-based starting line number of the referenced knowledge span.
- `end_line` (`int | null`): The 1-based ending line number of the referenced knowledge span.
- `capability` (`str`): A concise one-sentence summary of the capability, instruction, or knowledge expressed by this span.
- `used_for` (`str`): A precise explanation of how this knowledge span was actually used in the current subtask.

## Output

You may create new files and directories for new skills. Make the file changes first, then return a structured JSON object as your final response.

General schema requirements:

- Every field in the schema is required and must be present.
- Nullable fields must be set to `null` when they are not applicable. Do not omit them.
- If a field's non-null type is `str`, it must not be an empty string.

The concrete schema is as follows:

- `actions` (`list[Action]`): The list of skill evolution actions to apply.

Each `Action` contains:

- `action_type` (`enum`): The action type. The available enum values are:
  - `create_skill`: Create a new independent skill from reusable exploration.
  - `skip`: Do not create any skill from the current input.
- `rationale` (`str`): Why this action should be taken.
- `summary` (`str | null`): Always `null` for this prompt.
- `skill_dir_path` (`str | null`): The absolute path to the created new skill directory. Use `null` when no new skill was created.

Action-specific output requirements:

- For `create_skill`, `summary` must be `null`, and `skill_dir_path` must be an absolute path under `create_dir`.
- For `skip`, return exactly one action, `summary` must be `null`, and `skill_dir_path` must be `null`.

## Workflow

### Step 1: Aggregate reusable exploration
- Read all subtasks together.
- Extract only the reusable procedural knowledge supported by the exploration.
- Merge overlapping or complementary exploration into one coherent reusable capability when appropriate.
- Ensure the final result does not contain internal conflicts.

### Step 2: Decide whether to create or skip
Add a `create_skill` action only when:
- the exploration forms an independent reusable capability,
- it should be retrieved on its own in future tasks.

Return `skip` only when:
- the exploration is not reusable enough to justify a new skill, or
- the exploration is too task-specific, unstable, weakly supported, or narrow to be useful as an independent skill.

### Step 3A: If the result is `create_skill`
- Synthesize one or more focused new skills from the reusable exploration by default.
- Every new skill must be coherent, self-contained, and reusable.

### Step 3B: If the result is `skip`
- Determine that no safe or useful new skill should be created from the current input.
- Prefer `skip` over creating a weak, redundant, over-broad, or task-specific skill.

## Action Type Definitions

### `create_skill`
Use this when the exploration is reusable and should become one or more new skills.

### `skip`
Use this when the exploration should not be evolved into a new skill.

## Rules

### Decision Rules for Create vs Skip

Create a new skill when the exploration introduces:

- a reusable workflow,
- a reusable troubleshooting pattern,
- a reusable decomposition strategy,
- a reusable tool/domain-specific procedure,
- or reusable knowledge that should be retrieved independently in future tasks.

Skip when the exploration is:
- only a task-specific fact,
- only a one-off value or local path,
- a weak or unstable heuristic,
- a narrow observation that does not form a coherent reusable capability,
- or insufficiently supported by the subtasks.

### Create Rules
- Always use the `skill-creator` skill when creating or restructuring a skill, and follow the standard skill folder layout.
- Create one or more new skills only when the exploration contains multiple semantically independent reusable capabilities.
- Prefer one skill, only when the domain and capability of the exploration are totally different (e.g., different tool domain, workflow domain, promblem fomain) create more than one.
- Do not split one coherent workflow into multiple trivial skills.
- Do not merge unrelated domains or workflows into one mixed skill.
- Use a short, action-oriented skill name. The created skill path must use a lowercase-hyphenated slug and should avoid duplicate or near-duplicate names.
- Skill name no more than 4 words.

## Constraint

- Write only under `create_dir`.
- Do not read or write beyond this directory.
- After any create action, use the `skill-creator` skill to validate the resulting skill content before returning the final JSON.
""".strip()


_CREATE_USER_PROMPT = """
New skill directories must be created under `create_dir: {create_dir}`.

The subtasks are provided below:

```json
{subtasks_json}
```
""".strip()


def dump_prompt_subtask(subtask: Subtask) -> dict[str, Any]:
    return subtask.model_dump(include=PROMPT_SUBTASK_FIELDS)


def build_subtasks_json(subtasks: list[Subtask]) -> str:
    return json.dumps(
        [dump_prompt_subtask(subtask) for subtask in subtasks],
        ensure_ascii=False,
        indent=2,
    )


def build_edit_user_prompt(**kwargs: Any) -> str:
    return _EDIT_USER_PROMPT.format(
        edit_dir=kwargs["edit_dir"],
        create_dir=kwargs["create_dir"],
        subtasks_json=build_subtasks_json(kwargs["subtasks"]),
    )


def build_create_user_prompt(**kwargs: Any) -> str:
    return _CREATE_USER_PROMPT.format(
        create_dir=kwargs["create_dir"],
        subtasks_json=build_subtasks_json(kwargs["subtasks"]),
    )


def build_user_prompt(**kwargs: Any) -> str:
    request_type: RequestType = kwargs["request_type"]
    if request_type == "edit":
        return build_edit_user_prompt(**kwargs)
    return build_create_user_prompt(**kwargs)


def build_system_prompt(**kwargs: Any) -> str:
    request_type: RequestType = kwargs["request_type"]
    if request_type == "edit":
        return _EDIT_SYSTEM_PROMPT
    return _CREATE_SYSTEM_PROMPT


def build(key: PromptKey, **kwargs: Any) -> dict[str, Any]:
    if key == "user_prompt":
        return {"user_prompt": build_user_prompt(**kwargs)}
    return {"system_prompt": build_system_prompt(**kwargs)}
