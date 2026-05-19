from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from harbor.job import Job
from harbor.models.job.config import RetryConfig
from harbor.trial.hooks import TrialHookEvent
from harbor.utils.logger import logger

from skills_vote.evolve.model import (
    aggregate_feedback_payloads,
    feedback_to_evolve_requests,
)
from skills_vote.feedback.model import FeedbackPayload
from skills_vote.harbor.cli import SkillsVoteConfig

EVOLVE_STATE_NAME = "skills_vote_evolve_state.json"
CLAUDE_CODE_AGENT_KIND = "claude_code"


async def _step_feedback(
    *,
    skills_vote_config: dict[str, Any],
    result: Any,
    trial_dir: Path,
) -> FeedbackPayload:
    if skills_vote_config.get("agent_kind") == CLAUDE_CODE_AGENT_KIND:
        from skills_vote.feedback.claude_code import (
            step_feedback as step_feedback_claude_code,
        )

        return await step_feedback_claude_code(
            skills_vote_config=skills_vote_config,
            result=result,
            trial_dir=trial_dir,
        )

    from skills_vote.feedback.codex import step_feedback as step_feedback_codex

    return await step_feedback_codex(
        skills_vote_config=skills_vote_config,
        result=result,
        trial_dir=trial_dir,
    )


async def _step_evolve(
    *,
    skills_vote_config: dict[str, Any],
    output_dir: Path,
    requests: Any,
) -> Path | None:
    if skills_vote_config.get("agent_kind") == CLAUDE_CODE_AGENT_KIND:
        from skills_vote.evolve.claude_code import (
            step_evolve as step_evolve_claude_code,
        )

        return await step_evolve_claude_code(
            skills_vote_config=skills_vote_config,
            output_dir=output_dir,
            requests=requests,
        )

    from skills_vote.evolve.codex import step_evolve as step_evolve_codex

    return await step_evolve_codex(
        skills_vote_config=skills_vote_config,
        output_dir=output_dir,
        requests=requests,
    )


def _will_harbor_retry(
    *,
    event: TrialHookEvent,
    current_attempt_num: int,
    retry_config: RetryConfig,
) -> bool:
    if event.result is None or event.result.exception_info is None:
        return False
    if current_attempt_num > retry_config.max_retries:
        return False

    exception_type = event.result.exception_info.exception_type
    if (
        retry_config.exclude_exceptions is not None
        and exception_type in retry_config.exclude_exceptions
    ):
        return False
    if (  # noqa: SIM103
        retry_config.include_exceptions is not None
        and exception_type not in retry_config.include_exceptions
    ):
        return False
    return True


def _write_feedback_skip_marker(trial_dir: Path, reason: str) -> None:
    feedback_dir = trial_dir / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)
    (feedback_dir / "skipped.txt").write_text(f"{reason}\n", encoding="utf-8")


def _write_evolve_state(
    state_path: Path,
    pending_records: list[dict[str, Any]],
) -> None:
    state_path.write_text(
        json.dumps({"pending": pending_records}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _create_skipped_evolution_root(output_dir: Path) -> Path:
    run_root = output_dir / "evolve"
    shutil.rmtree(run_root, ignore_errors=True)
    run_root.mkdir(parents=True, exist_ok=True)
    return run_root


def _write_evolve_feedback_index(
    *,
    records: list[dict[str, Any]],
    run_root: Path,
) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "feedback_index.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


async def _run_evolve_batch(
    *,
    records: list[dict[str, Any]],
    skills_vote_config: dict[str, Any],
    trigger_trial_dir: Path,
) -> None:
    feedback_payloads = [
        FeedbackPayload.model_validate_json(
            Path(record["feedback_path"]).read_text(encoding="utf-8")
        )
        for record in records
        if record.get("feedback_path") is not None
    ]
    if not feedback_payloads:
        run_root = _create_skipped_evolution_root(trigger_trial_dir)
        (run_root / "skipped.txt").write_text(
            "Skip evolve batch because no trial produced feedback.\n",
            encoding="utf-8",
        )
        _write_evolve_feedback_index(
            records=records,
            run_root=run_root,
        )
        return

    aggregated_feedback = aggregate_feedback_payloads(feedback_payloads)
    requests = feedback_to_evolve_requests(feedback_payload=aggregated_feedback)
    if not requests:
        run_root = _create_skipped_evolution_root(trigger_trial_dir)
        (run_root / "skipped.txt").write_text(
            "Skip evolve batch because no pending feedback contained evolvable "
            "subtasks.\n",
            encoding="utf-8",
        )
        _write_evolve_feedback_index(
            records=records,
            run_root=run_root,
        )
        return

    run_root = await _step_evolve(
        skills_vote_config=skills_vote_config,
        output_dir=trigger_trial_dir,
        requests=requests,
    )
    if run_root is None:
        run_root = _create_skipped_evolution_root(trigger_trial_dir)
    _write_evolve_feedback_index(
        records=records,
        run_root=run_root,
    )


def register_cost(job: Job, _config: SkillsVoteConfig) -> None:
    from skills_vote.harbor.cost import write_job_cost

    cost_lock = asyncio.Lock()
    trial_attempts: dict[str, int] = {}

    async def on_trial_started(event: TrialHookEvent) -> None:
        trial_attempts[event.trial_id] = trial_attempts.get(event.trial_id, 0) + 1

    async def on_trial_ended(event: TrialHookEvent) -> None:
        if event.result is None:
            return
        current_attempt_num = trial_attempts.get(event.trial_id, 1)
        if _will_harbor_retry(
            event=event,
            current_attempt_num=current_attempt_num,
            retry_config=job.config.retry,
        ):
            logger.info(
                "Skipping SkillsVote cost update for retryable failed trial "
                "%s attempt %s/%s.",
                event.trial_id,
                current_attempt_num,
                job.config.retry.max_retries + 1,
            )
            return

        trial_attempts.pop(event.trial_id, None)

        trial_dir = Path(urlparse(event.result.trial_uri).path)
        async with cost_lock:
            try:
                await asyncio.to_thread(write_job_cost, trial_dir.parent)
            except Exception:
                logger.exception("Failed to write cost files for %s", trial_dir)

    job.on_trial_started(on_trial_started)
    job.on_trial_ended(on_trial_ended)


def register(job: Job, config: SkillsVoteConfig) -> None:
    skills_vote_config = config.model_dump(mode="python")
    skills_vote_config.setdefault(
        "agent_kind",
        (
            CLAUDE_CODE_AGENT_KIND
            if job.config.agents[0].import_path
            == "skills_vote.harbor.claude_code:SkillsVoteClaudeCode"
            else "codex"
        ),
    )
    if skills_vote_config["agent_kind"] == CLAUDE_CODE_AGENT_KIND:
        agent_config = job.config.agents[0]
        skills_vote_config["claude_model_name"] = agent_config.model_name
        skills_vote_config["claude_agent_env"] = agent_config.env
        skills_vote_config["claude_agent_kwargs"] = agent_config.kwargs
        skills_vote_config.setdefault(
            "claude_tool_kwargs",
            {
                key: value
                for key, value in agent_config.kwargs.items()
                if key in ("allowed_tools", "disallowed_tools")
            },
        )
    batch_condition = asyncio.Condition()
    state_path = job.job_dir / EVOLVE_STATE_NAME
    pending_records: list[dict[str, Any]] = (
        json.loads(state_path.read_text(encoding="utf-8")).get("pending", [])
        if state_path.exists()
        else []
    )
    remaining_trial_configs = getattr(job, "_remaining_trial_configs", None)
    expected_terminal_trials = (
        len(remaining_trial_configs)
        if remaining_trial_configs is not None
        else len(job)
    )
    completed_record_count = 0
    batch_running = False
    trial_attempts: dict[str, int] = {}

    async def on_trial_started(event: TrialHookEvent) -> None:
        trial_attempts[event.trial_id] = trial_attempts.get(event.trial_id, 0) + 1

    async def on_trial_ended(event: TrialHookEvent) -> None:
        nonlocal batch_running, completed_record_count

        if event.result is None:
            return
        current_attempt_num = trial_attempts.get(event.trial_id, 1)
        if _will_harbor_retry(
            event=event,
            current_attempt_num=current_attempt_num,
            retry_config=job.config.retry,
        ):
            logger.info(
                "Skipping SkillsVote feedback/evolve for retryable failed trial "
                "%s attempt %s/%s.",
                event.trial_id,
                current_attempt_num,
                job.config.retry.max_retries + 1,
            )
            return

        trial_attempts.pop(event.trial_id, None)
        if config.feedback_prompt_path is None:
            return

        trial_dir = Path(urlparse(event.result.trial_uri).path)
        feedback_path = None
        feedback_skipped_reason = None
        try:
            await _step_feedback(
                skills_vote_config=skills_vote_config,
                result=event.result,
                trial_dir=trial_dir,
            )
        except RuntimeError as exc:
            if not str(exc).startswith(
                (
                    "feedback missing agent session:",
                    "feedback missing verifier feedback:",
                    "feedback retryable output error:",
                )
            ):
                raise
            feedback_skipped_reason = str(exc)
            _write_feedback_skip_marker(trial_dir, feedback_skipped_reason)
        if config.evolve_prompt_path is None:
            return
        if feedback_skipped_reason is None:
            feedback_path = str((trial_dir / "feedback" / "feedback.json").resolve())

        record = {
            "result_id": str(event.result.id),
            "task_name": event.result.task_name,
            "trial_name": event.result.trial_name,
            "trial_dir": str(trial_dir.resolve()),
            "feedback_path": feedback_path,
        }
        if feedback_skipped_reason is not None:
            record["feedback_skipped_reason"] = feedback_skipped_reason
        record_id = record["result_id"]

        async with batch_condition:
            pending_records.append(record)
            completed_record_count += 1
            _write_evolve_state(state_path, pending_records)
            batch_condition.notify_all()

        async with batch_condition:
            while True:
                if not any(
                    pending_record["result_id"] == record_id
                    for pending_record in pending_records
                ):
                    return
                has_full_batch = len(pending_records) >= config.evolve_every_n_trials
                has_final_partial_batch = (
                    completed_record_count >= expected_terminal_trials
                    and bool(pending_records)
                )
                if (has_full_batch or has_final_partial_batch) and not batch_running:
                    batch_size = (
                        config.evolve_every_n_trials
                        if has_full_batch
                        else len(pending_records)
                    )
                    batch_records = pending_records[:batch_size]
                    batch_running = True
                    break
                await batch_condition.wait()

        try:
            await _run_evolve_batch(
                records=batch_records,
                skills_vote_config=skills_vote_config,
                trigger_trial_dir=trial_dir,
            )
        except Exception:
            async with batch_condition:
                batch_running = False
                batch_condition.notify_all()
            raise

        async with batch_condition:
            del pending_records[: len(batch_records)]
            _write_evolve_state(state_path, pending_records)
            batch_running = False
            batch_condition.notify_all()

    job.on_trial_started(on_trial_started)
    job.on_trial_ended(on_trial_ended)
