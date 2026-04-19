#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from cli_common import add_config_argument, resolve_existing_config_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_config_argument(parser)
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


def main() -> None:
    from local_skill_search import load_config, recommend_local_skills

    args = parse_args()
    config_path = resolve_existing_config_path(args.config)
    config = load_config(config_path)
    try:
        response = recommend_local_skills(args.query, config, top_k_override=args.top_k)
    except RuntimeError as exc:
        raise SystemExit(str(exc))
    print(json.dumps(response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
