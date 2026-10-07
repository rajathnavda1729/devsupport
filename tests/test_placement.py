"""Workspaces land in the target repo where the requirement is realised."""
import json
import unittest

from helpers import ToolTestCase


class PlacementTest(ToolTestCase):
    def setUp(self):
        super().setUp()
        (self.cwd / ".git").mkdir()                       # target repo root
        (self.cwd / "services" / "payments" / "src").mkdir(parents=True)

    def test_default_location_is_repo_root_even_from_subdir(self):
        sub = self.cwd / "services" / "payments" / "src"
        self.run_tool("scaffold.py", "new", "demo", "--text", "x", cwd=sub)
        self.assertTrue((self.cwd / "specs" / "demo" / "01-requirements" / "requirements.md").exists())
        self.assertFalse((sub / "specs").exists())

    def test_init_sets_repo_docs_location(self):
        self.run_tool("scaffold.py", "init", "--specs-dir", "docs/specs")
        self.run_tool("scaffold.py", "new", "demo", "--text", "x")
        self.assertTrue((self.cwd / "docs" / "specs" / "demo" / "02-design" / "hld.md").exists())
        self.assertIn("docs/specs/demo", self.run_tool("scaffold.py", "where", "demo").stdout)

    def test_at_module_places_and_registers_workspace(self):
        self.run_tool("scaffold.py", "new", "retry", "--at", "services/payments", "--text", "retry payments")
        ws = self.cwd / "services" / "payments" / "specs" / "retry"
        self.assertTrue((ws / "02-design" / "lld.md").exists())
        cfg = json.loads((self.cwd / ".devkit.json").read_text())
        self.assertEqual(cfg["features"]["retry"], "services/payments/specs/retry")
        # every tool finds it by slug, from anywhere in the repo
        self.run_tool("tracker.py", "-f", "retry", "add", "--title", "t", cwd=self.cwd / "services")
        self.assertTrue((ws / "03-delivery" / "TASKS.md").exists())
        self.run_tool("adr.py", "new", "--feature", "retry", "--title", "Use outbox")
        self.assertTrue(list((ws / "02-design" / "decisions").glob("ADR-0001-*.md")))
        self.assertIn(str(ws), self.run_tool("scaffold.py", "list").stdout)

    def test_at_rejects_missing_module_and_slug_clash(self):
        self.assertNotEqual(self.run_tool("scaffold.py", "new", "x", "--at", "nope", check=False).returncode, 0)
        self.run_tool("scaffold.py", "new", "dup", "--text", "x")
        p = self.run_tool("scaffold.py", "new", "dup", "--at", "services/payments", check=False)
        self.assertNotEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main()
