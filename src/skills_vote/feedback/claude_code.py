from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

from harbor.models.trial.result import TrialResult
from pydantic import ValidationError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from skills_vote.feedback.model import FeedbackOutputPayload, FeedbackPayload
from skills_vote.feedback.prompt import (
    format_available_skills,
    format_ground_truth_context,
)
from skills_vote.feedback.utils import (
    attach_ground_truth_path,
    dump_feedback_payload,
    extract_test_case_counts,
    prepare_ground_truth_dir,
)
from skills_vote.utils import (
    build_claude_agent_env_config,
    build_claude_env,
    build_claude_tool_args,
    build_prompt_template,
    find_latest_claude_session_file_by_id,
    read_claude_output_payload,
    read_claude_session_id_from_jsonl,
    run_command,
)

_RESUME_CWD_LOCKS: dict[Path, asyncio.Lock] = {}


def prepare_claude_config_dir(
    claude_config_dir: Path,
    *,
    source_claude_config_dir: Path | None = None,
    reset: bool = False,
) -> None:
    if reset:
        shutil.rmtree(claude_config_dir, ignore_errors=True)

    claude_config_dir.mkdir(parents=True, exist_ok=True)
    if source_claude_config_dir is not None and source_claude_config_dir.is_dir():
        shutil.copytree(
            source_claude_config_dir,
            claude_config_dir,
            dirs_exist_ok=True,
        )


def resolve_claude_resume_cwd(trial_dir: Path, session_project_dir: Path) -> Path:
    trajectory_path = trial_dir / "agent" / "trajectory.json"
    if trajectory_path.is_file():
        trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
        cwds = trajectory["agent"]["extra"]["cwds"]
        if cwds:
            return Path(cwds[0])
    return Path(session_project_dir.name.replace("-", "/"))


def get_resume_cwd_lock(resume_cwd: Path) -> asyncio.Lock:
    lock = _RESUME_CWD_LOCKS.get(resume_cwd)
    if lock is None:
        lock = asyncio.Lock()
        _RESUME_CWD_LOCKS[resume_cwd] = lock
    return lock


def build_claude_resume_context(*, resume_cwd: Path, feedback_dir: Path) -> str:
    return f"""
## Claude Code Resume Context

Claude Code is resumed from `{resume_cwd}` only because sessions are scoped to their original project directory.
Use `{feedback_dir.resolve()}` and the absolute paths in this prompt as the current feedback artifact context.
""".strip()


async def step_feedback(
    skills_vote_config: dict[str, Any],
    result: TrialResult,
    trial_dir: Path,
) -> FeedbackPayload:
    feedback_prompt_path = skills_vote_config["feedback_prompt_path"]
    source_claude_config_dir = Path(skills_vote_config["claude_config_dir"])
    feedback_dir = trial_dir / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)
    ground_truth_dir = (
        prepare_ground_truth_dir(result, trial_dir, feedback_dir)
        if skills_vote_config.get("feedback_include_ground_truth", False)
        else None
    )
    claude_config_dir = feedback_dir / ".claude"
    feedback_json_path = feedback_dir / "feedback.json"
    feedback_schema_path = feedback_dir / "feedback.schema.json"
    feedback_schema_path.write_text(
        json.dumps(
            FeedbackOutputPayload.model_json_schema(),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    session_root = trial_dir / "agent" / "sessions"
    session_project_root = session_root / "projects"
    session_files = [
        session_file
        for session_file in session_project_root.rglob("*.jsonl")
        if "subagents" not in session_file.parts
    ]
    if not session_files:
        raise RuntimeError(
            "feedback missing agent session:"
            f"expected exactly one agent session file in {session_project_root}, "
            "found 0"
        )
    if len(session_files) != 1:
        raise RuntimeError(
            f"expected exactly one agent session file in {session_project_root}, "
            f"found {len(session_files)}"
        )
    session_file = session_files[0]
    session_project_dir = session_file.parent
    session_id = read_claude_session_id_from_jsonl(session_file)
    resume_cwd = resolve_claude_resume_cwd(trial_dir, session_project_dir)

    agent_skills_dir = session_root / "skills"

    def prepare_feedback_claude_config_dir() -> None:
        prepare_claude_config_dir(
            claude_config_dir,
            source_claude_config_dir=source_claude_config_dir,
            reset=True,
        )
        shutil.copytree(
            session_root / "projects",
            claude_config_dir / "projects",
            dirs_exist_ok=True,
        )
        if agent_skills_dir.is_dir():
            shutil.copytree(
                agent_skills_dir,
                claude_config_dir / "skills",
                dirs_exist_ok=True,
            )

    verifier_summary_extractors = skills_vote_config.get(
        "feedback_verifier_summary_extractors",
        ["ctrf", "pytest_stdout", "reward"],
    )
    num_total_test_cases, num_passed_test_cases, num_failed_test_cases = (
        extract_test_case_counts(result, trial_dir, verifier_summary_extractors)
    )

    user_prompt = "\n\n".join(
        [
            build_prompt_template(
                feedback_prompt_path,
                key="user_prompt",
                cwd=str(feedback_dir.resolve()),
                available_skills=format_available_skills(agent_skills_dir),
                ground_truth_context=format_ground_truth_context(ground_truth_dir),
                num_total_test_cases=num_total_test_cases,
                num_passed_test_cases=num_passed_test_cases,
                num_failed_test_cases=num_failed_test_cases,
            ),
            build_claude_resume_context(
                resume_cwd=resume_cwd,
                feedback_dir=feedback_dir,
            ),
        ]
    )
    feedback_log_path = feedback_dir / "claude.feedback.txt"
    feedback_timeout_sec = skills_vote_config.get("feedback_timeout_sec", 1800)
    agent_config = result.config.agent
    env_config = build_claude_agent_env_config(
        env_config=skills_vote_config.get("claude_env", {}),
        agent_env=agent_config.env,
        agent_kwargs=agent_config.kwargs,
    )
    env = build_claude_env(
        model_name=agent_config.model_name,
        env_config=env_config,
        claude_config_dir=claude_config_dir,
    )
    claude_tool_args = build_claude_tool_args(
        {
            **skills_vote_config.get("claude_tool_kwargs", {}),
            **agent_config.kwargs,
        }
    )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception(
            lambda exc: (
                isinstance(exc, RuntimeError)
                and str(exc).startswith("feedback retryable output error:")
            )
        ),
        reraise=True,
    )
    async def run_feedback_once() -> FeedbackOutputPayload:
        prepare_feedback_claude_config_dir()
        try:
            resume_cwd.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeError(
                "feedback retryable output error:"
                f"failed to prepare Claude resume cwd={resume_cwd}"
            ) from exc
        feedback_json_path.unlink(missing_ok=True)
        feedback_log_path.unlink(missing_ok=True)
        command_error: RuntimeError | None = None

        try:
            async with get_resume_cwd_lock(resume_cwd):
                await run_command(
                    [
                        "claude",
                        "--output-format",
                        "json",
                        "--permission-mode=bypassPermissions",
                        *claude_tool_args,
                        "--json-schema",
                        feedback_schema_path.read_text(encoding="utf-8"),
                        "--resume",
                        session_id,
                        "--print",
                    ],
                    cwd=resume_cwd,
                    env=env,
                    stdin_text=user_prompt,
                    log_path=feedback_log_path,
                    timeout_sec=feedback_timeout_sec,
                )
        except TimeoutError as exc:
            raise RuntimeError(
                "feedback retryable output error:"
                f"claude timed out after {feedback_timeout_sec} seconds"
            ) from exc
        except RuntimeError as exc:
            command_error = exc

        try:
            feedback_session_file = find_latest_claude_session_file_by_id(
                claude_config_dir / "projects",
                session_id,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "feedback retryable output error:"
                f"session file not found for session_id={session_id}"
            ) from (command_error or exc)

        feedback_sessions_dir = feedback_dir / "sessions"
        feedback_sessions_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            feedback_session_file,
            feedback_sessions_dir / feedback_session_file.name,
        )
        if command_error is not None:
            raise RuntimeError(
                "feedback retryable output error:"
                f"claude command failed: {command_error}"
            ) from command_error

        try:
            feedback_payload = FeedbackOutputPayload.model_validate(
                read_claude_output_payload(feedback_log_path)
            )
            feedback_json_path.write_text(
                json.dumps(
                    feedback_payload.model_dump(),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            return feedback_payload
        except FileNotFoundError as exc:
            raise RuntimeError(
                "feedback retryable output error:"
                f"output file not found: {feedback_log_path}"
            ) from (command_error or exc)
        except (TypeError, json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError(
                "feedback retryable output error:"
                f"output is not valid FeedbackOutputPayload JSON: {feedback_log_path}"
            ) from (command_error or exc)

    feedback_payload = await run_feedback_once()
    feedback_payload = attach_ground_truth_path(
        feedback_payload,
        ground_truth_dir,
    )
    feedback_json = dump_feedback_payload(feedback_payload)
    feedback_json_path.write_text(
        json.dumps(feedback_json, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (trial_dir / "feedback.json").write_text(
        json.dumps(feedback_json, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return feedback_payload
