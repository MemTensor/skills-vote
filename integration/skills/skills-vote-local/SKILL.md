---
name: skills-vote-local
description: Use when retrieving the most relevant skills from a local or private skill library instead of relying on network-based skill discovery.
---

# Skills Vote Local

Read only this file first.

This skill retrieves the most relevant skills from a local or private skill library.

Work from this skill root directory.

Run:

```bash
uv run -qq python scripts/route_prompt.py --role main
```

If you are subagent but you read this file by mistake, run the above command with `--role subagent` instead.

Then follow the stdout exactly.

If routing.mode selects a subagent route, the user configuration explicitly requests subagent-based skill lookup.
The main agent should use subagent delegation when the current host/tooling permits it.

Do not use fallback merely because the current user message did not repeat "use subagent".

If the current host, tool policy, runtime, or authorization model cannot create a subagent in this turn, do not read raw route templates and do not use `doc/usage_reference.md`. Instead run:

```bash
uv run -qq python scripts/route_prompt.py --role main --fallback
```

Then follow the fallback stdout exactly.

Do not read `doc/handoff.md`, `doc/usage_reference.md`, `doc/config-schema.md`, or files under `scripts/` unless the route prompt tells you to.

If `scripts/route_prompt.py` cannot run, fall back to `doc/usage_reference.md` and use the direct local retrieval workflow.
