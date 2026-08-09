<div align="center">
  <h1>SkillsVote</h1>
  <p><strong>🧠 下一代原生智能体技能推荐引擎</strong></p>
  <p><em>为 AI 智能体提供即时、动态路由的技能赋能。</em></p>
  <p>由 <a href="https://memos.openmem.net/"><b>MemTensor</b></a> 提供支持</p>
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

## 🌟 为什么选择 SkillsVote？

告别庞大、硬编码且臃肿的技能列表！**SkillsVote** 正在构建一个智能、动态的生态系统，用于技能推荐、反馈和长期技能演进。

作为智能网关，SkillsVote 提供**即时推荐**，动态地将您的 AI 智能体路由到它们所需的确切技能。结果如何？⚡ **最大化 Token 效率** 以及 🎯 **极高的任务成功率**。

### 🌍 全球最大的技能库

在产品层面，我们正在挖掘 GitHub 庞大的开源宇宙，构建一个史无前例的技能库：

- 🔥 发现了 **1.68M+** 个 `SKILL.md` 文件
- 💎 经过[验证](https://github.com/anthropics/skills/blob/main/skills/skill-creator/scripts/quick_validate.py)后，有 **790K+** 个格式有效的技能

### 💡 关于此仓库

这是 SkillsVote 的**开源、本地优先核心**。它为您提供：

1. 一个强大的静态分析流水线，用于技能分析（profiling），以及
2. 一个智能的本地智能体推荐流水线。

## 📰 最新动态

- 🚀 **[2026-04-03] 发布日！** 发布了我们推荐和评估演示的第一个开源版本。

## ✨ 核心特性

<div align="center">
  <img src="assets/preprocess.png" width="90%">
</div>

1. **🔍 丰富的技能分析 (Skill Profiling)。** SkillsVote 不仅仅读取技能；它理解它们。我们为每个技能构建了结构化、全面的配置文件——涵盖操作系统要求、环境变量、CLI 需求和 MCP 依赖。这使得浏览我们的网站变得轻而易举，同时确保了严格的质量控制。
2. **🏗️ 真实任务构建与执行。** 我们远不止于静态检查！通过我们可验证性筛选的技能将接受测试：我们构建可执行任务、受控沙箱和严格的验证器，以证明一项技能*实际上*能帮助智能体完成真实工作。
3. **🧠 智能体推荐引擎。** 给定用户任务和本地技能目录，我们的智能体导航会搜索您的目录，并返回完美的推荐技能集，同时提供万无一失的使用指南。

有关我们评估流水线中使用的质量和可验证性标准的详细分类，请参阅[附录：评估指标详解](#appendix-evaluation-metrics-unpacked)。

## 🚀 快速开始

### 选项 1：安装托管技能（推荐）

#### 🤖 智能体设置提示词

通过直接集成 SkillsVote 为您的智能体（Codex、Claude Code、OpenClaw）充能！只需将此提示词提供给您的智能体：

```markdown
1. 通过运行 `npx skills add MemTensor/skills-vote --skill skills-vote` 安装技能
2. 在安装的 `skills-vote` 技能根目录中创建或更新 `.env` 文件，并设置 `SKILLS_VOTE_API_KEY="您的_API_密钥"`

除非明确要求，否则不要将其配置为系统或用户级环境变量。
```

#### 🔧 手动设置备选方案

您是命令行极客吗？请根据您的操作系统手动设置：

*Windows PowerShell*

```powershell
[Environment]::SetEnvironmentVariable("SKILLS_VOTE_API_KEY", "您的_API_密钥", "User")
npx skills add MemTensor/skills-vote --skill skills-vote
```

*MacOS/Linux (Bash/Zsh)*

```bash
# 对于 zsh，请使用 ~/.zshrc
echo 'export SKILLS_VOTE_API_KEY="您的_API_密钥"' >> ~/.bashrc && source ~/.bashrc
npx skills add MemTensor/skills-vote --skill skills-vote
```

> [!note]
> 不要忘记将 `您的_API_密钥` 替换为您实际的密钥！

### 选项 2：运行本地演示 🏠

想要在本地试驾核心引擎吗？只需遵循以下 3 个简单步骤：

**1. 安装依赖**

```bash
uv sync
```

**2. 配置环境**

复制示例配置并填写您的 Anthropic 凭据。

```bash
cp .env.example .env
```

调用官方 Anthropic API 时使用 `ANTHROPIC_API_KEY`。调用兼容 Anthropic 的第三方服务时使用 `ANTHROPIC_AUTH_TOKEN` 和 `ANTHROPIC_BASE_URL`。

**3. 运行示例**

```bash
bash examples/evaluate.sh
bash examples/recommend.sh
```

输出将被写入 `output/evaluate_results.jsonl` 和 `output/recommend_result.json`。

您可以使用以下命令覆盖查询词：

```bash
bash examples/recommend.sh -q "Summarize a pull request and highlight risky changes"
```

如果您想使用自己的本地技能，请更新 `scripts/configs/recommend.yaml` 和 `scripts/configs/evaluate.yaml` 中的 `skills_dir`，然后重新运行相同的命令。

## 📎 附录

<a id="appendix-evaluation-metrics-unpacked"></a>

### 📊 评估指标详解

**表 1. 质量评估**

| 指标 | 描述 | 为什么重要 |
|:-: |:-- |:-- |
| 一致性 (Consistency) | 技能是否集中在一个清晰、稳定的目标上，以及其余内容是否始终支持该目标。 | 推荐的技能应该是一个稳定的能力单元，而不是不相关主题的混合体。 |
| 完整性 (Completeness) | 引用的脚本、资源、模板和依赖项是否存在并可按文档说明使用。 | 损坏的引用和缺失的构件是开源技能库中最常见的故障模式之一。 |
| 任务导向性 (Task Orientation) | 技能是否为完成工作提供了可操作的指导，而不仅仅是背景信息。 | SkillsVote 推荐的是可执行的技能，而不仅仅是检索知识。 |

**表 2. 可验证性评估**

| 指标 | 描述 | 为什么重要 |
|:-: |:-- |:-- |
| 成功可验证性 (Success Verifiability) | 结果是否可以在低歧义的情况下通过编程进行判断。 | 诸如头脑风暴或写诗等主观技能不适合自动验证。 |
| 环境可控性 (Environment Controllability) | 所需环境是否可以在受控沙箱中可靠地重现、重置和执行。 | 依赖于实时外部系统或开放世界状态的技能很难进行确定性的基准测试。 |
| 任务可构建性 (Task Constructability) | 是否可以以合理的成本生成许多真实的实例和验证器。 | 某些领域需要昂贵的硬件、大型数据集或繁重的人工工作，不能很好地扩展以进行评估。 |

## 📄 许可证

此仓库采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

<div align="center">
  <i>由 <a href="https://memos.openmem.net/"><b>MemTensor</b></a> ❤️ 构建。准备好为你的技能投票了吗？</i>
</div>
