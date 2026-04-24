## Required workflow

You are the main agent.
This route delegates skill lookup to a subagent.

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

If you cannot call a subagent in the current environment, do not read raw route templates and do not use doc/usage_reference.md. Run:

```bash
uv run -qq python scripts/route_prompt.py --role main --fallback
```

Then follow the rendered fallback stdout exactly.
