# Install SkillsVote

Use this guide when asked to install the `skills-vote` skill for the current agent.

This guide installs the hosted `skills-vote` skill. For local or private skill libraries, use [`INSTALL_LOCAL.md`](INSTALL_LOCAL.md) to install `skills-vote-local`.

## Goal

Install `skills-vote` into the current agent's **global** skill directory by default. If the current request explicitly asks for workspace or current-project installation, use that scope instead. Then write `SKILLS_VOTE_API_KEY` and, when available, one usable GitHub token into the installed skill root.

This guide assumes the current request or conversation provides these runtime inputs:
- the current agent
- the API key value to write into `.env`
- optionally, a usable GitHub token if one is already available or explicitly provided

## Installation scope

Support both installation scopes:
- **Global**: default choice
- **Workspace / current project**: use only when the current request explicitly asks for it

Do not ask about scope unless the user gives conflicting or ambiguous scope instructions.

## Common `<current-agent>` values

Use the value in the right column for `-a <current-agent>`. These are `npx skills` agent identifiers, not generic product labels.

| Agent | `<current-agent>` |
| --- | --- |
| Codex | `codex` |
| Claude Code | `claude-code` |
| OpenClaw | `openclaw` |
| Cursor | `cursor` |
| Gemini CLI | `gemini-cli` |
| OpenCode | `opencode` |
| Cline | `cline` |
| GitHub Copilot CLI | `github-copilot` |
| Continue | `continue` |
| Windsurf | `windsurf` |
| OpenHands | `openhands` |
| Pi | `pi` |

If the current agent is not listed here, do not infer a new identifier from the product name. Ask the user for the correct `npx skills` agent identifier, or use a verified value supplied by the current runtime.

## Required flow

1. Determine the current agent and set `<current-agent>` accordingly. If you cannot determine the current agent reliably, stop and ask instead of guessing.
2. Determine the installation scope:
   - **Global (default):**

   ```bash
   npx skills add MemTensor/skills-vote -g -a <current-agent> -s skills-vote -y
   ```

   - **Workspace / current project** — use only when explicitly requested:

   ```bash
   npx skills add MemTensor/skills-vote -a <current-agent> -s skills-vote -y
   ```

3. Resolve the real installed path with the matching scope. Do **not** guess it:

   - **Global:**

   ```bash
   npx skills list -g -a <current-agent> --json
   ```

   - **Workspace / current project:**

   ```bash
   npx skills list -a <current-agent> --json
   ```

4. Read the returned JSON and find the `path` for `skills-vote`. Treat that path as the skill root. If no valid `path` is returned for `skills-vote`, stop and report the failure instead of guessing.
5. Create or update `<path>/.env` and set `SKILLS_VOTE_API_KEY` to the API key value provided in the current request or prompt. Do not write the literal string `YOUR_API_KEY`.
6. GitHub token handling is optional:
   - If a usable `GH_TOKEN` or `GITHUB_TOKEN` is already available or explicitly provided, you may write one of them into `<path>/.env`.
   - If the GitHub token is empty, missing, or not usable, tell the user that downloading skills may hit a GitHub rate limit and ask whether they want to provide a usable token.
   - If no usable GitHub token is ultimately provided, do **not** set `GH_TOKEN` or `GITHUB_TOKEN` in the `.env` file.

```env
SKILLS_VOTE_API_KEY="<provided-api-key>"
GITHUB_TOKEN="<usable-github-token>"
```

## Rules

- Do **not** install into the current project or workspace unless explicitly requested.
- Do **not** configure `SKILLS_VOTE_API_KEY` as a system-level or user-level environment variable unless explicitly requested.
- Do **not** hardcode the install path. Always use the path returned by `npx skills list ... --json`.
- If the current request does not provide a usable API key value, stop and ask the user to provide one or obtain one from `https://skills.vote`. Do not invent an API key.
