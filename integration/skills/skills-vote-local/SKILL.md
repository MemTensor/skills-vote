---
name: skills-vote-local
description: Use when retrieving the most relevant skills for a user request from a local or private skill library instead of relying on network-based skill discovery.
---

# Skills Vote Local

This skill retrieves the most relevant skills for a user request from a local or private skill library.

Use it like this:

- `rewrite query -> retrieve top candidates from the local skill library`

## Before you run anything

- Work from this skill root directory.

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
  -q "Retrieve the most relevant local skills for preparing, reviewing, and opening a pull request for an existing change."
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
