#!/usr/bin/env python3
"""skillkit — one-repo, symlink-first skill manager for multi-agent setups.

Design contract (see ../references/design.md):
  * One central Git repo (`skills-repo`) is the SINGLE SOURCE OF TRUTH. Real
    skill files live only there.
  * Every agent's skill directory receives a *link* (POSIX symlink / Windows
    NTFS junction), never a copy, so editing the repo changes every agent at
    once (zero copy, zero drift).
  * Changes (add / update / remove / init) automatically sync to the GitHub
    remote when configured (guarded by secret scanning; pass --no-push to skip).
  * Every mutating command is dry-run by default and only writes with --apply.
  * Nothing is ever deleted recursively. Removals are moves into
    <repo>/.skill-manager/trash/.

Python 3.8+, standard library only. Works on Linux, macOS, Windows and WSL.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

VERSION = "1.1.0"
DEFAULT_REPO = "~/skills-repo"
ALT_DEFAULT_REPO = "~/skills_repo"
CONFIG_NAME = "skill-manager.json"
STATE_DIR = ".skill-manager"
SKILL_FILE = "SKILL.md"
SELF_SKILL_ROOT = Path(__file__).resolve().parent.parent
SELF_UPSTREAM_URL = "https://github.com/fengxbin/skill-manager.git"

# ---------------------------------------------------------------------------
# Agent target table (the single place to add a new agent).
#
#   relpaths : candidate directories relative to HOME. Every EXISTING candidate
#              is linked (some tools ship two spellings, and one tool may be
#              installed in both). The first entry is used when creating.
#   bind     : "always" -> created if missing (the cross-tool hub dirs)
#              "auto"   -> linked only when the directory already exists
#   family   : display grouping (通用 / 海外 / 国内)
#   src      : "doc" = documented by the vendor, "probable" = community/indirect
#
# Sources: agentskills.io spec + vercel-labs/skills docs/agents.md (75+ agents),
# Google Antigravity docs, Kimi Code CLI docs, Qwen Code docs, CodeBuddy docs,
# Z.ai ZCode docs, and vendor docs for the rest. Add one tuple to support more.
# ---------------------------------------------------------------------------
_TARGET_SPEC = [
    # --- cross-tool hubs -------------------------------------------------
    ("agents", "通用 ~/.agents（Cline/Codex/Cursor/Kimi/Pi/Warp/Zed/Antigravity…）",
     [".agents/skills"], "always", "通用", "doc"),
    ("config-agents", "通用 ~/.config/agents（Amp/Replit/Universal/Kimi 推荐）",
     [".config/agents/skills"], "always", "通用", "doc"),
    # --- global CLI / IDE agents ----------------------------------------
    ("claude", "Claude Code（含 GLM Coding Plan 走 Claude 的场景）", [".claude/skills"], "auto", "海外", "doc"),
    ("codex", "OpenAI Codex CLI", [".codex/skills"], "auto", "海外", "doc"),
    ("gemini", "Google Gemini CLI", [".gemini/skills"], "auto", "海外", "doc"),
    ("antigravity", "Google Antigravity / Antigravity CLI",
     [".gemini/config/skills", ".gemini/antigravity/skills", ".antigravity/skills"], "auto", "海外", "doc"),
    ("copilot", "GitHub Copilot CLI", [".copilot/skills"], "auto", "海外", "doc"),
    ("cursor", "Cursor", [".cursor/skills"], "auto", "海外", "doc"),
    ("windsurf", "Windsurf (Codeium)", [".codeium/windsurf/skills", ".windsurf/skills"], "auto", "海外", "doc"),
    ("opencode", "opencode", [".config/opencode/skills", ".config/opencode/skill"], "auto", "海外", "doc"),
    ("amp", "Amp (Sourcegraph)", [".config/amp/skills"], "auto", "海外", "doc"),
    ("crush", "Crush (Charm)", [".config/crush/skills"], "auto", "海外", "doc"),
    ("goose", "Goose (Block)", [".config/goose/skills"], "auto", "海外", "doc"),
    ("devin", "Devin for Terminal", [".config/devin/skills"], "auto", "海外", "doc"),
    ("droid", "Factory Droid", [".factory/skills"], "auto", "海外", "doc"),
    ("augment", "Augment Code", [".augment/skills"], "auto", "海外", "doc"),
    ("continue", "Continue", [".continue/skills"], "auto", "海外", "doc"),
    ("cline", "Cline", [".cline/skills"], "auto", "海外", "doc"),
    ("roo", "Roo Code", [".roo/skills"], "auto", "海外", "doc"),
    ("kilo", "Kilo Code", [".kilo/skills"], "auto", "海外", "doc"),
    ("kiro", "Kiro CLI (AWS)", [".kiro/skills"], "auto", "海外", "doc"),
    ("junie", "Junie (JetBrains)", [".junie/skills"], "auto", "海外", "doc"),
    ("openhands", "OpenHands", [".openhands/skills"], "auto", "海外", "doc"),
    ("openclaw", "OpenClaw", [".openclaw/skills"], "auto", "海外", "doc"),
    ("aider-desk", "AiderDesk", [".aider-desk/skills"], "auto", "海外", "doc"),
    ("tabnine", "Tabnine CLI", [".tabnine/agent/skills"], "auto", "海外", "doc"),
    ("zencoder", "Zencoder / Zenflow", [".zencoder/skills"], "auto", "海外", "doc"),
    ("rovodev", "Rovo Dev (Atlassian)", [".rovodev/skills"], "auto", "海外", "doc"),
    ("cortex", "Cortex Code (Snowflake)", [".snowflake/cortex/skills"], "auto", "海外", "doc"),
    ("grok", "Grok Build", [".grok/skills"], "auto", "海外", "doc"),
    ("vibe", "Mistral Vibe", [".vibe/skills"], "auto", "海外", "doc"),
    ("posit", "Posit Assistant", [".posit/assistant/skills"], "auto", "海外", "doc"),
    ("bob", "IBM Bob", [".bob/skills"], "auto", "海外", "doc"),
    ("firebender", "Firebender", [".firebender/skills"], "auto", "海外", "doc"),
    ("forgecode", "ForgeCode", [".forge/skills"], "auto", "海外", "doc"),
    ("commandcode", "Command Code", [".commandcode/skills"], "auto", "海外", "doc"),
    ("codemaker", "Codemaker", [".codemaker/skills"], "auto", "海外", "doc"),
    ("codestudio", "Code Studio", [".codestudio/skills"], "auto", "海外", "doc"),
    ("deepagents", "Deep Agents", [".deepagents/agent/skills"], "auto", "海外", "doc"),
    ("hermes", "Hermes Agent", [".hermes/skills"], "auto", "海外", "doc"),
    ("mcpjam", "MCPJam", [".mcpjam/skills"], "auto", "海外", "doc"),
    ("jazz", "Jazz", [".jazz/skills"], "auto", "海外", "doc"),
    ("kimchi", "Kimchi", [".config/kimchi/harness/skills"], "auto", "海外", "doc"),
    ("kode", "Kode (shareAI)", [".kode/skills"], "auto", "海外", "doc"),
    ("moxby", "Moxby", [".moxby/skills"], "auto", "海外", "doc"),
    ("mux", "Mux", [".mux/skills"], "auto", "海外", "doc"),
    ("ona", "Ona", [".ona/skills"], "auto", "海外", "doc"),
    ("reasonix", "Reasonix", [".reasonix/skills"], "auto", "海外", "doc"),
    ("terramind", "Terramind", [".terramind/skills"], "auto", "海外", "doc"),
    ("tinycloud", "Tinycloud", [".tinycloud/skills"], "auto", "海外", "doc"),
    ("neovate", "Neovate", [".neovate/skills"], "auto", "海外", "doc"),
    ("pochi", "Pochi", [".pochi/skills"], "auto", "海外", "doc"),
    ("adal", "AdaL", [".adal/skills"], "auto", "海外", "doc"),
    ("autohand", "Autohand Code CLI", [".autohand/skills"], "auto", "海外", "doc"),
    ("inferencesh", "inference.sh", [".inferencesh/skills"], "auto", "海外", "doc"),
    ("zed", "Zed", [".zed/skills"], "auto", "海外", "probable"),
    ("warp", "Warp", [".warp/skills"], "auto", "海外", "probable"),
    ("astrbot", "AstrBot", [".astrbot/data/skills"], "auto", "海外", "doc"),
    # --- 国内 ------------------------------------------------------------
    ("pi", "Pi agent", [".pi/agent/skills", ".pi/skills"], "auto", "通用", "doc"),
    ("dsh", "DeepSeek Harness", [".dsh/skills"], "auto", "国内", "doc"),
    ("kimi", "Kimi Code CLI（月之暗面）", [".kimi/skills", ".kimi-code/skills"], "auto", "国内", "doc"),
    ("qwen", "Qwen Code（阿里）", [".qwen/skills"], "auto", "国内", "doc"),
    ("lingma", "通义灵码 Lingma（阿里）", [".lingma/skills"], "auto", "国内", "doc"),
    ("iflow", "iFlow CLI 心流（阿里/心流）", [".iflow/skills"], "auto", "国内", "doc"),
    ("qoder", "Qoder（阿里国际）", [".qoder/skills"], "auto", "国内", "doc"),
    ("qoder-cn", "Qoder CN（阿里）", [".qoder-cn/skills"], "auto", "国内", "doc"),
    ("codebuddy", "CodeBuddy / WorkBuddy（腾讯）", [".codebuddy/skills", ".workbuddy/skills"], "auto", "国内", "doc"),
    ("codearts", "CodeArts Agent（华为云）", [".codeartsdoer/skills"], "auto", "国内", "doc"),
    ("zcode", "ZCode / 智谱 GLM Coding", [".zcode/skills"], "auto", "国内", "doc"),
    ("minimax", "MiniMax Code", [".minimax/skills"], "auto", "国内", "doc"),
    ("trae", "Trae（字节）", [".trae/skills"], "auto", "国内", "doc"),
    ("trae-cn", "Trae CN（字节国内版）", [".trae-cn/skills"], "auto", "国内", "doc"),
    ("doubao", "豆包 / Doubao Work（字节，客户端上传技能包，本地目录未公开）",
     [".doubao/skills", ".doubao-work/skills"], "auto", "国内", "probable"),
]
TARGETS = [
    {"id": tid, "label": label, "relpaths": relpaths, "relpath": relpaths[0],
     "bind": bind, "family": family, "src": src}
    for tid, label, relpaths, bind, family, src in _TARGET_SPEC
]
TARGET_BY_ID = {t["id"]: t for t in TARGETS}

IGNORE_DIR_NAMES = {".git", ".skill-manager", "node_modules", ".venv", "__pycache__", ".ds_store", ".idea"}
IGNORE_FILE_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}

# Dynamic target discovery exclusions: never scan dev caches, IDE extensions,
# or built-in/system read-only skill folders (e.g. .codex/skills/.system,
# .cursor/skills-cursor, .gemini/antigravity/builtin/skills).
DISCOVER_SKIP_TOP_DIRS = {
    ".git", ".cache", ".npm", ".cargo", ".rustup", ".m2", ".gradle", ".nuget",
    ".vscode", ".vscode-insiders", ".vscode-server", ".docker", ".ssh", ".gnupg",
    ".local", ".venv", ".pyenv", ".nvm", ".rbenv", ".asdf", ".conda", ".ipython",
    ".jupyter", ".trash", ".kube", ".aws", ".azure", ".gcloud", ".terraform.d",
    ".mozilla", ".pki", ".dbus", ".cups", ".oh-my-zsh", ".zsh", ".bash", ".vim",
    ".emacs.d", ".android", ".bun", ".deno", ".pnpm-store", ".yarn", ".pip",
    ".skill-manager",
}
DISCOVER_SKIP_SUBDIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "cache", "caches",
    "logs", "log", "tmp", "temp", "brain", "builtin", "builtins", ".system",
    ".system_generated", "skills-cursor", "blobs", "extensions", "ext",
    "plugins", "plugin", "marketplaces", "marketplace", "connectors",
    "connectors-marketplace", "vendor", "vendor_imports", "security-resources",
    "bin", "lib", "site-packages", "dist", "build", "target", "backups",
    "backup", "trash", ".skill-manager", "sessions", "history", "telemetry",
    "crashpad", "gpucache", "code cache", "cacheddata", "user data", "storage",
    "checkpoints", "conversations", "projects", "worktrees", "npm", "packages",
}

SECRET_PATTERNS = [
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "GitHub PAT"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "GitHub fine-grained PAT"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "OpenAI-style key"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
    (re.compile(r"(?i)\b(xox[baprs]-[A-Za-z0-9-]{10,})"), "Slack token"),
    (re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+=]{16,}"), "inline credential"),
]
SECRET_FILE_HINTS = (".env", ".credentials", "auth.json", "id_rsa", "id_ed25519", ".pem", ".pfx", ".npmrc", ".pypirc")

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def log(msg=""):
    print(msg, flush=True)


def die(msg, code=2):
    print("error: " + msg, file=sys.stderr, flush=True)
    sys.exit(code)


def sh(cmd, cwd=None):
    """Run a command, return (rc, out, err). Never raises on non-zero."""
    return sh_in(cmd, cwd=cwd)


def sh_in(cmd, cwd=None):
    try:
        r = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", "command not found: %s" % cmd[0]
    except Exception as exc:  # pragma: no cover - defensive
        return 1, "", str(exc)


def is_wsl():
    if os.name == "nt":
        return False
    try:
        with open("/proc/version", "r", encoding="utf-8", errors="ignore") as fh:
            return "microsoft" in fh.read().lower()
    except OSError:
        return False


def to_win_path(p):
    """Convert a WSL path to a Windows path (only for Windows-visible mounts)."""
    s = str(p)
    if re.match(r"^[A-Za-z]:[\\/]", s):
        return s.replace("/", "\\")
    m = re.match(r"^/mnt/([a-zA-Z])(/.*)?$", s)
    if m:
        rest = (m.group(2) or "/").replace("/", "\\")
        return "%s:%s" % (m.group(1).upper(), rest if rest else "\\")
    return ""


def windows_visible(p):
    """True when a WSL path is reachable from Windows (i.e. under /mnt/<drive>)."""
    return bool(re.match(r"^/mnt/[a-zA-Z]/", str(p)))


def _strip_win_prefix(s):
    if s.startswith("\\\\?\\UNC\\") or s.startswith("\\??\\UNC\\"):
        return "\\\\" + s[8:]
    if s.startswith("\\\\?\\") or s.startswith("\\??\\"):
        return s[4:]
    return s


def _norm_path(p):
    s = _strip_win_prefix(str(p))
    return os.path.normcase(os.path.normpath(s))


def same_path(a, b):
    try:
        return _norm_path(os.path.realpath(str(a))) == _norm_path(os.path.realpath(str(b)))
    except OSError:
        return _norm_path(a) == _norm_path(b)


def path_within(child, parent):
    c = _norm_path(child)
    p = _norm_path(parent)
    return c == p or c.startswith(p.rstrip(os.sep) + os.sep)


def is_junction(p):
    p = Path(p)
    if p.is_symlink():
        return False
    if os.name == "nt":
        try:
            import ctypes
            FILE_ATTRIBUTE_REPARSE_POINT = 0x400
            FILE_ATTRIBUTE_DIRECTORY = 0x10
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(p))
            return bool(attrs != -1 and (attrs & FILE_ATTRIBUTE_REPARSE_POINT) and (attrs & FILE_ATTRIBUTE_DIRECTORY))
        except Exception:
            return False
    # Under WSL a junction is surfaced as a symlink, so os.path.islink already
    # answers the question; nothing else to probe here.
    return False


def is_skill_link(p):
    p = Path(p)
    return p.is_symlink() or is_junction(p)


def resolve_link_target(p):
    """Resolve the target of a symlink or junction (works even when dangling)."""
    p = Path(p)
    if not is_skill_link(p):
        return None
    try:
        raw = os.readlink(str(p))
        raw = _strip_win_prefix(raw)
        tp = Path(raw)
        if not tp.is_absolute():
            tp = p.parent / tp
        return Path(os.path.normpath(str(tp)))
    except OSError:
        pass
    try:
        return Path(os.path.normpath(_strip_win_prefix(os.path.realpath(str(p)))))
    except OSError:
        return None


def link_points_to(link, target):
    """True when `link` is a live link resolving to `target` (symlink or junction)."""
    link, target = Path(link), Path(target)
    if not is_skill_link(link) or not target.exists():
        return False
    try:
        resolved = resolve_link_target(link)
        if resolved and same_path(resolved, target):
            return True
        if link.exists():
            return os.path.samefile(str(link), str(target))
    except OSError:
        return False
    return False


def make_link(target, link, mode="auto", env="local"):
    """Create a link. Returns the created kind ('symlink'|'junction'|'copy') or raises.

    In 'auto' mode, never silently falls back to copy (zero-drift invariant).
    Pass --mode copy explicitly if you really want a copy.
    """
    target, link = Path(target), Path(link)
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or is_skill_link(link):
        raise RuntimeError("path already exists: %s" % link)

    if mode == "copy":
        copy_tree(target, link, keep_git=False)
        return "copy"

    errors = []
    is_win_target = bool(os.name == "nt" or (is_wsl() and windows_visible(link)))

    # Windows-visible targets use NTFS junctions: no admin rights, dev mode or
    # WSL metadata support required, and Windows agents resolve them natively.
    if is_win_target and mode in ("auto", "junction"):
        win_link, win_target = to_win_path(link), to_win_path(target)
        if not win_target:
            raise RuntimeError(
                "cannot link a Windows path to a non-Windows path (%s). "
                "Keep the repo on a Windows-visible drive (e.g. D:\\skills-repo), "
                "or run skillkit natively on Windows." % target
            )
        cwd = "/mnt/c" if (is_wsl() and Path("/mnt/c").is_dir()) else None
        rc, out, err = sh_in(["cmd.exe", "/c", "mklink", "/J", win_link, win_target], cwd=cwd)
        if rc != 0 and is_skill_link(link) and link_points_to(link, target):
            rc = 0  # cmd reported failure but the junction is live (encoding/UNC noise)
        if rc == 0:
            # drvfs/9p visibility can lag by a moment; rc==0 means it was created
            for _ in range(15):
                if link.exists() or is_skill_link(link):
                    break
                time.sleep(0.1)
            return "junction"
        errors.append("junction: %s" % (err or out))

    if mode in ("auto", "symlink"):
        try:
            os.symlink(str(target), str(link), target_is_directory=True)
            return "symlink"
        except (OSError, NotImplementedError) as exc:
            errors.append("symlink: %s" % exc)
            if mode == "symlink":
                raise RuntimeError(errors[-1])

    raise RuntimeError(
        "link creation failed (%s). Pass --mode copy only if you explicitly accept losing zero-drift."
        % ("; ".join(errors) or "unknown error")
    )


def remove_link(link, kind=None):
    """Remove a link (never the payload). Returns True on success."""
    link = Path(link)
    if link.is_symlink():
        os.unlink(str(link))
        return True
    if not link.exists() and not is_junction(link):
        return True
    if os.name == "nt":
        if not is_junction(link):
            return False  # refuse to touch a real directory
        try:
            os.rmdir(str(link))  # removes a junction, leaves its target intact
            return True
        except OSError:
            rc, _, _ = sh(["cmd.exe", "/c", "rmdir", str(link)])
            return rc == 0
    if is_wsl() and windows_visible(link):
        rc, _, _ = sh(["cmd.exe", "/c", "rmdir", to_win_path(link)])
        if rc == 0:
            return True
    return False


def _unlink_file(path):
    """Remove a single file or symlink, clearing Windows read-only bit if needed."""
    s = str(path)
    try:
        os.unlink(s)
    except PermissionError:
        try:
            os.chmod(s, stat.S_IWRITE)
            os.unlink(s)
        except OSError:
            raise


def _safe_walk(root):
    """os.walk wrapper that NEVER descends into symlinks OR Windows NTFS junctions."""
    for cur, dirs, files in os.walk(str(root), topdown=True, followlinks=False):
        safe_dirs = []
        link_dirs = []
        for d in dirs:
            dp = Path(cur) / d
            if is_skill_link(dp):
                link_dirs.append(d)
            else:
                safe_dirs.append(d)
        dirs[:] = safe_dirs
        yield cur, dirs, files, link_dirs


def _cleanup_temp_dir(tmp):
    """Remove a tool-created temp clone directory (strictly inside system tempdir, junction-safe)."""
    if not tmp:
        return
    tmp = Path(tmp)
    if not tmp.exists() and not is_skill_link(tmp):
        return
    sys_tmp = Path(tempfile.gettempdir()).resolve()
    try:
        resolved = tmp.resolve()
    except OSError:
        return
    if not path_within(resolved, sys_tmp) or not resolved.name.startswith("skillkit-"):
        return
    if is_skill_link(tmp):
        remove_link(tmp)
        return
    dirs_to_remove = []
    for cur, safe_dirs, files, link_dirs in _safe_walk(resolved):
        for name in files:
            try:
                _unlink_file(os.path.join(cur, name))
            except OSError:
                pass
        for ld in link_dirs:
            try:
                remove_link(os.path.join(cur, ld))
            except OSError:
                pass
        dirs_to_remove.append(cur)
    for d in reversed(dirs_to_remove):
        try:
            os.rmdir(d)
        except OSError:
            pass


def read_frontmatter(path):
    meta = {}
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return meta, ""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if not m:
        return meta, text
    for line in m.group(1).splitlines():
        if not line or line[0] in " \t#-":
            continue
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("\"'")
    return meta, text


def dir_hash(path):
    """Stable content hash of a skill directory (used for conflict detection)."""
    h = hashlib.sha256()
    path = Path(path)
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if d.lower() not in IGNORE_DIR_NAMES)
        for name in sorted(files):
            if name in IGNORE_FILE_NAMES:
                continue
            fp = Path(root) / name
            rel = str(fp.relative_to(path)).replace(os.sep, "/")
            h.update(rel.encode("utf-8", "replace"))
            try:
                h.update(fp.read_bytes())
            except OSError:
                h.update(b"<unreadable>")
    return h.hexdigest()


def newest_mtime(path):
    newest = 0.0
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d.lower() not in IGNORE_DIR_NAMES]
        for name in files:
            if name in IGNORE_FILE_NAMES:
                continue
            try:
                newest = max(newest, (Path(root) / name).stat().st_mtime)
            except OSError:
                pass
    return newest


def human_time(ts):
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    except (ValueError, OSError):
        return "?"


def copy_tree(src, dst, keep_git=False):
    """Copy a skill directory, excluding build/cache noise (and .git by default)."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    ignored_dirs = IGNORE_DIR_NAMES if not keep_git else (IGNORE_DIR_NAMES - {".git"})

    def _ignore(cur, names):
        out = []
        for n in names:
            if n in IGNORE_FILE_NAMES or n.lower() in ignored_dirs:
                out.append(n)
        return out

    shutil.copytree(str(src), str(dst), ignore=_ignore)
    return dst


def _unique_path(parent, label):
    """Avoid backup/trash collisions when a tool has multiple candidate dirs."""
    parent = Path(parent)
    cand = parent / label
    if not cand.exists() and not is_skill_link(cand):
        return cand
    i = 2
    while True:
        cand = parent / ("%s_%d" % (label, i))
        if not cand.exists() and not is_skill_link(cand):
            return cand
        i += 1


def _safe_is_dir(p):
    """Path.is_dir() that returns False instead of crashing on PermissionError."""
    try:
        return Path(p).is_dir()
    except OSError:
        return False


def _slug_from_relpath(relpath, taken_ids):
    """Derive a stable, readable target ID from a discovered relative path."""
    parts = [p for p in Path(relpath).parts if p]
    cleaned = []
    for p in parts:
        pl = p.lower()
        if pl in (".config", "appdata", "roaming", "library", "application support", "skills", "skill"):
            continue
        s = re.sub(r"[^a-z0-9-]+", "-", pl.lstrip(".")).strip("-")
        if s:
            cleaned.append(s)
    base = "-".join(cleaned) or "discovered"
    cand = base
    i = 2
    while cand in taken_ids:
        cand = "%s-%d" % (base, i)
        i += 1
    taken_ids.add(cand)
    return cand


def is_skill_dir(p):
    try:
        return (Path(p) / SKILL_FILE).is_file()
    except OSError:
        return False


def _repo_name_from_url(url):
    cleaned = url.strip().rstrip("/")
    cleaned = re.sub(r"[?#].*$", "", cleaned)
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    part = re.split(r"[/:]", cleaned)[-1]
    return part or "skill"


def _discover_skills_in_tree(root):
    """Find every skill directory inside a cloned git repository."""
    root = Path(root)
    if is_skill_dir(root):
        return [root]
    found = []
    for cur, dirs, files in os.walk(str(root)):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d.lower() not in IGNORE_DIR_NAMES)
        curp = Path(cur)
        if SKILL_FILE in files:
            found.append(curp)
            dirs[:] = []  # do not descend into a skill
    return found


def scan_secrets(repo):
    """Scan all repo skills for likely secrets / credential files."""
    findings = []
    for sk in repo_skills(repo):
        for cur, dirs, files in os.walk(str(sk["path"])):
            dirs[:] = [d for d in dirs if d.lower() not in IGNORE_DIR_NAMES]
            for name in files:
                fp = Path(cur) / name
                rel = str(fp.relative_to(repo)).replace(os.sep, "/")
                if any(h in name.lower() for h in SECRET_FILE_HINTS):
                    findings.append({"file": str(fp), "rel": rel, "reason": "possible secret file"})
                    continue
                try:
                    if fp.stat().st_size > 512 * 1024:
                        continue
                    text = fp.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for rx, label in SECRET_PATTERNS:
                    if rx.search(text):
                        findings.append({"file": str(fp), "rel": rel, "reason": label})
                        break
    return findings


# ---------------------------------------------------------------------------
# Context: repo, config, state, environment
# ---------------------------------------------------------------------------


class Context(object):
    def __init__(self, args):
        self.args = args
        self.json = bool(getattr(args, "json", False))
        self.yes = bool(getattr(args, "yes", False))
        self.apply = bool(getattr(args, "apply", False))
        self.verbose = bool(getattr(args, "verbose", False))
        self.home = Path(os.environ.get("SKILLKIT_HOME") or Path.home())
        self.wsl = is_wsl()
        self.environment_notes = []
        self._discovered_cache = {}
        self.repo_source = "none"
        self.repo = self._resolve_repo()
        self.config = self._load_config()
        self.state = self._load_state()

    def log(self, msg=""):
        if not self.json:
            log(msg)

    def platform_tag(self):
        if self.wsl:
            return "wsl"
        if os.name == "nt":
            return "windows"
        if sys.platform == "darwin":
            return "darwin"
        return "linux"

    def env_id(self):
        host = re.sub(r"[^A-Za-z0-9._-]", "_", socket.gethostname() or "local")
        return "%s-%s" % (self.platform_tag(), host)

    # -- repo -------------------------------------------------------------
    def location_file(self):
        """Pointer file that remembers where the repo lives on THIS machine.

        Follows the XDG habit (~/.config/skillkit/location) and works on Windows
        too, because Path.home() exists everywhere. Machine-specific by nature,
        so it is never committed to the repo.
        """
        return self.home / ".config" / "skillkit" / "location"

    def _looks_like_repo(self, cand):
        if not cand.is_dir():
            return False
        if (cand / CONFIG_NAME).is_file():
            return True
        if (cand / STATE_DIR).is_dir() and any((cand / STATE_DIR).glob("state*.json")):
            return True
        if (cand / "skills").is_dir() and (cand / ".git").exists():
            return True
        return False

    def _resolve_repo(self):
        self.repo_source = "none"
        explicit = getattr(self.args, "repo", None)
        if explicit:
            self.repo_source = "--repo"
            return Path(explicit).expanduser().resolve()
        env_repo = os.environ.get("SKILLKIT_REPO")
        if env_repo:
            self.repo_source = "SKILLKIT_REPO"
            return Path(env_repo).expanduser().resolve()

        loc = self.location_file()
        if loc.is_file():
            try:
                recorded = loc.read_text(encoding="utf-8").strip().splitlines()[0].strip()
            except (OSError, IndexError):
                recorded = ""
            if recorded:
                cand = Path(recorded).expanduser().resolve()
                if cand.is_dir() and (self._looks_like_repo(cand) or (cand / "skills").is_dir()):
                    self.repo_source = "recorded location (%s)" % loc
                    return cand

        candidates = [
            self.home / "skills-repo",
            Path(DEFAULT_REPO).expanduser(),
            self.home / "skills_repo",
            Path(ALT_DEFAULT_REPO).expanduser(),
            Path.cwd(),
        ]
        seen = set()
        for cand in candidates:
            cand = cand.resolve()
            key = _norm_path(cand)
            if key in seen:
                continue
            seen.add(key)
            if self._looks_like_repo(cand):
                self.repo_source = "auto-detected (%s)" % cand
                return cand
        return None

    def record_location(self, repo):
        """Persist the chosen repo path so later commands need no --repo."""
        loc = self.location_file()
        try:
            loc.parent.mkdir(parents=True, exist_ok=True)
            loc.write_text(str(Path(repo).resolve()) + "\n", encoding="utf-8")
            return True
        except OSError as exc:
            self.log("  ! could not record repo location (%s): %s" % (loc, exc))
            return False

    def require_repo(self):
        if not self.repo:
            die("no skills-repo found. Pass --repo PATH, set SKILLKIT_REPO, run 'skillkit init' "
                "(it remembers the location), or see 'skillkit repo --help'.")
        return self.repo

    # -- config / state ---------------------------------------------------
    def _load_config(self):
        cfg = {
            "version": 1,
            "targets": None,
            "link_mode": "auto",
            "category_layout": True,
            "conflict_policy": "newest",
            "auto_push": True,
            "discover_targets": True,
            "custom_targets": {},
            "sources": {},
        }
        if self.repo:
            p = self.repo / CONFIG_NAME
            if p.is_file():
                try:
                    cfg.update(json.loads(p.read_text(encoding="utf-8")))
                except ValueError:
                    die("invalid JSON in %s" % p)
        return cfg

    def save_config(self):
        self.require_repo()
        p = self.repo / CONFIG_NAME
        p.write_text(json.dumps(self.config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _state_path(self):
        if not self.repo:
            return None
        return self.repo / STATE_DIR / ("state-%s.json" % self.env_id())

    def _load_state(self):
        st = {"version": 1, "env_id": self.env_id(), "links": [], "backups": [], "environments": {}}
        p = self._state_path()
        legacy = (self.repo / STATE_DIR / "state.json") if self.repo else None
        src = p if (p and p.is_file()) else (legacy if (legacy and legacy.is_file()) else None)
        if src:
            try:
                loaded = json.loads(src.read_text(encoding="utf-8"))
                st.update(loaded)
                # Filter out foreign-OS paths when migrating from a shared legacy state.json
                if src == legacy:
                    is_nt = (os.name == "nt")
                    st["links"] = [
                        l for l in st.get("links", [])
                        if (bool(re.match(r"^[A-Za-z]:[\\/]", l.get("path", ""))) == is_nt)
                    ]
            except ValueError:
                pass
        return st

    def save_state(self):
        p = self._state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        self.state["env_id"] = self.env_id()
        p.write_text(json.dumps(self.state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.ensure_scaffolding()

    # -- environments -----------------------------------------------------
    def windows_home(self):
        """The CURRENT Windows user's profile as seen from WSL (via %USERPROFILE%)."""
        if not self.wsl or os.environ.get("SKILLKIT_HOME"):
            return None
        if not Path("/mnt/c/Users").is_dir():
            return None
        rc, out, _ = sh_in(["cmd.exe", "/c", "echo", "%USERPROFILE%"], cwd="/mnt/c")
        if rc == 0 and out and "USERPROFILE" not in out:
            win = out.strip()
            drive, rest = win[:2], win[2:].replace("\\", "/")
            guess = Path("/mnt/%s%s" % (drive[0].lower(), rest))
            if guess.is_dir():
                return guess
        return None

    def current_user(self):
        return os.environ.get("USER") or os.environ.get("USERNAME") or ""

    def windows_home_guard(self):
        """Return (profile, reason).

        Uses only %USERPROFILE% of the active Windows session (never enumerates
        other C:\\Users\\* directories). Refuses root unless --allow-cross-user;
        for non-root username differences (common with MS accounts), allows the
        active %USERPROFILE% and attaches a transparent note.
        """
        wh = self.windows_home()
        if not wh:
            return None, "no Windows profile detected"
        me, them = self.current_user(), wh.name
        if me.lower() == "root" and not getattr(self.args, "allow_cross_user", False):
            return None, (
                "running as root; touching Windows profile '%s' is refused "
                "(pass --allow-cross-user to override)" % them
            )
        if me and them and me.lower() != them.lower():
            return wh, (
                "using active Windows session profile '%s' (differs from Linux user '%s'; "
                "only %%USERPROFILE%% is touched)" % (them, me)
            )
        return wh, ""

    def env_homes(self, include_windows=False):
        homes = {"local": self.home}
        if include_windows:
            wh, reason = self.windows_home_guard()
            if wh:
                homes["windows"] = wh
            if reason and reason not in self.environment_notes:
                self.environment_notes.append(reason)
        return homes

    # -- target roots & active dynamic discovery --------------------------
    def custom_target_specs(self):
        """User/Agent-registered custom targets stored in skill-manager.json."""
        raw = self.config.get("custom_targets") or {}
        specs = []
        if not isinstance(raw, dict):
            return specs
        for tid, val in sorted(raw.items()):
            rels = val if isinstance(val, list) else [val]
            rels = [str(r).strip() for r in rels if str(r).strip()]
            if not rels:
                continue
            specs.append({
                "id": str(tid),
                "label": "Custom target (%s)" % tid,
                "relpaths": rels,
                "relpath": rels[0],
                "bind": "auto",
                "family": "自定义",
                "src": "custom",
            })
        return specs

    def candidate_roots(self, target, home):
        out = []
        for rel in target.get("relpaths") or [target["relpath"]]:
            p = Path(rel).expanduser()
            out.append(p if p.is_absolute() else (Path(home) / p))
        return out

    def _is_excluded_discovery_path(self, cand, home, known_roots):
        if not self._within(cand, home):
            return True
        if self.repo and path_within(cand, self.repo):
            return True
        if path_within(cand, SELF_SKILL_ROOT):
            return True
        if any(path_within(cand, kr) for kr in known_roots):
            return True
        return False

    def discover_extra_targets(self, env, home):
        """Actively discover skill directories not listed in the static table.

        Scans bounded user-level config roots (~/.*, ~/.config/*, and direct
        AppData/Roaming/<App>/skills or Library/Application Support/<App>/skills)
        while skipping system/built-in read-only folders, caches, and already-known
        targets. Results are cached per (env, home).
        """
        if bool(getattr(self.args, "no_discover", False)):
            return []
        if not self.config.get("discover_targets", True):
            return []
        home = Path(home)
        cache_key = (env, _norm_path(home))
        if cache_key in self._discovered_cache:
            return self._discovered_cache[cache_key]

        static_and_custom = TARGETS + self.custom_target_specs()
        known_roots = []
        taken_ids = {t["id"] for t in static_and_custom}
        for t in static_and_custom:
            for r in self.candidate_roots(t, home):
                known_roots.append(r)

        discovered_paths = {}  # norm_path -> Path

        def _record(cand):
            if self._is_excluded_discovery_path(cand, home, known_roots):
                return
            discovered_paths[_norm_path(cand)] = cand

        # 1) Bounded shallow walk under hidden dot-directories in HOME (includes ~/.config)
        try:
            top_entries = sorted(home.iterdir())
        except OSError:
            top_entries = []
        for top in top_entries:
            if not top.name.startswith(".") or top.name.lower() in DISCOVER_SKIP_TOP_DIRS:
                continue
            if is_skill_link(top) or not _safe_is_dir(top):
                continue
            for cur, dirs, files, _ in _safe_walk(top):
                curp = Path(cur)
                try:
                    rel_parts = curp.relative_to(home).parts
                except ValueError:
                    dirs[:] = []
                    continue
                if len(rel_parts) > 5 or self._is_excluded_discovery_path(curp, home, known_roots):
                    dirs[:] = []
                    continue
                # Prune noise, hidden subdirs (.system/.git), built-in/vendor/marketplace folders
                dirs[:] = [
                    d for d in dirs
                    if not d.startswith(".")
                    and d.lower() not in DISCOVER_SKIP_SUBDIRS
                    and "marketplace" not in d.lower()
                    and "vendor" not in d.lower()
                    and "builtin" not in d.lower()
                ]
                # Signal B: convention dir literally named `skills` under a dot/config root (depth 2..4)
                if curp.name.lower() == "skills" and 2 <= len(rel_parts) <= 4:
                    _record(curp)
                    dirs[:] = []
                    continue
                # Signal A: <parent>/<skill>/SKILL.md where parent looks like a skills container
                if SKILL_FILE in files and 3 <= len(rel_parts) <= 5:
                    parent = curp.parent
                    pl = parent.name.lower()
                    if (
                        parent != home
                        and parent != (home / ".config")
                        and not parent.name.startswith(".")
                        and pl not in DISCOVER_SKIP_SUBDIRS
                        and "skill" in pl
                    ):
                        _record(parent)
                    dirs[:] = []  # never descend inside a skill

        # 2) Fast O(N) depth-2 check for desktop agents in AppData/Roaming or Application Support
        desktop_roots = []
        if os.name == "nt" or env == "windows":
            desktop_roots.append(home / "AppData" / "Roaming")
        if sys.platform == "darwin" and env == "local":
            desktop_roots.append(home / "Library" / "Application Support")
        for droot in desktop_roots:
            if not _safe_is_dir(droot) or is_skill_link(droot):
                continue
            try:
                apps = sorted(droot.iterdir())
            except OSError:
                continue
            for app in apps:
                if app.name.startswith(".") or app.name.lower() in DISCOVER_SKIP_SUBDIRS:
                    continue
                if is_skill_link(app) or not _safe_is_dir(app):
                    continue
                for subname in ("skills", "skill"):
                    cand = app / subname
                    if is_skill_link(cand) or not _safe_is_dir(cand):
                        continue
                    if self._is_excluded_discovery_path(cand, home, known_roots):
                        continue
                    # Require at least one real <skill>/SKILL.md inside AppData/Application Support
                    try:
                        has_skill = any(
                            _safe_is_dir(child) and is_skill_dir(child)
                            for child in cand.iterdir()
                            if not child.name.startswith(".")
                        )
                    except OSError:
                        has_skill = False
                    if has_skill:
                        _record(cand)

        # Deduplicate ancestor/descendant overlaps (keep the shallower skills root)
        ordered = sorted(discovered_paths.values(), key=lambda p: len(p.parts))
        kept = []
        for p in ordered:
            if any(path_within(p, anc) for anc in kept):
                continue
            kept.append(p)

        specs = []
        for p in kept:
            try:
                rel = str(p.relative_to(home)).replace(os.sep, "/")
            except ValueError:
                rel = str(p)
            tid = _slug_from_relpath(rel, taken_ids)
            specs.append({
                "id": tid,
                "label": "Auto-discovered (%s)" % rel,
                "relpaths": [rel],
                "relpath": rel,
                "bind": "auto",
                "family": "自动发现",
                "src": "discovered",
            })
        self._discovered_cache[cache_key] = specs
        return specs

    def all_targets_for(self, env, home):
        """Unified target list: static baseline + persisted custom + actively discovered."""
        return TARGETS + self.custom_target_specs() + self.discover_extra_targets(env, home)

    def target_roots(self, target, env, home, create=False):
        """Existing candidate directories for a target (all of them).

        With create=True, an "always" bind target returns its primary directory
        so it can be created during --apply (dry-run never creates dirs).
        """
        roots = [r for r in self.candidate_roots(target, home) if _safe_is_dir(r)]
        if roots:
            return roots
        if create and target["bind"] == "always":
            return [self.candidate_roots(target, home)[0]]
        return []

    def _within(self, path, home):
        try:
            return path_within(Path(path).resolve(), Path(home).resolve())
        except OSError:
            return path_within(path, home)

    def enabled_targets(self, create=False):
        """Resolve which agent directories this machine manages."""
        explicit = self.config.get("targets")
        homes = self.env_homes(include_windows=bool(getattr(self.args, "include_windows", False)))
        resolved = []
        seen_roots = set()
        for env, home in homes.items():
            for t in self.all_targets_for(env, home):
                if explicit and t["id"] not in explicit:
                    continue
                for root in self.target_roots(t, env, home, create=create):
                    if not self._within(root, home):
                        note = "refusing target outside %s: %s (only the current user's home is managed)" % (home, root)
                        if note not in self.environment_notes:
                            self.environment_notes.append(note)
                        continue
                    key = _norm_path(root)
                    if key in seen_roots:
                        continue
                    seen_roots.add(key)
                    resolved.append({"target": t, "env": env, "root": root})
        return resolved

    def targets_by_id(self, ids, include_windows=False):
        homes = self.env_homes(include_windows=include_windows)
        out = []
        for tid in ids:
            matched_any = False
            for env, home in homes.items():
                by_id = {t["id"]: t for t in self.all_targets_for(env, home)}
                t = by_id.get(tid)
                if not t:
                    continue
                matched_any = True
                roots = [r for r in self.candidate_roots(t, home) if _safe_is_dir(r)]
                if not roots:
                    roots = [self.candidate_roots(t, home)[0]]
                for root in roots:
                    if self._within(root, home):
                        out.append({"target": t, "env": env, "root": root})
            if not matched_any:
                die("unknown target id: %s (run 'skillkit targets' or register with 'skillkit targets --add %s <path>')" % (tid, tid))
        return out

    # -- scaffolding ------------------------------------------------------
    def ensure_scaffolding(self):
        repo = self.require_repo()
        (repo / "skills").mkdir(parents=True, exist_ok=True)
        (repo / STATE_DIR).mkdir(parents=True, exist_ok=True)
        gi = repo / ".gitignore"
        wanted = [".skill-manager/", ".DS_Store", "Thumbs.db", "desktop.ini"]
        existing = gi.read_text(encoding="utf-8").splitlines() if gi.is_file() else []
        missing = [w for w in wanted if w not in existing]
        if missing:
            gi.write_text("\n".join(existing + missing) + "\n", encoding="utf-8")
        ga = repo / ".gitattributes"
        if not ga.is_file():
            ga.write_text("* text=auto eol=lf\n", encoding="utf-8")

    # -- output -----------------------------------------------------------
    def emit(self, obj, text=None):
        if self.json:
            print(json.dumps(obj, indent=2, ensure_ascii=False), flush=True)
        elif text is not None:
            log(text)
        else:
            log(json.dumps(obj, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Repo skill discovery & live link discovery
# ---------------------------------------------------------------------------


def repo_skills(repo):
    """Every directory under <repo>/skills that contains a SKILL.md."""
    repo = Path(repo)
    root = repo / "skills"
    out = []
    if not root.is_dir():
        return out
    for cur, dirs, files in os.walk(str(root)):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d.lower() not in {"node_modules"})
        curp = Path(cur)
        if len(curp.relative_to(root).parts) > 3:
            dirs[:] = []
            continue
        if SKILL_FILE in files:
            meta, _ = read_frontmatter(curp / SKILL_FILE)
            out.append({
                "name": curp.name,
                "fm_name": (meta.get("name") or "").strip(),
                "dir_name": curp.name,
                "path": curp,
                "rel": str(curp.relative_to(repo)).replace(os.sep, "/"),
                "description": meta.get("description", ""),
            })
            dirs[:] = []  # do not descend into a skill
    return out


FOREIGN_MARKERS = (".skills-lock.json", "skills-lock.json", ".skill-manager.json",
                   "install.json", ".install.json", ".source.json")


def is_our_link(entry, repo):
    """True when `entry` is a symlink/junction pointing inside our repo (live or dangling)."""
    if not repo:
        return False
    entry = Path(entry)
    if not is_skill_link(entry):
        return False
    target = resolve_link_target(entry)
    if not target:
        return False
    repo_real = os.path.realpath(str(repo))
    target_real = os.path.realpath(str(target)) if target.exists() else str(target)
    return path_within(target_real, repo_real) or path_within(str(target), str(repo))


def is_self_skill(entry):
    """True when `entry` is skill-manager itself (either direct clone or link)."""
    entry = Path(entry)
    if same_path(entry, SELF_SKILL_ROOT):
        return True
    if not is_skill_link(entry):
        return False
    target = resolve_link_target(entry)
    if not target:
        return False
    return same_path(target, SELF_SKILL_ROOT)


def foreign_reason(entry, repo=None):
    """Why an existing skill directory must be left alone (None = adoptable)."""
    entry = Path(entry)
    if is_self_skill(entry):
        return "self (skill-manager)"
    if is_skill_link(entry):
        if is_our_link(entry, repo):
            return None
        return "symlink (already linked/managed by another tool)"
    for marker in FOREIGN_MARKERS:
        if (entry / marker).is_file():
            return "lock/manifest file present (%s)" % marker
    if (entry / ".git").exists():
        return "git checkout inside the skill dir (use 'add <url>' instead)"
    return None


def discover_our_links(ctx, repo, targets=None):
    """Derive active + dangling links pointing into `repo` directly from the filesystem,
    plus any extra paths tracked in this environment's state file.
    """
    if targets is None:
        targets = ctx.enabled_targets(create=False)
    by_path = {}
    for tr in targets:
        root = tr["root"]
        if not root.is_dir():
            continue
        try:
            entries = sorted(root.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if is_skill_link(entry) and is_our_link(entry, repo):
                resolved = resolve_link_target(entry)
                kind = "junction" if is_junction(entry) else "symlink"
                by_path[_norm_path(entry)] = {
                    "name": entry.name,
                    "path": str(entry),
                    "target": str(resolved) if resolved else "",
                    "env": tr["env"],
                    "target_id": tr["target"]["id"],
                    "kind": kind,
                    "exists": entry.exists(),
                }
    for entry in ctx.state.get("links", []):
        lp = Path(entry["path"])
        key = _norm_path(lp)
        if key in by_path:
            continue
        if is_skill_link(lp) and is_our_link(lp, repo):
            resolved = resolve_link_target(lp)
            by_path[key] = {
                "name": entry["name"],
                "path": str(lp),
                "target": str(resolved) if resolved else entry.get("target", ""),
                "env": entry.get("env", "local"),
                "target_id": entry.get("target_id", "?"),
                "kind": "junction" if is_junction(lp) else "symlink",
                "exists": lp.exists(),
            }
    return list(by_path.values())


def prune_dangling_links(ctx, repo, targets=None, apply=False):
    """Remove links pointing into <repo>/skills/ whose target skill no longer exists."""
    skills_root = Path(repo) / "skills"
    skills_real = os.path.realpath(str(skills_root))
    pruned = []
    for entry in discover_our_links(ctx, repo, targets=targets):
        tp = Path(entry["target"]) if entry["target"] else None
        if not tp:
            continue
        in_skills = path_within(str(tp), skills_real) or path_within(str(tp), str(skills_root))
        if in_skills and not tp.exists():
            pruned.append(entry)
            if apply:
                lp = Path(entry["path"])
                if remove_link(lp):
                    ctx.state["links"] = [
                        e for e in ctx.state.get("links", [])
                        if _norm_path(e["path"]) != _norm_path(lp)
                    ]
    if apply and pruned:
        ctx.save_state()
    return pruned


def scan_env(ctx, env, home):
    """Find every skill living in a given environment's agent directories."""
    found = []
    seen_roots = set()
    for t in ctx.all_targets_for(env, home):
        for root in ctx.target_roots(t, env, home):
            if not ctx._within(root, home):
                continue
            rkey = _norm_path(root)
            if rkey in seen_roots:
                continue
            seen_roots.add(rkey)
            try:
                entries = sorted(root.iterdir())
            except OSError:
                continue
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                reason = foreign_reason(entry, ctx.repo)
                if is_skill_link(entry):
                    resolved = resolve_link_target(entry)
                    found.append({
                        "name": entry.name, "path": entry, "env": env, "target_id": t["id"],
                        "kind": "junction" if is_junction(entry) else "symlink",
                        "points_to": str(resolved) if resolved else "",
                        "hash": None, "mtime": 0, "files": 0, "frontmatter": {},
                        "managed_by": reason, "own": is_our_link(entry, ctx.repo),
                        "is_self": is_self_skill(entry), "has_git": False,
                    })
                    continue
                if not entry.is_dir() or not is_skill_dir(entry):
                    continue
                meta, _ = read_frontmatter(entry / SKILL_FILE)
                nfiles = sum(len(f) for _, _, f in os.walk(str(entry)))
                found.append({
                    "name": entry.name,
                    "fm_name": (meta.get("name") or "").strip(),
                    "dir_name": entry.name,
                    "path": entry,
                    "env": env,
                    "target_id": t["id"],
                    "kind": "dir",
                    "hash": dir_hash(entry),
                    "mtime": newest_mtime(entry),
                    "files": nfiles,
                    "frontmatter": meta,
                    "managed_by": reason,
                    "own": False,
                    "is_self": is_self_skill(entry),
                    "has_git": (entry / ".git").exists(),
                })
    return found


def group_by_name(items):
    groups = {}
    for it in items:
        groups.setdefault(it["name"], []).append(it)
    return groups


def pick_canonical(copies, prefer="newest"):
    """Choose which adoptable copy becomes the repo truth.

    prefer="newest"   -> newest mtime wins (default: the freshest install is
                         almost always the updated version), majority tie-break.
    prefer="majority" -> the content shared by the most directories wins.
    Any loser is backed up, never destroyed, and the plan lists both sides.
    """
    variants = {}
    for c in copies:
        if c.get("kind") in ("symlink", "junction") or c.get("managed_by"):
            continue
        variants.setdefault(c["hash"], []).append(c)
    if not variants:
        return None, variants

    def mtime_of(group):
        return max(x["mtime"] for x in group)

    if prefer == "majority":
        key = lambda kv: (len(kv[1]), mtime_of(kv[1]), sum(x["files"] for x in kv[1]))
    else:  # newest
        key = lambda kv: (mtime_of(kv[1]), len(kv[1]), sum(x["files"] for x in kv[1]))
    ranked = sorted(variants.items(), key=key, reverse=True)
    # Within the winning content hash group, pick the copy with newest mtime
    winners = sorted(ranked[0][1], key=lambda x: x["mtime"], reverse=True)
    return winners[0], variants


# ---------------------------------------------------------------------------
# Git & GitHub sync helpers
# ---------------------------------------------------------------------------


def git(repo, *args, check=False):
    rc, out, err = sh(["git", "-C", str(repo)] + list(args))
    if check and rc != 0:
        die("git %s failed: %s" % (" ".join(args), err or out))
    return rc, out, err


def git_is_repo(path):
    return (Path(path) / ".git").exists()


def git_dirty(repo):
    rc, out, _ = git(repo, "status", "--porcelain")
    return rc == 0 and bool(out.strip())


def git_has_remote(repo):
    rc, out, _ = git(repo, "remote")
    return rc == 0 and bool(out.strip())


def git_has_upstream(repo):
    rc, _, _ = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    return rc == 0


def git_identity(repo, field):
    rc, out, _ = git(repo, "config", "user." + field)
    if rc == 0 and out:
        return out
    rc, out, _ = sh(["git", "config", "--global", "user." + field])
    return out if rc == 0 else ""


def git_commit(repo, message):
    if not git_dirty(repo):
        return False
    git(repo, "add", "-A", check=True)
    rc, _, err = git(repo, "-c", "user.name=" + (git_identity(repo, "name") or "skillkit"),
                     "-c", "user.email=" + (git_identity(repo, "email") or "skillkit@localhost"),
                     "commit", "-m", message)
    if rc != 0:
        print("  ! git commit failed: %s" % err, file=sys.stderr, flush=True)
        return False
    return True


def have_gh():
    rc, _, _ = sh(["gh", "--version"])
    if rc != 0:
        return False
    rc, _, _ = sh(["gh", "auth", "status"])
    return rc == 0


def sync_push(ctx, repo, allow_secrets=False):
    """Push repo to remote after secret check. Never destroys local commits."""
    if not git_is_repo(repo):
        return {"status": "skipped", "reason": "not a git repository"}
    if not git_has_remote(repo):
        return {"status": "skipped", "reason": "no git remote configured"}
    findings = scan_secrets(repo)
    if findings and not allow_secrets:
        return {
            "status": "blocked",
            "reason": "potential secrets detected — push blocked (review or pass --allow-secrets)",
            "findings": findings,
        }
    if git_has_upstream(repo):
        rc, out, err = git(repo, "push")
    else:
        rc, out, err = git(repo, "push", "-u", "origin", "HEAD")
    if rc == 0:
        return {"status": "ok", "detail": out or "pushed to origin"}
    return {"status": "failed", "detail": err or out}


def _log_sync_result(ctx, res):
    status = res.get("status")
    if status == "ok":
        ctx.log("sync   : pushed to GitHub remote")
    elif status == "skipped":
        ctx.log("sync   : skipped (%s)" % res.get("reason", ""))
    elif status == "blocked":
        ctx.log("sync   : BLOCKED — %s" % res.get("reason", ""))
        for f in res.get("findings", [])[:10]:
            ctx.log("         ! %s: %s" % (f["reason"], f["rel"]))
    else:
        ctx.log("sync   : push FAILED (%s) — local commit is safe; run 'skillkit push --apply' later"
                % res.get("detail", ""))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_targets(ctx):
    """Show detected agent dirs (static + custom + auto-discovered), or add/remove custom targets."""
    args = ctx.args
    if getattr(args, "add_target", None):
        repo = ctx.require_repo()
        tid, raw_path = args.add_target
        tid = re.sub(r"[^A-Za-z0-9._-]", "-", tid.strip()).strip("-")
        if not tid:
            die("invalid target id")
        p = Path(raw_path).expanduser()
        abs_p = p if p.is_absolute() else (ctx.home / p)
        if not ctx._within(abs_p, ctx.home):
            die("refusing custom target outside %s: %s" % (ctx.home, abs_p))
        if path_within(abs_p, repo):
            die("refusing custom target inside skills-repo: %s" % abs_p)
        try:
            rel = str(abs_p.resolve().relative_to(ctx.home.resolve())).replace(os.sep, "/")
        except ValueError:
            rel = str(p).replace("\\", "/")
        custom = ctx.config.setdefault("custom_targets", {})
        existing_list = custom.get(tid)
        if isinstance(existing_list, list):
            if rel not in existing_list:
                existing_list.append(rel)
        elif isinstance(existing_list, str) and existing_list != rel:
            custom[tid] = [existing_list, rel]
        else:
            custom[tid] = [rel]
        ctx.save_config()
        git_commit(repo, "config: add custom target %s (%s)" % (tid, rel))
        ctx.emit({"id": tid, "relpaths": custom[tid], "path": str(ctx.home / rel)},
                 "registered custom target '%s' -> %s (saved in %s)" % (tid, rel, repo / CONFIG_NAME))
        return

    if getattr(args, "remove_target", None):
        repo = ctx.require_repo()
        tid = args.remove_target.strip()
        custom = ctx.config.get("custom_targets") or {}
        if tid not in custom:
            die("no custom target named %r in %s" % (tid, repo / CONFIG_NAME))
        removed_val = custom.pop(tid)
        ctx.config["custom_targets"] = custom
        ctx.save_config()
        git_commit(repo, "config: remove custom target %s" % tid)
        ctx.emit({"removed": tid, "relpaths": removed_val},
                 "removed custom target '%s' from %s" % (tid, repo / CONFIG_NAME))
        return

    rows = []
    homes = ctx.env_homes(include_windows=ctx.wsl or bool(ctx.args.include_windows))
    for env, home in homes.items():
        for t in ctx.all_targets_for(env, home):
            candidates = ctx.candidate_roots(t, home)
            existing = [r for r in candidates if _safe_is_dir(r)]
            n = 0
            for root in existing:
                try:
                    n += sum(1 for e in root.iterdir() if _safe_is_dir(e) or is_skill_link(e))
                except OSError:
                    pass
            rows.append({
                "env": env, "id": t["id"], "label": t["label"], "family": t["family"],
                "src": t["src"], "bind": t["bind"],
                "path": str(existing[0] if existing else candidates[0]),
                "alternates": [str(c) for c in candidates[1:]],
                "exists": bool(existing), "entries": n,
                "bound": bool(existing) or t["bind"] == "always",
            })
    src_badge = {"doc": "doc", "probable": "?", "custom": "cust", "discovered": "auto"}
    found = [r for r in rows if r["exists"]]
    discovered = [r for r in found if r["src"] == "discovered"]
    custom_rows = [r for r in rows if r["src"] == "custom"]
    lines = ["%-8s %-15s %-5s %-4s %-5s %s" % ("ENV", "ID", "EXIST", "SRC", "SKILL", "PATH")]
    for r in found:
        lines.append("%-8s %-15s %-5s %-4s %-5d %s" % (
            r["env"], r["id"][:15], "yes", src_badge.get(r["src"], "?"), r["entries"], r["path"]))
    hub = [r for r in rows if not r["exists"] and r["bind"] == "always"]
    for r in hub:
        lines.append("%-8s %-15s %-5s %-4s %-5d %s (created on apply)" % (
            r["env"], r["id"][:15], "no", "doc", 0, r["path"]))
    lines.append("")
    lines.append("%d detected dir(s) (%d auto-discovered, %d custom) across %d environment(s); %d built-in agent type(s)." % (
        len(found), len(discovered), len(custom_rows), len(homes), len(TARGETS)))
    for note in ctx.environment_notes:
        lines.append("note: " + note)
    ctx.emit({"environments": {k: str(v) for k, v in homes.items()},
              "detected": found, "discovered": discovered, "custom": custom_rows,
              "hubs": hub, "known_targets": len(TARGETS),
              "notes": ctx.environment_notes}, "\n".join(lines))


def cmd_scan(ctx):
    args = ctx.args
    inc_win = bool(args.include_windows) or args.env in ("windows", "all")
    homes = ctx.env_homes(include_windows=inc_win)
    if args.env == "local" and not args.include_windows:
        homes = {"local": homes["local"]}
    if args.env == "windows":
        homes = {"windows": homes["windows"]} if "windows" in homes else {}
        if not homes:
            die("no Windows environment detected (not WSL, or %USERPROFILE% unresolved)")

    all_found = []
    for env, home in homes.items():
        all_found.extend(scan_env(ctx, env, home))

    groups = group_by_name(all_found)
    entries = []
    for name, copies in sorted(groups.items()):
        real = [c for c in copies if c.get("kind") == "dir" and not c.get("managed_by")]
        hashes = {c["hash"] for c in real if c.get("hash")}
        canon, _ = pick_canonical(real)
        entries.append({
            "name": name,
            "copies": len(copies),
            "adoptable": len(real),
            "variants": len(hashes),
            "conflict": len(hashes) > 1,
            "managed_by": sorted({c["managed_by"] for c in copies if c.get("managed_by")}),
            "canonical": ({"env": canon["env"], "path": str(canon["path"]), "mtime": human_time(canon["mtime"])} if canon else None),
            "locations": [{"env": c["env"], "target": c["target_id"], "kind": c["kind"],
                           "path": str(c["path"]), "hash": (c["hash"] or "")[:10],
                           "mtime": human_time(c["mtime"]),
                           "managed_by": c.get("managed_by")} for c in copies],
        })

    if ctx.json:
        ctx.emit({"scanned_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "environments": list(homes),
                  "notes": ctx.environment_notes, "skills": entries})
        return
    log("scanned %d skills in %d environment(s)\n" % (len(entries), len(homes)))
    log("%-28s %-6s %-5s %-8s %s" % ("SKILL", "COPIES", "VAR", "CANON", "LOCATIONS"))
    for e in entries:
        locs = ", ".join("%s/%s" % (l["env"][:3], l["target"]) for l in e["locations"])
        flag = "  << CONFLICT" if e["conflict"] else ""
        if e["managed_by"]:
            if e["managed_by"] == ["self (skill-manager)"]:
                flag += "  [self]"
            else:
                flag += "  [skip: managed by another tool]"
        log("%-28s %-6d %-5d %-8s %s%s" % (e["name"][:28], e["copies"], e["variants"],
                                            (e["canonical"]["env"][:3] if e["canonical"] else "-"), locs, flag))
    for note in ctx.environment_notes:
        log("note: " + note)
    conflicts = [e for e in entries if e["conflict"]]
    if conflicts:
        log("\n%d name(s) exist with DIFFERENT content. Policy: keep the NEWEST copy," % len(conflicts))
        log("back the others up under %s/backup/, then link every agent to the surviving copy." % STATE_DIR)


def _recommended_repo(ctx):
    """Best default for THIS machine, with the reason shown to the user."""
    if os.environ.get("SKILLKIT_HOME"):
        return ctx.home / "skills-repo", "sandbox mode (SKILLKIT_HOME is set)"
    if ctx.wsl:
        for drive in ("d", "e", "f", "g"):
            root = Path("/mnt/%s" % drive)
            if root.is_dir():
                return root / "skills-repo", "Windows-visible drive: WSL agents AND Windows agents can use it"
        wh, _ = ctx.windows_home_guard()
        if wh:
            return wh / "skills-repo", "current Windows profile (the WSL filesystem is invisible to Windows)"
    return ctx.home / "skills-repo", "current user's home"


def _interactive(ctx=None):
    if ctx and (ctx.json or ctx.yes):
        return False
    if os.environ.get("CI") or os.environ.get("SKILLKIT_NONINTERACTIVE"):
        return False
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def _validate_repo_path(ctx, path):
    path = Path(path).expanduser().resolve()
    for tr in ctx.enabled_targets():
        if path_within(path, tr["root"]):
            return "inside an agent skill directory (%s)" % tr["root"]
    if path.name == "skills":
        return "that is a skills/ directory, not a repo root"
    if any(part.lower() in ("onedrive", "dropbox", "icloud drive") for part in path.parts):
        return "inside a cloud-sync folder (git + links fight with the sync client)"
    return None


def choose_repo(ctx, args):
    """Pick the repo location: --repo > recorded location > recommended default.

    Asking the user is deliberately ONE-TIME (at init) and only when interactive.
    Everything else stays non-interactive so scripts and agents never block.
    """
    if args.repo:
        return Path(args.repo).expanduser().resolve(), "--repo", []
    if ctx.repo:
        return ctx.repo, ctx.repo_source, []

    rec, why = _recommended_repo(ctx)
    notes = []
    alt = (ctx.home / "skills-repo").resolve()
    if alt != rec.resolve():
        notes.append("alternative: %s (this WSL filesystem only — Windows agents cannot see it)" % alt)
    notes.append("reason: " + why)

    if not _interactive(ctx):
        notes.append("non-interactive: using the recommended path (pass --repo to change it)")
        return rec.resolve(), "recommended default", notes

    log("")
    log("Where should skills-repo live on this machine?")
    log("  1) %s   <- recommended (%s)" % (rec, why))
    if alt != rec.resolve():
        log("  2) %s   (WSL-only: Windows agents will not see these skills)" % alt)
    log("  c) custom path")
    default = "1"
    try:
        answer = input("Choose [%s]: " % default).strip().lower() or default
    except EOFError:
        answer = default
    if answer in ("c", "custom", "3"):
        try:
            typed = input("Absolute path: ").strip()
        except EOFError:
            typed = ""
        if not typed:
            log("no path given, using the recommended one")
            return rec.resolve(), "recommended default", notes
        return Path(typed).expanduser().resolve(), "user typed", notes
    if answer == "2" and alt != rec.resolve():
        return alt, "user chose the WSL-only path", notes
    return rec.resolve(), "recommended default", notes


def _self_skill_name():
    meta, _ = read_frontmatter(SELF_SKILL_ROOT / SKILL_FILE)
    return (meta.get("name") or SELF_SKILL_ROOT.name or "skill-manager").strip()


def _self_upstream_url():
    if git_is_repo(SELF_SKILL_ROOT):
        rc, out, _ = git(SELF_SKILL_ROOT, "remote", "get-url", "origin")
        if rc == 0 and out.strip():
            return out.strip()
    return SELF_UPSTREAM_URL


def cmd_init(ctx):
    args = ctx.args
    repo, repo_source, repo_notes = choose_repo(ctx, args)
    ctx.repo = repo
    ctx.config = ctx._load_config()
    ctx.state = ctx._load_state()
    problem = _validate_repo_path(ctx, repo)
    if problem:
        die("refusing repo path %s: %s" % (repo, problem))
    if os.environ.get("SKILLKIT_HOME") and not ctx._within(repo, ctx.home):
        die("sandbox mode: SKILLKIT_HOME is set, so the repo must stay inside %s (got %s)" % (ctx.home, repo))

    # Pre-load template & self metadata BEFORE any move/replace of SELF_SKILL_ROOT
    template_path = SELF_SKILL_ROOT / "assets" / "repo-readme-template.md"
    readme_template_text = template_path.read_text(encoding="utf-8") if template_path.is_file() else ""
    self_name = _self_skill_name()
    self_upstream = _self_upstream_url()
    adopt_self = (
        not bool(getattr(args, "no_adopt_self", False))
        and is_skill_dir(SELF_SKILL_ROOT)
        and not path_within(SELF_SKILL_ROOT, repo / "skills")
    )

    ctx.log("== skillkit init ==")
    ctx.log("repo        : %s   [%s]" % (repo, repo_source))
    for note in repo_notes:
        ctx.log("              " + note)
    ctx.log("environment : %s%s" % ("WSL" if ctx.wsl else ("Windows" if os.name == "nt" else "POSIX"),
                                    " (home: %s)" % ctx.home))
    ctx.log("mode        : %s" % ("APPLY" if ctx.apply else "DRY-RUN (add --apply to execute)"))
    if repo.exists() and not repo.is_dir():
        die("%s exists and is not a directory" % repo)
    ctx.log("scope       : only the CURRENT user's home (%s); project-level and other users' dirs untouched" % ctx.home)
    ctx.log("conflict    : keep the NEWEST copy by default (--prefer majority to override)")
    ctx.log("removal     : moves into %s/trash/, never deletes; deletion needs a separate confirmation" % STATE_DIR)
    if ctx.wsl and not str(repo).startswith("/mnt/"):
        ctx.log("  note: repo lives inside the WSL filesystem, so Windows-side agents cannot use it.")
        ctx.log("        For dual WSL+Windows use, put the repo on a Windows drive (e.g. /mnt/d/skills-repo).")

    # ---- 1. repo + remote ----------------------------------------------
    remote_url = args.repo_url
    if repo.exists() and git_is_repo(repo):
        ctx.log("\n[1/5] repo already exists (%s)" % repo)
    else:
        ctx.log("\n[1/5] %s %s" % ("would create" if not ctx.apply else "creating", repo))
        if ctx.apply:
            repo.mkdir(parents=True, exist_ok=True)
            rc, _, _ = git(repo, "init", "-b", "main")
            if rc != 0:
                git(repo, "init", check=True)
                git(repo, "symbolic-ref", "HEAD", "refs/heads/main")

    prefer = getattr(args, "prefer", None) or ctx.config.get("conflict_policy") or "newest"
    if ctx.apply:
        ctx.ensure_scaffolding()
        ctx.config["conflict_policy"] = prefer
        if "auto_push" not in ctx.config:
            ctx.config["auto_push"] = True
        ctx.save_config()
        readme = repo / "README.md"
        if not readme.is_file() and readme_template_text:
            readme.write_text(readme_template_text, encoding="utf-8")

    # remote handling
    if remote_url:
        ctx.log("   remote: %s" % remote_url)
        if ctx.apply:
            rc, out, _ = git(repo, "remote")
            if "origin" in out.split():
                git(repo, "remote", "set-url", "origin", remote_url)
            else:
                git(repo, "remote", "add", "origin", remote_url)
    elif ctx.apply and args.create_remote and have_gh():
        rc, login, _ = sh(["gh", "api", "user", "--jq", ".login"])
        if rc != 0:
            die("gh is installed but not authenticated. Run: gh auth login")
        if repo.exists() and git_has_remote(repo):
            ctx.log("   remote: already configured, skipping gh repo create")
        else:
            rc, out, err = sh(["gh", "repo", "create", "%s/skills-repo" % login, "--private", "--source", str(repo)])
            if rc != 0:
                ctx.log("   ! gh repo create failed: %s" % (err or out))
            else:
                ctx.log("   created private repo %s/skills-repo" % login)
    elif ctx.apply and not git_has_remote(repo):
        if have_gh():
            ctx.log("   remote: none yet -> add with: git -C %s remote add origin <url> && git -C %s push -u origin HEAD" % (repo, repo))
            ctx.log("           (or re-run with --create-remote to create <you>/skills-repo via gh)")
        else:
            ctx.log("   remote: no authenticated 'gh' CLI found.")
            ctx.log("           create a private repo on GitHub (e.g. skills-repo), then:")
            ctx.log("             git -C %s remote add origin git@github.com:<you>/skills-repo.git" % repo)
            ctx.log("             git -C %s push -u origin HEAD" % repo)

    # ---- 2. scan --------------------------------------------------------
    inc_win = bool(args.include_windows)
    homes = ctx.env_homes(include_windows=inc_win)
    ctx.log("\n[2/5] scanning %d environment(s) for existing skills" % len(homes))
    found = []
    for env, home in homes.items():
        got = scan_env(ctx, env, home)
        found.extend(got)
        ctx.log("  %-8s %-4d skill copies  (home: %s)" % (env, len(got), home))
    for note in ctx.environment_notes:
        ctx.log("  note: " + note)
    if not inc_win and ctx.wsl:
        ctx.log("  note: Windows-side agent dirs are not scanned. Add --include-windows to include the CURRENT Windows user.")

    existing = repo_skills(repo) if repo.is_dir() else []
    existing_names = {s["name"] for s in existing}
    groups = group_by_name(found)

    plan_import, plan_skip, plan_backup, plan_foreign = [], [], [], []
    repo_by_name = {s["name"]: s for s in existing}
    self_plan = None
    self_step_aside = []
    if adopt_self:
        self_real_in_agent = [
            c for c in groups.get(self_name, [])
            if c.get("kind") == "dir" and c.get("is_self")
        ]
        if self_name not in existing_names:
            self_plan = {
                "name": self_name,
                "src": SELF_SKILL_ROOT,
                "dest": repo / "skills" / self_name,
                "upstream": self_upstream,
                "in_agent_dirs": self_real_in_agent,
            }
        elif self_real_in_agent:
            self_step_aside = self_real_in_agent

    for name, copies in sorted(groups.items()):
        if adopt_self and name == self_name:
            # Handle skill-manager itself via self_plan / self_step_aside (keep any non-self duplicates in plan_backup)
            other_real = [c for c in copies if c.get("kind") == "dir" and not c.get("is_self") and not c.get("managed_by")]
            for c in other_real:
                c["same_as_repo"] = False
                plan_backup.append(c)
            if self_name in existing_names and not self_step_aside and not other_real:
                plan_skip.append((name, "already in repo (skill-manager)", copies[0]))
            continue
        rejected = [c for c in copies if c.get("managed_by")]
        real = [c for c in copies if c.get("kind") == "dir" and not c.get("managed_by")]
        if rejected:
            plan_foreign.extend(rejected)
        if not real:
            if any(c.get("own") for c in copies):
                why = "already linked to this repo"
            elif any(c.get("is_self") for c in copies):
                why = "skill-manager itself (--no-adopt-self)"
            elif rejected:
                why = rejected[0]["managed_by"]
            else:
                why = "already a symlink (managed elsewhere)"
            plan_skip.append((name, why, copies[0]))
            continue
        if name in existing_names:
            repo_hash = dir_hash(repo_by_name[name]["path"])
            for c in real:
                c["same_as_repo"] = (c["hash"] == repo_hash)
                plan_backup.append(c)
            plan_skip.append((name, "already in repo (agent copies replaced by links)", real[0]))
            continue
        # Only adoptable real copies participate in conflict resolution (never foreign-managed dirs)
        canon, variants = pick_canonical(real, prefer)
        if canon is None:
            continue
        plan_import.append({"name": name, "canonical": canon, "variants": variants, "copies": real})
        for c in real:
            if c is canon:
                continue
            if args.no_dedupe and c["hash"] != canon["hash"]:
                continue
            c["same_as_repo"] = False
            plan_backup.append(c)
        if args.no_dedupe:
            for c in real:
                if c is not canon and c["hash"] != canon["hash"]:
                    plan_skip.append((name, "divergent copy kept as-is (--no-dedupe)", c))

    ctx.log("\n[3/5] plan")
    total_imports = len(plan_import) + (1 if self_plan else 0)
    ctx.log("  import : %d" % total_imports)
    if self_plan:
        note_self = " [self: strip .git, record upstream]"
        if self_plan["in_agent_dirs"]:
            note_self += " (will replace %s with link)" % self_plan["in_agent_dirs"][0]["path"]
        ctx.log("    + %-26s <- self (%s)%s" % (self_plan["name"], self_plan["src"], note_self))
    for item in plan_import:
        c = item["canonical"]
        conflict = len(item["variants"]) > 1
        ctx.log("    + %-26s <- %s/%s%s" % (item["name"], c["env"], c["target_id"],
                                            "   [CONFLICT keeping %s]" % human_time(c["mtime"]) if conflict else ""))
        if conflict:
            for h, group in sorted(item["variants"].items(), key=lambda kv: -max(x["mtime"] for x in kv[1])):
                mark = "*" if h == c["hash"] else " "
                ctx.log("        %s %d copy(ies), newest %s, e.g. %s" % (
                    mark, len(group), human_time(max(x["mtime"] for x in group)), group[0]["path"]))
            ctx.log("        (policy: --prefer %s; losers are backed up, not destroyed)" % prefer)
    if plan_backup or self_step_aside:
        ctx.log("  replace+backup : %d copy(ies) -> %s/backup/" % (len(plan_backup) + len(self_step_aside), STATE_DIR))
        for c in plan_backup + self_step_aside:
            ctx.log("    ~ %-26s %s (%s)" % (c["name"], c["path"], human_time(c["mtime"])))
    if plan_skip:
        ctx.log("  skip   : %d" % len(plan_skip))
        for name, why, _ in plan_skip:
            ctx.log("    - %-26s %s" % (name, why))
    if plan_foreign:
        ctx.log("  left alone (managed by another tool, reported only): %d copy(ies)" % len(plan_foreign))
        for c in plan_foreign[:12]:
            arrow = (" -> %s" % c["points_to"]) if c.get("points_to") else ""
            ctx.log("    ! %-26s %s%s  [%s]" % (c["name"], c["path"], arrow, c["managed_by"]))
        if len(plan_foreign) > 12:
            ctx.log("    ... %d more" % (len(plan_foreign) - 12))

    # ---- 3. execute imports --------------------------------------------
    stamp = time.strftime("%Y%m%d-%H%M%S")
    moved = 0
    copy_kept_paths = set()
    if ctx.apply:
        ctx.log("\n[4/5] migrating")
        backup_root = repo / STATE_DIR / "backup" / stamp
        if self_plan:
            s_src = Path(self_plan["src"])
            s_dest = Path(self_plan["dest"])
            if not s_dest.exists():
                backup_dst = _unique_path(backup_root / "self", self_plan["name"])
                copy_tree(s_src, backup_dst, keep_git=True)
                ctx.state.setdefault("backups", []).append({
                    "name": self_plan["name"], "from": str(s_src), "backup": str(backup_dst), "at": stamp,
                })
                # Always copy WITHOUT .git (avoids nested .git and preserves standalone dev clones)
                copy_tree(s_src, s_dest, keep_git=False)
                ctx.config.setdefault("sources", {})[self_plan["name"]] = self_plan["upstream"]
                ctx.save_config()
                ctx.log("  + %s (adopted from self; .git stripped, upstream saved)" % self_plan["name"])
                moved += 1
            for c in self_plan["in_agent_dirs"]:
                orig = Path(c["path"])
                if not orig.exists() or is_skill_link(orig):
                    continue
                if args.copy:
                    copy_kept_paths.add(_norm_path(orig))
                    continue
                if path_within(os.getcwd(), orig):
                    try:
                        os.chdir(str(repo))
                    except OSError:
                        pass
                trash = _unique_path(repo / STATE_DIR / "trash" / stamp / c["env"], "%s@%s" % (c["name"], c["target_id"]))
                trash.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.move(str(orig), str(trash))
                    ctx.log("  ~ replaced running self dir %s -> link" % orig)
                except (OSError, shutil.Error) as exc:
                    copy_kept_paths.add(_norm_path(orig))
                    ctx.log("  ! could not move running dir %s (in use: %s)." % (orig, exc))
                    ctx.log("    close any terminal inside it and re-run: python %s init --apply"
                            % (s_dest / "scripts" / "skillkit.py"))
        for c in self_step_aside:
            orig = Path(c["path"])
            if not orig.exists() or is_skill_link(orig):
                continue
            if args.copy:
                copy_kept_paths.add(_norm_path(orig))
                continue
            if path_within(os.getcwd(), orig):
                try:
                    os.chdir(str(repo))
                except OSError:
                    pass
            backup_dst = _unique_path(backup_root / c["env"], "%s@%s" % (c["name"], c["target_id"]))
            copy_tree(orig, backup_dst, keep_git=True)
            trash = _unique_path(repo / STATE_DIR / "trash" / stamp / c["env"], "%s@%s" % (c["name"], c["target_id"]))
            trash.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(orig), str(trash))
                ctx.log("  ~ stepped aside self dir %s -> link" % orig)
            except (OSError, shutil.Error) as exc:
                copy_kept_paths.add(_norm_path(orig))
                ctx.log("  ! could not move %s (in use: %s)" % (orig, exc))
        for item in plan_import:
            src = Path(item["canonical"]["path"])
            dest = repo / "skills" / item["name"]
            if dest.exists():
                ctx.log("  ! %s already exists in repo, skipped" % item["name"])
                continue
            backup_dst = _unique_path(backup_root / item["canonical"]["env"], item["name"])
            copy_tree(src, backup_dst, keep_git=True)
            ctx.state.setdefault("backups", []).append({
                "name": item["name"], "from": str(src), "backup": str(backup_dst), "at": stamp,
            })
            if args.copy:
                copy_tree(src, dest, keep_git=False)
                copy_kept_paths.add(_norm_path(src))
            else:
                shutil.move(str(src), str(dest))
            ctx.log("  + %s" % item["name"])
            moved += 1
        for c in plan_backup:
            src = Path(c["path"])
            if not src.exists() or is_skill_link(src):
                continue
            label = "%s@%s" % (c["name"], c["target_id"])
            if not c.get("same_as_repo"):
                backup_dst = _unique_path(backup_root / c["env"], label)
                copy_tree(src, backup_dst, keep_git=True)
            trash = _unique_path(repo / STATE_DIR / "trash" / stamp / c["env"], label)
            trash.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(src), str(trash))
            except (OSError, shutil.Error) as exc:
                ctx.log("  ! could not move %s: %s" % (src, exc))
                continue
            ctx.log("  ~ %s %s (%s)" % ("stepped aside" if c.get("same_as_repo") else "removed duplicate", src,
                                        "identical to repo" if c.get("same_as_repo") else "backed up"))
        ctx.ensure_scaffolding()
        ctx.save_state()
        if moved or plan_backup or self_step_aside or git_dirty(repo):
            git_commit(repo, "import: adopt %d skill(s) into skills-repo" % moved)
    else:
        ctx.log("\n[4/5] migration (skipped, dry-run)")

    # ---- 4. link --------------------------------------------------------
    ctx.log("\n[5/5] linking agents to skills-repo")
    skills = repo_skills(repo) if repo.is_dir() else []
    targets = ctx.enabled_targets(create=True)
    created = errs = 0
    sync_res = None
    if not ctx.apply:
        planned = len(skills) + total_imports
        ctx.log("  would link %d skill(s) into: %s" % (
            planned, ", ".join(sorted({r["target"]["id"] for r in targets})) or "(none detected)"))
    else:
        created, errs = link_all(ctx, skills, targets, skip_paths=copy_kept_paths)
        if copy_kept_paths:
            ctx.log("  note: kept %d original real dir(s) untouched (skipped linking over them)" % len(copy_kept_paths))
        ctx.log("  linked %d, errors %d" % (created, errs))
        git_commit(repo, "link: refresh agent links")
        should_push = (bool(args.push) or bool(ctx.config.get("auto_push", True))) and not bool(getattr(args, "no_push", False))
        if should_push and git_has_remote(repo):
            sync_res = sync_push(ctx, repo, allow_secrets=bool(getattr(args, "allow_secrets", False)))
            _log_sync_result(ctx, sync_res)

    recorded = False
    if ctx.apply:
        recorded = ctx.record_location(repo)
        if recorded:
            ctx.log("\nremembered repo location in %s" % ctx.location_file())
    else:
        ctx.log("\nwould remember the repo location in %s" % ctx.location_file())
    ctx.log("\nDone." if ctx.apply else "\nDry-run complete. Re-run with --apply to execute.")
    if ctx.apply and not git_has_remote(repo):
        ctx.log("Next: add a private GitHub remote, then 'skillkit push --apply'.")
    ctx.log("Next: 'skillkit doctor' to verify, 'skillkit list' to inspect.")

    if ctx.json:
        imported_names = ([self_plan["name"]] if self_plan else []) + [i["name"] for i in plan_import]
        ctx.emit({
            "apply": ctx.apply,
            "repo": str(repo),
            "repo_source": repo_source,
            "imported": imported_names,
            "self_adopted": bool(self_plan),
            "moved": moved,
            "backed_up": [str(c["path"]) for c in plan_backup + self_step_aside],
            "skipped": [{"name": n, "reason": w} for n, w, _ in plan_skip],
            "foreign": [{"name": c["name"], "path": str(c["path"]), "reason": c["managed_by"]} for c in plan_foreign],
            "targets": sorted({r["target"]["id"] for r in targets}),
            "linked": created,
            "errors": errs,
            "sync": sync_res,
            "location_recorded": recorded,
        })


def link_all(ctx, skills, targets, mode_override=None, skip_paths=None):
    """Create links for `skills` into `targets`, merging state by normalized link path."""
    created = errs = 0
    mode = mode_override or ctx.config.get("link_mode", "auto")
    skip_paths = skip_paths or set()
    existing_state = {
        _norm_path(e["path"]): e
        for e in ctx.state.get("links", [])
        if e.get("path")
    }
    for sk in skills:
        for tr in targets:
            root = tr["root"]
            link = root / sk["name"]
            if _norm_path(link) in skip_paths:
                continue
            try:
                root.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                ctx.log("  ! cannot create %s: %s" % (root, exc))
                errs += 1
                continue
            if link_points_to(link, sk["path"]):
                existing_state[_norm_path(link)] = {
                    "name": sk["name"], "path": str(link), "target": str(sk["path"]),
                    "env": tr["env"], "target_id": tr["target"]["id"],
                    "kind": "junction" if is_junction(link) else "symlink",
                }
                continue
            if link.exists() or is_skill_link(link):
                if not is_skill_link(link):
                    ctx.log("  ! %s is a REAL directory, not a link -> left untouched (run 'skillkit doctor' for details)" % link)
                    errs += 1
                    continue
                if not is_our_link(link, ctx.repo):
                    if not is_self_skill(link):
                        ctx.log("  ! %s is a link managed by another tool -> left untouched" % link)
                        continue
                remove_link(link)
            try:
                kind = make_link(sk["path"], link, mode=mode, env=tr["env"])
                existing_state[_norm_path(link)] = {
                    "name": sk["name"], "path": str(link), "target": str(sk["path"]),
                    "env": tr["env"], "target_id": tr["target"]["id"], "kind": kind,
                }
                created += 1
            except (RuntimeError, OSError, shutil.Error) as exc:
                ctx.log("  ! link failed %s: %s" % (link, exc))
                errs += 1
    ctx.state["links"] = sorted(existing_state.values(), key=lambda x: (x.get("name", ""), x.get("path", "")))
    ctx.save_state()
    return created, errs


def cmd_link(ctx):
    repo = ctx.require_repo()
    skills = repo_skills(repo)
    if ctx.args.names:
        wanted = set(ctx.args.names)
        skills = [s for s in skills if s["name"] in wanted or s["dir_name"] in wanted]
        missing = wanted - {s["name"] for s in skills} - {s["dir_name"] for s in skills}
        if missing:
            die("not in repo: %s" % ", ".join(sorted(missing)))
    if not skills:
        die("no skills selected")
    if ctx.args.to:
        targets = ctx.targets_by_id([x.strip() for x in ctx.args.to.split(",") if x.strip()],
                                    include_windows=bool(ctx.args.include_windows))
    else:
        targets = ctx.enabled_targets(create=True)
    mode_override = ctx.args.mode or None
    ctx.log("linking %d skill(s) into %d target dir(s) [%s]" % (
        len(skills), len(targets), "APPLY" if ctx.apply else "DRY-RUN"))
    planned = [{"skill": sk["name"], "link": str(tr["root"] / sk["name"]),
                "target_id": tr["target"]["id"], "env": tr["env"]}
               for sk in skills for tr in targets]
    if not ctx.apply:
        for item in planned:
            ctx.log("  %-28s -> %s" % (item["skill"], item["link"]))
        ctx.log("\nDry-run complete. Re-run with --apply.")
        if ctx.json:
            ctx.emit({"apply": False, "planned": planned})
        return
    created, errs = link_all(ctx, skills, targets, mode_override=mode_override)
    ctx.log("linked %d, errors %d" % (created, errs))
    git_commit(repo, "link: refresh agent links")
    if ctx.json:
        ctx.emit({"apply": True, "linked": created, "errors": errs, "planned": planned})


def cmd_unlink(ctx):
    repo = ctx.require_repo()
    names = set(ctx.args.names or [])
    if not names and not ctx.args.all:
        die("specify skill name(s) to unlink, or pass --all to unlink every skill")
    live_links = discover_our_links(ctx, repo)
    matched = [e for e in live_links if not names or e["name"] in names]
    removed = 0
    actions = []
    for entry in matched:
        link = Path(entry["path"])
        if not ctx.apply:
            ctx.log("would unlink %s" % link)
            actions.append({"name": entry["name"], "path": str(link), "status": "would_unlink"})
            continue
        if remove_link(link):
            ctx.log("unlinked %s" % link)
            removed += 1
            actions.append({"name": entry["name"], "path": str(link), "status": "unlinked"})
            ctx.state["links"] = [
                e for e in ctx.state.get("links", [])
                if _norm_path(e["path"]) != _norm_path(link)
            ]
        else:
            ctx.log("  ! could not unlink %s (real directory?)" % link)
            actions.append({"name": entry["name"], "path": str(link), "status": "failed"})
    if ctx.apply:
        ctx.save_state()
        ctx.log("removed %d link(s)" % removed)
    else:
        ctx.log("\nDry-run complete. Re-run with --apply.")
    if ctx.json:
        ctx.emit({"apply": ctx.apply, "removed": removed, "actions": actions})


def cmd_list(ctx):
    repo = ctx.require_repo()
    skills = repo_skills(repo)
    links = {}
    for entry in discover_our_links(ctx, repo):
        links.setdefault(entry["name"], []).append(entry)
    rows = []
    for sk in skills:
        ok = []
        for entry in links.get(sk["name"], []):
            status = "ok" if link_points_to(entry["path"], sk["path"]) else "BROKEN"
            ok.append({"target": entry.get("target_id", "?"), "env": entry.get("env", "?"),
                       "kind": entry.get("kind", "?"), "path": entry["path"], "status": status})
        rows.append({"name": sk["name"], "rel": sk["rel"], "description": sk["description"][:80], "links": ok})
    text = ["%-28s %-40s %s" % ("SKILL", "LINKS", "PATH")]
    for r in rows:
        linked = ", ".join("%s/%s%s" % (l["env"][:3], l["target"], "" if l["status"] == "ok" else "(BROKEN)") for l in r["links"]) or "-"
        text.append("%-28s %-40s %s" % (r["name"][:28], linked[:40], r["rel"]))
    ctx.emit({"repo": str(repo), "count": len(rows), "skills": rows}, "\n".join(text))


def cmd_repo(ctx):
    """Show (or set) which local repo this machine uses."""
    loc = ctx.location_file()
    if ctx.args.set_path:
        path = Path(ctx.args.set_path).expanduser().resolve()
        if not path.is_dir():
            die("not a directory: %s" % path)
        problem = _validate_repo_path(ctx, path)
        if problem:
            die("refusing %s: %s" % (path, problem))
        ok = ctx.record_location(path)
        ctx.emit({"repo": str(path), "saved": ok, "location_file": str(loc)},
                 "repo location set to %s  (%s)" % (path, "saved" if ok else "NOT saved"))
        return
    if ctx.args.forget:
        existed = loc.is_file()
        if existed:
            os.unlink(str(loc))  # one explicit path, the pointer file only
        ctx.emit({"forgot": existed, "location_file": str(loc)},
                 ("forgot the recorded location (%s removed)" % loc) if existed else ("nothing recorded (%s does not exist)" % loc))
        return
    rec, why = _recommended_repo(ctx)
    info = {
        "repo": str(ctx.repo) if ctx.repo else None,
        "source": ctx.repo_source,
        "location_file": str(loc),
        "location_recorded": loc.is_file(),
        "recommended": str(rec),
        "recommended_reason": why,
        "env_override": os.environ.get("SKILLKIT_REPO"),
    }
    text = [
        "repo        : %s" % (info["repo"] or "(not found)"),
        "source      : %s" % info["source"],
        "remembered  : %s%s" % (info["location_file"], "" if info["location_recorded"] else "  (absent)"),
        "recommended : %s  (%s)" % (info["recommended"], info["recommended_reason"]),
    ]
    ctx.emit(info, "\n".join(text))


def cmd_status(ctx):
    repo = ctx.require_repo()
    skills = repo_skills(repo)
    skill_by_name = {s["name"]: s for s in skills}
    links = discover_our_links(ctx, repo)
    broken = []
    for l in links:
        sk = skill_by_name.get(l["name"])
        if not sk or not link_points_to(l["path"], sk["path"]):
            broken.append(l)
    info = {
        "repo": str(repo),
        "repo_source": ctx.repo_source,
        "auto_push": bool(ctx.config.get("auto_push", True)),
        "git": {
            "is_repo": git_is_repo(repo),
            "dirty": git_dirty(repo),
            "remote": git_has_remote(repo),
            "branch": (git(repo, "rev-parse", "--abbrev-ref", "HEAD")[1] or "").strip(),
        },
        "skills": len(skills),
        "links": len(links),
        "broken_links": len(broken),
        "targets": [{"id": r["target"]["id"], "env": r["env"], "path": str(r["root"]),
                     "exists": r["root"].is_dir()} for r in ctx.enabled_targets(create=True)],
    }
    text = [
        "repo      : %s   [%s]" % (info["repo"], info.get("repo_source", "?")),
        "git       : %s%s%s" % ("ok" if info["git"]["is_repo"] else "NOT A REPO",
                                " (dirty)" if info["git"]["dirty"] else "",
                                "" if info["git"]["remote"] else " (no remote)"),
        "auto_push : %s" % ("on" if info["auto_push"] else "off"),
        "skills    : %d" % info["skills"],
        "links     : %d total, %d broken" % (info["links"], info["broken_links"]),
    ]
    for t in info["targets"]:
        text.append("target    : %-13s %-8s %s%s" % (
            t["id"], t["env"], t["path"], "" if t["exists"] else " (will create on apply)"))
    ctx.emit(info, "\n".join(text))


def _run_doctor_checks(ctx, repo):
    problems, warnings = [], []
    skills = repo_skills(repo)
    skill_by_name = {s["name"]: s for s in skills}
    targets = ctx.enabled_targets(create=True)

    # 1. frontmatter / naming
    seen = {}
    for sk in skills:
        meta, _ = read_frontmatter(Path(sk["path"]) / SKILL_FILE)
        if not meta.get("name"):
            problems.append("%s: SKILL.md has no 'name' in frontmatter" % sk["rel"])
        elif meta["name"].strip() != sk["dir_name"]:
            warnings.append("%s: frontmatter name '%s' != directory '%s'; links keep the DIRECTORY name "
                            "(the skill is never renamed)" % (sk["rel"], meta["name"], sk["dir_name"]))
        if not meta.get("description"):
            problems.append("%s: SKILL.md has no 'description'" % sk["rel"])
        if sk["name"] in seen:
            problems.append("duplicate skill name '%s' in %s and %s" % (sk["name"], seen[sk["name"]], sk["rel"]))
        seen[sk["name"]] = sk["rel"]

    # 2. live + dangling links pointing into this repo
    for entry in discover_our_links(ctx, repo, targets=targets):
        link = Path(entry["path"])
        target = Path(entry["target"]) if entry["target"] else None
        if not target or not target.exists():
            problems.append("dangling link %s -> missing %s" % (link, target or "?"))
        else:
            sk = skill_by_name.get(entry["name"])
            if sk and not link_points_to(link, sk["path"]):
                problems.append("stale link %s (expected -> %s)" % (link, sk["path"]))

    # 3. expected links for enabled targets
    expected = 0
    for tr in targets:
        for sk in skills:
            expected += 1
            link = tr["root"] / sk["name"]
            if not (link.exists() or is_skill_link(link)):
                problems.append("not linked: %s (target %s)" % (sk["name"], tr["root"]))
            elif is_skill_link(link) and is_our_link(link, repo) and not link_points_to(link, sk["path"]):
                msg = "stale link %s (expected -> %s)" % (link, sk["path"])
                if msg not in problems:
                    problems.append(msg)

    # 4. foreign / unmanaged skills inside agent dirs
    for tr in targets:
        root = tr["root"]
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if entry.name.startswith(".") or not (entry.is_dir() or is_skill_link(entry)):
                continue
            if not is_skill_link(entry) and not is_skill_dir(entry):
                continue  # not a skill directory (cache, notes, .system...) — ignore
            if is_self_skill(entry):
                continue
            if is_skill_link(entry):
                if is_our_link(entry, repo):
                    continue
                warnings.append("left alone in %s: %s [%s]" % (root, entry.name, foreign_reason(entry, repo)))
                continue
            reason = foreign_reason(entry, repo)
            if reason:
                warnings.append("left alone in %s: %s [%s]" % (root, entry.name, reason))
                continue
            problems.append("unmanaged real directory in %s: %s (run 'skillkit init --apply' to adopt)" % (root, entry.name))

    # 5. secrets
    for f in scan_secrets(repo):
        warnings.append("%s: %s" % (f["reason"], f["rel"]))

    # 6. git state
    info = {"skills": len(skills), "expected_links": expected}
    if git_is_repo(repo):
        if git_dirty(repo):
            warnings.append("repo has uncommitted changes (run 'skillkit push --apply')")
        if not git_has_remote(repo):
            warnings.append("repo has no git remote (no off-machine backup)")
    else:
        problems.append("%s is not a git repository" % repo)

    return skills, targets, problems, warnings, info


def cmd_doctor(ctx):
    repo = ctx.require_repo()
    skills, targets, problems, warnings, info = _run_doctor_checks(ctx, repo)
    repaired = None

    if ctx.args.fix:
        dangling = prune_dangling_links(ctx, repo, targets=targets, apply=False)
        if not ctx.apply:
            ctx.log("doctor --fix [DRY-RUN]: add --apply to repair missing/stale links and prune %d dangling link(s)." % len(dangling))
            for d in dangling:
                ctx.log("  would prune dangling link %s" % d["path"])
        else:
            ctx.log("repairing missing/stale links and pruning dangling links ...")
            pruned = prune_dangling_links(ctx, repo, targets=targets, apply=True)
            created, errs = link_all(ctx, skills, targets)
            repaired = {"relinked": created, "pruned": len(pruned), "errors": errs}
            ctx.log("relinked %d, pruned %d, errors %d" % (created, len(pruned), errs))
            # Re-verify honestly instead of masking failed repairs
            skills, targets, problems, warnings, info = _run_doctor_checks(ctx, repo)

    payload = {"ok": not problems, "problems": problems, "warnings": warnings, "info": info}
    if repaired is not None:
        payload["repaired"] = repaired
    if ctx.json:
        ctx.emit(payload)
        return
    log("doctor: %d skill(s), %d expected link(s)" % (info["skills"], info["expected_links"]))
    if not problems and not warnings:
        log("all good.")
    for p in problems:
        log("  PROBLEM  %s" % p)
    for w in warnings:
        log("  warning  %s" % w)
    log("\n%d problem(s), %d warning(s)%s" % (
        len(problems), len(warnings),
        " (use --fix --apply for link repair)" if problems else ""))


def cmd_add(ctx):
    args = ctx.args
    repo = ctx.require_repo()
    src = args.source
    is_url = bool(re.match(r"^(https?://|git@|ssh://|file://)", src))
    tmp = None
    try:
        if is_url:
            tmp = Path(tempfile.mkdtemp(prefix="skillkit-clone-"))
            ctx.log("cloning %s" % src)
            rc, out, err = sh(["git", "clone", "--depth", "1", src, str(tmp)])
            if rc != 0:
                die("git clone failed: %s" % (err or out))
            candidates = _discover_skills_in_tree(tmp)
            if not candidates:
                die("no SKILL.md found in %s" % src)
            if len(candidates) > 1:
                if args.skill:
                    hits = [c for c in candidates if c.name == args.skill]
                    if not hits:
                        die("skill %r not found in repo (available: %s)" % (
                            args.skill, ", ".join(c.name for c in candidates)))
                    selected = hits
                elif args.all:
                    selected = candidates
                else:
                    avail = ", ".join(c.name for c in candidates)
                    die("multiple skills found in %s (%s). Pass --skill <name> to pick one, or --all to add all."
                        % (src, avail))
            else:
                selected = candidates
        else:
            source_dir = Path(src).expanduser().resolve()
            if not source_dir.is_dir():
                die("not a directory: %s" % source_dir)
            if not is_skill_dir(source_dir):
                die("no SKILL.md in %s" % source_dir)
            selected = [source_dir]

        existing_by_name = {s["name"]: s for s in repo_skills(repo)}
        plan = []
        for sdir in selected:
            if args.name and len(selected) == 1:
                raw_name = args.name
            elif tmp and same_path(sdir, tmp):
                raw_name = _repo_name_from_url(src)
            else:
                raw_name = sdir.name  # directory name wins: never rename a skill
            name = re.sub(r"[^A-Za-z0-9._-]", "-", raw_name.strip())
            category = args.category
            dest = repo / "skills" / (category + "/" if category else "") / name
            existing = existing_by_name.get(name)
            if existing and not args.force:
                die("%s already exists in the repo at %s (use --force to replace; old copy goes to %s/trash/)"
                    % (name, existing["rel"], STATE_DIR))
            plan.append({"name": name, "source_dir": sdir, "dest": dest, "existing": existing})

        for item in plan:
            ctx.log("add %s -> %s [%s]" % (item["name"], item["dest"], "APPLY" if ctx.apply else "DRY-RUN"))
            if item["existing"]:
                ctx.log("  replacing existing copy at %s (moved to %s/trash/)" % (item["existing"]["rel"], STATE_DIR))

        will_push = bool(ctx.config.get("auto_push", True)) and not bool(getattr(args, "no_push", False))
        if not ctx.apply:
            if will_push and git_has_remote(repo):
                ctx.log("would auto-push to GitHub remote after commit (pass --no-push to skip)")
            ctx.log("dry-run complete. Re-run with --apply.")
            if ctx.json:
                ctx.emit({
                    "apply": False,
                    "will_push": will_push and git_has_remote(repo),
                    "items": [{"name": i["name"], "dest": str(i["dest"]), "replacing": bool(i["existing"])} for i in plan],
                })
            return

        stamp = time.strftime("%Y%m%d-%H%M%S")
        added_names = []
        for item in plan:
            if item["existing"]:
                old_path = Path(item["existing"]["path"])
                if old_path.exists():
                    trash = _unique_path(repo / STATE_DIR / "trash" / stamp, item["name"])
                    trash.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(old_path), str(trash))
            elif item["dest"].exists():
                trash = _unique_path(repo / STATE_DIR / "trash" / stamp, item["name"])
                trash.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item["dest"]), str(trash))
            copy_tree(item["source_dir"], item["dest"], keep_git=False)
            added_names.append(item["name"])
            if is_url:
                ctx.config.setdefault("sources", {})[item["name"]] = src

        if is_url or not (repo / CONFIG_NAME).is_file():
            ctx.save_config()
        ctx.ensure_scaffolding()
        git_commit(repo, "add: %s" % ", ".join(added_names))

        created = errs = 0
        if not args.no_link:
            added_skills = [s for s in repo_skills(repo) if s["name"] in set(added_names)]
            created, errs = link_all(ctx, added_skills, ctx.enabled_targets(create=True))
            ctx.log("linked %d, errors %d" % (created, errs))

        sync_res = None
        if will_push:
            sync_res = sync_push(ctx, repo, allow_secrets=bool(getattr(args, "allow_secrets", False)))
            _log_sync_result(ctx, sync_res)
        else:
            ctx.log("done (auto-push disabled). Run 'skillkit push --apply' to publish.")

        if ctx.json:
            ctx.emit({
                "apply": True,
                "added": added_names,
                "linked": created,
                "errors": errs,
                "sync": sync_res,
            })
    finally:
        _cleanup_temp_dir(tmp)


def cmd_update(ctx):
    args = ctx.args
    repo = ctx.require_repo()
    sources = ctx.config.get("sources", {})
    names = args.names or sorted(sources)
    if not names:
        die("no recorded upstream sources; use 'skillkit add <url>' first")

    repo_by_name = {s["name"]: s for s in repo_skills(repo)}
    updated, skipped, failed = [], [], []
    will_push = bool(ctx.config.get("auto_push", True)) and not bool(getattr(args, "no_push", False))

    for name in names:
        url = sources.get(name)
        if not url:
            ctx.log("skip %s: no recorded source" % name)
            skipped.append({"name": name, "reason": "no recorded source"})
            continue
        sk = repo_by_name.get(name)
        if not sk:
            ctx.log("skip %s: not in repo" % name)
            skipped.append({"name": name, "reason": "not in repo"})
            continue
        dest = Path(sk["path"])
        ctx.log("update %s <- %s [%s]" % (name, url, "APPLY" if ctx.apply else "DRY-RUN"))
        if not ctx.apply:
            continue
        tmp = None
        staging = None
        try:
            tmp = Path(tempfile.mkdtemp(prefix="skillkit-upd-"))
            rc, out, err = sh(["git", "clone", "--depth", "1", url, str(tmp)])
            if rc != 0:
                msg = err or out
                ctx.log("  ! clone failed: %s" % msg)
                failed.append({"name": name, "reason": msg})
                continue
            cands = _discover_skills_in_tree(tmp)
            if not cands:
                ctx.log("  ! no SKILL.md upstream")
                failed.append({"name": name, "reason": "no SKILL.md upstream"})
                continue
            chosen = next((c for c in cands if c.name == name), cands[0])
            # Copy to sibling staging dir first so the existing skill stays intact on copy error
            staging = dest.parent / (".skillkit-staging-%s-%d" % (name, int(time.time())))
            copy_tree(chosen, staging, keep_git=False)
            trash = _unique_path(repo / STATE_DIR / "trash" / time.strftime("%Y%m%d-%H%M%S"), name)
            trash.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dest), str(trash))
            shutil.move(str(staging), str(dest))
            staging = None
            updated.append(name)
            ctx.log("  updated")
        except (OSError, shutil.Error) as exc:
            ctx.log("  ! update failed: %s" % exc)
            failed.append({"name": name, "reason": str(exc)})
        finally:
            _cleanup_temp_dir(tmp)
            if staging and staging.exists():
                trash_st = _unique_path(repo / STATE_DIR / "trash" / time.strftime("%Y%m%d-%H%M%S"), name + "-staging")
                trash_st.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.move(str(staging), str(trash_st))
                except OSError:
                    pass

    sync_res = None
    created = errs = 0
    if not ctx.apply:
        if will_push and git_has_remote(repo):
            ctx.log("would auto-push to GitHub remote after commit (pass --no-push to skip)")
        ctx.log("dry-run complete. Re-run with --apply.")
    else:
        if updated:
            git_commit(repo, "update: %s" % ", ".join(updated))
            refreshed = [s for s in repo_skills(repo) if s["name"] in set(updated)]
            created, errs = link_all(ctx, refreshed, ctx.enabled_targets(create=True))
            if will_push:
                sync_res = sync_push(ctx, repo, allow_secrets=bool(getattr(args, "allow_secrets", False)))
                _log_sync_result(ctx, sync_res)
            else:
                ctx.log("done (auto-push disabled). Run 'skillkit push --apply' to publish.")

    if ctx.json:
        ctx.emit({
            "apply": ctx.apply,
            "updated": updated,
            "skipped": skipped,
            "failed": failed,
            "linked": created,
            "errors": errs,
            "sync": sync_res,
        })


def cmd_remove(ctx):
    args = ctx.args
    repo = ctx.require_repo()
    names = args.names
    skills = {s["name"]: s for s in repo_skills(repo)}
    live_links = discover_our_links(ctx, repo)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    will_push = bool(ctx.config.get("auto_push", True)) and not bool(getattr(args, "no_push", False))
    removed, skipped = [], []

    for name in names:
        sk = skills.get(name)
        if not sk:
            ctx.log("skip %s: not in repo" % name)
            skipped.append(name)
            continue
        ctx.log("remove %s [%s]  (links removed, payload MOVED to %s/trash/ — nothing is deleted)"
                % (name, "APPLY" if ctx.apply else "DRY-RUN", STATE_DIR))
        matching_links = [e for e in live_links if e["name"] == name]
        if not ctx.apply:
            for entry in matching_links:
                ctx.log("  would unlink %s" % entry["path"])
            ctx.log("  would move %s -> %s/trash/<timestamp>/%s" % (sk["path"], STATE_DIR, name))
            continue
        # 1) unlink every agent dir that points at it (from filesystem + state)
        for entry in matching_links:
            link = Path(entry["path"])
            if is_skill_link(link):
                remove_link(link)
                ctx.log("  unlinked %s" % link)
            ctx.state["links"] = [
                e for e in ctx.state.get("links", [])
                if _norm_path(e["path"]) != _norm_path(link)
            ]
        # 2) move the payload to .skill-manager/trash (never delete)
        trash = _unique_path(repo / STATE_DIR / "trash" / stamp, name)
        trash.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(sk["path"]), str(trash))
        ctx.config.get("sources", {}).pop(name, None)
        removed.append({"name": name, "trash": str(trash)})
        ctx.log("  moved to %s" % trash)

    sync_res = None
    if not ctx.apply:
        if will_push and git_has_remote(repo):
            ctx.log("would auto-push to GitHub remote after commit (pass --no-push to skip)")
        ctx.log("dry-run complete. Re-run with --apply.")
    elif removed:
        ctx.save_config()
        ctx.save_state()
        git_commit(repo, "remove: %s" % ", ".join(r["name"] for r in removed))
        if will_push:
            sync_res = sync_push(ctx, repo, allow_secrets=bool(getattr(args, "allow_secrets", False)))
            _log_sync_result(ctx, sync_res)
        ctx.log("done. Recover from %s/trash/%s/ if this was a mistake." % (STATE_DIR, stamp))

    if ctx.json:
        ctx.emit({"apply": ctx.apply, "removed": removed, "skipped": skipped, "sync": sync_res})


def _tree_files(path):
    """Collect files and link entries under `path` without ever descending into symlinks/junctions."""
    out = []
    for cur, _, files, link_dirs in _safe_walk(path):
        for name in sorted(files):
            out.append(Path(cur) / name)
        for ld in sorted(link_dirs):
            out.append(Path(cur) / ld)
    return out


def _trash_entries(root):
    """List top-level trashed items under <repo>/.skill-manager/trash/<ts>/."""
    rows = []
    for tsdir in sorted(root.iterdir()):
        if not tsdir.is_dir():
            continue
        for child in sorted(tsdir.iterdir()):
            # Handles both <ts>/<skill> and <ts>/<env>/<skill@target>
            if child.is_dir() and child.name in ("local", "windows"):
                for sub in sorted(child.iterdir()):
                    rows.append({
                        "timestamp": tsdir.name, "env": child.name, "name": sub.name,
                        "path": sub, "files": len(_tree_files(sub)) if sub.is_dir() else 1,
                    })
            else:
                rows.append({
                    "timestamp": tsdir.name, "env": "", "name": child.name,
                    "path": child, "files": len(_tree_files(child)) if child.is_dir() else 1,
                })
    return rows


def cmd_trash(ctx):
    """List or purge the trash. Purging DELETES files, so it is gated twice."""
    repo = ctx.require_repo()
    root = repo / STATE_DIR / "trash"
    args = ctx.args
    if not root.is_dir():
        ctx.emit({"trash_root": str(root), "items": []}, "trash is empty (%s)" % root)
        return
    if not args.purge:
        entries = _trash_entries(root)
        rows = [
            {"timestamp": e["timestamp"], "env": e["env"], "name": e["name"],
             "path": str(e["path"]), "files": e["files"]}
            for e in entries
        ]
        lines = []
        for r in rows:
            lines.append("%-16s %-30s %3d file(s)  %s" % (r["timestamp"], r["name"], r["files"], r["path"]))
        if not rows:
            lines.append("trash is empty")
        lines.append("\nNothing deleted. 'skillkit trash --purge <name>' lists exact files and requires")
        lines.append("both --confirm-delete and an explicit yes before deleting anything one path at a time.")
        ctx.emit({"trash_root": str(root), "items": rows}, "\n".join(lines))
        return

    # ---- purge: two gates, entry-level matching only, one unlink per file --
    needle = args.purge
    entries = _trash_entries(root)
    if needle == "all":
        victims = [p for p in sorted(root.iterdir())]
    else:
        victims = [
            e["path"] for e in entries
            if e["name"] == needle or e["timestamp"] == needle
            or ("%s/%s" % (e["timestamp"], e["name"])) == needle
        ]
        # Also allow exact timestamp dir match when it contains multiple entries
        ts_exact = root / needle
        if ts_exact.is_dir() and ts_exact not in victims:
            victims = [ts_exact]
    if not victims:
        die("no trash entry matches %r (run 'skillkit trash' to see exact entry names/timestamps)" % needle)

    files = []
    for v in victims:
        files.extend([v] if v.is_file() or is_skill_link(v) else _tree_files(v))
    ctx.log("About to DELETE %d file(s) from %d trash entr(ies):" % (len(files), len(victims)))
    for f in files[:200]:
        ctx.log("  " + str(f))
    if len(files) > 200:
        ctx.log("  ... %d more" % (len(files) - 200))
    ctx.log("")
    ctx.log("This violates the user's default 'no batch delete' rule, so it needs an explicit OK.")
    if not args.confirm_delete:
        ctx.log("Refusing: re-run with --confirm-delete after the user confirms.")
        if ctx.json:
            ctx.emit({"deleted": 0, "refused": True, "files": [str(f) for f in files]})
        return
    if not ctx.yes:
        try:
            answer = input("Type DELETE to confirm: ").strip()
        except EOFError:
            answer = ""
        if answer != "DELETE":
            ctx.log("aborted, nothing deleted")
            if ctx.json:
                ctx.emit({"deleted": 0, "aborted": True})
            return
    removed = 0
    for f in files:
        try:
            if is_skill_link(f):
                if remove_link(f):
                    removed += 1
            else:
                _unlink_file(f)
                removed += 1
        except OSError as exc:
            ctx.log("  ! %s: %s" % (f, exc))
    for v in sorted(victims, key=lambda x: len(str(x)), reverse=True):
        if v.is_dir() and not is_skill_link(v):
            dirs_to_prune = [cur for cur, _, _, _ in _safe_walk(v)]
            for d in reversed(dirs_to_prune):
                try:
                    os.rmdir(d)
                except OSError:
                    pass
    # Prune now-empty timestamp folders under trash root (junction-safe)
    for tsdir in sorted(root.iterdir()):
        if tsdir.is_dir() and not is_skill_link(tsdir):
            dirs_to_prune = [cur for cur, _, _, _ in _safe_walk(tsdir)]
            for d in reversed(dirs_to_prune):
                try:
                    os.rmdir(d)
                except OSError:
                    pass
    ctx.log("deleted %d file(s); empty directories pruned." % removed)
    if ctx.json:
        ctx.emit({"deleted": removed, "victims": [str(v) for v in victims]})


def cmd_restore(ctx):
    repo = ctx.require_repo()
    skills = repo_skills(repo)
    targets = ctx.enabled_targets(create=True)
    ctx.log("restore %d skill(s) into %d target dir(s) [%s]" % (
        len(skills), len(targets), "APPLY" if ctx.apply else "DRY-RUN"))
    for tr in targets:
        ctx.log("  %-13s %-8s %s%s" % (
            tr["target"]["id"], tr["env"], tr["root"], "" if tr["root"].is_dir() else " (will create)"))
    if not ctx.apply:
        ctx.log("\nDry-run complete. Re-run with --apply.")
        if ctx.json:
            ctx.emit({"apply": False, "skills": len(skills),
                      "targets": [{"id": tr["target"]["id"], "env": tr["env"], "path": str(tr["root"])} for tr in targets]})
        return
    created, errs = link_all(ctx, skills, targets)
    ctx.record_location(repo)
    ctx.log("linked %d, errors %d" % (created, errs))
    if ctx.json:
        ctx.emit({"apply": True, "skills": len(skills), "linked": created, "errors": errs})


def cmd_install(ctx):
    """Link skill-manager itself into every detected Agent's default skill directory.

    Does not require skills-repo to exist yet: this is the one-command bootstrap
    so users never have to manually run ln -s / mklink /J for each Agent.
    """
    args = ctx.args
    src = SELF_SKILL_ROOT
    if not is_skill_dir(src):
        die("skill-manager SKILL.md not found at %s" % src)
    meta, _ = read_frontmatter(src / SKILL_FILE)
    skill_name = (meta.get("name") or src.name or "skill-manager").strip()
    if args.to:
        targets = ctx.targets_by_id([x.strip() for x in args.to.split(",") if x.strip()],
                                    include_windows=bool(args.include_windows))
    else:
        targets = ctx.enabled_targets(create=True)
    mode = args.mode or "auto"
    ctx.log("install %s (%s) into %d target dir(s) [%s]" % (
        skill_name, src, len(targets), "APPLY" if ctx.apply else "DRY-RUN"))
    for note in ctx.environment_notes:
        ctx.log("  note: " + note)

    actions = []
    created = skipped = errs = 0
    for tr in targets:
        root = tr["root"]
        link = root / skill_name
        if link_points_to(link, src):
            ctx.log("  = %-15s %-8s %s (already linked)" % (tr["target"]["id"][:15], tr["env"], link))
            actions.append({"target_id": tr["target"]["id"], "env": tr["env"], "path": str(link), "status": "already_linked"})
            skipped += 1
            continue
        if not is_skill_link(link) and same_path(link, src):
            ctx.log("  = %-15s %-8s %s (already here)" % (tr["target"]["id"][:15], tr["env"], link))
            actions.append({"target_id": tr["target"]["id"], "env": tr["env"], "path": str(link), "status": "already_here"})
            skipped += 1
            continue
        if link.exists() or is_skill_link(link):
            if not is_skill_link(link):
                ctx.log("  ! %-13s %-8s %s is a REAL directory -> left untouched" % (tr["target"]["id"], tr["env"], link))
                actions.append({"target_id": tr["target"]["id"], "env": tr["env"], "path": str(link), "status": "blocked_real_dir"})
                errs += 1
                continue
            if not is_self_skill(link):
                ctx.log("  ! %-13s %-8s %s points elsewhere -> left untouched" % (tr["target"]["id"], tr["env"], link))
                actions.append({"target_id": tr["target"]["id"], "env": tr["env"], "path": str(link), "status": "blocked_other_link"})
                errs += 1
                continue
        if not ctx.apply:
            ctx.log("  + %-13s %-8s %s -> %s" % (tr["target"]["id"], tr["env"], link, src))
            actions.append({"target_id": tr["target"]["id"], "env": tr["env"], "path": str(link), "status": "would_link"})
            continue
        try:
            root.mkdir(parents=True, exist_ok=True)
            if is_skill_link(link):
                remove_link(link)
            kind = make_link(src, link, mode=mode, env=tr["env"])
            ctx.log("  + %-13s %-8s %s (%s)" % (tr["target"]["id"], tr["env"], link, kind))
            actions.append({"target_id": tr["target"]["id"], "env": tr["env"], "path": str(link), "status": "linked", "kind": kind})
            created += 1
        except (RuntimeError, OSError, shutil.Error) as exc:
            ctx.log("  ! %-13s %-8s %s: %s" % (tr["target"]["id"], tr["env"], link, exc))
            actions.append({"target_id": tr["target"]["id"], "env": tr["env"], "path": str(link), "status": "error", "error": str(exc)})
            errs += 1

    if ctx.apply:
        ctx.log("\ninstalled: linked %d, already ok %d, errors %d" % (created, skipped, errs))
        ctx.log("Open a new Agent session and say: '帮我初始化 skills-repo' (or run 'skillkit init').")
    else:
        ctx.log("\nDry-run complete. Re-run with --apply to install into these Agent directories.")
    if ctx.json:
        ctx.emit({
            "apply": ctx.apply,
            "skill": skill_name,
            "source": str(src),
            "linked": created,
            "skipped": skipped,
            "errors": errs,
            "actions": actions,
        })


def cmd_push(ctx):
    args = ctx.args
    repo = ctx.require_repo()
    if not git_is_repo(repo):
        die("%s is not a git repository" % repo)
    if not git_has_remote(repo):
        die("no git remote. Add one: git -C %s remote add origin git@github.com:<you>/skills-repo.git" % repo)
    msg = args.message or "sync: update skills"
    dirty = git_dirty(repo)
    findings = scan_secrets(repo)
    if findings and not bool(getattr(args, "allow_secrets", False)):
        ctx.log("BLOCKED: potential secrets detected in skills-repo:")
        for f in findings[:10]:
            ctx.log("  ! %s: %s" % (f["reason"], f["rel"]))
        ctx.log("Remove the secrets before pushing (or pass --allow-secrets if these are false positives).")
        if ctx.json:
            ctx.emit({"apply": ctx.apply, "status": "blocked", "findings": findings})
        sys.exit(2)
    if not ctx.apply:
        if dirty:
            ctx.log("would: git add -A && git commit -m %r && git push" % msg)
        else:
            ctx.log("would: git push")
        ctx.log("dry-run complete. Re-run with --apply.")
        if ctx.json:
            ctx.emit({"apply": False, "dirty": dirty, "message": msg})
        return
    committed = False
    if dirty:
        committed = git_commit(repo, msg)
    res = sync_push(ctx, repo, allow_secrets=bool(getattr(args, "allow_secrets", False)))
    _log_sync_result(ctx, res)
    if ctx.json:
        ctx.emit({"apply": True, "committed": committed, "sync": res})
    if res.get("status") not in ("ok",):
        sys.exit(1)


def cmd_pull(ctx):
    repo = ctx.require_repo()
    if not ctx.apply:
        ctx.log("would: git pull --rebase --autostash && prune dangling links && relink all targets")
        ctx.log("dry-run complete. Re-run with --apply.")
        if ctx.json:
            ctx.emit({"apply": False})
        return
    rc, out, err = git(repo, "pull", "--rebase", "--autostash")
    pull_ok = (rc == 0)
    ctx.log("pull %s%s" % ("ok" if pull_ok else "FAILED", "" if pull_ok else ": " + (err or out)))
    targets = ctx.enabled_targets(create=True)
    pruned = prune_dangling_links(ctx, repo, targets=targets, apply=True)
    skills = repo_skills(repo)
    created, errs = link_all(ctx, skills, targets)
    ctx.log("relinked %d, pruned %d dangling link(s), errors %d" % (created, len(pruned), errs))
    if ctx.json:
        ctx.emit({"apply": True, "pull_ok": pull_ok, "detail": out if pull_ok else (err or out),
                  "relinked": created, "pruned": [p["path"] for p in pruned], "errors": errs})
    if not pull_ok:
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    # defaults are SUPPRESS so a value given before the subcommand is not
    # overwritten by the subparser's default; main() fills the gaps.
    S = argparse.SUPPRESS
    common.add_argument("--repo", default=S, help="path to skills-repo (default <home>/skills-repo)")
    common.add_argument("--json", action="store_true", default=S, help="machine-readable JSON output")
    common.add_argument("--apply", action="store_true", default=S, help="execute instead of dry-run")
    common.add_argument("-y", "--yes", action="store_true", default=S, help="assume yes / non-interactive")
    common.add_argument("-v", "--verbose", action="store_true", default=S)
    common.add_argument("--include-windows", action="store_true", default=S,
                        help="also consider the CURRENT Windows user's dirs when running inside WSL")
    common.add_argument("--allow-cross-user", action="store_true", default=S,
                        help="allow touching Windows profile even when running as root")
    common.add_argument("--no-discover", action="store_true", default=S,
                        help="disable active dynamic discovery of unlisted agent skill directories")

    p = argparse.ArgumentParser(prog="skillkit", description="one-repo, symlink-first skill manager",
                                parents=[common])
    p.add_argument("--version", action="version", version="skillkit " + VERSION)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("install", parents=[common],
                        help="link skill-manager itself into every detected Agent's default skill dir")
    sp.add_argument("--to", help="comma separated target ids (default: all detected agents + universal hubs)")
    sp.add_argument("--mode", choices=["auto", "symlink", "junction", "copy"])
    sp.set_defaults(func=cmd_install)

    sp = sub.add_parser("init", parents=[common], help="bootstrap skills-repo + migrate existing skills + link")
    sp.add_argument("--repo-url", help="git remote URL to attach (skips gh)")
    sp.add_argument("--create-remote", action="store_true", help="create <you>/skills-repo via gh (private)")
    sp.add_argument("--copy", action="store_true",
                    help="copy instead of move the originals (leaves original dirs unlinked)")
    sp.add_argument("--no-dedupe", action="store_true", help="keep differing duplicate copies untouched")
    sp.add_argument("--prefer", choices=["newest", "majority"], default="newest",
                    help="conflict policy when the same skill differs between agents (default: newest)")
    sp.add_argument("--no-adopt-self", action="store_true",
                    help="keep skill-manager outside skills-repo (do not copy it into skills/)")
    sp.add_argument("--push", action="store_true", help="push after importing")
    sp.add_argument("--no-push", action="store_true", help="skip automatic push to GitHub remote")
    sp.add_argument("--allow-secrets", action="store_true", help="allow push even if secret scanner warns")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("scan", parents=[common], help="inventory skills across all agent dirs")
    sp.add_argument("--env", default="local", choices=["local", "windows", "all"])
    sp.set_defaults(func=cmd_scan)

    sp = sub.add_parser("repo", parents=[common], help="show / set / forget which local skills-repo this machine uses")
    sp.add_argument("--set", dest="set_path", help="record this path as the repo for this machine")
    sp.add_argument("--forget", action="store_true", help="drop the recorded location")
    sp.set_defaults(func=cmd_repo)

    sp = sub.add_parser("targets", parents=[common],
                        help="show detected agent skill directories (static + custom + auto-discovered)")
    sp.add_argument("--add", dest="add_target", nargs=2, metavar=("ID", "PATH"),
                    help="persist a custom agent skill dir in skill-manager.json (relative to HOME)")
    sp.add_argument("--remove", dest="remove_target", metavar="ID",
                    help="remove a custom agent skill dir from skill-manager.json")
    sp.set_defaults(func=cmd_targets)

    sp = sub.add_parser("list", parents=[common], help="list repo skills and their links")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("status", parents=[common], help="repo + link + sync status")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("doctor", parents=[common], help="validate skills, links, secrets, git")
    sp.add_argument("--fix", action="store_true", help="repair missing/stale links and prune dangling links (use with --apply)")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("add", parents=[common], help="install a skill (local dir or git URL) into skills-repo and sync")
    sp.add_argument("source")
    sp.add_argument("--name", help="override skill directory name")
    sp.add_argument("--skill", help="pick one skill by name when a git repo contains multiple skills")
    sp.add_argument("--all", action="store_true", help="add all skills when a git repo contains multiple skills")
    sp.add_argument("--category", help="optional subfolder under skills/")
    sp.add_argument("--force", action="store_true", help="replace existing skill (old copy moves to trash)")
    sp.add_argument("--no-link", action="store_true", help="do not create agent links")
    sp.add_argument("--no-push", action="store_true", help="skip automatic push to GitHub remote")
    sp.add_argument("--allow-secrets", action="store_true", help="allow push even if secret scanner warns")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("update", parents=[common], help="re-fetch skills recorded with a git source and sync")
    sp.add_argument("names", nargs="*")
    sp.add_argument("--no-push", action="store_true", help="skip automatic push to GitHub remote")
    sp.add_argument("--allow-secrets", action="store_true", help="allow push even if secret scanner warns")
    sp.set_defaults(func=cmd_update)

    sp = sub.add_parser("link", parents=[common], help="create links for repo skills")
    sp.add_argument("names", nargs="*")
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--to", help="comma separated target ids, e.g. agents,claude,codex,pi,antigravity,kimi,qwen,codebuddy "
                                 "(run 'skillkit targets' for the full list of 73)")
    sp.add_argument("--mode", choices=["auto", "symlink", "junction", "copy"])
    sp.set_defaults(func=cmd_link)

    sp = sub.add_parser("unlink", parents=[common], help="remove links (payload stays in skills-repo)")
    sp.add_argument("names", nargs="*")
    sp.add_argument("--all", action="store_true", help="unlink every skill managed by this repo")
    sp.set_defaults(func=cmd_unlink)

    sp = sub.add_parser("remove", parents=[common], help="unlink + move a skill to trash + sync (never deletes)")
    sp.add_argument("names", nargs="+")
    sp.add_argument("--no-push", action="store_true", help="skip automatic push to GitHub remote")
    sp.add_argument("--allow-secrets", action="store_true", help="allow push even if secret scanner warns")
    sp.set_defaults(func=cmd_remove)

    sp = sub.add_parser("trash", parents=[common],
                        help="list the trash; --purge deletes (needs --confirm-delete + typed confirmation)")
    sp.add_argument("--purge", help="exact entry name, timestamp, or 'all' to purge")
    sp.add_argument("--confirm-delete", action="store_true", help="required gate for any deletion")
    sp.set_defaults(func=cmd_trash)

    sp = sub.add_parser("restore", parents=[common], help="rebuild every link from skills-repo (new machine)")
    sp.set_defaults(func=cmd_restore)

    sp = sub.add_parser("push", parents=[common], help="commit + push skills-repo (secret-checked)")
    sp.add_argument("-m", "--message")
    sp.add_argument("--allow-secrets", action="store_true", help="allow push even if secret scanner warns")
    sp.set_defaults(func=cmd_push)

    sp = sub.add_parser("pull", parents=[common], help="git pull --rebase + prune dangling links + relink")
    sp.set_defaults(func=cmd_pull)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    for key, default in (("repo", None), ("json", False), ("apply", False), ("yes", False),
                         ("verbose", False), ("include_windows", False), ("allow_cross_user", False),
                         ("no_discover", False)):
        if not hasattr(args, key):
            setattr(args, key, default)
    ctx = Context(args)
    if args.cmd not in ("install", "init", "targets", "scan", "repo"):
        if not ctx.repo:
            die("no skills-repo found. Pass --repo PATH, set SKILLKIT_REPO, or run 'skillkit init'.")
    try:
        args.func(ctx)
    except KeyboardInterrupt:
        die("interrupted", 130)


if __name__ == "__main__":
    main()
