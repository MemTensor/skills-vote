## Required workflow

You are the delegated subagent.
Work from this skill root: {skill_root}

Rewrite the handoff task into a short, standalone, retrieval-oriented query.
Run one planned retrieval pass:

```bash
{recommend_command}
```

Single-pass mode means one planned recommend.py call.
You may perform one corrective retrieval only if the first call fails, returns no usable candidates, or the query was clearly malformed.
Do not do exploratory query refinement in single-pass mode.

Return strict JSON only.
