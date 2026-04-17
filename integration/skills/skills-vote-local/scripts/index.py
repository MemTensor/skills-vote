#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
    config_path = Path(raw_path).resolve() if raw_path else DEFAULT_CONFIG_PATH.resolve()
    if not config_path.exists():
        raise SystemExit(
            f"Config file not found: {config_path}. Create config/config.yaml first."
        )
    return config_path


def main() -> None:
    from local_skill_search import index_build, load_config

    args = parse_args()
    config_path = resolve_config_path(args.config)
    config = load_config(config_path)
    result = index_build(config)
    result["config"] = str(config_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
