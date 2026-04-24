## Retrieval context policy

retrieval_context.mode = recommend_plus_skill_md

After recommend.py returns candidates, MUST read the SKILL.md for each skill you are about to recommend during recommendation-time evaluation.
When close alternatives matter, read their SKILL.md files too so the final reason can explain the ordering and tradeoff.
Do not scan full candidate directories by default.
This restriction applies only to recommendation-time evidence, not to execution-time use after a skill has been selected.
