---
name: skills-vote
description: Find the most relevant external agent skills for the current task, then submit grounded feedback about which skills were actually used and useful in the same session. Whenever you start a task, use this skill first.
metadata:
  version: "1.0"
---

# Skill Discovery And Feedback

Read only this file first. Do not read `scripts/` or any other files in this skill unless this file or a script output explicitly tells you to do so.

Use this skill in two moments:

- Before you fetch or invoke external skills for the current task.
- After the task is effectively done, to report what skills were actually useful.

Skip this skill if you are not considering any external skills at all.

All paths mentioned in this file are relative to this skill root. `cd` to this root directory before running any command here.

## Preconditions

Before using this skill, ensure that:

- `SKILLS_VOTE_API_KEY` is set in the environment
- `uv` is installed and available on `PATH`
- the runtime can execute local scripts with `uv run`
- `GITHUB_TOKEN` or `GH_TOKEN` may be needed later if GitHub blocks skill downloads because the repo is private or rate-limited

1. Confirm `SKILLS_VOTE_API_KEY` is set:
   - macOS or Linux: `bash scripts/check_api_key.sh`
   - Windows PowerShell: `powershell -ExecutionPolicy Bypass -File scripts/check_api_key.ps1`
2. Verify that `uv` is installed: `uv -V`
3. If `uv` is missing, install it from the [official docs](https://docs.astral.sh/uv/getting-started/installation/).
   - macOS or Linux:
     - If curl is available, `curl -LsSf https://astral.sh/uv/install.sh | sh`
     - Otherwise `wget -qOhttps://astral.sh/uv/install.sh | sh`
   - Windows PowerShell: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
4. Verify again: `uv -V`

## Recommend

### Request schema

`recommend.py` accepts one JSON object with these fields:

`query` (`str`): A standalone, explicit, and retrieval-optimized description of the user's task. Rewrite the original request to improve clarity, specificity, and usefulness for search, retrieval, or downstream planning. When appropriate, include reasonable implied constraints, likely substeps, supporting tasks, or candidate approaches that are directly relevant to completing the task. Favor expansions that make the task easier to retrieve against or execute, but avoid adding weakly supported assumptions, unrelated details, or excessive verbosity. For example, if the original query is "make a video," the rewritten query may expand it into a fuller task such as planning the content, identifying the audience, drafting a script, preparing slides, designing charts or visual assets, considering animation tools like Manim, recording narration, editing the final video, and rehearsing delivery.
- `client_name` (`Literal["codex", "codex-app", "claude-code", "cursor", "gemini-cli", "openclaw-cli", "opencode"] | None = None`): Name of this agent. If unknown/unverified or not listed, omit the field or return `null`.
- `client_version` (`str | None = None`): Version of this agent. Prefer the exact version string reported by the client itself. If unknown/unverified, omit the field or return `null`.
- `download_dir` (`str = ".skills_vote/"`): Directory to download recommended skills into. Relative paths are resolved from the current working directory. The path must be writable from the current runtime.

### Example

Before sending the request, try to identify the `client_name` and `client_version` from the executable or CLI when possible. If no command exists to extract the version and it cannot be retrieved from the environment (e.g., some desktop apps), omit these fields.

| `client_name` | `client_version` | `command` | `output` |
| :-: | :-: | :-: | :-: |
| `openclaw-cli` | `2026.3.24` | `openclaw -v` | `OpenClaw 2026.3.24 (cff6dc9)` |
| `codex` | `0.117.0` | `codex -V` | `codex-cli 0.117.0` |
| `codex-app` | `26.325.21221` | `N/A` | `N/A` |
| `claude-code` | `2.1.85` | `claude -v` | `2.1.85 (Claude Code)` |
| `cursor` | `2.6.13` | `cursor -v` | `2.6.13` |
| `gemini-cli` | `0.35.1` | `gemini -v` | `0.35.1` |
| `opencode` | `1.3.0` | `opencode -v` | `1.3.0` |

Next, run `recommend.py` exactly once with one JSON object on stdin via EOF. Do not pass prose around the JSON, multiple JSON objects, or extra shell flags.

`recommend.py` may take around 5 minutes end to end. You must wait for it to finish completely and must not do other work before it exits. If you need progress, keep watching stdout until the command finishes.

```bash
uv run -qq scripts/recommend.py <<'EOF'
{
  "query": "Add integration tests for a FastAPI skill recommendation flow, mock the gateway, and verify the returned skills and feedback flow.",
  "client_name": "codex",
  "client_version": "0.117.0",
  "download_dir": ".skills_vote/"
}
EOF
```
