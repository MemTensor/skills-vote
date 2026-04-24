## Required workflow

You are the main agent.
Work from this skill root: {skill_root}

Do not delegate this skill lookup to a subagent.
Rewrite the current user task into a short, standalone, retrieval-oriented query.
Run one planned retrieval pass:

```bash
{recommend_command}
```

Single-pass mode means one planned recommend.py call.
You may perform one corrective retrieval only if the first call fails, returns no usable candidates, or the query was clearly malformed.
Do not do exploratory query refinement in single-pass mode.

After you select a skill, retrieval_context no longer restricts execution-time use of that selected skill.
