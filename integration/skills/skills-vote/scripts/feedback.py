# /// script
# dependencies = ["httpx>=0.28.1", "pydantic>=2.12.0", "python-dotenv>=1.2.2"]
# ///

from __future__ import annotations

import sys
from pathlib import Path

from models import FeedbackRequest, FeedbackResponse
from prompt import (
    render_auth_error,
    render_feedback_guide,
    render_feedback_success,
    render_feedback_validation_error,
    render_gateway_busy_error,
    render_gateway_rejected_error,
    render_invalid_response,
    render_local_error,
    render_missing_token,
    render_network_error,
)
from pydantic import ValidationError
from utils import (
    post_json,
    resolve_api_base_url,
    resolve_api_key,
)

FEEDBACK_ACTION = "feedback"
FEEDBACK_ENDPOINT = "feedback/insert"


def print_guide() -> int:
    script_path = Path(__file__).resolve()
    guide_path = Path(__file__).resolve().parent.parent / "docs" / "feedback_guide.md"
    print(render_feedback_guide(guide_path=guide_path, script_path=script_path))
    return 0


def main() -> int:
    script_path = Path(__file__).resolve()
    skill_root = script_path.parent.parent
    guide_path = script_path.parent.parent / "docs" / "feedback_guide.md"

    try:
        payload = sys.stdin.read().strip()
        if not payload:
            return print_guide()

        api_key = resolve_api_key(skill_root)
        if not api_key:
            print(render_missing_token(), file=sys.stderr)
            return 1
        try:
            request_model = FeedbackRequest.model_validate_json(payload)
        except ValidationError as error:
            print(
                render_feedback_validation_error(guide_path, str(error)),
                file=sys.stderr,
            )
            return 1

        api_base_url = resolve_api_base_url()
        response_result = post_json(
            f"{api_base_url}/{FEEDBACK_ENDPOINT}",
            api_key,
            request_model.model_dump(mode="json"),
        )
        if response_result.kind == "http":
            status_code = response_result.status_code or 0
            if status_code in {401, 403}:
                print(render_auth_error(FEEDBACK_ACTION), file=sys.stderr)
                return 1
            if status_code in {408, 429} or status_code >= 500:
                print(
                    render_gateway_busy_error(
                        FEEDBACK_ACTION,
                        status_code,
                        response_result.attempts,
                    ),
                    file=sys.stderr,
                )
                return 1
            print(
                render_gateway_rejected_error(FEEDBACK_ACTION, status_code),
                file=sys.stderr,
            )
            return 1
        if response_result.kind == "transport":
            print(
                render_network_error(
                    FEEDBACK_ACTION,
                    api_base_url,
                    response_result.attempts,
                ),
                file=sys.stderr,
            )
            return 1
        if response_result.kind == "protocol" or response_result.payload is None:
            print(render_invalid_response(FEEDBACK_ACTION), file=sys.stderr)
            return 1

        try:
            FeedbackResponse.model_validate(response_result.payload["data"])
        except ValidationError:
            print(render_invalid_response(FEEDBACK_ACTION), file=sys.stderr)
            return 1

        print(render_feedback_success(request_model.session_id))
        return 0
    except Exception:
        print(render_local_error(FEEDBACK_ACTION), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
