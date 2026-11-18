# skill-manager

让所有 AI 编程工具（Pi、Codex、Claude Code、Cursor、Kimi、Qwen Code、CodeBuddy…共 73 种）
**共用同一份技能文件**。技能只存一份，工具目录里放的是"快捷方式"（软链接），
所以改一次全部生效，换电脑一条命令恢复。

## 先分清两个东西，不然一定糊涂

| | 是什么 | 放在哪 |
|---|---|---|
| ① **本项目** | 工具本身（几个脚本 + 说明） | 你 clone 下来的目录，比如 `~/skill-manager` |
| ② **你的技能仓库** | 存你所有技能的地方（一个 Git 仓库，可以推到自己的 GitHub） | 由 `init` 创建，比如 `~/skills-repo` 或 `D:\skills-repo` |

①是"管家"，②是"仓库"。装①只是让 Agent 学会用这个管家；②要等你说一句"初始化技能仓库"才会建。

## 一、安装（3 步）

**第 1 步：下载到哪**

`git clone <地址> <目标目录>` —— 第二个参数就是下载位置，不写则下载到**当前目录**下的同名文件夹。
本项目本身只有一个技能，建议按下表选位置（**只下一份**，别下两遍，否则会各改各的）：

| 你的情况 | 下载到 | WSL 里的路径 | Windows 里看到的路径 |
|---|---|---|---|
| 只用 WSL 里的工具（Pi 等） | `~/skill-manager` | `/home/你/skill-manager` | Windows 看不到 |
| WSL + Windows 都要用（推荐） | D 盘 | `/mnt/d/skill-manager` | `D:\skill-manager` |
| 只用 Windows 里的工具 | 用户目录 | — | `C:\Users\你\skill-manager` |

```bash
# WSL + Windows 共用（推荐）：放在两边都看得见的 D 盘
git clone https://github.com/fengxbin/skill-manager.git /mnt/d/skill-manager
```

**第 2 步：在工具目录里放一个"快捷方式"，指向刚才下载的位置**

WSL 里的工具用软链接（`-s`）：

```bash
mkdir -p ~/.pi/agent/skills && ln -s /mnt/d/skill-manager ~/.pi/agent/skills/skill-manager   # Pi
mkdir -p ~/.kimi/skills     && ln -s /mnt/d/skill-manager ~/.kimi/skills/skill-manager        # Kimi
```

Windows 里的工具用目录联接（在 PowerShell 里敲，不需要管理员）：

```powershell
cmd /c mklink /J "%USERPROFILE%\.codex\skills\skill-manager" "D:\skill-manager"
cmd /c mklink /J "%USERPROFILE%\.claude\skills\skill-manager" "D:\skill-manager"
```

> 如果第 1 步下载到了 `~/skill-manager`（WSL 内部），把上面的 `/mnt/d/skill-manager` 换成它，
> 并且**不要**在 Windows 侧建链接——Windows 读不到 WSL 内部的文件。

**第 3 步：确认装上了**

```bash
ls ~/.pi/agent/skills/skill-manager/SKILL.md          # WSL 侧：能列出文件就成功
```
```powershell
dir "%USERPROFILE%\.codex\skills\skill-manager\SKILL.md"   # Windows 侧
```

然后**新开**一个 Agent 会话，输入 `/skill:skill-manager`（Pi）或直接说话，见下一节。

## 二、装好之后怎么用：跟 Agent 说话就行

不用背命令，把需求说出来，Agent 会自己按技能里的说明操作：

| 你想干什么 | 就这么说 |
|---|---|
| 先看看情况（推荐第一步） | "帮我盘点一下本机所有技能，看看有没有重复和内容冲突" |
| 把散在各工具里的技能收拢到一处 | "帮我初始化技能仓库" |
| 装一个新技能 | "把这个技能装进来：https://github.com/某人/某仓库" |
| 某个工具里技能加载不出来 | "我的技能在 Codex 里不显示，帮我查一下" |
| 同步到自己的 GitHub | "同步一下技能仓库" |
| 删掉某个技能 | "把 old-skill 移掉"（它会先问你再动） |

Pi 里也可以直接敲 `/skill:skill-manager <动词>`，例如 `/skill:skill-manager doctor`；
Claude Code / Cursor 在 `/` 菜单里能看到它；Codex 目前只有技能机制（旧的 `/prompts` 已取消）。

## 三、想自己敲命令（可选，Agent 不在手边时用）

```bash
python3 ~/skill-manager/scripts/skillkit.py targets    # 本机有哪些工具的技能目录
python3 ~/skill-manager/scripts/skillkit.py scan       # 只读盘点：副本、冲突
python3 ~/skill-manager/scripts/skillkit.py init       # 先看计划，不动手
python3 ~/skill-manager/scripts/skillkit.py init --apply   # 确认后执行
python3 ~/skill-manager/scripts/skillkit.py doctor     # 体检
```

嫌长可以装成命令，之后用 `skillkit <命令>`：

```bash
ln -sf ~/skill-manager/scripts/skillkit.py ~/.local/bin/skillkit   # ~/.local/bin 要在 PATH 里
skillkit targets
```

**所有会改东西的命令默认只打印计划，加 `--apply` 才真的执行。**

## 四、它不会动你的东西

- 只建快捷方式：**不改技能内容、不改目录名、不改任何工具里已有的调用方式**
- 删除 = 移到 `.skill-manager/trash/`，不是真删；真要清空会先列出全部路径再问你
- 只操作你当前用户；项目里的技能、被别人工具管着的技能，只看不动，只在报告里提一句

## 五、几个常见问题

**WSL 和 Windows 都要用？（两个东西都要放对）**
- ①本项目：放 `/mnt/d/skill-manager`（= `D:\skill-manager`），两边共用一份
- ②技能仓库：由 `init` 建在 `/mnt/d/skills-repo`（= `D:\skills-repo`），两边各跑一次 `skillkit restore --apply`

放在 WSL 内部（`~/`）时，Windows 侧一律看不到；WSL 侧的软链接也无法被 Windows 解析。

**技能名重复但内容不一样怎么办？**
保留**最后修改时间最新**的那份，其余自动备份到 `.skill-manager/backup/`，原位置改成快捷方式。

**要什么环境？**
Python 3.8+ 和 git。Windows、Linux、macOS、WSL 都行。

## 六、文件说明

`SKILL.md` 是给 Agent 看的操作说明；`scripts/skillkit.py` 是全部功能的实现；
`references/` 里是参考手册（工具目录表、迁移流程、排错、设计说明）；`assets/` 是给你自己技能仓库用的模板。
