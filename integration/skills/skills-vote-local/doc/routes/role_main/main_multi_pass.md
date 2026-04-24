## Required workflow

You are the main agent.
Work from this skill root: {skill_root}

Do not delegate this skill lookup to a subagent.
Rewrite the current user task into a short, standalone, retrieval-oriented query.
Run retrieval with:

```bash
{recommend_command}
```

You may refine the query and run additional retrieval passes when results are ambiguous, too generic, missing key domain terms, overlapping in capability, or empty.
Use at most {max_passes} retrieval passes.
Stop as soon as the recommendation is stable.

After you select a skill, retrieval_context no longer restricts execution-time use of that selected skill.
