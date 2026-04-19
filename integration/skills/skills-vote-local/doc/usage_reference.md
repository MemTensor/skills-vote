# skills-vote-local usage reference

Use this document when you need to run `skills-vote-local` yourself instead of delegating the lookup to a subagent.

Work from this skill root directory.

## Workflow

### 1. Rewrite the query

`scripts/recommend.py` expects a rewritten, retrieval-oriented query; it does not rewrite for you.

Rewrite the original request into a short, standalone, retrieval-oriented query.

Rules:

- Preserve the original task's domain terms and key intent words.
- Rewrite for retrieval, not task execution.
- Keep it short, standalone, and searchable.

Example:

- raw: `make a PR for it`
- rewritten: `Prepare, review, and open a pull request for an existing change.`

### 2. Optional: run the environment check

Run the environment check before retrieval when setting up or debugging the skill.

```bash
uv run -qq python scripts/check_env.py
```

### 3. Run retrieval

```bash
uv run -qq python scripts/recommend.py \
  -q "Prepare, review, and open a pull request for an existing change."
```

If you want a wider recall window for one query, pass `--top-k N`.

Output fields:

- `selected_skills`: final top skill names
- `candidates`: returned candidates with path, description, and score

## Config

- The expected live config location is `config/config.yaml`.
- If the config is already prepared, use it as-is.
- Read `doc/config-schema.md` only when you need to create or edit the config.

## Notes

- Before querying, `scripts/recommend.py` automatically runs incremental `update`.
- You usually do not need to rebuild the index manually.
- If you want a full rebuild, run:

```bash
uv run -qq python scripts/index.py
```
