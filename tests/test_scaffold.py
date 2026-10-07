import json
import unittest

from helpers import ToolTestCase


class ScaffoldTest(ToolTestCase):
    def test_new_creates_grouped_workspace(self):
        self.run_tool("scaffold.py", "new", "url-shortener", "--text", "Shorten URLs for marketing")
        d = self.cwd / "specs" / "url-shortener"
        for name in ("01-requirements/input.md", "01-requirements/requirements.md", "02-design/solutioning.md",
                     "02-design/hld.md", "02-design/lld.md", "02-design/reviews/design-review.md",
                     "03-delivery/tasks.json", "03-delivery/execution-plan.md", "04-quality/testing-guide.md",
                     "04-quality/test-plan.md", "04-quality/benchmark-plan.md", "README.md"):
            self.assertTrue((d / name).exists(), name)
        for sub in ("02-design/decisions", "04-quality/benchmarks"):
            self.assertTrue((d / sub).is_dir(), sub)
        self.assertFalse((d / "04-quality" / "test-report.md").exists())  # on demand only
        self.assertIn("Shorten URLs for marketing", (d / "01-requirements" / "input.md").read_text())
        hld = (d / "02-design" / "hld.md").read_text()
        self.assertTrue(hld.startswith("<!-- devkit:doc type=hld v=1 -->"))
        self.assertNotIn("{{", hld)
        self.assertIn("specs/url-shortener/04-quality/benchmarks", (d / "04-quality" / "benchmark-plan.md").read_text())

    def test_skeleton_passes_doclint(self):
        self.run_tool("scaffold.py", "new", "demo", "--text", "x")
        out = self.run_tool("doclint.py").stdout
        self.assertIn("0 error(s)", out)

    def test_new_does_not_overwrite_without_force(self):
        self.run_tool("scaffold.py", "new", "demo", "--text", "x")
        req = self.cwd / "specs" / "demo" / "01-requirements" / "requirements.md"
        req.write_text("custom")
        out = self.run_tool("scaffold.py", "new", "demo", "--text", "x").stdout
        self.assertIn("kept existing", out)
        self.assertEqual(req.read_text(), "custom")

    def test_rejects_bad_slug(self):
        p = self.run_tool("scaffold.py", "new", "Bad Slug", check=False)
        self.assertNotEqual(p.returncode, 0)

    def test_status_reports_draft_and_next_step(self):
        self.run_tool("scaffold.py", "new", "demo", "--text", "x")
        out = self.run_tool("scaffold.py", "status", "demo").stdout
        self.assertIn("draft", out)
        self.assertIn("next step: 01-requirements/requirements.md", out)

    def test_doc_creates_on_demand_type(self):
        self.run_tool("scaffold.py", "new", "demo", "--text", "x")
        out = self.run_tool("scaffold.py", "doc", "demo", "test-report").stdout
        self.assertIn("created", out)
        self.assertTrue((self.cwd / "specs/demo/04-quality/test-report.md").exists())
        self.assertNotEqual(self.run_tool("scaffold.py", "doc", "demo", "board", check=False).returncode, 0)

    def test_index_lists_groups_and_decisions(self):
        self.run_tool("scaffold.py", "new", "demo", "--text", "x")
        self.run_tool("adr.py", "new", "--feature", "demo", "--title", "Use outbox")
        self.run_tool("scaffold.py", "index", "demo")
        index = (self.cwd / "specs/demo/README.md").read_text()
        for heading in ("Requirements — `01-requirements/`", "Design & decisions — `02-design/`",
                        "Delivery — `03-delivery/`", "Quality — `04-quality/`"):
            self.assertIn(heading, index)
        self.assertIn("ADR-0001", index)
        self.assertIn("tracker.py -f demo board", index)

    def test_index_never_overwrites_human_readme(self):
        self.run_tool("scaffold.py", "new", "demo", "--text", "x")
        readme = self.cwd / "specs/demo/README.md"
        readme.write_text("# my notes\n")
        self.run_tool("scaffold.py", "index", "demo")
        self.assertEqual(readme.read_text(), "# my notes\n")

    def test_migrate_flat_workspace(self):
        old = self.cwd / "specs" / "legacy"
        (old / "adr").mkdir(parents=True)
        (old / "00-input.md").write_text("# Raw Requirement — Legacy\nold input\n")
        (old / "03-hld.md").write_text("# High-Level Design — Legacy\n")
        (old / "tasks.json").write_text(json.dumps({"feature": "legacy", "tasks": []}))
        (old / "adr" / "ADR-001-x.md").write_text("# ADR-001: X\n**Status:** Accepted\n")
        self.assertNotEqual(self.run_tool("scaffold.py", "status", "legacy", check=False).returncode, 0)
        self.run_tool("scaffold.py", "migrate", "legacy")
        self.assertTrue((old / "01-requirements/input.md").read_text().startswith("<!-- devkit:doc type=input"))
        self.assertTrue((old / "02-design/hld.md").exists())
        self.assertTrue((old / "03-delivery/tasks.json").exists())
        self.assertTrue((old / "02-design/decisions/ADR-001-x.md").exists())
        self.assertFalse((old / "00-input.md").exists())
        self.run_tool("scaffold.py", "status", "legacy")

    def test_types_lists_all_templates(self):
        out = self.run_tool("scaffold.py", "types").stdout
        for t in ("requirements", "hld", "lld", "design-review", "test-report", "execution-plan"):
            self.assertIn(t, out)


if __name__ == "__main__":
    unittest.main()
