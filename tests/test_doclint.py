import json
import subprocess
import sys
import unittest

from helpers import ROOT, ToolTestCase


class DoclintTest(ToolTestCase):
    def setUp(self):
        super().setUp()
        self.run_tool("scaffold.py", "new", "demo", "--text", "x")
        self.hld = self.cwd / "specs/demo/02-design/hld.md"
        self.req = self.cwd / "specs/demo/01-requirements/requirements.md"

    def lint(self, path, check=False):
        return self.run_tool("doclint.py", path, check=check)

    def test_missing_section_is_error(self):
        self.hld.write_text(self.hld.read_text().replace("## 6. Data architecture", "### Data architecture"))
        p = self.lint(self.hld)
        self.assertEqual(p.returncode, 1)
        self.assertIn("missing section '## 6. Data architecture'", p.stdout)

    def test_extra_section_is_error(self):
        self.hld.write_text(self.hld.read_text() + "\n## 14. My own section\ntext\n")
        self.assertIn("extra section '## 14. My own section'", self.lint(self.hld).stdout)

    def test_changed_table_columns_is_error(self):
        self.req.write_text(self.req.read_text().replace("| ID | Requirement (The system shall…) | Actor |",
                                                         "| ID | Requirement | Actor |"))
        p = self.lint(self.req)
        self.assertEqual(p.returncode, 1)
        self.assertIn("table with columns", p.stdout)

    def test_mermaid_required_and_validated(self):
        text = self.hld.read_text()
        start = text.index("## 3. System context")
        end = text.index("## 4.")
        self.hld.write_text(text[:start] + "## 3. System context (C4 level 1)\nJust prose.\n\n" + text[end:])
        self.assertIn("mermaid diagram required", self.lint(self.hld).stdout)
        self.hld.write_text(text.replace("flowchart LR\n  user", "flowchat LR\n  user", 1))
        self.assertIn("does not start with a diagram type", self.lint(self.hld).stdout)

    def test_none_section_is_allowed(self):
        text = self.req.read_text()
        start = text.index("## 9. Dependencies")
        end = text.index("## 10.")
        self.req.write_text(text[:start] + "## 9. Dependencies\nNone — fully self-contained.\n\n" + text[end:])
        out = self.lint(self.req).stdout
        self.assertIn("0 error(s)", out)
        self.assertNotIn("9. Dependencies", out.split("unresolved TODO in:")[-1])

    def test_todo_blocks_approval(self):
        self.assertEqual(self.lint(self.hld).returncode, 0)
        self.hld.write_text(self.hld.read_text().replace("**Status:** Draft", "**Status:** Approved"))
        p = self.lint(self.hld)
        self.assertEqual(p.returncode, 1)
        self.assertIn("not allowed in status Approved", p.stdout)

    def test_invalid_status_and_h1(self):
        self.hld.write_text(self.hld.read_text().replace("**Status:** Draft", "**Status:** Done")
                            .replace("# High-Level Design —", "# HLD —"))
        out = self.lint(self.hld).stdout
        self.assertIn("**Status:** must be one of", out)
        self.assertIn("H1 must start with 'High-Level Design —'", out)

    def test_missing_marker(self):
        f = self.cwd / "loose.md"
        f.write_text("# free form\n")
        self.assertIn("missing devkit marker", self.lint(f).stdout)

    def test_generated_docs_skipped(self):
        self.run_tool("tracker.py", "-f", "demo", "add", "--title", "t")
        self.assertIn("0 error(s)", self.run_tool("doclint.py", "--feature", "demo").stdout)


class HookTest(ToolTestCase):
    def hook(self, name, file_path):
        return subprocess.run([sys.executable, str(ROOT / "devkit/hooks" / name)], cwd=self.cwd, text=True,
                              input=json.dumps({"tool_input": {"file_path": str(file_path)}}), capture_output=True)

    def test_guard_blocks_generated_files_only(self):
        self.run_tool("scaffold.py", "new", "demo", "--text", "x")
        self.run_tool("tracker.py", "-f", "demo", "add", "--title", "t")
        ws = self.cwd / "specs/demo"
        for f in ("03-delivery/TASKS.md", "03-delivery/tasks.json", "README.md"):
            self.assertEqual(self.hook("guard_generated.py", ws / f).returncode, 2, f)
        self.assertEqual(self.hook("guard_generated.py", ws / "02-design/hld.md").returncode, 0)

    def test_lint_hook_reports_template_drift_and_refreshes_index(self):
        self.run_tool("scaffold.py", "new", "demo", "--text", "x")
        hld = self.cwd / "specs/demo/02-design/hld.md"
        self.assertEqual(self.hook("lint_doc.py", hld).returncode, 0)
        hld.write_text(hld.read_text().replace("## 6. Data architecture", "## Data stuff"))
        p = self.hook("lint_doc.py", hld)
        self.assertEqual(p.returncode, 2)
        self.assertIn("missing section", p.stderr)
        self.assertTrue((self.cwd / "specs/demo/README.md").exists())


if __name__ == "__main__":
    unittest.main()
