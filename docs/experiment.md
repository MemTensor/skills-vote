# Experiment Guide

SkillsVote runs benchmark experiments on top of [Harbor](https://github.com/harbor-framework/harbor). This guide is intended for reproducing the published experiments.

## Repository Layout

Only the files and module groups needed for running experiments are shown here.

```text
.
├── src/skills_vote/
│   ├── harbor/                          # Harbor CLI wrapper, Agent adapter, and hooks
│   ├── recommend/                       # Pre-task skill recommendation
│   ├── feedback/                        # Post-task subtasks attribution
│   └── evolve/                          # Controlled skill evolution
├── scripts/
│   ├── init_agent_configs.sh            # Creates `.skills_vote/.codex_*` homes
│   ├── prebuild_images.py               # Downloads datasets and prebuilds task Docker images
│   ├── run_tb_pro_search_offline_then_tb2_*.sh
│   └── configs/
│       ├── prebuild_images.yaml         # Dataset/image prebuild plan
│       ├── tb_pro/                      # Terminal-Bench Pro configs
│       ├── tb2/                         # Terminal-Bench 2 configs
│       ├── swebenchpro/                 # SWE-Bench Pro baseline configs
│       └── swebenchpro_repos/           # SWE-Bench Pro per-repository configs
└── .skills_vote/                        # Generated Codex homes and skill directories
```

## Requirements

Use a environment with:

- Python `>=3.12`, managed by `uv`.
- Docker Engine on `amd64/x86`.
- `tmux` and `tmuxp` for multi-job launch files.
- Network access to the model endpoint, benchmark dataset sources, and Docker registries.
- An OpenAI-compatible API key for Codex model calls.

> Recommended hardware for the published configurations is 32 CPU cores, 64 GB RAM, and a fast SSD. Dataset mirrors, Docker images, and experiment outputs can require roughly 2 TB of local storage. Smaller machines can still run the experiments after lowering runtime concurrency.

## Installation

Install dependencies:

```bash
uv sync
```

Create a local environment file:

```bash
cp .env.example .env
```

Fill in at least:

```bash
OPENAI_API_KEY=...
OPENAI_BASE_URL=...
CODEX_FORCE_API_KEY=1
```

Initialize the Codex homes :

```bash
bash scripts/init_agent_configs.sh
```

The script creates `.skills_vote/.codex_gpt_5_4_mini`, `.skills_vote/.codex_gpt_5_2`, and `.skills_vote/.codex_gpt_5_5_xhigh`, writes `config.toml` with project trust plus disabled system-skill entries using absolute paths.

Prebuild the dataset images:

```bash
uv run scripts/prebuild_images.py --cfg-path scripts/configs/prebuild_images.yaml
```

This downloads benchmark metadata and builds task images according to the published prebuild plan. The first run can take several hours depending on network speed and Docker image cache state.

## Configuration Notes

Each experiment YAML combines Harbor runtime settings and SkillsVote settings. Before launching, check:

- `n_concurrent_trials`: number of trials Harbor may run at once.
- `agents[0].model_name`: model identifier passed to the agent provider.
- `agents[0].kwargs.reasoning_effort`: reasoning setting for Codex.
- `agents[0].kwargs.version`: Codex CLI version expected inside task images.

## Launch Experiments

| Setting | Meaning |
| --- | --- |
| Baseline | - |
| Offline | Collect offline experience and test with recommendation|
| Online |  |

The examples below use `gpt_5_4_mini`. To run another model, use the matching model directory under `scripts/configs/**/codex/` and the matching script under `scripts/`.

### SWE-Bench Pro

Baseline:

```bash
uv run svt run -c scripts/configs/swebenchpro/codex/gpt_5_4_mini/baseline.yaml
```

Online:

```bash
uvx tmuxp load -d scripts/configs/swebenchpro_repos/codex/gpt_5_4_mini/search_online_evolve_tmuxp.yaml
```

### Terminal-Bench 2

Baseline:

```bash
uv run svt run -c scripts/configs/tb2/codex/gpt_5_4_mini/baseline.yaml
```
Offline

```bash
bash scripts/run_tb_pro_search_offline_then_tb2_search_gpt_5_4_mini.sh
```

Offline (w/o recommendation):

```bash
bash scripts/run_tb_pro_search_offline_then_tb2_gpt_5_4_mini.sh
```

Online:

```bash
uvx tmuxp load -d scripts/configs/tb2/codex/gpt_5_4_mini/search_online_evolve_tmuxp_5.yaml
```

Online (w/o recommendation):

```bash
uvx tmuxp load -d scripts/configs/tb2/codex/gpt_5_4_mini/online_evolve_tmuxp_5.yaml
```



## Output
Use the local website to check the results:
```bash
uv run harbor view output
```
