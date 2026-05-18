#!/usr/bin/env python3
# /// script
# dependencies = ["PyYAML>=6.0.3,<7.0.0", "chromadb>=1.3.5,<2.0.0"]
# ///

from __future__ import annotations

import argparse
import json

from cli_common import add_config_argument, resolve_existing_config_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_config_argument(parser)
    return parser.parse_args()


def main() -> None:
    from local_skill_search import index_build, load_config

    args = parse_args()
    config_path = resolve_existing_config_path(args.config)
    config = load_config(config_path)
    result = index_build(config)
    result["config"] = str(config_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
