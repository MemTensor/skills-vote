from __future__ import annotations

import asyncio
import contextlib
import importlib
import json
import os
import re
import signal
from pathlib import Path
from typing import Any, Literal

PromptKey = Literal["user_prompt", "system_prompt"]
CLAUDE_TOOL_FLAGS = {
    "allowed_tools": "--allowedTools",
    "disallowed_tools": "--disallowedTools",
}
CLAUDE_KWARG_ENV_KEYS = {
    "max_thinking_tokens": "MAX_THINKING_TOKENS",
}


def resolve_import_path(import_path: str, **kwargs: Any) -> Any:
    if ":" not in import_path:
        raise ValueError(
            f"Import path must be in format 'module.path:name': {import_path}"
        )

    module_path, attr_name = import_path.split(":", 1)
    module = importlib.import_module(module_path)
    value = getattr(module, attr_name)
    return value(**kwargs) if callable(value) else value


def build_prompt_template(
    prompt_path: str,
    *,
    key: PromptKey,
    **kwargs: Any,
) -> str:
    prompt_bundle = resolve_import_path(prompt_path, key=key, **kwargs)
    if not isinstance(prompt_bundle, dict):
        raise TypeError("Prompt builder must return a mapping.")

    value = prompt_bundle[key]

    if not isinstance(value, str):
        raise TypeError(f"Prompt builder must return a string for {key}.")
    return value


def _get_claude_env(env_config: dict[str, Any], key: str) -> str | None:
    if key in env_config:
        value = env_config[key]
        return None if value is None else str(value)
    return os.environ.get(key)


def _get_claude_env_or(env_config: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _get_claude_env(env_config, key)
        if value:
            return value
    return None


def build_claude_env(
    *,
    model_name: str,
    env_config: dict[str, Any],
    claude_config_dir: Path | str,
) -> dict[str, str]:
    path = _get_claude_env(env_config, "PATH") or os.environ.get("PATH", "")
    local_bin = str(Path.home() / ".local" / "bin")
    env: dict[str, str] = {
        "FORCE_AUTO_BACKGROUND_TASKS": "1",
        "ENABLE_BACKGROUND_TASKS": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "IS_SANDBOX": "1",
        "PATH": f"{local_bin}:{path}" if path else local_bin,
    }

    anthropic_base_url = _get_claude_env(env_config, "ANTHROPIC_BASE_URL")
    if anthropic_base_url:
        env["ANTHROPIC_BASE_URL"] = anthropic_base_url

    anthropic_auth_token = _get_claude_env(env_config, "ANTHROPIC_AUTH_TOKEN")
    if anthropic_auth_token:
        env["ANTHROPIC_AUTH_TOKEN"] = anthropic_auth_token

    anthropic_api_key = _get_claude_env_or(
        env_config,
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
    )
    if anthropic_api_key:
        env["ANTHROPIC_API_KEY"] = anthropic_api_key

    if "ANTHROPIC_BASE_URL" in env:
        env["ANTHROPIC_MODEL"] = model_name
    else:
        env["ANTHROPIC_MODEL"] = model_name.split("/")[-1]

    for key, value in env_config.items():
        if value is not None and (key == "ANTHROPIC_MODEL" or "MODEL" not in key):
            env.setdefault(key, str(value))
    env["CLAUDE_CONFIG_DIR"] = str(claude_config_dir)
    return env


def build_claude_agent_env_config(
    *,
    env_config: dict[str, Any] | None = None,
    agent_env: dict[str, Any] | None = None,
    agent_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if env_config:
        merged.update(env_config)
    if agent_env:
        merged.update(agent_env)
    if agent_kwargs:
        for kwarg_key, env_key in CLAUDE_KWARG_ENV_KEYS.items():
            if kwarg_key in agent_kwargs:
                merged[env_key] = agent_kwargs[kwarg_key]
    return merged


def _strip_cli_quotes(value: Any) -> str:
    text = str(value)
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def build_claude_tool_args(tool_kwargs: dict[str, Any]) -> list[str]:
    args: list[str] = []
    for key, flag in CLAUDE_TOOL_FLAGS.items():
        if key in tool_kwargs:
            args.extend([flag, _strip_cli_quotes(tool_kwargs[key])])
    return args


async def run_command(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    stdin_text: str | None = None,
    log_path: Path,
    timeout_sec: float | None = None,
) -> None:
    merged_env = os.environ.copy()
    if env is not None:
        merged_env.update(env)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(cwd),
            env=merged_env,
            stdin=asyncio.subprocess.PIPE if stdin_text is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as exc:
        log_path.write_text(f"[command failed to start] {exc}\n", encoding="utf-8")
        raise RuntimeError(f"command failed to start: {args[0]}: {exc}") from exc
    input_bytes = stdin_text.encode("utf-8") if stdin_text is not None else None
    try:
        stdout, _ = await asyncio.wait_for(
            process.communicate(input_bytes),
            timeout=timeout_sec,
        )
    except TimeoutError as exc:
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        stdout, _ = await process.communicate()
        output = stdout.decode("utf-8", errors="replace")
        marker = f"\n[command timed out after {timeout_sec} seconds]\n"
        log_path.write_text(output + marker, encoding="utf-8")
        raise TimeoutError(f"command timed out after {timeout_sec} seconds") from exc

    output = stdout.decode("utf-8", errors="replace")
    log_path.write_text(output, encoding="utf-8")

    if process.returncode != 0:
        tail = "\n".join(output.splitlines()[-40:])
        raise RuntimeError(
            f"command failed with exit code {process.returncode}: {tail}"
        )


def read_session_id_from_jsonl(session_file: Path) -> str:
    with session_file.open(encoding="utf-8", errors="replace") as file:
        first_line = file.readline().strip()
    if not first_line:
        raise ValueError(f"session file is empty: {session_file}")
    payload = json.loads(first_line)
    return payload["payload"]["id"]


def find_latest_session_file_by_id(sessions_root: Path, session_id: str) -> Path:
    if not sessions_root.exists():
        raise FileNotFoundError(f"sessions directory not found: {sessions_root}")

    matching_files: list[Path] = []
    for session_file in sessions_root.rglob("*.jsonl"):
        try:
            candidate_session_id = read_session_id_from_jsonl(session_file)
        except (KeyError, ValueError, json.JSONDecodeError):
            continue
        if candidate_session_id == session_id:
            matching_files.append(session_file)

    if not matching_files:
        raise FileNotFoundError(
            f"no session file found for session_id={session_id} under {sessions_root}"
        )

    return max(matching_files, key=lambda path: path.stat().st_mtime_ns)


def read_claude_session_id_from_jsonl(session_file: Path) -> str:
    with session_file.open(encoding="utf-8", errors="replace") as file:
        for line in file:
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            session_id = payload.get("sessionId")
            if isinstance(session_id, str) and session_id:
                return session_id
    return session_file.stem


def find_latest_claude_session_file_by_id(
    sessions_root: Path,
    session_id: str,
) -> Path:
    matching_files: list[Path] = []
    for session_file in sessions_root.rglob("*.jsonl"):
        try:
            candidate_session_id = read_claude_session_id_from_jsonl(session_file)
        except (ValueError, json.JSONDecodeError):
            continue
        if candidate_session_id == session_id:
            matching_files.append(session_file)

    if not matching_files:
        raise FileNotFoundError(
            f"no Claude session file found for session_id={session_id} "
            f"under {sessions_root}"
        )

    return max(matching_files, key=lambda path: path.stat().st_mtime_ns)


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    return match.group(1).strip() if match is not None else stripped


def _loads_json_object(text: str) -> dict[str, Any]:
    stripped = _strip_json_fence(text)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            raise
        payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise TypeError("Claude output JSON must be an object.")
    return payload


def read_claude_output_payload(output_path: Path) -> dict[str, Any]:
    output = _loads_json_object(output_path.read_text(encoding="utf-8"))
    structured_output = output.get("structured_output")
    if isinstance(structured_output, dict):
        return structured_output
    if isinstance(structured_output, str):
        return _loads_json_object(structured_output)

    result = output.get("result")
    if isinstance(result, str):
        return _loads_json_object(result)
    return output
