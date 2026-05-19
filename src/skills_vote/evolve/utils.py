from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from skills_vote.feedback.model import Subtask


def dump_subtask_without_ground_truth(subtask: Subtask) -> dict[str, Any]:
    payload = subtask.model_dump()
    payload.pop("ground_truth_path", None)
    return payload


# 为了防止大模型创建的 skill_dir 路径有问题
def resolve_created_skill_dir(
    create_dir: Path,
    skill_dir_path: str,
) -> Path | None:
    raw_path = skill_dir_path.strip()
    if not raw_path:
        return None

    create_root = create_dir.resolve()
    candidate_path = Path(raw_path)
    if candidate_path.is_absolute():
        resolved_path = candidate_path.resolve()
        try:
            relative_to_create_root = resolved_path.relative_to(create_root)
        except ValueError:
            return None
        if len(relative_to_create_root.parts) != 1:
            return None
        return resolved_path

    normalized_parts = tuple(
        part for part in candidate_path.parts if part not in {"", "."}
    )
    if not normalized_parts:
        return None
    if any(part == ".." for part in normalized_parts):
        return None

    normalized_path = Path(*normalized_parts)
    if normalized_path.parts[0] == "create":
        if len(normalized_path.parts) != 2:
            return None
        resolved_path = create_dir.parent / normalized_path
    else:
        if len(normalized_path.parts) != 1:
            return None
        resolved_path = create_dir / normalized_path

    if not resolved_path.resolve().is_relative_to(create_root):
        return None

    return resolved_path


def copy_created_skill_dir(
    *,
    create_dir: Path,
    request_dir: Path,
    skill_dir_path: str,
    working_skills_dir: Path,
) -> bool:
    created_skill_dir = resolve_created_skill_dir(create_dir, skill_dir_path)
    if created_skill_dir is None:
        _write_skipped_created_skill(
            request_dir,
            skill_dir_path=skill_dir_path,
            reason="resolved skill_dir_path is not a direct child of create_dir",
        )
        return False

    if not created_skill_dir.is_dir():
        _write_skipped_created_skill(
            request_dir,
            skill_dir_path=skill_dir_path,
            resolved_path=created_skill_dir,
            reason="resolved skill directory does not exist",
        )
        return False

    destination = working_skills_dir / created_skill_dir.name
    shutil.rmtree(destination, ignore_errors=True)
    try:
        shutil.copytree(created_skill_dir, destination, dirs_exist_ok=True)
    except FileNotFoundError:
        shutil.rmtree(destination, ignore_errors=True)
        _write_skipped_created_skill(
            request_dir,
            skill_dir_path=skill_dir_path,
            resolved_path=created_skill_dir,
            reason="resolved skill directory disappeared before copy",
        )
        return False

    return True


def _write_skipped_created_skill(
    request_dir: Path,
    *,
    skill_dir_path: str,
    reason: str,
    resolved_path: Path | None = None,
) -> None:
    fields = [
        f"reason={reason}",
        f"skill_dir_path={skill_dir_path}",
    ]
    if resolved_path is not None:
        fields.append(f"resolved_path={resolved_path}")
    with (request_dir / "skipped_created_skills.txt").open(
        "a",
        encoding="utf-8",
    ) as file:
        file.write("Skip created skill because " + "; ".join(fields) + "\n")
