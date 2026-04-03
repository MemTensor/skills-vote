from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

DEFAULT_DOWNLOAD_DIR = Path(".skills_vote")
DEFAULT_DOWNLOAD_DIR_TEXT = f"{DEFAULT_DOWNLOAD_DIR.as_posix()}/"


def truncate_prefix(text: str, prefix_len: int) -> str:
    return text if len(text) <= prefix_len else f"{text[:prefix_len]}..."


def render_missing_token() -> str:
    return """
SKILLS_VOTE_API_KEY is required to request recommendations and submit runtime feedback.
Try to read the environment again. If you still cannot access the API key, ask the user to provide or set it.
If no valid API key is available, stop using this skill.
""".strip()


def render_recommend_missing_stdin(script_path: Path, skill_md: Path) -> str:
    return f"""
Skill recommendation requires exactly one JSON object on stdin via EOF.
Your current invocation is missing that payload or the EOF block is malformed.
Read only this file and follow the "Recommend" section: `{skill_md}`
Use this example shape:
```bash
uv run -qq {script_path} <<'EOF'
{{
  "query": "user task or intent",
  "client_name": "codex",
  "client_version": "0.117.0",
  "download_dir": "{DEFAULT_DOWNLOAD_DIR_TEXT}"
}}
EOF
```
""".strip()


def render_recommend_validation_error(skill_md: Path, detail: str) -> str:
    return f"""
Skill recommendation input is invalid.
Read only this file and fix the request body before retrying: `{skill_md}`
Validation details:
{detail.strip()}
""".strip()


def render_feedback_validation_error(guide_path: Path, detail: str) -> str:
    return f"""
Runtime feedback input is invalid.
Read the feedback guide, then fix the request body before retrying: `{guide_path}`
Validation details:
{detail.strip()}
""".strip()


def render_invalid_response(action: str) -> str:
    return f"""
The {action} step returned invalid data. This is an internal backend error.
Do not try to repair the response locally. Stop using this skill for this task.
""".strip()


def render_local_error(action: str) -> str:
    return f"""
The local client hit an unexpected error while running the {action} step.
Do not try to recover by guessing new fields or reading traceback output. Stop using this skill for this task.
""".strip()


def render_auth_error(action: str) -> str:
    return f"""
The {action} step was rejected because SKILLS_VOTE_API_KEY is missing, invalid, or unauthorized.
Try to read the API key again or ask the user to provide or set it. If you still cannot obtain a valid API key, stop using this skill.
""".strip()


def render_network_error(action: str, base_url: str, attempts: int) -> str:
    return f"""
The {action} step could not reach the backend at `{base_url}`.
The local client retried {attempts} times automatically and still could not connect.
This looks like a client-side network problem. Ask the user to enable network access,
then retry this skill.
""".strip()


def render_gateway_busy_error(action: str, status_code: int, attempts: int) -> str:
    return f"""
The {action} step failed because the backend returned HTTP {status_code}.
The local client retried {attempts} times automatically and the backend is still
unavailable. Treat this as an internal backend error and stop using this skill for
this task.
""".strip()


def render_gateway_rejected_error(action: str, status_code: int) -> str:
    return f"""
The {action} step was rejected by the backend with HTTP {status_code}.
This is not a local formatting issue anymore. Do not keep changing fields blindly.
Stop using this skill unless the user gives you a different backend or instructions.
""".strip()


def render_download_error(download_dir: Path) -> str:
    return f"""
The recommendation request succeeded, but `download_dir` is invalid or not writable in the current environment: `{download_dir}`
Choose a different download_dir inside the current workspace or stop using this skill.
""".strip()


def render_recommend_ready(
    session_id: str,
    download_dir: Path,
    skills: Iterable[tuple[str, str, str]],
    reason: str,
    estimated_download_time: str,
    description_prefix_len: int = 80,
) -> str:
    skills = list(skills)
    reason = reason.strip()
    skills_block = "\n".join(
        (f"- `{name}`: {truncate_prefix(description, description_prefix_len)}")
        for name, description, _repo_url in skills
    )
    guidance_block = f"\n\nRecommendation guidance: {reason}" if reason else ""
    return f"""
Recommended {len(skills)} skills:
{skills_block}
{guidance_block}

Session ID: {session_id}
Starting download of {len(skills)} skills to {download_dir}. Estimated time: {estimated_download_time}.
""".strip()


def render_recommend_success(
    session_id: str,
    download_dir: Path,
    installed_skills: Iterable[str],
    invalid_token_skills: Iterable[str],
    failed_skills: Iterable[str],
    feedback_guide: Path,
) -> str:
    installed_skills = list(installed_skills)
    invalid_token_skills = list(invalid_token_skills)
    failed_skills = list(failed_skills)
    installed_block = ", ".join(f"`{name}`" for name in installed_skills) or "none"
    if installed_skills and not invalid_token_skills and not failed_skills:
        download_block = f"All skills downloaded successfully to {download_dir}."
    elif not installed_skills:
        download_block = f"All skills failed to download to {download_dir}."
        if invalid_token_skills and not failed_skills:
            download_block += " Invalid `GITHUB_TOKEN` or `GH_TOKEN`."
        elif invalid_token_skills:
            download_block += (
                " Some failures were caused by invalid `GITHUB_TOKEN` or `GH_TOKEN`."
            )
    else:
        installed_count = len(installed_skills)
        installed_label = "skill" if installed_count == 1 else "skills"
        failed_entries = [
            f"`{name}` (invalid `GITHUB_TOKEN` or `GH_TOKEN`)"
            for name in invalid_token_skills
        ] + [f"`{name}`" for name in failed_skills]
        failed_count = len(failed_entries)
        failed_label = "skill" if failed_count == 1 else "skills"
        download_block = (
            f"Downloaded {installed_count} {installed_label} successfully to {download_dir}: "
            f"{installed_block}\n"
            f"Failed to download {failed_count} {failed_label}: "
            + ", ".join(failed_entries)
        )
    return f"""
{download_block}

Reminder:
- Remember this session ID for feedback: {session_id}
- When the task is almost done, read the feedback guide: `{feedback_guide}`
- Feedback should capture the task trajectory, the subtasks you actually performed, the skills you actually used, and the runtime environment that mattered.
""".strip()


def render_feedback_guide(guide_path: Path, script_path: Path) -> str:
    return f"""
Submit runtime feedback only when the task is about to finish.
Read the feedback guide: `{guide_path}`

Submit with:
  uv run -qq {script_path} <<'EOF'
  {{
    ...
  }}
  EOF
""".strip()


def render_feedback_success(session_id: str) -> str:
    return f"""
Runtime feedback accepted.
Session ID: {session_id}
You can stop using this skill for this task.
""".strip()
