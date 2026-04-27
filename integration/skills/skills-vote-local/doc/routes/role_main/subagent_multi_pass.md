## Required workflow

You are the main agent.
This route delegates skill lookup to a subagent.

## Important delegation authority

The active routing.mode is subagent_*.
This is a user-configured route for this skill.
Because routing.mode is subagent_*, the user-configured route explicitly requests subagent-based skill lookup.
Treat this configuration as an explicit user request to use subagent-based skill lookup.

Do not downgrade to fallback merely because the current user message did not repeat "use subagent".
The user's routing configuration is the explicit delegation request for this skill.

You should create a subagent for skill lookup when the current host/tooling permits subagent delegation.

Do not run recommend.py yourself.
Do not rewrite the task into a retrieval query.
Package the current task into a self-contained handoff task for the subagent.

Send the subagent to:
{handoff_path}

The handoff task must include objective, key domain terms, constraints, and relevant context.
The subagent may run up to {max_passes} retrieval passes and will return strict JSON.

During the normal delegated path, the main agent does not perform retrieval, does not inspect candidate skill files, and does not inspect candidate skill directories.
The subagent performs query rewrite, recommend.py calls, candidate inspection, and the final JSON recommendation.

The retrieval_context policy applies to the subagent during the normal delegated path.

If the current host, tool policy, runtime, or authorization model cannot create a subagent in this turn, do not read raw route templates and do not use doc/usage_reference.md. Run:

```bash
uv run -qq python scripts/route_prompt.py --role main --fallback
```

Then follow the rendered fallback stdout exactly.
When using fallback, explain that the configured subagent route could not be used in this turn due to host/tooling/runtime constraints.
