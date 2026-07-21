---
description: 用原生 Agent worktree 隔离演示一个两 Agent wave
allowed-tools: Bash, Read, Write, Edit, Agent, TaskOutput
disable-model-invocation: true
---

# waveDemo — 原生 Agent worktree wave 调度演示

执行这个 demo，不要创建或调用任何 `.sh`、`.js`、`.py` 等脚本文件。所有确定性
操作必须是本 Markdown 中的 Bash 片段；所有 Agent 生命周期必须通过 Claude Code
原生 `Agent` 和 `TaskOutput` 工具完成。

## 0. 原生隔离的边界

`isolation="worktree"` 由 Claude Code runtime 创建并绑定 worktree；编排器不负责
决定 worktree 根目录。根目录属于 Claude Code 的 `WorktreeCreate` hook 配置。

不要通过扫描 `git worktree list` 猜测元数据。若 runtime 的 Agent 启动响应没有
`agent_id`、`worktree_path`、`branch`，停止此 demo，保留已有 `METAIN.md`，并明确
说明当前 Claude Code runtime 不提供这个工作流所需的启动元数据。用户若要控制原生
worktree 位置，应在运行命令前配置 Claude Code 的 `WorktreeCreate` hook；这是
runtime 配置，不是本命令应手写的 worktree 脚本。

## 1. 初始化与防护

1. 在当前仓库根目录执行这些检查，并向用户展示结果：

   ```bash
   git rev-parse --show-toplevel
   git branch --show-current
   git status --short
   test ! -e METAIN.md
   git rev-parse HEAD
   ```

2. 若当前目录不是仓库根目录、处于 detached HEAD、工作区不干净或 `METAIN.md`
   已存在，停止；绝不覆盖已有 manifest。
3. 保存以下值，并用这个 Bash 片段初始化 manifest；不得让任何 worker 写此文件：

   ```bash
   set -euo pipefail
   REPO_ROOT=$(git rev-parse --show-toplevel)
   EXPECTED_BRANCH=$(git branch --show-current)
   EXPECTED_BASE=$(git rev-parse HEAD)
   DISPATCH_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
   {
     printf '# Wave demo manifest\n\n'
     printf -- '- repository_root: %s\n' "$REPO_ROOT"
     printf -- '- expected_branch: %s\n' "$EXPECTED_BRANCH"
     printf -- '- expected_base: %s\n' "$EXPECTED_BASE"
     printf -- '- dispatched_at: %s\n' "$DISPATCH_TS"
     printf '\n## Agents\n'
   } > "$REPO_ROOT/METAIN.md"
   ```
4. 输出：

   ```text
   [heartbeat] wave demo initialized; expected_base=<EXPECTED_BASE>
   ```

## 2. 串行 dispatch、并行执行

对 A、B **逐个**执行下面完整生命周期。绝不能在同一条 assistant 消息中同时发起
两个 `Agent` 调用，因为它们的 worktree 初始化会竞争共享 Git 元数据锁。

在每次 dispatch 前输出：

```text
[heartbeat] Agent <A|B> starting; creating isolated worktree
```

然后调用：

```text
Agent(
  subagent_type="general-purpose",
  name="wave-demo-<a|b>",
  description="Complete wave demo agent <A|B>",
  isolation="worktree",
  run_in_background=true,
  prompt="""
You are Agent <A|B> in a two-agent worktree scheduling demo.

FIRST, before editing anything, run this exact base-correction protocol. Claude
Code may initially seed an isolated worktree from its primary checkout, which
can differ from the invoking feature branch. Only this protocol may correct it.

```bash
set -euo pipefail
ACTUAL_BRANCH=$(git rev-parse --abbrev-ref HEAD)
git rev-parse --is-inside-work-tree >/dev/null
test -n "$ACTUAL_BRANCH"
printf '%s' "$ACTUAL_BRANCH" | grep -Eq '^worktree-agent-[A-Za-z0-9._/-]+$'
test -z "$(git status --porcelain)"
git cat-file -e <EXPECTED_BASE>^{commit}

if [ "$(git rev-parse HEAD)" != "<EXPECTED_BASE>" ]; then
  # This is safe only after all guards above: it moves this fresh, isolated,
  # non-protected worktree-agent branch and never touches the primary checkout.
  git reset --hard <EXPECTED_BASE>
fi

test "$(git rev-parse HEAD)" = "<EXPECTED_BASE>"
test "$(git merge-base HEAD <EXPECTED_BASE>)" = "<EXPECTED_BASE>"
```

If any command in this protocol fails, stop and report failure without editing.

Create exactly one file at the repository root:
- Agent A: wave-demo-agent-a.md
- Agent B: wave-demo-agent-b.md

The file is a short Markdown proof containing your agent ID, worktree path,
branch, and expected base. Commit only that file with message:
demo: agent <A|B> worktree proof

Do not modify METAIN.md. Do not merge, remove a worktree, rebase, or modify any
other file. Do not run another reset after the guarded initial base correction.
Verify git status is clean before returning.

End with:
DEMO_RESULT
status: completed
agent_id: <your runtime agent id>
worktree_path: <your pwd -P>
branch: <your branch>
expected_base: <EXPECTED_BASE>
commit: <commit sha>
"""
)
```

`Agent(...)` 返回后，**这不是完成结果**，而是启动结果。立即读取返回值，并把 runtime
的 camelCase 字段标准化为 manifest 的 snake_case 字段：

```json
{
  "agentId": "...",
  "worktreePath": "...",
  "worktreeBranch": "..."
}
```

对应关系是 `agent_id ← agentId`、`worktree_path ← worktreePath`、
`branch ← worktreeBranch`。部分 Claude Code 版本会把分支字段称为 `branch`；接受
它作为 `worktreeBranch` 的同义字段。

用 Bash 检查返回的路径为绝对路径、分支符合 `worktree-agent-*` 命名空间且
`EXPECTED_BASE` 在该 Git 仓库中可解析：

```bash
git -C <worktree_path> rev-parse --is-inside-work-tree
git -C <worktree_path> cat-file -e <EXPECTED_BASE>^{commit}
git -C <worktree_path> rev-parse --abbrev-ref HEAD | grep -E '^worktree-agent-'
```

不要在这里要求 Agent 当前 `HEAD` 已等于 `<EXPECTED_BASE>`：它可能刚启动且尚未执行
上面的受保护 base-correction。该断言只在 Agent 最终返回时验证。任何检查失败都停止
后续 dispatch，不扫描或删除任何 worktree。

将启动元数据连同 `EXPECTED_BASE` 追加到 `METAIN.md`。只有编排器这一单一写者会写
manifest，因此 A、B 并行时不会产生共享文件竞态。格式必须包含这个对象：

```json
{
  "agent_id": "...",
  "worktree_path": "...",
  "branch": "...",
  "expected_base": "..."
}
```

随后输出：

```text
[heartbeat] Agent <A|B> worktree ready; metadata recorded; agent running in background
```

只有 A 的上述 metadata 已写入后，才 dispatch B。A 在 B 创建期间已在后台执行，这
就是“创建串行、运行并行”。

## 3. 等待、心跳和交付核验

保存两个 `agent_id`。现在不再派发任何 Agent，也不做 merge/cleanup。

对未完成任务循环调用：

```text
TaskOutput(task_id=<agent_id>, block=true, timeout=10000)
```

每次等待超时或返回增量输出都打印：

```text
[heartbeat] waiting for Agent A/B; completed <P>/2
```

某 Agent 返回最终结果时，输出以下之一：

```text
[heartbeat] Agent <A|B> returned; verifying delivery
[heartbeat] Agent <A|B> failed; completed <P>/2
```

对成功返回的 Agent，用它在 `METAIN.md` 中的**精确** branch/path（不做广泛发现）
验证：

```bash
git merge-base --is-ancestor <EXPECTED_BASE> <branch>
test "$(git merge-base <branch> <EXPECTED_BASE>)" = "<EXPECTED_BASE>"
test "$(git rev-parse <branch>)" != "<EXPECTED_BASE>"
git cat-file -e <branch>:wave-demo-agent-<a|b>.md
git -C <worktree_path> status --porcelain
```

并检查最终 Agent 输出含 `DEMO_RESULT`、相同 `agent_id` 与同一 `EXPECTED_BASE`。
只有全部通过，才把该 Agent 标成 `completed` 并输出：

```text
[heartbeat] Agent <A|B> completed; Git delivery verified; completed <P>/2
```

若 Agent 完成事件没有到达，执行有界 spot-check：检查 manifest 中对应 branch 的新提交、
预期文件和 worktree 状态。若三项均成立，记录 `completed (spot-check)`；若连续三轮
（每轮 30 秒）都没有完成事件、提交或预期文件，记录 `failed (stalled)` 并通知用户。

## 4. 结束

读取并展示 `METAIN.md`，汇总 A/B 的 metadata、启动/完成心跳和验证结果。这个 demo
刻意不 merge、不删除分支、不清理 worktree；它们是下一阶段的学习输入。

最终用简短说明区分两类返回：`Agent(...)` 的启动 metadata 是调度句柄；`TaskOutput`
或 completion notification 的最终输出才是 Agent 业务结果。`METAIN.md` 加 Git
交付物是可恢复、可审计的事实来源。
