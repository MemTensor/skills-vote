# Config schema

`skills-vote-local` uses YAML configuration.

Recommended file layout:

- place the live config at `config/config.yaml` when needed
- place an example or starter config at `config/config.yaml.example` when useful

Keep config responsibilities narrow:

- point to the real skill library to index
- point to the Chroma output directory to use
- choose the embedding provider
- choose retrieval limits

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

- `include`: scan globs for candidate `SKILL.md` files
- `include` can be absolute or relative; relative patterns are resolved against the config file directory
- a common relative form is something like `../skills/**/SKILL.md` when the target skill library sits next to this package
- `exclude`: glob filters applied to the absolute matched file path
- `extend_include`: extra scan globs appended after `include`
- `extend_exclude`: extra absolute-path glob filters appended after `exclude`
- legacy `roots` configs are still tolerated for backward compatibility, but new configs should express scan scope directly in `include`

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
  model: text-embedding-3-large
  dimensions: 3072
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
- `dimensions` is a config note for your embedding setup; current requests send `model` and `input`
- `base_url` should point to an OpenAI-compatible embeddings endpoint

## `retrieval`

```yaml
retrieval:
  top_k: 20
  final_k: 5
```

- `top_k`: default Chroma recall size, can be overridden per query with `scripts/recommend.py --top-k N`
- `final_k`: default final returned candidate count after truncation
- if `top_k < final_k`, the returned count is clamped to `top_k`

## `indexing`

```yaml
indexing:
  update_on_start: true
```

- `update_on_start=true`: run incremental `update` automatically before each query
- `false`: query the existing collection as-is
- normal usage should rely on auto-update during query
- `rebuild_on_start` is still accepted for backward compatibility, but `update_on_start` is preferred
