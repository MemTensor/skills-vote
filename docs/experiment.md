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
│   ├── skillrouter/                     # SkillRouter evaluation
│   ├── feedback/                        # Post-task attribution
│   └── evolve/                          # Controlled skill evolution
├── scripts/
│   ├── init_agent_configs.sh            # Codex homes initialization
│   ├── prebuild_images.py               # Datasets downloading and Docker images pre-building
│   ├── skillrouter/                     # SkillRouter data preparation and evaluation
│   └── configs/
│       ├── prebuild_images.yaml         # Dataset/image prebuild plan
│       ├── skillrouter/                 # SkillRouter evaluation configurations
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
> The recommended hardware for the published configurations includes 32 CPU cores, 64 GB RAM, and a fast SSD. Datasets and experiment outputs may require approximately 2 TB of local storage. Systems with lower hardware specifications can run experiments by reducing concurrency.

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
| &emsp;SkillsVote | Pre-task skills recommendation and post-task attribution and evolution. |
| &emsp;ReasoningBank | Pre-task memory retrieval and post-task updating following the ReasoningBank protocol. |
| &emsp;skill-creator | Post-task skill generation from completed trajectories with <code>skill-creator</code> skill. |
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

**Post-task Attribution**
The session of solver agent is copied into a newly created `.codex` directory and resumed after execution. This allows the agent to perform subtasks attribution over its own trajectory.

```yaml
skills_vote:
  register_import_paths:
    - skills_vote.harbor.hooks:register   # Register hooks that trigger post-task attribution and evolution
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

First run offline evolution on Terminal-Bench Pro:
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
Then run recommendation on Terminal-Bench 2.0:
```yaml
n_attempts: 5   # In the non-evolution setting, task order is unconstrained and avg@5 can be evaluated in a single run.
n_concurrent_trials: 32    # Unconstrained task order allows higher concurrency.
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

Run recommendation on a frozen library of ~10K curated open source skills:

```yaml
environment:
  mounts_json:    # Mount skill library into container for recommendation
    - type: bind
      source: ${skills_vote.recommend_skills_dir}
      target: /skills
      read_only: true
    - type: bind
      source: ${skills_vote.seed_skills_dir}
      target: /real-skills
      read_only: true
agents:
  - import_path: skills_vote.harbor.agents:SkillsVoteCodex
    kwargs:
      recommend:
        skills_dir: /skills   # The skills directory for agent to explore. Only contains the content of `SKILL.md`, not complete skill directories. 
        install_skills_dir: /real-skills  # Contains complete skill directories to be installed to solver agent.
        prompt_path: skills_vote.recommend.prompt:build
        skills_vote_library_manifest: ${skills_vote.skills_vote_library_manifest}   # Manifest of skills for matching recommendation results with path of complete skill directories.
skills_vote:
  recommend_skills_dir: /mnt/data/skills   # Local path of simplified skills.
  seed_skills_dir: /mnt/data/skills_origin  # Local path of complete skills.
  skills_vote_library_manifest: ${abspath:.skills_vote/skills_vote_skill_library_manifest.jsonl}
...
```

### Online Configurations

Start from an empty skill library and update it along the test-time task stream.

**SkillsVote**

Run pre-task recommendation, post-task attribution and evolution over sequential task stream:

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

**ReasoningBank**

Reproduce ReasoningBank with pre-task memory retrieval and post-task memory updating (Memory-aware Test-time Scaling (MaTTS) disabled):

```yaml
n_attempts: 1   # Each task is attempted once, following the fixed default task order.
n_concurrent_trials: 1  # Follow the sequential task stream. 
skills_vote:
  reasoningbank:
    memory_path: ${abspath:${jobs_dir}/${job_name}/reasoningbank/memory.jsonl}  # Memory bank following ReasoningBank protocol.
    retrieval_map_path: ${abspath:.skills_vote/reasoningbank/tb2/retrieval_map.jsonl} # Pre-computed result of memory retrieval, which is fixed with the fixed task stream.
    prompt_path: skills_vote.reasoningbank.prompt:build
    update_timeout_sec: 1800
    update_litellm_max_attempts: 3
    update_litellm_retry_wait_sec: 10
    update_max_trajectory_chars: 1100000    # Limitation of the input of trajectory.
    update_max_tokens: 10240
```

**skill-creator**

Use `skill-creator` skill with agent to proceed post-task skill evolution:

```yaml
n_attempts: 1   # Each task is attempted once, following the fixed default task order.
n_concurrent_trials: 1  # Follow the sequential task stream. 
environment:
  mounts_json:
    - type: bind
      source: ${skills_vote.working_skills_dir} # Mount runtime skill library evolving over task stream.
      target: /skills
      read_only: true
  ...
agents:
  - import_path: skills_vote.harbor.agents:SkillsVoteCodex
    kwargs:
      skills_dir: /skills # Skill installation provided by Harbor.
skills_vote:
  working_skills_dir: ${abspath:${jobs_dir}/${job_name}/working_skills}
  skill_backup_dir: ${abspath:${jobs_dir}/${job_name}/skills_backup}
  skill_creator_prompt_path: skills_vote.evolve.skill_creator_prompt:build  # Simple prompt designed for using `skill-creator`
  skill_creator_timeout_sec: 1800
```

### Routing over Large Skill Libraries

**SkillsVote**

Evaluate recommendation of SkillsVote on large skill libraries:

```yaml
split_names:           # The 1k ~ full library splits of SkillRouter's public set.
  - 1k
  ...
  - full
model: gpt-5.4-mini    # Codex model used as the recommendation agent.
thinking_effort: xhigh 
recommend_top_k: 10    # Number of skills returned by SkillsVote.
metric_top_k: 10       
skill_root: input/skillrouter/skills  # Prebuilt markdown-only skill corpus.
codex_workspace: /tmp/skills          # Temporary workspace exposed to Codex for search.
output_dir: output/skillrouter/skills_vote
datetime: ${now:%Y-%m-%d__%H-%M-%S}
num_recommend_concurrency: 32  # Concurrent recommendation tasks.
recommend_timeout: 7200        # Timeout in seconds for one recommendation run.
num_persist_batch_size: 8      
```

**SkillRouter**

Reproduce the released SkillRouter embedding and reranker pipeline:

```yaml
split_names:           # The 1k ~ full library splits of SkillRouter's public set.
  - 1k
  ...
  - full
retrieve_top_k: 50    # Number of skills kept after embedding retrieval.
rerank_top_n: 20      # Number of retrieved skills passed to the reranker.
metric_top_k: 10      
output_dir: output/skillrouter/skillrouter
datetime: ${now:%Y-%m-%d__%H-%M-%S}
num_rerank_concurrency: 8  # Concurrent rerank requests.
rerank_timeout: 60         # Timeout in seconds for one rerank request.
num_persist_batch_size: 8
```

## Launch Experiments

The examples below use `gpt_5_4_mini`. To run another model, use the corresponding model directory under `scripts/configs/**/codex/` and the matching script under `scripts/`.

### SWE-Bench Pro

**w/o skills**

```bash
uv run svt run -c scripts/configs/swebenchpro/codex/gpt_5_4_mini/baseline.yaml
```

**Offline Curated**

First, download curated skills from our Huggingface repository (upcoming):

Then start the experiment (check the path of skills):
```bash
uv run svt run -c scripts/configs/swebenchpro/codex/gpt_5_4_mini/curated_skill_search_seed.yaml
```

**Online SkillsVote**

```bash
uvx tmuxp load -d scripts/configs/swebenchpro_repos/codex/gpt_5_4_mini/search_online_evolve_tmuxp.yaml
```

**Online ReasoningBank**

```bash
uvx tmuxp load -d scripts/configs/swebenchpro_repos/codex/gpt_5_4_mini/reasoningbank_search_online_evolve_tmuxp.yaml
```

**Online skill-creator**

```bash
uvx tmuxp load -d scripts/configs/swebenchpro_repos/codex/gpt_5_4_mini/skill_creator_search_online_evolve_tmuxp.yaml
```

### Terminal-Bench 2.0

**w/o skills**

```bash
uv run svt run -c scripts/configs/tb2/codex/gpt_5_4_mini/baseline.yaml
```

**Offline TB-Pro**

```bash
bash scripts/run_tb_pro_search_offline_then_tb2_search_gpt_5_4_mini.sh
```

**Offline TB-Pro (w/o recommendation)**

```bash
bash scripts/run_tb_pro_search_offline_then_tb2_gpt_5_4_mini.sh
```

**Offline Curated**

```bash
uvx tmuxp load -d scripts/configs/tb2/codex/gpt_5_4_mini/curated_skill_search_seed.yaml
```

**Online SkillsVote**

```bash
uvx tmuxp load -d scripts/configs/tb2/codex/gpt_5_4_mini/search_online_evolve_tmuxp_5.yaml
```

**Online SkillsVote (w/o recommendation)**

```bash
uvx tmuxp load -d scripts/configs/tb2/codex/gpt_5_4_mini/online_evolve_tmuxp_5.yaml
```

**Online ReasoningBank**

```bash
uvx tmuxp load -d scripts/configs/tb2/codex/gpt_5_4_mini/reasoningbank_search_online_evolve_tmuxp_5.yaml
```

**Online Skill-creator**

```bash
uvx tmuxp load -d scripts/configs/tb2/codex/gpt_5_4_mini/skill_creator_search_online_evolve_tmuxp_5.yaml
```

## Output

Use the local web interface to inspect the results:

```bash
uv run harbor view output
```
