#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import yaml
from cli_common import add_config_argument, resolve_config_path
from config_validation import (
    find_unsupported_config_fields,
    resolve_retrieval_method,
)
from sync_skills import SKILLS_ROOT, sync_skill_namespace


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_config_argument(parser)
    return parser.parse_args()


def check_uv() -> dict[str, object]:
    uv_path = shutil.which("uv")
    if not uv_path:
        return {"ok": False, "message": "uv is not available on PATH."}

    try:
        completed = subprocess.run(
            [uv_path, "-V"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        return {"ok": False, "message": f"uv check failed: {exc}"}

    return {"ok": True, "message": completed.stdout.strip() or completed.stderr.strip()}


def check_config(config_path: Path) -> dict[str, object]:
    result: dict[str, object] = {
        "path": str(config_path),
        "exists": config_path.exists(),
    }
    if not config_path.exists():
        result["ok"] = False
        result["message"] = "Config file not found."
        return result

    from local_skill_search import load_config

    try:
        load_config(config_path)
    except Exception as exc:
        result["ok"] = False
        result["message"] = f"Config load failed: {exc}"
        return result

    result["ok"] = True
    result["message"] = "Config file exists and loads successfully."
    return result


def read_config_yaml(
    config_path: Path,
) -> tuple[dict[str, object] | None, dict[str, object]]:
    result: dict[str, object] = {
        "path": str(config_path),
        "exists": config_path.exists(),
    }
    if not config_path.exists():
        result["ok"] = False
        result["message"] = "Config file not found."
        return None, result

    try:
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        result["ok"] = False
        result["message"] = f"Config parse failed: {exc}"
        return None, result

    if not isinstance(loaded, dict):
        result["ok"] = False
        result["message"] = "Config root must be a YAML object."
        return None, result

    unsupported_fields = find_unsupported_config_fields(loaded)
    if unsupported_fields:
        result["ok"] = False
        result["message"] = "Unsupported config field(s): " + ", ".join(
            unsupported_fields
        )
        return None, result

    result["ok"] = True
    result["message"] = "Config file exists and parses successfully."
    return loaded, result


def get_retrieval_method(config: dict[str, object] | None) -> tuple[str, list[str]]:
    if not config:
        return "agentic_grep", []
    retrieval = config.get("retrieval")
    if not isinstance(retrieval, dict):
        return "agentic_grep", []
    method, warning = resolve_retrieval_method(retrieval.get("method"))
    return method, [warning] if warning is not None else []


def check_tool(name: str) -> dict[str, object]:
    path = shutil.which(name)
    if not path:
        return {"ok": False, "message": f"{name} is not available on PATH."}
    return {"ok": True, "path": path}


def format_sync_result(sync_result) -> dict[str, object]:
    return {
        "ok": sync_result.ok,
        "skills_count": sync_result.skills_count,
        "skills_root": str(SKILLS_ROOT),
        "skills_root_exists": SKILLS_ROOT.exists(),
        "warnings": sync_result.warnings,
        "errors": sync_result.errors,
    }


def main() -> None:
    args = parse_args()
    config_path = resolve_config_path(args.config)

    uv_result = check_uv()
    raw_config, raw_config_result = read_config_yaml(config_path)
    retrieval_method, warnings = get_retrieval_method(raw_config)

    if retrieval_method == "agentic_grep":
        find_result = check_tool("find")
        grep_result = check_tool("grep")
        if raw_config is None:
            sync_result_json = {
                "ok": False,
                "skills_count": 0,
                "skills_root": str(SKILLS_ROOT),
                "skills_root_exists": SKILLS_ROOT.exists(),
                "warnings": [],
                "errors": ["Config could not be parsed."],
            }
        else:
            sync_result = sync_skill_namespace(raw_config, config_path)
            sync_result_json = format_sync_result(sync_result)

        ok = bool(uv_result["ok"]) and bool(raw_config_result["ok"])
        ok = ok and bool(find_result["ok"]) and bool(grep_result["ok"])
        ok = ok and bool(sync_result_json["ok"])
        print(
            json.dumps(
                {
                    "ok": ok,
                    "retrieval_method": retrieval_method,
                    "uv": uv_result,
                    "config": raw_config_result,
                    "tools": {
                        "find": find_result,
                        "grep": grep_result,
                    },
                    "skills_sync": sync_result_json,
                    "warnings": warnings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if not ok:
            raise SystemExit(1)
        return

    config_result = check_config(config_path)
    ok = bool(uv_result["ok"]) and bool(config_result["ok"])
    print(
        json.dumps(
            {
                "ok": ok,
                "retrieval_method": retrieval_method,
                "uv": uv_result,
                "config": config_result,
                "warnings": warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
