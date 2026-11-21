# 常见问题与坑

## `gh` 是什么？没装行不行？

`gh` 是 **GitHub 官方的命令行客户端**（GitHub CLI，<https://cli.github.com>）：

- `gh auth login` → 登录（存 token）
- `gh repo create <you>/skills_repo --private --source=.` → 一条命令建私有仓库
- `gh repo view <you>/skills_repo` / `gh api user --jq .login` → 查仓库、查用户名

**没装完全可以**：本工具只在 `gh` 存在**且** `gh auth status` 通过时才用它。
否则 `init` 打印两行手动命令：

```bash
git -C <repo> remote add origin git@github.com:<you>/skills_repo.git
git -C <repo> push -u origin HEAD
```

也可以在网页上建好空仓库，然后 `init --repo-url <url> --apply` 直接接入并自动推送。

## "备份/回滚没有路径"指什么？

早期方案只说"迁移前备份，以防万一"，但没说明备份放在哪、怎么回滚 —— 真出问题时找不到东西。
现在路径是固定的：

```
<repo>/.skill-manager/
├── backup/<YYYYmmdd-HHMMSS>/<env>/<name>/   # init 迁移前，原目录的完整副本
├── trash/<YYYYmmdd-HHMMSS>/<name>/          # 被判为重复而移走的副本、remove 掉的技能
└── state-<platform>-<host>.json             # 当前环境的链接缓存（WSL 与 Windows 各自独立，丢了也可从文件系统推导）
```

`init` / `remove` 都会把这次的路径打印出来。回滚 = 把目录**移动**回原来的 Agent 目录
（先移除那里的链）。`backup/` 和 `trash/` 都在 `.gitignore` 里，不会被推到 GitHub。

## 同名 skill 内容不一致（最常见的真实问题）

规则：**保留最新版本**。`init` 的裁决：

1. 按内容哈希分组；
2. 取**最新修改时间**的那一组（`--prefer newest`，默认）；
   平票看副本数 → 再平票看文件数；
3. 其余副本：先复制到 `backup/`，再移入 `trash/`，原位置改成指向仓库的链。

dry-run 会把每个变体的**副本数、最新时间、示例路径**全列出来，胜出的那份前面有 `*`。
用户想换一份时：在 `--apply` 之前手工把想要的那份覆盖到目标目录即可。

`--prefer majority`（多数目录一致的版本胜出）只作为例外手段，不默认使用。

## 已被别的工具管理的技能

判定（满足任一即跳过并报告）：

- 目录本身是 symlink / junction（别的工具已经链过）
- 目录内有 `.skills-lock.json`、`skills-lock.json`、`.skill-manager.json`、`install.json`、`.source.json`
- 目录内嵌 `.git`（是 git clone 下来的上游仓库）

`scan` 显示 `[skip: managed by another tool]`，`init` 在"left alone"清单里列出路径和原因
（symlink 还会显示指向哪里）。**不会接管、不会覆盖**。真要纳管：`add <url>` 重新装进仓库。

## Windows

**软链失败 / 需要管理员**

`os.symlink` 在 Windows 需要管理员或开发者模式。本工具**对 Windows 可见路径优先用 NTFS junction**
（`mklink /J`），不需要任何特权，Agent 读取效果与软链一致。只有 `--mode symlink` 才强制真软链。

```bash
python3 scripts/skillkit.py link --mode junction --apply
python3 scripts/skillkit.py link --mode copy     --apply   # 最后手段，会告警"失去零漂移"
```

**删除 junction 会不会删到仓库内容？**

不会。`remove_link()` 对 junction 用 `os.rmdir` / `cmd /c rmdir`（非递归），只移除链接点本身。

**中文 Windows 下 `cmd.exe` 输出乱码**

脚本统一 `encoding="utf-8", errors="replace"` 解码，并且**以"链接是否可解析"为准**，
不看命令输出文本。

## WSL

**能不能从 WSL 管 Windows 侧的目录？**

读：可以。写链接：可以，但必须 junction，且仓库要在 Windows 可见盘：

```bash
python3 scripts/skillkit.py init --repo /mnt/d/skills_repo --include-windows --apply
```

**仓库在 `~/skills_repo`（ext4）会怎样？**

Linux 侧正常；Windows 侧看不到，`init` 会提示，Windows 目标不会被链接。

**WSL 用户名和 Windows 用户名不同怎么办？**

`--include-windows` 只通过 `cmd.exe /c echo %USERPROFILE%` 读取**当前活跃 Windows 会话**的用户目录，
绝不枚举 `C:\Users\*` 下其他用户。若 WSL 以 `root` 运行则会直接拒绝（需显式 `--allow-cross-user`）；
若普通 WSL 用户名与 Windows 目录名不同（例如微软账号目录名截断），会打印一条透明的 `note:` 提醒后正常处理。

**drvfs 上的软链有延迟**

`/mnt/*` 是 9p，创建后短暂不可见属正常。`make_link` 最多重试 1.5 秒。

**Windows 侧也要跑一次**

同一仓库、两套链接。Windows 侧装好 Python 后：

```powershell
python C:\path\to\skillkit.py restore --apply
python C:\path\to\skillkit.py doctor
```

## 项目级技能

`<project>/.claude/skills`、`<project>/.agents/skills` 等项目级目录**不在范围内**（多项目共用会互相
污染）。需要纳管就显式指定：

```bash
python3 scripts/skillkit.py add ./some-project/.claude/skills/foo --name foo --apply
```

## 目录里是"真目录"而不是链

`link_all()` **不会**覆盖真目录（那是用户数据）。两条出路：

```bash
python3 scripts/skillkit.py init --apply   # 备份 + 移走 + 建链
python3 scripts/skillkit.py doctor         # 先看清楚是哪些
```

若 `doctor` 报 `left alone ... [managed by another tool]`，说明它属于上面"已被别的工具管理"，
按那条处理。

## 删除与"禁止批量删除"规则

工具内部**没有任何递归删除**：

- `init`：复制到 `backup/` → 移动原目录
- `remove`：解除链 → 移动到 `trash/`
- `trash`：默认只列清单

真要删（清理垃圾箱）：

```bash
python3 scripts/skillkit.py trash                          # 列清单
python3 scripts/skillkit.py trash --purge old-skill        # 打印每个路径后拒绝
python3 scripts/skillkit.py trash --purge old-skill --confirm-delete   # 额外手输 DELETE
```

实现是逐个路径 `os.unlink` + 自底向上 `os.rmdir`，不使用 `shutil.rmtree`。

## 密钥泄露

技能目录里可能混着 token（`.env`、`auth.json`、`.credentials.yaml`、`id_rsa`、`sk-...`）。
`doctor` 会扫 7 类模式 + 敏感文件名并给出 warning；**自动同步与 `push` 之前也会强制执行密钥检查，命中即拦截推送**（确认是误报时才显式传 `--allow-secrets`）。
远端默认是**私有仓库**（`--create-remote` 强制 `--private`）。

## 仓库里出现嵌套 `.git`

第三方 skill 用 `git clone` 拿到会带 `.git`。正确做法是走 `add <url> --apply`：脚本 clone 到系统临时目录后
**剥离 `.git` 只复制 payload**，同时把上游 URL 记到 `skill-manager.json.sources` 并自动推送到 GitHub，以后 `update --apply` 一键刷新。

## 权限 / 磁盘

- 不要放 OneDrive 同步目录（同步冲突 + junction 失效）。
- 不要放网络盘（junction 可用但慢且易掉线）。
- `doctor` 报 `repo has no git remote` = 没有异地备份，提醒用户加 remote。

## 忘了仓库 / 不想每次都带 `--repo`

```bash
python3 scripts/skillkit.py repo                 # 当前路径 + 来源（flag / 环境变量 / 记录 / 默认）+ 推荐值
python3 scripts/skillkit.py repo --set /mnt/d/skills_repo
python3 scripts/skillkit.py repo --forget
```

`init --apply` / `restore --apply` 成功后会写入 `~/.config/skillkit/location`；之后 `list / doctor / push / pull` 都不用带路径。

## 排查顺序（照这个顺序走）

```bash
python3 scripts/skillkit.py repo                 # 0. 用的哪个仓库、从哪来的
python3 scripts/skillkit.py targets              # 1. 认得哪些目录，有没有提示
python3 scripts/skillkit.py status               # 2. 是不是 git、有没有 remote、auto_push 状态、链几条
python3 scripts/skillkit.py list                 # 3. 每个 skill 链到了哪些 Agent
python3 scripts/skillkit.py doctor               # 4. 缺链/断链/冲突/密钥/别家管理
python3 scripts/skillkit.py doctor --fix --apply # 5. 只修链接和清死链，不动 payload
```
