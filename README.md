# skill-manager

用**一个统一的本地仓库 `skills-repo`** 管理你所有 AI 编程 Agent（Claude Code、Codex、Cursor、Google Antigravity、Pi、Kimi、Qwen Code、CodeBuddy、Trae 等 **73 种工具**）的技能，并**自动同步到 GitHub**。

## 为什么需要它？

同时使用多个 AI 编程工具时，每个工具都有自己默认的技能目录（`~/.claude/skills`、`~/.codex/skills`、`~/.cursor/skills`、`~/.gemini/antigravity/skills`……）：
- 同一个技能会被重复下载多份，既占空间又容易版本不一致；
- 改了一个工具里的技能，其他工具不会同步；
- 换一台电脑或重装系统，所有技能都得重新找一遍。

**`skill-manager` 的做法**：

```text
                GitHub 私有仓库（云端备份 / 多设备同步）
                                  ▲
                                  │  add / update / remove 自动同步
                                  ▼
         本地唯一仓库：skills-repo（如 ~/skills-repo 或 D:\skills-repo）
                  ├── skills/<技能名>/SKILL.md
                  └── skill-manager.json
                     │            │            │
          软链接 / 目录联接（零复制，改一处所有工具同时生效）
                     ▼            ▼            ▼
      ~/.claude/skills    ~/.codex/skills    ~/.cursor/skills  ...（共 73 种）
```

1. **只存一份**：所有技能的真实文件统一放在 `skills-repo/skills/` 下；
2. **复用各工具默认目录，仅放链接**：各 Agent 的默认技能目录只放软链接（Linux/macOS/WSL 用 symlink，Windows 用无需管理员权限的 NTFS junction），零复制、零漂移；
3. **自动同步 GitHub**：每次下载（`add`）、更新（`update`）或移除（`remove`）技能，提交后自动推送到你的 GitHub 私有仓库（推前自动扫描敏感密钥，防止泄露）。

> **只需区分两个目录**：
> - **`skill-manager`（本仓库）**：管理工具本身（脚本 + 给 Agent 看的说明）。
> - **`skills-repo`（你的技能仓库）**：存放你个人所有技能的 Git 仓库，由 `init` 创建并推送到你自己的 GitHub。

---

## 快速开始（3 步）

环境要求：**Python 3.8+**（纯标准库，无需安装任何第三方依赖）和 **Git**。

### 第 1 步：安装 `skill-manager`（一条命令自动挂载到本机所有 Agent）

`skill-manager` 本身也是一个 skill，需要出现在 Agent 默认的技能目录里才能被识别。你**不需要**手动给每个工具敲 `ln -s` 或 `mklink`——直接运行内置的 `install --apply`，它会自动探测本机已安装的所有 Agent 默认目录（以及通用目录 `~/.agents/skills`）并一次性自动建好链接：

#### macOS / Linux

```bash
git clone https://github.com/fengxbin/skill-manager.git ~/skill-manager
python3 ~/skill-manager/scripts/skillkit.py install --apply

# （可选）把 CLI 加到 PATH，以后可直接敲 skillkit
mkdir -p ~/.local/bin && ln -sf ~/skill-manager/scripts/skillkit.py ~/.local/bin/skillkit
```

#### Windows（PowerShell，无需管理员权限）

```powershell
git clone https://github.com/fengxbin/skill-manager.git "$env:USERPROFILE\skill-manager"
python "$env:USERPROFILE\skill-manager\scripts\skillkit.py" install --apply
```

#### WSL + Windows 共用（推荐放 D 盘，两边都能访问）

Windows 读不到 WSL 内部目录（`~/`），所以放在 `D:` 盘，一条命令同时挂载 WSL 与 Windows 两侧的 Agent：

```bash
git clone https://github.com/fengxbin/skill-manager.git /mnt/d/skill-manager
python3 /mnt/d/skill-manager/scripts/skillkit.py install --include-windows --apply
```

> **只用单一工具？** 也可以直接 `git clone` 到该工具默认的技能目录（例如 `~/.claude/skills/skill-manager`），连 `install` 都不用跑；之后若想让其他工具也共用，再跑一次 `install --apply` 即可。

完成后**新开一个 Agent 会话**，Agent 就能识别 `skill-manager`。

---

### 第 2 步：初始化 `skills-repo` 并绑定 GitHub

你可以直接对 Agent 说：**「帮我盘点本机所有技能，然后初始化 skills-repo 并关联到我的 GitHub 私有仓库」**。

也可以自己敲命令：

```bash
# 1. 只读盘点：看看本机各 Agent 里有哪些技能、有没有重复或内容冲突
python3 ~/skill-manager/scripts/skillkit.py scan

# 2. 预览初始化计划（默认 dry-run，不会修改任何文件）
python3 ~/skill-manager/scripts/skillkit.py init

# 3. 确认无误后执行：收拢技能到 ~/skills-repo、在各 Agent 建链接并提交
# 方式 A：已在 GitHub 建好空私有仓库 skills-repo
python3 ~/skill-manager/scripts/skillkit.py init --repo-url git@github.com:<你的用户名>/skills-repo.git --apply

# 方式 B：已登录 GitHub CLI (gh)，自动建私有仓库并推送
python3 ~/skill-manager/scripts/skillkit.py init --create-remote --apply
```

> WSL + Windows 共用时，推荐放 D 盘并加上 `--include-windows`：
> `python3 /mnt/d/skill-manager/scripts/skillkit.py init --repo /mnt/d/skills-repo --include-windows --apply`
> 之后在 Windows 侧跑一次 `restore --apply` 即可给 Windows 侧所有 Agent 建好链接。

`init --apply` 会把 `skills-repo` 的路径记住在 `~/.config/skillkit/location`，后续所有命令都不需要再传 `--repo`。

---

### 第 3 步：日常使用

#### 方式一：直接跟 Agent 说话（推荐）

装好后不用背命令，直接把需求告诉 Agent（Pi 也支持 `/skill:skill-manager <动词>`）：

| 你想做什么 | 直接这么说 | 实际行为 |
|---|---|---|
| 安装/下载新技能 | “把这个技能装进来：`https://github.com/owner/repo`” | 克隆进 `skills-repo/skills/` → 链接到全部 Agent → **自动 push 到 GitHub** |
| 更新已装技能 | “帮我更新所有技能”（或指定技能名） | 重新拉取上游 → 替换并备份旧版 → 重建链接 → **自动 push 到 GitHub** |
| 盘点与检查 | “帮我检查一下本机技能和链接状态” | 运行 `scan` / `doctor`，报告冲突、断链、密钥风险 |
| 移除技能 | “把 `old-skill` 移掉” | 解除所有 Agent 链接 → 移入回收站 → **自动 push 到 GitHub** |
| 换机 / 拉取最新 | “同步一下 GitHub 上的最新技能” | `git pull --rebase` → 清理已删技能的死链接 → 补齐新技能链接 |

#### 方式二：CLI 命令速查

假设已将 `skillkit.py` 链接为 `skillkit`（未链接则替换为 `python3 <路径>/scripts/skillkit.py`）：

```bash
# 查看状态
skillkit targets                  # 本机识别到的 Agent 默认技能目录
skillkit scan                     # 只读盘点本机已有技能与冲突
skillkit list                     # 列出 skills-repo 中的技能及链接状态
skillkit status                   # 仓库、Git、auto_push 与链接概览
skillkit doctor                   # 全面体检（frontmatter、断链、未纳管目录、密钥风险）
skillkit doctor --fix --apply     # 自动修复缺失/过期链接并清理已删技能的死链

# 日常增删改（写操作默认 dry-run，加 --apply 执行；有 remote 时自动同步到 GitHub）
skillkit add <本地目录或Git地址> --apply          # 下载/导入技能 + 全员建链 + 自动 push
skillkit add <多技能仓库URL> --skill <名> --apply # 从多技能仓库挑选一个安装（或 --all 全装）
skillkit update [技能名...] --apply               # 从上游更新已记录 URL 的技能 + 自动 push
skillkit remove <技能名...> --apply               # 解除链接 + 移入回收站 + 自动 push

# 手动同步与换机恢复
skillkit push --apply             # 手动提交并推送到 GitHub（内置密钥拦截）
skillkit pull --apply             # 从 GitHub 拉取更新 + 清理死链 + 重建所有链接
skillkit restore --apply          # 新电脑 clone skills-repo 后，一条命令恢复全部链接
```

> **不想某次操作自动推送？** 加上 `--no-push` 即可；如果想全局关闭自动推送，把 `skills-repo/skill-manager.json` 里的 `"auto_push"` 改为 `false`。

---

## `skills-repo` 目录结构

```text
skills-repo/
├── README.md                  # 仓库说明（由 init 自动生成）
├── skill-manager.json         # 配置：目标 Agent、链接模式、冲突策略、auto_push、上游 URL
├── skills/
│   └── <技能名>/SKILL.md      # 唯一真实文件（也支持 skills/<分类>/<技能名>/SKILL.md）
└── .skill-manager/            # 已写入 .gitignore，不上传 GitHub
    ├── state-<平台>-<主机>.json  # 当前环境的链接缓存（WSL 与 Windows 独立隔离）
    ├── backup/<时间戳>/        # init 迁移前的原样备份
    └── trash/<时间戳>/         # remove 或冲突覆盖后的旧版本，可随时恢复
```

---

## 安全与边界原则

- **写操作默认演习（Dry-run）**：`install` / `init` / `add` / `update` / `remove` / `link` / `unlink` / `restore` / `push` / `pull` / `doctor --fix` 不加 `--apply` 绝不改动文件。
- **永不递归删除**：`remove` 和冲突覆盖只会把文件**移动**到 `.skill-manager/trash/`；真正清空回收站需要 `trash --purge <条目名> --confirm-delete` 并手动输入 `DELETE`。
- **同名冲突不乱覆盖**：同一技能在多个 Agent 中内容不同时，默认保留**最后修改时间最新**的一份，其余先备份再替换为链接。
- **推前密钥拦截**：自动同步和 `push` 之前会扫描 7 类常见密钥（GitHub PAT、OpenAI Key、AWS Key、私钥、`.env` 等），命中时直接拦截推送（确认为误报时可用 `--allow-secrets` 放行）。
- **克制边界**：只操作当前用户目录；项目级目录（`<project>/.claude/skills` 等）和已被其他工具管理的目录（外部 symlink、`skills-lock.json`、`install.json`、内嵌 `.git`）一律跳过并仅作报告。

---

## 常见问题

**Q：换了一台新电脑怎么快速恢复所有技能？**
```bash
git clone git@github.com:<你的用户名>/skills-repo.git ~/skills-repo
python3 ~/skill-manager/scripts/skillkit.py restore --repo ~/skills-repo --apply
python3 ~/skill-manager/scripts/skillkit.py doctor
```

**Q：如何修改一个已有技能？**
直接编辑 `skills-repo/skills/<技能名>/` 下的文件即可。因为各 Agent 默认目录里全是链接，改完立刻对所有工具生效；随后运行 `skillkit push --apply` 同步到 GitHub。

**Q：为什么 `add` 从 GitHub 装技能后，仓库里没有嵌套 `.git`？**
`add` 会先克隆到系统临时目录，再**剥离 `.git` 仅复制技能文件**到 `skills-repo/skills/<技能名>/`，同时把上游地址记录到 `skill-manager.json` 的 `sources` 中，后续运行 `skillkit update --apply` 即可一键跟进上游更新。

**Q：工具会自动创建 `~/.agents/skills` 吗？**
会。`~/.agents/skills` 和 `~/.config/agents/skills` 是多款工具（Codex、Cursor、Kimi、Pi、Antigravity、Cline、Warp、Zed 等）共同认可的通用目录，会被自动创建并链接；同时本机已存在的各工具专属默认目录（如 `~/.claude/skills`、`~/.codex/skills`、`~/.gemini/antigravity/skills`）也会一并链接，无需你关心每个工具到底读哪个。

---

## 更多文档

- [SKILL.md](SKILL.md)：给 AI Agent 执行的操作契约与 Slash 触发说明
- [references/targets.md](references/targets.md)：全部 73 种受支持 Agent 的目录清单
- [references/migration.md](references/migration.md)：从散落目录迁移到 `skills-repo` 的标准步骤
- [references/troubleshooting.md](references/troubleshooting.md)：Windows Junction、WSL、冲突与密钥排错
- [references/design.md](references/design.md)：架构设计取舍与数据格式
