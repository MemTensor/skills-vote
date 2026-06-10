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

Fill in the following variables:

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

## Experiment Settings

<table style="width: 100%; table-layout: fixed;">
  <colgroup>
    <col style="width: 9.5em;">
    <col>
  </colgroup>
  <thead>
    <tr>
      <th style="white-space: nowrap;">Setting</th>
      <th>Meaning</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td style="white-space: nowrap;">w/o Skills</td>
      <td style="overflow-wrap: break-word;">Base solver w/o an external skill library.</td>
    </tr>
    <tr>
      <td style="white-space: nowrap;">Online</td>
      <td style="overflow-wrap: break-word;">Start from an empty skill library and update it along the test-time task stream.</td>
    </tr>
    <tr>
      <td style="white-space: nowrap;">&emsp;SkillsVote</td>
      <td style="overflow-wrap: break-word;">Pre-task skills recommendation and post-execution attribution and evolution.</td>
    </tr>
    <tr>
      <td style="white-space: nowrap;">&emsp;ReasoningBank</td>
      <td style="overflow-wrap: break-word;">Pre-task memory retrieval and post-execution updating following the ReasoningBank protocol.</td>
    </tr>
    <tr>
      <td style="white-space: nowrap;">&emsp;skill-creator</td>
      <td style="overflow-wrap: break-word;">Post-execution skill generation from completed trajectories with <code>skill-creator</code> skill.</td>
    </tr>
    <tr>
      <td style="white-space: nowrap;">Offline</td>
      <td style="overflow-wrap: break-word;">Start from a frozen skill library and use it only through pre-task recommendation on the test set.</td>
    </tr>
    <tr>
      <td style="white-space: nowrap;">&emsp;TB-Pro</td>
      <td style="overflow-wrap: break-word;">Skill library is built from historical Terminal-Bench Pro tasks trajectories.</td>
    </tr>
    <tr>
      <td style="white-space: nowrap;">&emsp;Curated</td>
      <td style="overflow-wrap: break-word;">Skill library contains approximately 10k curated skills selected by the SkillsVote collecting-and-profiling pipeline from open-source skills.</td>
    </tr>
  </tbody>
</table>

## Configurations

Each experiment YAML file includes Harbor runtime configurations and SkillsVote configurations.

### Harbor Configurations

* `n_attempts`: the number of trials executed for each task.
* `n_concurrent_trials`: the number of trials that Harbor may run simultaneously.
* `retry.max_retries`: the maximum number of retries for each trial when errors occur.
* `retry.exclude_exceptions`: exception types excluded from retry. These failures are treated as reflecting agent capability and are not retried.
* `agent_timeout_multiplier`: a multiplier applied to the task's default agent-step timeout.
* `environment.mounts_json`: directories mounted into the Docker container. We use this option to mount the skill directory into the task container for recommendation.
* `agents[0].model_name`: the model identifier passed to the agent provider.
* `agents[0].kwargs.reasoning_effort`: the reasoning setting used for Codex.
* `agents[0].kwargs.allowed_skills`: the Codex system skills that are allowed during execution. By default, all system skills are disabled to minimize their influence on task execution.
* `datasets`: the dataset paths to run. By default, experiments use the prebuilt dataset images.

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