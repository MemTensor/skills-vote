# skills-vote-local handoff

You are the delegated subagent for a local/private skill recommendation task.

This handoff is used when routing.mode is subagent_*.
The user configuration explicitly requests that skill lookup be performed by a subagent.

Read only this file first.
Work from the `skills-vote-local` skill root directory.

The subagent must render its own route:

```bash
uv run -qq python scripts/route_prompt.py --role subagent
```

Then follow the rendered stdout exactly.

The rendered stdout may select vector retrieval or `agentic_grep`.
If it selects `agentic_grep`, search only the synced `./.skills/` namespace exactly as the route prompt instructs.

Do not read `SKILL.md`, `doc/usage_reference.md`, `doc/config-schema.md`, or files under `scripts/` unless the route prompt tells you to.

If `scripts/route_prompt.py` cannot run, return strict JSON with `skills: []` and a `reason` explaining that the route prompt could not be loaded.
