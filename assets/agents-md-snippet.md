# 技能管理规范（粘贴到全局 AGENTS.md / CLAUDE.md）

<!-- 把下面整段并入 ~/AGENTS.md、~/.codex/AGENTS.md 或 CLAUDE.md，使所有 Agent 都走同一套流程 -->

## Skill 管理

本机所有 Agent 技能由 `skill-manager` 统一管理：一个 Git 仓库（默认 `~/skills-repo`）是唯一真相源，
各 Agent 目录里只有指向它的链接（零复制、零漂移）。已知 73 种 Agent 目录
（Claude Code / Codex / Pi / DSH / Gemini / Antigravity / Copilot / Cursor / Windsurf /
Cline / Roo / Kilo / OpenCode / Kimi / Qwen / 通义灵码 / iFlow / Qoder / CodeBuddy / CodeArts /
ZCode / MiniMax / Trae …）。

- **安装技能**：只能用 `skill-manager`（`scripts/skillkit.py add <dir|git-url> --apply`）。
  禁止运行 Agent 自带的安装器往 `~/.codex/skills`、`~/.claude/skills`、`~/.pi/agent/skills`、
  `~/.agents/skills`、`~/.copilot/skills` 等目录写文件。
- **修改技能**：在 `~/skills-repo/skills/<name>/` 里改，不要在 Agent 目录里改（那里是链接）。
- **同名冲突**：以**最新修改时间**的那份为准；其余备份到 `.skill-manager/backup/`。
  不要手工猜测版本。
- **同步**：`skillkit.py push --apply` / `pull --apply`；换机用 `init` 或 `restore`。
- **边界**：只操作当前用户。项目级技能（`<project>/.claude/skills` 等）不动；
  已被其它工具管理的目录（symlink、`skills-lock.json`、`install.json`、内含 `.git`）跳过并报告。
- **删除**：默认只移动到 `.skill-manager/trash/`。真要删文件（违反"禁止批量删除"规则）时，
  先列出准确路径 → 等用户确认 → 再用 `trash --purge <name> --confirm-delete`。
  永不使用 `rm -rf`、`del /s`、`Remove-Item -Recurse`、`shutil.rmtree`。
- **写操作一律先 dry-run**：默认不加 `--apply` 只打印计划；念给用户确认后再执行。
- **出问题先诊断**：`targets` → `status` → `list` → `doctor`（`--fix` 只修链接）。

技能路径：`skill-manager/scripts/skillkit.py`（Python 3.8+，仅标准库）。
