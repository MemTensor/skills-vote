from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

PromptKey = Literal["user_prompt", "system_prompt"]

_PROMPT = """
## TODO

Based on the current task context, execution trace, environment feedback, and any skill interactions that actually happened, summarize the execution into a list of structured subtasks.

## Input

The current working directory is now located at `{cwd}`, and the only skills currently accessible in this execution context are:
`{available_skills}`

{ground_truth_context}

The task-level ground-truth verifier reported: out of a total of {num_total_test_cases} private test cases, {num_passed_test_cases} passed and {num_failed_test_cases} failed.

This signal should be interpreted as the authoritative final evaluation of the whole task, rather than as evidence about any single subtask in isolation.
If the verifier only exposes an aggregated scalar reward instead of explicit counts, treat that reward as one aggregated private test case: reward `1` means passed, otherwise failed.

Note:

- Earlier paths from previous context may describe the same logical files or skills, but those old paths are no longer accessible now.
- If the same skill name appears again in the current context, assume its content is identical to what was provided earlier. Only the path has changed.
- Any skill reference in the output must use the currently accessible path context, not stale historical paths.

## Output

Return a structured JSON object as your final response.

General schema requirements:

- Every field in the schema is required and must be present.
- Nullable fields must be set to `null` when they are not applicable. Do not omit them.
- If a field's non-null type is `str`, it must not be an empty string.

The concrete schema is as follows:

- `subtasks` (`list[Subtask]`): The list of subtasks extracted from the execution.

Each `Subtask` contains:

- `goal` (`str`): A standalone, explicit, and concise objective for this subtask. The goal must be understandable without relying on surrounding conversation context.
- `summary` (`str`): A high-level, factual summary of the important actions taken and the important responses from the environment. Abstract repetitive low-level operations, but explicitly include meaningful actions, key failures, key recoveries, decisive observations, and important environment feedback.
- `exploration` (`str | null`): Reusable knowledge, procedure, constraint, workaround, recovery pattern, or decomposition discovered during this subtask. Use `null` when the subtask does not produce such an exploration outcome.
- `exploration_reason` (`str`): An explanation of the exploration assessment.
  - If `exploration` is a string, explain why it is reusable and worth retaining beyond this single execution.
  - If `exploration` is `null`, explain why this subtask does not contain the kind of reusable knowledge, procedure, constraint, workaround, recovery pattern, or decomposition that is worth retaining.
- `judge` (`enum`): The primary judgement source for this subtask. The available enum values are:
  - `environment`: The subtask is primarily judged by observable environment feedback, such as terminal output, test results, API responses, file existence, build results, deployment results, or runtime behavior.
  - `human`: The subtask result fundamentally depends on human preference-based review or evaluation.
  - `unknown`: There is no explicit judge signal.
- `judge_reason` (`str`): Evidence-based justification for the chosen judge type. Explain why this subtask is primarily judged by environment feedback, by human review, or by no explicit judge at all.
- `attribution` (`enum`): The final result-and-cause label for this subtask. The available enum values are:
  - `success_viewed_skill_but_not_used`: The agent viewed a skill, but that skill did not materially shape the successful path. The subtask was ultimately completed through the agent's own exploration.
  - `success_no_skill_seen`: The agent never viewed any skill and still completed the subtask through independent exploration.
  - `success_skill_used_with_extra_exploration`: The agent genuinely relied on a skill and completed the subtask, but additional exploration was still required. That exploration must depend on the skill context; without the skill's framing, the extra exploration would not naturally arise.
  - `fail_skill_issue`: The main reason for failure lies in the skill itself, such as outdated knowledge, incorrect steps, missing knowledge, ambiguous instructions, or insufficient environment notes.
  - `fail_agent_limit`: The main reason for failure lies in the agent itself, such as context-window failure, hallucination, or failure to correctly understand or follow the linked skill.
  - `fail_client_env`: The main reason for failure lies in the client-side environment, such as OS mismatch, permission limitations, missing executable packages, unavailable network access, sandbox restrictions, or insufficient hardware.
  - `fail_external_env`: The main reason for failure lies in external systems or services, such as unstable APIs, upstream outages, or remote dependency failures.
  - `fail_unknown_env`: The subtask clearly failed due to some environmental cause, but the evidence is insufficient to distinguish client environment from external environment.
  - `uncertain_human_judge_required`: The result fundamentally depends on human preference-based review or evaluation, but such judgement is unavailable.
  - `uncertain_environment_judge_inconclusive`: Some environment-based signal exists, but it is not sufficient to conclusively establish success or failure for the full goal.
  - `uncertain_no_judge`: No explicit judge signal exists, and the task is not simple enough to be treated as self-evident.
- `attribution_reason` (`str`): Evidence-based justification for the chosen attribution. State the decisive facts, observations, or trajectory patterns that explain why this subtask is labeled with this specific result-and-cause category.
- `skill_linked` (`str | null`): The canonical name of the single skill linked to this subtask. A skill is linked if it was viewed during this subtask, or if it materially shaped the action path, reasoning path, or exploration path. Use `null` only when no skill should be linked to this subtask.
- `skill_refs` (`list[SkillRef]`): The knowledge spans from the linked skill that actually affected this subtask. Include only spans that were genuinely relied upon. Use an empty list when no concrete knowledge span from the linked skill was actually used.

Each `SkillRef` contains:

- `file_path` (`str`): The path to the referenced file inside the skill directory, relative to the skill root. Do not use an absolute path.
- `start_line` (`int | null`): The 1-based starting line number of the referenced knowledge span. Use `null` when a reliable line-level reference is unavailable.
- `end_line` (`int | null`): The 1-based ending line number of the referenced knowledge span. Use `null` when a reliable line-level reference is unavailable.
- `capability` (`str`): A concise one-sentence summary of the capability, instruction, or knowledge expressed by this span.
- `used_for` (`str`): A precise explanation of how this knowledge span was actually used in the current subtask.

## Rules

### Subtask definition and granularity

A subtask must be a minimal but semantically complete unit of work.

Each subtask must satisfy all of the following:

- it has one standalone goal;
- it has one primary judge source;
- it has at most one linked skill context.

Split work into separate subtasks when any of the following changes:

- the goal changes;
- the primary judge source changes;
- the linked skill context changes.

Do not split merely because many low-level commands were executed.

Good splitting examples:

- "Implement a frontend page that can be built and run locally" and "make the frontend page visually better" should usually be separate subtasks.
  - The first goal is to implement a runnable page and may be judged by environment feedback such as build success, launch success, or deployment success.
  - The second goal is visual quality and usually depends on human judgement, so it may be uncertain.
- "Implement training code that can run successfully" and "train a meaningfully stronger model" should usually be separate subtasks.
  - The first goal is to make the training pipeline work and may be judged by environment feedback.
  - The second goal is model quality and may remain uncertain unless there is a trusted benchmark or verifier.

### Attribution

`attribution` directly encodes:

- the final result state;
- the primary reason category.

Always determine attribution from the final state of the subtask.

If a subtask failed at first but was eventually completed, it must still be labeled as a success attribution.

Use a failure attribution only when the goal was still not achieved by the end of the subtask.

Use an uncertain attribution only when the result cannot be conclusively established as either success or failure.

`attribution` and `judge` are related but not identical:

- `attribution` answers what the final result was and what the main cause category is;
- `judge` answers what kind of signal mainly supports that conclusion.

Uncertain attributions are especially appropriate in the following cases:

- the goal requires human review or evaluation, but such review is unavailable;
- some environment feedback exists, but it does not fully cover the goal;
- no explicit judge signal exists, and the task is not simple enough to be self-evident.

### Judge

Use:

- `environment` when the primary judgement comes from observable environment feedback ( including the verifier from the benchmark);
- `human` when the result fundamentally depends on human preference-based review or evaluation;
- `unknown` when there is no explicit judge signal.

Important distinctions:

- Executed tests may still count as `environment`, because they produce objective feedback when run.
- However, if it is unclear whether those tests fully cover the goal, the correct attribution may still be `uncertain_environment_judge_inconclusive`.
- For trivial self-evident tasks, `judge` may be `unknown` even when the attribution is successful.
- A verifier is a task-level ground-truth judgement signal for overall success or failure. It evaluates whether the full task goal has been achieved, rather than whether any individual subtask has succeeded. Please assume that a trusted verifier covers the complete test space, including all relevant cases, not just a subset. Therefore, it is possible for the overall task to be successful even if some subtasks failed along the way, because those failed subtasks may have been intermediate attempts that were later corrected. However, it should not be possible for all subtasks to be successful while the final task still fails, because the task-level verifier is the authoritative ground truth for the final outcome.

Example:

- If the user asks `1 + 1 =?` and the agent answers `2` without using a calculator, `judge` can be `unknown`.

### `skill_linked` and `skill_refs`

Each subtask may link to at most one skill.

A skill is linked to a subtask if it was viewed during that subtask, or if it materially shaped the execution path for that subtask.

All viewed skills must be covered by the subtask list. If the agent viewed three different skills during the overall task, those three viewed skills must be reflected across the produced subtasks.

Therefore:

- a viewed skill may and often should be linked to the subtask;
- when the attribution is `success_viewed_skill_but_not_used`, `skill_linked` should normally be present;
- set `skill_linked` to `null` only when no skill is meaningfully associated with the subtask.

`skill_refs` should include only the knowledge spans that were actually used.

Do not include unrelated spans from the same skill.

If a skill was only viewed but no specific knowledge span was actually used, set `skill_refs` to an empty list.

### Exploration vs Summary

`summary` is a high-level factual execution summary. It describes what happened in the subtask.

`exploration` is different. It captures a reusable delta discovered through the subtask. It may go beyond factual retelling and may include reusable knowledge, procedure, constraint, workaround, recovery pattern, decomposition, or why a certain exploration direction was meaningful.

Set `exploration` to a non-empty string only when the subtask produced such reusable content. Otherwise set it to `null`.

Do not record as `exploration`:

- ordinary trial-and-error;
- repetitive command attempts;
- low-level operational noise;
- one-off accidental discoveries that do not generalize.
""".strip()


def format_available_skills(skills_dir: Path) -> str:
    return json.dumps(
        {
            skill_dir.name: str(skill_dir.resolve())
            for skill_dir in sorted(skills_dir.iterdir())
            if skill_dir.is_dir() and not skill_dir.name.startswith(".")
        },
        ensure_ascii=False,
    )


_CLAUDE_PROMPT = """
## TODO

Based on the current task context, execution trace, environment feedback, and any skill interactions that actually happened, summarize the execution into a list of structured subtasks.

## Input

The current working directory is now located at `{cwd}`, and the only skills currently accessible in this execution context are:
`{available_skills}`

{ground_truth_context}

The task-level ground-truth verifier reported: out of a total of {num_total_test_cases} private test cases, {num_passed_test_cases} passed and {num_failed_test_cases} failed.

This signal should be interpreted as the authoritative final evaluation of the whole task, rather than as evidence about any single subtask in isolation.
If the verifier only exposes an aggregated scalar reward instead of explicit counts, treat that reward as one aggregated private test case: reward `1` means passed, otherwise failed.

Note:

- Earlier paths from previous context may describe the same logical files or skills, but those old paths are no longer accessible now.
- If the same skill name appears again in the current context, assume its content is identical to what was provided earlier. Only the path has changed.
- Any skill reference in the output must use the currently accessible path context, not stale historical paths.
- Claude Code skill tool outputs may include a historical line like `Base directory for this skill: ...`. Treat that path as trajectory evidence only.
- When producing `skill_refs`, resolve the linked skill from the current `available_skills` mapping above, actively use Read on the relevant skill files from that current path, and use that content to determine `file_path`, `start_line`, and `end_line`.
- If the current skill directory cannot be read, do not invent file or line references from memory. Use an empty `skill_refs` list or `null` line numbers according to the schema.

## Output

Return a structured JSON object as your final response.

General schema requirements:

- Every field in the schema is required and must be present.
- Nullable fields must be set to `null` when they are not applicable. Do not omit them.
- If a field's non-null type is `str`, it must not be an empty string.

The concrete schema is as follows:

- `subtasks` (`list[Subtask]`): The list of subtasks extracted from the execution.

Each `Subtask` contains:

- `goal` (`str`): A standalone, explicit, and concise objective for this subtask. The goal must be understandable without relying on surrounding conversation context.
- `summary` (`str`): A high-level, factual summary of the important actions taken and the important responses from the environment. Abstract repetitive low-level operations, but explicitly include meaningful actions, key failures, key recoveries, decisive observations, and important environment feedback.
- `exploration` (`str | null`): Reusable knowledge, procedure, constraint, workaround, recovery pattern, or decomposition discovered during this subtask. Use `null` when the subtask does not produce such an exploration outcome.
- `exploration_reason` (`str`): An explanation of the exploration assessment.
  - If `exploration` is a string, explain why it is reusable and worth retaining beyond this single execution.
  - If `exploration` is `null`, explain why this subtask does not contain the kind of reusable knowledge, procedure, constraint, workaround, recovery pattern, or decomposition that is worth retaining.
- `judge` (`enum`): The primary judgement source for this subtask. The available enum values are:
  - `environment`: The subtask is primarily judged by observable environment feedback, such as terminal output, test results, API responses, file existence, build results, deployment results, or runtime behavior.
  - `human`: The subtask result fundamentally depends on human preference-based review or evaluation.
  - `unknown`: There is no explicit judge signal.
- `judge_reason` (`str`): Evidence-based justification for the chosen judge type. Explain why this subtask is primarily judged by environment feedback, by human review, or by no explicit judge at all.
- `attribution` (`enum`): The final result-and-cause label for this subtask. The available enum values are:
  - `success_viewed_skill_but_not_used`: The agent viewed a skill, but that skill did not materially shape the successful path. The subtask was ultimately completed through the agent's own exploration.
  - `success_no_skill_seen`: The agent never viewed any skill and still completed the subtask through independent exploration.
  - `success_skill_used_with_extra_exploration`: The agent genuinely relied on a skill and completed the subtask, but additional exploration was still required. That exploration must depend on the skill context; without the skill's framing, the extra exploration would not naturally arise.
  - `fail_skill_issue`: The main reason for failure lies in the skill itself, such as outdated knowledge, incorrect steps, missing knowledge, ambiguous instructions, or insufficient environment notes.
  - `fail_agent_limit`: The main reason for failure lies in the agent itself, such as context-window failure, hallucination, or failure to correctly understand or follow the linked skill.
  - `fail_client_env`: The main reason for failure lies in the client-side environment, such as OS mismatch, permission limitations, missing executable packages, unavailable network access, sandbox restrictions, or insufficient hardware.
  - `fail_external_env`: The main reason for failure lies in external systems or services, such as unstable APIs, upstream outages, or remote dependency failures.
  - `fail_unknown_env`: The subtask clearly failed due to some environmental cause, but the evidence is insufficient to distinguish client environment from external environment.
  - `uncertain_human_judge_required`: The result fundamentally depends on human preference-based review or evaluation, but such judgement is unavailable.
  - `uncertain_environment_judge_inconclusive`: Some environment-based signal exists, but it is not sufficient to conclusively establish success or failure for the full goal.
  - `uncertain_no_judge`: No explicit judge signal exists, and the task is not simple enough to be treated as self-evident.
- `attribution_reason` (`str`): Evidence-based justification for the chosen attribution. State the decisive facts, observations, or trajectory patterns that explain why this subtask is labeled with this specific result-and-cause category.
- `skill_linked` (`str | null`): The canonical name of the single skill linked to this subtask. A skill is linked if it was viewed during this subtask, or if it materially shaped the action path, reasoning path, or exploration path. Use `null` only when no skill should be linked to this subtask.
- `skill_refs` (`list[SkillRef]`): The knowledge spans from the linked skill that actually affected this subtask. Include only spans that were genuinely relied upon. Use an empty list when no concrete knowledge span from the linked skill was actually used.

Each `SkillRef` contains:

- `file_path` (`str`): The path to the referenced file inside the skill directory, relative to the skill root. Do not use an absolute path. When a `SkillRef` is needed, read the currently accessible skill content again to check this relative path.
- `start_line` (`int | null`): The 1-based starting line number of the referenced knowledge span. When a `SkillRef` is needed, read the currently accessible skill content again to check this line number. Use `null` when a reliable line-level reference is unavailable.
- `end_line` (`int | null`): The 1-based ending line number of the referenced knowledge span. When a `SkillRef` is needed, read the currently accessible skill content again to check this line number. Use `null` when a reliable line-level reference is unavailable.
- `capability` (`str`): A concise one-sentence summary of the capability, instruction, or knowledge expressed by this span.
- `used_for` (`str`): A precise explanation of how this knowledge span was actually used in the current subtask.

## Rules

### Subtask definition and granularity

A subtask must be a minimal but semantically complete unit of work.

Each subtask must satisfy all of the following:

- it has one standalone goal;
- it has one primary judge source;
- it has at most one linked skill context.

Split work into separate subtasks when any of the following changes:

- the goal changes;
- the primary judge source changes;
- the linked skill context changes.

Do not split merely because many low-level commands were executed.

Good splitting examples:

- "Implement a frontend page that can be built and run locally" and "make the frontend page visually better" should usually be separate subtasks.
  - The first goal is to implement a runnable page and may be judged by environment feedback such as build success, launch success, or deployment success.
  - The second goal is visual quality and usually depends on human judgement, so it may be uncertain.
- "Implement training code that can run successfully" and "train a meaningfully stronger model" should usually be separate subtasks.
  - The first goal is to make the training pipeline work and may be judged by environment feedback.
  - The second goal is model quality and may remain uncertain unless there is a trusted benchmark or verifier.

### Attribution

`attribution` directly encodes:

- the final result state;
- the primary reason category.

Always determine attribution from the final state of the subtask.

If a subtask failed at first but was eventually completed, it must still be labeled as a success attribution.

Use a failure attribution only when the goal was still not achieved by the end of the subtask.

Use an uncertain attribution only when the result cannot be conclusively established as either success or failure.

`attribution` and `judge` are related but not identical:

- `attribution` answers what the final result was and what the main cause category is;
- `judge` answers what kind of signal mainly supports that conclusion.

Uncertain attributions are especially appropriate in the following cases:

- the goal requires human review or evaluation, but such review is unavailable;
- some environment feedback exists, but it does not fully cover the goal;
- no explicit judge signal exists, and the task is not simple enough to be self-evident.

### Judge

Use:

- `environment` when the primary judgement comes from observable environment feedback ( including the verifier from the benchmark);
- `human` when the result fundamentally depends on human preference-based review or evaluation;
- `unknown` when there is no explicit judge signal.

Important distinctions:

- Executed tests may still count as `environment`, because they produce objective feedback when run.
- However, if it is unclear whether those tests fully cover the goal, the correct attribution may still be `uncertain_environment_judge_inconclusive`.
- For trivial self-evident tasks, `judge` may be `unknown` even when the attribution is successful.
- A verifier is a task-level ground-truth judgement signal for overall success or failure. It evaluates whether the full task goal has been achieved, rather than whether any individual subtask has succeeded. Please assume that a trusted verifier covers the complete test space, including all relevant cases, not just a subset. Therefore, it is possible for the overall task to be successful even if some subtasks failed along the way, because those failed subtasks may have been intermediate attempts that were later corrected. However, it should not be possible for all subtasks to be successful while the final task still fails, because the task-level verifier is the authoritative ground truth for the final outcome.

Example:

- If the user asks `1 + 1 =?` and the agent answers `2` without using a calculator, `judge` can be `unknown`.

### `skill_linked` and `skill_refs`

Each subtask may link to at most one skill.

A skill is linked to a subtask if it was viewed during that subtask, or if it materially shaped the execution path for that subtask.

All viewed skills must be covered by the subtask list. If the agent viewed three different skills during the overall task, those three viewed skills must be reflected across the produced subtasks.

Therefore:

- a viewed skill may and often should be linked to the subtask;
- when the attribution is `success_viewed_skill_but_not_used`, `skill_linked` should normally be present;
- set `skill_linked` to `null` only when no skill is meaningfully associated with the subtask.

`skill_refs` should include only the knowledge spans that were actually used.

Do not include unrelated spans from the same skill.

If a skill was only viewed but no specific knowledge span was actually used, set `skill_refs` to an empty list.

### Exploration vs Summary

`summary` is a high-level factual execution summary. It describes what happened in the subtask.

`exploration` is different. It captures a reusable delta discovered through the subtask. It may go beyond factual retelling and may include reusable knowledge, procedure, constraint, workaround, recovery pattern, decomposition, or why a certain exploration direction was meaningful.

Set `exploration` to a non-empty string only when the subtask produced such reusable content. Otherwise set it to `null`.

Do not record as `exploration`:

- ordinary trial-and-error;
- repetitive command attempts;
- low-level operational noise;
- one-off accidental discoveries that do not generalize.
""".strip()


def format_ground_truth_context(ground_truth_dir: Path | None) -> str:
    if ground_truth_dir is None:
        return ""
    return f"""
The task oracle files are available at `{ground_truth_dir.resolve()}`.
The directory may contain:

- `solution/`: the ground-truth solution files for this task.
- `verifier/tests/`: the verification test files for this task.
- `verifier/test-stdout.txt`: the stdout produced by the verification tests.

Use these files only as oracle evidence for splitting subtasks, interpreting verification behavior, and judging whether a successful exploration is actually correct.
Do not copy answers, canary strings, fixed private values, one-off paths, or exact ground-truth outputs into `exploration`.
The `ground_truth_path` field is attached programmatically after your response; do not output it yourself.
""".strip()


def build_user_prompt(**kwargs: Any) -> str:
    return _PROMPT.format(**kwargs)


def build_claude_user_prompt(**kwargs: Any) -> str:
    return _CLAUDE_PROMPT.format(**kwargs)


def build(key: PromptKey, **kwargs: Any) -> dict[str, Any]:
    if key != "user_prompt":
        raise KeyError(f"Unsupported feedback prompt key: {key}")
    return {"user_prompt": build_user_prompt(**kwargs)}


def build_claude(key: PromptKey, **kwargs: Any) -> dict[str, Any]:
    if key != "user_prompt":
        raise KeyError(f"Unsupported feedback prompt key: {key}")
    return {"user_prompt": build_claude_user_prompt(**kwargs)}
