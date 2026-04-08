from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from time import monotonic
from typing import TypedDict, cast
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen

TEMP_DIR_PREFIX = ".skills-vote-"
USER_AGENT = "skills-vote"
DOWNLOAD_PROGRESS_INTERVAL_SECONDS = 3.0
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
GITHUB_API_ROOT = "https://api.github.com"


class InvalidGitHubTokenError(Exception):
    pass


class GitHubContentItem(TypedDict):
    type: str
    path: str
    url: str


def download_github_repo_dir(
    skills: list[tuple[str, str]],
    target_dir: Path,
    progress: Callable[[str], None],
) -> tuple[list[str], list[str], list[str]]:
    emit = progress
    target_dir.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    invalid_token: list[str] = []
    failed: list[str] = []
    total = len(skills)
    for index, (skill_name, repo_url) in enumerate(skills, start=1):
        label = f"Skill {index}/{total}"
        dest_dir = target_dir / skill_name
        if dest_dir.exists():
            emit(f"{label}: `{skill_name}` already exists")
            installed.append(skill_name)
            continue
        emit(f"{label}: downloading `{skill_name}`")
        try:
            owner, repo, commit, skill_path = _resolve_skill_repo(repo_url)
            skill_md = _github_contents(owner, repo, commit, skill_path / "SKILL.md")
            if not isinstance(skill_md, dict) or skill_md["type"] != "file":
                raise ValueError("missing SKILL.md")
            with tempfile.TemporaryDirectory(
                prefix=TEMP_DIR_PREFIX, dir=target_dir
            ) as tmp_dir:
                downloaded_bytes = 0
                next_report_at = monotonic() + DOWNLOAD_PROGRESS_INTERVAL_SECONDS

                def on_chunk(chunk_size: int, *, _label: str = label) -> None:
                    nonlocal downloaded_bytes, next_report_at
                    downloaded_bytes += chunk_size
                    if monotonic() < next_report_at:
                        return
                    emit(
                        f"{_label}: {downloaded_bytes / (1024 * 1024):.1f} MB downloaded"
                    )
                    next_report_at = monotonic() + DOWNLOAD_PROGRESS_INTERVAL_SECONDS

                skill_dir = Path(tmp_dir) / "skill"
                _download_github_dir(
                    owner,
                    repo,
                    commit,
                    skill_path,
                    skill_dir,
                    progress=on_chunk,
                )
                skill_dir.rename(dest_dir)
                emit(f"{label}: download complete")
            installed.append(skill_name)
        except InvalidGitHubTokenError:
            emit(f"{label}: failed, invalid `GITHUB_TOKEN` or `GH_TOKEN`")
            invalid_token.append(skill_name)
        except Exception:
            emit(f"{label}: failed")
            failed.append(skill_name)
    return installed, invalid_token, failed


def _resolve_skill_repo(repo_url: str) -> tuple[str, str, str, Path]:
    parsed = urlsplit(repo_url)
    if parsed.netloc != "github.com":
        raise ValueError("unsupported host")
    owner, repo, _tree, commit, *rest = [
        unquote(part) for part in parsed.path.split("/") if part
    ]
    return owner, repo, commit, Path(*[part for part in rest if part != "."])


def _github_contents(
    owner: str, repo: str, commit: str, path: Path
) -> GitHubContentItem | list[GitHubContentItem]:
    encoded_path = "/".join(quote(part, safe="") for part in path.parts)
    url = (
        f"{GITHUB_API_ROOT}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/contents"
        f"{f'/{encoded_path}' if encoded_path else ''}?ref={quote(commit, safe='')}"
    )
    return cast(
        GitHubContentItem | list[GitHubContentItem],
        json.loads(
            (
                _request(url, headers={"Accept": "application/vnd.github+json"})
                or b"null"
            ).decode()
        ),
    )


def _download_github_dir(
    owner: str,
    repo: str,
    commit: str,
    remote_dir: Path,
    local_dir: Path,
    progress: Callable[[int], None] | None = None,
) -> None:
    items = _github_contents(owner, repo, commit, remote_dir)
    if not isinstance(items, list):
        raise ValueError(f"{remote_dir.as_posix()} is not a directory")
    local_dir.mkdir(parents=True, exist_ok=True)
    for item in items:
        item_path = Path(item["path"])
        if item.get("type") == "dir":
            _download_github_dir(
                owner,
                repo,
                commit,
                item_path,
                local_dir / item_path.name,
                progress=progress,
            )
            continue
        if item.get("type") != "file":
            continue
        _request(
            item["url"],
            target_path=local_dir / item_path.name,
            progress=progress,
            headers={"Accept": "application/vnd.github.raw"},
        )


def _github_token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def _request_once(
    url: str,
    token: str | None = None,
    target_path: Path | None = None,
    progress: Callable[[int], None] | None = None,
    headers: dict[str, str] | None = None,
) -> bytes | None:
    headers = {"User-Agent": USER_AGENT, **(headers or {})}
    if token:
        headers["Authorization"] = f"token {token}"
    request = Request(url, headers=headers)
    with urlopen(request) as response:
        if target_path is not None:
            with target_path.open("wb") as target_file:
                while chunk := response.read(DOWNLOAD_CHUNK_SIZE):
                    target_file.write(chunk)
                    if progress is not None:
                        progress(len(chunk))
            return None
        return response.read()


def _request(
    url: str,
    target_path: Path | None = None,
    progress: Callable[[int], None] | None = None,
    headers: dict[str, str] | None = None,
) -> bytes | None:
    token = _github_token()
    try:
        return _request_once(
            url,
            target_path=target_path,
            progress=progress,
            headers=headers,
        )
    except HTTPError:
        if not token:
            raise
    try:
        return _request_once(
            url,
            token,
            target_path=target_path,
            progress=progress,
            headers=headers,
        )
    except HTTPError as error:
        if error.code in {401, 403}:
            raise InvalidGitHubTokenError from error
        raise
