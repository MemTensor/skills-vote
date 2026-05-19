<div align="center">
  <h1>SkillsVote</h1>
  <p><strong>Lifecycle Governance of Agent Skills: From Collection and Recommendation to Evolution</strong></p>
  <p><em>Route skills just in time, learn from task execution, and evolve reusable skill libraries through attribution-grounded feedback.</em></p>
  <p>Powered by <a href="https://memos.openmem.net/"><b>MemTensor</b></a></p>
</div>

<p align="center">
  <a href="https://arxiv.org/abs/2605.18401">
    <img alt="arXiv" src="https://img.shields.io/badge/arXiv-2605.18401-b31b1b?style=for-the-badge&logo=arxiv&logoColor=white">
  </a>
  <a href="https://skills.vote">
    <img alt="Website" src="https://img.shields.io/badge/Website-skills.vote-blue?style=for-the-badge&logo=google-chrome">
  </a>
  <a href="https://mp.weixin.qq.com/s/fA4DbNnCVbsToOt886VcfQ">
    <img alt="WeChat Blog" src="https://img.shields.io/badge/WeChat-Blog_Post-07C160?style=for-the-badge&logo=wechat&logoColor=white">
  </a>
  <a href="http://xhslink.com/o/9c53b8USOxK">
    <img alt="rednote" src="https://img.shields.io/badge/rednote-Post-FF2442?style=for-the-badge">
  </a>
  <a href="https://opensource.org/license/mit/">
    <img alt="License" src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge&logo=opensourceinitiative&logoColor=white">
  </a>
  <a href="#quick-start">
    <img alt="Quick Start" src="https://img.shields.io/badge/Quick_Start-Ready_To_Go-yellow?style=for-the-badge&logo=rocket">
  </a>
</p>

<div align="center">
  <img src="assets/pipeline.png" width="90%">
</div>

## 🧭 What SkillsVote Governs

Agent skills are becoming a reusable execution layer for coding agents, research agents, and workflow agents. SkillsVote starts from this large-scale setting: we have discovered over 🔥 **1.68M** `SKILL.md` files from open-source GitHub repositories, including over 💎 **790K** format-valid skills verified with the official Anthropic skill validator, making SkillsVote the world's largest open agent skill library 🌍.

At this scale, skill management is no longer about manually maintaining a short curated list. Agents face three linked problems: which skills to load before a task, how to tell whether a skill actually helped during execution, and how to update the library without accumulating noisy or unverified experience.

SkillsVote treats skills as lifecycle-managed artifacts. It connects collection, profiling, just-in-time recommendation, trajectory-based attribution, and feedback-driven evolution into one loop:

1. **Collect and profile skills** from open-source or private skill libraries.
2. **Recommend relevant skills** before task execution, instead of loading a large static skill list.
3. **Attribute task outcomes** after execution using trajectories, skill usage, and verifier signals.
4. **Evolve the skill library** by updating or creating reusable skills from grounded, attributed feedback.

## 📰 Latest News

- 📄 **[2026-05-19] Technical Report.** We released the SkillsVote technical report on arXiv: [arXiv:2605.18401](https://arxiv.org/abs/2605.18401).
- 🧭 **[2026-05-18] Local Skill Integration.** We released the first version of `skills-vote-local`, enabling local/private skill recommendation with configurable retrieval strategies.
- 🌅 **[2026-04-09] Special Share.** Core contributor's share on [Linux.do](https://linux.do).
- 📣 **[2026-04-08] Social Launch.** Our launch announcement is now live on [WeChat Blog](https://mp.weixin.qq.com/s/fA4DbNnCVbsToOt886VcfQ) and [rednote](http://xhslink.com/o/9c53b8USOxK).
- 🚀 **[2026-04-03] Launch Day!** Published the very first open-source release of our recommendation and evaluation demos.

## 🗺️ Roadmap: Towards the Full Skill Lifecycle

SkillsVote is being open-sourced in stages to support transparent research on agent skill collection, recommendation, attribution, and evolution.

- [x] **Skill profiling and preprocessing.** Analyze skill runtime requirements, dependencies, quality, and verifiability.
- [x] **Benchmark evaluation scripts.** Release scripts and configs for reproducing the main experiments reported in our paper.
- [x] **Hosted SkillsVote skill integration.** Release the `skills-vote` agent skill that connects agents to the hosted SkillsVote service for cloud-based recommendation and attribution-grounded feedback.
- [x] **Local SkillsVote recommendation integration.** Release `skills-vote-local` with configurable local/private skill recommendation strategies, including agentic search and vector search.
- [ ] **Local SkillsVote attribution and evolution integration.** Extend `skills-vote-local` with attribution-grounded feedback and local skill library evolution.
- [ ] **Main experiment trajectories and results.** Release benchmark trajectories and aggregated results to support inspection and reproduction of the reported experiments.

## 📊 Evaluation Results

SkillsVote is evaluated on agentic coding and terminal challenge benchmarks, including **Terminal-Bench Pro**, **Terminal-Bench 2.0**, and **SWE-Bench Pro**.

<div align="center">
  <img src="assets/main_results.svg" width="100%">
  <img src="assets/main_results_tables.png" width="100%">
</div>

The results show that just-in-time skill recommendation and feedback-driven evolution improve agent performance on long-horizon tasks. Detailed reproduction instructions, benchmark setup configs, and scripts are documented in [`docs/experiment.md`](docs/experiment.md).

## 🚀 Quick Start

| Integration         | Best for                                                                                                    | Requires                                               |
|:------------------ |:---------------------------------------------------------------------------------------------------------- |:----------------------------------------------------- |
| `skills-vote`       | Using the hosted SkillsVote service for cloud-based skill recommendation and attribution-grounded feedback. | `SKILLS_VOTE_API_KEY`                                  |
| `skills-vote-local` | Recommending skills from a local or private `SKILL.md` library without relying on the hosted index.         | Local config; no SkillsVote API key for agentic search |

### Option 1: Install the Hosted Skill

Use this integration when you want agents to retrieve skills from the hosted SkillsVote service and submit post-task feedback for attribution.

#### 🤖 Agent Setup Prompt

Supercharge your agents (Codex, Claude Code, OpenClaw) by integrating SkillsVote directly! Just drop this prompt into your agent:

```markdown
Install the `skills-vote` skill following https://raw.githubusercontent.com/MemTensor/skills-vote/main/integration/skills/INSTALL.md

Use the following values: 
- `SKILLS_VOTE_API_KEY`: "YOUR_API_KEY"
- `GH_TOKEN`: "YOUR_GITHUB_TOKEN"
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

### Option 2: Install the Local-first Skill

Use this integration when your skills are stored in a local or private `SKILL.md` library and you want recommendation without the hosted index.

#### 🤖 Agent Setup Prompt

```markdown
Install the `skills-vote-local` skill following https://raw.githubusercontent.com/MemTensor/skills-vote/main/integration/skills/INSTALL.md
```

#### 🔧 Manual Setup Alternative

```bash
npx skills add MemTensor/skills-vote --skill skills-vote-local
```

After installation, open the installed skill root and configure `configs/config.yaml`. See [Install SkillsVote Skills](integration/skills/INSTALL.md) for the full configuration flow.

## ♥️ Acknowledgements

SkillsVote builds on the broader agent skill and agentic benchmark ecosystem. We thank the maintainers and contributors of [Anthropic Skills](https://github.com/anthropics/skills), [Harbor](https://github.com/harbor-framework/harbor), and open-source agent skill repositories for making this research possible.

## 📚 Citation

If you find SkillsVote useful for your research or development, please cite:

```bibtex
@misc{liu2026skillsvotelifecyclegovernanceagent,
  title={SkillsVote: Lifecycle Governance of Agent Skills from Collection, Recommendation to Evolution},
  author={Hongyi Liu and Haoyan Yang and Tao Jiang and Bo Tang and Feiyu Xiong and Zhiyu Li},
  year={2026},
  eprint={2605.18401},
  archivePrefix={arXiv},
  primaryClass={cs.CL},
  url={https://arxiv.org/abs/2605.18401},
}
```

## 📄 License

This repository is licensed under the MIT License. See [LICENSE](LICENSE).

<div align="center">
  <i>Built with ❤️ by <a href="https://memos.openmem.net/"><b>MemTensor</b></a>. Ready to vote for your skills?</i>
</div>
