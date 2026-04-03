from collections.abc import AsyncIterator, Sequence
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    PermissionUpdate,
    ResultMessage,
)
from pydantic import BaseModel

PATH_KEYS = {
    "Edit": "file_path",
    "Glob": "path",
    "Grep": "path",
    "LS": "path",
    "NotebookEdit": "notebook_path",
    "Read": "file_path",
    "Write": "file_path",
}


async def structured_output_claude_agent_stream[OutputModel: BaseModel](
    *,
    system_prompt: str | None = None,
    user_prompt: str | None = None,
    cwd: str | Path | None = None,
    response_format: type[OutputModel],
    model: str,
    tools: list[str] | None = None,
    max_turns: int | None = None,
    read_roots: Sequence[str | Path] | None = None,
    write_roots: Sequence[str | Path] | None = None,
) -> AsyncIterator[object]:
    cwd_path = Path(cwd).resolve() if cwd is not None else None
    resolved_read_roots = tuple(
        Path(root).resolve()
        for root in (read_roots or ([cwd_path] if cwd_path else []))
    )
    resolved_write_roots = tuple(
        Path(root).resolve()
        for root in (write_roots or ([cwd_path] if cwd_path else []))
    )
    permission_updates = [
        PermissionUpdate(
            type="addDirectories",
            directories=[
                str(path)
                for path in dict.fromkeys(
                    path
                    for path in (cwd_path, *resolved_read_roots, *resolved_write_roots)
                    if path is not None
                )
            ],
            destination="session",
        )
    ]
    permission_updates_sent = False

    def allow_tool() -> PermissionResultAllow:
        nonlocal permission_updates_sent
        if permission_updates_sent or not permission_updates[0].directories:
            return PermissionResultAllow()
        permission_updates_sent = True
        return PermissionResultAllow(updated_permissions=permission_updates)

    async def can_use_tool(tool_name: str, tool_input: dict, _) -> object:
        path_key = PATH_KEYS.get(tool_name)
        if path_key is None:
            return allow_tool()
        raw_path = tool_input.get(path_key)
        if raw_path is None:
            if cwd_path is None:
                return PermissionResultDeny(message=f"{tool_name} requires a cwd.")
            candidate_path = cwd_path
        else:
            path = Path(raw_path)
            candidate_path = (
                cwd_path / path if cwd_path and not path.is_absolute() else path
            ).resolve()
        roots = (
            resolved_write_roots
            if tool_name in {"Edit", "NotebookEdit", "Write"}
            else resolved_read_roots
        )
        if not roots or any(candidate_path.is_relative_to(root) for root in roots):
            return allow_tool()
        return PermissionResultDeny(
            message=f"{tool_name} path outside allowed roots: {candidate_path}"
        )
    print("Running with agent, this may take a while...")
    async with ClaudeSDKClient(
        options=ClaudeAgentOptions(
            tools=tools,
            permission_mode="default",
            system_prompt=system_prompt,
            cwd=cwd,
            add_dirs=list(
                dict.fromkeys(
                    str(path)
                    for path in (*resolved_read_roots, *resolved_write_roots)
                    if path != cwd_path
                )
            ),
            setting_sources=["project"],
            model=model,
            max_turns=max_turns,
            can_use_tool=can_use_tool,
            output_format={
                "type": "json_schema",
                "schema": response_format.model_json_schema(),
            },
        )
    ) as client:
        await client.query(user_prompt or "")
        async for message in client.receive_messages():
            yield message
            if isinstance(message, ResultMessage):
                if message.structured_output is None:
                    raise RuntimeError(message.result or "Claude query failed.")
                return
    raise RuntimeError("Claude agent finished without structured output.")
