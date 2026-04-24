# skills-vote-local handoff

You are the delegated subagent for a local/private skill recommendation task.

Read only this file first.
Work from the `skills-vote-local` skill root directory.

Run:

```bash
uv run -qq python scripts/route_prompt.py --role subagent
```

Then follow the stdout exactly.

Do not read `SKILL.md`, `doc/usage_reference.md`, `doc/config-schema.md`, or files under `scripts/` unless the route prompt tells you to.

If `scripts/route_prompt.py` cannot run, return strict JSON with `skills: []` and a `reason` explaining that the route prompt could not be loaded.
