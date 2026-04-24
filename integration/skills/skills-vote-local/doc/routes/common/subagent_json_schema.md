## Final response contract

Return strict JSON only. Do not use Markdown, bullets, code fences, or explanation outside the JSON object.

Use this exact schema:

The fenced block below is only a schema example. Your final response must not include code fences.

```json
{
  "skills": [
    {
      "name": "string",
      "description": "string",
      "path": "string"
    }
  ],
  "reason": "string"
}
```

Rules:

- Use only the top-level fields `skills` and `reason`.
- Each item in `skills` must contain only `name`, `description`, and `path`.
- Order `skills` by recommendation priority.
- Do not add score-like fields.
- If there is no usable skill, return `{"skills": [], "reason": "No usable skill was found because ..."}`.
