# Install SkillsVote

Use this guide when asked to install the `skills-vote` skill for the current agent.

## Goal

Install `skills-vote` into the current agent's **global** skill directory, not the current project or workspace. Then write `SKILLS_VOTE_API_KEY` only into the installed skill root.

This guide assumes the current request provides two runtime inputs:
- the current agent
- the API key value to write into `.env`

## Common `<current-agent>` values

Use the value in the right column for `-a <current-agent>`.

| Agent | `<current-agent>` |
| --- | --- |
| Codex | `codex` |
| Claude Code | `claude-code` |
| OpenClaw | `openclaw` |
| Cursor | `cursor` |
| Gemini CLI | `gemini-cli` |
| OpenCode | `opencode` |
| Cline | `cline` |
| GitHub Copilot | `github-copilot` |
| Continue | `continue` |
| Windsurf | `windsurf` |
| OpenHands | `openhands` |
| Pi | `pi` |

If the current agent is not listed here, use the exact agent value accepted by `npx skills add -a ...`.

## Required flow

1. Determine the current agent and set `<current-agent>` accordingly. If you cannot determine the current agent reliably, stop and ask instead of guessing.
2. Install the skill globally:

```bash
npx skills add MemTensor/skills-vote -g -a <current-agent> -s skills-vote -y
```

3. Resolve the real installed path. Do **not** guess it:

```bash
npx skills list -g -a <current-agent> --json
```

4. Read the returned JSON and find the `path` for `skills-vote`. Treat that path as the skill root. If no valid `path` is returned for `skills-vote`, stop and report the failure instead of guessing.
5. Create or update `<path>/.env` and set `SKILLS_VOTE_API_KEY` to the API key value provided in the current request or prompt. Do not write the literal string `YOUR_API_KEY`.

```env
SKILLS_VOTE_API_KEY="<provided-api-key>"
```

## Rules

- Do **not** install into the current project or workspace unless explicitly requested.
- Do **not** configure `SKILLS_VOTE_API_KEY` as a system-level or user-level environment variable unless explicitly requested.
- Do **not** hardcode the install path. Always use the path returned by `npx skills list ... --json`.
- If the current request does not provide a usable API key value, stop and ask your owner to provide one or obtain one from `https://skills.vote`. Do not invent an API key.

