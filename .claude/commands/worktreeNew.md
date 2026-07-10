---
description: 安全创建当前 Git 项目的 worktree，统一放到 /Users/zz/worktree
argument-hint: <这个 worktree 要做什么>
allowed-tools: Bash, AskUserQuestion
---

# worktreeNew - 安全创建 worktree

你要为用户在当前 Git 项目下创建一个新的功能 worktree。

用户输入的用途描述：`$ARGUMENTS`

## 目标命名规则

- worktree 根目录固定为：`/Users/zz/worktree`
- 项目名来自当前仓库根目录 basename，并把不适合路径/分支的字符转成 `_`
- 从用户输入总结一个简短英文 slug：
  - 小写 snake_case
  - 只允许 `a-z`、`0-9`、`_`
  - 控制在 2 到 5 个英文词以内
  - 如果用户输入为空，先问用户这个 worktree 用来做什么，不要继续
- 工作目录：`/Users/zz/worktree/<project_name>_worktree_<slug>`
- 分支名：`worktree_<slug>`

## 必须执行的安全检查

按顺序执行并向用户展示关键结果：

1. 确认当前目录在 Git 仓库中：
   - `git rev-parse --show-toplevel`
2. 确认当前分支：
   - `git branch --show-current`
   - 如果为空，说明处于 detached HEAD，停止并解释需要先切到一个分支。
3. 检查当前工作区是否干净：
   - `git status --short`
   - 如果有输出，说明当前主工作区有未提交改动。解释：新 worktree 会基于当前 `HEAD` 创建，不会自动带上未提交改动。必须询问用户是否继续；用户未确认时停止。
4. 检查目标分支是否已存在：
   - `git show-ref --verify --quiet refs/heads/<branch_name>`
   - 如果已存在，停止，不覆盖。提示用户换一个更具体的用途描述，或者手动决定是否复用旧分支。
5. 检查目标目录是否已存在：
   - 如果目标目录存在，停止，不覆盖、不清空。
6. 确保根目录存在：
   - `mkdir -p /Users/zz/worktree`

## 创建命令

通过当前分支创建新分支和 worktree：

```bash
git worktree add -b <branch_name> <worktree_path> <current_branch>
```

不要使用 `rm`、`git reset`、`git checkout --` 等破坏性命令。

## 完成后输出

创建成功后，用简洁表格展示：

- 原项目根目录
- 基准分支
- 新分支名
- worktree 工作目录
- 进入目录命令：`cd <worktree_path>`

如果任何一步失败，停止并说明失败点，不要尝试绕过安全检查。
