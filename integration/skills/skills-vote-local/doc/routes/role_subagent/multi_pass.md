## Required workflow

You are the delegated subagent.
Work from this skill root: {skill_root}

Rewrite the handoff task into a short, standalone, retrieval-oriented query.
Run retrieval with:

```bash
{recommend_command}
```

You may refine the query and run additional retrieval passes when results are ambiguous, too generic, missing key domain terms, overlapping in capability, or empty.
Use at most {max_passes} retrieval passes.
Stop as soon as the recommendation is stable.

Return strict JSON only.
