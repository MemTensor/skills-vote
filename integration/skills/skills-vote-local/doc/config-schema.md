# Config schema

`skills-vote-local` uses YAML configuration.

Use `config/config.yaml` as the live config file when needed.

- place an example or starter config at `config/config.yaml.example` when useful

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
- `dimensions` is used by the local `hashing` provider
- `base_url` should point to an OpenAI-compatible embeddings endpoint

## `retrieval`

```yaml
retrieval:
  top_k: 5
  final_k: 5
```

- `top_k`: default Chroma recall size, can be overridden per query with `scripts/recommend.py --top-k N`
- `final_k`: reserved for future use; keep it in config, but it is not used by the current implementation

## `indexing`

```yaml
indexing:
  update_on_start: true
```

- `update_on_start=true`: run incremental `update` automatically before each query
- `false`: query the existing collection as-is
