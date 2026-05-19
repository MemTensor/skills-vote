# Config schema

`skills-vote-local` reads `configs/config.yaml` by default.

Production recommendation: start with `retrieval.method: agentic_search`.
It needs only a skill-library glob and does not require Chroma, an embedding
provider, or an API key.

Unsupported top-level or section fields are rejected instead of ignored. When
changing the config, start from the example below and keep only fields listed in
this document.

## Production starter

```yaml
routing:
  mode: subagent_multi_pass
  max_passes: 3

retrieval:
  method: agentic_search

retrieval_context:
  mode: recommend_plus_skill_md

skill_library:
  include:
    - /path/to/your-skill-library/**/SKILL.md
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

## `routing`

```yaml
routing:
  mode: subagent_multi_pass
  max_passes: 3
```

- `mode`: chooses who performs skill lookup and whether lookup is single-pass or multi-pass.
- allowed values:
  - `main_single_pass`
  - `main_multi_pass`
  - `subagent_single_pass`
  - `subagent_multi_pass`
- production default: `subagent_multi_pass`, so the main agent keeps only the handoff brief and the subagent performs retrieval.
- invalid values cause `scripts/route_prompt.py` to print a warning and fall back to `subagent_multi_pass`.
- `max_passes`: maximum retrieval passes for multi-pass routes; use `3` unless the skill library is unusually noisy.
- single-pass routes ignore `max_passes` and always use one planned pass.

## `retrieval`

```yaml
retrieval:
  method: agentic_search
```

- `method`: retrieval backend.
  - `agentic_search`: sync include-matched skills into `./.skills/` as directory symlinks and search them with bounded `find`/`grep`.
  - `vector_search`: use `scripts/recommend.py`, Chroma, and the configured embedding provider.
- production default: `agentic_search`.
- set this field explicitly in committed configs so the intended retrieval backend is visible at a glance.

When `method` is `agentic_search`:

- `scripts/route_prompt.py` syncs `project_root/.skills/` before rendering the route.
- `project_root` is computed from the script location, not the shell cwd or config.
- `.skills/` is an agent-facing namespace, not the real skill source.
- sync creates and unlinks only managed directory symlinks under `.skills/`.
- sync does not write a manifest, sentinel file, `.gitignore`, or copied skill files.
- `.skills/**` is excluded from discovery to avoid recursive namespace pollution.
- prompts use `find -H ./.skills/* ... -exec grep ...` so only top-level alias symlinks are followed.
- prompts do not use `scripts/recommend.py`, vector_search, or embedding retrieval.

`vector_search` retrieval options:

```yaml
retrieval:
  method: vector_search
  top_k: 5
```

- `top_k`: default Chroma recall size; can be overridden per query with `scripts/recommend.py --top-k N`.
- omit `top_k` when using `agentic_search`.

## `retrieval_context`

```yaml
retrieval_context:
  mode: recommend_plus_skill_md
```

- controls how much candidate skill content the retrieval actor must inspect during recommendation.
- applies to the agent that actually performs retrieval.
- allowed values:
  - `recommend_only`
  - `recommend_plus_skill_md`
  - `recommend_plus_skill_dir`
- this policy only controls recommendation-time evidence; after a skill is selected for actual task execution, the execution agent may read the selected skill's `SKILL.md`.
- in `agentic_search` mode this setting is shown for awareness but does not restrict corpus scope; the corpus remains `./.skills/`, with `SKILL.md` searched first and full skill directories searched only when needed.

## `skill_library`

```yaml
skill_library:
  include:
    - /path/to/your-skill-library/**/SKILL.md
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

- `include`: required glob patterns used to find candidate `SKILL.md` files.
- `include` can be absolute or relative; relative patterns are resolved from the config file directory.
- common relative forms:
  - `../skills/**/SKILL.md`
  - `../../.codex/skills/**/SKILL.md`
- `exclude`: glob filters applied to matched absolute paths and canonical paths.
- include `.skills/**` in `exclude` for vector_search mode; agentic sync also excludes `.skills/**` internally.

## `vector_search` `chroma`

```yaml
chroma:
  path: ../output/chroma/skills_vote_local
  collection: skills_vote_local
```

- used only when `retrieval.method` is `vector_search`.
- `path`: where the local Chroma data directory will be created.
- relative paths are resolved from the config file directory.
- choose a writable location owned by the current runtime.
- `collection`: Chroma collection name.

## `vector_search` `embedding`

```yaml
embedding:
  provider: openai-compatible
  model: bge-m3
  dimensions: 1024
  api_key_env: OPENAI_API_KEY
  api_key: ""
  base_url: https://api.openai.com/v1
  extra_headers: {}
```

Supported providers:

- `openai-compatible`: external embeddings API, supports either `api_key` or `api_key_env`.
- `hashing`: deterministic local baseline, no API key, useful for smoke tests rather than semantic production retrieval.

Notes:

- production vector_search should use `openai-compatible`, `bge-m3`, and `1024` dimensions unless the embedding service requires different values.
- `api_key` takes precedence when both `api_key` and `api_key_env` are present.
- keep `api_key: ""` in committed configs; prefer `api_key_env` for real credentials.
- `model` defaults to `bge-m3`; the local `hashing` provider ignores it.
- `dimensions` defaults to `1024`; the local `hashing` provider uses it directly.
- `base_url` should point to an OpenAI-compatible embeddings endpoint and should not be blank for `openai-compatible`.
- `extra_headers` is for provider-specific HTTP headers; keep `{}` unless required.

## `vector_search` `indexing`

```yaml
indexing:
  update_on_start: true
```

- used only when `retrieval.method` is `vector_search`.
- `update_on_start=true`: run incremental `update` automatically before each query.
- `false`: query the existing collection as-is.
