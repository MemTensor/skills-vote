from __future__ import annotations

import asyncio
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from time import monotonic
from urllib.parse import quote, unquote, urlsplit

TEMP_DIR_PREFIX = ".skills-vote-"
USER_AGENT = "skills-vote"
DOWNLOAD_PROGRESS_INTERVAL_SECONDS = 5.0
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
DOWNLOAD_CONCURRENCY = 32
DOWNLOAD_RETRIES = 3
GITHUB_API_ROOT = "https://api.github.com"


class InvalidGitHubTokenError(Exception):
    pass


def download_github_repo_dir(
    skills: list[tuple[str, str]],
    target_dir: Path,
    progress: Callable[[str], None],
) -> tuple[list[str], list[str], list[str]]:
    target_dir.mkdir(parents=True, exist_ok=True)
    statuses = [""] * len(skills)
    pending: list[tuple[int, str, str]] = []
    finished = 0
    total = len(skills)

    for index, (skill_name, repo_url) in enumerate(skills):
        if (target_dir / skill_name).exists():
            statuses[index] = "installed"
            finished += 1
            progress(f"`{skill_name}` already exists ({finished}/{total})")
        else:
            pending.append((index, skill_name, repo_url))

    if pending:
        for index, status in asyncio.run(
            _download_pending(pending, target_dir, progress, finished, total)
        ).items():
            statuses[index] = status

    installed = [
        skills[index][0]
        for index, status in enumerate(statuses)
        if status == "installed"
    ]
    invalid_token = [
        skills[index][0]
        for index, status in enumerate(statuses)
        if status == "invalid_token"
    ]
    failed = [
        skills[index][0] for index, status in enumerate(statuses) if status == "failed"
    ]
    return installed, invalid_token, failed


async def _download_pending(
    pending: list[tuple[int, str, str]],
    target_dir: Path,
    progress: Callable[[str], None],
    finished: int,
    total: int,
) -> dict[int, str]:
    import httpx

    token = _github_token()
    semaphore = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)
    downloaded_bytes = 0
    next_report_at = monotonic() + DOWNLOAD_PROGRESS_INTERVAL_SECONDS
    results: dict[int, str] = {}

    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"token {token}"

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=60.0,
        limits=httpx.Limits(
            max_connections=DOWNLOAD_CONCURRENCY,
            max_keepalive_connections=DOWNLOAD_CONCURRENCY,
        ),
    ) as client:

        def on_chunk(chunk_size: int) -> None:
            nonlocal downloaded_bytes, next_report_at
            downloaded_bytes += chunk_size
            if monotonic() < next_report_at:
                return
            progress(f"Downloaded {downloaded_bytes / 1024:.1f} KB")
            next_report_at = monotonic() + DOWNLOAD_PROGRESS_INTERVAL_SECONDS

        async def request(
            url: str,
            *,
            headers: dict[str, str] | None = None,
            target_path: Path | None = None,
        ) -> bytes | None:
            for attempt in range(DOWNLOAD_RETRIES):
                try:
                    async with semaphore:
                        if target_path is None:
                            response = await client.get(url, headers=headers)
                            response.raise_for_status()
                            return response.content
                        async with client.stream(
                            "GET", url, headers=headers
                        ) as response:
                            response.raise_for_status()
                            with target_path.open("wb") as target_file:
                                async for chunk in response.aiter_bytes(
                                    DOWNLOAD_CHUNK_SIZE
                                ):
                                    target_file.write(chunk)
                                    on_chunk(len(chunk))
                            return None
                except httpx.HTTPStatusError as error:
                    if token and error.response.status_code in {401, 403}:
                        raise InvalidGitHubTokenError from error
                    if attempt == DOWNLOAD_RETRIES - 1:
                        raise
                except httpx.HTTPError:
                    if attempt == DOWNLOAD_RETRIES - 1:
                        raise
            raise RuntimeError("unreachable")

        async def github_contents(
            owner: str, repo: str, commit: str, path: Path
        ) -> dict | list:
            encoded_path = "/".join(quote(part, safe="") for part in path.parts)
            url = (
                f"{GITHUB_API_ROOT}/repos/{quote(owner, safe='')}/"
                f"{quote(repo, safe='')}/contents"
                f"{f'/{encoded_path}' if encoded_path else ''}?ref={quote(commit, safe='')}"
            )
            return json.loads(
                (
                    await request(
                        url, headers={"Accept": "application/vnd.github+json"}
                    )
                    or b"null"
                ).decode()
            )

        async def download_dir(
            owner: str, repo: str, commit: str, remote_dir: Path, local_dir: Path
        ) -> None:
            items = await github_contents(owner, repo, commit, remote_dir)
            if not isinstance(items, list):
                raise ValueError(f"{remote_dir.as_posix()} is not a directory")
            local_dir.mkdir(parents=True, exist_ok=True)
            await asyncio.gather(
                *[
                    download_dir(
                        owner, repo, commit, item_path, local_dir / item_path.name
                    )
                    if item.get("type") == "dir"
                    else request(
                        item["url"],
                        headers={"Accept": "application/vnd.github.raw"},
                        target_path=local_dir / item_path.name,
                    )
                    for item in items
                    for item_path in [Path(item["path"])]
                    if item.get("type") in {"dir", "file"}
                ]
            )

        async def download_skill(
            index: int, skill_name: str, repo_url: str
        ) -> tuple[int, str, str]:
            try:
                owner, repo, commit, skill_path = _resolve_skill_repo(repo_url)
                skill_md = await github_contents(
                    owner, repo, commit, skill_path / "SKILL.md"
                )
                if not isinstance(skill_md, dict) or skill_md.get("type") != "file":
                    raise ValueError("missing SKILL.md")
                with tempfile.TemporaryDirectory(
                    prefix=TEMP_DIR_PREFIX, dir=target_dir
                ) as tmp_dir:
                    skill_dir = Path(tmp_dir) / "skill"
                    await download_dir(owner, repo, commit, skill_path, skill_dir)
                    skill_dir.rename(target_dir / skill_name)
                return index, skill_name, "installed"
            except InvalidGitHubTokenError:
                return index, skill_name, "invalid_token"
            except Exception:
                return index, skill_name, "failed"

        tasks = [
            asyncio.create_task(download_skill(index, skill_name, repo_url))
            for index, skill_name, repo_url in pending
        ]
        for task in asyncio.as_completed(tasks):
            index, skill_name, status = await task
            results[index] = status
            finished += 1
            if status == "installed":
                progress(f"Downloaded `{skill_name}` ({finished}/{total})")
            elif status == "invalid_token":
                progress(
                    f"Failed `{skill_name}`: invalid `GITHUB_TOKEN` or `GH_TOKEN` "
                    f"({finished}/{total})"
                )
            else:
                progress(f"Failed `{skill_name}` ({finished}/{total})")
    return results


def _resolve_skill_repo(repo_url: str) -> tuple[str, str, str, Path]:
    parsed = urlsplit(repo_url)
    if parsed.netloc != "github.com":
        raise ValueError("unsupported host")
    owner, repo, _tree, commit, *rest = [
        unquote(part) for part in parsed.path.split("/") if part
    ]
    return owner, repo, commit, Path(*[part for part in rest if part != "."])


def _github_token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
