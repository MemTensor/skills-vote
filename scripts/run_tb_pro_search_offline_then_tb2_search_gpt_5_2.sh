#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

TB_PRO_SEARCH_OFFLINE_CONFIG="scripts/configs/tb_pro/codex/gpt_5_2/search_offline_evolve_task_48_agg_4_ep_1.yaml"
TB2_SEARCH_CONFIG="scripts/configs/tb2/codex/gpt_5_2/search_seed_tb_pro_search_offline_evolve_task_48_agg_4_ep_1.yaml"
SEED_SKILLS_DIR=".skills_vote/gpt_5_2_medium_tb_pro_search_offline_evolve_task_48_agg_4_ep_1"

RUN_TIMESTAMP="${RUN_TIMESTAMP:-$(date +%Y-%m-%d__%H-%M-%S)}"
TB_PRO_SEARCH_OFFLINE_JOB_NAME="tb_pro_codex_gpt_5_2_medium_search_offline_evolve_task_48_agg_4_ep_1__${RUN_TIMESTAMP}"
TB_PRO_SEARCH_OFFLINE_JOB_DIR="output/${TB_PRO_SEARCH_OFFLINE_JOB_NAME}"
TB_PRO_SEARCH_OFFLINE_WORKING_SKILLS_DIR="${TB_PRO_SEARCH_OFFLINE_JOB_DIR}/working_skills"
TB2_SEARCH_SESSION_NAME="tb2_gpt_5_2_medium_search_seed_tb_pro_search_offline_evolve_task_48_agg_4_ep_1_${RUN_TIMESTAMP}"
TB2_SEARCH_JOB_NAME="tb2_codex_gpt_5_2_medium_search_seed_tb_pro_search_offline_evolve_task_48_agg_4_ep_1__${RUN_TIMESTAMP}"

echo "Running tb_pro gpt-5.2 medium search offline evolve: ${TB_PRO_SEARCH_OFFLINE_JOB_NAME}"
uv run svt run -c "${TB_PRO_SEARCH_OFFLINE_CONFIG}" -y "job_name=${TB_PRO_SEARCH_OFFLINE_JOB_NAME}"

if [[ ! -d "${TB_PRO_SEARCH_OFFLINE_WORKING_SKILLS_DIR}" ]]; then
  echo "working_skills not found: ${TB_PRO_SEARCH_OFFLINE_WORKING_SKILLS_DIR}" >&2
  exit 1
fi

if [[ -z "$(find "${TB_PRO_SEARCH_OFFLINE_WORKING_SKILLS_DIR}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "working_skills is empty: ${TB_PRO_SEARCH_OFFLINE_WORKING_SKILLS_DIR}" >&2
  exit 1
fi

echo "Publishing tb_pro gpt-5.2 medium search working_skills to seed dir: ${SEED_SKILLS_DIR}"
mkdir -p "$(dirname "${SEED_SKILLS_DIR}")"
tmp_seed_dir="$(mktemp -d "${SEED_SKILLS_DIR}.tmp.XXXXXX")"
trap 'rm -rf "${tmp_seed_dir}"' EXIT
cp -R "${TB_PRO_SEARCH_OFFLINE_WORKING_SKILLS_DIR}/." "${tmp_seed_dir}/"
rm -rf "${SEED_SKILLS_DIR}"
mv "${tmp_seed_dir}" "${SEED_SKILLS_DIR}"
trap - EXIT

echo "Starting tb2 seed + search in tmux session: ${TB2_SEARCH_SESSION_NAME}"
tmux new-session -d -s "${TB2_SEARCH_SESSION_NAME}" -c "${REPO_ROOT}" \
  "uv run svt run -c \"${TB2_SEARCH_CONFIG}\" -y \"job_name=${TB2_SEARCH_JOB_NAME}\""
