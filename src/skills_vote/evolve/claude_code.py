from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from skills_vote.evolve.model import (
    EDIT_ACTION_TYPES,
    Action,
    EvolveOutput,
    EvolveRequest,
)
from skills_vote.evolve.utils import (
    copy_created_skill_dir,
    dump_subtask_without_ground_truth,
)
from skills_vote.utils import (
    build_claude_agent_env_config,
    build_claude_env,
    build_claude_tool_args,
    build_prompt_template,
    find_latest_claude_session_file_by_id,
    read_claude_output_payload,
    run_command,
)


def extract_claude_session_id(output_path: Path) -> str:
    output = json.loads(output_path.read_text(encoding="utf-8"))
    session_id = output.get("session_id")
    if isinstance(session_id, str) and session_id:
        return session_id
    raise ValueError(f"Claude output does not contain session_id: {output_path}")


async def step_evolve(
    skills_vote_config: dict[str, Any],
    output_dir: Path,
    requests: list[EvolveRequest],
) -> Path | None:
    if not requests:
        return None

    evolve_prompt_path = skills_vote_config["evolve_prompt_path"]
    evolve_timeout_sec = skills_vote_config["evolve_timeout_sec"]
    claude_config_dir = Path(skills_vote_config["claude_config_dir"])
    working_skills_dir = Path(skills_vote_config["working_skills_dir"])
    skill_backup_dir = Path(skills_vote_config["skill_backup_dir"])
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = output_dir / "evolve"
    shutil.rmtree(run_root, ignore_errors=True)
    run_root.mkdir(parents=True, exist_ok=True)
    working_skills_dir.mkdir(parents=True, exist_ok=True)
    skill_backup_dir.mkdir(parents=True, exist_ok=True)
    claude_config_dir.mkdir(parents=True, exist_ok=True)

    runtime_root = run_root / ".tmp"
    runtime_root.mkdir(parents=True, exist_ok=True)
    evolve_schema_path = runtime_root / "evolution.schema.json"
    evolve_schema_path.write_text(
        json.dumps(EvolveOutput.model_json_schema(), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    env_config = build_claude_agent_env_config(
        env_config=skills_vote_config.get("claude_env", {}),
        agent_env=skills_vote_config.get("claude_agent_env", {}),
        agent_kwargs=skills_vote_config.get("claude_agent_kwargs", {}),
    )
    env = build_claude_env(
        model_name=skills_vote_config["claude_model_name"],
        env_config=env_config,
        claude_config_dir=claude_config_dir,
    )
    claude_tool_args = build_claude_tool_args(
        skills_vote_config.get("claude_tool_kwargs", {})
    )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception(
            lambda exc: (
                isinstance(exc, RuntimeError)
                and str(exc).startswith("evolution retryable output error:")
            )
        ),
        reraise=True,
    )
    async def run_evolve_once(
        *,
        create_dir: Path,
        edit_dir: Path | None,
        request_runtime_dir: Path,
        request_session_dir: Path,
        request_dir: Path,
        request_dir_name: str,
        system_prompt: str,
        user_prompt: str,
        working_skill_dir: Path | None,
    ) -> EvolveOutput:
        shutil.rmtree(request_runtime_dir, ignore_errors=True)
        shutil.rmtree(request_session_dir, ignore_errors=True)
        shutil.rmtree(create_dir, ignore_errors=True)
        if edit_dir is not None:
            shutil.rmtree(edit_dir.parent, ignore_errors=True)
        request_runtime_dir.mkdir(parents=True, exist_ok=True)
        create_dir.mkdir(parents=True, exist_ok=True)
        if working_skill_dir is not None and edit_dir is not None:
            shutil.copytree(working_skill_dir, edit_dir, dirs_exist_ok=True)

        output_path = request_runtime_dir / "evolution.json"
        evolve_log_path = request_runtime_dir / "claude.evolution.txt"
        output_path.unlink(missing_ok=True)
        evolve_log_path.unlink(missing_ok=True)
        command_error: RuntimeError | None = None

        try:
            await run_command(
                [
                    "claude",
                    "--output-format",
                    "json",
                    "--permission-mode=bypassPermissions",
                    *claude_tool_args,
                    "--json-schema",
                    evolve_schema_path.read_text(encoding="utf-8"),
                    "--append-system-prompt",
                    system_prompt,
                    "--print",
                ],
                cwd=request_dir,
                env=env,
                stdin_text=user_prompt,
                log_path=evolve_log_path,
                timeout_sec=evolve_timeout_sec,
            )
        except TimeoutError as exc:
            raise RuntimeError(
                "evolution retryable output error:"
                f"claude timed out for request={request_dir_name} "
                f"after {evolve_timeout_sec} seconds"
            ) from exc
        except RuntimeError as exc:
            command_error = exc
        if command_error is not None:
            raise RuntimeError(
                "evolution retryable output error:"
                f"claude command failed for request={request_dir_name}: {command_error}"
            ) from command_error

        try:
            evolve_session_id = extract_claude_session_id(evolve_log_path)
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "evolution retryable output error:"
                f"session id not found in {evolve_log_path}"
            ) from (command_error or exc)

        try:
            evolve_session_file = find_latest_claude_session_file_by_id(
                claude_config_dir / "projects",
                evolve_session_id,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "evolution retryable output error:"
                f"session file not found for request={request_dir_name} "
                f"session_id={evolve_session_id}"
            ) from (command_error or exc)

        request_session_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            evolve_session_file,
            request_session_dir / evolve_session_file.name,
        )

        try:
            evolve_output = EvolveOutput.model_validate(
                read_claude_output_payload(evolve_log_path)
            )
            output_path.write_text(
                json.dumps(
                    evolve_output.model_dump(),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            return evolve_output
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"evolution retryable output error:output file not found: {evolve_log_path}"
            ) from (command_error or exc)
        except (TypeError, json.JSONDecodeError, ValidationError) as exc:
            raise RuntimeError(
                "evolution retryable output error:"
                f"output is not valid EvolveOutput JSON: {evolve_log_path}"
            ) from (command_error or exc)

    for request in requests:
        request_dir = run_root / request.request_dir_name
        request_dir.mkdir(parents=True, exist_ok=True)
        request_runtime_dir = runtime_root / request.request_dir_name
        request_session_dir = run_root / "sessions" / request.request_dir_name

        target_skill_name = request.target_skill_name
        is_edit_request = target_skill_name is not None
        working_skill_dir = (
            working_skills_dir / target_skill_name
            if target_skill_name is not None
            else None
        )
        edit_dir = (
            request_dir / "edit" / target_skill_name
            if target_skill_name is not None
            else None
        )
        create_dir = request_dir / "create" if is_edit_request else request_dir
        target_skill_path = str(edit_dir.resolve()) if edit_dir is not None else None
        request_payload = {
            "timestamp": timestamp,
            "target_skill_name": target_skill_name,
            "target_skill_path": target_skill_path,
            "edit_dir": target_skill_path,
            "create_dir": str(create_dir.resolve()),
            "subtasks": [
                dump_subtask_without_ground_truth(subtask)
                for subtask in request.subtasks
            ],
        }
        if working_skill_dir is not None and not working_skill_dir.is_dir():
            (request_dir / "request.json").write_text(
                json.dumps(request_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (request_dir / "skipped.txt").write_text(
                "Skip evolve request because target skill directory does not exist: "
                f"{working_skill_dir}\n",
                encoding="utf-8",
            )
            continue

        if working_skill_dir is not None:
            backup_dir = skill_backup_dir / target_skill_name / timestamp
            shutil.copytree(working_skill_dir, backup_dir, dirs_exist_ok=True)

        prompt_values = {
            "request_type": "edit" if is_edit_request else "create",
            "subtasks": request.subtasks,
            "create_dir": str(create_dir.resolve()),
            "edit_dir": target_skill_path,
            "target_skill_name": target_skill_name,
        }

        system_prompt = build_prompt_template(
            evolve_prompt_path,
            key="system_prompt",
            **prompt_values,
        )
        user_prompt = build_prompt_template(
            evolve_prompt_path,
            key="user_prompt",
            **prompt_values,
        )

        evolve_output = await run_evolve_once(
            create_dir=create_dir,
            edit_dir=edit_dir,
            request_runtime_dir=request_runtime_dir,
            request_session_dir=request_session_dir,
            request_dir=request_dir,
            request_dir_name=request.request_dir_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            working_skill_dir=working_skill_dir,
        )
        evolve_actions = evolve_output.actions
        (request_dir / "request.json").write_text(
            json.dumps(request_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (request_dir / "evolution.json").write_text(
            json.dumps(evolve_output.model_dump(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        shutil.copy2(
            request_runtime_dir / "claude.evolution.txt",
            request_dir / "claude.evolution.txt",
        )

        edit_actions: list[Action] = [
            action
            for action in evolve_actions
            if action.action_type in EDIT_ACTION_TYPES
        ]
        if working_skill_dir is not None and edit_actions:
            if edit_dir is None:
                continue
            evolution_log_path = edit_dir / "EVOLUTION_LOG.json"
            evolution_log = (
                json.loads(evolution_log_path.read_text(encoding="utf-8"))
                if evolution_log_path.exists()
                else []
            )
            evolution_log.append(
                {
                    "timestamp": timestamp,
                    "target_skill_name": target_skill_name,
                    "target_skill_path": target_skill_path,
                    "result": evolve_output.model_dump(),
                    "subtasks": [
                        dump_subtask_without_ground_truth(subtask)
                        for subtask in request.subtasks
                    ],
                }
            )
            evolution_log_path.write_text(
                json.dumps(evolution_log, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            shutil.rmtree(working_skill_dir, ignore_errors=True)
            shutil.copytree(edit_dir, working_skill_dir, dirs_exist_ok=True)

        for action in evolve_actions:
            if action.action_type != "create_skill" or action.skill_dir_path is None:
                continue

            copy_created_skill_dir(
                create_dir=create_dir,
                request_dir=request_dir,
                skill_dir_path=action.skill_dir_path,
                working_skills_dir=working_skills_dir,
            )

    shutil.rmtree(runtime_root, ignore_errors=True)
    return run_root
