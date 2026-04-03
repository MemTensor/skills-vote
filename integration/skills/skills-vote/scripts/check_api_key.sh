#!/usr/bin/env bash

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
[ -f "$root/.env" ] && set -a && . "$root/.env" && set +a
[ -n "$SKILLS_VOTE_API_KEY" ] && echo "SKILLS_VOTE_API_KEY is set" || echo "SKILLS_VOTE_API_KEY is missing"
