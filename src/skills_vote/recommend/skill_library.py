from __future__ import annotations

import json
import shlex
from pathlib import Path, PurePosixPath


def build_install_all_skills_command(
    *,
    skills_dir: str,
    install_skills_dir: str | None,
    agent_home_env_var: str,
    skills_vote_library_manifest: str | None,
) -> str:
    target = f'"${agent_home_env_var}/skills"'
    if skills_vote_library_manifest is None:
        return (
            f"mkdir -p {target}\n"
            f"cp -R {shlex.quote(skills_dir.rstrip('/') + '/.')} {target}"
        )

    source_root = install_skills_dir or skills_dir
    return (
        f"mkdir -p {target}\n"
        f"find {shlex.quote(source_root.rstrip('/'))} "
        "-mindepth 3 -maxdepth 3 -name SKILL.md -type f -print "
        "2>/dev/null | sort | while IFS= read -r skill_file; do\n"
        '  skill_dir="$(dirname "$skill_file")"\n'
        f'  cp -R "$skill_dir" {target}/\n'
        "done"
    )


def load_manifest_mapping(
    manifest_path: Path,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    try:
        with manifest_path.open(encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                item = json.loads(line)
                skill_name = item["skill_name"]
                path = item["path"]
                if skill_name not in mapping:
                    mapping[skill_name] = path
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"failed to read skill manifest: {manifest_path}") from exc
    return mapping


def _container_skill_path(*, manifest_path: str, install_skills_dir: str) -> str:
    path = PurePosixPath(manifest_path)
    skill_path = path.parent if path.name == "SKILL.md" else path
    return (
        f"{install_skills_dir.rstrip('/')}/{skill_path.parent.name}/{skill_path.name}"
    )


def build_install_selected_skills_command(
    *,
    skill_names: list[str],
    skills_dir: str,
    install_skills_dir: str | None,
    agent_home_env_var: str,
    skills_vote_library_manifest: str | None,
) -> str:
    target = f'"${agent_home_env_var}/skills"'
    commands = [f"mkdir -p {target}"]

    mapping: dict[str, str] = {}
    if skills_vote_library_manifest is not None:
        mapping = load_manifest_mapping(Path(skills_vote_library_manifest).expanduser())

    for skill_name in skill_names:
        if skills_vote_library_manifest is not None:
            source_path = mapping.get(skill_name)
            if source_path is None:
                raise RuntimeError(f"recommended skill not found: {skill_name}")
            source = _container_skill_path(
                manifest_path=source_path,
                install_skills_dir=install_skills_dir or skills_dir,
            )
        else:
            source = f"{skills_dir.rstrip('/')}/{skill_name}"
        commands.append(f"cp -R {shlex.quote(source)} {target}/")

    return "\n".join(commands)
