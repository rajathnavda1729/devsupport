"""The `devkit` CLI: reviewable install/update/uninstall and command pass-through."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

CLI = ROOT / "bin" / "devkit"


class CliTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.repo = base / "repo"
        self.home = base / "home"
        self.repo.mkdir()
        self.home.mkdir()
        (self.repo / ".git").mkdir()
        self.env = {**os.environ, "HOME": str(self.home), "NO_COLOR": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        self.env.pop("DEVKIT_FEATURE", None)

    def tearDown(self):
        self._tmp.cleanup()

    def devkit(self, *args, check=True, cwd=None):
        p = subprocess.run([sys.executable, str(CLI), *map(str, args)], cwd=cwd or self.repo, env=self.env,
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
        if check and p.returncode != 0:
            self.fail(f"devkit {args} exited {p.returncode}\n{p.stdout}\n{p.stderr}")
        return p

    def manifest(self, root=None):
        return json.loads(((root or self.repo / ".claude") / "devkit-install.json").read_text())

    def test_dry_run_writes_nothing(self):
        out = self.devkit("install", "--dry-run").stdout
        self.assertIn("+ new       .claude/skills/devkit/SKILL.md", out)
        self.assertIn("merge     .claude/settings.json", out)
        self.assertEqual(sorted(p.name for p in self.repo.iterdir()), [".git"])

    def test_requires_confirmation_when_not_interactive(self):
        p = self.devkit("install", check=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn("re-run with --yes", p.stderr)
        self.assertFalse((self.repo / ".claude").exists())

    def test_install_project(self):
        (self.repo / "CLAUDE.md").write_text("# My service\nkeep me\n")
        sp = self.repo / ".claude" / "settings.json"
        sp.parent.mkdir()
        sp.write_text(json.dumps({"permissions": {"allow": ["Bash(npm test:*)"]},
                                  "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "mine.sh"}]}]}}))
        self.devkit("install", "--yes", "--specs-dir", "docs/specs")
        for rel in (".claude/skills/devkit/SKILL.md", ".claude/agents/decision-challenger.md",
                    ".claude/rules/review-before-implementing.md", "devkit/tools/review.py",
                    "devkit/hooks/lint_doc.py", "devkit/README-DEVKIT.md"):
            self.assertTrue((self.repo / rel).exists(), rel)
        self.assertTrue(os.access(self.repo / "devkit/tools/tracker.py", os.X_OK))
        settings = json.loads(sp.read_text())
        self.assertIn("Bash(npm test:*)", settings["permissions"]["allow"])
        self.assertIn("Bash(python3 devkit/tools/review.py:*)", settings["permissions"]["allow"])
        commands = [h["command"] for g in settings["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertIn("mine.sh", commands)
        self.assertTrue(any("guard_generated.py" in c for c in commands))
        claude_md = (self.repo / "CLAUDE.md").read_text()
        self.assertTrue(claude_md.startswith("# My service\nkeep me"))
        self.assertIn("<!-- devkit:begin -->", claude_md)
        self.assertEqual(json.loads((self.repo / ".devkit.json").read_text())["specs_dir"], "docs/specs")
        self.assertTrue((self.repo / "docs/adr/decision-log.md").exists())  # adr scan ran
        self.assertIn("already up to date", self.devkit("install").stdout)

    def test_local_edits_are_conflicts_not_overwritten(self):
        self.devkit("install", "--yes")
        skill = self.repo / ".claude/skills/hld/SKILL.md"
        skill.write_text(skill.read_text() + "\nour team note\n")
        out = self.devkit("update", "--yes").stdout
        self.assertIn("conflict  .claude/skills/hld/SKILL.md", out)
        self.assertIn("our team note", skill.read_text())
        self.assertIn("-our team note", self.devkit("diff", "hld").stdout)
        self.devkit("update", "--yes", "--force")
        self.assertNotIn("our team note", skill.read_text())

    def test_update_replaces_untouched_files_from_older_version(self):
        self.devkit("install", "--yes")
        skill = self.repo / ".claude/skills/lld/SKILL.md"
        skill.write_text("old version of the skill\n")  # simulate a file from a previous devkit release
        m = self.manifest()
        m["files"][".claude/skills/lld/SKILL.md"] = hashlib.sha256(b"old version of the skill\n").hexdigest()[:16]
        (self.repo / ".claude/devkit-install.json").write_text(json.dumps(m))
        out = self.devkit("update", "--yes").stdout
        self.assertIn("~ update    .claude/skills/lld/SKILL.md", out)
        self.assertNotIn("old version", skill.read_text())

    def test_uninstall_keeps_user_content(self):
        (self.repo / "CLAUDE.md").write_text("# Mine\n")
        self.devkit("install", "--yes")
        self.devkit("new", "demo", "--text", "x")
        edited = self.repo / ".claude/skills/hld/SKILL.md"
        edited.write_text("customised\n")
        self.devkit("uninstall", "--yes")
        self.assertFalse((self.repo / "devkit/tools").exists())
        self.assertFalse((self.repo / ".claude/skills/devkit").exists())
        self.assertTrue(edited.exists())                                  # edited locally -> kept
        self.assertTrue((self.repo / "specs/demo/02-design/hld.md").exists())  # workspaces untouched
        self.assertEqual((self.repo / "CLAUDE.md").read_text(), "# Mine\n")
        self.assertFalse((self.repo / ".claude/settings.json").exists())   # only devkit entries were there

    def test_user_scope(self):
        self.devkit("install", "--user", "--yes")
        claude = self.home / ".claude"
        self.assertTrue((claude / "skills/devkit/SKILL.md").exists())
        self.assertTrue((claude / "agents/decision-challenger.md").exists())
        self.assertFalse((claude / "devkit").exists())
        self.assertEqual(self.manifest(claude)["scope"], "user")
        p = self.devkit("install", "--user", "--only", "tools", check=False)
        self.assertNotEqual(p.returncode, 0)

    def test_refuses_kit_repo_as_target(self):
        p = self.devkit("install", "--dry-run", "--target", ROOT, check=False)
        self.assertNotEqual(p.returncode, 0)

    def test_passthrough_and_review_gate(self):
        self.devkit("install", "--yes")
        self.devkit("new", "demo", "--text", "Retry payments")
        self.assertIn("specs/demo", self.devkit("where", "demo").stdout)
        self.devkit("task", "-f", "demo", "add", "--title", "Build", "--type", "feature")
        p = self.devkit("task", "-f", "demo", "start", "T-001", check=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("not ready for implementation", p.stderr)
        p = self.devkit("review", "demo", check=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn("NOT READY", p.stdout)
        self.assertIn("0 error(s)", self.devkit("lint", "--feature", "demo").stdout)
        self.assertIn("found 0 ADR(s)", self.devkit("adr", "scan").stdout)

    def test_doctor_and_help(self):
        self.assertIn("devkit install", self.devkit("--help").stdout)
        self.devkit("install", "--yes")
        out = self.devkit("doctor").stdout
        self.assertIn("all files present", out)
        self.assertIn("settings.json has devkit hooks", out)


if __name__ == "__main__":
    unittest.main()
