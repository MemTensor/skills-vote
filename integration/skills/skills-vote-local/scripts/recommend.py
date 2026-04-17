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
    parser.add_argument(
        "-q",
        "--query",
        required=True,
        help="A rewritten, retrieval-optimized query.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        help="Override retrieval.top_k for this query.",
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
    from local_skill_search import load_config, recommend_local_skills

    args = parse_args()
    config_path = resolve_config_path(args.config)
    config = load_config(config_path)
    try:
        response = recommend_local_skills(args.query, config, top_k_override=args.top_k)
    except RuntimeError as exc:
        raise SystemExit(str(exc))
    print(json.dumps(response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
