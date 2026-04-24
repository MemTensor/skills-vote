## Debug and config notes

Do not read doc/usage_reference.md during normal routing.
Read doc/usage_reference.md only if route_prompt.py fails or you need the legacy direct-use reference.
Read doc/config-schema.md only when you need to create or edit config/config.yaml, or when recommend.py reports a config problem.

recommend.py automatically runs incremental update before querying.
Usually do not run scripts/index.py unless a full rebuild is explicitly needed.
For setup/debug only, you may run:

```bash
uv run -qq python scripts/check_env.py
```
