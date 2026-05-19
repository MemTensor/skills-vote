from __future__ import annotations

import json
import shlex
from pathlib import PurePosixPath
from typing import Any

from harbor.agents.installed.base import CliFlag
from harbor.agents.installed.claude_code import ClaudeCode
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.trial.paths import EnvironmentPaths

from skills_vote.recommend.claude_code import step_recommend
from skills_vote.recommend.model import RecommendConfig
from skills_vote.recommend.utils import append_recommendation_to_instruction

SYSTEM_SKILL_OVERRIDES = {
    "update-config": "off",
    "simplify": "off",
    "batch": "off",
    "fewer-permission-prompts": "off",
    "debug": "off",
    "loop": "off",
    "claude-api": "off",
}


class SkillsVoteClaudeCode(ClaudeCode):
    CLI_FLAGS = [
        CliFlag(
            flag.kwarg,
            cli=flag.cli,
            type=flag.type,
            choices=flag.choices,
            default=flag.default,
            env_fallback=(
                None if flag.kwarg == "reasoning_effort" else flag.env_fallback
            ),
            format=flag.format,
        )
        for flag in ClaudeCode.CLI_FLAGS
    ]

    def __init__(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        allowed_skills = kwargs.pop("allowed_skills", None)
        allowed_plugins = kwargs.pop("allowed_plugins", None)
        plugin_dirs = kwargs.pop("plugin_dirs", None)
        self._allowed_skills = None if allowed_skills is None else set(allowed_skills)
        if allowed_plugins:
            raise ValueError(
                "Claude Code plugin whitelisting by installed plugin name is not "
                "supported by Harbor. Pass local plugin directories with plugin_dirs."
            )
        if plugin_dirs is None:
            self._plugin_dirs: list[str] = []
        elif isinstance(plugin_dirs, str):
            self._plugin_dirs = [plugin_dirs]
        else:
            self._plugin_dirs = list(plugin_dirs)
        kwargs.pop("enabled", None)
        recommend_config_data = kwargs.pop("recommend", None)
        self.recommend_config = (
            None
            if recommend_config_data is None
            else RecommendConfig.model_validate(recommend_config_data)
        )
        if self.recommend_config is not None:
            kwargs["skills_dir"] = None

        super().__init__(*args, **kwargs)

    @staticmethod
    def name() -> str:
        return "SkillsVoteClaudeCode"

    async def setup(self, environment: BaseEnvironment) -> None:
        await environment.exec(command="mkdir -p /installed-agent", user="root")

        setup_dir = self.logs_dir / "setup"
        setup_dir.mkdir(parents=True, exist_ok=True)
        (setup_dir / "mode.txt").write_text(
            "skip install script; use preinstalled claude CLI in image\n",
            encoding="utf-8",
        )

        if self._version is not None:
            return

        version_command = self.get_version_command()
        if version_command is None:
            return

        try:
            result = await environment.exec(command=version_command)
        except Exception as exc:
            (setup_dir / "version-error.txt").write_text(str(exc), encoding="utf-8")
            return

        (setup_dir / "version-return-code.txt").write_text(
            str(result.return_code),
            encoding="utf-8",
        )
        if result.stdout:
            (setup_dir / "version-stdout.txt").write_text(
                result.stdout,
                encoding="utf-8",
            )
        if result.stderr:
            (setup_dir / "version-stderr.txt").write_text(
                result.stderr,
                encoding="utf-8",
            )
        if result.return_code == 0 and result.stdout:
            self._version = self.parse_version(result.stdout)

    def _system_skill_is_allowed(self, skill_name: str) -> bool:
        if self._allowed_skills is None:
            return True

        allowed_names: set[str] = set()
        for allowed_skill in self._allowed_skills:
            path = PurePosixPath(str(allowed_skill))
            allowed_names.add(str(allowed_skill))
            allowed_names.add(path.as_posix())
            if path.name == "SKILL.md":
                allowed_names.add(path.parent.name)
            else:
                allowed_names.add(path.name)
        return skill_name in allowed_names

    def _build_disable_system_skills_command(self) -> str | None:
        if self._allowed_skills is None:
            return None

        skill_overrides = {
            skill_name: override
            for skill_name, override in SYSTEM_SKILL_OVERRIDES.items()
            if not self._system_skill_is_allowed(skill_name)
        }
        if not skill_overrides:
            return None

        settings = json.dumps(
            {"skillOverrides": skill_overrides},
            ensure_ascii=False,
            indent=2,
        )
        return f'printf %s {shlex.quote(settings)} > "$CLAUDE_CONFIG_DIR/settings.json"'

    def _get_env_or(self, *keys: str) -> str | None:
        for key in keys:
            value = self._get_env(key)
            if value:
                return value
        return None

    def _build_claude_env(self) -> dict[str, str]:
        env: dict[str, str] = {
            "FORCE_AUTO_BACKGROUND_TASKS": "1",
            "ENABLE_BACKGROUND_TASKS": "1",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "IS_SANDBOX": "1",
        }

        anthropic_base_url = self._get_env("ANTHROPIC_BASE_URL")
        if anthropic_base_url:
            env["ANTHROPIC_BASE_URL"] = anthropic_base_url

        anthropic_auth_token = self._get_env("ANTHROPIC_AUTH_TOKEN")
        if anthropic_auth_token:
            env["ANTHROPIC_AUTH_TOKEN"] = anthropic_auth_token

        anthropic_api_key = self._get_env_or(
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
        )
        if anthropic_api_key:
            env["ANTHROPIC_API_KEY"] = anthropic_api_key

        if "ANTHROPIC_BASE_URL" in env:
            env["ANTHROPIC_MODEL"] = self.model_name
        else:
            env["ANTHROPIC_MODEL"] = self.model_name.split("/")[-1]

        env.update(self.resolve_env_vars())
        env["CLAUDE_CONFIG_DIR"] = (EnvironmentPaths.agent_dir / "sessions").as_posix()
        return env

    def _build_claude_setup_command(self) -> str:
        commands = [
            (
                'mkdir -p "$CLAUDE_CONFIG_DIR/debug" '
                '"$CLAUDE_CONFIG_DIR/projects/-app" '
                '"$CLAUDE_CONFIG_DIR/shell-snapshots" '
                '"$CLAUDE_CONFIG_DIR/statsig" '
                '"$CLAUDE_CONFIG_DIR/todos" '
                '"$CLAUDE_CONFIG_DIR/skills"'
            )
        ]
        disable_system_skills_command = self._build_disable_system_skills_command()
        if disable_system_skills_command:
            commands.append(disable_system_skills_command)

        skills_command = self._build_register_skills_command()
        if skills_command:
            commands.append(skills_command)

        memory_command = self._build_register_memory_command()
        if memory_command:
            commands.append(memory_command)

        mcp_command = self._build_register_mcp_servers_command()
        if mcp_command:
            commands.append(mcp_command)

        return "\n".join(commands)

    def _build_plugin_dir_flags(self) -> str:
        if not self._plugin_dirs:
            return ""
        return " ".join(
            f"--plugin-dir {shlex.quote(plugin_dir)}"
            for plugin_dir in self._plugin_dirs
        )

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        env = self._build_claude_env()
        cli_flags = self.build_cli_flags()
        cli_flags_arg = (cli_flags + " ") if cli_flags else ""

        if self.recommend_config is not None:
            recommendation = await step_recommend(
                agent=self,
                instruction=instruction,
                environment=environment,
                recommend_config=self.recommend_config,
                main_env=env,
                cli_flags_arg=cli_flags_arg,
            )
            if recommendation is not None and recommendation.skill_names:
                instruction = append_recommendation_to_instruction(
                    instruction,
                    recommendation,
                )

        instruction = self.render_instruction(instruction)
        escaped_instruction = shlex.quote(instruction)

        setup_command = self._build_claude_setup_command()
        await self.exec_as_agent(
            environment,
            command=setup_command,
            env=env,
        )

        plugin_dir_flags = self._build_plugin_dir_flags()
        extra_flags = " ".join(flag for flag in (cli_flags, plugin_dir_flags) if flag)
        extra_flags_arg = (extra_flags + " ") if extra_flags else ""

        await self.exec_as_agent(
            environment,
            command=(
                'export PATH="$HOME/.local/bin:$PATH"; '
                "claude --verbose --output-format=stream-json "
                "--permission-mode=bypassPermissions "
                f"{extra_flags_arg}"
                f"--print -- {escaped_instruction} 2>&1 </dev/null | tee "
                f"/logs/agent/claude-code.txt"
            ),
            env=env,
        )
