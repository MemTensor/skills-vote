---
name: skills-vote-local
description: Use when retrieving the most relevant skills for a user request from a local or private skill library instead of relying on network-based skill discovery.
---

# Skills Vote Local

Read only this file first.

This skill retrieves the most relevant skills for a user request from a local or private skill library.

## Delegate skill lookup to a subagent

Prefer this path whenever you can call a subagent.

Do not read `doc/handoff.md` yourself unless you are actually acting as the delegated subagent.

If you can call a subagent, let the subagent handle the skill lookup for you.

A fast lightweight subagent is usually enough for the first retrieval pass.

Point it to `doc/handoff.md`.

If the subagent may not inherit this working directory, give it the explicit handoff path.

Example:

```text
You need to read /path/to/skills-vote-local/doc/handoff.md
and recommend skills for me with the task:
<self-contained task description>
```

Make the task description self-contained. Do not assume the subagent has your full context.

Include the objective, the key domain terms, any relevant constraints, and the current artifact or situation when that context matters.

The subagent should start from `doc/handoff.md`, run retrieval, and only read more files when it needs better recommendation quality or config/debug context.

## If you cannot call a subagent

Only do this when you cannot call a subagent, or when the user explicitly wants you to run the lookup yourself.

Read `doc/usage_reference.md` and follow the workflow there yourself.

- `doc/usage_reference.md` is the direct-use workflow
- `doc/config-schema.md` is only for creating or editing config
