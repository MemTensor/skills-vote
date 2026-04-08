<div align="center">
  <h1>SkillsVote</h1>
  <p><strong>🧠 The Next-Gen Agent-Native Skill Recommendation Engine</strong></p>
  <p><em>Empowering AI agents with just-in-time, dynamically routed skills.</em></p>
  <p>Powered by <a href="https://memos.openmem.net/"><b>MemTensor</b></a></p>
</div>

<p align="center">
  <a href="https://skills.vote">
    <img alt="Website" src="https://img.shields.io/badge/Website-skills.vote-blue?style=for-the-badge&logo=google-chrome">
  </a>
  <a href="https://opensource.org/license/mit/">
    <img alt="License" src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge&logo=opensourceinitiative&logoColor=white">
  </a>
  <a href="#quick-start">
    <img alt="Quick Start" src="https://img.shields.io/badge/Quick_Start-Ready_To_Go-yellow?style=for-the-badge&logo=rocket">
  </a>
</p>

<div align="center">
  <img src="assets/arch.png" width="90%">
</div>

## 🌟 Why SkillsVote?

Say goodbye to massive, hardcoded, and bloated skill lists! **SkillsVote** is building an intelligent, dynamic ecosystem for skill recommendation, feedback, and long-term skill evolution.

Acting as a smart gateway, SkillsVote delivers **just-in-time recommendations**, dynamically routing your AI agents to the exact skills they need. The result? ⚡ **Maximized token efficiency** and 🎯 **sky-high task success rates**.

### 🌍 The World's Largest Skill Library

At the product level, we are mining the vast open-source universe of GitHub to build an unprecedented library:

- 🔥 **1.68M+** discovered `SKILL.md` files
- 💎 **790K+** format-valid skills after [validation](https://github.com/anthropics/skills/blob/main/skills/skill-creator/scripts/quick_validate.py)

### 💡 About This Repository

This is the **open-source, local-first core** of SkillsVote. It equips you with:

1. a powerful static analysis pipeline for skill profiling, and
2. a smart local agentic recommendation pipeline.

## 📰 Latest News

- 🚀 **[2026-04-03] Launch Day!** Published the very first open-source release of our recommendation and evaluation demos.

## ✨ Key Features

<div align="center">
  <img src="assets/preprocess.png" width="90%">
</div>

1. **🔍 Rich Skill Profiling.** SkillsVote doesn't just read skills; it understands them. We build a structured, comprehensive profile for every skill—covering OS requirements, env variables, CLI needs, and MCP dependencies. This makes browsing our website a breeze while ensuring strict quality control.
2. **🏗️ Real Task Construction & Execution.** We go far beyond static inspection! Skills that pass our verifiability screening are put to the test: we construct executable tasks, controlled sandboxes, and strict validators to prove that a skill *actually* helps agents get real work done.
3. **🧠 Agentic Recommendation Engine.** Given a user task and a local skill directory, our agentic navigation searches your directory and returns the perfect recommended skill set, complete with foolproof usage guidance.

For a detailed breakdown of the quality and verifiability criteria used in our evaluation pipeline, see [Appendix: Evaluation Metrics Unpacked](#appendix-evaluation-metrics-unpacked).

## 🚀 Quick Start

### Option 1: Install the Hosted Skill (Recommended)

#### 🤖 Agent Setup Prompt

Supercharge your agents (Codex, Claude Code, OpenClaw) by integrating SkillsVote directly! Just drop this prompt into your agent:

```markdown
1. Install the skill by running `npx skills add MemTensor/skills-vote --skill skills-vote`
2. Create or update `.env` file located in the root directory of the installed `skills-vote` skill and set `SKILLS_VOTE_API_KEY="YOUR_API_KEY"`

Do not configure this as a system or user-level environment variable unless explicitly requested.
```

#### 🔧 Manual Setup Alternative

Are you a CLI warrior? Set it up manually based on your OS:

*Windows PowerShell*

```powershell
[Environment]::SetEnvironmentVariable("SKILLS_VOTE_API_KEY", "YOUR_API_KEY", "User")
npx skills add MemTensor/skills-vote --skill skills-vote
```

*MacOS/linux (Bash/Zsh)*

```bash
# For zsh, use ~/.zshrc instead
echo 'export SKILLS_VOTE_API_KEY="YOUR_API_KEY"' >> ~/.bashrc && source ~/.bashrc
npx skills add MemTensor/skills-vote --skill skills-vote
```

> [!note]
> Don't forget to replace `YOUR_API_KEY` with your actual key!

### Option 2: Run the Local Demo 🏠

Want to test drive the core engine locally? Just follow these 3 easy steps:

**1. Install dependencies**

```bash
uv sync
```

**2. Configure Environment**

Copy the example config and fill in your Anthropic credentials.

```bash
cp .env.example .env
```

Use `ANTHROPIC_API_KEY` when calling the official Anthropic API. Use `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_BASE_URL` when calling a third-party Anthropic-compatible service.

**3. Run the examples**

```bash
bash examples/evaluate.sh
bash examples/recommend.sh
```

Outputs are written to `output/evaluate_results.jsonl` and `output/recommend_result.json`.

You can override the query with:

```bash
bash examples/recommend.sh -q "Summarize a pull request and highlight risky changes"
```

If you want to use your own local skills, update `skills_dir` in `scripts/configs/recommend.yaml` and `scripts/configs/evaluate.yaml`, then rerun the same commands.

## 📎 Appendix

<a id="appendix-evaluation-metrics-unpacked"></a>

### 📊 Evaluation Metrics Unpacked

**Table 1. Quality Evaluation**

| Metric | Description | Why it matters |
|:-: |:-- |:-- |
| Content Consistency | Whether the skill stays centered on one clear, stable purpose and whether the rest of the content consistently supports that purpose. | A recommended skill should be a stable capability unit, not a mixed bundle of unrelated topics. |
| Reference Completeness | Whether the referenced scripts, resources, templates, and dependencies are present and usable as documented. | Broken references and missing artifacts are one of the most common failure modes in open-source skill libraries. |
| Task Orientation | Whether the skill provides actionable guidance for completing work rather than only background information. | SkillsVote is recommending executable skills, not just retrieving knowledge. |

**Table 2. Verifiability Evaluation**

| Metric | Description | Why it matters |
|:-: |:-- |:-- |
| Success Verifiability | Whether results can be judged programmatically with low ambiguity. | Subjective skills such as brainstorming or poetry writing are not suitable for automatic validation. |
| Environment Controllability | Whether the required environment can be reproduced, reset, and executed reliably in a controlled sandbox. | Skills that depend on live external systems or open-world state are hard to benchmark deterministically. |
| Task Constructability | Whether many realistic task instances and validators can be generated at reasonable cost. | Some domains require expensive hardware, large datasets, or heavy manual work and do not scale well for evaluation. |

## 📄 License

This repository is licensed under the MIT License. See [LICENSE](LICENSE).

<div align="center">
  <i>Built with ❤️ by <a href="https://memos.openmem.net/"><b>MemTensor</b></a>. Ready to vote for your skills?</i>
</div>
