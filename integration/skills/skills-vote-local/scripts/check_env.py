#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR.parent / "config" / "config.yaml"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--config",
        help="Path to the YAML config. Defaults to config/config.yaml when present.",
    )
    return parser.parse_args()


def resolve_config_path(raw_path: str | None) -> Path:
    return Path(raw_path).resolve() if raw_path else DEFAULT_CONFIG_PATH.resolve()


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
    result: dict[str, object] = {"path": str(config_path), "exists": config_path.exists()}
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


def main() -> None:
    args = parse_args()
    config_path = resolve_config_path(args.config)

    uv_result = check_uv()
    config_result = check_config(config_path)

    ok = bool(uv_result["ok"]) and bool(config_result["ok"])
    print(
        json.dumps(
            {
                "ok": ok,
                "uv": uv_result,
                "config": config_result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
