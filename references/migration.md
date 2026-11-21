# 迁移契约（给 Agent 执行）

这份文档是**指令**，不是说明文。Agent 读到它就应该能一步步跑完，不需要用户回忆命令。

## 0. 前置条件

```bash
command -v git python3     # 都必须存在
python3 -V                 # 需要 >= 3.8
# 可选：GitHub 官方 CLI（建私有仓库用）
command -v gh && gh auth status
```

缺 `python3`：先解决环境，不要用 shell 硬凑。
缺 `gh`：跳过 `--create-remote`，让用户手动建仓库后把 URL 交给你（`--repo-url`）。

## 1. 只读盘点（不写任何文件）

```bash
python3 scripts/skillkit.py targets          # 本机真实存在的 Agent 目录 + 拒绝/提示
python3 scripts/skillkit.py scan --include-windows --json
```

汇报三件事：

1. 一共多少个 skill、几个环境（`local` / `windows`）、扫到了哪些 Agent 目录。
2. `conflict: true` 的条目 —— 同名不同内容。逐条列出**每个变体**的路径 + 修改时间，
   并说明按规则会保留哪一份（最新）。
3. `managed_by` 非空的条目 —— 已被别的工具管理，本次**跳过并只报告**。

**此时不要执行任何 `--apply`。**

## 2. 边界（不可越线）

| 边界 | 规则 |
|---|---|
| 用户 | 只操作**当前用户**。目标目录必须在该环境 HOME 之下；超出即拒绝并报告 |
| Windows 侧 | 只处理当前活跃 Windows 会话的 `%USERPROFILE%`（永不枚举 `C:\Users\*` 其他用户）；若 WSL 以 `root` 运行则直接拒绝 |
| 项目级 | `<project>/.claude/skills`、`<project>/.agents/skills` 等**不动**，可以口头提醒 |
| 第三方管理 | 外部 symlink/junction、`skills-lock.json`、`.skill-manager.json`、`install.json`、内含 `.git` → 跳过（不参与冲突裁决） |
| 删除 | 一律先报告 + 等用户确认；默认只做"移动到 trash" |

## 3. 决定仓库位置

| 用户情况 | 仓库路径 |
|---|---|
| 只有 Linux / macOS | `~/skills-repo` |
| Windows 单环境 | `%USERPROFILE%\skills-repo` |
| WSL + Windows 双环境 | Windows 可见盘，如 `/mnt/d/skills-repo`（Windows 侧是 `D:\skills-repo`） |

WSL 下若用户坚持放 `~/skills-repo`（ext4），明确告知：Windows 侧 Agent 拿不到这批技能。

## 4. 远端仓库（私有）

已有仓库：

```bash
git clone <url> <repo-path>        # 或 init 时带 --repo-url <url>
```

没有仓库：

```bash
# gh 已认证（gh = GitHub 官方 CLI）
python3 scripts/skillkit.py init --repo <path> --create-remote --apply
# 无 gh：由 init 打印两条命令，交给用户执行
git -C <path> remote add origin git@github.com:<user>/skills-repo.git
git -C <path> push -u origin HEAD
```

`gh repo view <user>/skills-repo` 能查到就直接 clone，不要重复创建。

## 5. 迁移（唯一的破坏性步骤，且只是"移动"）

```bash
python3 scripts/skillkit.py init --repo <path> --include-windows        # dry-run
# ← 把计划念给用户：仓库路径、导入清单、冲突双方（路径+日期+谁胜出）、
#    将被备份/让位的重复副本、被跳过的"别家管理"目录、目标 Agent 目录列表
python3 scripts/skillkit.py init --repo <path> --include-windows --apply
```

`--apply` 按顺序做：

1. `git init` + `skill-manager.json` + `README.md` + `.gitignore` + `.gitattributes`（仓库为空时）。
2. 自动将 `skill-manager` 自身安全收编进 `skills/skill-manager/`（剥离 `.git`、记录上游 URL 到 `sources`；若原本装在某 Agent 目录内则先备份移走再换成链接；传 `--no-adopt-self` 可跳过）。
3. 每个 skill：先把原目录复制到 `.skill-manager/backup/<ts>/<env>/<name>/`，再**移动**到 `skills/<name>/`。
4. 同名多副本：**保留最新版本**（默认 `--prefer newest`）；其余备份后移入 `.skill-manager/trash/<ts>/`。
5. 自动创建通用落点（`~/.agents/skills`、`~/.config/agents/skills`）并在每个已存在的 Agent 目录建链（POSIX symlink，Windows junction）。
6. `git commit`；若已配置远端且通过密钥扫描，自动推送到 GitHub（加 `--no-push` 可跳过）。

**不要**自己写 `mv` / `ln -s` 代替这一步：备份、冲突裁决、幂等、跨平台链接都在脚本里。

## 6. 验证

```bash
python3 scripts/skillkit.py doctor --json
python3 scripts/skillkit.py list
```

- `problems` 必须为空；`warnings` 逐条报告（常见：无 remote、疑似密钥、被别家管理的目录）。
- `list` 里不允许出现 `BROKEN`。
- 抽查一个真实 Agent（例如 `~/.codex/skills/<name>/SKILL.md` 可读）。

## 7. 收尾

1. `python3 scripts/skillkit.py push --apply`（有 remote 时）。
2. 把 `assets/agents-md-snippet.md` 并入用户全局 `AGENTS.md` / `CLAUDE.md`。
3. 报告：导入数量、冲突裁决结果（谁是最新、旧的备份在哪）、跳过的目录及原因、
   未纳管项（项目级、外部安装器管理）。
4. 若用户还有另一套环境（Windows ↔ WSL），提醒在**另一侧**也跑一次
   `restore --apply`（同一仓库，各自建本地链接）。

## 8. 回滚与删除

```bash
ls <repo>/.skill-manager/backup/<ts>/     # 迁移前原样内容
ls <repo>/.skill-manager/trash/<ts>/      # 被判为重复而移走的副本
```

回滚：把目录**移动**回原 Agent 目录（先移除那里的链）。

清理垃圾（**删除**，必须用户确认）：

```bash
python3 scripts/skillkit.py trash                             # 只列出
python3 scripts/skillkit.py trash --purge <name>              # 打印全部路径后拒绝
python3 scripts/skillkit.py trash --purge <name> --confirm-delete   # 还需手输 DELETE
```

永远不要用 `rm -rf` / `del /s` / `Remove-Item -Recurse`；`purge` 内部是一次一个路径的删除。
