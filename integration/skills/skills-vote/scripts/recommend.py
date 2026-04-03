# /// script
# dependencies = ["httpx>=0.28.1", "pydantic>=2.12.0", "python-dotenv>=1.2.2"]
# ///

from __future__ import annotations

import sys
from pathlib import Path

from download import download_github_repo_dir
from models import RecommendInput, RecommendResponse
from prompt import (
    DEFAULT_DOWNLOAD_DIR,
    render_auth_error,
    render_download_error,
    render_gateway_busy_error,
    render_gateway_rejected_error,
    render_invalid_response,
    render_local_error,
    render_missing_token,
    render_network_error,
    render_recommend_missing_stdin,
    render_recommend_ready,
    render_recommend_success,
    render_recommend_validation_error,
)
from pydantic import ValidationError
from utils import (
    post_json,
    resolve_api_base_url,
    resolve_api_key,
)

RECOMMEND_ACTION = "recommend"
RECOMMEND_ENDPOINT = "recommend"
ESTIMATED_DOWNLOAD_TIME = "3min"


def prepare_download_dir(download_dir: Path) -> Path | None:
    try:
        resolved = download_dir.resolve()
        resolved.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return resolved


def main() -> int:
    script_path = Path(__file__).resolve()
    skill_root = script_path.parent.parent
    skill_md = script_path.parent.parent / "SKILL.md"
    feedback_guide = script_path.parent.parent / "docs" / "feedback_guide.md"

    try:
        payload = sys.stdin.read().strip()
        if not payload:
            print(
                render_recommend_missing_stdin(script_path, skill_md), file=sys.stderr
            )
            return 1

        api_key = resolve_api_key(skill_root)
        if not api_key:
            print(render_missing_token(), file=sys.stderr)
            return 1
        try:
            request_model = RecommendInput.model_validate_json(payload)
        except ValidationError as error:
            print(
                render_recommend_validation_error(skill_md, str(error)),
                file=sys.stderr,
            )
            return 1

        download_dir = Path(request_model.download_dir or DEFAULT_DOWNLOAD_DIR)
        request_payload = request_model.model_dump(mode="json")
        request_payload.pop("download_dir", None)
        api_base_url = resolve_api_base_url()
        response_result = post_json(
            f"{api_base_url}/{RECOMMEND_ENDPOINT}",
            api_key,
            request_payload,
        )
        if response_result.kind == "http":
            status_code = response_result.status_code or 0
            if status_code in {401, 403}:
                print(render_auth_error(RECOMMEND_ACTION), file=sys.stderr)
                return 1
            if status_code in {408, 429} or status_code >= 500:
                print(
                    render_gateway_busy_error(
                        RECOMMEND_ACTION,
                        status_code,
                        response_result.attempts,
                    ),
                    file=sys.stderr,
                )
                return 1
            print(
                render_gateway_rejected_error(RECOMMEND_ACTION, status_code),
                file=sys.stderr,
            )
            return 1
        if response_result.kind == "transport":
            print(
                render_network_error(
                    RECOMMEND_ACTION,
                    api_base_url,
                    response_result.attempts,
                ),
                file=sys.stderr,
            )
            return 1
        if response_result.kind == "protocol" or response_result.payload is None:
            print(render_invalid_response(RECOMMEND_ACTION), file=sys.stderr)
            return 1

        try:
            response = RecommendResponse.model_validate(response_result.payload["data"])
        except ValidationError:
            print(render_invalid_response(RECOMMEND_ACTION), file=sys.stderr)
            return 1

        resolved_download_dir = prepare_download_dir(download_dir)
        if resolved_download_dir is None:
            print(render_download_error(download_dir.absolute()), file=sys.stderr)
            return 1

        print(
            render_recommend_ready(
                session_id=response.session_id,
                download_dir=resolved_download_dir,
                skills=[
                    (skill.name, skill.description, skill.repo_url)
                    for skill in response.skills
                ],
                reason=response.reason,
                estimated_download_time=ESTIMATED_DOWNLOAD_TIME,
            ),
            flush=True,
        )

        try:
            installed_skills, invalid_token_skills, failed_skills = (
                download_github_repo_dir(
                    [(skill.name, skill.repo_url) for skill in response.skills],
                    resolved_download_dir,
                    progress=lambda message: print(message, flush=True),
                )
            )
        except OSError:
            print(render_download_error(resolved_download_dir), file=sys.stderr)
            return 1

        print(
            render_recommend_success(
                session_id=response.session_id,
                download_dir=resolved_download_dir,
                installed_skills=installed_skills,
                invalid_token_skills=invalid_token_skills,
                failed_skills=failed_skills,
                feedback_guide=feedback_guide,
            ),
            flush=True,
        )
        return 0
    except Exception:
        print(render_local_error(RECOMMEND_ACTION), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
