import json
import unittest

from helpers import ToolTestCase

REQS = """# Requirements
| ID | Requirement | Actor | Priority | Criticality |
|----|-------------|-------|----------|-------------|
| FR-001 | The system shall create links | User | Must | CRITICAL |
| FR-002 | The system shall list links | User | Should | Medium |
| NFR-001 | p95 under 150ms | - | Must | High |
"""

TESTS = """| ID | Title | Requirements |
|----|-------|--------------|
| TC-001 | create | FR-001 |
| TC-002 | perf | NFR-001 |
"""


class TrackerTest(ToolTestCase):
    def setUp(self):
        super().setUp()
        self.run_tool("scaffold.py", "new", "demo", "--text", "x")
        self.fdir = self.cwd / "specs" / "demo"
        # tracker mechanics only; the readiness gate has its own tests (test_review.py)
        (self.cwd / ".devkit.json").write_text(json.dumps({"gates": {"implementation": False}}))

    def t(self, *args, check=True):
        return self.run_tool("tracker.py", "-f", "demo", *args, check=check)

    def import_tasks(self, tasks):
        f = self.cwd / "draft.json"
        f.write_text(json.dumps({"tasks": tasks}))
        return self.t("import", f)

    def test_add_assigns_ids_and_renders_board(self):
        self.t("add", "--title", "First", "--reqs", "FR-001", "-a", "works")
        self.t("add", "--title", "Second", "--deps", "T-001")
        data = json.loads((self.fdir / "03-delivery" / "tasks.json").read_text())
        self.assertEqual([t["id"] for t in data["tasks"]], ["T-001", "T-002"])
        board = (self.fdir / "03-delivery" / "TASKS.md").read_text()
        self.assertIn("Ready to start", board)
        self.assertIn("T001 --> T002", board)

    def test_next_respects_dependencies_and_priority(self):
        self.import_tasks([
            {"id": "T-001", "title": "a", "priority": "P2"},
            {"id": "T-002", "title": "b", "priority": "P0"},
            {"id": "T-003", "title": "c", "priority": "P0", "depends_on": ["T-001"]},
        ])
        out = self.t("next").stdout.splitlines()
        self.assertTrue(out[0].startswith("T-002"))
        self.assertFalse(any(line.startswith("T-003") for line in out))
        self.t("done", "T-001")
        self.assertIn("T-003", self.t("next").stdout)

    def test_start_blocks_on_unfinished_deps(self):
        self.import_tasks([{"id": "T-001", "title": "a"}, {"id": "T-002", "title": "b", "depends_on": "T-001"}])
        p = self.t("start", "T-002", check=False)
        self.assertNotEqual(p.returncode, 0)
        self.t("start", "T-002", "--force", "--note", "pairing on it")

    def test_block_requires_note(self):
        self.import_tasks([{"id": "T-001", "title": "a"}])
        self.assertNotEqual(self.t("block", "T-001", check=False).returncode, 0)
        self.t("block", "T-001", "--note", "waiting")
        self.assertIn("waiting", (self.fdir / "03-delivery" / "TASKS.md").read_text())

    def test_waves_and_critical_path(self):
        self.import_tasks([
            {"id": "T-001", "title": "a", "estimate": "S"},
            {"id": "T-002", "title": "b", "estimate": "L", "depends_on": ["T-001"]},
            {"id": "T-003", "title": "c", "estimate": "XS", "depends_on": ["T-001"]},
            {"id": "T-004", "title": "d", "estimate": "M", "depends_on": ["T-002", "T-003"]},
        ])
        data = json.loads(self.t("waves", "--json").stdout)
        self.assertEqual(data["waves"], [["T-001"], ["T-002", "T-003"], ["T-004"]])
        self.assertEqual(data["critical_path"], ["T-001", "T-002", "T-004"])
        self.assertEqual(data["critical_path_points"], 9)

    def test_validate_detects_cycle_and_unknown_dep(self):
        self.import_tasks([
            {"id": "T-001", "title": "a", "depends_on": ["T-002"]},
            {"id": "T-002", "title": "b", "depends_on": ["T-001"]},
            {"id": "T-003", "title": "c", "depends_on": ["T-999"]},
        ])
        p = self.t("validate", check=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn("cycle", p.stdout)
        self.assertIn("unknown task T-999", p.stdout)

    def test_validate_requires_critical_coverage(self):
        (self.fdir / "01-requirements" / "requirements.md").write_text(REQS)
        (self.fdir / "04-quality" / "test-plan.md").write_text(TESTS)
        self.import_tasks([{"id": "T-001", "title": "list", "requirements": ["FR-002"], "acceptance": ["ok"]}])
        p = self.t("validate", check=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn("critical requirement FR-001 has no task", p.stdout)
        self.import_tasks([{"id": "T-002", "title": "create", "requirements": ["FR-001"], "acceptance": ["ok"]}])
        p = self.t("validate", check=False)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn("FR-002 has no test", p.stdout)  # non-critical gap is only a warning

    def test_trace_writes_matrix(self):
        (self.fdir / "01-requirements" / "requirements.md").write_text(REQS)
        (self.fdir / "04-quality" / "test-plan.md").write_text(TESTS)
        self.import_tasks([{"id": "T-001", "title": "create", "requirements": ["FR-001"]}])
        self.t("trace")
        matrix = (self.fdir / "04-quality" / "traceability.md").read_text()
        self.assertIn("| FR-001 | 🔴 yes | T-001 | TC-001 | ✅ |", matrix)

    def test_import_updates_existing(self):
        self.import_tasks([{"id": "T-001", "title": "a"}])
        self.t("start", "T-001")
        self.import_tasks([{"id": "T-001", "title": "a renamed"}])
        task = json.loads(self.t("show", "T-001").stdout)
        self.assertEqual(task["title"], "a renamed")
        self.assertEqual(task["status"], "in_progress")

    def test_rejects_invalid_enum(self):
        f = self.cwd / "bad.json"
        f.write_text(json.dumps([{"title": "x", "priority": "urgent"}]))
        self.assertNotEqual(self.t("import", f, check=False).returncode, 0)


if __name__ == "__main__":
    unittest.main()
