from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx

DEFAULT_BASE_URL = "https://api.skills.vote/api/v1"
RETRY_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 180.0
API_KEY_ENV_NAME = "SKILLS_VOTE_API_KEY"


@dataclass(frozen=True)
class PostJSONResult:
    kind: Literal["ok", "http", "transport", "protocol"]
    payload: dict[str, Any] | None = None
    status_code: int | None = None
    attempts: int = 1


def resolve_api_base_url() -> str:
    return (os.environ.get("SKILLS_VOTE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def resolve_api_key(skill_root: Path) -> str | None:
    env_path = skill_root / ".env"
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            key, value = line.split("=", 1)
            os.environ[key] = value
    return os.environ.get(API_KEY_ENV_NAME)


def _post_json_once(url: str, api_key: str, payload: dict[str, Any]) -> PostJSONResult:
    try:
        response = httpx.post(
            url,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={
                "Authorization": f"api_key {api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        return PostJSONResult(kind="http", status_code=error.response.status_code)
    except httpx.HTTPError:
        return PostJSONResult(kind="transport")
    if not response.content:
        return PostJSONResult(kind="ok", payload={"accepted": True})
    try:
        return PostJSONResult(kind="ok", payload=response.json())
    except ValueError:
        return PostJSONResult(kind="protocol")


def is_retryable_result(result: PostJSONResult) -> bool:
    return result.kind == "transport" or (
        result.kind == "http"
        and result.status_code is not None
        and (result.status_code in {408, 429} or result.status_code >= 500)
    )


def post_json(
    url: str,
    api_key: str,
    payload: dict[str, Any],
    retry_attempts: int = RETRY_ATTEMPTS,
) -> PostJSONResult:
    last_result = PostJSONResult(kind="transport", attempts=retry_attempts)
    for attempt in range(1, retry_attempts + 1):
        result = _post_json_once(url, api_key, payload)
        result = PostJSONResult(
            kind=result.kind,
            payload=result.payload,
            status_code=result.status_code,
            attempts=attempt,
        )
        if not is_retryable_result(result) or attempt == retry_attempts:
            return result
        last_result = result
    return last_result
