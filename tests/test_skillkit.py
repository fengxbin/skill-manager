#!/usr/bin/env python3
"""Regression test suite for scripts/skillkit.py (stdlib unittest only)."""

import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLKIT = ROOT / "scripts" / "skillkit.py"


def _is_junction(p):
    p = Path(p)
    if p.is_symlink():
        return False
    if os.name == "nt":
        import ctypes
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(p))
        return bool(attrs != -1 and (attrs & 0x400) and (attrs & 0x10))
    return False


def _force_remove_tree(path):
    """Test teardown helper (handles Windows read-only git files & NEVER follows junctions)."""
    path = Path(path)
    if path.is_symlink():
        os.unlink(str(path))
        return
    if _is_junction(path):
        os.rmdir(str(path))
        return
    if not path.exists():
        return
    dirs_to_remove = []
    for cur, dirs, files in os.walk(str(path), topdown=True, followlinks=False):
        safe_dirs = []
        for d in dirs:
            dp = os.path.join(cur, d)
            if os.path.islink(dp):
                try:
                    os.unlink(dp)
                except OSError:
                    pass
            elif _is_junction(dp):
                try:
                    os.rmdir(dp)
                except OSError:
                    pass
            else:
                safe_dirs.append(d)
        dirs[:] = safe_dirs
        for name in files:
            fp = os.path.join(cur, name)
            try:
                os.unlink(fp)
            except PermissionError:
                os.chmod(fp, stat.S_IWRITE)
                os.unlink(fp)
            except OSError:
                pass
        dirs_to_remove.append(cur)
    for d in reversed(dirs_to_remove):
        try:
            os.rmdir(d)
        except OSError:
            pass


def make_skill(dir_path, name, body="hello", mtime=None):
    p = Path(dir_path)
    p.mkdir(parents=True, exist_ok=True)
    skill_md = p / "SKILL.md"
    skill_md.write_text(
        "---\nname: %s\ndescription: Test skill %s\n---\n\n%s\n" % (name, name, body),
        encoding="utf-8",
    )
    if mtime is not None:
        os.utime(str(skill_md), (mtime, mtime))
    return p


def git_run(cwd, *args):
    r = subprocess.run(
        ["git", "-C", str(cwd)] + list(args),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        raise RuntimeError("git %s failed: %s %s" % (args, r.stdout, r.stderr))
    return r.stdout.strip()


def make_git_skill_repo(base_dir, repo_name, skills_map):
    """Create a local git repo (working tree) suitable for `file://` cloning.

    skills_map: dict of relative_subdir -> (skill_name, body)
                use "" as key for root-level SKILL.md.
    """
    repo = Path(base_dir) / repo_name
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    git_run(repo, "config", "user.name", "tester")
    git_run(repo, "config", "user.email", "tester@example.com")
    for rel, (sname, body) in skills_map.items():
        target = repo / rel if rel else repo
        make_skill(target, sname, body=body)
    git_run(repo, "add", "-A")
    git_run(repo, "commit", "-m", "initial")
    return repo


def make_bare_remote(base_dir, name="origin.git"):
    bare = Path(base_dir) / name
    bare.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True)
    return bare


class SkillkitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="skillkit-test-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.env = os.environ.copy()
        self.env["SKILLKIT_HOME"] = str(self.home)
        self.env["SKILLKIT_NONINTERACTIVE"] = "1"
        self.env.pop("SKILLKIT_REPO", None)

    def tearDown(self):
        _force_remove_tree(self.tmp)

    def run_cli(self, *args, check=True, env_extra=None):
        env = self.env.copy()
        if env_extra:
            env.update(env_extra)
        r = subprocess.run(
            [sys.executable, str(SKILLKIT)] + list(args),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if check and r.returncode != 0:
            self.fail("CLI %s failed (rc=%d)\nSTDOUT:\n%s\nSTDERR:\n%s" % (args, r.returncode, r.stdout, r.stderr))
        return r

    def test_init_defaults_hubs_config_and_conflict_resolution(self):
        now = time.time()
        # Two agent dirs with conflicting content for 'alpha'
        make_skill(self.home / ".claude" / "skills" / "alpha", "alpha", body="older", mtime=now - 3600)
        make_skill(self.home / ".codex" / "skills" / "alpha", "alpha", body="newer", mtime=now - 60)
        # Multi-candidate dir for pi with duplicate 'alpha' (tests backup label collision fix)
        make_skill(self.home / ".pi" / "agent" / "skills" / "alpha", "alpha", body="pi-old-1", mtime=now - 7200)
        make_skill(self.home / ".pi" / "skills" / "alpha", "alpha", body="pi-old-2", mtime=now - 7000)

        # Dry-run should not create skills-repo
        r_dry = self.run_cli("init", "--json")
        dry_data = json.loads(r_dry.stdout)
        self.assertFalse(dry_data["apply"])
        self.assertFalse((self.home / "skills-repo").exists())

        # Apply
        r = self.run_cli("init", "--apply", "--json")
        data = json.loads(r.stdout)
        self.assertTrue(data["apply"])
        repo = self.home / "skills-repo"
        self.assertTrue(repo.is_dir())
        self.assertTrue((repo / "skill-manager.json").is_file())
        cfg = json.loads((repo / "skill-manager.json").read_text(encoding="utf-8"))
        self.assertTrue(cfg["auto_push"])
        self.assertEqual(cfg["conflict_policy"], "newest")

        # Newest version won
        content = (repo / "skills" / "alpha" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("newer", content)

        # bind="always" hubs were actually created and linked
        self.assertTrue((self.home / ".agents" / "skills" / "alpha" / "SKILL.md").is_file())
        self.assertTrue((self.home / ".config" / "agents" / "skills" / "alpha" / "SKILL.md").is_file())

        # doctor reports 0 problems
        r_doc = self.run_cli("doctor", "--json")
        doc = json.loads(r_doc.stdout)
        self.assertTrue(doc["ok"], doc)
        self.assertEqual(doc["problems"], [])

    def test_init_never_adopts_foreign_managed_even_if_newer(self):
        now = time.time()
        # Adoptable older copy in claude
        make_skill(self.home / ".claude" / "skills" / "beta", "beta", body="adoptable-older", mtime=now - 3600)
        # Foreign-managed newer copy in codex (has skills-lock.json)
        foreign = make_skill(self.home / ".codex" / "skills" / "beta", "beta", body="foreign-newer", mtime=now)
        (foreign / "skills-lock.json").write_text("{}", encoding="utf-8")

        self.run_cli("init", "--apply")
        repo = self.home / "skills-repo"
        # Repo must have adopted the older adoptable copy, NOT the foreign one
        self.assertIn("adoptable-older", (repo / "skills" / "beta" / "SKILL.md").read_text(encoding="utf-8"))
        # Foreign directory in codex must still be untouched with its lock file
        self.assertTrue((foreign / "skills-lock.json").is_file())
        self.assertIn("foreign-newer", (foreign / "SKILL.md").read_text(encoding="utf-8"))

    def test_add_update_remove_with_git_url_strips_git_and_auto_pushes(self):
        bare = make_bare_remote(self.tmp)
        upstream = make_git_skill_repo(self.tmp, "my-awesome-skill", {"": ("my-awesome-skill", "v1")})
        upstream_url = upstream.resolve().as_uri()
        remote_url = bare.resolve().as_uri()

        # Init repo attached to bare remote
        make_skill(self.home / ".claude" / "skills" / "seed", "seed", body="seed")
        self.run_cli("init", "--repo-url", remote_url, "--apply")
        repo = self.home / "skills-repo"

        # Verify init auto-pushed to remote
        remote_log = git_run(bare, "log", "--oneline", "--all")
        self.assertTrue(remote_log)

        # Dry-run add <url> leaves no temp clone behind and doesn't touch repo
        r_dry = self.run_cli("add", upstream_url, "--json")
        dry = json.loads(r_dry.stdout)
        self.assertEqual(dry["items"][0]["name"], "my-awesome-skill")
        self.assertTrue(dry["will_push"])
        self.assertFalse((repo / "skills" / "my-awesome-skill").exists())

        # Apply add <url>
        r_add = self.run_cli("add", upstream_url, "--apply", "--json")
        added = json.loads(r_add.stdout)
        self.assertEqual(added["added"], ["my-awesome-skill"])
        self.assertEqual(added["sync"]["status"], "ok")

        # Critical bugfix check: .git must NOT be copied into skills/<name>/
        self.assertFalse((repo / "skills" / "my-awesome-skill" / ".git").exists())
        self.assertIn("v1", (self.home / ".claude" / "skills" / "my-awesome-skill" / "SKILL.md").read_text(encoding="utf-8"))

        # Verify remote has the added skill
        ls_tree = git_run(bare, "ls-tree", "-r", "--name-only", "HEAD")
        self.assertIn("skills/my-awesome-skill/SKILL.md", ls_tree)

        # Update upstream to v2 and run update --apply
        make_skill(upstream, "my-awesome-skill", body="v2")
        git_run(upstream, "add", "-A")
        git_run(upstream, "commit", "-m", "v2")

        r_upd = self.run_cli("update", "my-awesome-skill", "--apply", "--json")
        upd = json.loads(r_upd.stdout)
        self.assertEqual(upd["updated"], ["my-awesome-skill"])
        self.assertEqual(upd["sync"]["status"], "ok")
        self.assertFalse((repo / "skills" / "my-awesome-skill" / ".git").exists())
        self.assertIn("v2", (self.home / ".claude" / "skills" / "my-awesome-skill" / "SKILL.md").read_text(encoding="utf-8"))

        # Remove skill -> unlinks even if state file is deleted, and auto-pushes
        for sf in (repo / ".skill-manager").glob("state*.json"):
            os.unlink(str(sf))
        r_rm = self.run_cli("remove", "my-awesome-skill", "--apply", "--json")
        rm = json.loads(r_rm.stdout)
        self.assertEqual(rm["sync"]["status"], "ok")
        self.assertFalse((self.home / ".claude" / "skills" / "my-awesome-skill").exists())
        self.assertFalse((repo / "skills" / "my-awesome-skill").exists())

        ls_tree_after = git_run(bare, "ls-tree", "-r", "--name-only", "HEAD")
        self.assertNotIn("skills/my-awesome-skill/SKILL.md", ls_tree_after)

    def test_multi_skill_repo_and_cross_category_duplicate_guard(self):
        self.run_cli("init", "--apply")
        multi = make_git_skill_repo(self.tmp, "skill-pack", {
            "pack/one": ("one", "skill one"),
            "pack/two": ("two", "skill two"),
        })
        url = multi.resolve().as_uri()

        # Without --skill or --all, should fail cleanly listing both skills
        r_fail = self.run_cli("add", url, check=False)
        self.assertNotEqual(r_fail.returncode, 0)
        self.assertIn("one", r_fail.stderr)
        self.assertIn("two", r_fail.stderr)

        # With --all --apply, imports both
        r_all = self.run_cli("add", url, "--all", "--category", "catA", "--apply", "--json")
        self.assertEqual(sorted(json.loads(r_all.stdout)["added"]), ["one", "two"])

        # Cross-category duplicate must be rejected without --force
        local_dup = make_skill(self.tmp / "dup" / "one", "one", body="dup")
        r_dup = self.run_cli("add", str(local_dup), "--category", "catB", "--apply", check=False)
        self.assertNotEqual(r_dup.returncode, 0)
        self.assertIn("already exists", r_dup.stderr)

    def test_secret_gate_blocks_push_until_cleaned_or_overridden(self):
        bare = make_bare_remote(self.tmp)
        self.run_cli("init", "--repo-url", bare.resolve().as_uri(), "--apply")

        fake_token = "ghp_" + "1234567890abcdefghijklmno"
        secret_skill = make_skill(self.tmp / "leaky", "leaky", body="token: " + fake_token)
        r_add = self.run_cli("add", str(secret_skill), "--apply", "--json")
        res = json.loads(r_add.stdout)
        self.assertEqual(res["sync"]["status"], "blocked")

        # Direct push also blocks
        r_push = self.run_cli("push", "--apply", "--json", check=False)
        self.assertNotEqual(r_push.returncode, 0)
        self.assertEqual(json.loads(r_push.stdout)["status"], "blocked")

        # --allow-secrets overrides explicitly
        r_ok = self.run_cli("push", "--apply", "--allow-secrets", "--json")
        self.assertEqual(json.loads(r_ok.stdout)["sync"]["status"], "ok")

    def test_unlink_requires_args_and_pull_prunes_dangling_links(self):
        bare = make_bare_remote(self.tmp)
        remote_url = bare.resolve().as_uri()
        make_skill(self.home / ".claude" / "skills" / "gamma", "gamma", body="g")
        make_skill(self.home / ".claude" / "skills" / "delta", "delta", body="d")
        self.run_cli("init", "--repo-url", remote_url, "--apply")

        # unlink without name or --all must fail
        r_bad = self.run_cli("unlink", "--apply", check=False)
        self.assertNotEqual(r_bad.returncode, 0)

        # Simulate Machine B removing 'delta' and pushing to remote
        machine_b = self.tmp / "machine_b"
        subprocess.run(["git", "clone", remote_url, str(machine_b)], check=True, capture_output=True)
        git_run(machine_b, "config", "user.name", "b")
        git_run(machine_b, "config", "user.email", "b@example.com")
        git_run(machine_b, "rm", "-r", "skills/delta")
        git_run(machine_b, "commit", "-m", "remove delta on machine B")
        git_run(machine_b, "push")

        # Machine A runs pull --apply -> dangling link for 'delta' is pruned!
        r_pull = self.run_cli("pull", "--apply", "--json")
        pull_data = json.loads(r_pull.stdout)
        self.assertTrue(pull_data["pull_ok"])
        self.assertGreaterEqual(len(pull_data["pruned"]), 1)
        self.assertFalse((self.home / ".claude" / "skills" / "delta").exists())
        self.assertTrue((self.home / ".claude" / "skills" / "gamma" / "SKILL.md").is_file())

    def test_doctor_fix_dry_run_honest_reverify_and_trash_json(self):
        make_skill(self.home / ".claude" / "skills" / "eps", "eps", body="e")
        self.run_cli("init", "--apply")

        # Break the link by removing it
        self.run_cli("unlink", "eps", "--apply")

        # doctor --fix without --apply must NOT repair
        self.run_cli("doctor", "--fix", "--json")
        self.assertFalse((self.home / ".claude" / "skills" / "eps").exists())

        # doctor --fix --apply repairs it
        r_fix = self.run_cli("doctor", "--fix", "--apply", "--json")
        fixed = json.loads(r_fix.stdout)
        self.assertTrue(fixed["ok"])
        self.assertTrue((self.home / ".claude" / "skills" / "eps" / "SKILL.md").is_file())

        # Replace link with a blocking REAL directory -> doctor --fix --apply must NOT hide the problem
        self.run_cli("unlink", "eps", "--apply")
        make_skill(self.home / ".claude" / "skills" / "eps", "eps", body="blocking-real-dir")
        r_still_bad = self.run_cli("doctor", "--fix", "--apply", "--json")
        still = json.loads(r_still_bad.stdout)
        self.assertFalse(still["ok"])
        self.assertTrue(any("unmanaged real directory" in p for p in still["problems"]))

        # Remove skill -> trash --json must emit pure JSON, and --purge SKILL.md must fail
        self.run_cli("remove", "eps", "--apply")
        r_trash = self.run_cli("trash", "--json")
        tdata = json.loads(r_trash.stdout)
        self.assertEqual(len(tdata["items"]), 1)
        self.assertEqual(tdata["items"][0]["name"], "eps")

        r_nested = self.run_cli("trash", "--purge", "SKILL.md", "--confirm-delete", "-y", check=False)
        self.assertNotEqual(r_nested.returncode, 0)

        r_purge = self.run_cli("trash", "--purge", "eps", "--confirm-delete", "-y", "--json")
        self.assertGreaterEqual(json.loads(r_purge.stdout)["deleted"], 1)

    def test_alt_skills_repo_underscore_autodetect(self):
        alt = self.home / "skills_repo"
        make_skill(alt / "skills" / "old", "old", body="alt")
        subprocess.run(["git", "init", str(alt)], check=True, capture_output=True)
        r = self.run_cli("repo", "--json")
        info = json.loads(r.stdout)
        self.assertEqual(Path(info["repo"]).resolve(), alt.resolve())

    def test_install_self_links_all_detected_agents_and_doctor_clean(self):
        # Simulate two installed agents
        (self.home / ".claude" / "skills").mkdir(parents=True)
        (self.home / ".codex" / "skills").mkdir(parents=True)

        # Dry-run must not create links
        r_dry = self.run_cli("install", "--json")
        dry = json.loads(r_dry.stdout)
        self.assertFalse(dry["apply"])
        self.assertFalse((self.home / ".claude" / "skills" / "skill-manager").exists())

        # Apply installs into all detected agent dirs + universal hubs in one shot
        r = self.run_cli("install", "--apply", "--json")
        res = json.loads(r.stdout)
        self.assertTrue(res["apply"])
        self.assertEqual(res["errors"], 0)
        self.assertGreaterEqual(res["linked"], 4)  # claude, codex, agents, config-agents
        self.assertTrue((self.home / ".claude" / "skills" / "skill-manager" / "SKILL.md").is_file())
        self.assertTrue((self.home / ".codex" / "skills" / "skill-manager" / "SKILL.md").is_file())
        self.assertTrue((self.home / ".agents" / "skills" / "skill-manager" / "SKILL.md").is_file())

        # Idempotent re-run
        r2 = self.run_cli("install", "--apply", "--json")
        res2 = json.loads(r2.stdout)
        self.assertEqual(res2["linked"], 0)
        self.assertGreaterEqual(res2["skipped"], 4)

        # After init, skill-manager is adopted into skills-repo and links are upgraded;
        # doctor must report 0 problems and no false warning for skill-manager
        make_skill(self.home / ".claude" / "skills" / "demo", "demo", body="demo")
        self.run_cli("init", "--apply")
        repo = self.home / "skills-repo"
        self.assertTrue((repo / "skills" / "skill-manager" / "SKILL.md").is_file())
        self.assertFalse((repo / "skills" / "skill-manager" / ".git").exists())
        doc = json.loads(self.run_cli("doctor", "--json").stdout)
        self.assertTrue(doc["ok"], doc)
        self.assertFalse(any("skill-manager" in w for w in doc["warnings"]), doc["warnings"])

    def test_codex_direct_install_self_adopted_into_skills_repo(self):
        """Simulate Codex installing skill-manager directly into ~/.codex/skills/skill-manager
        (complete with a .git folder), then running init --apply from inside it."""
        import shutil
        codex_sm = self.home / ".codex" / "skills" / "skill-manager"
        (self.home / ".claude" / "skills").mkdir(parents=True)
        shutil.copytree(
            str(ROOT), str(codex_sm),
            ignore=shutil.ignore_patterns(".git", "__pycache__", ".skill-manager"),
        )
        # Put a real git repo inside codex_sm to simulate `git clone` by Codex
        subprocess.run(["git", "init", str(codex_sm)], check=True, capture_output=True)
        git_run(codex_sm, "remote", "add", "origin", "https://github.com/fengxbin/skill-manager.git")

        # Run init --apply using the copy living INSIDE ~/.codex/skills/skill-manager!
        codex_cli = codex_sm / "scripts" / "skillkit.py"
        r = subprocess.run(
            [sys.executable, str(codex_cli), "init", "--apply", "--json"],
            env=self.env, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        self.assertEqual(r.returncode, 0, "STDOUT:\n%s\nSTDERR:\n%s" % (r.stdout, r.stderr))
        data = json.loads(r.stdout)
        self.assertTrue(data["self_adopted"])
        self.assertIn("skill-manager", data["imported"])

        repo = self.home / "skills-repo"
        adopted = repo / "skills" / "skill-manager"
        self.assertTrue((adopted / "SKILL.md").is_file())
        # .git must be stripped so skills-repo has no broken nested gitlink
        self.assertFalse((adopted / ".git").exists())

        # Upstream URL must be saved in skill-manager.json.sources
        cfg = json.loads((repo / "skill-manager.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["sources"].get("skill-manager"), "https://github.com/fengxbin/skill-manager.git")

        # ~/.codex/skills/skill-manager must now be a link pointing to skills-repo/skills/skill-manager
        self.assertTrue(codex_sm.is_symlink() or _is_junction(codex_sm))
        self.assertTrue((codex_sm / "SKILL.md").is_file())
        # Other agents (claude + universal hub) also received links automatically
        self.assertTrue((self.home / ".claude" / "skills" / "skill-manager" / "SKILL.md").is_file())
        self.assertTrue((self.home / ".agents" / "skills" / "skill-manager" / "SKILL.md").is_file())

        # Doctor run from the adopted copy reports 0 problems
        r_doc = subprocess.run(
            [sys.executable, str(adopted / "scripts" / "skillkit.py"), "doctor", "--json"],
            env=self.env, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        self.assertEqual(r_doc.returncode, 0, r_doc.stderr)
        doc = json.loads(r_doc.stdout)
        self.assertTrue(doc["ok"], doc)
        self.assertEqual(doc["problems"], [])

    def test_init_no_adopt_self_keeps_skill_manager_external(self):
        make_skill(self.home / ".claude" / "skills" / "solo", "solo", body="solo")
        r = self.run_cli("init", "--no-adopt-self", "--apply", "--json")
        data = json.loads(r.stdout)
        self.assertFalse(data["self_adopted"])
        self.assertFalse((self.home / "skills-repo" / "skills" / "skill-manager").exists())
        doc = json.loads(self.run_cli("doctor", "--json").stdout)
        self.assertTrue(doc["ok"], doc)


if __name__ == "__main__":
    unittest.main()
