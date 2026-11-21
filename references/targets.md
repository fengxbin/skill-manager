# Agent 目标目录表（targets）

`scripts/skillkit.py` 采用**三层目录发现机制**，避免因 Agent 版本迭代换目录或出现新工具而漏检：

1. **静态基线表（73 种已知 Agent）**：`_TARGET_SPEC` 提供规范 ID 与多候选路径。
2. **主动浅层动态发现（默认开启，`--no-discover` 可关闭）**：自动扫描当前用户配置根（`~/.*`、`~/.config/*`，以及 Windows `%APPDATA%\<App>\skills`、macOS `~/Library/Application Support/<App>/skills`），通过 `SKILL.md` 内容特征或空 `skills/` 约定目录发现不在表里的新目录（`SRC = auto`），同时严格排除工具内置只读目录（`.system`、`skills-cursor`、`builtin`）、缓存和 `node_modules`。
3. **自定义目录持久化**：`skillkit targets --add <id> <relpath>` 将新路径写入 `skill-manager.json` 的 `custom_targets`（`SRC = cust`），`--remove <id>` 移除。

如需把某个新工具沉淀进静态基线表，只需在 `_TARGET_SPEC` 里加一行元组：

```python
("newtool", "New Tool", [".newtool/skills"], "auto", "海外", "doc"),
#  id        label      候选目录列表        绑定    分组    来源
```

- **候选目录**：列出该工具所有已知写法；**存在的每一个都会被链接**（有的工具改过目录名，
  有的机器上装了同一工具的两个版本）。建新目录时用第一个。
- **绑定**：`always` = 不存在也创建（跨工具的中立落点）；`auto` = 只有已存在才链接。
- **来源**：`doc` = 厂商文档明确；`probable` = 社区/间接证据；`cust` = 用户自定义；`auto` = 主动动态发现。

## 全部目标

| id | 工具 | 全局目录（相对 HOME） | 绑定 | 来源 |
|---|---|---|---|---|
| `agents` | 通用 ~/.agents（Cline/Codex/Cursor/Kimi/Pi/Warp/Zed/Antigravity…） | `.agents/skills` | 总是创建 | 官方文档 |
| `config-agents` | 通用 ~/.config/agents（Amp/Replit/Universal/Kimi 推荐） | `.config/agents/skills` | 总是创建 | 官方文档 |
| `claude` | Claude Code（含 GLM Coding Plan 走 Claude 的场景） | `.claude/skills` | 存在才绑定 | 官方文档 |
| `codex` | OpenAI Codex CLI | `.codex/skills` | 存在才绑定 | 官方文档 |
| `gemini` | Google Gemini CLI | `.gemini/skills` | 存在才绑定 | 官方文档 |
| `antigravity` | Google Antigravity / Antigravity CLI | `.gemini/config/skills`<br>`.gemini/antigravity/skills`<br>`.antigravity/skills` | 存在才绑定 | 官方文档 |
| `copilot` | GitHub Copilot CLI | `.copilot/skills` | 存在才绑定 | 官方文档 |
| `cursor` | Cursor | `.cursor/skills` | 存在才绑定 | 官方文档 |
| `windsurf` | Windsurf (Codeium) | `.codeium/windsurf/skills`<br>`.windsurf/skills` | 存在才绑定 | 官方文档 |
| `opencode` | opencode | `.config/opencode/skills`<br>`.config/opencode/skill` | 存在才绑定 | 官方文档 |
| `amp` | Amp (Sourcegraph) | `.config/amp/skills` | 存在才绑定 | 官方文档 |
| `crush` | Crush (Charm) | `.config/crush/skills` | 存在才绑定 | 官方文档 |
| `goose` | Goose (Block) | `.config/goose/skills` | 存在才绑定 | 官方文档 |
| `devin` | Devin for Terminal | `.config/devin/skills` | 存在才绑定 | 官方文档 |
| `droid` | Factory Droid | `.factory/skills` | 存在才绑定 | 官方文档 |
| `augment` | Augment Code | `.augment/skills` | 存在才绑定 | 官方文档 |
| `continue` | Continue | `.continue/skills` | 存在才绑定 | 官方文档 |
| `cline` | Cline | `.cline/skills` | 存在才绑定 | 官方文档 |
| `roo` | Roo Code | `.roo/skills` | 存在才绑定 | 官方文档 |
| `kilo` | Kilo Code | `.kilo/skills` | 存在才绑定 | 官方文档 |
| `kiro` | Kiro CLI (AWS) | `.kiro/skills` | 存在才绑定 | 官方文档 |
| `junie` | Junie (JetBrains) | `.junie/skills` | 存在才绑定 | 官方文档 |
| `openhands` | OpenHands | `.openhands/skills` | 存在才绑定 | 官方文档 |
| `openclaw` | OpenClaw | `.openclaw/skills` | 存在才绑定 | 官方文档 |
| `aider-desk` | AiderDesk | `.aider-desk/skills` | 存在才绑定 | 官方文档 |
| `tabnine` | Tabnine CLI | `.tabnine/agent/skills` | 存在才绑定 | 官方文档 |
| `zencoder` | Zencoder / Zenflow | `.zencoder/skills` | 存在才绑定 | 官方文档 |
| `rovodev` | Rovo Dev (Atlassian) | `.rovodev/skills` | 存在才绑定 | 官方文档 |
| `cortex` | Cortex Code (Snowflake) | `.snowflake/cortex/skills` | 存在才绑定 | 官方文档 |
| `grok` | Grok Build | `.grok/skills` | 存在才绑定 | 官方文档 |
| `vibe` | Mistral Vibe | `.vibe/skills` | 存在才绑定 | 官方文档 |
| `posit` | Posit Assistant | `.posit/assistant/skills` | 存在才绑定 | 官方文档 |
| `bob` | IBM Bob | `.bob/skills` | 存在才绑定 | 官方文档 |
| `firebender` | Firebender | `.firebender/skills` | 存在才绑定 | 官方文档 |
| `forgecode` | ForgeCode | `.forge/skills` | 存在才绑定 | 官方文档 |
| `commandcode` | Command Code | `.commandcode/skills` | 存在才绑定 | 官方文档 |
| `codemaker` | Codemaker | `.codemaker/skills` | 存在才绑定 | 官方文档 |
| `codestudio` | Code Studio | `.codestudio/skills` | 存在才绑定 | 官方文档 |
| `deepagents` | Deep Agents | `.deepagents/agent/skills` | 存在才绑定 | 官方文档 |
| `hermes` | Hermes Agent | `.hermes/skills` | 存在才绑定 | 官方文档 |
| `mcpjam` | MCPJam | `.mcpjam/skills` | 存在才绑定 | 官方文档 |
| `jazz` | Jazz | `.jazz/skills` | 存在才绑定 | 官方文档 |
| `kimchi` | Kimchi | `.config/kimchi/harness/skills` | 存在才绑定 | 官方文档 |
| `kode` | Kode (shareAI) | `.kode/skills` | 存在才绑定 | 官方文档 |
| `moxby` | Moxby | `.moxby/skills` | 存在才绑定 | 官方文档 |
| `mux` | Mux | `.mux/skills` | 存在才绑定 | 官方文档 |
| `ona` | Ona | `.ona/skills` | 存在才绑定 | 官方文档 |
| `reasonix` | Reasonix | `.reasonix/skills` | 存在才绑定 | 官方文档 |
| `terramind` | Terramind | `.terramind/skills` | 存在才绑定 | 官方文档 |
| `tinycloud` | Tinycloud | `.tinycloud/skills` | 存在才绑定 | 官方文档 |
| `neovate` | Neovate | `.neovate/skills` | 存在才绑定 | 官方文档 |
| `pochi` | Pochi | `.pochi/skills` | 存在才绑定 | 官方文档 |
| `adal` | AdaL | `.adal/skills` | 存在才绑定 | 官方文档 |
| `autohand` | Autohand Code CLI | `.autohand/skills` | 存在才绑定 | 官方文档 |
| `inferencesh` | inference.sh | `.inferencesh/skills` | 存在才绑定 | 官方文档 |
| `zed` | Zed | `.zed/skills` | 存在才绑定 | 社区推断 |
| `warp` | Warp | `.warp/skills` | 存在才绑定 | 社区推断 |
| `astrbot` | AstrBot | `.astrbot/data/skills` | 存在才绑定 | 官方文档 |
| `pi` | Pi agent | `.pi/agent/skills`<br>`.pi/skills` | 存在才绑定 | 官方文档 |
| `dsh` | DeepSeek Harness | `.dsh/skills` | 存在才绑定 | 官方文档 |
| `kimi` | Kimi Code CLI（月之暗面） | `.kimi/skills`<br>`.kimi-code/skills` | 存在才绑定 | 官方文档 |
| `qwen` | Qwen Code（阿里） | `.qwen/skills` | 存在才绑定 | 官方文档 |
| `lingma` | 通义灵码 Lingma（阿里） | `.lingma/skills` | 存在才绑定 | 官方文档 |
| `iflow` | iFlow CLI 心流（阿里/心流） | `.iflow/skills` | 存在才绑定 | 官方文档 |
| `qoder` | Qoder（阿里国际） | `.qoder/skills` | 存在才绑定 | 官方文档 |
| `qoder-cn` | Qoder CN（阿里） | `.qoder-cn/skills` | 存在才绑定 | 官方文档 |
| `codebuddy` | CodeBuddy / WorkBuddy（腾讯） | `.codebuddy/skills`<br>`.workbuddy/skills` | 存在才绑定 | 官方文档 |
| `codearts` | CodeArts Agent（华为云） | `.codeartsdoer/skills` | 存在才绑定 | 官方文档 |
| `zcode` | ZCode / 智谱 GLM Coding | `.zcode/skills` | 存在才绑定 | 官方文档 |
| `minimax` | MiniMax Code | `.minimax/skills` | 存在才绑定 | 官方文档 |
| `trae` | Trae（字节） | `.trae/skills` | 存在才绑定 | 官方文档 |
| `trae-cn` | Trae CN（字节国内版） | `.trae-cn/skills` | 存在才绑定 | 官方文档 |
| `doubao` | 豆包 / Doubao Work（字节，客户端上传技能包，本地目录未公开） | `.doubao/skills`<br>`.doubao-work/skills` | 存在才绑定 | 社区推断 |

## 收录依据

- Agent Skills 开放规范：<https://agentskills.io>
- 75+ 工具的全局/项目路径清单：`vercel-labs/skills` 的 `docs/agents.md`
- 各家官方文档：Google Antigravity、Kimi Code CLI、Qwen Code、CodeBuddy、Z.ai ZCode、
  Cline/Kilo/Roo、OpenCode、Crush、Goose、Droid、Kiro、Junie、Copilot、Windsurf 等

## 国产工具的实际情况

| 工具 | 状态 |
|---|---|
| Kimi Code CLI（月之暗面） | `~/.kimi/skills`，同时读 `~/.config/agents/skills`、`~/.agents/skills` |
| Qwen Code（阿里） | `~/.qwen/skills` |
| 通义灵码 Lingma（阿里） | `~/.lingma/skills` |
| iFlow CLI 心流 | `~/.iflow/skills` |
| Qoder / Qoder CN（阿里） | `~/.qoder/skills`、`~/.qoder-cn/skills` |
| CodeBuddy / WorkBuddy（腾讯） | `~/.codebuddy/skills`（IDE 与 CLI 同目录） |
| CodeArts Agent（华为云） | `~/.codeartsdoer/skills` |
| ZCode / 智谱 GLM Coding | `~/.zcode/skills`；用 GLM Coding Plan 跑 Claude Code 时走 `~/.claude/skills` |
| MiniMax Code | `~/.minimax/skills` |
| Trae / Trae CN（字节） | `~/.trae/skills`、`~/.trae-cn/skills` |
| 豆包 / Doubao Work（字节） | **没有公开的本地技能目录**：技能是在客户端里上传/管理技能包（含 `SKILL.md`）。已加入 `~/.doubao/skills`、`~/.doubao-work/skills` 作为"存在才绑定"的候选，实际不会创建。要让豆包用上同一份技能，走"客户端上传技能包"，把仓库里的目录打包上传。 |

## 环境（environments）

| 环境 | HOME 根 | 说明 |
|---|---|---|
| `local` | `$HOME` | 当前系统（Linux / macOS / WSL 内） |
| `windows` | `%USERPROFILE%`（WSL 下经 `cmd.exe` 探测） | **只处理当前活跃 Windows 会话的 `%USERPROFILE%`** |

**用户边界保护**：WSL 下只读当前 Windows 会话的 `%USERPROFILE%`（永不枚举 `C:\Users\*` 下其他用户目录）；
若 WSL 当前用户为 `root` 则直接拒绝（`--allow-cross-user` 才例外）；若非 root 用户名与 Windows 目录名不同
（微软账号常见截断），会输出提示 note 透明告知。任何解析出来的目标目录如果不在该环境 HOME 之下，
也会被拒绝（`refusing target outside ...`）。

**跨边界规则**

- WSL 可以读 Windows 目录（`/mnt/c/...`），所以 `init --include-windows` 能收编 Windows 侧的技能。
- Windows 读不到 WSL 的 ext4，所以仓库要放在 Windows 可见盘（`/mnt/d/skills-repo` ↔ `D:\skills-repo`）。
- 每个环境的链接在各自环境内创建：WSL 建 symlink，Windows 建 junction；两端各自维护独立的状态文件
  `state-<platform>-<host>.json`，互不覆盖。

## 查看本机情况

```bash
python3 scripts/skillkit.py targets          # 只列"真实存在"的目录 + 待创建的中立落点
python3 scripts/skillkit.py targets --json   # 结构化，含 alternates / family / src
```

## 不在默认范围内

| 位置 | 为什么跳过 | 怎么办 |
|---|---|---|
| `<project>/.claude/skills`、`<project>/.agents/skills` 等项目级目录 | 项目专属技能，进全局仓库会破坏项目独立性 | 先不动；需要时 `add <dir> --name <n>` |
| `~/.pi/agent/npm/node_modules/**/skills`、`node_modules` 内 | 第三方包自带，由包管理器负责 | 不动 |
| 已经是符号链接 / junction 的目录 | 已被其它工具管理 | `scan`/`init` 只报告并跳过 |
| 带 `skills-lock.json`、`.skill-manager.json`、`install.json` 或内含 `.git` 的目录 | 上游/其它工具管理，改了会被覆盖 | 用 `add <url>` 重新纳入仓库 |
| 其它用户的 HOME、`/root`、系统级目录 | 硬性边界：只操作当前用户 | 拒绝并报告 |
