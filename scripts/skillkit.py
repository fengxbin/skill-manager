#!/usr/bin/env python3
"""skillkit — one-repo, symlink-first skill manager for multi-agent setups.

Design contract (see ../references/design.md):
  * The Git repo is the SINGLE SOURCE OF TRUTH. Real files live only there.
  * Every agent's skill directory receives a *link* (symlink / NTFS junction),
    never a copy, so editing the repo changes every agent at once (zero drift).
  * Every mutating command is dry-run by default and only writes with --apply.
  * Nothing is ever deleted recursively. Removals are moves into <repo>/.trash/.

Python 3.8+, standard library only. Works on Linux, macOS, Windows and WSL.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

VERSION = "1.0.0"
DEFAULT_REPO = "~/skills-repo"
CONFIG_NAME = "skill-manager.json"
STATE_DIR = ".skill-manager"
TRASH_DIR = ".trash"
SKILL_FILE = "SKILL.md"

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
    ("antigravity", "Google Antigravity / Antigravity CLI", [".gemini/config/skills", ".antigravity/skills"], "auto", "海外", "doc"),
    ("copilot", "GitHub Copilot CLI", [".copilot/skills"], "auto", "海外", "doc"),
    ("cursor", "Cursor", [".cursor/skills"], "auto", "海外", "doc"),
    ("windsurf", "Windsurf (Codeium)", [".codeium/windsurf/skills", ".windsurf/skills"], "auto", "海外", "doc"),
    ("opencode", "opencode", [".config/opencode/skill", ".config/opencode/skills"], "auto", "海外", "doc"),
    ("amp", "Amp (Sourcegraph)", [".config/amp/skills"], "auto", "海外", "doc"),
    ("crush", "Crush (Charm)", [".config/crush/skills"], "auto", "海外", "doc"),
    ("goose", "Goose (Block)", [".config/goose/skills"], "auto", "海外", "doc"),
    ("devin", "Devin for Terminal", [".config/devin/skills"], "auto", "海外", "doc"),
    ("droid", "Factory Droid", [".factory/skills"], "auto", "海外", "doc"),
    ("augment", "Augment Code", [".augment/skills"], "auto", "海外", "doc"),
    ("continue", "Continue", [".continue/skills"], "auto", "海外", "doc"),
    ("cline", "Cline", [".cline/skills"], "auto", "海外", "probable"),
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
    ("codebuddy", "CodeBuddy / WorkBuddy（腾讯）", [".codebuddy/skills"], "auto", "国内", "doc"),
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


def is_junction(p):
    p = Path(p)
    if not p.is_dir() or p.is_symlink():
        return False
    if os.name == "nt":
        try:
            import ctypes  # noqa: F401  (attribute probe below)
            FILE_ATTRIBUTE_REPARSE_POINT = 0x400
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(p))
            return bool(attrs != -1 and attrs & FILE_ATTRIBUTE_REPARSE_POINT)
        except Exception:
            return False
    # Under WSL a junction is surfaced as a symlink, so os.path.islink already
    # answers the question; nothing else to probe here.
    return False


def link_points_to(link, target):
    """True when `link` is a live link resolving to `target` (symlink or junction)."""
    link, target = Path(link), Path(target)
    if not link.exists() and not link.is_symlink():
        return False
    try:
        if link.is_symlink():
            return Path(os.path.realpath(link)).resolve() == target.resolve()
        return os.path.samefile(link, target) and Path(os.path.realpath(link)).resolve() == target.resolve()
    except OSError:
        return False


def make_link(target, link, mode="auto", env="local"):
    """Create a link. Returns the created kind ('symlink'|'junction'|'copy') or raises."""
    target, link = Path(target), Path(link)
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        raise RuntimeError("path already exists: %s" % link)

    if mode == "copy":
        shutil.copytree(str(target), str(link))
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
        if rc != 0 and (Path(link).exists() or Path(link).is_symlink()) and link_points_to(link, target):
            rc = 0  # cmd reported failure but the junction is live (encoding/UNC noise)
        if rc == 0:
            # drvfs/9p visibility can lag by a moment; rc==0 means it was created
            for _ in range(15):
                if Path(link).exists() or Path(link).is_symlink():
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

    if mode == "auto":
        if Path(link).exists() or Path(link).is_symlink():
            raise RuntimeError("path already exists after link attempt: %s" % link)
        shutil.copytree(str(target), str(link))
        print("  ! fell back to COPY for %s (zero-drift lost): %s" % (link, "; ".join(errors)))
        return "copy"
    raise RuntimeError("; ".join(errors) or "link creation failed")


def remove_link(link, kind=None):
    """Remove a link (never the payload). Returns True on success."""
    link = Path(link)
    if link.is_symlink():
        os.unlink(str(link))
        return True
    if not link.exists():
        return True
    if os.name == "nt":
        try:
            os.rmdir(str(link))  # removes a junction, leaves its target intact
            return True
        except OSError:
            return False
    if is_wsl() and windows_visible(link):
        rc, _, _ = sh(["cmd.exe", "/c", "rmdir", to_win_path(link)])
        if rc == 0:
            return True
    try:
        os.rmdir(str(link))
        return True
    except OSError:
        pass
    # last resort: refuse to touch a real directory
    return False


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


def copy_tree(src, dst):
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(src), str(dst), ignore=shutil.ignore_patterns(*IGNORE_DIR_NAMES - {".git"}))
    return dst


def is_skill_dir(p):
    return (Path(p) / SKILL_FILE).is_file()


def is_skill_link(p):
    p = Path(p)
    return p.is_symlink() or is_junction(p)


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
        self.repo_source = "none"
        self.repo = self._resolve_repo()
        self.config = self._load_config()
        self.state = self._load_state()

    # -- repo -------------------------------------------------------------
    def location_file(self):
        """Pointer file that remembers where the repo lives on THIS machine.

        Follows the XDG habit (~/.config/skillkit/location) and works on Windows
        too, because Path.home() exists everywhere. Machine-specific by nature,
        so it is never committed to the repo.
        """
        return self.home / ".config" / "skillkit" / "location"

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
                if cand.is_dir() and ((cand / CONFIG_NAME).is_file() or (cand / (STATE_DIR + "/state.json")).is_file()
                                      or (cand / "skills").is_dir()):
                    self.repo_source = "recorded location (%s)" % loc
                    return cand

        for cand in [self.home / "skills-repo", Path(DEFAULT_REPO).expanduser(), Path.cwd()]:
            cand = cand.resolve()
            if (cand / CONFIG_NAME).is_file() or (cand / (STATE_DIR + "/state.json")).is_file():
                self.repo_source = "auto-detected (%s)" % cand
                return cand
            if (cand / "skills").is_dir() and (cand / ".git").exists():
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
            print("  ! could not record repo location (%s): %s" % (loc, exc))
            return False

    def require_repo(self):
        if not self.repo:
            die("no skills repo found. Pass --repo PATH, set SKILLKIT_REPO, run 'skillkit init' "
                "(it remembers the location), or see 'skillkit repo --help'.")
        return self.repo

    # -- config / state ---------------------------------------------------
    def _load_config(self):
        cfg = {
            "version": 1,
            "targets": None,
            "link_mode": "auto",
            "category_layout": True,
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
        return self.repo / STATE_DIR / "state.json" if self.repo else None

    def _load_state(self):
        st = {"version": 1, "links": [], "backups": [], "environments": {}}
        p = self._state_path()
        if p and p.is_file():
            try:
                st.update(json.loads(p.read_text(encoding="utf-8")))
            except ValueError:
                pass
        return st

    def save_state(self):
        p = self._state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.ensure_scaffolding()

    # -- environments -----------------------------------------------------
    def windows_home(self):
        """The CURRENT Windows user's profile as seen from WSL.

        Only the same user is considered: cross-user operation is refused unless
        --allow-cross-user is passed explicitly (see windows_home_guard()).
        """
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
        """Return (profile, reason) — profile is None when it must not be touched."""
        wh = self.windows_home()
        if not wh:
            return None, "no Windows profile detected"
        if getattr(self.args, "allow_cross_user", False):
            return wh, ""
        me, them = self.current_user(), wh.name
        if me and them and me.lower() != them.lower():
            return None, ("Windows profile '%s' is not the current user '%s'; "
                          "cross-user operation refused (pass --allow-cross-user to override)" % (them, me))
        return wh, ""

    def env_homes(self, include_windows=False):
        homes = {"local": self.home}
        if include_windows:
            wh, reason = self.windows_home_guard()
            if wh:
                homes["windows"] = wh
            elif reason:
                self.environment_notes.append(reason)
        return homes

    # -- target roots -----------------------------------------------------
    def candidate_roots(self, target, home):
        return [Path(home) / rel for rel in target.get("relpaths") or [target["relpath"]]]

    def target_roots(self, target, env, home, create=False):
        """Existing candidate directories for a target (all of them).

        With create=True, a "always" bind target gets its primary directory
        created when none of the candidates exists yet.
        """
        roots = [r for r in self.candidate_roots(target, home) if r.is_dir()]
        if roots:
            return roots
        if create and target["bind"] == "always":
            return [self.candidate_roots(target, home)[0]]
        return []

    def _within(self, path, home):
        try:
            return Path(path).resolve().is_relative_to(Path(home).resolve())
        except AttributeError:  # py3.8
            try:
                Path(path).resolve().relative_to(Path(home).resolve())
                return True
            except ValueError:
                return False
        except ValueError:
            return False

    def enabled_targets(self, create=False):
        """Resolve which agent directories this machine manages."""
        explicit = self.config.get("targets")
        homes = self.env_homes(include_windows=bool(getattr(self.args, "include_windows", False)))
        resolved = []
        for env, home in homes.items():
            for t in TARGETS:
                if explicit and t["id"] not in explicit:
                    continue
                for root in self.target_roots(t, env, home, create=create):
                    if not self._within(root, home):
                        self.environment_notes.append(
                            "refusing target outside %s: %s (only the current user's home is managed)" % (home, root))
                        continue
                    resolved.append({"target": t, "env": env, "root": root})
        return resolved

    def targets_by_id(self, ids, include_windows=False):
        homes = self.env_homes(include_windows=include_windows)
        out = []
        for tid in ids:
            t = TARGET_BY_ID.get(tid)
            if not t:
                die("unknown target id: %s" % tid)
            for env, home in homes.items():
                roots = self.target_roots(t, env, home, create=True)
                for root in roots:
                    if self._within(root, home):
                        out.append({"target": t, "env": env, "root": root})
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
            print(json.dumps(obj, indent=2, ensure_ascii=False))
        elif text is not None:
            log(text)
        else:
            log(json.dumps(obj, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Repo skill discovery
# ---------------------------------------------------------------------------


def repo_skills(repo):
    """Every directory under <repo>/skills that contains a SKILL.md."""
    repo = Path(repo)
    root = repo / "skills"
    out = []
    if not root.is_dir():
        return out
    for cur, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d.lower() not in {"node_modules"})
        curp = Path(cur)
        if len(curp.relative_to(root).parts) > 3:
            dirs[:] = []
            continue
        if SKILL_FILE in files:
            meta, _ = read_frontmatter(curp / SKILL_FILE)
            name = (meta.get("name") or curp.name).strip()
            out.append({
                "name": name,
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
    """True when the link resolves into our repo (that is the desired state)."""
    if not repo:
        return False
    entry = Path(entry)
    if not (entry.is_symlink() or is_junction(entry)):
        return False
    real = Path(os.path.realpath(entry))
    repo = Path(repo)
    return real == repo or repo in real.parents


def foreign_reason(entry, repo=None):
    """Why an existing skill directory must be left alone (None = adoptable)."""
    entry = Path(entry)
    if entry.is_symlink() or is_junction(entry):
        if is_our_link(entry, repo):
            return None
        return "symlink (already linked/managed by another tool)"
    for marker in FOREIGN_MARKERS:
        if (entry / marker).is_file():
            return "lock/manifest file present (%s)" % marker
    if (entry / ".git").exists():
        return "git checkout inside the skill dir (use 'add <url>' instead)"
    return None


def scan_env(ctx, env, home):
    """Find every skill living in a given environment's agent directories."""
    found = []
    for t in TARGETS:
        for root in ctx.target_roots(t, env, home):
            if not ctx._within(root, home):
                continue
            try:
                entries = sorted(root.iterdir())
            except OSError:
                continue
            for entry in entries:
                if entry.name.startswith("."):
                    continue
                reason = foreign_reason(entry, ctx.repo)
                if entry.is_symlink() or is_junction(entry):
                    found.append({
                        "name": entry.name, "path": entry, "env": env, "target_id": t["id"],
                        "kind": "symlink", "points_to": os.path.realpath(entry), "hash": None,
                        "mtime": 0, "files": 0, "frontmatter": {}, "managed_by": reason,
                        "own": is_our_link(entry, ctx.repo), "has_git": False,
                    })
                    continue
                if not entry.is_dir() or not is_skill_dir(entry):
                    continue
                meta, _ = read_frontmatter(entry / SKILL_FILE)
                nfiles = sum(len(f) for _, _, f in os.walk(entry))
                found.append({
                    "name": (meta.get("name") or entry.name).strip(),
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
                    "has_git": (entry / ".git").exists(),
                })
    return found


def group_by_name(items):
    groups = {}
    for it in items:
        groups.setdefault(it["name"], []).append(it)
    return groups


def pick_canonical(copies, prefer="newest"):
    """Choose which copy becomes the repo truth.

    prefer="newest"   -> newest mtime wins (default: the freshest install is
                         almost always the updated version), majority tie-break.
    prefer="majority" -> the content shared by the most directories wins.
    Any loser is backed up, never destroyed, and the plan lists both sides.
    """
    variants = {}
    for c in copies:
        if c.get("kind") == "symlink":
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
    return ranked[0][1][0], variants


# ---------------------------------------------------------------------------
# Git helpers
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


def git_commit(repo, message):
    if not git_dirty(repo):
        return False
    git(repo, "add", "-A", check=True)
    rc, _, err = git(repo, "-c", "user.name=" + (git_identity(repo, "name") or "skillkit"),
                      "-c", "user.email=" + (git_identity(repo, "email") or "skillkit@localhost"),
                      "commit", "-m", message)
    if rc != 0:
        print("  ! git commit failed: %s" % err)
        return False
    return True


def git_identity(repo, field):
    rc, out, _ = sh(["git", "config", "--global", "user." + field])
    return out if rc == 0 else ""


def have_gh():
    rc, _, _ = sh(["gh", "--version"])
    if rc != 0:
        return False
    rc, _, _ = sh(["gh", "auth", "status"])
    return rc == 0


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_targets(ctx):
    """Show the whole table: which agent dirs exist, and what is inside."""
    rows = []
    homes = ctx.env_homes(include_windows=ctx.wsl or bool(ctx.args.include_windows))
    for env, home in homes.items():
        for t in TARGETS:
            candidates = ctx.candidate_roots(t, home)
            existing = [r for r in candidates if r.is_dir()]
            n = 0
            for root in existing:
                try:
                    n += sum(1 for e in root.iterdir() if e.is_dir() or e.is_symlink())
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
    found = [r for r in rows if r["exists"]]
    lines = ["%-8s %-13s %-5s %-4s %-5s %s" % ("ENV", "ID", "EXIST", "SRC", "SKILL", "PATH")]
    for r in found:
        lines.append("%-8s %-13s %-5s %-4s %-5d %s" % (
            r["env"], r["id"], "yes", "doc" if r["src"] == "doc" else "?", r["entries"], r["path"]))
    hub = [r for r in rows if not r["exists"] and r["bind"] == "always"]
    for r in hub:
        lines.append("%-8s %-13s %-5s %-4s %-5d %s (created on demand)" % (
            r["env"], r["id"], "no", "doc", 0, r["path"]))
    lines.append("")
    lines.append("%d detected dir(s) across %d environment(s); %d agent type(s) known." % (
        len(found), len(homes), len(TARGETS)))
    for note in ctx.environment_notes:
        lines.append("note: " + note)
    ctx.emit({"environments": {k: str(v) for k, v in homes.items()},
              "detected": found, "known_targets": len(TARGETS),
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
        real = [c for c in copies if c.get("kind") != "symlink" and not c.get("managed_by_probe")]
        hashes = {c["hash"] for c in real if c.get("hash")}
        canon, variants = pick_canonical(copies)
        entries.append({
            "name": name,
            "copies": len(copies),
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


def _interactive():
    if os.environ.get("CI") or os.environ.get("SKILLKIT_NONINTERACTIVE"):
        return False
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def _validate_repo_path(ctx, path):
    path = Path(path).expanduser().resolve()
    for tr in ctx.enabled_targets():
        if path == tr["root"] or tr["root"] in path.parents:
            return "inside an agent skill directory (%s)" % tr["root"]
    if path.name == "skills":
        return "that is a skills/ directory, not a repo root"
    if any(part.lower() in ("onedrive", "dropbox", "icloud drive") for part in path.parts):
        return "inside a cloud-sync folder (git + links fight with the sync client)"
    return None


def choose_repo(ctx, args):
    """Pick the repo location: --repo > recorded location > recommended default.

    Asking the user is deliberately ONE-TIME (at init) and only when the answer
    actually changes behaviour, e.g. a WSL box also serving Windows agents.
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

    if not _interactive():
        notes.append("non-interactive: using the recommended path (pass --repo to change it)")
        return rec.resolve(), "recommended default", notes

    log("")
    log("Where should the skills repo live on this machine?")
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


def cmd_init(ctx):
    args = ctx.args
    repo, repo_source, repo_notes = choose_repo(ctx, args)
    ctx.repo = repo
    problem = _validate_repo_path(ctx, repo)
    if problem:
        die("refusing repo path %s: %s" % (repo, problem))
    if os.environ.get("SKILLKIT_HOME") and not ctx._within(repo, ctx.home):
        die("sandbox mode: SKILLKIT_HOME is set, so the repo must stay inside %s (got %s)" % (ctx.home, repo))

    log("== skillkit init ==")
    log("repo        : %s   [%s]" % (repo, repo_source))
    for note in repo_notes:
        log("              " + note)
    log("environment : %s%s" % ("WSL" if ctx.wsl else ("Windows" if os.name == "nt" else "POSIX"),
                                " (home: %s)" % ctx.home))
    log("mode        : %s" % ("APPLY" if ctx.apply else "DRY-RUN (add --apply to execute)"))
    if repo.exists() and not repo.is_dir():
        die("%s exists and is not a directory" % repo)
    log("scope       : only the CURRENT user's home (%s); project-level and other users' dirs untouched" % ctx.home)
    log("conflict    : keep the NEWEST copy by default (--prefer majority to override)")
    log("removal     : moves into %s/trash/, never deletes; deletion needs a separate confirmation" % STATE_DIR)
    if ctx.wsl and str(repo).startswith("/mnt/") is False:
        log("  note: repo lives inside the WSL filesystem, so Windows-side agents cannot use it.")
        log("        For dual WSL+Windows use, put the repo on a Windows drive (e.g. /mnt/d/skills-repo).")

    # ---- 1. repo + remote ----------------------------------------------
    remote_url = args.repo_url
    if repo.exists() and git_is_repo(repo):
        log("\n[1/5] repo already exists (%s)" % repo)
    else:
        log("\n[1/5] %s %s" % ("would create" if not ctx.apply else "creating", repo))
        if ctx.apply:
            repo.mkdir(parents=True, exist_ok=True)
            git(repo, "init", "-b", "main")
            git(repo, "symbolic-ref", "HEAD", "refs/heads/main")

    if ctx.apply:
        ctx.ensure_scaffolding()
        readme = repo / "README.md"
        template = Path(__file__).resolve().parent.parent / "assets" / "repo-readme-template.md"
        if not readme.is_file() and template.is_file():
            readme.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")

    # remote handling
    if remote_url:
        log("   remote: %s" % remote_url)
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
            log("   remote: already configured, skipping gh repo create")
        else:
            rc, out, err = sh(["gh", "repo", "create", "%s/skills-repo" % login, "--private", "--source", str(repo), "--push"])
            if rc != 0:
                log("   ! gh repo create failed: %s" % (err or out))
            else:
                log("   created private repo %s/skills-repo" % login)
    elif ctx.apply:
        if have_gh():
            log("   remote: none yet -> add with: git -C %s remote add origin <url> && git push -u origin HEAD" % repo)
            log("           (or re-run with --create-remote to create <you>/skills-repo via gh)")
        else:
            log("   remote: no authenticated 'gh' CLI found.")
            log("           create the private repo in the browser, then:")
            log("             git -C %s remote add origin git@github.com:<you>/skills-repo.git" % repo)
            log("             git -C %s push -u origin HEAD" % repo)

    # ---- 2. scan --------------------------------------------------------
    inc_win = bool(args.include_windows)
    homes = ctx.env_homes(include_windows=inc_win)
    log("\n[2/5] scanning %d environment(s) for existing skills" % len(homes))
    found = []
    for env, home in homes.items():
        got = scan_env(ctx, env, home)
        found.extend(got)
        log("  %-8s %-4d skill copies  (home: %s)" % (env, len(got), home))
    for note in ctx.environment_notes:
        log("  note: " + note)
    if not inc_win and ctx.wsl:
        log("  note: Windows-side agent dirs are not scanned. Add --include-windows to include the CURRENT Windows user.")

    prefer = getattr(args, "prefer", None) or ctx.config.get("conflict_policy") or "newest"
    existing = repo_skills(repo) if repo.is_dir() else []
    existing_names = {s["name"] for s in existing}
    groups = group_by_name(found)

    plan_import, plan_skip, plan_backup, plan_foreign = [], [], [], []
    repo_by_name = {s["name"]: s for s in existing}
    for name, copies in sorted(groups.items()):
        rejected = [c for c in copies if c.get("managed_by")]
        real = [c for c in copies if c.get("kind") != "symlink" and not c.get("managed_by")]
        if rejected:
            plan_foreign.extend(rejected)
        if not real:
            if any(c.get("own") for c in copies):
                why = "already linked to this repo"
            elif rejected:
                why = rejected[0]["managed_by"]
            else:
                why = "already a symlink (managed elsewhere)"
            plan_skip.append((name, why, copies[0]))
            continue
        if name in existing_names:
            # Already in the repo: the agent-side copies are redundant. Back them
            # up and step aside so the link can take their place.
            repo_hash = dir_hash(repo_by_name[name]["path"])
            for c in real:
                c["same_as_repo"] = (c["hash"] == repo_hash)
                plan_backup.append(c)
            plan_skip.append((name, "already in repo (agent copies replaced by links)", real[0]))
            continue
        canon, variants = pick_canonical(copies, prefer)
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
                    # keep the divergent copy where it is: it will block linking
                    plan_skip.append((name, "divergent copy kept as-is (--no-dedupe)", c))

    log("\n[3/5] plan")
    log("  import : %d" % len(plan_import))
    for item in plan_import:
        c = item["canonical"]
        conflict = len(item["variants"]) > 1
        log("    + %-26s <- %s/%s%s" % (item["name"], c["env"], c["target_id"],
                                        "   [CONFLICT keeping %s]" % human_time(c["mtime"]) if conflict else ""))
        if conflict:
            for h, group in sorted(item["variants"].items(), key=lambda kv: -len(kv[1])):
                mark = "*" if group[0] is c or h == c["hash"] else " "
                log("        %s %d copy(ies), newest %s, e.g. %s" % (
                    mark, len(group), human_time(max(x["mtime"] for x in group)), group[0]["path"]))
            log("        (policy: --prefer %s; losers are backed up, not destroyed)" % prefer)
    if plan_backup:
        log("  replace+backup : %d duplicate copies -> %s/backup/" % (len(plan_backup), STATE_DIR))
        for c in plan_backup:
            log("    ~ %-26s %s (%s)" % (c["name"], c["path"], human_time(c["mtime"])))
    if plan_skip:
        log("  skip   : %d" % len(plan_skip))
        for name, why, c in plan_skip:
            log("    - %-26s %s" % (name, why))
    if plan_foreign:
        log("  left alone (managed by another tool, reported only): %d copy(ies)" % len(plan_foreign))
        for c in plan_foreign[:12]:
            arrow = (" -> %s" % c["points_to"]) if c.get("points_to") else ""
            log("    ! %-26s %s%s  [%s]" % (c["name"], c["path"], arrow, c["managed_by"]))
        if len(plan_foreign) > 12:
            log("    ... %d more" % (len(plan_foreign) - 12))

    # ---- 3. execute imports --------------------------------------------
    stamp = time.strftime("%Y%m%d-%H%M%S")
    moved = 0
    if ctx.apply:
        log("\n[4/5] migrating")
        backup_root = repo / STATE_DIR / "backup" / stamp
        for item in plan_import:
            src = Path(item["canonical"]["path"])
            dest = repo / "skills" / item["name"]
            if dest.exists():
                log("  ! %s already exists in repo, skipped" % item["name"])
                continue
            copy_tree(src, backup_root / item["canonical"]["env"] / item["name"])
            ctx.state.setdefault("backups", []).append({
                "name": item["name"], "from": str(src), "backup": str(backup_root / item["canonical"]["env"] / item["name"]),
                "at": stamp,
            })
            if args.copy:
                copy_tree(src, dest)
            else:
                shutil.move(str(src), str(dest))
            log("  + %s" % item["name"])
            moved += 1
        for c in plan_backup:
            src = Path(c["path"])
            if not src.exists() or is_skill_link(src):
                continue
            label = "%s@%s" % (c["name"], c["target_id"])
            if not c.get("same_as_repo"):
                copy_tree(src, backup_root / c["env"] / label)
            trash = repo / STATE_DIR / "trash" / stamp / c["env"] / label
            trash.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(src), str(trash))
            except (OSError, shutil.Error) as exc:
                log("  ! could not move %s: %s" % (src, exc))
                continue
            log("  ~ %s %s (%s)" % ("stepped aside" if c.get("same_as_repo") else "removed duplicate", src,
                                    "identical to repo" if c.get("same_as_repo") else "backed up"))
        ctx.ensure_scaffolding()
        ctx.save_state()
        if moved or plan_backup:
            git_commit(repo, "import: adopt %d skill(s) into the central repo" % moved)
    else:
        log("\n[4/5] migration (skipped, dry-run)")

    # ---- 4. link --------------------------------------------------------
    log("\n[5/5] linking agents to the repo")
    skills = repo_skills(repo) if repo.is_dir() else []
    if not ctx.apply:
        planned = len(skills) + len(plan_import)
        log("  would link %d skill(s) into: %s" % (planned, ", ".join(sorted({r["target"]["id"] for r in ctx.enabled_targets()})) or "(none detected)"))
    else:
        created, errs = link_all(ctx, skills, ctx.enabled_targets())
        log("  linked %d, errors %d" % (created, errs))
        git_commit(repo, "link: refresh agent symlinks")
        if args.push:
            rc, out, err = git(repo, "push", "-u", "origin", "HEAD")
            log("  push: %s" % ("ok" if rc == 0 else (err or out)))

    if ctx.apply:
        if ctx.record_location(repo):
            log("\nremembered repo location in %s" % ctx.location_file())
    else:
        log("\nwould remember the repo location in %s" % ctx.location_file())
    log("\nDone." if ctx.apply else "\nDry-run complete. Re-run with --apply to execute.")
    if ctx.apply and not git_has_remote(repo):
        log("Next: add a private remote, then 'skillkit push'.")
    log("Next: 'skillkit doctor' to verify, 'skillkit list' to inspect.")


def link_all(ctx, skills, targets):
    created = errs = 0
    mode = ctx.config.get("link_mode", "auto")
    keep = []
    for sk in skills:
        for tr in targets:
            root = tr["root"]
            link = root / sk["name"]
            try:
                root.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                log("  ! cannot create %s: %s" % (root, exc))
                errs += 1
                continue
            if link_points_to(link, sk["path"]):
                keep.append({"name": sk["name"], "path": str(link), "target": str(sk["path"]),
                             "env": tr["env"], "target_id": tr["target"]["id"], "kind": "existing"})
                continue
            if link.exists() or link.is_symlink():
                if not (link.is_symlink() or is_junction(link)):
                    log("  ! %s is a REAL directory, not a link -> left untouched (run 'skillkit doctor' for details)" % link)
                    errs += 1
                    continue
                remove_link(link)
            try:
                kind = make_link(sk["path"], link, mode=mode, env=tr["env"])
                keep.append({"name": sk["name"], "path": str(link), "target": str(sk["path"]),
                             "env": tr["env"], "target_id": tr["target"]["id"], "kind": kind})
                created += 1
            except (RuntimeError, OSError, shutil.Error) as exc:
                log("  ! link failed %s: %s" % (link, exc))
                errs += 1
    ctx.state["links"] = keep + [l for l in ctx.state.get("links", []) if l["name"] not in {k["name"] for k in keep}]
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
        targets = ctx.enabled_targets()
    if ctx.args.mode:
        ctx.config["link_mode"] = ctx.args.mode
    log("linking %d skill(s) into %d target dir(s) [%s]" % (len(skills), len(targets),
                                                           "APPLY" if ctx.apply else "DRY-RUN"))
    if not ctx.apply:
        for sk in skills:
            for tr in targets:
                log("  %-28s -> %s" % (sk["name"], tr["root"] / sk["name"]))
        log("\nDry-run complete. Re-run with --apply.")
        return
    created, errs = link_all(ctx, skills, targets)
    log("linked %d, errors %d" % (created, errs))
    git_commit(repo, "link: refresh agent symlinks")


def cmd_unlink(ctx):
    ctx.require_repo()
    names = set(ctx.args.names or [])
    removed = 0
    for entry in list(ctx.state.get("links", [])):
        if names and entry["name"] not in names:
            continue
        link = Path(entry["path"])
        if link.is_symlink() or is_junction(link):
            if not ctx.apply:
                log("would unlink %s" % link)
                continue
            if remove_link(link):
                log("unlinked %s" % link)
                removed += 1
            else:
                log("  ! could not unlink %s (real directory?)" % link)
            ctx.state["links"] = [e for e in ctx.state["links"] if e["path"] != entry["path"]]
    if ctx.apply:
        ctx.save_state()
        log("removed %d link(s)" % removed)


def cmd_list(ctx):
    repo = ctx.require_repo()
    skills = repo_skills(repo)
    links = {}
    for entry in ctx.state.get("links", []):
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
        log("repo location set to %s  (%s)" % (path, "saved" if ok else "NOT saved"))
        return
    if ctx.args.forget:
        if loc.is_file():
            os.unlink(str(loc))          # one explicit path, the pointer file only
            log("forgot the recorded location (%s removed)" % loc)
        else:
            log("nothing recorded (%s does not exist)" % loc)
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
    links = ctx.state.get("links", [])
    broken = [l for l in links if not link_points_to(l["path"], l["target"])]
    info = {
        "repo": str(repo),
        "repo_source": ctx.repo_source,
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
                     "exists": r["root"].is_dir()} for r in ctx.enabled_targets()],
    }
    text = [
        "repo      : %s   [%s]" % (info["repo"], info.get("repo_source", "?")),
        "git       : %s%s%s" % ("ok" if info["git"]["is_repo"] else "NOT A REPO",
                                " (dirty)" if info["git"]["dirty"] else "",
                                "" if info["git"]["remote"] else " (no remote)"),
        "skills    : %d" % info["skills"],
        "links     : %d total, %d broken" % (info["links"], info["broken_links"]),
    ]
    for t in info["targets"]:
        text.append("target    : %-9s %-8s %s" % (t["id"], t["env"], t["path"]))
    ctx.emit(info, "\n".join(text))


def cmd_doctor(ctx):
    repo = ctx.require_repo()
    problems, warnings = [], []
    skills = repo_skills(repo)

    # 1. frontmatter / naming
    seen = {}
    for sk in skills:
        meta, _ = read_frontmatter(Path(sk["path"]) / SKILL_FILE)
        if not meta.get("name"):
            problems.append("%s: SKILL.md has no 'name' in frontmatter" % sk["rel"])
        elif meta["name"].strip() != sk["dir_name"]:
            warnings.append("%s: name '%s' differs from dir '%s' (links use the name)" % (sk["rel"], meta["name"], sk["dir_name"]))
        if not meta.get("description"):
            problems.append("%s: SKILL.md has no 'description'" % sk["rel"])
        if sk["name"] in seen:
            problems.append("duplicate skill name '%s' in %s and %s" % (sk["name"], seen[sk["name"]], sk["rel"]))
        seen[sk["name"]] = sk["rel"]

    # 2. links
    for entry in ctx.state.get("links", []):
        link, target = Path(entry["path"]), Path(entry["target"])
        if not target.exists():
            problems.append("link %s points at missing skill %s" % (link, target))
        elif not link.exists() and not link.is_symlink():
            problems.append("missing link %s -> %s" % (link, target))
        elif not link_points_to(link, target):
            problems.append("stale link %s (expected -> %s)" % (link, target))

    # 3. expected links for enabled targets
    expected = 0
    for tr in ctx.enabled_targets():
        for sk in skills:
            expected += 1
            link = tr["root"] / sk["name"]
            if not (link.exists() or link.is_symlink()):
                problems.append("not linked: %s (target %s)" % (sk["name"], tr["root"]))

    # 4. foreign / unmanaged skills inside agent dirs
    for tr in ctx.enabled_targets():
        root = tr["root"]
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            if entry.name.startswith(".") or not (entry.is_dir() or entry.is_symlink()):
                continue
            if not (entry.is_symlink() or is_junction(entry)) and not is_skill_dir(entry):
                continue          # not a skill directory (cache, notes, .system...) — ignore
            if entry.is_symlink() or is_junction(entry):
                if not is_our_link(entry, repo):
                    warnings.append("left alone in %s: %s [%s]"
                                    % (root, entry.name, foreign_reason(entry, repo)))
                continue          # our own link = desired state, nothing to report
            reason = foreign_reason(entry, repo)
            if reason:
                warnings.append("left alone in %s: %s [%s]" % (root, entry.name, reason))
                continue
            problems.append("unmanaged real directory in %s: %s (run 'skillkit init --apply' to adopt)" % (root, entry.name))

    # 5. secrets
    for sk in skills:
        for cur, dirs, files in os.walk(sk["path"]):
            dirs[:] = [d for d in dirs if d.lower() not in IGNORE_DIR_NAMES]
            for name in files:
                fp = Path(cur) / name
                if any(h in name.lower() for h in SECRET_FILE_HINTS):
                    warnings.append("possible secret file: %s" % fp)
                    continue
                if fp.stat().st_size > 512 * 1024:
                    continue
                try:
                    text = fp.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for rx, label in SECRET_PATTERNS:
                    if rx.search(text):
                        warnings.append("%s in %s" % (label, fp))
                        break

    # 6. git state
    info = {"skills": len(skills), "expected_links": expected}
    if git_is_repo(repo):
        if git_dirty(repo):
            warnings.append("repo has uncommitted changes (run 'skillkit push')")
        if not git_has_remote(repo):
            warnings.append("repo has no git remote (no off-machine backup)")
    else:
        problems.append("%s is not a git repository" % repo)

    if ctx.args.fix and problems:
        log("attempting repair of missing/broken links ...")
        created, errs = link_all(ctx, skills, ctx.enabled_targets())
        log("relinked %d, errors %d" % (created, errs))
        problems = [p for p in problems if not p.startswith(("missing link", "not linked", "stale link"))]

    payload = {"ok": not problems, "problems": problems, "warnings": warnings, "info": info}
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
    log("\n%d problem(s), %d warning(s)%s" % (len(problems), len(warnings),
                                              " (use --fix for link repair)" if problems else ""))


def cmd_add(ctx):
    args = ctx.args
    repo = ctx.require_repo()
    src = args.source
    is_url = bool(re.match(r"^(https?://|git@|ssh://)", src))
    tmp = None
    if is_url:
        tmp = Path(os.path.join(os.environ.get("TMPDIR", "/tmp"), "skillkit-clone-%d" % int(time.time())))
        log("cloning %s" % src)
        rc, out, err = sh(["git", "clone", "--depth", "1", src, str(tmp)])
        if rc != 0:
            die("git clone failed: %s" % (err or out))
        candidates = [p for p in [tmp] + sorted(tmp.iterdir()) if is_skill_dir(p)]
        if not candidates:
            sub = [p for p in tmp.rglob(SKILL_FILE) if ".git" not in p.parts]
            if sub:
                candidates = [sub[0].parent]
        if not candidates:
            die("no SKILL.md found in %s" % src)
        source_dir = candidates[0]
    else:
        source_dir = Path(src).expanduser()
        if not source_dir.is_dir():
            die("not a directory: %s" % source_dir)
        if not is_skill_dir(source_dir):
            die("no SKILL.md in %s" % source_dir)

    meta, _ = read_frontmatter(source_dir / SKILL_FILE)
    name = args.name or meta.get("name") or source_dir.name
    name = re.sub(r"[^A-Za-z0-9._-]", "-", name.strip())
    category = args.category
    dest = repo / "skills" / (category + "/" if category else "") / name
    log("add %s -> %s [%s]" % (name, dest, "APPLY" if ctx.apply else "DRY-RUN"))
    if dest.exists():
        if not args.force:
            die("%s already exists in the repo (use --force to replace; old copy goes to .trash)" % name)
        log("  replacing existing copy (moved to %s/trash/)" % STATE_DIR)
        if ctx.apply:
            trash = repo / STATE_DIR / "trash" / time.strftime("%Y%m%d-%H%M%S") / name
            trash.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dest), str(trash))
    if not ctx.apply:
        log("dry-run complete. Re-run with --apply.")
        return
    copy_tree(source_dir, dest)
    if tmp and tmp.exists():
        # single, explicit path; no recursive delete of user data
        shutil.move(str(tmp), str(repo / STATE_DIR / "trash" / ("clone-" + str(int(time.time())))))
    if is_url:
        ctx.config.setdefault("sources", {})[name] = src
        ctx.save_config()
    ctx.ensure_scaffolding()
    git_commit(repo, "add: %s" % name)
    if not args.no_link:
        created, errs = link_all(ctx, [s for s in repo_skills(repo) if s["name"] == name], ctx.enabled_targets())
        log("linked %d, errors %d" % (created, errs))
    log("done. 'skillkit push' to publish.")


def cmd_update(ctx):
    repo = ctx.require_repo()
    sources = ctx.config.get("sources", {})
    names = ctx.args.names or sorted(sources)
    if not names:
        die("no recorded upstream sources; use 'skillkit add <url>' first")
    for name in names:
        url = sources.get(name)
        if not url:
            log("skip %s: no recorded source" % name)
            continue
        dest = repo / "skills" / name
        if not dest.is_dir():
            hits = [s for s in repo_skills(repo) if s["name"] == name]
            if not hits:
                log("skip %s: not in repo" % name)
                continue
            dest = hits[0]["path"]
        log("update %s <- %s [%s]" % (name, url, "APPLY" if ctx.apply else "DRY-RUN"))
        if not ctx.apply:
            continue
        tmp = Path(os.path.join(os.environ.get("TMPDIR", "/tmp"), "skillkit-upd-%d" % int(time.time())))
        rc, out, err = sh(["git", "clone", "--depth", "1", url, str(tmp)])
        if rc != 0:
            log("  ! clone failed: %s" % (err or out))
            continue
        cands = [p for p in [tmp] + sorted(tmp.iterdir()) if is_skill_dir(p)]
        if not cands:
            log("  ! no SKILL.md upstream")
            continue
        trash = repo / STATE_DIR / "trash" / time.strftime("%Y%m%d-%H%M%S") / name
        trash.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dest), str(trash))
        copy_tree(cands[0], dest)
        shutil.move(str(tmp), str(repo / STATE_DIR / "trash" / ("upd-" + str(int(time.time())))))
        log("  updated")
    if ctx.apply:
        git_commit(repo, "update: refresh from upstream")
        log("done. 'skillkit push' to publish.")


def cmd_remove(ctx):
    repo = ctx.require_repo()
    names = ctx.args.names
    skills = {s["name"]: s for s in repo_skills(repo)}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for name in names:
        sk = skills.get(name)
        if not sk:
            log("skip %s: not in repo" % name)
            continue
        log("remove %s [%s]  (links removed, payload MOVED to %s/trash/ — nothing is deleted)"
            % (name, "APPLY" if ctx.apply else "DRY-RUN", STATE_DIR))
        if not ctx.apply:
            for entry in ctx.state.get("links", []):
                if entry["name"] == name:
                    log("  would unlink %s" % entry["path"])
            log("  would move %s -> %s/trash/<timestamp>/%s" % (sk["path"], STATE_DIR, name))
            continue
        # 1) unlink every agent dir that points at it
        for entry in list(ctx.state.get("links", [])):
            if entry["name"] != name:
                continue
            link = Path(entry["path"])
            if link.is_symlink() or is_junction(link):
                remove_link(link)
                log("  unlinked %s" % link)
            ctx.state["links"] = [e for e in ctx.state.get("links") if e["path"] != entry["path"]]
        # 2) move the payload to .trash (never delete)
        trash = repo / STATE_DIR / "trash" / stamp / name
        trash.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(sk["path"]), str(trash))
        ctx.config.get("sources", {}).pop(name, None)
        log("  moved to %s" % trash)
    if ctx.apply:
        ctx.save_config()
        ctx.save_state()
        git_commit(repo, "remove: %s" % ", ".join(names))
        log("done. Recover from %s/trash/%s/ if this was a mistake." % (STATE_DIR, stamp))


def _tree_files(path):
    out = []
    for cur, dirs, files in os.walk(path):
        for name in sorted(files):
            out.append(Path(cur) / name)
    return out


def cmd_trash(ctx):
    """List or purge the trash. Purging DELETES files, so it is gated twice."""
    repo = ctx.require_repo()
    root = repo / STATE_DIR / "trash"
    args = ctx.args
    if not root.is_dir():
        log("trash is empty (%s)" % root)
        return
    if not args.purge:
        rows = []
        for tsdir in sorted(root.iterdir()):
            if not tsdir.is_dir():
                continue
            for item in sorted(tsdir.rglob("*")):
                if item.is_dir() and not any(p.is_dir() for p in item.iterdir()):
                    rows.append({"timestamp": tsdir.name, "name": item.name, "path": str(item),
                                 "files": len(_tree_files(item))})
        for r in rows:
            log("%-16s %-30s %3d file(s)  %s" % (r["timestamp"], r["name"], r["files"], r["path"]))
        if not rows:
            log("trash is empty")
        log("\nNothing deleted. 'skillkit trash --purge <name>' lists exact files and requires")
        log("both --confirm-delete and an explicit yes before deleting anything one path at a time.")
        ctx.emit({"trash_root": str(root), "items": rows})
        return

    # ---- purge: two gates, exact paths, one unlink per file ---------------
    needle = args.purge
    victims = [p for p in root.rglob(needle) if p.exists() or p.is_symlink()]
    if needle == "all":
        victims = [p for p in root.iterdir()]
    if not victims:
        die("no trash entry matches %r" % needle)
    files = []
    for v in victims:
        files.extend([v] if v.is_file() or v.is_symlink() else _tree_files(v))
    log("About to DELETE %d file(s) from %d trash entr(ies):" % (len(files), len(victims)))
    for f in files[:200]:
        log("  " + str(f))
    if len(files) > 200:
        log("  ... %d more" % (len(files) - 200))
    log("")
    log("This violates the user's default 'no batch delete' rule, so it needs an explicit OK.")
    if not args.confirm_delete:
        log("Refusing: re-run with --confirm-delete after the user confirms.")
        return
    if not ctx.yes:
        try:
            answer = input("Type DELETE to confirm: ").strip()
        except EOFError:
            answer = ""
        if answer != "DELETE":
            log("aborted, nothing deleted")
            return
    removed = 0
    for f in files:
        try:
            os.unlink(str(f))
            removed += 1
        except OSError as exc:
            log("  ! %s: %s" % (f, exc))
    for v in sorted(victims, key=lambda x: len(str(x)), reverse=True):
        for cur, dirs, _ in os.walk(v, topdown=False):
            for d in dirs:
                try:
                    os.rmdir(os.path.join(cur, d))
                except OSError:
                    pass
        try:
            os.rmdir(str(v))
        except OSError:
            pass
    log("deleted %d file(s); empty directories pruned." % removed)


def cmd_restore(ctx):
    repo = ctx.require_repo()
    skills = repo_skills(repo)
    targets = ctx.enabled_targets()
    log("restore %d skill(s) into %d target dir(s) [%s]" % (len(skills), len(targets),
                                                            "APPLY" if ctx.apply else "DRY-RUN"))
    for tr in targets:
        log("  %-9s %-8s %s" % (tr["target"]["id"], tr["env"], tr["root"]))
    if not ctx.apply:
        log("\nDry-run complete. Re-run with --apply.")
        return
    created, errs = link_all(ctx, skills, targets)
    log("linked %d, errors %d" % (created, errs))


def cmd_push(ctx):
    repo = ctx.require_repo()
    if not git_is_repo(repo):
        die("%s is not a git repository" % repo)
    if not git_has_remote(repo):
        die("no git remote. Add one: git -C %s remote add origin git@github.com:<you>/skills-repo.git" % repo)
    msg = ctx.args.message or "sync: update skills"
    if git_dirty(repo):
        if not ctx.apply:
            log("would: git add -A && git commit -m %r && git push" % msg)
            log("dry-run complete. Re-run with --apply.")
            return
        git_commit(repo, msg)
    if not ctx.apply:
        log("would: git push")
        return
    rc, out, err = git(repo, "push")
    log("push %s%s" % ("ok" if rc == 0 else "FAILED", "" if rc == 0 else ": " + (err or out)))


def cmd_pull(ctx):
    repo = ctx.require_repo()
    if not ctx.apply:
        log("would: git pull --rebase && restore links")
        return
    rc, out, err = git(repo, "pull", "--rebase", "--autostash")
    log("pull %s%s" % ("ok" if rc == 0 else "FAILED", "" if rc == 0 else ": " + (err or out)))
    skills = repo_skills(repo)
    created, errs = link_all(ctx, skills, ctx.enabled_targets())
    log("relinked %d, errors %d" % (created, errs))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    # defaults are SUPPRESS so a value given before the subcommand is not
    # overwritten by the subparser's default; main() fills the gaps.
    S = argparse.SUPPRESS
    common.add_argument("--repo", default=S, help="path to the skills repo (default <home>/skills-repo)")
    common.add_argument("--json", action="store_true", default=S, help="machine-readable output")
    common.add_argument("--apply", action="store_true", default=S, help="execute instead of dry-run")
    common.add_argument("-y", "--yes", action="store_true", default=S, help="assume yes / non-interactive")
    common.add_argument("-v", "--verbose", action="store_true", default=S)
    common.add_argument("--include-windows", action="store_true", default=S,
                        help="also consider the CURRENT Windows user's dirs when running inside WSL")
    common.add_argument("--allow-cross-user", action="store_true", default=S,
                        help="allow touching a Windows profile that is not the current user (refused by default)")

    p = argparse.ArgumentParser(prog="skillkit", description="one-repo, symlink-first skill manager",
                                parents=[common])
    p.add_argument("--version", action="version", version="skillkit " + VERSION)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", parents=[common], help="bootstrap repo + migrate existing skills + link")
    sp.add_argument("--repo-url", help="git remote URL to attach (skips gh)")
    sp.add_argument("--create-remote", action="store_true", help="create <you>/skills-repo via gh (private)")
    sp.add_argument("--copy", action="store_true",
                    help="copy instead of move the originals (move is the default: they are backed up first)")
    sp.add_argument("--no-dedupe", action="store_true", help="keep differing duplicate copies untouched")
    sp.add_argument("--prefer", choices=["newest", "majority"], default="newest",
                    help="conflict policy when the same skill differs between agents (default: newest)")
    sp.add_argument("--push", action="store_true", help="push after importing")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("scan", parents=[common], help="inventory skills across all agent dirs")
    sp.add_argument("--env", default="local", choices=["local", "windows", "all"])
    sp.set_defaults(func=cmd_scan)

    sp = sub.add_parser("repo", parents=[common], help="show / set / forget which local repo this machine uses")
    sp.add_argument("--set", dest="set_path", help="record this path as the repo for this machine")
    sp.add_argument("--forget", action="store_true", help="drop the recorded location")
    sp.set_defaults(func=cmd_repo)

    sp = sub.add_parser("targets", parents=[common], help="show detected agent skill directories")
    sp.set_defaults(func=cmd_targets)

    sp = sub.add_parser("list", parents=[common], help="list repo skills and their links")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("status", parents=[common], help="repo + link status")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("doctor", parents=[common], help="validate skills, links, secrets, git")
    sp.add_argument("--fix", action="store_true", help="repair missing/broken links")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("add", parents=[common], help="install a skill (local dir or git URL) into the repo")
    sp.add_argument("source")
    sp.add_argument("--name")
    sp.add_argument("--category")
    sp.add_argument("--force", action="store_true")
    sp.add_argument("--no-link", action="store_true")
    sp.set_defaults(func=cmd_add)

    sp = sub.add_parser("update", parents=[common], help="re-fetch skills recorded with a git source")
    sp.add_argument("names", nargs="*")
    sp.set_defaults(func=cmd_update)

    sp = sub.add_parser("link", parents=[common], help="create links for repo skills")
    sp.add_argument("names", nargs="*")
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--to", help="comma separated target ids, e.g. agents,claude,codex,pi,antigravity,kimi,qwen,codebuddy "
                                 "(run 'skillkit targets' for the full list of 73)")
    sp.add_argument("--mode", choices=["auto", "symlink", "junction", "copy"])
    sp.set_defaults(func=cmd_link)

    sp = sub.add_parser("unlink", parents=[common], help="remove links (payload stays in the repo)")
    sp.add_argument("names", nargs="*")
    sp.add_argument("--all", action="store_true")
    sp.set_defaults(func=cmd_unlink)

    sp = sub.add_parser("remove", parents=[common], help="unlink + move a skill to .trash (never deletes)")
    sp.add_argument("names", nargs="+")
    sp.set_defaults(func=cmd_remove)

    sp = sub.add_parser("trash", parents=[common],
                        help="list the trash; --purge deletes (needs --confirm-delete + typed confirmation)")
    sp.add_argument("--purge", help="name, path fragment, or 'all' to purge")
    sp.add_argument("--confirm-delete", action="store_true", help="required gate for any deletion")
    sp.set_defaults(func=cmd_trash)

    sp = sub.add_parser("restore", parents=[common], help="rebuild every link from the repo (new machine)")
    sp.set_defaults(func=cmd_restore)

    sp = sub.add_parser("push", parents=[common], help="commit + push the repo")
    sp.add_argument("-m", "--message")
    sp.set_defaults(func=cmd_push)

    sp = sub.add_parser("pull", parents=[common], help="git pull --rebase + relink")
    sp.set_defaults(func=cmd_pull)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    for key, default in (("repo", None), ("json", False), ("apply", False), ("yes", False),
                         ("verbose", False), ("include_windows", False), ("allow_cross_user", False)):
        if not hasattr(args, key):
            setattr(args, key, default)
    ctx = Context(args)
    if args.cmd not in ("init", "targets", "scan", "repo"):
        if not ctx.repo:
            die("no skills repo found. Pass --repo PATH, set SKILLKIT_REPO, or run 'skillkit init'.")
    try:
        args.func(ctx)
    except KeyboardInterrupt:
        die("interrupted", 130)


if __name__ == "__main__":
    main()
