# AI Capabilities

| Ability | Claude Code | Codex | Status | Purpose |
|---|---|---|---|---|
| `planAlign` / `plan-align` | `.claude/commands/planAlign.md` | `plugins/didala-plugin/skills/plan-align/SKILL.md` | Active | 飞书需求评审、问题对齐、方案设计、流程图呈现、表结构规范、功能需求点排期与评审文档回写 |
| `dbSchema` | `.claude/commands/dbSchema.md` + `.claude/scripts/db_schema_helper.py` | — | Active | 本地辅助程序优先从 XML、也可从其他配置识别 MySQL/MariaDB/PostgreSQL 连接信息；只向 Claude 返回脱敏元数据，确认后以超时受控的短连接获取完整 DDL 与字段说明字典。Generator XML、KMS/加密/外部托管 datasource 会输出诊断并安全停止 |
| `worktreeNew` / `worktreeClean` / `worktree-flow` | `.claude/commands/worktreeNew.md`, `.claude/commands/worktreeClean.md` | `plugins/didala-plugin/skills/worktree-flow/SKILL.md` | Active | 安全创建和清理当前项目的 Git worktree，统一放到 `/Users/zz/worktree`，清理前检查未合并分支、未提交内容和删除后的残留目录 |
| `waveDemo` | `.claude/commands/waveDemo.md` | — | Active | 教学用：用 Claude Code 原生 worktree Agent 串行 dispatch 两个任务、后台并行运行，写入 `METAIN.md`，等待、心跳和 Git 交付核验 |

## Capability Template

新增能力时，建议记录：

- 名称：命令名或 skill 名。
- 适用平台：Claude Code / Codex / both。
- 触发方式：用户自然语言或 slash command 示例。
- 输入：需要用户提供的信息。
- 输出：最终沉淀物或交付物。
- 外部依赖：例如飞书、GitHub、数据库、内部系统等。
- 安全边界：哪些动作需要用户确认。
