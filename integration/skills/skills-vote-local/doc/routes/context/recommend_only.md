## Retrieval context policy

retrieval_context.mode = recommend_only

During retrieval/recommendation, use only recommend.py output fields such as name, description, path, and score.
MUST NOT read candidate skill files.
MUST NOT inspect candidate skill directories.
This restriction applies only to recommendation-time evidence, not to execution-time use after a skill has been selected.
