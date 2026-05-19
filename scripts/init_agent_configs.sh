#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

CODEX_HOME_DIRS=(
  ".skills_vote/.codex_gpt_5_4_mini"
  ".skills_vote/.codex_gpt_5_2"
  ".skills_vote/.codex_gpt_5_5_xhigh"
)
SYSTEM_SKILL_NAMES=(
  "skill-installer"
  "plugin-creator"
  "skill-creator"
  "openai-docs"
  "imagegen"
)

if [[ -f ".env" ]]; then
  set -a
  source ".env"
  set +a
fi

: "${OPENAI_API_KEY:?Set OPENAI_API_KEY in .env or the environment before running this script.}"

mkdir -p "${CODEX_HOME_DIRS[@]}"

escaped_repo_root="${REPO_ROOT//\\/\\\\}"
escaped_repo_root="${escaped_repo_root//\"/\\\"}"
for codex_home_dir in "${CODEX_HOME_DIRS[@]}"; do
  codex_home_abs="${REPO_ROOT}/${codex_home_dir}"
  escaped_codex_home_abs="${codex_home_abs//\\/\\\\}"
  escaped_codex_home_abs="${escaped_codex_home_abs//\"/\\\"}"
  codex_config="${codex_home_dir}/config.toml"
  auth_json="${codex_home_dir}/auth.json"

  {
    printf '# SkillsVote Codex home.\n'
    printf '# Model and API settings are read from environment variables.\n\n'
    printf '[projects."%s"]\n' "${escaped_repo_root}"
    printf 'trust_level = "trusted"\n'
    for skill_name in "${SYSTEM_SKILL_NAMES[@]}"; do
      printf '\n[[skills.config]]\n'
      printf 'enabled = false\n'
      printf 'path = "%s/skills/.system/%s/SKILL.md"\n' "${escaped_codex_home_abs}" "${skill_name}"
    done
  } >"${codex_config}"

  {
    printf '{\n'
    printf '  "OPENAI_API_KEY": "%s"\n' "${OPENAI_API_KEY}"
    printf '}\n'
  } >"${auth_json}"
  chmod 600 "${auth_json}"
done

echo "Initialized model-specific Codex homes"
