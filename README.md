# skill-manager

多 Agent 技能管理器：**一个 Git 仓库是唯一真相源，各 Agent 目录里只放指向它的链接**
（POSIX 用 symlink，Windows 用 junction）。改仓库一次全员生效；换机 `clone` + `restore` 恢复。
支持 73 种 Agent 目录，清单见 [`references/targets.md`](references/targets.md)。
所有逻辑在 `scripts/skillkit.py`（Python 3.8+，仅标准库）。

## 快速开始

```bash
S=<skill>/scripts/skillkit.py

python3 $S targets                  # 本机有哪些 Agent 目录
python3 $S scan --include-windows   # 只读盘点：副本数 / 内容冲突 / 被别家管理的
python3 $S init                     # dry-run（交互终端会问一次仓库位置）
python3 $S init --apply             # 备份 + 迁移 + 建链 + 本地提交
python3 $S doctor                   # 体检
```

日常与换机：

```bash
python3 $S add <repo-url|dir> --apply     # 安装 = 进仓库 + 建链 + 提交
python3 $S push --apply                   # 推远端
python3 $S pull --apply                   # 拉取 + 重建链
python3 $S list                           # 每个技能链到了哪里
python3 $S remove <name> --apply          # 解链 + 移入 .trash

git clone <repo-url> ~/skills-repo && python3 $S restore --apply && python3 $S doctor   # 换机
```

## 在 Agent 里怎么用

技能被链接进 Agent 后，客户端会自动把它变成一个斜杠命令：Pi 用 `/skill:skill-manager <动词>`
（如 `/skill:skill-manager doctor`），Claude Code / Cursor 在 `/` 菜单里出现，
Codex 只支持技能（`/prompts` 已移除）。也可以用自然语言直接说"帮我盘一下 skill 有没有冲突"。
动词与命令的对应关系见 `SKILL.md` 的 Slash entry points 一节。

## 仓库位置

`--repo` → `SKILLKIT_REPO` → `~/.config/skillkit/location`（`init` 写入，之后无需带路径）→ 自动探测。
`python3 $S repo` 查看来源，`repo --set PATH` / `--forget` 管理。
推荐值：WSL 且有 Windows 环境 → `/mnt/<非C盘>/skills-repo`（两侧都能用）；否则 `~/skills-repo`。
落在 Agent skills 目录内、`skills/` 本身、或云同步盘里的路径会被拒绝。

## 命令

所有写操作默认 **dry-run**，须加 `--apply`；`--json` 输出可解析结果。

| 命令 | 作用 |
|---|---|
| `targets` / `scan` | 本机 Agent 目录 / 技能盘点（含冲突与被别家管理项） |
| `init` | 建仓库 → 迁移（备份/移动）→ 建链 → 提交 |
| `add <dir\|url>` / `update` | 安装技能 / 按记录的上游刷新 |
| `link` / `unlink` | 建链 / 解链（文件本体留在仓库） |
| `remove` / `trash` | 解链后移入 `.trash` / 列垃圾箱或 `--purge` |
| `restore` | 按仓库内容重建全部链接 |
| `list` / `status` / `doctor` | 查看 / 状态 / 体检（`--fix` 只修链接） |
| `repo` | 仓库位置：查看 / 设置 / 清除记录 |
| `push` / `pull` | Git 同步 |

## 规则

1. **同名冲突保留最新版本**：取修改时间最新的一份，其余备份到 `.skill-manager/backup/`，
   原位置改为链接（`init` 会列出每个变体的副本数、时间、路径）。
2. **只操作当前用户**：目标必须在当前用户 HOME 下；WSL 侧只处理同名 Windows profile，
   不一致直接拒绝（`--allow-cross-user` 才例外）。
3. **项目级与已被别家管理的技能不动**：`<project>/.claude/skills` 等不在范围；已是
   symlink/junction、或带 `skills-lock.json`/`install.json`/内嵌 `.git` 的目录只报告、不接管。

## 删除与回滚

无递归删除：`init` 先复制到 `backup/<ts>/` 再移动原目录；`remove` 移动到 `trash/<ts>/<name>`；
`trash` 默认只列清单。真要清理时先打印全部路径，再加 `--confirm-delete` 并手输 `DELETE`：

```bash
python3 $S trash --purge <name> --confirm-delete
```

回滚：把 `backup/<ts>/` 或 `trash/<ts>/` 中的目录移回原位置（先移除该处链接）。
推送前 `doctor` 会扫描疑似密钥并告警。

## 文件

`SKILL.md`（Agent 操作契约）· `scripts/skillkit.py` ·
`references/{targets,migration,troubleshooting,design}.md` ·
`assets/{repo-readme-template,agents-md-snippet}.md`、`config.example.json`
