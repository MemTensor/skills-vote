from __future__ import annotations

import shlex
from collections.abc import Iterable
from contextlib import suppress
from pathlib import PurePosixPath
from typing import Any

import tomlkit
from harbor.agents.installed.codex import Codex
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from harbor.models.trial.paths import EnvironmentPaths

from skills_vote.recommend.codex import step_recommend
from skills_vote.recommend.model import RecommendConfig
from skills_vote.recommend.utils import append_recommendation_to_instruction

SYSTEM_SKILL_NAMES = [
    "skill-installer",
    "plugin-creator",
    "skill-creator",
    "openai-docs",
    "imagegen",
]


class SkillsVoteCodex(Codex):
    def __init__(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        allowed_skills = kwargs.pop("allowed_skills", None)
        allowed_plugins = kwargs.pop("allowed_plugins", None)
        self._allowed_skills = None if allowed_skills is None else set(allowed_skills)
        self._allowed_plugins = (
            None if allowed_plugins is None else set(allowed_plugins)
        )
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
        return "SkillsVoteCodex"

    async def setup(self, environment: BaseEnvironment) -> None:
        await environment.exec(command="mkdir -p /installed-agent", user="root")

        setup_dir = self.logs_dir / "setup"
        setup_dir.mkdir(parents=True, exist_ok=True)
        (setup_dir / "mode.txt").write_text(
            "skip install script; use preinstalled codex CLI in image\n",
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

    @staticmethod
    def _dedupe(values: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(values))

    async def _discover_system_skill_paths(
        self,
        environment: BaseEnvironment,
        env: dict[str, str],
    ) -> list[str]:
        result = await self.exec_as_agent(
            environment,
            command=(
                'find "$CODEX_HOME/skills/.system" "$HOME/.codex/skills/.system" '
                "-name SKILL.md -type f 2>/dev/null || true"
            ),
            env=env,
        )
        return self._dedupe(
            line.strip() for line in (result.stdout or "").splitlines() if line.strip()
        )

    async def _discover_system_plugin_names(
        self,
        environment: BaseEnvironment,
        env: dict[str, str],
    ) -> list[str]:
        result = await self.exec_as_agent(
            environment,
            command=(
                "sed -n "
                '\'s/^\\[plugins\\."\\([^"]*\\)"\\].*/\\1/p; '
                "s/^\\[plugins\\.\\([^]]*\\)\\].*/\\1/p' "
                '"$CODEX_HOME/config.toml" "$HOME/.codex/config.toml" '
                "2>/dev/null || true"
            ),
            env=env,
        )
        return self._dedupe(
            plugin_name
            for line in (result.stdout or "").splitlines()
            if (plugin_name := line.strip()) and "@openai-" in plugin_name
        )

    async def _initialize_codex_home(
        self,
        environment: BaseEnvironment,
        env: dict[str, str],
    ) -> None:
        if self._allowed_skills is None and self._allowed_plugins is None:
            return

        await self.exec_as_agent(
            environment,
            command=(
                'if [ -s "$NVM_DIR/nvm.sh" ]; then . "$NVM_DIR/nvm.sh"; fi; '
                "timeout 5s codex app-server --listen stdio:// "
                "</dev/null >/tmp/codex-app-server-init.log 2>&1 || true"
            ),
            env=env,
        )

    def _skill_is_allowed(self, skill_path: str) -> bool:
        if self._allowed_skills is None:
            return True
        path = PurePosixPath(skill_path)
        return bool(
            self._allowed_skills
            & {
                skill_path,
                path.as_posix(),
                path.parent.name,
            }
        )

    def _plugin_is_allowed(self, plugin_name: str) -> bool:
        if self._allowed_plugins is None:
            return True
        return bool(
            self._allowed_plugins
            & {
                plugin_name,
                plugin_name.split("@", 1)[0],
            }
        )

    async def _disabled_skill_paths(
        self,
        environment: BaseEnvironment,
        env: dict[str, str],
        *,
        codex_home: str | None = None,
    ) -> list[str]:
        if self._allowed_skills is None:
            return []
        skill_paths = await self._discover_system_skill_paths(environment, env)
        if not skill_paths:
            fallback_codex_home = codex_home or EnvironmentPaths.agent_dir.as_posix()
            skill_paths = [
                (
                    f"{fallback_codex_home.rstrip('/')}/skills/.system/"
                    f"{skill_name}/SKILL.md"
                )
                for skill_name in SYSTEM_SKILL_NAMES
            ]
        return [path for path in skill_paths if not self._skill_is_allowed(path)]

    async def _disabled_plugin_names(
        self,
        environment: BaseEnvironment,
        env: dict[str, str],
    ) -> list[str]:
        if self._allowed_plugins is None:
            return []
        plugin_names = await self._discover_system_plugin_names(environment, env)
        return [
            plugin_name
            for plugin_name in plugin_names
            if not self._plugin_is_allowed(plugin_name)
        ]

    def _build_config_toml(
        self,
        openai_base_url: str | None,
        disabled_skill_paths: list[str],
        disabled_plugin_names: list[str],
        trusted_project_paths: list[str] | None = None,
    ) -> str:
        doc = tomlkit.document()

        if openai_base_url:
            doc["openai_base_url"] = openai_base_url

        if self.mcp_servers:
            mcp_servers = tomlkit.table()
            for server in self.mcp_servers:
                config = tomlkit.table()
                if server.transport == "stdio":
                    cmd_parts = [server.command] + server.args if server.command else []
                    config["command"] = shlex.join(cmd_parts)
                else:
                    config["url"] = server.url
                mcp_servers[server.name] = config
            doc["mcp_servers"] = mcp_servers

        if disabled_skill_paths:
            skills = tomlkit.table()
            skill_config = tomlkit.aot()
            for skill_path in disabled_skill_paths:
                item = tomlkit.table()
                item["enabled"] = False
                item["path"] = skill_path
                skill_config.append(item)
            skills["config"] = skill_config
            doc["skills"] = skills

        if disabled_plugin_names:
            plugins = tomlkit.table()
            for plugin_name in disabled_plugin_names:
                item = tomlkit.table()
                item["enabled"] = False
                plugins[plugin_name] = item
            doc["plugins"] = plugins

        if trusted_project_paths:
            projects = tomlkit.table()
            for project_path in trusted_project_paths:
                item = tomlkit.table()
                item["trust_level"] = "trusted"
                projects[project_path] = item
            doc["projects"] = projects

        return tomlkit.dumps(doc)

    async def _upload_config_toml(
        self,
        environment: BaseEnvironment,
        config_toml: str,
    ) -> None:
        if not config_toml.strip():
            return

        config_path = self.logs_dir / "config.toml"
        config_path.write_text(config_toml, encoding="utf-8")
        target_path = (EnvironmentPaths.agent_dir / "config.toml").as_posix()
        await environment.upload_file(config_path, target_path)
        if environment.default_user is not None:
            await self.exec_as_root(
                environment,
                command=f"chown {environment.default_user} {shlex.quote(target_path)}",
            )

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        if not self.model_name:
            raise ValueError("Model name is required")

        model = self.model_name.split("/")[-1]
        cli_flags = self.build_cli_flags()
        cli_flags_arg = (cli_flags + " ") if cli_flags else ""
        main_env: dict[str, str] = {"CODEX_HOME": EnvironmentPaths.agent_dir.as_posix()}
        openai_base_url = self._get_env("OPENAI_BASE_URL")

        if self.recommend_config is not None:
            recommendation = await step_recommend(
                agent=self,
                instruction=instruction,
                environment=environment,
                recommend_config=self.recommend_config,
                main_env=main_env,
                openai_base_url=openai_base_url,
                model=model,
                cli_flags_arg=cli_flags_arg,
            )
            if recommendation is not None and recommendation.skill_names:
                instruction = append_recommendation_to_instruction(
                    instruction,
                    recommendation,
                )

        instruction = self.render_instruction(instruction)
        escaped_instruction = shlex.quote(instruction)
        auth_json_path = self._resolve_auth_json_path()

        env: dict[str, str] = {
            "CODEX_HOME": EnvironmentPaths.agent_dir.as_posix(),
        }

        if auth_json_path:
            self.logger.debug("Codex auth: using auth.json from %s", auth_json_path)
            auth_target = (EnvironmentPaths.agent_dir / "auth.json").as_posix()
            await environment.upload_file(auth_json_path, auth_target)
            if environment.default_user is not None:
                await self.exec_as_root(
                    environment,
                    command=f"chown {environment.default_user} {auth_target}",
                )
        else:
            self.logger.debug("Codex auth: using OPENAI_API_KEY")
            env["OPENAI_API_KEY"] = self._get_env("OPENAI_API_KEY") or ""

        if openai_base_url:
            env["OPENAI_BASE_URL"] = openai_base_url

        setup_command = 'mkdir -p "$CODEX_HOME"\n'
        if not auth_json_path:
            setup_command += (
                "mkdir -p /tmp/codex-secrets\n"
                "cat >/tmp/codex-secrets/auth.json <<EOF\n"
                '{\n  "OPENAI_API_KEY": "${OPENAI_API_KEY}"\n}\nEOF\n'
                'ln -sf /tmp/codex-secrets/auth.json "$CODEX_HOME/auth.json"\n'
            )

        skills_command = self._build_register_skills_command()
        if skills_command:
            setup_command += f"\n{skills_command}"

        if setup_command.strip():
            await self.exec_as_agent(
                environment,
                command=setup_command,
                env=env,
            )

        await self._initialize_codex_home(environment, env)

        disabled_skill_paths = await self._disabled_skill_paths(environment, env)
        disabled_plugin_names = await self._disabled_plugin_names(environment, env)
        config_toml = self._build_config_toml(
            openai_base_url=openai_base_url,
            disabled_skill_paths=disabled_skill_paths,
            disabled_plugin_names=disabled_plugin_names,
        )
        await self._upload_config_toml(environment, config_toml)

        try:
            await self.exec_as_agent(
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
                    "-- "
                    f"{escaped_instruction} "
                    f"2>&1 </dev/null | tee "
                    f"{EnvironmentPaths.agent_dir / self._OUTPUT_FILENAME}"
                ),
                env=env,
            )
        finally:
            with suppress(Exception):
                await self.exec_as_agent(
                    environment,
                    command='rm -rf /tmp/codex-secrets "$CODEX_HOME/auth.json" "$CODEX_HOME/tmp"',
                    env={"CODEX_HOME": EnvironmentPaths.agent_dir.as_posix()},
                )
