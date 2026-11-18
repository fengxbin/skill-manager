# 设计与取舍

## 一句话

**Git 仓库是唯一真相源；Agent 目录里只有链接；同名冲突保留最新版本；只操作当前用户；写操作先 dry-run；删除一律变成移动 + 二次确认。**

## 设计要点从哪来

| 做法 | 为什么采纳 |
|---|---|
| `install === symlink`、仓库即真相源、没有 `update` 概念（改仓库即生效） | 零复制零漂移；改一次全员生效，不需要额外同步步骤 |
| 建链失败降级 junction、部署幂等 | 跨平台可用；重复执行不会破坏现状 |
| 多 Agent 目录清单 + `--agent` 式多目标分发 + lock 文件识别 | 一套内容服务多种工具；外部管理的技能能识别并避开 |
| `init / link / status / doctor / push / pull` 这类生命周期命令面 | 心智负担低；Agent 也能照着做 |
| 目录搬运失败时先备份、删除变成移动 | 任何一步都可回滚 |
| 写操作默认 dry-run、单文件输出 `--json` | Agent 与人都能安全使用 |

## 与原始讨论相比，补掉的遗漏

原始讨论（Codex/PI/DSH 共用 skill、自建仓库、软链、让 Agent 按规范安装）方向正确，
但落地时缺下面这些。每条都在实现里有对应机制。

1. **同名不同内容没有裁决规则（最致命的遗漏）**
   原始讨论假设"收进仓库"就行。实测本机 10 个目录里 **13 个重名、其中 10 个内容不同**
   （同一 skill 在 `~/.agents`、`~/.claude`、`~/.pi`、`~/.copilot`、Windows 侧
   `.codex/.claude/.gemini/.cursor/.copilot` 各一份，版本不一）。直接迁移等于随机丢弃某个版本。
   → 规则：**保留最新版本**（`--prefer newest`，平票看副本数/文件数）；dry-run 列出每个变体的
   副本数、时间、示例路径；败者进 `backup/` + `trash/`。

2. **Agent 覆盖太少（只有 Codex/PI/DSH/Claude）**
   → 建成 **73 条**的目标表（`_TARGET_SPEC`）：海外 50+（含 Google Antigravity、
   GitHub Copilot CLI、Cline/Roo/Kilo、Crush、Goose、Droid、Kiro、Junie、Zed、Warp、Amp…），
   国内（Kimi、Qwen Code、通义灵码、iFlow、Qoder、CodeBuddy/WorkBuddy、CodeArts、ZCode/智谱、
   MiniMax、Trae/Trae CN、豆包）。候选目录支持**多个写法**，存在的每一个都链。

3. **`gh` 不是必然存在，而且很多人不知道它是什么**
   `gh` = GitHub 官方 CLI。原始方案把它当默认路径，本机（WSL + Windows）根本没装。
   → `have_gh()` 同时检查存在性与 `gh auth status`；不满足就打印两条 `git remote add`/`git push`，
   并支持 `--repo-url` 接入已有仓库。

4. **"不要跨用户"必须写成硬边界**
   → 目标目录必须在该环境 HOME 之下（越界即 `refusing target outside ...`）；
   Windows profile 名与当前用户名不一致时直接拒绝并提示（`--allow-cross-user` 才例外）。

5. **WSL ↔ Windows 的链接是单向的**
   Windows 读不到 ext4。→ 仓库必须放 Windows 可见盘；每个环境各自建链；
   `to_win_path()` 翻译，目标不可见时直接报错而不是静默复制。

6. **Windows 上应该优先 junction 而不是 symlink**
   原始讨论写"symlink 失败降级 junction"，实践上应反过来：junction 不需要管理员/开发者模式，
   也不依赖 WSL 的 metadata。→ 对 `os.name == "nt"` 或 WSL 下 `/mnt/*` 目标优先 `mklink /J`。

7. **"备份/回滚"只说"以防万一"，没有路径**
   → 固定 `repo/.skill-manager/{backup,trash}/<ts>/<env>/<name>`，命令主动打印可恢复路径，
   文档写明回滚手法，`.gitignore` 排除。

8. **"迁移"是复制还是移动没说清**
   只复制 → 真目录挡住链接。→ 默认**移动**（先复制到 backup），`--copy` 保留；
   已在仓库里的重复副本：内容相同直接让位进 trash，不同则先备份。

9. **哪些目录该扫、哪些不该扫**
   → 默认只扫当前用户级目录；项目级（`<project>/.claude/skills` 等）不碰、只提醒；
   `node_modules` / 第三方包目录排除。

10. **已被别的工具管理的目录必须跳过并报告**
    symlink/junction、`skills-lock.json`、`.skill-manager.json`、`install.json`、内嵌 `.git`
    → `scan` 标 `[skip: managed by another tool]`，`init` 列在 "left alone" 清单（symlink 还显示指向），
    不接管、不覆盖。

11. **密钥泄露**
    "私有仓库"≠安全。→ `doctor` 扫 7 类模式 + 敏感文件名，推之前告警。

12. **删除与用户全局硬规则的冲突**
    用户硬规则：禁止批量/递归删除。→ 代码里没有 `rmtree`：`remove`/`init` 全部 move 到 trash，
    链接用 `os.unlink`/`os.rmdir`（单个链接点）。唯一删除入口是 `trash --purge`，
    需 `--confirm-delete` **且**手输 `DELETE`，删除前打印每一个路径，逐个 `os.unlink`。

## 明确不做的

- **不做数据库/状态中心**：状态从文件系统推导；`.skill-manager/state.json` 只是"这台机器建过哪些链"
  的缓存，坏了 `restore` 重建。
- **不作为 skill 商店**：不维护 lock、不做生态分发。装别人的技能走 `add <url>`。
- **不做 GUI / 后台守护**：只在显式执行命令时改变状态。
- **不跨用户、不代理写入另一侧环境**：两个环境各跑一次，行为可预测。
- **不接管项目级技能**：多项目共用一个全局仓库必然互相污染。

## 本地仓库位置策略

不做"每次都问"，也不写死一个目录，而是 **默认 + 记住 + 只在必要时问一次**：

| 优先级 | 来源 | 说明 |
|---|---|---|
| 1 | `--repo PATH` | 显式指定，最高优先 |
| 2 | `SKILLKIT_REPO` 环境变量 | CI、多仓库切换 |
| 3 | `~/.config/skillkit/location` | `init` 成功后写入；`repo --set/--forget` 管理 |
| 4 | 自动探测 | `~/skills-repo`、cwd 里的 `skill-manager.json` / `skills/` + `.git` |

推荐值（`init` 会打印理由）：

- WSL + 探测到 Windows profile → `/mnt/<第一个可用非 C: 盘>/skills-repo`（Windows 可见盘才两边都能用）
- 其它 → `<home>/skills-repo`

只在 `init`、只在交互终端、且优先值尚未记录时弹菜单；`--json` / `-y` / `CI` / 非 TTY 直接用推荐值并打印。
路径安全校验：不得落在某 Agent 的 skills 目录内、不得是 `skills/` 目录本身、不得在 OneDrive/Dropbox/iCloud 里。

**为什么这样设计**：默认值要能覆盖绝大多数机器，覆盖入口要足够简单（flag / 环境变量 / 一次性选择），
并且选择必须能被记住，否则每条命令都得带路径。WSL 与 Windows 并存是唯一会出现“默认值让功能静默失效”的场景，所以只有它需要主动提示。

## 数据结构

`skill-manager.json`（入库，人可读）：

```json
{
  "version": 1,
  "targets": null,
  "link_mode": "auto",
  "category_layout": true,
  "conflict_policy": "newest",
  "sources": { "some-skill": "https://github.com/owner/repo" }
}
```

`.skill-manager/state.json`（不入库）：`links[]`（name/path/target/env/target_id/kind）、
`backups[]`、`environments{}`。

## 幂等性

- `init` 重跑：已是链接的跳过，已在仓库的副本让位（必要时备份），被别家管理的一直跳过。
- `link` 重跑：指向正确就跳过，指向错误只替换链接点。
- `doctor --fix` 只补缺失/断链，不动内容。
- `add` 同名默认拒绝，`--force` 才替换（旧版进 trash）。

## 验证证据（写这份实现时的实测）

- 沙箱演练（假 `$HOME`，不影响真实目录）：迁移、最新版本裁决、幂等重跑、add/remove/restore/unlink、
  断链检测与 `--fix`、lock 管理跳过、trash 双重闸门、payload 不丢、可恢复。
- 本机 `scan --include-windows`：2 个环境、**10 个真实存在的 Agent 目录**、53+ 个 skill 名、
  10 个内容冲突；`targets` 列出 73 种已知 Agent，正确拒绝跨用户 profile。
- 实测新发现：`~/.copilot/skills` 里 11 个条目已经是 symlink（别家工具已链过）→ 被正确跳过并报告；
  `~/.config/opencode/skills` 使用复数写法 → 多候选目录机制命中。
- junction 实测：WSL 经 `cmd.exe /c mklink /J` 在 `C:\Users\...` 建链 → 可读、可解析、
  移除后目标文件完好。
