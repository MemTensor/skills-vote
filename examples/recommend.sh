#!/usr/bin/env bash
set -euo pipefail

uv run scripts/recommend.py -c scripts/configs/recommend.yaml "$@"
