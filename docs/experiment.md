# Experiment Guide

The benchmark evaluation is built on [Harbor](https://github.com/harbor-framework/harbor). This guide is intended to support the reproduction of the published experiments.

## Repository Layout

```text
skills-vote
├── src/skills_vote/
│   ├── harbor/                          
│   │   ├── agents.py                    # SkillsVote agent
│   │   ├── cli.py                       # SkillsVote CLI for running Harbor jobs
│   │   └── hooks.py                     # Post-task stage integration into Harbor lifecycle
│   ├── recommend/                       # Pre-task skill recommendation
│   │   ├── codex.py                     # Recommendation implementation
│   │   ├── model.py                     # Config and output models
│   │   ├── prompt.py                    # Prompt templates
│   │   └── utils.py                     
│   ├── feedback/                        # Post-task attribution
│   └── evolve/                          # Controlled skill evolution
├── scripts/
│   ├── init_agent_configs.sh            # Codex homes initialization
│   ├── prebuild_images.py               # Datasets downloading and Docker images pre-building
│   └── configs/
│       ├── prebuild_images.yaml         # Dataset/image prebuild plan
│       ├── tb_pro/                      # Terminal-Bench Pro configurations
│       ├── tb2/                         # Terminal-Bench 2.0 configurations
│       ├── swebenchpro/                 # SWE-Bench Pro configurations
│       └── swebenchpro_repos/           # SWE-Bench Pro per-repository configurations
└── .skills_vote/                        # Generated Codex homes and skill directories
```

## Requirements

* Python `>=3.12`, managed by `uv`.
* Docker Engine on `amd64/x86`.
* `tmux` and `tmuxp` for launching multi-job configuration files.
* An API compatible with the `/responses` endpoint.

> [!TIP]
> The recommended hardware for the published configurations includes 32 CPU cores, 64 GB RAM, and a fast SSD. Dataset mirrors, Docker images, and experiment outputs may require approximately 2 TB of local storage. Smaller machines can also run the experiments by reducing runtime concurrency.

## Setup

Install the dependencies:

```bash
uv sync
```

Create a local environment file:

```bash
cp .env.example .env
```

Fill the following variables in `.env`:

```bash
OPENAI_API_KEY=...
OPENAI_BASE_URL=...
CODEX_FORCE_API_KEY=1
```

Initialize the Codex homes:

```bash
bash scripts/init_agent_configs.sh
```

> [!NOTE]
> This script creates `.skills_vote/.codex_gpt_5_4_mini`, `.skills_vote/.codex_gpt_5_2`, and `.skills_vote/.codex_gpt_5_5_xhigh`. It also writes `config.toml` for disabling system skills of Codex.

Specify which datasets to set up in `scripts/configs/prebuild_images.yaml`:

```yaml
max_workers: 32 # Number of parallel image builds
datasets:
  - name: terminal-bench
    version: "2.0"
    download_dir: input/tb2 # Directory for downloaded datasets
    registry_url: null
    registry_path: null
    task_names: []  # Empty list means all tasks
    exclude_task_names: []  # Exculding tasks from `task_names`

agents:         # Pre-installed agent
  - name: codex
    version: "0.125.0"

dependencies:   # Pre-installed dependencies
  - name: nvm
    version: "v0.40.4"
  - name: node
    version: "22"
```

Download datasets and build Docker images, which may take a long time:

```bash
uv run scripts/prebuild_images.py
```

## Experiment Settings

| Setting | Meaning |
| --- | --- |
| w/o Skills | Base solver w/o an external skill library. |
| Online | Start from an empty skill library and update it along the test-time task stream. |
| &emsp;SkillsVote | Pre-task skills recommendation and post-execution attribution and evolution. |
| &emsp;ReasoningBank | Pre-task memory retrieval and post-execution updating following the ReasoningBank protocol. |
| &emsp;skill-creator | Post-execution skill generation from completed trajectories with <code>skill-creator</code> skill. |
| Offline | Start from a frozen skill library and use it only through pre-task recommendation on the test set. |
| &emsp;TB-Pro | Skill library is built from historical Terminal-Bench Pro tasks trajectories. |
| &emsp;Curated | ~10k open source skills curated by the SkillsVote collecting and profiling pipeline. |

## Configurations

Each experiment YAML file includes Harbor runtime configurations and SkillsVote configurations.

### Harbor Configurations

```yaml
n_attempts: 1  # Trials per task
n_concurrent_trials: 32  # Concurrent trials
retry:
  max_retries: 3  # Retry limit
  exclude_exceptions:  # Non-retried verifier failures
    - VerifierTimeoutError      # These four types of failures  
    - RewardFileNotFoundError   # are treated as reflecting agent capability,
    - RewardFileEmptyError      # so they are not retried.
    - VerifierOutputParseError
agent_timeout_multiplier: 4.0  # Agent-step timeout multiplier applied to the task's default value
environment:
  type: docker
  mounts_json:  # Directories mounted into task containers, for skill recommendation
    ...
agents:
  - import_path: skills_vote.harbor.agents:SkillsVoteCodex
    model_name: openai/gpt-5.4-mini
    kwargs:
      reasoning_effort: medium  # Codex reasoning setting
      allowed_skills: []  # Empty for disabling Codex system skills
datasets:
  - name: swebenchpro
    version: "1.0"
    download_dir: input/swebenchpro  # Dataset path
```

### SkillsVote Configurations

We implement `SkillsVoteCodex` as the solver agent by extending Harbor's Codex agent. The agent skips the setup phase and disables Codex built-in system skills and plugins for reducing network overhead, while leaving the task-execution logic unchanged.

**Recommendation**

After the skill directory is mounted into the Docker container, the agent is launched inside the mounted directory to perform recommendation. The recommended skills are then copied into the solver agent's `skills` directory.

```yaml
agents:
  - import_path: skills_vote.harbor.agents:SkillsVoteCodex
    kwargs:
      recommend:
        skills_dir: /skills     # Mounted skill directory inside Docker
        prompt_path: skills_vote.recommend.prompt:build     # Recommendation prompt
skills_vote:
  seed_skills_dir: ${abspath:.skills_vote/offline_skills}  # Initial skill library
```

**Post-execution Attribution**
The session of solver agent is copied into a newly created `.codex` directory and resumed after execution. This allows the agent to perform subtasks attribution over its own trajectory.

```yaml
skills_vote:
  register_import_paths:
    - skills_vote.harbor.hooks:register   # Register hooks that trigger post-execution attribution and evolution
  codex_home: ${abspath:.skills_vote/.codex}    # Local Codex directory whose authentication files are reused for attribution
  feedback_prompt_path: skills_vote.feedback.prompt:build   # Attribution prompt
  feedback_verifier_summary_extractors:   # Benchmark-specific reward extractors
    - ctrf
    - pytest_stdout
    - output_json
  feedback_include_ground_truth: false   # Provide ground truth to assist attribution during offline evolution
```

**Evolution**

Based on the attribution results, subtasks are aggregated and routed to either the skill-creation or skill-editing branch of the evolution.

```yaml
skills_vote:
  register_import_paths:
    - skills_vote.harbor.hooks:register
  codex_home: ${abspath:.skills_vote/.codex}    # codex home for evolution 
  working_skills_dir: ${abspath:${jobs_dir}/${job_name}/working_skills}   # skill library evolving with trial
  skill_backup_dir: ${abspath:${jobs_dir}/${job_name}/skills_backup}  # Backup directory for evolved skills
  evolve_prompt_path: skills_vote.evolve.prompt:build   # Evolution Prompt
  evolve_timeout_sec: 1800
  evolve_every_n_trials: 1  # Batch size of evolution, default value is 1.
```

### Offline Configurations

Start from a frozen skill library and use it only through pre-task recommendation on the test set.

**TB-Pro** 

First run offline evolution on Terminal-Bench Pro
```yaml
n_attempts: 1   # Each task is attempted once, following the fixed default task order.
n_concurrent_trials: 4  # Execute one synchronized batch of 4 trials at a time.
agents:
  - import_path: skills_vote.harbor.agents:SkillsVoteCodex
    kwargs:
      recommend:  # Enable Recommend
        ...
skills_vote:
  evolve_every_n_trials: 4  # Aggregate the trajectories from each completed batch of 4 trials and pass them to one offline evolution step.
  feedback_include_ground_truth: true # Ground truth is provided only to assist attribution decisions. 
...
```
Then run recommendation on Terminal-Bench 2.0
```yaml
n_attempts: 5   # In the non-evolution setting, task order is unconstrained and avg@5 can be evaluated in a single run.
n_concurrent_trials: 32    # unconstrained task order allows higher concurrency.
agents:
  - import_path: skills_vote.harbor.agents:SkillsVoteCodex
    kwargs:
      recommend:  # Enable Recommend
        ...
skills_vote:
  seed_skills_dir: ${abspath:tb_pro_frozen_skill_library}
...
```

**Curated**


### Online Configurations

Start from an empty skill library and update it along the test-time task stream.

**SkillsVote**

Run pre-task recommendation, post-execution and evolution over sequential task stream.
```yaml
n_attempts: 1   # Each task is attempted once, following the fixed default task order.
n_concurrent_trials: 1  # Follow the sequential task stream. 
environment:
  mounts_json:
    - type: bind
      source: ${skills_vote.working_skills_dir}   # Mount runtime skill library evolving over task stream.
      target: /skills
      read_only: true
  ...
agents:
  - import_path: skills_vote.harbor.agents:SkillsVoteCodex
    kwargs:
      recommend:  # Enable Recommend
  ...
skills_vote:
  register_import_paths:
    - skills_vote.harbor.hooks:register
  working_skills_dir: ${abspath:${jobs_dir}/${job_name}/working_skills}
  evolve_every_n_trials: 1
...
```

**Reasoningbank**

**skill-creator**

## Launch Experiments

The examples below use `gpt_5_4_mini`. To run another model, use the corresponding model directory under `scripts/configs/**/codex/` and the matching script under `scripts/`.

### SWE-Bench Pro

w/o Skills:

```bash
uv run svt run -c scripts/configs/swebenchpro/codex/gpt_5_4_mini/baseline.yaml
```

Online SkillsVote:

```bash
uvx tmuxp load -d scripts/configs/swebenchpro_repos/codex/gpt_5_4_mini/search_online_evolve_tmuxp.yaml
```

### Terminal-Bench 2

w/o skills:

```bash
uv run svt run -c scripts/configs/tb2/codex/gpt_5_4_mini/baseline.yaml
```

Offline TB-Pro:

```bash
bash scripts/run_tb_pro_search_offline_then_tb2_search_gpt_5_4_mini.sh
```

Offline TB-Pro (w/o recommendation):

```bash
bash scripts/run_tb_pro_search_offline_then_tb2_gpt_5_4_mini.sh
```

Online SkillsVote:

```bash
uvx tmuxp load -d scripts/configs/tb2/codex/gpt_5_4_mini/search_online_evolve_tmuxp_5.yaml
```

Online SkillsVote (w/o recommendation):

```bash
uvx tmuxp load -d scripts/configs/tb2/codex/gpt_5_4_mini/online_evolve_tmuxp_5.yaml
```

## Output

Use the local web interface to inspect the results:

```bash
uv run harbor view output
```
