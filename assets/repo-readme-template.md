# skills-repo

我所有 Agent 技能的**唯一真相源**。

真实文件只存在于本仓库的 `skills/` 下；每个 Agent 的技能目录里只有一个指向本仓库的**链接**
（Linux/macOS/WSL: symlink，Windows: NTFS junction）。因此在仓库里改一次，所有 Agent 立刻生效
（零复制、零漂移），Git 负责跨设备同步。

已知 73 种 Agent 目录：Claude Code、OpenAI Codex、Pi、DeepSeek Harness、Google Gemini CLI、
**Google Antigravity**、GitHub Copilot CLI、Cursor、Windsurf、Cline、Roo Code、Kilo Code、
OpenCode、Crush、Goose、Factory Droid、AWS Kiro、JetBrains Junie、OpenHands、OpenClaw、Zed、
Warp、Amp、Augment、Continue、AiderDesk、Tabnine、Zencoder、**Kimi Code CLI**、**Qwen Code**、
**通义灵码 Lingma**、**iFlow 心流**、**Qoder**、**CodeBuddy / WorkBuddy**、**CodeArts Agent**、
**ZCode / 智谱 GLM**、**MiniMax Code**、**Trae / Trae CN** 等。完整列表见 skill-manager 技能里的
`references/targets.md`。

## 目录结构

```
skills-repo/
├── README.md              # 本文件
├── skill-manager.json     # 启用的 Agent 目标、链接模式、冲突策略、上游来源
├── skills/
│   └── <name>/SKILL.md    # 一个目录 = 一个技能（也允许 <category>/<name>/）
└── .skill-manager/        # gitignored: state / backup / trash
```

## 新增 / 修改一个技能

```bash
# 新增（本地目录或 Git 仓库）
python3 <skill-manager>/scripts/skillkit.py add <dir|git-url> --apply
python3 <skill-manager>/scripts/skillkit.py push --apply

# 修改：直接改 skills/<name>/ 下的文件；链接会立刻反映到所有 Agent
git add skills/<name> && git commit -m "update <name>" && git push
```

不要在这些地方直接编辑文件：`~/.agents/skills`、`~/.claude/skills`、`~/.pi/agent/skills`、
`~/.codex/skills`、`~/.copilot/skills`、`~/.kimi/skills`、`~/.qwen/skills`、`~/.codebuddy/skills` —— 
它们都是指向本仓库的链接。

## 链接关系

| Agent | 链接位置 |
|---|---|
| 通用目录（Cline / Codex / Cursor / Kimi / Pi / Warp / Zed / Antigravity 都读） | `~/.agents/skills/<name>` |
| 通用目录（Amp / Replit / Universal / Kimi 推荐） | `~/.config/agents/skills/<name>` |
| Claude Code（含 GLM Coding Plan） | `~/.claude/skills/<name>` |
| OpenAI Codex CLI | `~/.codex/skills/<name>` |
| Pi agent | `~/.pi/agent/skills/<name>` |
| DeepSeek Harness | `~/.dsh/skills/<name>` |
| Google Gemini CLI | `~/.gemini/skills/<name>` |
| Google Antigravity | `~/.gemini/config/skills/<name>` |
| GitHub Copilot CLI | `~/.copilot/skills/<name>` |
| Cursor | `~/.cursor/skills/<name>` |
| Windsurf | `~/.codeium/windsurf/skills/<name>` |
| Kimi Code CLI | `~/.kimi/skills/<name>` |
| Qwen Code | `~/.qwen/skills/<name>` |
| CodeBuddy（腾讯） | `~/.codebuddy/skills/<name>` |
| ZCode（智谱） | `~/.zcode/skills/<name>` |
| Trae（字节） | `~/.trae/skills/<name>` |

```bash
# POSIX 手工等价写法（脚本会自动做，这里只是备查）
mkdir -p ~/.claude/skills
ln -s ~/skills-repo/skills/<name> ~/.claude/skills/<name>
# Windows：junction，无需管理员权限
cmd /c mklink /J "%USERPROFILE%\.codex\skills\<name>" "D:\skills-repo\skills\<name>"
```

## 规则

- **同名冲突保留最新版本**：内容不同时以修改时间最新的为准，老版本备份到
  `.skill-manager/backup/`，不删除。
- **只操作当前用户**：不跨用户、不碰系统目录；项目级技能不动。
- **被别的工具管理的目录跳过**：symlink / `skills-lock.json` / `install.json` / 内嵌 `.git`。
- **不做递归删除**：`remove` 只是移动进 `.skill-manager/trash/`。

## 迁移到新机器

```bash
# 1. 克隆仓库（WSL + Windows 双环境：放在 Windows 可见盘，如 /mnt/d/skills-repo）
git clone <repo-url> ~/skills-repo

# 2. 重建全部链接（先 dry-run 看清单，再 --apply）
python3 <skill-manager>/scripts/skillkit.py restore --repo ~/skills-repo
python3 <skill-manager>/scripts/skillkit.py restore --repo ~/skills-repo --apply

# 3. 体检
python3 <skill-manager>/scripts/skillkit.py doctor --repo ~/skills-repo
```

机器上已有"野生"技能目录时，用 `init` 而不是 `restore`（会先备份再迁移，冲突保留最新版本）：

```bash
python3 <skill-manager>/scripts/skillkit.py init --repo ~/skills-repo --apply
```

## For Agents

如果你是帮用户操作本仓库的 AI Agent，遵守以下契约：

```markdown
1. 先跑只读命令：`skillkit.py targets` / `scan --json` / `list` / `doctor`，不要先动手。
2. 任何写操作先 dry-run，把计划（导入哪些、备份哪些、冲突谁胜出、链到哪些目录）
   念给用户，得到确认后才加 `--apply`。
3. 安装新技能只能走 `skillkit.py add <dir|url>`，禁止手工 `cp` 到任何 Agent 目录，
   禁止运行 Agent 自带的 skill 安装器写 `~/.codex/skills` 之类的位置。
4. 同名冲突以"最新修改时间"为准；把每个变体的路径和时间如实报给用户。
5. 只操作当前用户；项目级技能与"已被其它工具管理"的目录跳过并报告，不要接管。
6. 永不 `rm -rf` / `del /s` / `Remove-Item -Recurse`。删除技能用
   `skillkit.py remove <name> --apply`（移入 `.skill-manager/trash/`）。
   确实需要清理垃圾时：先列出准确路径 → 用户确认 → `trash --purge <name> --confirm-delete`
   （还需手输 DELETE）。
7. 迁移/同步过程中不要修改 `skills/` 里的内容；只做链接与同步操作。
8. 结束时跑 `doctor` 并如实汇报 problems / warnings；有 secrets 告警时先停手问用户。
9. 链接指向本仓库是正确状态；如果看到"真目录"而不是链接，说明还有未纳管的副本
   （或它被别的工具管理）。
```
