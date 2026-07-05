# Didala Plugin

自迭代 AI 能力仓库，同时维护 Codex 插件与 Claude Code command。当前首个能力是 `planAlign` / `plan-align`：用于飞书需求评审、方案设计、跨需求依赖检查、排期，并在用户确认后回写飞书评审文档。

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

如果不想用软链接，也可以复制文件：

```bash
cp .claude/commands/planAlign.md ~/.claude/commands/planAlign.md
```

## Install For Codex

本仓库自带 repo-local marketplace。克隆仓库后，从任意目录执行：

```bash
codex plugin marketplace add /path/to/Didala_plugin
codex plugin add didala-plugin@didala-ai
```

本机当前路径示例：

```bash
codex plugin marketplace add /Users/zhangyu/IdeaProjects/Didala_plugin
codex plugin add didala-plugin@didala-ai
```

安装或更新后，建议新开一个 Codex thread，让 Codex 重新加载插件能力。

使用方式：

```text
使用 plan-align 评审这个飞书需求：<链接>
使用 plan-align 复评这个需求：<链接>
使用 plan-align 给「模块名」单独出方案和排期
```

## Update Workflow

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

## Notes

- 飞书读写相关动作需要当前 Codex / Claude 环境具备可用的 `lark-cli` 或对应飞书能力。
- 写入飞书文档前，工作流要求先向用户确认。
- 原始产品需求文档不直接修改，评审结论统一沉淀到评审文档。
