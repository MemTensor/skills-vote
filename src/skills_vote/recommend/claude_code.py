from __future__ import annotations

import json
import shlex
from contextlib import suppress
from typing import Any

from harbor.environments.base import BaseEnvironment
from pydantic import ValidationError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from skills_vote.recommend.model import RecommendConfig, RecommendOutput
from skills_vote.utils import build_prompt_template, read_claude_output_payload


async def step_recommend(
    *,
    agent: Any,
    instruction: str,
    environment: BaseEnvironment,
    recommend_config: RecommendConfig,
    main_env: dict[str, str],
    cli_flags_arg: str,
) -> RecommendOutput | None:
    skills_dir = recommend_config.skills_dir
    recommendation_dir = agent.logs_dir.parent / "recommendation"
    recommendation_dir.mkdir(parents=True, exist_ok=True)

    schema_path = recommendation_dir / "recommendation.schema.json"
    output_path = recommendation_dir / "recommendation.json"
    log_path = recommendation_dir / "claude.recommendation.txt"
    command_error_path = recommendation_dir / "command-error.txt"
    output_error_path = recommendation_dir / "recommendation-error.txt"
    schema_json = (
        json.dumps(
            RecommendOutput.model_json_schema(),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    schema_path.write_text(schema_json, encoding="utf-8")

    env_claude_config_dir = "/tmp/claude-recommendation-home"
    env_recommendation_dir = "/tmp/claude-recommendation"
    env = dict(main_env)
    env["CLAUDE_CONFIG_DIR"] = env_claude_config_dir
    cleanup_command = (
        f"rm -rf {shlex.quote(env_claude_config_dir)} "
        f"{shlex.quote(env_recommendation_dir)}"
    )
    install_all_skills_command = (
        'mkdir -p "$CLAUDE_CONFIG_DIR/skills"\n'
        f"cp -R {shlex.quote(skills_dir.rstrip('/') + '/.')} "
        '"$CLAUDE_CONFIG_DIR/skills"'
    )

    system_prompt = build_prompt_template(
        recommend_config.prompt_path,
        key="system_prompt",
        default_top_k=recommend_config.default_top_k,
    )
    user_prompt = build_prompt_template(
        recommend_config.prompt_path,
        key="user_prompt",
        skills_root=skills_dir,
        user_query=instruction,
    )

    setup_command = (
        f"rm -rf {shlex.quote(env_claude_config_dir)} "
        f"{shlex.quote(env_recommendation_dir)}\n"
        'mkdir -p "$CLAUDE_CONFIG_DIR" "$CLAUDE_CONFIG_DIR/skills"\n'
        f"mkdir -p {shlex.quote(env_recommendation_dir)}\n"
    )
    disable_system_skills_command = agent._build_disable_system_skills_command()
    if disable_system_skills_command:
        setup_command += f"{disable_system_skills_command}\n"

    await agent.exec_as_agent(environment, command=setup_command, env=env)

    output_target = f"{env_recommendation_dir}/{output_path.name}"
    log_target = f"{env_recommendation_dir}/{log_path.name}"
    env_projects_dir = f"{env_claude_config_dir}/projects"
    local_sessions_dir = recommendation_dir / "sessions" / "projects"

    async def download_recommendation_artifacts() -> None:
        local_sessions_dir.mkdir(parents=True, exist_ok=True)
        with suppress(Exception):
            await environment.download_file(log_target, log_path)
        with suppress(Exception):
            await environment.download_file(output_target, output_path)
        with suppress(Exception):
            await environment.download_dir(env_projects_dir, local_sessions_dir)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception(
            lambda exc: (
                isinstance(exc, RuntimeError)
                and str(exc).startswith("recommendation output error:")
            )
        ),
        reraise=True,
    )
    async def recommend_once() -> RecommendOutput:
        command_error_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
        log_path.unlink(missing_ok=True)

        try:
            await agent.exec_as_agent(
                environment,
                command=f"rm -f {shlex.quote(output_target)} {shlex.quote(log_target)}",
                env=env,
            )
            await agent.exec_as_agent(
                environment,
                command=(
                    'export PATH="$HOME/.local/bin:$PATH"; '
                    "claude --output-format=json "
                    "--permission-mode=bypassPermissions "
                    f"{cli_flags_arg}"
                    f"--json-schema {shlex.quote(schema_json)} "
                    f"--append-system-prompt {shlex.quote(system_prompt)} "
                    f"--print -- {shlex.quote(user_prompt)} "
                    f"> {shlex.quote(output_target)} 2>&1\n"
                    "status=$?\n"
                    f"cp {shlex.quote(output_target)} {shlex.quote(log_target)}\n"
                    "exit $status"
                ),
                cwd=skills_dir,
                env=env,
            )
        except RuntimeError as exc:
            command_error_path.write_text(f"{exc}\n", encoding="utf-8")
        finally:
            await download_recommendation_artifacts()

        try:
            recommendation = RecommendOutput.model_validate(
                read_claude_output_payload(output_path)
            )
            output_path.write_text(
                json.dumps(
                    recommendation.model_dump(),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            return recommendation
        except (
            FileNotFoundError,
            TypeError,
            json.JSONDecodeError,
            ValidationError,
        ) as exc:
            raise RuntimeError(
                f"recommendation output error: invalid output in {output_path}"
            ) from exc

    try:
        recommendation = await recommend_once()
    except RuntimeError as exc:
        if not str(exc).startswith("recommendation output error:"):
            raise
        output_error_path.write_text(f"{exc}\n", encoding="utf-8")
        await agent.exec_as_agent(
            environment,
            command=install_all_skills_command,
            env=main_env,
        )
        with suppress(RuntimeError):
            await agent.exec_as_agent(
                environment,
                command=cleanup_command,
                env=env,
            )
        return None

    try:
        if recommendation.skill_names:
            commands = ['mkdir -p "$CLAUDE_CONFIG_DIR/skills"']
            for skill_name in recommendation.skill_names:
                source = f"{skills_dir.rstrip('/')}/{skill_name}"
                commands.append(
                    f'cp -R {shlex.quote(source)} "$CLAUDE_CONFIG_DIR/skills"/'
                )
            await agent.exec_as_agent(
                environment,
                command="\n".join(commands),
                env=main_env,
            )
    except RuntimeError as exc:
        (recommendation_dir / "install-error.txt").write_text(
            f"{exc}\n",
            encoding="utf-8",
        )
        await agent.exec_as_agent(
            environment,
            command=install_all_skills_command,
            env=main_env,
        )
        with suppress(RuntimeError):
            await agent.exec_as_agent(
                environment,
                command=cleanup_command,
                env=env,
            )
        return None

    with suppress(RuntimeError):
        await agent.exec_as_agent(
            environment,
            command=cleanup_command,
            env=env,
        )
    return recommendation
