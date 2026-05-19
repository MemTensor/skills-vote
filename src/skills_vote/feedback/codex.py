from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import tomlkit
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
    feedback_codex_cli_args,
    prepare_ground_truth_dir,
)
from skills_vote.utils import (
    build_prompt_template,
    find_latest_session_file_by_id,
    read_session_id_from_jsonl,
    run_command,
)


def prepare_codex_home(
    codex_home: Path,
    *,
    source_codex_home: Path,
    config_path: Path,
    reset: bool = False,
) -> None:
    if reset:
        shutil.rmtree(codex_home, ignore_errors=True)

    codex_home.mkdir(parents=True, exist_ok=True)
    config = tomlkit.parse(config_path.read_text(encoding="utf-8"))
    config.pop("skills", None)
    config.pop("projects", None)
    (codex_home / "config.toml").write_text(tomlkit.dumps(config), encoding="utf-8")
    shutil.copy2(source_codex_home / "auth.json", codex_home / "auth.json")


async def step_feedback(
    skills_vote_config: dict[str, Any],
    result: TrialResult,
    trial_dir: Path,
) -> FeedbackPayload:
    feedback_prompt_path = skills_vote_config["feedback_prompt_path"]
    source_codex_home = Path(skills_vote_config["codex_home"])
    feedback_dir = trial_dir / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)
    ground_truth_dir = (
        prepare_ground_truth_dir(result, trial_dir, feedback_dir)
        if skills_vote_config.get("feedback_include_ground_truth", False)
        else None
    )
    codex_home = feedback_dir / ".codex"
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
    session_files = list(session_root.rglob("*.jsonl"))
    if not session_files:
        raise RuntimeError(
            "feedback missing agent session:"
            f"expected exactly one agent session file in {session_root}, found 0"
        )
    if len(session_files) != 1:
        raise RuntimeError(
            f"expected exactly one agent session file in {session_root}, "
            f"found {len(session_files)}"
        )
    session_id = read_session_id_from_jsonl(session_files[0])

    agent_dir = trial_dir / "agent"
    agent_skills_dir = agent_dir / "skills"

    def prepare_feedback_codex_home() -> None:
        prepare_codex_home(
            codex_home,
            source_codex_home=source_codex_home,
            config_path=agent_dir / "config.toml",
            reset=True,
        )
        shutil.copytree(agent_skills_dir, codex_home / "skills")
        shutil.copytree(session_root, codex_home / "sessions", dirs_exist_ok=True)
        for pattern in ("state_*.sqlite*", "logs_*.sqlite*"):
            for source in agent_dir.glob(pattern):
                shutil.copy2(source, codex_home / source.name)

    verifier_summary_extractors = skills_vote_config.get(
        "feedback_verifier_summary_extractors",
        ["ctrf", "pytest_stdout", "reward"],
    )
    num_total_test_cases, num_passed_test_cases, num_failed_test_cases = (
        extract_test_case_counts(result, trial_dir, verifier_summary_extractors)
    )

    user_prompt = build_prompt_template(
        feedback_prompt_path,
        key="user_prompt",
        cwd=str(feedback_dir.resolve()),
        available_skills=format_available_skills(agent_skills_dir),
        ground_truth_context=format_ground_truth_context(ground_truth_dir),
        num_total_test_cases=num_total_test_cases,
        num_passed_test_cases=num_passed_test_cases,
        num_failed_test_cases=num_failed_test_cases,
    )
    feedback_log_path = feedback_dir / "codex.feedback.txt"
    feedback_cli_args = feedback_codex_cli_args(result)
    feedback_timeout_sec = skills_vote_config.get("feedback_timeout_sec", 1800)

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
        prepare_feedback_codex_home()
        feedback_json_path.unlink(missing_ok=True)
        feedback_log_path.unlink(missing_ok=True)
        command_error: RuntimeError | None = None

        try:
            await run_command(
                [
                    "codex",
                    "exec",
                    "--output-schema",
                    str(feedback_schema_path),
                    "--output-last-message",
                    str(feedback_json_path),
                    *feedback_cli_args,
                    "resume",
                    session_id,
                    "--dangerously-bypass-approvals-and-sandbox",
                    "--skip-git-repo-check",
                    "-",
                ],
                cwd=feedback_dir,
                env={"CODEX_HOME": str(codex_home)},
                stdin_text=user_prompt,
                log_path=feedback_log_path,
                timeout_sec=feedback_timeout_sec,
            )
        except TimeoutError as exc:
            raise RuntimeError(
                "feedback retryable output error:"
                f"codex exec timed out after {feedback_timeout_sec} seconds"
            ) from exc
        except RuntimeError as exc:
            command_error = exc

        try:
            feedback_session_file = find_latest_session_file_by_id(
                codex_home / "sessions",
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

        try:
            return FeedbackOutputPayload.model_validate_json(
                feedback_json_path.read_text(encoding="utf-8")
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "feedback retryable output error:"
                f"output file not found: {feedback_json_path}"
            ) from (command_error or exc)
        except ValidationError as exc:
            raise RuntimeError(
                "feedback retryable output error:"
                f"output is not valid FeedbackOutputPayload JSON: {feedback_json_path}"
            ) from (command_error or exc)

    try:
        feedback_payload = await run_feedback_once()
    finally:
        (codex_home / "auth.json").unlink(missing_ok=True)

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
