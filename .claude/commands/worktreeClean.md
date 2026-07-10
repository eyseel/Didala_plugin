---
description: 安全清理当前 Git 项目在 /Users/zz/worktree 下的 worktree
argument-hint: [--delete-unmerged-branches]
allowed-tools: Bash, AskUserQuestion
---

# worktreeClean - 安全清理 worktree

你要清理当前 Git 项目下由 `worktreeNew` 工作流创建的 worktree。

用户输入的选项：`$ARGUMENTS`

## 识别范围

只能处理同时满足以下条件的 worktree：

- 属于当前 Git 仓库的 `git worktree list --porcelain` 输出
- 路径在 `/Users/zz/worktree/` 下
- 目录名匹配：`<project_name>_worktree_<slug>`
- 分支名匹配：`worktree_<slug>`

其中 `<project_name>` 来自当前仓库根目录 basename，并把不适合路径/分支的字符转成 `_`。

严禁处理：

- 当前主工作区
- 不在 `/Users/zz/worktree/` 下的 worktree
- 分支名不是 `worktree_*` 的 worktree
- 目录名不匹配当前项目名的 worktree

## 必须执行的安全检查

1. 确认当前目录在 Git 仓库中：
   - `git rev-parse --show-toplevel`
2. 确认当前分支：
   - `git branch --show-current`
   - 如果为空，说明处于 detached HEAD，停止并解释需要先切到要作为合并判断目标的分支。
3. 列出 worktree：
   - `git worktree list --porcelain`
4. 对每个候选 worktree 检查：
   - worktree 路径
   - 分支名
   - 是否已合并到当前分支：`git merge-base --is-ancestor <branch_name> <current_branch>`
   - 是否有未提交内容：`git -C <worktree_path> status --porcelain --untracked-files=all`

## 清理策略

按候选项分组后再行动：

### A. 已合并且干净

无需用户确认，直接清理：

```bash
git worktree remove <worktree_path>
git branch -d <branch_name>
```

如果 `git branch -d` 失败，停止并报告原因，不要改用 `-D`。

### B. 已合并但有未提交内容

必须先向用户确认。说明删除 worktree 会丢失这些未提交或未跟踪文件。

用户确认后：

```bash
git worktree remove --force <worktree_path>
git branch -d <branch_name>
```

如果用户不确认，跳过该 worktree。

### C. 未合并且干净

必须先向用户确认。说明该分支尚未合并到当前分支。

用户确认后默认只删除 worktree，保留分支：

```bash
git worktree remove <worktree_path>
```

保留分支的原因：分支里的提交仍可后续 `git merge <branch_name>`，也可以重新挂载 worktree。

### D. 未合并且有未提交内容

这是最高风险场景，必须强提醒：

- 分支提交尚未合并到当前分支
- 未提交或未跟踪文件删除后会丢失
- 默认只允许删除 worktree，保留分支

用户明确确认后：

```bash
git worktree remove --force <worktree_path>
```

## 关于删除未合并分支

默认不要删除未合并分支。

只有当用户输入包含 `--delete-unmerged-branches`，或者用户明确说“彻底删除未合并分支”，并且你再次确认后，才允许在删除 worktree 之后执行：

```bash
git branch -D <branch_name>
```

这个动作必须逐项列出分支名，并取得用户确认；不要批量静默强删。

## 完成后输出

输出清理结果表：

- worktree 路径
- 分支名
- 合并状态
- 工作区状态
- 执行动作：删除 worktree / 删除分支 / 保留分支 / 跳过

如果没有候选 worktree，说明当前项目没有符合本工作流命名规则的 worktree。
