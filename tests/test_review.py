"""Decision evaluation + implementation-readiness gate."""
import json
import re
import unittest

from helpers import ToolTestCase

MATRIX = """| Criterion (linked req) | Weight | Option A | Option B | Option C |
|------------------------|--------|----------|----------|----------|
| Latency (NFR-001) | 50 | {a1} | {b1} | n/a |
| Simplicity | 30 | {a2} | {b2} | n/a |
| Cost | 20 | {a3} | {b3} | n/a |
| **Total** | **100** | | | |"""

ADR_FILL = {
    "## Context\n": "## Context\nRetries are needed for transient card failures (FR-001).\n",
    "## Decision drivers\n": "## Decision drivers\n- NFR-001 latency\n",
    "## Considered options\n": "## Considered options\n1. Fixed delay\n2. Exponential backoff with jitter\n",
    "## Decision\n": "## Decision\nWe will use exponential backoff with full jitter, max 3 attempts.\n",
    "## Compliance & evidence\n": "## Compliance & evidence\nRetryPolicy class; unit test test_backoff.\n",
    "## Revisit when\n": "## Revisit when\nRetry success rate < 50%.\n",
    "## Related\n": "## Related\nFR-001\n",
}
EVAL = """## Evaluation
- **Comparison:** see ../solutioning.md §6 (A 4.3 vs B 3.1)
- **Sensitivity:** robust to ±20% weights
- **Evidence quality:** measured — benchmarks/optA.json
- **Reversibility:** two-way door; swap policy class
- **Pre-mortem:** retry storms during outage; mitigated by circuit breaker and caps
- **Challenge:** "fixed delay is simpler" — rejected, causes synchronized retries
"""


def fill_todos(text: str) -> str:
    text = re.sub(r"<!--\s*TODO.*?-->", "Filled in.", text, flags=re.S)
    return text.replace("**Status:** Draft", "**Status:** Approved")


class ReviewTestBase(ToolTestCase):
    def setUp(self):
        super().setUp()
        (self.cwd / ".git").mkdir()
        self.run_tool("scaffold.py", "new", "pay", "--text", "Retry failed payments")
        self.ws = self.cwd / "specs" / "pay"
        self.pristine_solutioning = (self.ws / "02-design/solutioning.md").read_text()

    def doc(self, rel):
        return self.ws / rel

    def write_solutioning(self, a=(5, 4, 4), b=(3, 3, 3), recommendation="We choose Option A.", poc_result=""):
        p = self.doc("02-design/solutioning.md")
        t = self.pristine_solutioning
        t = t.replace("<!-- TODO: | ADR-0003 | Use PostgreSQL for transactional data | Accepted | constrains | rules out a document store for orders | -->",
                      "None relevant — searched: payments, retry")
        t = t.replace("### Option A — <!-- TODO: name -->", "### Option A — Backoff in service")
        t = t.replace("### Option B — <!-- TODO: name -->", "### Option B — Retry queue")
        start = t.index("| Criterion (linked req)")
        end = t.index("| **Total** | **100** | | | |") + len("| **Total** | **100** | | | |")
        t = t[:start] + MATRIX.format(a1=a[0], a2=a[1], a3=a[2], b1=b[0], b2=b[1], b3=b[2]) + t[end:]
        t = t.replace("| Pattern | Problem signal it addresses | Fit (✅ adopt / 🤔 maybe / ❌ reject) | Reason | Requirements served |\n"
                      "|---------|-----------------------------|----------------------------------------|--------|---------------------|\n<!-- TODO -->",
                      "| Pattern | Problem signal it addresses | Fit (✅ adopt / 🤔 maybe / ❌ reject) | Reason | Requirements served |\n"
                      "|---------|-----------------------------|----------------------------------------|--------|---------------------|\n"
                      "| Retry + backoff | transient failures | ✅ adopt | simplest | FR-001 |\n"
                      "| Saga | multi-service txn | ❌ reject | single service | - |")
        if poc_result:
            t = t.replace("| Experiment | Option(s) | Command / endpoint | Metric | Pass criterion | Result |\n"
                          "|------------|-----------|--------------------|--------|----------------|--------|\n<!-- TODO -->",
                          "| Experiment | Option(s) | Command / endpoint | Metric | Pass criterion | Result |\n"
                          "|------------|-----------|--------------------|--------|----------------|--------|\n"
                          f"| retry latency | A, B | bench.py cmd | p95 | ≤ 200 ms | {poc_result} |")
        rec_start = t.index("## 9. Recommendation")
        rec_end = t.index("## 10.")
        t = t[:rec_start] + f"## 9. Recommendation\n{recommendation}\n\n" + t[rec_end:]
        p.write_text(fill_todos(t))

    def make_adr(self, accept=True, evaluated=True):
        path = self.run_tool("adr.py", "new", "--feature", "pay", "--title", "Exponential backoff").stdout.splitlines()[0]
        text = open(path).read()
        for k, v in ADR_FILL.items():
            text = text.replace(k, v, 1)
        if evaluated:
            start = text.index("## Evaluation")
            end = text.index("## Decision\n")
            text = text[:start] + EVAL + "\n" + text[end:]
            text = text.replace("- **Negative / accepted trade-offs:** <!-- TODO -->",
                                "- **Negative / accepted trade-offs:** slower final failure")
        text = re.sub(r"<!--\s*TODO.*?-->", "", text, flags=re.S)
        open(path, "w").write(text)
        if accept:
            self.run_tool("adr.py", "set-status", "ADR-0001", "accepted")
        return path

    def make_ready(self):
        for rel in ("01-requirements/requirements.md", "02-design/hld.md", "02-design/lld.md",
                    "03-delivery/execution-plan.md", "04-quality/test-plan.md"):
            self.doc(rel).write_text(fill_todos(self.doc(rel).read_text()))
        self.write_solutioning()
        self.make_adr()
        sol = self.doc("02-design/solutioning.md")
        sol.write_text(sol.read_text().replace("## 10. New decisions (ADRs written for this feature)\n",
                                               "## 10. New decisions (ADRs written for this feature)\nADR-0001 backoff.\n"))
        rv = self.doc("02-design/reviews/design-review.md")
        t = rv.read_text().replace("<!-- TODO: APPROVE | APPROVE WITH CHANGES | REWORK — one paragraph of rationale -->",
                                   "APPROVE — design covers all requirements.")
        rv.write_text(fill_todos(t))
        self.run_tool("tracker.py", "-f", "pay", "add", "--title", "Retry worker", "--type", "feature",
                      "-a", "retries 3 times")
        self.run_tool("tracker.py", "-f", "pay", "add", "--title", "Spike: provider error codes", "--type", "spike")


class MatrixTest(ReviewTestBase):
    def matrix(self):
        return self.run_tool("review.py", "matrix", "pay", check=False)

    def test_clear_winner_is_robust(self):
        self.write_solutioning()
        p = self.matrix()
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn("Option A", p.stdout)
        self.assertIn("robust", p.stdout)

    def test_close_call_needs_evidence_or_override(self):
        self.write_solutioning(a=(4, 3, 3), b=(4, 3, 3.5))  # A=350, B=360 -> B wins by <10%
        p = self.matrix()
        self.assertIn("recommends Option A but the matrix winner is Option B", p.stdout)
        self.write_solutioning(a=(4, 3, 3), b=(4, 3, 3.5), recommendation="We choose Option B.")
        self.assertIn("close call", self.matrix().stdout)
        self.write_solutioning(a=(4, 3, 3), b=(4, 3, 3.5), recommendation="We choose Option B.", poc_result="B p95 120 ms ✅")
        self.assertEqual(self.matrix().returncode, 0)

    def test_close_call_with_unmeasured_experiment_needs_fallback(self):
        self.write_solutioning(a=(4, 3, 3), b=(4, 3, 3.5), recommendation="We choose Option B.", poc_result="B p95 120 ms ✅")
        sol = self.doc("02-design/solutioning.md")
        rows = "| retry latency | A, B | bench.py cmd | p95 | ≤ 200 ms | B p95 120 ms ✅ |"
        sol.write_text(sol.read_text().replace(rows, rows + "\n| full load | B | staging | p95 | ≤ 50 ms | not run — needs staging |"))
        self.assertIn("depends on unmeasured experiment(s): full load", self.matrix().stdout)
        sol.write_text(sol.read_text().replace("We choose Option B.", "We choose Option B.\n**Fallback:** switch to A if staging fails."))
        self.assertEqual(self.matrix().returncode, 0)

    def test_sensitivity_flip_detected(self):
        # A wins on latency only; B wins the rest. Shifting latency weight flips the winner.
        self.write_solutioning(a=(5, 2, 2), b=(2, 5, 5))
        out = self.matrix().stdout
        self.assertIn("FRAGILE", out)

    def test_decisive_scores_reported(self):
        self.write_solutioning(a=(4, 3, 3), b=(4, 3, 3.5), recommendation="We choose Option B.", poc_result="B ok")
        out = self.matrix().stdout
        self.assertIn("decisive score", out)
        self.assertIn("Option B 'Cost' 3.5→2.5", out)
        self.write_solutioning()  # clear winner: A 5,4,4 vs B 3,3,3
        self.assertIn("score sensitivity (±1 per cell): robust", self.matrix().stdout)

    def test_override_is_accepted_explicitly(self):
        self.write_solutioning(a=(5, 4, 4), b=(3, 3, 3),
                               recommendation="We choose Option B.\n**Override:** B reuses the platform queue team owns.")
        self.assertEqual(self.matrix().returncode, 0)

    def test_weights_must_sum_to_100(self):
        self.write_solutioning()
        sol = self.doc("02-design/solutioning.md")
        sol.write_text(sol.read_text().replace("| Cost | 20 |", "| Cost | 10 |"))
        self.assertIn("weights sum to 90", self.matrix().stdout)


class DecisionTest(ReviewTestBase):
    def test_fresh_adr_has_gaps(self):
        self.run_tool("adr.py", "new", "--feature", "pay", "--title", "Raw")
        p = self.run_tool("review.py", "decision", "1", check=False)
        self.assertEqual(p.returncode, 1)
        for gap in ("'Context' is empty", "at least 2 required", "Evaluation 'Pre-mortem'", "no negative"):
            self.assertIn(gap, p.stdout)

    def test_placeholder_and_multiline_values(self):
        path = self.make_adr(accept=False)
        text = open(path).read()
        text = text.replace("- **Challenge:** \"fixed delay is simpler\" — rejected, causes synchronized retries",
                            "- **Challenge:** pending the challenger review")
        text = text.replace("- **Comparison:** see ../solutioning.md §6 (A 4.3 vs B 3.1)",
                            "- **Comparison:**\n  - Option 1 wins on latency\n  - Option 2 loses on cost")
        open(path, "w").write(text)
        out = self.run_tool("review.py", "decision", "1", check=False).stdout
        self.assertIn("Evaluation 'Challenge' is a placeholder", out)
        self.assertNotIn("'Comparison'", out)  # continuation lines count as content

    def test_evaluated_adr_passes(self):
        self.make_adr()
        p = self.run_tool("review.py", "decision", "ADR-0001", check=False)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn("thoroughly evaluated", p.stdout)


class ReadinessGateTest(ReviewTestBase):
    def test_fresh_feature_not_ready_and_start_blocked(self):
        p = self.run_tool("review.py", "readiness", "pay", check=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn("NOT READY", p.stdout)
        report = self.doc("03-delivery/readiness.md").read_text()
        self.assertIn("devkit:doc type=readiness v=1 generated", report)
        self.run_tool("tracker.py", "-f", "pay", "add", "--title", "Build it", "--type", "feature")
        p = self.run_tool("tracker.py", "-f", "pay", "start", "T-001", check=False)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("not ready for implementation", p.stderr)

    def test_spike_exempt_and_force_requires_note(self):
        self.run_tool("tracker.py", "-f", "pay", "add", "--title", "Spike", "--type", "spike")
        self.run_tool("tracker.py", "-f", "pay", "start", "T-001")
        self.run_tool("tracker.py", "-f", "pay", "add", "--title", "Build", "--type", "feature")
        self.assertNotEqual(self.run_tool("tracker.py", "-f", "pay", "start", "T-002", "--force", check=False).returncode, 0)
        self.run_tool("tracker.py", "-f", "pay", "start", "T-002", "--force", "--note", "hotfix approved by lead")
        task = json.loads(self.run_tool("tracker.py", "-f", "pay", "show", "T-002").stdout)
        self.assertIn("READINESS GATE BYPASSED", task["notes"][-1])
        self.assertIn("hotfix approved by lead", task["notes"][-1])

    def test_fully_reviewed_feature_is_ready(self):
        self.make_ready()
        p = self.run_tool("review.py", "readiness", "pay", "-v", check=False)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.run_tool("tracker.py", "-f", "pay", "start", "T-001")

    def test_rejected_decision_does_not_block(self):
        self.make_ready()
        self.run_tool("adr.py", "new", "--feature", "pay", "--title", "Rejected alternative")
        self.run_tool("adr.py", "set-status", "2", "rejected")
        p = self.run_tool("review.py", "readiness", "pay", check=False)
        self.assertEqual(p.returncode, 0, p.stdout)

    def test_unaccepted_decision_blocks(self):
        self.make_ready()
        self.run_tool("adr.py", "set-status", "1", "proposed")
        p = self.run_tool("review.py", "readiness", "pay", check=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn("is Proposed — the user must accept it", p.stdout)

    def test_blocking_open_question_blocks(self):
        self.make_ready()
        req = self.doc("01-requirements/requirements.md")
        t = req.read_text()
        header = "|---|----------|-----------|----------|--------|\n"
        req.write_text(t.replace(header, header + "| Q1 | Are rewards paid from the board? | Yes | Live Ops | Open |\n"
                                         "| Q2 | Nice to have colours? | No | UX | Open |\n", 1))
        out = self.run_tool("review.py", "readiness", "pay", check=False).stdout
        self.assertIn("blocking question Q1 unanswered", out)
        self.assertNotIn("Q2", out)

    def test_unresolved_blocking_finding_blocks(self):
        self.make_ready()
        rv = self.doc("02-design/reviews/design-review.md")
        t = rv.read_text()
        header = "|---|------------|---------|-------------------|---------------|----------|\n"
        t = t.replace(header + "Filled in.", header + "| 1 | hld §5 | no timeout on provider call | FR-001 | add 2s timeout | no |", 1)
        rv.write_text(t)
        p = self.run_tool("review.py", "readiness", "pay", check=False)
        self.assertIn("blocking finding #1 unresolved", p.stdout)


if __name__ == "__main__":
    unittest.main()
