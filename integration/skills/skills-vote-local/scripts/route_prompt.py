#!/usr/bin/env python3
# /// script
# dependencies = ["PyYAML>=6.0.3,<7.0.0"]
# ///

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import prompt
import yaml
from cli_common import resolve_config_path
from config_validation import (
    DEFAULT_RETRIEVAL_METHOD,
    find_unsupported_config_fields,
    resolve_retrieval_method,
)
from sync_skills import PROJECT_ROOT, SKILLS_ROOT, SyncResult, sync_skill_namespace

SKILL_ROOT = PROJECT_ROOT
HANDOFF_PATH = SKILL_ROOT / "docs" / "handoff.md"
DEFAULT_MODE = "subagent_multi_pass"
DEFAULT_MAX_PASSES = 3
DEFAULT_CONTEXT = "recommend_plus_skill_md"
PLACEHOLDER_RE = re.compile(r"{[a-zA-Z_][a-zA-Z0-9_]*}")
ALLOWED_MODES = {
    "main_single_pass",
    "main_multi_pass",
    "subagent_single_pass",
    "subagent_multi_pass",
}
ALLOWED_CONTEXTS = {
    "recommend_only",
    "recommend_plus_skill_md",
    "recommend_plus_skill_dir",
}


@dataclass(slots=True)
class RouterConfig:
    configured_mode: str
    resolved_mode: str
    configured_max_passes: int
    effective_max_passes: int
    retrieval_context: str
    retrieval_method: str
    config_path: Path
    config_loaded: bool
    config_errors: list[str]
    sync_result: SyncResult | None
    warnings: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True, choices=("main", "subagent"))
    parser.add_argument(
        "--fallback",
        action="store_true",
        help=(
            "Render the main-agent fallback route when the configured subagent "
            "delegation route cannot be used in this turn."
        ),
    )
    args = parser.parse_args()
    if args.fallback and args.role != "main":
        parser.error("--fallback can only be used with --role main")
    return args


def _read_config(config_path: Path, warnings: list[str]) -> tuple[dict[str, Any], bool]:
    if not config_path.exists():
        warnings.append(
            f"Config file not found: {config_path}. Using routing defaults only."
        )
        return {}, False

    try:
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        warnings.append(
            f"Could not parse config file {config_path}: {exc}. Using routing defaults only."
        )
        return {}, False

    if not isinstance(loaded, dict):
        warnings.append(
            "Config top-level value is not a mapping. Using routing defaults only."
        )
        return {}, False

    unsupported_fields = find_unsupported_config_fields(loaded)
    if unsupported_fields:
        warnings.append(
            "Unsupported config field(s): "
            + ", ".join(unsupported_fields)
            + ". Remove or rename unsupported fields in configs/config.yaml."
        )
        return loaded, True

    return loaded, True


def _section(config: dict[str, Any], key: str) -> dict[str, Any]:
    value = config.get(key)
    return value if isinstance(value, dict) else {}


def _resolve_mode(routing: dict[str, Any], warnings: list[str]) -> tuple[str, str]:
    configured_mode = str(routing.get("mode", DEFAULT_MODE))
    if configured_mode in ALLOWED_MODES:
        return configured_mode, configured_mode

    warnings.append(
        f'Unsupported routing.mode "{configured_mode}". '
        f'Falling back to "{DEFAULT_MODE}".'
    )
    return configured_mode, DEFAULT_MODE


def _resolve_max_passes(routing: dict[str, Any], warnings: list[str]) -> int:
    raw_max_passes = routing.get("max_passes", DEFAULT_MAX_PASSES)
    try:
        if isinstance(raw_max_passes, bool):
            raise ValueError("booleans are not valid pass counts")
        max_passes = int(raw_max_passes)
    except (TypeError, ValueError):
        warnings.append(
            f"Invalid routing.max_passes {raw_max_passes!r}. "
            f"Falling back to {DEFAULT_MAX_PASSES}."
        )
        return DEFAULT_MAX_PASSES

    if max_passes < 1:
        warnings.append(
            f"Invalid routing.max_passes {raw_max_passes!r}. "
            f"Falling back to {DEFAULT_MAX_PASSES}."
        )
        return DEFAULT_MAX_PASSES
    return max_passes


def _resolve_context(context: dict[str, Any], warnings: list[str]) -> str:
    configured_context = str(context.get("mode", DEFAULT_CONTEXT))
    if configured_context in ALLOWED_CONTEXTS:
        return configured_context

    warnings.append(
        f'Unsupported retrieval_context.mode "{configured_context}". '
        f'Falling back to "{DEFAULT_CONTEXT}".'
    )
    return DEFAULT_CONTEXT


def _resolve_retrieval_method(retrieval: dict[str, Any], warnings: list[str]) -> str:
    configured_method, warning = resolve_retrieval_method(
        retrieval.get("method", DEFAULT_RETRIEVAL_METHOD)
    )
    if warning is not None:
        warnings.append(warning)
    return configured_method


def _main_equivalent_mode(mode: str) -> str:
    if mode == "subagent_single_pass":
        return "main_single_pass"
    if mode == "subagent_multi_pass":
        return "main_multi_pass"
    return mode


def load_router_config(role: str, *, fallback: bool = False) -> RouterConfig:
    config_path = resolve_config_path(None)
    warnings: list[str] = []
    config, config_loaded = _read_config(config_path, warnings)
    config_errors = (
        find_unsupported_config_fields(config) if config_loaded and config else []
    )
    routing = _section(config, "routing")
    context = _section(config, "retrieval_context")
    retrieval = _section(config, "retrieval")
    configured_mode, resolved_mode = _resolve_mode(routing, warnings)
    configured_max_passes = _resolve_max_passes(routing, warnings)
    retrieval_context = _resolve_context(context, warnings)
    retrieval_method = _resolve_retrieval_method(retrieval, warnings)
    effective_mode = _main_equivalent_mode(resolved_mode) if fallback else resolved_mode
    if effective_mode.endswith("single_pass"):
        effective_max_passes = 1
    else:
        effective_max_passes = configured_max_passes

    if role == "subagent" and resolved_mode.startswith("main_"):
        pass_kind = (
            "single-pass" if resolved_mode.endswith("single_pass") else "multi-pass"
        )
        warnings.append(
            f"routing.mode is {resolved_mode}, so a parent agent normally should not "
            f"delegate. Since this prompt is for a subagent, rendering the equivalent "
            f"{pass_kind} retrieval workflow."
        )

    sync_result = None
    if config_loaded and not config_errors and retrieval_method == "agentic_search":
        sync_result = sync_skill_namespace(config, config_path)
        warnings.extend(sync_result.warnings)
        warnings.extend(sync_result.errors)

    return RouterConfig(
        configured_mode=configured_mode,
        resolved_mode=resolved_mode,
        configured_max_passes=configured_max_passes,
        effective_max_passes=effective_max_passes,
        retrieval_context=retrieval_context,
        retrieval_method=retrieval_method,
        config_path=config_path,
        config_loaded=config_loaded,
        config_errors=config_errors,
        sync_result=sync_result,
        warnings=warnings,
    )


def _render_header(role: str, config: RouterConfig, *, fallback: bool) -> str:
    lines = [
        "# skills-vote-local route",
        "",
        f"role: {role}",
        f"fallback: {str(fallback).lower()}",
        f"routing.mode: {config.resolved_mode}",
        f"retrieval.method: {config.retrieval_method}",
        f"retrieval_context.mode: {config.retrieval_context}",
        f"max_passes: {config.effective_max_passes}",
    ]

    if not config.config_loaded:
        lines.append("config: missing")
    elif config.config_errors:
        lines.append("config: invalid")

    if config.sync_result is not None:
        sync_state = "ok" if config.sync_result.ok else "failed"
        lines.extend(
            [
                "skills_root: ./.skills",
                f"skills_sync: {sync_state}",
                f"skills_count: {config.sync_result.skills_count}",
            ]
        )

    if config.warnings:
        lines.append("warnings:")
        lines.extend(f"- {warning}" for warning in config.warnings)
    else:
        lines.append("warnings: none")

    lines.append("")
    return "\n".join(lines)


def _recommend_command() -> str:
    return prompt.render_recommend_command()


def _single_pass_mode(mode: str) -> bool:
    return mode.endswith("single_pass")


def _find_unresolved_placeholders(rendered_body: str) -> list[str]:
    return sorted(set(PLACEHOLDER_RE.findall(rendered_body)))


def _should_render_retrieval_context(role: str, mode: str, *, fallback: bool) -> bool:
    if fallback:
        return True
    return role != "main" or not mode.startswith("subagent_")


def _should_render_debug_notes(role: str, mode: str, *, fallback: bool) -> bool:
    return _should_render_retrieval_context(role, mode, fallback=fallback)


def _render_agentic_workflow(role: str, config: RouterConfig, *, fallback: bool) -> str:
    effective_mode = (
        _main_equivalent_mode(config.resolved_mode)
        if fallback
        else config.resolved_mode
    )
    single_pass = effective_mode.endswith("single_pass")
    delegated_main = (
        role == "main" and not fallback and config.resolved_mode.startswith("subagent_")
    )
    body_parts = []
    if role == "subagent":
        body_parts.append(prompt.render_agentic_subagent_output_requirement())
    if delegated_main:
        body_parts.append(
            prompt.render_agentic_delegated_policy_summary(
                retrieval_context=config.retrieval_context,
            )
        )
    else:
        body_parts.append(
            prompt.render_agentic_common_policy(
                retrieval_context=config.retrieval_context,
                skills_root=str(SKILLS_ROOT),
            )
        )
    if config.sync_result is not None and config.sync_result.skills_count == 0:
        body_parts.append(prompt.render_agentic_zero_skills_note())

    if delegated_main:
        body_parts.append(
            prompt.render_agentic_main_delegated(
                handoff_path=str(HANDOFF_PATH),
                max_passes=config.configured_max_passes,
                single_pass=single_pass,
            )
        )
        return "\n\n".join(body_parts)

    if role == "subagent":
        body_parts.append(
            prompt.render_agentic_subagent(
                single_pass=single_pass,
                max_passes=config.configured_max_passes,
            )
        )
        body_parts.append(
            prompt.render_agentic_search_protocol(
                max_passes=config.configured_max_passes,
                single_pass=single_pass,
            )
        )
        body_parts.append(prompt.render_agentic_search_examples())
        body_parts.append(prompt.render_agentic_debug_notes())
        body_parts.append(prompt.render_agentic_subagent_json_schema())
        return "\n\n".join(body_parts)

    if fallback:
        body_parts.append(prompt.render_fallback_preamble())
    body_parts.append(
        prompt.render_agentic_main_direct(
            single_pass=single_pass,
            max_passes=config.configured_max_passes,
        )
    )
    body_parts.append(
        prompt.render_agentic_search_protocol(
            max_passes=config.configured_max_passes,
            single_pass=single_pass,
        )
    )
    body_parts.append(prompt.render_agentic_search_examples())
    body_parts.append(prompt.render_agentic_debug_notes())
    return "\n\n".join(body_parts)


def _render_vector_search_workflow(
    role: str, config: RouterConfig, *, fallback: bool
) -> str:
    effective_mode = (
        _main_equivalent_mode(config.resolved_mode)
        if fallback
        else config.resolved_mode
    )
    single_pass = _single_pass_mode(effective_mode)
    body_parts = []
    if fallback:
        body_parts.append(prompt.render_fallback_preamble())

    if role == "main" and not fallback and config.resolved_mode.startswith("subagent_"):
        body_parts.append(
            prompt.render_vector_search_main_delegated(
                handoff_path=str(HANDOFF_PATH),
                max_passes=config.configured_max_passes,
                single_pass=single_pass,
            )
        )
        return "\n\n".join(body_parts)

    if role == "subagent":
        if single_pass:
            body_parts.append(
                prompt.render_vector_search_subagent_single_pass(
                    skill_root=str(SKILL_ROOT)
                )
            )
        else:
            body_parts.append(
                prompt.render_vector_search_subagent_multi_pass(
                    skill_root=str(SKILL_ROOT),
                    max_passes=config.configured_max_passes,
                )
            )
    elif single_pass:
        body_parts.append(
            prompt.render_vector_search_main_single_pass(skill_root=str(SKILL_ROOT))
        )
    else:
        body_parts.append(
            prompt.render_vector_search_main_multi_pass(
                skill_root=str(SKILL_ROOT),
                max_passes=config.configured_max_passes,
            )
        )

    if _should_render_retrieval_context(role, config.resolved_mode, fallback=fallback):
        body_parts.append(
            prompt.render_retrieval_context_policy(config.retrieval_context)
        )
    if _should_render_debug_notes(role, config.resolved_mode, fallback=fallback):
        body_parts.append(prompt.render_vector_search_debug_notes())
    if role == "subagent":
        body_parts.append(prompt.render_vector_search_subagent_json_schema())
    return "\n\n".join(body_parts)


def render_route_prompt(
    role: str, config: RouterConfig, *, fallback: bool = False
) -> str:
    body_parts = []
    if not config.config_loaded:
        body_parts.append(prompt.render_missing_config_prompt())
    elif config.config_errors:
        body_parts.append(
            prompt.render_invalid_config_prompt(config_errors=config.config_errors)
        )
    elif config.retrieval_method == "agentic_search" and (
        config.sync_result is None or not config.sync_result.ok
    ):
        body_parts.append(
            prompt.render_agentic_sync_failed_prompt(skills_root=str(SKILLS_ROOT))
        )
    elif config.retrieval_method == "agentic_search":
        body_parts.append(_render_agentic_workflow(role, config, fallback=fallback))
    else:
        body_parts.append(
            _render_vector_search_workflow(role, config, fallback=fallback)
        )
    rendered_body = "\n\n".join(body_parts)
    unresolved_placeholders = _find_unresolved_placeholders(rendered_body)
    if unresolved_placeholders:
        config.warnings.append(
            "Unresolved template placeholders: "
            + ", ".join(unresolved_placeholders)
            + "."
        )
    return (
        "\n\n".join(
            [_render_header(role, config, fallback=fallback), rendered_body]
        ).rstrip()
        + "\n"
    )


def main() -> None:
    args = parse_args()
    config = load_router_config(args.role, fallback=args.fallback)
    print(render_route_prompt(args.role, config, fallback=args.fallback), end="")


if __name__ == "__main__":
    main()
