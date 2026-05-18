# Install SkillsVote Local

Use this guide when asked to install the `skills-vote-local` skill for the current agent.

## Goal

Install `skills-vote-local` into the current agent's skill directory, then help the user configure which local skill libraries it should search.

`skills-vote-local` is different from `skills-vote`:

- `skills-vote` calls the hosted SkillsVote service.
- `skills-vote-local` searches local or private skill directories on the user's machine.

Do not stop after installation. The important part of this guide is the post-install configuration step.

## Installation Scope

Install globally by default. If the current request explicitly asks for workspace or current-project installation, use that scope instead.

Do not ask about scope unless the user gives conflicting or ambiguous scope instructions.

## Common `<current-agent>` Values

Use the value in the right column for `-a <current-agent>`. These are `npx skills` agent identifiers.

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

## Required Flow

1. Determine the current agent and set `<current-agent>`. If you cannot determine the current agent reliably, ask the user instead of guessing.
2. Record the original working directory before changing directories:

   ```bash
   ORIGINAL_WORKDIR="$PWD"
   ```

3. Determine the installation scope.
4. Install the skill:

   - Global:

   ```bash
   npx skills add MemTensor/skills-vote -g -a <current-agent> -s skills-vote-local -y
   ```

   - Workspace / current project:

   ```bash
   npx skills add MemTensor/skills-vote -a <current-agent> -s skills-vote-local -y
   ```

5. Resolve the real installed path with the matching scope. Do not guess it:

   - Global:

   ```bash
   npx skills list -g -a <current-agent> --json
   ```

   - Workspace / current project:

   ```bash
   npx skills list -a <current-agent> --json
   ```

6. Read the returned JSON and find the `path` for `skills-vote-local`. Treat that path as the skill root. If no valid `path` is returned, report the failure instead of guessing.
7. `cd` to the installed skill root.
8. Create `config/config.yaml` from `config/config.yaml.example` if it does not already exist.
9. Discover likely local skill libraries from `ORIGINAL_WORKDIR` and common user-level paths, then ask the user which ones to include.
10. Ask the user which retrieval method to use: `agentic_search` or `vector_search`.
11. Update `config/config.yaml`.
12. Run the skill's own environment check:

```bash
uv run -qq scripts/check_env.py
```

## Configure Local Skill Libraries

After installation, inspect likely local skill locations and ask the user which ones should be included.

Search only directories that commonly contain agent skills. Do not crawl the whole filesystem.

Recommended candidate locations:

- the original working directory and its common subdirectories:
  - `.codex/skills`
  - `.claude/skills`
  - `.agents/skills`
  - `.skills`
  - `skills`
  - `integration/skills`
  - `runtime_test/skills`
  - `runtime_test/skills-main/skills`
- common user-level skill directories:
  - `~/.codex/skills`
  - `~/.claude/skills`
  - `~/.config/skills`
  - `~/.local/share/skills`
  - `~/.agents/skills`

Use a bounded scan such as:

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
    original / ".skills",
    original / "skills",
    original / "integration" / "skills",
    original / "runtime_test" / "skills",
    original / "runtime_test" / "skills-main" / "skills",
    Path.home() / ".codex" / "skills",
    Path.home() / ".claude" / "skills",
    Path.home() / ".agents" / "skills",
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
        skill_md = current / "SKILL.md"
        if skill_md.is_file():
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

Then summarize the likely skill library roots and ask which should be included. A skill library root is usually the directory that contains many skill subdirectories, not each individual skill directory.

Ask a concrete question before writing the config:

```text
I found these likely local skill-library roots:
1. <path> (<N> SKILL.md files)
2. <path> (<N> SKILL.md files)

Which of these should `skills-vote-local` search? You can choose one, several, or none, and you can add another path.
```

The user may choose one path, many paths, or none. Do not include a directory without user confirmation.

Write the confirmed roots as `SKILL.md` glob patterns:

```yaml
skill_library:
  include:
    - "/absolute/path/to/confirmed-skill-library/**/SKILL.md"
  exclude: []
```

Prefer absolute paths in `config/config.yaml` so the skill works from any current working directory.

## Choose Retrieval Method

Ask the user which retrieval method they want before writing `retrieval.method`:

```text
Which retrieval method should `skills-vote-local` use?

1. `agentic_search` (recommended): no embedding API key; searches the synced local skill namespace with filesystem search.
2. `vector_search`: semantic search with Chroma; requires an embedding provider, model, dimensions, base URL, and API key or API-key environment variable.
```

### Option A: `agentic_search`

Recommended default for first setup.

This method searches the confirmed local skills with filesystem tools and does not require an embedding API key.

```yaml
retrieval:
  method: agentic_search
```

Use this when:

- the user wants the simplest local setup;
- the skill library is small or medium-sized;
- no embedding provider is available yet;
- local inspection is more important than vector recall.

### Option B: `vector_search`

Use this when the user wants semantic vector retrieval over a larger local library.

`vector_search` requires embedding configuration. Ask the user for:

- embedding provider or OpenAI-compatible base URL;
- embedding model;
- embedding dimensions;
- API key or API-key environment variable;
- whether the vector index should be built now.

Example OpenAI-compatible configuration:

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

Do not write fake API keys such as `sk-xx`. If the user wants to use an environment variable, leave `api_key` empty and set `api_key_env`.

If the user chooses `vector_search` but has no embedding key or endpoint ready, ask whether to configure the embedding settings now or use `agentic_search` for the first setup.

## Minimal Example Config

This is a good first configuration after the user confirms the local skill directories:

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

## Rules

- Do not install `skills-vote-local` when the user asked for the hosted `skills-vote` service.
- Do not configure cloud API keys for `skills-vote-local` unless the user chooses `vector_search`.
- Do not invent local skill paths.
- Do not include directories before the user confirms them.
- Do not write placeholder values such as `/path/to/your-skill-library/` into the final config.
- Do not write fake API keys.
- Do not write legacy retrieval method names such as `agentic_grep` or `vector`.
- Prefer `agentic_search` as the safe default when the user is unsure.
