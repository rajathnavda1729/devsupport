import http.server
import json
import sys
import threading
import unittest

from helpers import TOOLS, ToolTestCase

sys.path.insert(0, str(TOOLS))
import bench  # noqa: E402


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        code = 500 if self.path == "/fail" else 200
        self.send_response(code)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


class BenchUnitTest(unittest.TestCase):
    def test_percentile_interpolates(self):
        vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        self.assertEqual(bench.percentile(vals, 0.5), 5.5)
        self.assertEqual(bench.percentile(vals, 0), 1)
        self.assertEqual(bench.percentile(vals, 1), 10)

    def test_summarize_error_rate(self):
        s = bench.summarize([10.0, 20.0, 30.0], errors=1, wall_s=1.0)
        self.assertEqual(s["count"], 4)
        self.assertEqual(s["error_rate"], 0.25)
        self.assertEqual(s["p50_ms"], 20.0)
        self.assertEqual(s["throughput_rps"], 3.0)


class BenchCliTest(ToolTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_cmd_benchmark_with_slo(self):
        out = self.cwd / "r.json"
        self.run_tool("bench.py", "cmd", "--name", "true", "-n", "5", "--warmup", "1",
                      "--slo", "error_rate<=0", "--out", out, "true")
        r = json.loads(out.read_text())
        self.assertEqual(r["stats"]["ok"], 5)
        self.assertTrue(r["passed"])

    def test_failing_slo_exits_nonzero(self):
        p = self.run_tool("bench.py", "cmd", "--name", "f", "-n", "3", "--warmup", "0",
                          "--slo", "error_rate<=0", "false", check=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn("FAIL", p.stdout)

    def test_http_benchmark(self):
        out = self.cwd / "h.json"
        self.run_tool("bench.py", "http", "--name", "get", "--url", self.url + "/", "-n", "40", "-c", "4",
                      "--slo", "p95_ms<=2000", "--out", out)
        self.assertEqual(json.loads(out.read_text())["stats"]["errors"], 0)
        p = self.run_tool("bench.py", "http", "--name", "bad", "--url", self.url + "/fail", "-n", "5",
                          "--slo", "error_rate<=0.1", check=False)
        self.assertEqual(p.returncode, 1)

    def _result(self, name, **stats):
        base = {"p50_ms": 10, "p95_ms": 20, "p99_ms": 30, "throughput_rps": 100, "error_rate": 0}
        base.update(stats)
        path = self.cwd / f"{name}.json"
        path.write_text(json.dumps({"name": name, "kind": "cmd", "stats": base, "slo": [], "passed": True}))
        return path

    def test_compare_detects_regression(self):
        base = self._result("base")
        same = self._result("same", p95_ms=21)
        slow = self._result("slow", p95_ms=40)
        self.assertEqual(self.run_tool("bench.py", "compare", base, same, check=False).returncode, 0)
        p = self.run_tool("bench.py", "compare", base, slow, check=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn("regressions: p95_ms", p.stdout)

    def test_report_lists_all(self):
        a, b = self._result("optA", p95_ms=15), self._result("optB", p95_ms=25)
        out = self.run_tool("bench.py", "report", a, b, "--out", self.cwd / "R.md").stdout
        self.assertIn("**Fastest p95:** optA", out)


if __name__ == "__main__":
    unittest.main()
