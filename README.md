# Didala Plugin

自迭代 AI 能力仓库，同时维护 Codex 插件与 Claude Code command。当前首个能力是 `planAlign` / `plan-align`：用于飞书需求评审、方案设计、跨需求依赖检查、按功能模块需求点排期，并在用户确认后回写飞书评审文档。

## Repository Layout

```text
.
├── .agents/plugins/marketplace.json
├── .claude/commands/planAlign.md
├── docs/capabilities.md
└── plugins/didala-plugin
    ├── .codex-plugin/plugin.json
    └── skills/plan-align/SKILL.md
```

- `.claude/commands/planAlign.md`: Claude Code command 源文件。
- `plugins/didala-plugin`: Codex 插件根目录。
- `plugins/didala-plugin/skills/plan-align/SKILL.md`: Codex skill 版本。
- `docs/capabilities.md`: 能力索引，后续沉淀新的 AI 工作流时先登记到这里。

## Install For Claude Code

从仓库根目录执行：

```bash
mkdir -p ~/.claude/commands
ln -sf "$(pwd)/.claude/commands/planAlign.md" ~/.claude/commands/planAlign.md
```

使用方式：

```text
/planAlign <飞书需求链接>
/planAlign <飞书需求链接> 背景:...
/planAlign 复评 <飞书需求链接>
/planAlign 方案:<模块名>
```

推荐使用软链接；后续更新仓库后，Claude Code command 会直接读到最新内容。如果不想用软链接，也可以复制文件：

```bash
cp .claude/commands/planAlign.md ~/.claude/commands/planAlign.md
```

复制安装时，每次仓库更新后都需要重新执行上述 `cp` 命令。

## Install For Codex

本仓库自带 repo-local marketplace。克隆仓库后，从任意目录执行：

```bash
codex plugin marketplace add /path/to/Didala_plugin
codex plugin add didala-plugin@didala-ai
```

本机当前路径示例：

```bash
codex plugin marketplace add /Users/zz/IdeaProjects/Didala_plugin
codex plugin add didala-plugin@didala-ai
```

安装或更新后，建议新开一个 Codex thread，让 Codex 重新加载插件能力。

使用方式：

```text
使用 plan-align 评审这个飞书需求：<链接>
使用 plan-align 复评这个需求：<链接>
使用 plan-align 给「模块名」单独出方案和排期
```

## Current planAlign Behavior

- 排期按功能模块需求点拆分，不按 DAO/domain/controller 等开发分层拆分。
- 每个排期任务块控制在 `0.5 人日` 到 `2 人日`，并标注范围边界、依赖、关键路径与待对齐影响。
- 问题清单包含 `对齐状态`、`对齐内容`、`影响更新` 三列；对齐状态支持 `待对齐` / `定` / `改需求` / `挂起` / `不做`。
- 表结构设计内置 MySQL DDL/DML 工程规范，覆盖引擎字符集、命名、主键、必备时间字段、字段类型、索引、改表、大表风险、DML 和发布审查；不依赖本机 `/Users/zz/Documents/...` 下的原始规范文件。
- 模块方案、用户确认视图、写入飞书文档等节点，能用流程图表达的尽量附 Mermaid 流程图或时序图，并保留到评审文档中。

## Update Workflow

### Update Existing Claude Code Command Locally

如果使用推荐的软链接安装方式，只需要拉取或修改本仓库即可；新开 Claude Code 会话后使用最新 command。

如果使用复制安装方式，更新仓库后重新复制：

```bash
cp .claude/commands/planAlign.md ~/.claude/commands/planAlign.md
```

### Add A New AI Capability

1. 在 `docs/capabilities.md` 登记能力名称、触发方式、支持平台和状态。
2. Claude Code 能力放到 `.claude/commands/<name>.md`。
3. Codex 能力放到 `plugins/didala-plugin/skills/<name>/SKILL.md`。
4. 更新本 README 的安装或使用说明。

### Update Existing Codex Plugin Locally

修改 `plugins/didala-plugin` 后重新安装：

```bash
codex plugin add didala-plugin@didala-ai
```

如果 Codex 没有感知到更新，给 `plugins/didala-plugin/.codex-plugin/plugin.json` 的 `version` 加一个 build metadata 后缀，例如：

```json
"version": "0.1.0+codex.local-20260705"
```

然后再次执行：

```bash
codex plugin add didala-plugin@didala-ai
```

安装或更新后，建议新开一个 Codex thread，让 Codex 重新加载插件能力。

## Notes

- 飞书读写相关动作需要当前 Codex / Claude 环境具备可用的 `lark-cli` 或对应飞书能力。
- 写入飞书文档前，工作流要求先向用户确认。
- 原始产品需求文档不直接修改，评审结论统一沉淀到评审文档。
