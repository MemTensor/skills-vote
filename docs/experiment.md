# Experiment Guide

The benchmark evaluation is built on [Harbor](https://github.com/harbor-framework/harbor). This guide is intended to support the reproduction of the published experiments.

## Repository Layout

```text
.
├── src/skills_vote/
│   ├── harbor/                          # Harbor CLI wrapper, agent adapter, and hooks
│   ├── recommend/                       # Pre-task skill recommendation
│   ├── feedback/                        # Post-task subtask attribution
│   └── evolve/                          # Controlled skill evolution
├── scripts/
│   ├── init_agent_configs.sh            # Creates `.skills_vote/.codex_*` homes
│   ├── prebuild_images.py               # Downloads datasets and prebuilds task Docker images
│   └── configs/
│       ├── prebuild_images.yaml         # Dataset/image prebuild plan
│       ├── tb_pro/                      # Terminal-Bench Pro configurations
│       ├── tb2/                         # Terminal-Bench 2 configurations
│       ├── swebenchpro/                 # SWE-Bench Pro baseline configurations
│       └── swebenchpro_repos/           # SWE-Bench Pro per-repository configurations
└── .skills_vote/                        # Generated Codex homes and skill directories
```

## Requirements

Use an environment that satisfies the following requirements:

* Python `>=3.12`, managed by `uv`.
* Docker Engine on `amd64/x86`.
* `tmux` and `tmuxp` for launching multi-job configuration files.
* Network access to the model endpoint, benchmark dataset sources, and Docker registries.
* An OpenAI-compatible API key for Codex model calls.

> The recommended hardware for the published configurations includes 32 CPU cores, 64 GB RAM, and a fast SSD. Dataset mirrors, Docker images, and experiment outputs may require approximately 2 TB of local storage. Smaller machines can also run the experiments by reducing runtime concurrency.

## Installation

Install the dependencies:

```bash
uv sync
```

Create a local environment file:

```bash
cp .env.example .env
```

Fill in at least the following variables:

```bash
OPENAI_API_KEY=...
OPENAI_BASE_URL=...
CODEX_FORCE_API_KEY=1
```

Initialize the Codex homes:

```bash
bash scripts/init_agent_configs.sh
```

This script creates `.skills_vote/.codex_gpt_5_4_mini`, `.skills_vote/.codex_gpt_5_2`, and `.skills_vote/.codex_gpt_5_5_xhigh`. It also writes `config.toml`, which includes project trust settings and disabled system-skill entries using absolute paths.

Prebuild the dataset images:

```bash
uv run scripts/prebuild_images.py --cfg-path scripts/configs/prebuild_images.yaml
```

This downloads benchmark metadata and builds task images according to the published prebuild plan. The first run may take several hours, depending on network speed.

## Configuration Notes

Each experiment YAML file combines Harbor runtime settings with SkillsVote settings. Before launching an experiment, check the following fields:

* `n_concurrent_trials`: the number of trials that Harbor may run simultaneously.
* `agents[0].model_name`: the model identifier passed to the agent provider.
* `agents[0].kwargs.reasoning_effort`: the reasoning setting used for Codex.
* `agents[0].kwargs.version`: the Codex CLI version expected inside the task images.

## Launch Experiments

| Setting  | Meaning                                                                                                 |
| -------- | ------------------------------------------------------------------------------------------------------- |
| Baseline | -                                                                                                       |
| Offline  | A skill library is built from historical tasks and transferred to unseen tasks for recommendation only. |
| Online   | The experiment starts from an empty skill library for recommendation and evolution.                     |

The examples below use `gpt_5_4_mini`. To run another model, use the corresponding model directory under `scripts/configs/**/codex/` and the matching script under `scripts/`.

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

Offline:

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

Use the local web interface to inspect the results:

```bash
uv run harbor view output
```