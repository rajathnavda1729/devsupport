import json
import sys
import unittest

from helpers import TOOLS, ToolTestCase

sys.path.insert(0, str(TOOLS))
import logwatch  # noqa: E402

LOG = """2026-10-07T10:00:00Z INFO server started on :8080
2026-10-07T10:00:01Z WARN slow request id=123 took 900ms
2026-10-07T10:00:02Z ERROR db failed for user 42: connection refused
Traceback (most recent call last):
  File "app.py", line 10, in handle
    raise ValueError("bad")
ValueError: bad
2026-10-07T10:00:03Z ERROR db failed for user 77: connection refused
{"level":"error","msg":"payment failed","order":9}
{"level":30,"msg":"ok"}
"""


class LogwatchUnitTest(unittest.TestCase):
    def test_signature_normalises_variable_parts(self):
        a = logwatch.signature("2026-10-07T10:00:02Z ERROR db failed for user 42")
        b = logwatch.signature("2026-10-07T11:00:02Z ERROR db failed for user 77")
        self.assertEqual(a, b)

    def test_rule_threshold_window(self):
        r = logwatch.Rule.from_dict({"name": "x", "pattern": "boom", "threshold": 2, "window_sec": 10})
        self.assertFalse(r.observe(0))
        self.assertTrue(r.observe(1))
        self.assertFalse(r.observe(2))   # cooldown within window
        self.assertFalse(r.observe(30))  # window reset: only 1 hit

    def test_norm_level(self):
        self.assertEqual(logwatch.norm_level("warning"), "WARN")
        self.assertEqual(logwatch.norm_level(50), "ERROR")
        self.assertIsNone(logwatch.norm_level("chatty"))


class LogwatchCliTest(ToolTestCase):
    def setUp(self):
        super().setUp()
        self.log = self.cwd / "app.log"
        self.log.write_text(LOG)

    def test_once_report_counts_and_signatures(self):
        report = self.cwd / "report.md"
        self.run_tool("logwatch.py", self.log, "--once", "--no-rules", "--report", report)
        text = report.read_text()
        self.assertIn("ERROR=4", text)  # 2 plain + ValueError line + json error
        self.assertIn("| 2 | ERROR |", text)  # two "db failed" lines grouped

    def test_fail_on_error(self):
        p = self.run_tool("logwatch.py", self.log, "--once", "--no-rules", "--fail-on", "ERROR", check=False)
        self.assertEqual(p.returncode, 1)
        ok = self.cwd / "ok.log"
        ok.write_text("INFO fine\n")
        self.assertEqual(self.run_tool("logwatch.py", ok, "--once", "--no-rules", "--fail-on", "ERROR").returncode, 0)

    def test_level_filter_and_traceback_grouping(self):
        out = self.run_tool("logwatch.py", self.log, "--once", "--no-rules", "--level", "ERROR").stdout
        self.assertNotIn("server started", out)
        self.assertIn('File "app.py"', out)  # continuation follows its ERROR header
        self.assertNotIn("slow request", out)

    def test_default_rules_fire_alerts(self):
        alerts = self.cwd / "alerts.jsonl"
        p = self.run_tool("logwatch.py", self.log, "--once", "--alerts-file", alerts, check=False)
        names = {json.loads(line)["rule"] for line in alerts.read_text().splitlines()}
        self.assertIn("unhandled-exception", names)
        self.assertEqual(p.returncode, 1)  # critical alert -> failure

    def test_config_profile_and_stdin(self):
        cfg = self.cwd / "profile.json"
        cfg.write_text(json.dumps({"rules": [{"name": "dup", "pattern": "duplicate_charge", "severity": "critical"}]}))
        p = self.run_tool("logwatch.py", "--stdin", "--config", cfg, "--no-rules",
                          stdin_text="INFO ok\nERROR duplicate_charge order=1\n", check=False)
        self.assertIn("ALERT [CRITICAL] dup", p.stderr)
        self.assertEqual(p.returncode, 1)

    def test_cmd_source(self):
        p = self.run_tool("logwatch.py", "--cmd", "echo 'WARN disk low'; echo 'INFO done'", "--no-rules")
        self.assertIn("WARN disk low", p.stdout)
        self.assertIn("WARN=1", p.stderr)


if __name__ == "__main__":
    unittest.main()
