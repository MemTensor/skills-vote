from __future__ import annotations

import fnmatch
import glob
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from config_validation import (
    contains_placeholder_path,
    require_supported_skill_library_fields,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = PROJECT_ROOT / ".skills"
SKILL_FILE_NAME = "SKILL.md"
MANAGED_ALIAS_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-[0-9a-f]{8}$")


@dataclass(slots=True)
class SkillAlias:
    alias: str
    source_dir: Path
    source_skill_md: Path
    matched_paths: list[Path] = field(default_factory=list)


@dataclass(slots=True)
class SyncResult:
    ok: bool
    skills_count: int = 0
    aliases: list[SkillAlias] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _collect_patterns(values: object) -> list[str]:
    if not isinstance(values, list | tuple):
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def _normalize_scan_pattern(base_dir: Path, raw_pattern: str) -> str:
    path = Path(str(raw_pattern).strip()).expanduser()
    if path.is_absolute():
        return str(path)
    return str(base_dir / path)


def _build_scan_include_patterns(
    base_dir: Path, skill_library: dict[str, Any]
) -> list[str]:
    include_patterns = _collect_patterns(skill_library.get("include"))
    return [_normalize_scan_pattern(base_dir, pattern) for pattern in include_patterns]


def _matches_any(path_text: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path_text, pattern) for pattern in patterns)


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _should_scan_path(
    raw_skill_path: Path,
    canonical_skill_path: Path,
    skill_library: dict[str, Any],
) -> bool:
    if raw_skill_path.name != SKILL_FILE_NAME:
        return False
    if _is_under(raw_skill_path.absolute(), SKILLS_ROOT):
        return False
    if _is_under(canonical_skill_path, SKILLS_ROOT):
        return False
    excludes = _collect_patterns(skill_library.get("exclude"))
    if not excludes:
        return True
    return not (
        _matches_any(raw_skill_path.absolute().as_posix(), excludes)
        or _matches_any(canonical_skill_path.as_posix(), excludes)
    )


def discover_skill_aliases(
    config: dict[str, Any], config_path: Path
) -> list[SkillAlias]:
    skill_library = config.get("skill_library")
    if not isinstance(skill_library, dict):
        raise ValueError("skill_library must be a YAML object")
    require_supported_skill_library_fields(skill_library)

    include_patterns = _build_scan_include_patterns(config_path.parent, skill_library)
    include_patterns = [pattern for pattern in include_patterns if pattern.strip()]
    if not include_patterns:
        raise ValueError("skill_library.include must contain at least one glob pattern")
    if any(contains_placeholder_path(pattern) for pattern in include_patterns):
        raise ValueError("Replace placeholder paths in skill_library.include")

    aliases_by_root: dict[Path, SkillAlias] = {}
    for include_pattern in include_patterns:
        for matched_path in glob.iglob(include_pattern, recursive=True):
            raw_skill_path = Path(matched_path)
            try:
                canonical_skill_md = raw_skill_path.resolve()
            except OSError:
                continue
            if not canonical_skill_md.is_file():
                continue
            if not _should_scan_path(raw_skill_path, canonical_skill_md, skill_library):
                continue

            canonical_skill_root = canonical_skill_md.parent
            alias = aliases_by_root.get(canonical_skill_root)
            if alias is None:
                alias = SkillAlias(
                    alias=_build_alias(canonical_skill_root, canonical_skill_md),
                    source_dir=canonical_skill_root,
                    source_skill_md=canonical_skill_md,
                )
                aliases_by_root[canonical_skill_root] = alias
            alias.matched_paths.append(raw_skill_path.absolute())

    return sorted(aliases_by_root.values(), key=lambda item: item.alias)


def _read_skill_name(skill_md: Path) -> str:
    try:
        raw_text = skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return skill_md.parent.name

    stripped = raw_text.lstrip()
    if not stripped.startswith("---"):
        return skill_md.parent.name

    lines = stripped.splitlines()
    try:
        end_index = lines[1:].index("---") + 1
    except ValueError:
        return skill_md.parent.name

    try:
        frontmatter = yaml.safe_load("\n".join(lines[1:end_index])) or {}
    except yaml.YAMLError:
        return skill_md.parent.name

    if isinstance(frontmatter, dict):
        for key in ("name", "title"):
            value = str(frontmatter.get(key) or "").strip()
            if value:
                return value
    return skill_md.parent.name


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "skill"


def _build_alias(skill_root: Path, skill_md: Path) -> str:
    slug = _slugify(_read_skill_name(skill_md))
    hash8 = hashlib.sha256(str(skill_root).encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{hash8}"


def _safe_resolve_symlink(path: Path) -> Path | None:
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return None


def _preflight_alias_paths(desired: dict[str, SkillAlias]) -> list[str]:
    errors: list[str] = []
    for alias in desired:
        alias_path = SKILLS_ROOT / alias
        if alias_path.exists() and not alias_path.is_symlink():
            errors.append(f"Alias path is occupied by a non-symlink: {alias_path}")
    return errors


def _remove_stale_managed_symlinks(
    desired: dict[str, SkillAlias],
    warnings: list[str],
) -> None:
    if not SKILLS_ROOT.exists():
        return

    for entry in SKILLS_ROOT.iterdir():
        if not entry.is_symlink():
            warnings.append(f"Leaving unmanaged non-symlink in .skills/: {entry.name}")
            continue
        if not MANAGED_ALIAS_RE.fullmatch(entry.name):
            warnings.append(f"Leaving unmanaged symlink in .skills/: {entry.name}")
            continue

        desired_alias = desired.get(entry.name)
        resolved_target = _safe_resolve_symlink(entry)
        if desired_alias is None or resolved_target != desired_alias.source_dir:
            entry.unlink()


def _create_or_fix_aliases(desired: dict[str, SkillAlias]) -> None:
    for alias, skill_alias in desired.items():
        alias_path = SKILLS_ROOT / alias
        if alias_path.is_symlink():
            resolved_target = _safe_resolve_symlink(alias_path)
            if resolved_target == skill_alias.source_dir:
                continue
            alias_path.unlink()
        alias_path.symlink_to(skill_alias.source_dir, target_is_directory=True)


def sync_skill_namespace(config: dict[str, Any], config_path: Path) -> SyncResult:
    warnings: list[str] = []
    try:
        aliases = discover_skill_aliases(config, config_path)
        desired = {alias.alias: alias for alias in aliases}
        if len(desired) != len(aliases):
            raise ValueError(
                "Alias collision detected while building .skills namespace"
            )

        SKILLS_ROOT.mkdir(parents=True, exist_ok=True)
        errors = _preflight_alias_paths(desired)
        if errors:
            return SyncResult(
                ok=False,
                skills_count=len(aliases),
                aliases=aliases,
                warnings=warnings,
                errors=errors,
            )

        _remove_stale_managed_symlinks(desired, warnings)
        _create_or_fix_aliases(desired)
        return SyncResult(
            ok=True,
            skills_count=len(aliases),
            aliases=aliases,
            warnings=warnings,
        )
    except Exception as exc:
        return SyncResult(ok=False, warnings=warnings, errors=[str(exc)])
