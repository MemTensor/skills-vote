# Install SkillsVote Skills

Use this workflow to install `skills-vote` or `skills-vote-local` for the current agent.

## 1. Choose The Skill

- Use `skills-vote` for hosted SkillsVote recommendations. It calls the SkillsVote cloud service and needs `SKILLS_VOTE_API_KEY`.
- Use `skills-vote-local` for local or private skill libraries. Its default `agentic_search` mode does not need a SkillsVote cloud API key.
- If the prompt says local, private, offline, workspace, on-machine, or self-hosted skill discovery, choose `skills-vote-local`.
- If the prompt says hosted, cloud, SkillsVote API, or provides `SKILLS_VOTE_API_KEY`, choose `skills-vote`.
- If the prompt only says "install SkillsVote", ask which skill to install.

## 2. Choose The Scope

- Default: global install.
- Use workspace/current-project install only when the user explicitly asks for it.
- Do not ask about scope unless the request is conflicting or ambiguous.

## 3. Set `<current-agent>`

Use this local short table first.

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
| Windsurf | `windsurf` |
| Pi | `pi` |
| Hermes Agent | `hermes-agent` |
| Trae | `trae` |
| Antigravity | `antigravity` |

If the current agent is not listed, fetch the upstream `Supported Agents` table:

```bash
curl -L https://raw.githubusercontent.com/vercel-labs/skills/main/README.md
```

Use the matching value from the `--agent` column. If no reliable match exists, ask the user. Do not invent an identifier.

## 4. Install

1. Set `<skill-name>` to `skills-vote` or `skills-vote-local`.
2. Save the starting directory before changing directories:

   ```bash
   ORIGINAL_WORKDIR="$PWD"
   ```

3. Install.

   Global:

   ```bash
   npx skills add MemTensor/skills-vote -g -a <current-agent> -s <skill-name> -y
   ```

   Workspace/current project:

   ```bash
   npx skills add MemTensor/skills-vote -a <current-agent> -s <skill-name> -y
   ```

4. Resolve the installed path. Do not guess it.

   Global:

   ```bash
   npx skills list -g -a <current-agent> --json
   ```

   Workspace/current project:

   ```bash
   npx skills list -a <current-agent> --json
   ```

5. Read the JSON. Find the `path` for `<skill-name>`. Use it as `<installed-skill-root>`.
6. If no valid path is returned, report the install failure.

## 5. Configure `skills-vote`

Use this section only for `skills-vote`.

1. Require a real `SKILLS_VOTE_API_KEY`.
2. Create or update `<installed-skill-root>/.env`.
3. Write the provided API key.
4. Write `GH_TOKEN` or `GITHUB_TOKEN` only when a usable token is already available or explicitly provided.

```env
SKILLS_VOTE_API_KEY="<provided-api-key>"
GITHUB_TOKEN="<usable-github-token>"
```

Rules:

- Do not write placeholder API keys.
- Do not write system-level environment variables unless explicitly asked.
- If no GitHub token is available, omit it and warn that downloads may hit GitHub rate limits.

## 6. Configure `skills-vote-local`

Use this section only for `skills-vote-local`.

Do not stop after installation. Create `configs/config.yaml`.

1. `cd` to `<installed-skill-root>`.
2. If needed, create `configs/config.yaml` from `configs/config.yaml.example`.
3. Discover likely local skill libraries.
4. Ask which paths to include.
5. Ask whether to use `agentic_search` or `vector_search`.
6. Write `configs/config.yaml`.
7. Run:

```bash
uv run -qq scripts/check_env.py
```

### 6.1 Discover Local Skill Libraries

Search only likely skill roots. Do not crawl the whole filesystem.

Candidate roots:

- `$ORIGINAL_WORKDIR`
- `$ORIGINAL_WORKDIR/.codex/skills`
- `$ORIGINAL_WORKDIR/.claude/skills`
- `$ORIGINAL_WORKDIR/.agents/skills`
- `$ORIGINAL_WORKDIR/.hermes/skills`
- `$ORIGINAL_WORKDIR/.trae/skills`
- `$ORIGINAL_WORKDIR/.skills`
- `$ORIGINAL_WORKDIR/skills`
- `~/.codex/skills`
- `~/.claude/skills`
- `~/.agents/skills`
- `~/.hermes/skills`
- `~/.trae/skills`
- `~/.gemini/antigravity/skills`
- `~/.config/skills`
- `~/.local/share/skills`

Use this bounded scan:

```bash
python3 - <<'PY'
import os
from pathlib import Path

original = Path(os.environ.get("ORIGINAL_WORKDIR", Path.cwd())).expanduser().resolve()
roots = [
    original if (original / "SKILL.md").is_file() else None,
    original / ".codex" / "skills",
    original / ".claude" / "skills",
    original / ".agents" / "skills",
    original / ".hermes" / "skills",
    original / ".trae" / "skills",
    original / ".skills",
    original / "skills",
    Path.home() / ".codex" / "skills",
    Path.home() / ".claude" / "skills",
    Path.home() / ".agents" / "skills",
    Path.home() / ".hermes" / "skills",
    Path.home() / ".trae" / "skills",
    Path.home() / ".gemini" / "antigravity" / "skills",
    Path.home() / ".config" / "skills",
    Path.home() / ".local" / "share" / "skills",
]
prune_names = {
    ".git",
    ".hg",
    ".svn",
    ".skills",
    ".skills_vote",
    ".venv",
    "__pycache__",
    "node_modules",
}
max_depth = 6
seen_roots = set()

for root in roots:
    if root is None:
        continue
    root = root.expanduser().resolve()
    if root in seen_roots or not root.exists() or not root.is_dir():
        continue
    seen_roots.add(root)
    count = 0
    stack = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        if current.name in prune_names:
            continue
        if (current / "SKILL.md").is_file():
            count += 1
        if depth >= max_depth:
            continue
        try:
            children = list(current.iterdir())
        except OSError:
            continue
        stack.extend((child, depth + 1) for child in children if child.is_dir())
    if count:
        print(f"{root}\t{count}")
PY
```

Ask:

```text
I found these likely local skill-library roots:
1. <path> (<N> SKILL.md files)
2. <path> (<N> SKILL.md files)

Which paths should `skills-vote-local` search? You can choose one, several, none, or add another path.
```

Do not include any path without user confirmation.

### 6.2 Write Include Paths

Write confirmed roots as absolute `SKILL.md` glob patterns.

```yaml
skill_library:
  include:
    - "/absolute/path/to/confirmed-skill-library/**/SKILL.md"
  exclude:
    - "**/.git/**"
    - "**/.hg/**"
    - "**/.svn/**"
    - "**/.skills/**"
    - "**/.venv/**"
    - "**/venv/**"
    - "**/node_modules/**"
    - "**/__pycache__/**"
    - "**/.pytest_cache/**"
    - "**/.mypy_cache/**"
    - "**/.ruff_cache/**"
    - "**/dist/**"
    - "**/build/**"
```

### 6.3 Choose Retrieval

Ask:

```text
Which retrieval method should `skills-vote-local` use?

1. `agentic_search` (recommended): filesystem search over the synced local skill namespace. No embedding key needed.
2. `vector_search`: semantic search with Chroma. Requires embedding provider, model, dimensions, base URL, and API key or API-key environment variable.
```

Default to `agentic_search` when the user is unsure.

```yaml
retrieval:
  method: agentic_search
```

Use `vector_search` only when the user wants semantic retrieval and can provide embedding settings.

```yaml
retrieval:
  method: vector_search

embedding:
  provider: openai-compatible
  model: bge-m3
  dimensions: 1024
  api_key_env: OPENAI_API_KEY
  api_key: ""
  base_url: "https://api.openai.com/v1"
  extra_headers: {}
```

If the user wants an environment variable, leave `api_key` empty and set `api_key_env`.

### 6.4 Minimal Local Config

Use this shape after the user confirms include paths:

```yaml
skill_library:
  include:
    - "/absolute/path/to/skills/**/SKILL.md"
  exclude:
    - "**/.git/**"
    - "**/.hg/**"
    - "**/.svn/**"
    - "**/.skills/**"
    - "**/.venv/**"
    - "**/venv/**"
    - "**/node_modules/**"
    - "**/__pycache__/**"
    - "**/.pytest_cache/**"
    - "**/.mypy_cache/**"
    - "**/.ruff_cache/**"
    - "**/dist/**"
    - "**/build/**"

retrieval:
  method: agentic_search

routing:
  mode: subagent_multi_pass
  max_passes: 3
```

Local rules:

- Do not configure cloud API keys unless the user chooses `vector_search`.
- Do not invent local paths.
- Do not write placeholder paths into the final config.
- Do not write fake API keys.
