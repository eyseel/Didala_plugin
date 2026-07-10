---
name: worktree-flow
description: 安全创建和清理 Git worktree。Use when the user asks to create a worktree for the current project, clean project worktrees, inspect unmerged worktree branches, or manage /Users/zz/worktree directories.
---

# worktree-flow - Git worktree 安全工作流

你协助用户安全管理当前 Git 项目的 worktree。这个 workflow 只处理由本规则创建的 worktree，避免误删主工作区或其他项目目录。

## 固定约定

- worktree 根目录：`/Users/zz/worktree`
- 创建目录：`/Users/zz/worktree/<project_name>_worktree_<slug>`
- 创建分支：`worktree_<slug>`
- `<project_name>` 来自当前仓库根目录 basename，并把不适合路径/分支的字符转成 `_`
- `<slug>` 从用户描述总结，使用小写 snake_case，只允许 `a-z`、`0-9`、`_`，控制在 2 到 5 个英文词以内

## 创建 worktree

当用户要求“创建 worktree”“新建 worktree”“开一个 worktree 做某功能”时：

1. 确认当前目录在 Git 仓库中：`git rev-parse --show-toplevel`
2. 确认当前分支：`git branch --show-current`
   - 如果为空，停止；用户需要先切到一个正常分支。
3. 如果用户没有说明用途，先问清楚用途再继续。
4. 检查当前工作区：`git status --short`
   - 如果有未提交改动，说明新 worktree 基于当前 `HEAD`，不会自动带上未提交改动；继续前需要用户确认。
5. 生成目标分支名和目录名。
6. 检查分支是否已存在：`git show-ref --verify --quiet refs/heads/<branch_name>`
   - 已存在则停止，不覆盖。
7. 检查目标目录是否已存在。
   - 已存在则停止，不覆盖、不清空。
8. 创建根目录：`mkdir -p /Users/zz/worktree`
9. 创建 worktree：
   - `git worktree add -b <branch_name> <worktree_path> <current_branch>`

完成后展示：原项目根目录、基准分支、新分支名、worktree 工作目录、进入目录命令。

## 清理 worktree

当用户要求“清理 worktree”“删除 worktree”“清理当前项目 worktree”时：

1. 确认当前目录在 Git 仓库中：`git rev-parse --show-toplevel`
2. 确认当前分支：`git branch --show-current`
   - 如果为空，停止；用户需要先切到要作为合并判断目标的分支。
3. 读取 `git worktree list --porcelain`
4. 只选择同时满足以下条件的候选项：
   - 路径在 `/Users/zz/worktree/` 下
   - 目录名匹配 `<project_name>_worktree_<slug>`
   - 分支名匹配 `worktree_<slug>`
5. 对每个候选项检查：
   - 是否已合并到当前分支：`git merge-base --is-ancestor <branch_name> <current_branch>`
   - 是否有未提交内容：`git -C <worktree_path> status --porcelain --untracked-files=all`

## 清理策略

- 已合并且干净：直接 `git worktree remove <path>`，然后 `git branch -d <branch>`。
- 已合并但有未提交内容：先确认；确认后 `git worktree remove --force <path>`，然后 `git branch -d <branch>`。
- 未合并且干净：先确认；确认后只 `git worktree remove <path>`，保留分支。
- 未合并且有未提交内容：强提醒并确认；确认后只 `git worktree remove --force <path>`，保留分支。

默认不要删除未合并分支。只有用户明确要求“彻底删除未合并分支”或传入 `--delete-unmerged-branches`，并再次确认后，才允许在删除 worktree 后执行 `git branch -D <branch>`。

## 残留目录处理

`git worktree remove` 成功后，检查原路径是否仍然存在：`test -e <worktree_path>`。

如果目录不存在，记录为无残留。

如果目录仍然存在，说明可能有 IDEA、ignored 构建产物、`.idea`、`.DS_Store`、日志文件等残留。此时按下面规则处理：

1. 再次确认该路径已经不在 `git worktree list --porcelain` 输出中。
   - 如果仍在列表中，停止并报告；不要删除目录。
2. 再次确认路径在 `/Users/zz/worktree/` 下，basename 匹配 `<project_name>_worktree_<slug>`，且不是当前主工作区。
3. 检查 `<worktree_path>/.git`。
   - 如果 `.git` 文件或目录仍存在，停止并报告；不要 `rm -rf`。
4. 用 `find <worktree_path> -maxdepth 2 -mindepth 1 -print` 列出残留内容。
5. 提醒用户如果 IDEA 仍打开该目录，建议先关闭对应项目窗口。
6. 只有用户明确确认，或用户传入 `--delete-residual-dirs` 后你再次确认，才执行：
   - `rm -rf -- <worktree_path>`
7. 删除后再次检查路径是否还存在；如果仍存在，提示用户关闭 IDEA 或相关进程后重试。

残留目录删除只适用于已经成功从 Git worktree 列表中移除的路径。不要对仍被 Git 识别为 worktree 的目录执行 `rm -rf`。

## 禁止事项

- 不要使用 `rm -rf` 删除仍被 Git 识别为 worktree 的目录。
- 不要处理当前主工作区。
- 不要处理不在 `/Users/zz/worktree/` 下的目录。
- 不要处理不符合 `<project_name>_worktree_*` 和 `worktree_*` 命名规则的 worktree。
- 不要在 `git branch -d` 失败后自动改用 `git branch -D`。

## 输出格式

创建完成后输出：

| 字段 | 值 |
|---|---|
| 原项目根目录 | ... |
| 基准分支 | ... |
| worktree 分支 | ... |
| worktree 目录 | ... |
| 进入目录 | `cd ...` |

清理完成后输出：

| worktree 目录 | 分支 | 合并状态 | 工作区状态 | 动作 | 残留状态 |
|---|---|---|---|---|---|
| ... | ... | 已合并/未合并 | 干净/有未提交内容 | 删除 worktree / 删除分支 / 保留分支 / 跳过 | 无残留 / 有残留已删 / 有残留保留 / 残留删除失败 |
