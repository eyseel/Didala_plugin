# Didala Plugin

自迭代 AI 能力仓库，同时维护 Codex 插件与 Claude Code command。当前能力包括：

- `planAlign` / `plan-align`：用于飞书需求评审、方案设计、跨需求依赖检查、按功能模块需求点排期，并在用户确认后回写飞书评审文档。
- `worktreeNew` / `worktreeClean` / `worktree-flow`：用于安全创建和清理当前项目的 Git worktree，统一放到 `/Users/zz/worktree`。
- `waveDemo`：用两个 Claude Code CLI Agent 演示“串行创建 worktree、并行执行、记录 manifest、等待并核验结果”的最小调度器。

## Repository Layout

```text
.
├── .agents/plugins/marketplace.json
├── .claude/commands/planAlign.md
├── .claude/commands/worktreeClean.md
├── .claude/commands/worktreeNew.md
├── .claude/commands/waveDemo.md
├── docs/capabilities.md
└── plugins/didala-plugin
    ├── .codex-plugin/plugin.json
    └── skills
        ├── plan-align/SKILL.md
        └── worktree-flow/SKILL.md
```

- `.claude/commands/planAlign.md`: Claude Code command 源文件。
- `.claude/commands/worktreeNew.md`: Claude Code 新建 worktree command。
- `.claude/commands/worktreeClean.md`: Claude Code 清理 worktree command。
- `.claude/commands/waveDemo.md`: Claude Code 双 Agent worktree wave 调度演示命令。
- `plugins/didala-plugin`: Codex 插件根目录。
- `plugins/didala-plugin/skills/plan-align/SKILL.md`: Codex skill 版本。
- `plugins/didala-plugin/skills/worktree-flow/SKILL.md`: Codex worktree workflow 版本。
- `docs/capabilities.md`: 能力索引，后续沉淀新的 AI 工作流时先登记到这里。

## Install For Claude Code

从仓库根目录执行：

```bash
mkdir -p ~/.claude/commands
ln -sf "$(pwd)/.claude/commands/planAlign.md" ~/.claude/commands/planAlign.md
ln -sf "$(pwd)/.claude/commands/worktreeNew.md" ~/.claude/commands/worktreeNew.md
ln -sf "$(pwd)/.claude/commands/worktreeClean.md" ~/.claude/commands/worktreeClean.md
ln -sf "$(pwd)/.claude/commands/waveDemo.md" ~/.claude/commands/waveDemo.md
```

使用方式：

```text
/planAlign <飞书需求链接>
/planAlign <飞书需求链接> 背景:...
/planAlign 复评 <飞书需求链接>
/planAlign 方案:<模块名>

/worktreeNew 修复登录回调问题
/worktreeNew 重构订单结算流程
/worktreeClean
/worktreeClean --delete-unmerged-branches
/worktreeClean --delete-residual-dirs

/waveDemo
```

推荐使用软链接；后续更新仓库后，Claude Code command 会直接读到最新内容。如果不想用软链接，也可以复制文件：

```bash
cp .claude/commands/planAlign.md ~/.claude/commands/planAlign.md
cp .claude/commands/worktreeNew.md ~/.claude/commands/worktreeNew.md
cp .claude/commands/worktreeClean.md ~/.claude/commands/worktreeClean.md
cp .claude/commands/waveDemo.md ~/.claude/commands/waveDemo.md
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
使用 worktree-flow 为当前项目创建一个用于修复登录回调的 worktree
使用 worktree-flow 清理当前项目下的 worktree
```

## Current planAlign Behavior

- 排期按功能模块需求点拆分，不按 DAO/domain/controller 等开发分层拆分。
- 每个排期任务块控制在 `0.5 人日` 到 `2 人日`，并标注范围边界、依赖、关键路径与待对齐影响。
- 问题清单包含 `对齐状态`、`对齐内容`、`影响更新` 三列；对齐状态支持 `待对齐` / `定` / `改需求` / `挂起` / `不做`。
- 表结构设计内置 MySQL DDL/DML 工程规范，覆盖引擎字符集、命名、主键、必备时间字段、字段类型、索引、改表、大表风险、DML 和发布审查；不依赖本机 `/Users/zz/Documents/...` 下的原始规范文件。
- 模块方案、用户确认视图、写入飞书文档等节点，能用流程图表达的尽量附 Mermaid 流程图或时序图，并保留到评审文档中。

## Current worktree Behavior

- 新建 worktree 时，必须在 Git 仓库内执行，并基于当前分支创建 `worktree_<slug>` 分支。
- worktree 工作目录固定为 `/Users/zz/worktree/<项目名>_worktree_<slug>`。
- 如果当前主工作区有未提交改动，创建前会提醒：新 worktree 基于当前 `HEAD`，不会自动带上未提交改动。
- 清理 worktree 时，只处理路径在 `/Users/zz/worktree/` 且目录名、分支名符合本工作流规则的条目。
- 已合并且干净的 worktree 会直接删除，并删除对应 `worktree_*` 分支。
- 未合并或有未提交内容的 worktree 会先提醒并等待确认；未合并分支默认保留，仍可后续合并或重新挂载 worktree。
- worktree 删除后会检查原目录是否还有 IDEA、ignored 构建产物、`.DS_Store`、日志等残留；只有确认该路径已不在 `git worktree list` 且没有 `.git` 指针后，才会在用户确认下删除残留普通目录。
- 默认不用 `rm -rf` 清理仍被 Git 识别的 worktree；统一先通过 `git worktree remove` 处理。

## Wave Demo Behavior

`/waveDemo` 是一个刻意简化的学习工具，而不是通用任务执行器。

- 编排文档逐个调用 Claude Code 原生 `Agent(isolation="worktree", run_in_background=true)`，因此 runtime 负责创建、绑定和运行每个 worktree Agent；创建 Agent B 时，Agent A 已经在运行。
- 某些 Claude Code runtime 会从 primary checkout 而非调用命令的 feature branch 初始化 worktree。Agent 在修改前会先确认它处于全新的 `worktree-agent-*` 分支且干净，然后仅在该隔离分支执行一次 `git reset --hard <expected_base>` 校正基线；绝不重置主工作区或受保护分支。
- 运行 manifest 写入当前仓库根目录的 `METAIN.md`。每个启动 metadata 对象包含 `agent_id`、`worktree_path`、`branch` 与 `expected_base`；worker 不得写这个共享文件。
- 等待阶段通过 `TaskOutput` 和 completion notification；最终还会检查分支是否从 base 前进、预期文件是否已提交、worktree 是否干净，避免只相信文本“完成”通知。
- demo 有意保留分支和 worktree，不会自动 merge 或 cleanup。先检查 `METAIN.md` 与日志，再手动练习下一阶段。

worktree 根目录由 Claude Code 的 `WorktreeCreate` hook 决定，不由命令参数传入。若 Agent 启动响应没有完整 metadata，命令会安全停止，不通过扫描 worktree 猜测归属。

### Claude Code runtime prerequisite

要让原生 Agent worktree 同时基于当前 feature 分支、并放到项目外的统一目录，在用户级
`~/.claude/settings.json` 中保留既有配置并合并以下两个字段：

```json
{
  "worktree": {
    "base": "head"
  },
  "hooks": {
    "WorktreeCreate": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "set -euo pipefail; repo=\"$(git rev-parse --show-toplevel)\"; cd \"$repo\"; root=/Users/zz/worktree/wareTreeDemo; mkdir -p \"$root\"; id=\"$(date -u +%Y%m%dT%H%M%S)-$$\"; path=\"$root/agent-$id\"; branch=\"worktree-agent-$id\"; git worktree add -b \"$branch\" \"$path\" HEAD >&2; printf '%s\\n' \"$path\""
          }
        ]
      }
    ]
  }
}
```

不要用这段 JSON 覆盖整个 settings 文件：将 `worktree` 字段加入顶层，并把
`WorktreeCreate` 条目合并进已有的 `hooks` 对象。hook 必须只在 stdout 最后一行输出
已创建的绝对目录；上面的 `git worktree add` 输出被重定向到 stderr。Claude Code 会把
这个目录绑定给 Agent；没有配置 `WorktreeRemove` 时，runtime 的默认 Git 清理路径仍可用。

## Update Workflow

### Update Existing Claude Code Command Locally

如果使用推荐的软链接安装方式，只需要拉取或修改本仓库即可；新开 Claude Code 会话后使用最新 command。

如果使用复制安装方式，更新仓库后重新复制：

```bash
cp .claude/commands/planAlign.md ~/.claude/commands/planAlign.md
cp .claude/commands/worktreeNew.md ~/.claude/commands/worktreeNew.md
cp .claude/commands/worktreeClean.md ~/.claude/commands/worktreeClean.md
cp .claude/commands/waveDemo.md ~/.claude/commands/waveDemo.md
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
