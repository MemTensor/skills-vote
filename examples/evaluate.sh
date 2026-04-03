#!/usr/bin/env bash
set -euo pipefail

uv run scripts/evaluate.py -c scripts/configs/evaluate.yaml "$@"
