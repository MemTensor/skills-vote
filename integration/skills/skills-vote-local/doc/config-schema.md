# Config schema

`skills-vote-local` uses YAML configuration.

Use `config/config.yaml` as the live config file when needed.

- place an example or starter config at `config/config.yaml.example` when useful

## `routing`

```yaml
routing:
  mode: subagent_multi_pass
  max_passes: 3
```

- `mode`: controls which agent performs vector retrieval and whether retrieval is single-pass or multi-pass
- allowed values:
  - `main_single_pass`
  - `main_multi_pass`
  - `subagent_single_pass`
  - `subagent_multi_pass`
- `delegate_to_subagent` is deprecated and is not a supported alias
- invalid values cause `scripts/route_prompt.py` to print a warning and fall back to `subagent_multi_pass`
- `max_passes`: maximum retrieval passes for multi-pass workflows; defaults to `3`

## `retrieval_context`

```yaml
retrieval_context:
  mode: recommend_plus_skill_md
```

- controls how much candidate skill content the retrieval actor must inspect during recommendation
- applies to the agent that actually performs retrieval
- allowed values:
  - `recommend_only`
  - `recommend_plus_skill_md`
  - `recommend_plus_skill_dir`
- this policy only controls recommendation-time evidence; after a skill is selected for actual task execution, the execution agent may read the selected skill's `SKILL.md`
- when `retrieval.method` is `agentic_grep`, this setting is displayed for awareness but does not restrict search scope; agentic grep always searches `SKILL.md` first, then full skill directories when needed

## `skill_library`

```yaml
skill_library:
  include:
    - /path/to/your-skill-library/**/SKILL.md
  exclude:
    - "**/.git/**"
    - "**/.venv/**"
    - "**/node_modules/**"
    - "**/__pycache__/**"
  extend_include: []
  extend_exclude: []
```

- `include`: glob patterns used to find candidate `SKILL.md` files
- `include` can be absolute or relative; relative patterns are resolved from the config file directory
- a common relative form is something like `../skills/**/SKILL.md` when the target skill library sits next to this package
- `exclude`: glob filters applied to the absolute matched file path
- `extend_include`: extra scan globs appended after `include`
- `extend_exclude`: extra absolute-path glob filters appended after `exclude`

## `chroma`

```yaml
chroma:
  path: ../output/chroma/skills_vote_local
  collection: skills_vote_local
```

- `path`: where the local Chroma data directory will be created
- relative paths are resolved from the config file directory
- choose a writable location owned by the current runtime

## `embedding`

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

- `hashing`: deterministic local baseline, no API key
- `openai-compatible`: external embeddings API, supports either `api_key` or `api_key_env`

Notes:

- `api_key` takes precedence when both are present
- default embedding settings are `openai-compatible`, `bge-m3`, and `1024` dimensions
- `model` defaults to `bge-m3`; the local `hashing` provider ignores it
- `dimensions` defaults to `1024`; it is used directly by the local `hashing` provider
- `base_url` should point to an OpenAI-compatible embeddings endpoint

## `retrieval`

```yaml
retrieval:
  method: vector
  top_k: 5
  final_k: 5
```

- `method`: retrieval backend
  - `vector`: use `scripts/recommend.py` and the local vector index
  - `agentic_grep`: sync include-matched skills into `./.skills/` as directory symlinks and search them with `find`/`grep`
- `top_k`: default Chroma recall size, can be overridden per query with `scripts/recommend.py --top-k N`
- `final_k`: reserved for future use; keep it in config, but it is not used by the current implementation

When `method` is `agentic_grep`:

- `scripts/route_prompt.py` syncs `project_root/.skills/` before rendering the route
- `project_root` is computed from the script location, not the shell cwd or config
- `.skills/` is an agent-facing namespace, not the real skill source
- sync creates and unlinks only managed directory symlinks under `.skills/`
- sync does not write a manifest, sentinel file, `.gitignore`, or copied skill files
- `.skills/**` is excluded from discovery to avoid recursive namespace pollution
- prompts use symlink-aware `find -H ./.skills/* ... -exec grep ...`
- prompts do not use `scripts/recommend.py` or vector retrieval in this mode

## `indexing`

```yaml
indexing:
  update_on_start: true
```

- `update_on_start=true`: run incremental `update` automatically before each query
- `false`: query the existing collection as-is
