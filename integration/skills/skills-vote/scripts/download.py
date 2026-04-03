from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from shutil import copytree
from time import monotonic
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from zipfile import ZipFile

TEMP_DIR_PREFIX = ".skills-vote-"
USER_AGENT = "skills-vote"
DOWNLOAD_PROGRESS_INTERVAL_SECONDS = 5.0
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


class InvalidGitHubTokenError(Exception):
    pass


def download_github_repo_dir(
    skills: list[tuple[str, str]],
    target_dir: Path,
    progress: Callable[[str], None] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    emit = progress or (lambda _message: None)
    target_dir.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    invalid_token: list[str] = []
    failed: list[str] = []
    total = len(skills)
    for index, (skill_name, repo_url) in enumerate(skills, start=1):
        label = f"Skill {index}/{total}"
        emit(f"{label}: downloading `{skill_name}`")
        try:
            archive_url, skill_path, skill_md_url = _resolve_skill_urls(repo_url)
            _request(skill_md_url)
            with tempfile.TemporaryDirectory(
                prefix=TEMP_DIR_PREFIX, dir=target_dir
            ) as tmp_dir:
                archive_path = _download_repo_archive(
                    archive_url,
                    Path(tmp_dir),
                    progress=lambda downloaded_bytes: emit(
                        f"{label}: {_format_megabytes(downloaded_bytes)} MB downloaded"
                    ),
                )
                emit(f"{label}: download complete")
                emit(f"{label}: extracting")
                repo_root = _extract_repo_archive(archive_path, Path(tmp_dir))
                skill_dir = repo_root / skill_path
                dest_dir = target_dir / skill_name
                if dest_dir.exists():
                    emit(f"{label}: failed")
                    failed.append(skill_name)
                    continue
                copytree(skill_dir, dest_dir)
                emit(f"{label}: extraction complete")
            installed.append(skill_name)
        except InvalidGitHubTokenError:
            emit(f"{label}: failed, invalid `GITHUB_TOKEN` or `GH_TOKEN`")
            invalid_token.append(skill_name)
        except Exception:
            emit(f"{label}: failed")
            failed.append(skill_name)
    return installed, invalid_token, failed


def _resolve_skill_urls(repo_url: str) -> tuple[str, Path, str]:
    parsed = urlsplit(repo_url)
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    owner = parts[0]
    repo = parts[1]
    commit = parts[3]
    skill_parts = [part for part in parts[4:] if part != "."]
    skill_path = Path(*skill_parts) if skill_parts else Path()
    skill_md_path = (skill_path / "SKILL.md").as_posix()
    archive_netloc = (
        "codeload.github.com" if parsed.netloc == "github.com" else parsed.netloc
    )
    archive_path = (
        f"/{owner}/{repo}/zip/{commit}"
        if parsed.netloc == "github.com"
        else f"/{owner}/{repo}/archive/{commit}.zip"
    )
    archive_url = urlunsplit(
        (parsed.scheme or "https", archive_netloc, archive_path, "", "")
    )
    skill_md_url = urlunsplit(
        parsed._replace(
            path=f"/{owner}/{repo}/blob/{commit}/{skill_md_path}",
            query="",
            fragment="",
        )
    )
    return archive_url, skill_path, skill_md_url


def _format_megabytes(byte_count: int) -> str:
    return f"{byte_count / (1024 * 1024):.1f}"


def _download_repo_archive(
    archive_url: str,
    target_dir: Path,
    progress: Callable[[int], None] | None = None,
) -> Path:
    archive_path = target_dir / "repo.zip"
    _request(archive_url, target_path=archive_path, progress=progress)
    return archive_path


def _extract_repo_archive(archive_path: Path, target_dir: Path) -> Path:
    with ZipFile(archive_path) as archive:
        root = next(name.split("/")[0] for name in archive.namelist() if name)
        archive.extractall(target_dir)
    return target_dir / root


def _github_token(url: str) -> str | None:
    if not urlsplit(url).netloc.endswith("github.com"):
        return None
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def _request_once(
    url: str,
    token: str | None = None,
    target_path: Path | None = None,
    progress: Callable[[int], None] | None = None,
) -> bytes | None:
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"token {token}"
    request = Request(url, headers=headers)
    with urlopen(request) as response:
        if target_path is not None:
            downloaded_bytes = 0
            next_report_at = monotonic() + DOWNLOAD_PROGRESS_INTERVAL_SECONDS
            with target_path.open("wb") as target_file:
                while chunk := response.read(DOWNLOAD_CHUNK_SIZE):
                    target_file.write(chunk)
                    downloaded_bytes += len(chunk)
                    if progress is not None and monotonic() >= next_report_at:
                        progress(downloaded_bytes)
                        next_report_at = (
                            monotonic() + DOWNLOAD_PROGRESS_INTERVAL_SECONDS
                        )
            return None
        return response.read()


def _request(
    url: str,
    target_path: Path | None = None,
    progress: Callable[[int], None] | None = None,
) -> bytes | None:
    token = _github_token(url)
    try:
        return _request_once(url, target_path=target_path, progress=progress)
    except HTTPError:
        if not token:
            raise
    try:
        return _request_once(
            url,
            token,
            target_path=target_path,
            progress=progress,
        )
    except HTTPError as error:
        if error.code in {401, 403}:
            raise InvalidGitHubTokenError from error
        raise
