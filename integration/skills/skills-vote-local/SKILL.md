---
name: skills-vote-local
description: Use when retrieving the most relevant skills from a local or private skill library instead of relying on network-based skill discovery.
---

# Skills Vote Local

Read only this file first. Do not read `scripts/`, `docs/`, or any other files in this skill unless this file or a script output explicitly tells you to do so.

Use this skill when the current task needs skill discovery from a local or private skill library instead of a network service.

All paths mentioned in this file are relative to this skill root. `cd` to this root directory before running any command here.

Run:

```bash
uv run -qq scripts/route_prompt.py --role main
```

Then follow the rendered stdout exactly.

If routing.mode selects a subagent route, the user configuration explicitly requests subagent-based skill lookup.
The main agent should use subagent delegation when the current host/tooling permits it.

Do not use fallback merely because the current user message did not repeat "use subagent".

If the current host, tool policy, runtime, or authorization model cannot create a subagent in this turn, run:

```bash
uv run -qq scripts/route_prompt.py --role main --fallback
```

Then follow the fallback stdout exactly.

If you are a subagent and you read this file directly, do not run this command with `--role main`. Run:

```bash
uv run -qq scripts/route_prompt.py --role subagent
```

Then follow the rendered stdout exactly.
