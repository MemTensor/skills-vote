# Feedback Guide

Read this only when the task is about to finish and you are ready to report what actually happened.

## Request schema

`feedback.py` accepts one JSON object with these fields:

- `session_id` (`str`): The session identifier returned by `recommend.py` for this task.
- `os` (`list[Literal["linux", "macos", "windows"]]`): OS families expected to work on.
- `write_scope` (`Literal["read", "workspace", "system"] | None = None`): Maximum expected write/side-effect scope when running the skill as intended. Return:
  - `read`: no file writes.
  - `workspace`: write only inside the workspace or a dedicated output directory; does not change system settings, services, installed software, or other machine-wide state
  - `system`: writes outside the workspace or dedicated directory, or changes system settings, services, installed software, running processes, or other machine-wide state
- `privilege` (`Literal["rootless", "sudo"] | None = None`): Whether the skill requires elevated privileges.
- `externalty` (`Literal["offline", "online", "secured"] | None = None`): External dependency level. Return:
  - `offline`: no network or external account dependency is part of the core skill workflow
  - `online`: network access is part of the core workflow, but no secrets or privileged account are required. Do not treat incidental dependency installation or one-time setup as `online` unless fetching/deployment/network interaction is itself part of the main skill.
  - `secured`: secrets, authenticated accounts, or protected services are required as part of the core workflow
- `envs` (`list[str]`): Environment variable names referenced or required. Never include values. Ignore any variable whose name starts with `SKILLS_VOTE`.
- `bins` (`list[str]`): Top-level executable command names required/used (canonicalized, lowercase, unversioned). Exclude package names such as `torch`, `nextjs`, etc., unless they are also invoked as standalone executables. Exclude shell builtins and basic OS utilities (e.g., `cp`, `open`, `nohup`, `kill`, and `bash`).
- `mcps` (`list[str]`): MCP server identifiers required/used (canonicalized, unversioned).
- `environment_reason` (`str`): 3-5 sentences evidence-based justification for the environment tags.
- `subtasks` (`list[Subtask]`): A list of substasks whose outcomes and evidence summarize what actually happened during the task.
  - `goal` (`str`): A standalone, explicit, and concise description of the objective. This goal can be fully understandable without context and act as an independent task prompt.
  - `summary` (`str`): A comprehensive, factual summary of the specific actions taken and the environment's responses. Abstract repetitive, low-level commands (e.g., summarize multiple `ls`, `grep`, or `glob` commands simply as `"Explored the codebase to understand the routing logic"`), while explicitly detail the significant actions (e.g., `"Queried the facebook MCP to retrieve user profile data"`).
  - `skills_used` (`list[str]`): A list containing the exact, canonical names of the skills that were ACTUALLY EXECUTED or INVOKED by the agent during this subtask and MUST be a strict subset of the skills recommended in this session.
  - `outcome` (`Literal["success", "partial", "fail"] | None = None`): The rigorously verified result of this subtask. Output `"success"` ONLY IF there is an undeniable, objective signal (e.g., verified file existence, explicit `"successfully installed"` stdout). Output `"fail"` if explicit errors, timeouts, or rejections occurred (e.g., repository not found, permission denied). Output `"partial"` if only a subset of the goal was verifiably achieved. Output `null` if you lack concrete, explicit environmental feedback to definitively prove the result.
  - `reason` (`str`): The exact evidence or environmental feedback that justifies your choice for `"outcome"`. If the outcome is `null`, explicitly state what verification signal was missing.

For any field typed as `... | None = None`, you may either omit the field or send JSON `null`.

All environment fields (`os`, `write_scope`, `privilege`, `externalty`, and `environment_reason`) should describe the runtime required by the agent while executing the skill itself, not the environment of generated outputs, deployed artifacts, or downstream user code.

## Example

Submit feedback with exactly one JSON object on stdin via EOF:

```bash
uv run -qq scripts/feedback.py <<'EOF'
{
  "session_id": "sample-session-id",
  "os": ["macos"],
  "write_scope": "workspace",
  "privilege": "rootless",
  "externalty": "offline",
  "envs": [],
  "bins": ["python", "soffice"],
  "mcps": [],
  "environment_reason": "The agent completed the task entirely on local files inside the workspace. It used Python-based tooling to read a PDF source document, write an XLSX workbook, and attempt a PPTX export, with LibreOffice available for local document handling. No network calls, authenticated services, or MCP servers were required for the core workflow. No step needed elevated privileges or wrote outside the workspace.",
  "subtasks": [
    {
      "goal": "Extract the key financial metrics from a local quarterly PDF report into structured rows.",
      "summary": "Opened the local quarterly report PDF, reviewed the pages containing the revenue and expense tables, and extracted the figures needed for the deliverable. Normalized the metric names so the later workbook would use consistent row labels, then prepared the extracted values in a structured form for export. The work stayed entirely on local files and did not require any network access, credentials, or external services.",
      "skills_used": ["pdf"],
      "outcome": "success",
      "reason": "The PDF content was read successfully and the extracted rows were available for the next workbook-generation step."
    },
    {
      "goal": "Create a spreadsheet that organizes the extracted report metrics into a reusable workbook.",
      "summary": "Created an XLSX workbook in the workspace, added a summary sheet for headline numbers, and populated detailed rows with the metrics extracted from the source PDF. Adjusted headers and cell placement so the workbook matched the requested layout, then checked the generated file after the write step completed. The workbook was produced successfully, but one appendix table from the PDF could not be mapped cleanly because the source rows were malformed and the corresponding worksheet remained incomplete.",
      "skills_used": ["xlsx"],
      "outcome": "partial",
      "reason": "The XLSX workbook was written to the workspace and verified to exist, but the appendix worksheet was incomplete because the extracted source rows could not be parsed into the expected columns."
    },
    {
      "goal": "Generate a presentation deck that summarizes the report findings for a stakeholder update.",
      "summary": "Used the structured metrics from the workbook to assemble slide content for a stakeholder update deck, including headline results, supporting numbers, and a closing summary detailed enough to stand on its own. Attempted to export the resulting presentation to a PPTX file under the workspace output directory, but the local export step failed before the final file was created. No fallback export path succeeded during the task.",
      "skills_used": ["xlsx", "pptx"],
      "outcome": "fail",
      "reason": "The presentation export command returned an error and no PPTX file was present in the expected output path afterward."
    }
  ]
}
EOF
```
