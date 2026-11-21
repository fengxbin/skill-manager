---
name: skill-manager
description: One-repo (`skills-repo`), symlink-first manager for agent skills shared by many agents (Claude Code, Codex, Pi, Cursor, Gemini, Antigravity, Kimi, Qwen, CodeBuddy, ZCode, Trae, Copilot, Cline/Roo/Kilo, OpenCode, Windsurf, DSH, 70+ more) on Linux/macOS/Windows/WSL, with automatic GitHub sync on add/update/remove. Use when the user wants to install or adopt a skill, migrate scattered skills into one central Git repo (`skills-repo`), link/relink skills into agent directories, update/sync skills to GitHub, see where skills conflict, or diagnose broken links. Triggers - "安装这个 skill", "管理 skill", "迁移技能", "同步 skills", "skill 软链接", "skills-repo", "skills repo", "skill 冲突", "skill-manager".
---

# skill-manager

One central Git repo (**`skills-repo`**) is the **single source of truth**; every agent directory gets a
**link** (symlink on POSIX, NTFS junction on Windows) — never a copy. Edit the repo once,
every agent changes (**zero copy, zero drift**). Every `add` / `update` / `remove` automatically
commits and pushes to the configured GitHub remote (guarded by secret scanning; pass `--no-push`
to skip). 73 agent types are built in, serving Claude Code, Codex, Pi, DSH, Kimi, Qwen, CodeBuddy,
ZCode, Trae, Copilot, Antigravity, Cursor, Cline/Roo/Kilo, OpenCode, Windsurf and the rest.

Everything is done by `scripts/skillkit.py` (Python 3.8+, stdlib only).
If it has been installed on PATH as `skillkit`, the examples below can drop the
`python3 <skill>/scripts/` prefix (e.g. `skillkit doctor`); use the full path otherwise.

## When to use

- "mount skill-manager itself into all my Agents" → `install` (auto-detects every agent's default skill folder)
- "install / download this skill from GitHub" → `add` (clones, strips `.git`, links all agents, auto-pushes to GitHub)
- "update my installed skills" → `update` (re-fetches recorded git URLs, replaces safely, auto-pushes to GitHub)
- "my skills are scattered across N directories" → `scan`, then `init`
- "these two copies differ / which one wins?" → `scan` shows the conflict, `init` applies the rule
- "new machine / new WSL distro" → `restore` (or `init` if wild skills already exist)
- "skill stopped loading in Codex/Pi/Cursor/Antigravity" → `doctor`
- "sync my skills to/from GitHub" → `push` / `pull`

## Hard rules (do not break these)

1. **Never rename a skill and never edit its `SKILL.md`.** The repo directory and every link
   keep the skill's ORIGINAL directory name, so whatever command the agent already uses keeps
   working. Frontmatter `name` is read-only metadata (only reported when it differs); payload
   files are copied/moved byte for byte, never rewritten.
2. **Newest wins.** When the same skill name has different content in several agent dirs,
   the copy with the **newest modification time** becomes the repo truth; everything else is
   backed up and stepped aside. Never pick by hand without telling the user which one won.
3. **Scope = the current user only.** Never touch another user's home, `/root`, system dirs,
   or other profiles under `C:\Users\*`. In WSL, only `%USERPROFILE%` of the active Windows
   session is considered; running as `root` is refused unless `--allow-cross-user`.
4. **Project-level skills stay put.** `<project>/.claude/skills`, `<project>/.agents/skills`
   and friends are out of scope. Report them if you see them, do not migrate them.
5. **Skills already managed by another tool are skipped and reported.** External symlink/junction,
   `skills-lock.json`, `.skill-manager.json`, `install.json`, or an embedded `.git` → leave it,
   say so. Never adopt or overwrite (and never include them in conflict voting).
6. **Never copy a skill into an agent directory.** Payload lives in `skills-repo`; agents get links.
   `auto` mode never silently falls back to copy (`--mode copy` must be explicitly passed).
7. **Never delete.** `remove` moves payloads to `<repo>/.skill-manager/trash/<ts>/`.
   Deletion (batch or recursive) is forbidden by the user's global rule: if it is ever
   genuinely needed, print the exact paths, ask the user, wait for confirmation, then — only
   with `trash --purge <entry> --confirm-delete` — delete one path at a time. Never `rm -rf`,
   `del /s`, `Remove-Item -Recurse`, `shutil.rmtree`.
8. **Dry-run first.** Every mutating command (including `install` and `doctor --fix`) prints a
   plan and writes nothing without `--apply`. Show the plan, get a yes, then re-run with `--apply`.
9. **Secret gate before push.** Auto-push and `push` scan for secrets first and block if any are
   found. Report the exact file and reason to the user; never pass `--allow-secrets` without asking.
10. Prefer `--json` when you need to reason about the output (all commands emit valid JSON with `--json`).

## Slash entry points

Once this skill is linked into an agent, the agent client exposes it as a slash command by
itself — no extra wrapper files are needed:

| Client | How it appears | Notes |
|---|---|---|
| Pi | `/skill:skill-manager <verb>` | official: skills are exposed as `/skill:<name>`, text after it is appended as the user request |
| Claude Code | skill listed in the `/` menu (invocable, and model-invocable) | custom commands were merged into skills; `.claude/commands/` still works |
| Codex CLI | skills only | `/prompts` was removed in v0.117.0 in favour of skills |
| Gemini CLI / Antigravity | skills dir + `/skills` catalogue | `.gemini/commands/*.toml` exists for prompt templates |
| Cursor | skills dir + `/` menu | `.cursor/commands/*.md` exists; Cursor ships `/migrate-to-skills` |
| Others | model-invoked only | first-class support varies |

Map the first word after the command to an action, so `/skill:skill-manager doctor` behaves
deterministically instead of being reinterpreted:

| Invocation | Run first (read-only) | Needs user OK |
|---|---|---|
| `scan` / `盘点` | `scan --include-windows --json` | — |
| `targets` | `targets --json` | — |
| `list` / `status` | `list --json` / `status --json` | — |
| `doctor` / `检查` | `doctor --json` | `doctor --fix --apply` |
| `init` / `初始化` | `scan` → `init` (dry-run) | `init --apply` |
| `add <dir\|url>` / `装` | `add <src>` (dry-run) | `add --apply` |
| `update` / `更新` | `update` (dry-run) | `update --apply` |
| `sync` / `同步` | `push` / `pull` (dry-run) | `--apply` |
| `remove <name>` / `删` | `remove <name>` (dry-run) | `remove --apply` |
| no verb / free text | follow the procedure below | always |

## Command surface

```
skillkit.py install   [--to ...] [--mode auto|symlink|junction|copy] [--include-windows] [--apply]
                                               # link skill-manager itself into all detected agent dirs
skillkit.py init      [--apply] [--repo-url URL | --create-remote] [--include-windows]
                      [--prefer newest|majority] [--no-dedupe] [--copy] [--push | --no-push]
skillkit.py scan      [--env local|windows|all] [--include-windows] [--json]
skillkit.py repo      [--set PATH | --forget]  # which local skills-repo this machine uses
skillkit.py targets   [--json]                 # which agent dirs exist on this machine
skillkit.py list      [--json]                 # repo skills + live links across targets
skillkit.py status    [--json]                 # git state, auto_push, link counts
skillkit.py doctor    [--fix] [--apply] [--json]  # frontmatter, links, secrets, unmanaged dirs
skillkit.py add       <dir|git-url> [--name N] [--skill S | --all] [--category C]
                      [--force] [--no-link] [--no-push] [--allow-secrets] [--apply]
skillkit.py update    [name...] [--no-push] [--allow-secrets] [--apply]
skillkit.py link      [name...] [--to agents,claude,codex,pi,...] [--mode auto|symlink|junction|copy] [--apply]
skillkit.py unlink    <name...> | --all [--apply]
skillkit.py remove    <name...> [--no-push] [--allow-secrets] [--apply]  # unlink + trash + sync
skillkit.py trash     [--purge ENTRY|all] [--confirm-delete]             # double-gated delete
skillkit.py restore   [--apply]                # rebuild all links (new machine)
skillkit.py push      [-m MSG] [--allow-secrets] [--apply]
skillkit.py pull      [--apply]                # git pull --rebase + prune dangling links + relink
```

Global flags: `--repo PATH` (default `~/skills-repo`, fallback `~/skills_repo`, override with `SKILLKIT_REPO`),
`--json`, `--apply`, `-y`, `-v`, `--include-windows`, `--allow-cross-user`.
Testing hook: `SKILLKIT_HOME` overrides `$HOME` for target discovery.

## Procedures

### First-time setup (adopt everything this user has)

0. **Where does `skills-repo` go?** Run `skillkit.py repo` — it prints the recommended path *and why*
   (WSL+Windows → `/mnt/d/skills-repo`, a Windows-visible drive; single env → `~/skills-repo`).
   `init` asks once in an interactive terminal (Enter = recommended) and then remembers the answer
   in `~/.config/skillkit/location`, so later commands need no `--repo`. Non-interactive runs
   (`--json`, `-y`, CI) never block: they take the recommended path and print it.
   Do not invent a path yourself: if the user wants a different one, use `--repo` (or
   `repo --set`), and never pick something inside an agent's skills dir or a cloud-sync folder.
1. `python3 <skill>/scripts/skillkit.py targets` — confirm which agent dirs exist.
2. `... scan --include-windows` — read-only inventory. Note every `<< CONFLICT`, every
   `[skip: managed by another tool]`, and the environment notes.
3. `... init --repo ~/skills-repo` — dry run. Read out: repo path, imports, conflicts with
   both sides (path + date), duplicates to be backed up, target dirs.
4. Ask for confirmation. Then `... init --repo ~/skills-repo --apply` (with `--repo-url <url>` or `--create-remote`).
   - Writes `skill-manager.json` (with `auto_push: true`), creates universal hubs (`~/.agents/skills`, `~/.config/agents/skills`), links every detected target, commits, and pushes if a remote is configured.
   - No `gh` CLI → `init` prints the two `git remote add` / `git push` lines; relay them.
   - Dual WSL + Windows → repo on a Windows drive (`/mnt/d/skills-repo`) + `--include-windows`, then run `restore --apply` on the Windows side as well.
5. `... doctor` — report problems/warnings (secrets, unmanaged dirs, no remote).
6. Have the user paste `assets/agents-md-snippet.md` into their global `AGENTS.md`/`CLAUDE.md`.

### Install a new skill (the only correct download path)

```
skillkit.py add https://github.com/owner/repo              # dry run
skillkit.py add https://github.com/owner/repo --apply      # clone, strip .git, link, commit, auto-push
```
`add` clones to a temporary dir (cleaned up automatically), copies the payload (without `.git`) into
`skills/<name>/`, records the upstream URL in `skill-manager.json`, links every enabled target,
commits, and **automatically pushes to GitHub** if a remote is configured (pass `--no-push` to skip).
For multi-skill repos, pass `--skill <name>` or `--all`. Never let an agent's own installer write
into `~/.codex/skills` etc.

### Update skills from upstream

```
skillkit.py update [name...]             # dry run
skillkit.py update [name...] --apply     # re-fetch, stage & swap safely, relink, commit, auto-push
```

### New machine / new WSL distro

```
git clone <remote> ~/skills-repo
skillkit.py restore --repo ~/skills-repo          # dry run
skillkit.py restore --repo ~/skills-repo --apply  # rebuild all links & remember location
skillkit.py doctor
```
A skill that exists as a real directory makes `restore` refuse — that is intended; use
`init --apply`, which backs up and replaces.

### Refresh after another machine pushed

`skillkit.py pull --apply` (`git pull --rebase` + prunes dangling links of removed skills + relinks new skills), then `doctor`.

### Remove a skill

`skillkit.py remove <name> --apply` → unlinks across all targets, **moves** payload to
`.skill-manager/trash/<ts>/<name>`, commits, and auto-pushes to GitHub. Report the trash path.
Do not purge it as part of the task; purging is the user's decision (`trash --purge` is double-gated).

## Decision rules

| Situation | Action |
|---|---|
| Same name, different content | newest mtime wins (`--prefer majority` only if the user asks) — report every variant with path + date and which one won |
| Dir is external symlink/junction, or has `skills-lock.json` / `install.json` / `.git` | skip + report "managed by another tool"; never adopt or include in conflict voting |
| Frontmatter `name` != directory name | keep the directory name, report the mismatch (`doctor` warns); do not rename |
| Multi-skill GitHub repo | dry-run lists available skills; ask user whether to pick `--skill <name>` or `--all` |
| Project-level `.claude/skills` etc. | out of scope; mention it, do not migrate |
| Windows target while in WSL | repo must be on `/mnt/<drive>/…`; junction is created via `cmd.exe` |
| Symlink/junction creation fails | report error clearly; only use `--mode copy` if user explicitly accepts losing zero-drift |
| Secret scanner blocks push | report exact file & secret type; ask user to clean it; never pass `--allow-secrets` silently |
| User asks to delete something | print exact paths, wait for confirmation, then `trash --purge <entry> --confirm-delete`; no recursive delete ever |
| Repo location unclear | `repo` shows path + source (flag / env / recorded / default); ask only at `init` |

## Files

- `scripts/skillkit.py` — the CLI (all logic)
- `tests/test_skillkit.py` — stdlib `unittest` regression suite
- `references/targets.md` — the full 73-agent table, environment rules, how to add one
- `references/migration.md` — the Agent-executable migration contract
- `references/troubleshooting.md` — Windows/junction/WSL/drvfs、仓库位置、同名冲突、密钥排查
- `references/design.md` — why it works this way, data layout, known trade-offs
- `assets/repo-readme-template.md` — README dropped into a fresh `skills-repo`
- `assets/agents-md-snippet.md` — rules to paste into a global `AGENTS.md`
- `assets/config.example.json` — `skill-manager.json` example

## Verification

```
python3 scripts/skillkit.py targets          # agent dirs found (and notes)
python3 scripts/skillkit.py list             # every skill, every live link, BROKEN flags
python3 scripts/skillkit.py doctor --json    # problems, warnings, secrets, drift
```
Done when `doctor` reports `0 problem(s)` (warnings allowed) and `list` shows no `BROKEN`.
