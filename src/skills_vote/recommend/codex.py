from __future__ import annotations

import json
import shlex
from contextlib import suppress
from pathlib import Path
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
from skills_vote.utils import build_prompt_template


async def _upload_recommendation_config_toml(
    agent: Any,
    environment: BaseEnvironment,
    config_toml: str,
    codex_home: str,
    local_dir: Path,
) -> None:
    if not config_toml.strip():
        return

    config_path = local_dir / "config.toml"
    config_path.write_text(config_toml, encoding="utf-8")
    target_path = f"{codex_home.rstrip('/')}/config.toml"
    await environment.upload_file(config_path, target_path)
    if environment.default_user is not None:
        await agent.exec_as_root(
            environment,
            command=f"chown {environment.default_user} {shlex.quote(target_path)}",
        )


async def step_recommend(
    *,
    agent: Any,
    instruction: str,
    environment: BaseEnvironment,
    recommend_config: RecommendConfig,
    main_env: dict[str, str],
    openai_base_url: str | None,
    model: str,
    cli_flags_arg: str,
) -> RecommendOutput | None:
    skills_dir = recommend_config.skills_dir
    recommendation_dir = agent.logs_dir.parent / "recommendation"
    recommendation_dir.mkdir(parents=True, exist_ok=True)

    schema_path = recommendation_dir / "recommendation.schema.json"
    output_path = recommendation_dir / "recommendation.json"
    log_path = recommendation_dir / "codex.recommendation.txt"
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

    env_codex_home = "/tmp/codex-recommendation-home"
    env_recommendation_dir = "/tmp/codex-recommendation"
    env: dict[str, str] = {"CODEX_HOME": env_codex_home}
    schema_target = f"{env_recommendation_dir}/{schema_path.name}"
    cleanup_command = (
        f"rm -rf /tmp/codex-secrets {shlex.quote(env_codex_home)} "
        f"{shlex.quote(env_recommendation_dir)}"
    )
    install_all_skills_command = (
        'mkdir -p "$CODEX_HOME/skills"\n'
        f"cp -R {shlex.quote(skills_dir.rstrip('/') + '/.')} "
        '"$CODEX_HOME/skills"'
    )

    auth_json_path = agent._resolve_auth_json_path()
    if not auth_json_path:
        env["OPENAI_API_KEY"] = agent._get_env("OPENAI_API_KEY") or ""

    if openai_base_url:
        env["OPENAI_BASE_URL"] = openai_base_url

    setup_command = (
        f"rm -rf {shlex.quote(env_codex_home)} "
        f"{shlex.quote(env_recommendation_dir)}\n"
        'mkdir -p "$CODEX_HOME"\n'
        'mkdir -p "$CODEX_HOME/skills"\n'
        f"mkdir -p {shlex.quote(env_recommendation_dir)}\n"
        f"printf %s {shlex.quote(schema_json)} > {shlex.quote(schema_target)}\n"
    )
    if not auth_json_path:
        setup_command += (
            "mkdir -p /tmp/codex-secrets\n"
            "cat >/tmp/codex-secrets/auth.json <<EOF\n"
            '{\n  "OPENAI_API_KEY": "${OPENAI_API_KEY}"\n}\nEOF\n'
            'ln -sf /tmp/codex-secrets/auth.json "$CODEX_HOME/auth.json"\n'
        )

    await agent.exec_as_agent(environment, command=setup_command, env=env)
    if auth_json_path:
        auth_target = f"{env_codex_home}/auth.json"
        await environment.upload_file(auth_json_path, auth_target)
        if environment.default_user is not None:
            await agent.exec_as_root(
                environment,
                command=f"chown {environment.default_user} {auth_target}",
            )

    disabled_skill_paths = await agent._disabled_skill_paths(
        environment,
        env,
        codex_home=env_codex_home,
    )
    disabled_plugin_names = await agent._disabled_plugin_names(environment, env)
    config_toml = agent._build_config_toml(
        openai_base_url=openai_base_url,
        disabled_skill_paths=disabled_skill_paths,
        disabled_plugin_names=disabled_plugin_names,
        trusted_project_paths=[skills_dir],
    )
    await _upload_recommendation_config_toml(
        agent=agent,
        environment=environment,
        config_toml=config_toml,
        codex_home=env_codex_home,
        local_dir=recommendation_dir,
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

    output_target = f"{env_recommendation_dir}/{output_path.name}"
    log_target = f"{env_recommendation_dir}/{log_path.name}"
    move_session_command = (
        'sessions_prefix="$CODEX_HOME/sessions/"\n'
        'session_file="$(find "$CODEX_HOME/sessions" -name \'*.jsonl\' '
        '-type f -print -quit 2>/dev/null)"\n'
        'if [ -n "$session_file" ]; then\n'
        '  rel="${session_file#$sessions_prefix}"\n'
        f'  destination="{env_recommendation_dir}/sessions/$rel"\n'
        '  mkdir -p "$(dirname "$destination")"\n'
        '  mv "$session_file" "$destination"\n'
        "fi"
    )
    env_sessions_dir = f"{env_recommendation_dir}/sessions"
    local_sessions_dir = recommendation_dir / "sessions"

    async def download_recommendation_artifacts() -> None:
        local_sessions_dir.mkdir(parents=True, exist_ok=True)
        with suppress(Exception):
            await environment.download_file(log_target, log_path)
        with suppress(Exception):
            await environment.download_file(output_target, output_path)
        with suppress(Exception):
            await environment.download_dir(env_sessions_dir, local_sessions_dir)

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
                    'if [ -s "$NVM_DIR/nvm.sh" ]; then . "$NVM_DIR/nvm.sh"; fi; '
                    "codex exec "
                    "--dangerously-bypass-approvals-and-sandbox "
                    "--skip-git-repo-check "
                    f"--model {model} "
                    "--json "
                    "--enable unified_exec "
                    f"{cli_flags_arg}"
                    f"-c {shlex.quote(f'developer_instructions={system_prompt}')} "
                    f"--output-schema {shlex.quote(schema_target)} "
                    f"--output-last-message {shlex.quote(output_target)} "
                    "-- "
                    f"{shlex.quote(user_prompt)} "
                    f"2>&1 </dev/null | tee {shlex.quote(log_target)}"
                ),
                cwd=skills_dir,
                env=env,
            )
        except RuntimeError as exc:
            command_error_path.write_text(f"{exc}\n", encoding="utf-8")
        finally:
            with suppress(RuntimeError):
                await agent.exec_as_agent(
                    environment,
                    command=move_session_command,
                    env=env,
                )
            await download_recommendation_artifacts()

        try:
            return RecommendOutput.model_validate_json(
                output_path.read_text(encoding="utf-8")
            )
        except (FileNotFoundError, ValidationError) as exc:
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
            commands = ['mkdir -p "$CODEX_HOME/skills"']
            for skill_name in recommendation.skill_names:
                source = f"{skills_dir.rstrip('/')}/{skill_name}"
                commands.append(f'cp -R {shlex.quote(source)} "$CODEX_HOME/skills"/')
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
