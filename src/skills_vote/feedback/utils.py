from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import shortuuid
from harbor.models.trial.result import TrialResult

from skills_vote.feedback.model import FeedbackOutputPayload, FeedbackPayload


def read_ctrf_verifier_feedback(trial_dir: Path) -> dict[str, Any]:
    ctrf_path = trial_dir / "verifier" / "ctrf.json"
    if not ctrf_path.exists():
        raise RuntimeError(
            "feedback missing verifier feedback:"
            f"expected ctrf.json in {ctrf_path.parent}, found 0"
        )

    try:
        ctrf_payload = json.loads(ctrf_path.read_text(encoding="utf-8"))
        results = ctrf_payload["results"]
        summary = results["summary"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError(
            f"feedback missing verifier feedback:invalid ctrf payload in {ctrf_path}"
        ) from exc

    failed_tests = [
        {
            key: test[key]
            for key in ("name", "file_path", "message")
            if key in test and test[key] is not None
        }
        for test in results.get("tests", [])
        if test.get("status") == "failed"
    ]
    return {
        "tool": results.get("tool"),
        "summary": {
            key: summary[key]
            for key in ("tests", "passed", "failed", "skipped", "pending", "other")
            if key in summary and summary[key] is not None
        },
        "failed_tests": failed_tests,
    }


def extract_test_case_counts(
    result: TrialResult,
    trial_dir: Path,
    extractors: list[str],
) -> tuple[int, int, int]:
    errors: list[str] = []
    for extractor in extractors:
        try:
            match extractor:
                case "ctrf":
                    return extract_ctrf_test_case_counts(trial_dir)
                case "pytest_stdout":
                    return extract_pytest_stdout_test_case_counts(trial_dir)
                case "output_json":
                    return extract_output_json_test_case_counts(trial_dir)
                case "reward":
                    return extract_reward_test_case_counts(result)
                case _:
                    raise RuntimeError(
                        f"unknown verifier summary extractor {extractor}"
                    )
        except RuntimeError as exc:
            errors.append(f"{extractor}: {exc}")

    raise RuntimeError(
        "feedback missing verifier feedback:"
        "all configured verifier summary extractors failed: " + "; ".join(errors)
    )


def extract_ctrf_test_case_counts(trial_dir: Path) -> tuple[int, int, int]:
    verifier_feedback = read_ctrf_verifier_feedback(trial_dir)

    summary = verifier_feedback["summary"]
    total = summary.get("tests")
    passed = summary.get("passed")
    failed = summary.get("failed")
    if isinstance(total, int) and isinstance(passed, int) and isinstance(failed, int):
        return total, passed, failed

    ctrf_path = trial_dir / "verifier" / "ctrf.json"
    raise RuntimeError(f"invalid ctrf summary counts in {ctrf_path}")


def extract_pytest_stdout_test_case_counts(trial_dir: Path) -> tuple[int, int, int]:
    stdout_path = trial_dir / "verifier" / "test-stdout.txt"
    if not stdout_path.exists():
        raise RuntimeError(
            "feedback missing verifier feedback:"
            f"expected pytest summary in {stdout_path}"
        )

    stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
    counts = parse_pytest_summary_counts(stdout)
    if counts is None:
        raise RuntimeError(
            "feedback missing verifier feedback:"
            f"could not parse pytest summary in {stdout_path}"
        )
    return counts


def parse_pytest_summary_counts(stdout: str) -> tuple[int, int, int] | None:
    status_counts = parse_pytest_final_summary_line(stdout)
    if status_counts is None:
        status_counts = parse_pytest_short_summary_lines(stdout)
    if status_counts is None:
        return None

    passed = status_counts.get("passed", 0)
    failed = status_counts.get("failed", 0) + status_counts.get("error", 0)
    total = sum(
        status_counts.get(status, 0)
        for status in ("passed", "failed", "error", "skipped", "xfailed", "xpassed")
    )
    if total == 0:
        return None
    return total, passed, failed


def parse_pytest_final_summary_line(stdout: str) -> dict[str, int] | None:
    for line in reversed(stdout.splitlines()):
        body = line.strip("= ").strip()
        if " in " not in body:
            continue

        matches = re.findall(
            r"(\d+)\s+"
            r"(passed|failed|errors?|skipped|xfailed|xpassed|warnings?)\b",
            body,
        )
        if not matches:
            continue

        counts: dict[str, int] = {}
        for value, status in matches:
            if status.startswith("warning"):
                continue
            counts[status.rstrip("s")] = int(value)
        if counts:
            return counts
    return None


def parse_pytest_short_summary_lines(stdout: str) -> dict[str, int] | None:
    counts: dict[str, int] = {}
    for line in stdout.splitlines():
        match = re.match(r"^\s*(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\s+", line)
        if match is None:
            continue
        status = match.group(1).lower()
        if status == "xfail":
            status = "xfailed"
        elif status == "xpass":
            status = "xpassed"
        counts[status] = counts.get(status, 0) + 1

    return counts or None


def extract_output_json_test_case_counts(trial_dir: Path) -> tuple[int, int, int]:
    output_path = trial_dir / "verifier" / "output.json"
    if not output_path.exists():
        raise RuntimeError(f"expected verifier output JSON in {output_path}")

    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        tests = payload["tests"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError(f"invalid verifier output JSON in {output_path}") from exc

    if not isinstance(tests, list):
        raise RuntimeError(f"invalid verifier output tests list in {output_path}")

    counts = parse_test_status_counts(tests)
    if counts is None:
        raise RuntimeError(f"could not parse verifier output tests in {output_path}")
    return counts


def parse_test_status_counts(tests: list[Any]) -> tuple[int, int, int] | None:
    if not tests:
        return None

    passed = 0
    failed = 0
    total = 0
    for test in tests:
        if not isinstance(test, dict):
            continue
        status = str(test.get("status", "")).strip().lower()
        if not status:
            continue

        total += 1
        if status in {"pass", "passed", "success", "ok"}:
            passed += 1
        elif status in {"fail", "failed", "failure", "error", "errored"}:
            failed += 1

    if total == 0:
        return None
    return total, passed, failed


def extract_reward_test_case_counts(result: TrialResult) -> tuple[int, int, int]:
    if result.verifier_result is None or not result.verifier_result.rewards:
        raise RuntimeError(
            "feedback missing verifier feedback:"
            "expected verifier_result.rewards in Harbor trial result"
        )

    rewards = result.verifier_result.rewards
    reward = rewards.get("reward")
    if reward is None:
        if len(rewards) != 1:
            raise RuntimeError(
                "feedback missing verifier feedback:"
                "expected a scalar verifier reward, or a `reward` entry"
            )
        reward = next(iter(rewards.values()))

    passed = int(float(reward) == 1.0)
    return 1, passed, 1 - passed


def resolve_task_dir(result: TrialResult) -> Path:
    task_config = result.config.task
    try:
        task_dir = task_config.get_local_path()
        if task_dir.exists():
            return task_dir
    except ValueError:
        pass

    task_id = task_config.get_task_id()
    download_dir = task_config.download_dir
    task_path = getattr(task_id, "path", None)
    if download_dir is not None and task_path is not None:
        return (
            Path(download_dir).expanduser().resolve()
            / shortuuid.uuid(str(task_id))
            / task_path.name
        )

    return task_config.get_local_path()


def copytree_if_exists(source: Path, destination: Path) -> bool:
    if not source.is_dir():
        return False
    shutil.copytree(source, destination, dirs_exist_ok=True)
    return True


def copyfile_if_exists(source: Path, destination: Path) -> bool:
    if not source.is_file():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def prepare_ground_truth_dir(
    result: TrialResult,
    trial_dir: Path,
    feedback_dir: Path,
) -> Path:
    task_dir = resolve_task_dir(result)
    ground_truth_dir = feedback_dir / "ground-truth"
    verifier_dir = ground_truth_dir / "verifier"
    shutil.rmtree(ground_truth_dir, ignore_errors=True)
    ground_truth_dir.mkdir(parents=True, exist_ok=True)
    verifier_dir.mkdir(parents=True, exist_ok=True)

    copied = {
        "solution": copytree_if_exists(
            task_dir / "solution",
            ground_truth_dir / "solution",
        ),
        "verifier/tests": copytree_if_exists(
            task_dir / "tests",
            verifier_dir / "tests",
        ),
        "verifier/test-stdout.txt": copyfile_if_exists(
            trial_dir / "verifier" / "test-stdout.txt",
            verifier_dir / "test-stdout.txt",
        ),
    }
    (ground_truth_dir / "manifest.json").write_text(
        json.dumps(
            {
                "task_dir": str(task_dir.resolve()),
                "copied": copied,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return ground_truth_dir


def attach_ground_truth_path(
    feedback_payload: FeedbackOutputPayload,
    ground_truth_dir: Path | None,
) -> FeedbackPayload:
    payload = feedback_payload.model_dump()
    if ground_truth_dir is None:
        return FeedbackPayload.model_validate(payload)

    ground_truth_path = str(ground_truth_dir.resolve())
    for subtask in payload["subtasks"]:
        subtask["ground_truth_path"] = ground_truth_path
    return FeedbackPayload.model_validate(payload)


def dump_feedback_payload(feedback_payload: FeedbackPayload) -> dict[str, Any]:
    payload = feedback_payload.model_dump()
    for subtask in payload["subtasks"]:
        if subtask.get("ground_truth_path") is None:
            subtask.pop("ground_truth_path", None)
    return payload


def feedback_codex_cli_args(result: TrialResult) -> list[str]:
    agent_config = result.config.agent
    agent_kwargs = agent_config.kwargs
    model = agent_config.model_name.split("/")[-1]  # type: ignore
    return [
        "--model",
        model,
        "-c",
        f"model_reasoning_effort={agent_kwargs.get('reasoning_effort', 'high')}",
        "-c",
        f"model_reasoning_summary={agent_kwargs.get('reasoning_summary', 'auto')}",
        "-c",
        "project_root_markers=[]",
        "-c",
        "project_doc_max_bytes=0",
    ]
