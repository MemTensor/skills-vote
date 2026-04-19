# skills-vote-local handoff

Read only this file first. Do not read `SKILL.md`, `doc/config-schema.md`, or `scripts/` unless this file tells you to.

Use this handoff when a parent agent asks you to recommend skills from a local or private skill library for a specific task.

## Parent prompt shape

A parent agent can hand you work like this:

```text
You need to read /path/to/skills-vote-local/doc/handoff.md
and recommend skills for me with the task:
<task>
```

## Your job

- rewrite the task into a short retrieval-oriented query
- run retrieval against the local skill library
- use more than one retrieval pass when that improves recommendation quality
- read returned candidate `SKILL.md` files when needed to understand each skill's capability boundary
- return a final recommendation to the parent agent as strict JSON only

## Default workflow

### 1. Rewrite the task for retrieval

Rules:

- Preserve the original task's domain terms and key intent words.
- Rewrite for retrieval, not task execution.
- Keep it short, standalone, and searchable.

Example:

- task: `make a PR for it`
- query: `Prepare, review, and open a pull request for an existing change.`

### 2. Optional: run the environment check

Run this only when setting up, debugging, or if retrieval fails unexpectedly.

```bash
uv run -qq python scripts/check_env.py
```

### 3. Run retrieval

```bash
uv run -qq python scripts/recommend.py \
  -q "<rewritten query>"
```

Use `--top-k N` only when the parent agent wants a wider recall window.

### 4. Improve the recommendation only when needed

If the first pass is ambiguous, low-confidence, or the parent agent asks for a better recommendation:

- run another retrieval round with a refined query
- open the candidate skill `SKILL.md` files returned by `recommend.py`
- compare which skills best fit the task and where their boundaries differ
- keep iterating until you have a stable recommendation or a clear uncertainty to report

Do not read this skill's own `SKILL.md` by default. Use it only when you need the broader parent-agent-facing contract.
Read `doc/usage_reference.md` only when you need the direct-use workflow in more detail.

## Config and rebuild only when needed

- The live config location is `config/config.yaml`.
- Read `doc/config-schema.md` only when you need to create or edit config.
- `scripts/recommend.py` automatically runs incremental `update` before querying.
- Only run a full rebuild when you explicitly need one:

```bash
uv run -qq python scripts/index.py
```

## What to send back to the parent agent

Return strict JSON only. Do not use Markdown, bullets, code fences, or any explanation outside the JSON object.

Use this exact schema:

```json
{
  "skills": [
    {
      "name": "string",
      "description": "string",
      "path": "string"
    }
  ],
  "reason": "string"
}
```

Rules:

- Use only the top-level fields `skills` and `reason`.
- Each item in `skills` must contain only `name`, `description`, and `path`.
- Order `skills` by recommendation priority. Use ordering to express priority; do not add score-like fields.
- `reason` must explain why these skills were chosen, why they are ordered this way, and why close alternatives were not selected when that matters.

Example:

```json
{
  "skills": [
    {
      "name": "review-pr",
      "description": "Use this skill when the user asks to review a PR or pull request.",
      "path": "/path/to/review-pr/SKILL.md"
    },
    {
      "name": "pr-description",
      "description": "Use this skill when the user needs help drafting or improving a PR description.",
      "path": "/path/to/pr-description/SKILL.md"
    }
  ],
  "reason": "review-pr is ranked first because the task is primarily about reviewing and opening a pull request. pr-description is ranked second because it is useful for the PR-writing part of the task but is narrower. Similar skills focused on generic editing were not chosen because they do not match the pull-request workflow as directly."
}
```
