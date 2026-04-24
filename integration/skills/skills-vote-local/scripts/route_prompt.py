#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from cli_common import resolve_config_path

SKILL_ROOT = Path(__file__).resolve().parent.parent
ROUTES_DIR = SKILL_ROOT / "doc" / "routes"
HANDOFF_PATH = SKILL_ROOT / "doc" / "handoff.md"
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
    config_path: Path
    config_loaded: bool
    warnings: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True, choices=("main", "subagent"))
    parser.add_argument(
        "--fallback",
        action="store_true",
        help="Render the main-agent fallback route when subagent delegation is unavailable.",
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
        f'Falling back to "{DEFAULT_MODE}". '
        'Note: "delegate_to_subagent" is deprecated and is not an alias.'
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
    routing = _section(config, "routing")
    context = _section(config, "retrieval_context")
    configured_mode, resolved_mode = _resolve_mode(routing, warnings)
    configured_max_passes = _resolve_max_passes(routing, warnings)
    retrieval_context = _resolve_context(context, warnings)
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

    return RouterConfig(
        configured_mode=configured_mode,
        resolved_mode=resolved_mode,
        configured_max_passes=configured_max_passes,
        effective_max_passes=effective_max_passes,
        retrieval_context=retrieval_context,
        config_path=config_path,
        config_loaded=config_loaded,
        warnings=warnings,
    )


def _render_header(role: str, config: RouterConfig, *, fallback: bool) -> str:
    warnings = config.warnings or ["none"]
    warning_lines = "\n".join(f"- {warning}" for warning in warnings)
    return "\n".join(
        [
            "# skills-vote-local route",
            "",
            f"role: {role}",
            f"fallback: {str(fallback).lower()}",
            f"configured_mode: {config.configured_mode}",
            f"resolved_mode: {config.resolved_mode}",
            f"retrieval_context: {config.retrieval_context}",
            f"configured_max_passes: {config.configured_max_passes}",
            f"effective_max_passes: {config.effective_max_passes}",
            f"skill_root: {SKILL_ROOT}",
            f"config_path: {config.config_path}",
            f"config_loaded: {str(config.config_loaded).lower()}",
            "warnings:",
            warning_lines,
            "",
        ]
    )


def _workflow_template_path(role: str, mode: str) -> Path:
    if role == "main":
        return ROUTES_DIR / "role_main" / f"{mode}.md"
    if mode.endswith("single_pass"):
        return ROUTES_DIR / "role_subagent" / "single_pass.md"
    return ROUTES_DIR / "role_subagent" / "multi_pass.md"


def _read_template(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _recommend_command() -> str:
    return 'uv run -qq python scripts/recommend.py \\\n  -q "<rewritten query>"'


def _template_values(config: RouterConfig) -> dict[str, str]:
    return {
        "skill_root": str(SKILL_ROOT),
        "handoff_path": str(HANDOFF_PATH),
        "recommend_command": _recommend_command(),
        "max_passes": str(config.configured_max_passes),
        "effective_max_passes": str(config.effective_max_passes),
        "resolved_mode": config.resolved_mode,
        "retrieval_context": config.retrieval_context,
    }


def _render_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


def _find_unresolved_placeholders(rendered_body: str) -> list[str]:
    return sorted(set(PLACEHOLDER_RE.findall(rendered_body)))


def _should_render_retrieval_context(role: str, mode: str, *, fallback: bool) -> bool:
    if fallback:
        return True
    return role != "main" or not mode.startswith("subagent_")


def _should_render_debug_notes(role: str, mode: str, *, fallback: bool) -> bool:
    return _should_render_retrieval_context(role, mode, fallback=fallback)


FALLBACK_PREAMBLE = """## Fallback mode

You are the main agent running fallback because subagent delegation is unavailable.
Follow the equivalent main-agent workflow below.
Preserve the configured single-pass or multi-pass behavior and the configured retrieval_context policy.
Do not read raw route templates directly.
Do not read doc/usage_reference.md unless route_prompt.py itself cannot run."""

MISSING_CONFIG_PROMPT = """## Missing default config

Default config/config.yaml was not found or could not be loaded.

Do not run recommend.py yet.

Local skill retrieval is not configured until config/config.yaml exists and can be loaded.

Next steps:

1. Create config/config.yaml from config/config.yaml.example.
2. Configure skill_library.include to point at one or more skill libraries.
3. Then rerun:

```bash
uv run -qq python scripts/route_prompt.py --role main
```

If you are a subagent, return no selected skills and explain that retrieval is unavailable because the default config is missing.
Example response shape: `{"skills": [], "reason": "Default config/config.yaml was not found, so local skill retrieval is not configured yet."}`."""


def render_route_prompt(
    role: str, config: RouterConfig, *, fallback: bool = False
) -> str:
    values = _template_values(config)
    workflow_mode = (
        _main_equivalent_mode(config.resolved_mode)
        if fallback
        else config.resolved_mode
    )
    body_parts = []
    if not config.config_loaded:
        body_parts.append(MISSING_CONFIG_PROMPT)
    else:
        if fallback:
            body_parts.append(FALLBACK_PREAMBLE)
        body_parts.append(
            _render_template(
                _read_template(_workflow_template_path(role, workflow_mode)), values
            )
        )
        if _should_render_retrieval_context(
            role, config.resolved_mode, fallback=fallback
        ):
            body_parts.append(
                _render_template(
                    _read_template(
                        ROUTES_DIR / "context" / f"{config.retrieval_context}.md"
                    ),
                    values,
                )
            )
        if _should_render_debug_notes(role, config.resolved_mode, fallback=fallback):
            body_parts.append(
                _render_template(
                    _read_template(ROUTES_DIR / "common" / "debug_and_config_notes.md"),
                    values,
                )
            )
        if role == "subagent":
            body_parts.append(
                _read_template(ROUTES_DIR / "common" / "subagent_json_schema.md")
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
