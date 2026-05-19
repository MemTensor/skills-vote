from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR.parent / "configs" / "config.yaml"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def add_config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-c",
        "--config",
        help="Path to the YAML config. Defaults to configs/config.yaml when present.",
    )


def resolve_config_path(raw_path: str | None) -> Path:
    return Path(raw_path).resolve() if raw_path else DEFAULT_CONFIG_PATH.resolve()


def resolve_existing_config_path(raw_path: str | None) -> Path:
    config_path = resolve_config_path(raw_path)
    if not config_path.exists():
        raise SystemExit(
            f"Config file not found: {config_path}. Create configs/config.yaml first."
        )
    return config_path
