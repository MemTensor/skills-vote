## Retrieval context policy

retrieval_context.mode = recommend_plus_skill_dir

After recommend.py returns candidates, MUST read the SKILL.md for each skill you are about to recommend during recommendation-time evaluation.
MUST perform shallow directory understanding for those candidate skills.
Use the parent directory of each candidate SKILL.md path as <skill_dir>.

Suggested command:

```bash
find <skill_dir> -maxdepth 2 -type f | sort
```

You may read README.md, doc/*.md, docs/*.md, small manifest/config-like files, and a small number of clearly relevant usage scripts.
Skip .git, .venv, node_modules, __pycache__, dist, build, large generated files, binary files, and unrelated deep trees.
This is shallow directory understanding, not a full source audit.
This restriction applies only to recommendation-time evidence, not to execution-time use after a skill has been selected.
