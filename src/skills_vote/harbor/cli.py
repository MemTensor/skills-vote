from __future__ import annotations

import argparse
import importlib
import shutil
import signal
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Self, cast

import yaml
from dotenv import dotenv_values, load_dotenv
from harbor import JobResult
from harbor.cli.jobs import (
    _confirm_host_env_access,
    _format_duration,
    _handle_sigterm,
    console,
    print_job_results_tables,
)
from harbor.cli.notifications import show_registry_hint_if_first_run
from harbor.cli.utils import run_async
from harbor.environments.factory import EnvironmentFactory
from harbor.job import Job
from harbor.models.job.config import JobConfig
from harbor.models.trial.paths import TrialPaths
from harbor.models.trial.result import TrialResult
from omegaconf import OmegaConf
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

DEFAULT_ENV_FILE = Path(".env")
SKILLS_VOTE_CONFIG_NAME = "skills_vote_config.yaml"
RegisterFn = Callable[[Job, "SkillsVoteConfig"], Any]
VerifierSummaryExtractor = Literal["ctrf", "pytest_stdout", "output_json", "reward"]


def _default_verifier_summary_extractors() -> list[VerifierSummaryExtractor]:
    return ["ctrf", "pytest_stdout", "reward"]


class SkillsVoteConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    register_import_paths: list[str] = Field(default_factory=list)
    feedback_prompt_path: str | None = None
    feedback_timeout_sec: int | None = Field(default=1800, ge=1)
    evolve_prompt_path: str | None = None
    evolve_every_n_trials: int = Field(default=1, ge=1)
    evolve_timeout_sec: int | None = Field(default=None, ge=1)
    feedback_include_ground_truth: bool = False
    feedback_verifier_summary_extractors: list[VerifierSummaryExtractor] = Field(
        default_factory=_default_verifier_summary_extractors,
        min_length=1,
    )
    _register_fns: list[RegisterFn] = PrivateAttr(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def validate_register_fns_input(cls, data: Any) -> Any:
        if isinstance(data, dict) and "register_fns" in data:
            raise ValueError("register_fns cannot be provided directly.")
        return data

    @model_validator(mode="after")
    def validate_prompt_stage_dependencies(self) -> Self:
        if self.evolve_prompt_path is not None and self.feedback_prompt_path is None:
            raise ValueError("evolve_prompt_path requires feedback_prompt_path.")
        if self.evolve_prompt_path is not None and self.evolve_timeout_sec is None:
            raise ValueError("evolve_prompt_path requires evolve_timeout_sec.")
        return self

    @classmethod
    def load_from_path(cls, config_path: Path) -> Self:
        if not config_path.exists():
            return cls()

        raw_config = yaml.safe_load(config_path.read_text())
        if raw_config is None:
            raw_config = {}
        if not isinstance(raw_config, dict):
            raise TypeError("skills_vote config must be a mapping.")
        return cls.model_validate(raw_config)

    @property
    def register_fns(self) -> list[RegisterFn]:
        return self._register_fns

    def model_post_init(self, __context: Any) -> None:
        register_fns: list[RegisterFn] = []
        for import_path in self.register_import_paths:
            if ":" not in import_path:
                raise ValueError(
                    "Register import path must be in format 'module.path:function'."
                )

            module_path, register_name = import_path.split(":", 1)
            module = importlib.import_module(module_path)
            register = getattr(module, register_name)
            if not callable(register):
                raise TypeError(f"Register '{import_path}' is not callable.")
            register_fns.append(cast(RegisterFn, register))
        self._register_fns = register_fns

    def save(self, config_path: Path) -> None:
        if config_path.suffix not in {".yaml", ".yml"}:
            raise ValueError(f"Config file must be a YAML file: {config_path}")
        config_data = self.model_dump(
            mode="python",
            exclude_defaults=True,
            exclude_none=True,
        )
        if not config_data:
            return

        config_path.write_text(
            yaml.safe_dump(config_data, sort_keys=False),
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument(
        "-c",
        "--config",
        "--config-path",
        dest="config_path",
        type=Path,
        required=True,
    )
    run_parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
    )
    run_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip confirmation when tasks read environment variables from the host.",
    )
    run_parser.add_argument(
        "overrides",
        nargs="*",
        help="OmegaConf dotlist overrides, for example: job_name=my_job",
    )
    run_parser.set_defaults(handler=run_command)

    resume_parser = subparsers.add_parser("resume")
    resume_parser.add_argument(
        "-p",
        "--job-path",
        type=Path,
        required=True,
    )
    resume_parser.add_argument(
        "-f",
        "--filter-error-type",
        dest="filter_error_types",
        action="append",
    )
    resume_parser.set_defaults(handler=resume_command)

    return parser


def resolve_config(
    config_path: Path,
    overrides: list[str] | None = None,
) -> dict[str, Any]:
    resolved_now = datetime.now()
    OmegaConf.register_new_resolver(
        "now",
        lambda pattern: resolved_now.strftime(pattern),
        replace=True,
    )
    OmegaConf.register_new_resolver(
        "abspath",
        lambda path: str(Path(path).expanduser().resolve()),
        replace=True,
    )
    cfg = OmegaConf.load(config_path.expanduser().resolve())
    if not OmegaConf.is_dict(cfg):
        raise TypeError("Harbor job config must be a mapping.")
    if overrides:
        cfg = OmegaConf.merge(cfg, OmegaConf.from_dotlist(overrides))
    container = OmegaConf.to_container(cfg, resolve=True)
    if not isinstance(container, dict):
        raise TypeError("Harbor job config must be a mapping.")
    return cast(dict[str, Any], container)


def load_env_file(env_file: Path) -> set[str]:
    if env_file.exists():
        load_dotenv(env_file, override=True)
        return {key for key in dotenv_values(env_file) if key is not None}

    if env_file != DEFAULT_ENV_FILE:
        raise FileNotFoundError(f"Env file not found: {env_file}")

    return set()


def attach_registers(job: Job, skills_vote_config: SkillsVoteConfig) -> None:
    for register in skills_vote_config.register_fns:
        register(job, skills_vote_config)


def prepare_skills_workspace(skills_vote_config: SkillsVoteConfig) -> None:
    if not skills_vote_config.register_import_paths:
        return

    working_skills_dir_config = getattr(skills_vote_config, "working_skills_dir", None)
    skill_backup_dir_config = getattr(skills_vote_config, "skill_backup_dir", None)
    if working_skills_dir_config is None or skill_backup_dir_config is None:
        return

    working_skills_dir = Path(working_skills_dir_config).expanduser().resolve()
    skill_backup_dir = Path(skill_backup_dir_config).expanduser().resolve()
    seed_skills_dir = getattr(skills_vote_config, "seed_skills_dir", None)

    working_skills_dir.mkdir(parents=True, exist_ok=True)
    skill_backup_dir.mkdir(parents=True, exist_ok=True)
    if seed_skills_dir is None:
        return

    seed_skills_dir = Path(seed_skills_dir).expanduser().resolve()
    if seed_skills_dir == working_skills_dir:
        return
    if any(working_skills_dir.iterdir()):
        return
    shutil.copytree(seed_skills_dir, working_skills_dir, dirs_exist_ok=True)


def print_job_summary(job: Job, job_result) -> None:
    console.print()
    print_job_results_tables(job_result)
    console.print("[bold]Job Info[/bold]")
    console.print(
        f"Total runtime: {_format_duration(job_result.started_at, job_result.finished_at)}"
    )
    console.print(f"Results written to {job._job_result_path}")
    console.print(f"Inspect results by running `harbor view {job.job_dir.parent}`")
    console.print()


def cleanup_resume_trials(
    job_path: Path,
    filter_error_types: list[str],
) -> None:
    if not filter_error_types:
        return

    filter_error_types_set = set(filter_error_types)
    for trial_dir in job_path.iterdir():
        if not trial_dir.is_dir():
            continue

        trial_paths = TrialPaths(trial_dir)
        if not trial_paths.result_path.exists():
            continue

        trial_result = TrialResult.model_validate_json(
            trial_paths.result_path.read_text()
        )
        if (
            trial_result.exception_info is None
            or trial_result.exception_info.exception_type not in filter_error_types_set
        ):
            continue

        console.print(
            "Removing trial directory with "
            f"{trial_result.exception_info.exception_type}: {trial_dir.name}"
        )
        shutil.rmtree(trial_dir)


async def run_job(
    job_config: JobConfig,
    skills_vote_config: SkillsVoteConfig,
    *,
    explicit_env_file_keys: set[str] | None = None,
    skip_confirm: bool = False,
) -> tuple[Job, JobResult]:
    job = await Job.create(job_config)
    prepare_skills_workspace(skills_vote_config)
    _confirm_host_env_access(
        job,
        console,
        explicit_env_file_keys=explicit_env_file_keys,
        skip_confirm=skip_confirm,
    )
    attach_registers(job, skills_vote_config)
    skills_vote_config.save(job.job_dir / SKILLS_VOTE_CONFIG_NAME)
    return job, await job.run()


async def resume_job(
    job_config: JobConfig,
    skills_vote_config: SkillsVoteConfig,
) -> tuple[Job, JobResult]:
    job = await Job.create(job_config)
    prepare_skills_workspace(skills_vote_config)
    attach_registers(job, skills_vote_config)
    return job, await job.run()


def run_command(args: argparse.Namespace) -> None:
    explicit_env_file_keys = load_env_file(args.env_file)

    resolved_config = resolve_config(args.config_path, args.overrides)
    skills_vote_config = resolved_config.pop("skills_vote", {})
    if skills_vote_config is None:
        skills_vote_config = {}
    if not isinstance(skills_vote_config, dict):
        raise TypeError("skills_vote config must be a mapping.")
    skills_vote_config = SkillsVoteConfig.model_validate(skills_vote_config)
    job_config = JobConfig.model_validate(resolved_config)

    EnvironmentFactory.run_preflight(
        type=job_config.environment.type,
        import_path=job_config.environment.import_path,
    )
    signal.signal(signal.SIGTERM, _handle_sigterm)
    show_registry_hint_if_first_run(console)

    job, job_result = run_async(
        run_job(
            job_config,
            skills_vote_config,
            explicit_env_file_keys=explicit_env_file_keys,
            skip_confirm=args.yes,
        )
    )
    print_job_summary(job, job_result)


def resume_command(args: argparse.Namespace) -> None:
    if not args.job_path.exists():
        raise ValueError(f"Job directory does not exist: {args.job_path}")

    config_path = args.job_path / "config.json"
    if not config_path.exists():
        raise ValueError(f"Config file not found: {config_path}")

    filter_error_types = args.filter_error_types or ["CancelledError"]
    cleanup_resume_trials(args.job_path, filter_error_types)

    job_config = JobConfig.model_validate_json(config_path.read_text())
    skills_vote_config = SkillsVoteConfig.load_from_path(
        args.job_path / SKILLS_VOTE_CONFIG_NAME
    )

    EnvironmentFactory.run_preflight(
        type=job_config.environment.type,
        import_path=job_config.environment.import_path,
    )

    _, job_result = run_async(resume_job(job_config, skills_vote_config))
    print_job_results_tables(job_result)


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.handler(args)
