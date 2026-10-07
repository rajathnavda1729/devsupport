#!/usr/bin/env python3
"""devkit benchmark harness (stdlib only).

Measures latency/throughput of a shell command or an HTTP endpoint, gates the
result against SLOs taken from NFRs, compares runs to catch regressions, and
renders side-by-side reports for comparing candidate solutions.

Examples:
  bench.py cmd  --name sort-v1 -n 30 --warmup 3 "python3 sort.py data.txt" --out specs/x/benchmarks/sort-v1.json
  bench.py http --name create-link --url http://localhost:8080/links -X POST \\
                --data '{"url":"https://example.com"}' -H 'Content-Type: application/json' \\
                -n 500 -c 20 --slo "p95_ms<=150" --slo "error_rate<=0.01" --out specs/x/benchmarks/create.json
  bench.py compare specs/x/benchmarks/baseline.json specs/x/benchmarks/create.json --threshold 10
  bench.py report specs/x/benchmarks/*.json --out specs/x/benchmarks/REPORT.md
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

LOWER_IS_BETTER = {"mean_ms", "p50_ms", "p90_ms", "p95_ms", "p99_ms", "max_ms", "error_rate"}
HIGHER_IS_BETTER = {"throughput_rps"}
DEFAULT_COMPARE = ["p50_ms", "p95_ms", "p99_ms", "throughput_rps", "error_rate"]
SLO_RE = re.compile(r"^\s*(\w+)\s*(<=|>=|<|>|==)\s*([0-9.]+)\s*$")
OPS = {"<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b,
       ">": lambda a, b: a > b, "==": lambda a, b: a == b}


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def summarize(samples_ms: list[float], errors: int, wall_s: float) -> dict:
    ok = sorted(samples_ms)
    total = len(ok) + errors
    r = lambda v: round(v, 3) if v == v else None  # NaN -> None
    return {
        "count": total, "ok": len(ok), "errors": errors,
        "error_rate": round(errors / total, 4) if total else 0.0,
        "min_ms": r(ok[0]) if ok else None, "max_ms": r(ok[-1]) if ok else None,
        "mean_ms": r(statistics.fmean(ok)) if ok else None,
        "stdev_ms": r(statistics.stdev(ok)) if len(ok) > 1 else 0.0,
        "p50_ms": r(percentile(ok, .50)), "p90_ms": r(percentile(ok, .90)),
        "p95_ms": r(percentile(ok, .95)), "p99_ms": r(percentile(ok, .99)),
        "throughput_rps": round(len(ok) / wall_s, 2) if wall_s > 0 else None,
        "wall_s": round(wall_s, 3),
    }


def git_sha() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def environment() -> dict:
    return {"python": platform.python_version(), "platform": platform.platform(),
            "machine": platform.machine(), "cpu_count": os.cpu_count(), "git_sha": git_sha()}


def run_load(fn, n: int, warmup: int, concurrency: int, duration: float | None) -> tuple[list[float], int, float, list[str]]:
    for _ in range(warmup):
        fn()
    samples, errors, messages = [], 0, []

    def one(_):
        t0 = time.perf_counter()
        ok, msg = fn()
        return ok, (time.perf_counter() - t0) * 1000, msg

    def record(batch):
        nonlocal errors
        for ok, ms, msg in batch:
            if ok:
                samples.append(ms)
            else:
                errors += 1
                messages.append(msg)

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        if duration:
            deadline = start + duration
            while time.perf_counter() < deadline:
                record(pool.map(one, range(concurrency)))
        else:
            record(pool.map(one, range(n)))
    return samples, errors, time.perf_counter() - start, messages


def evaluate_slos(stats: dict, slos: list[str]) -> list[dict]:
    results = []
    for expr in slos:
        m = SLO_RE.match(expr)
        if not m:
            sys.exit(f"error: bad --slo {expr!r} (expected e.g. p95_ms<=200)")
        metric, op, target = m.group(1), m.group(2), float(m.group(3))
        if metric not in stats:
            sys.exit(f"error: unknown metric {metric!r}; choose from {', '.join(sorted(stats))}")
        value = stats[metric]
        results.append({"slo": expr, "value": value, "pass": value is not None and OPS[op](value, target)})
    return results


def finish(a, kind: str, config: dict, samples, errors, wall, messages) -> int:
    stats = summarize(samples, errors, wall)
    slo = evaluate_slos(stats, a.slo or [])
    result = {"name": a.name, "kind": kind, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "config": config, "env": environment(), "stats": stats, "slo": slo,
              "passed": all(s["pass"] for s in slo), "sample_errors": sorted(set(messages))[:10],
              "samples_ms": [round(s, 3) for s in samples]}
    print(f"{a.name}: n={stats['count']} ok={stats['ok']} err={stats['errors']} "
          f"p50={stats['p50_ms']}ms p95={stats['p95_ms']}ms p99={stats['p99_ms']}ms "
          f"mean={stats['mean_ms']}ms rps={stats['throughput_rps']}")
    for s in slo:
        print(f"  SLO {s['slo']:<22} value={s['value']}  {'PASS' if s['pass'] else 'FAIL'}")
    if result["sample_errors"]:
        print("  errors: " + "; ".join(result["sample_errors"][:3]))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"  saved: {a.out}")
    return 0 if result["passed"] else 1


def cmd_cmd(a) -> int:
    def fn():
        try:
            p = subprocess.run(a.command, shell=True, capture_output=True, text=True, timeout=a.timeout)
            return p.returncode == 0, f"exit {p.returncode}: {p.stderr.strip()[:200]}"
        except subprocess.TimeoutExpired:
            return False, f"timeout after {a.timeout}s"
    config = {"command": a.command, "n": a.n, "warmup": a.warmup, "concurrency": a.concurrency,
              "duration": a.duration, "timeout": a.timeout}
    return finish(a, "cmd", config, *run_load(fn, a.n, a.warmup, a.concurrency, a.duration))


def cmd_http(a) -> int:
    headers = {}
    for h in a.header or []:
        k, _, v = h.partition(":")
        headers[k.strip()] = v.strip()
    body = a.data.encode() if a.data else None
    if a.data_file:
        body = Path(a.data_file).read_bytes()
    expect = set(int(c) for c in a.expect.split(",")) if a.expect else None

    def fn():
        req = urllib.request.Request(a.url, data=body, method=a.method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=a.timeout) as resp:
                resp.read()
                code = resp.status
        except urllib.error.HTTPError as e:
            code = e.code
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            return False, f"{type(e).__name__}: {getattr(e, 'reason', e)}"
        ok = code in expect if expect else 200 <= code < 400
        return ok, f"HTTP {code}"
    config = {"url": a.url, "method": a.method, "n": a.n, "warmup": a.warmup, "concurrency": a.concurrency,
              "duration": a.duration, "timeout": a.timeout, "headers": list(headers)}
    return finish(a, "http", config, *run_load(fn, a.n, a.warmup, a.concurrency, a.duration))


def load_result(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"error: cannot read {path}: {e}")


def cmd_compare(a) -> int:
    base, cur = load_result(a.baseline), load_result(a.current)
    metrics = a.metrics.split(",") if a.metrics else DEFAULT_COMPARE
    t = a.threshold / 100
    regressions = []
    print(f"| Metric | Baseline ({base['name']}) | Current ({cur['name']}) | Δ | Verdict |")
    print("|---|---|---|---|---|")
    for m in metrics:
        b, c = base["stats"].get(m), cur["stats"].get(m)
        if b is None or c is None:
            print(f"| {m} | {b} | {c} | - | n/a |")
            continue
        delta = ((c - b) / b * 100) if b else (0.0 if c == b else float("inf"))
        if m == "error_rate":
            worse, better = c - b > a.max_error_delta, b - c > a.max_error_delta
        elif m in HIGHER_IS_BETTER:
            worse, better = c < b * (1 - t), c > b * (1 + t)
        else:
            worse = c > b * (1 + t) and (c - b) > a.min_delta_ms
            better = c < b * (1 - t) and (b - c) > a.min_delta_ms
        verdict = "🔴 regression" if worse else ("🟢 improved" if better else "⚪ same")
        if worse:
            regressions.append(m)
        print(f"| {m} | {b} | {c} | {delta:+.1f}% | {verdict} |")
    print()
    print(f"regressions: {', '.join(regressions)}" if regressions else "no regressions")
    return 1 if regressions else 0


def cmd_report(a) -> int:
    results = [load_result(p) for p in a.files]
    cols = ["p50_ms", "p95_ms", "p99_ms", "mean_ms", "stdev_ms", "throughput_rps", "error_rate"]
    lines = ["# Benchmark Report", "", f"_Generated {time.strftime('%Y-%m-%d %H:%M')} by `devkit/tools/bench.py`._", "",
             "| Name | Kind | n | " + " | ".join(cols) + " | SLOs |",
             "|---|---|---|" + "---|" * len(cols) + "---|"]
    for r in results:
        s = r["stats"]
        slo = "✅" if r.get("passed", True) and r.get("slo") else ("❌ " + ", ".join(
            x["slo"] for x in r.get("slo", []) if not x["pass"]) if r.get("slo") else "-")
        lines.append(f"| {r['name']} | {r['kind']} | {s.get('count', '-')} | " + " | ".join(
            str(s.get(c)) for c in cols) + f" | {slo} |")
    ranked = [r for r in results if r["stats"].get("p95_ms") is not None]
    if len(ranked) > 1:
        best = min(ranked, key=lambda r: r["stats"]["p95_ms"])
        lines += ["", f"**Fastest p95:** {best['name']} ({best['stats']['p95_ms']} ms)"]
    envs = {json.dumps(r.get("env", {}).get("platform")) for r in results}
    if len(envs) > 1:
        lines += ["", "⚠️ Results come from different platforms — comparisons may be invalid."]
    text = "\n".join(lines) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"report written: {a.out}")
    print(text)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="sub", required=True)

    def load_opts(sp):
        sp.add_argument("--name", required=True)
        sp.add_argument("-n", type=int, default=20, help="iterations (ignored with --duration)")
        sp.add_argument("--warmup", type=int, default=2)
        sp.add_argument("-c", "--concurrency", type=int, default=1)
        sp.add_argument("--duration", type=float, help="run for N seconds instead of -n iterations")
        sp.add_argument("--timeout", type=float, default=30)
        sp.add_argument("--slo", action="append", help="gate, e.g. p95_ms<=200 (repeatable)")
        sp.add_argument("--out", help="write JSON result here")

    sp = sub.add_parser("cmd", help="benchmark a shell command")
    load_opts(sp)
    sp.add_argument("command")
    sp.set_defaults(fn=cmd_cmd)
    sp = sub.add_parser("http", help="benchmark an HTTP endpoint")
    load_opts(sp)
    sp.add_argument("--url", required=True)
    sp.add_argument("-X", "--method", default="GET")
    sp.add_argument("-H", "--header", action="append")
    sp.add_argument("--data")
    sp.add_argument("--data-file")
    sp.add_argument("--expect", help="comma-separated acceptable status codes (default 2xx/3xx)")
    sp.set_defaults(fn=cmd_http)
    sp = sub.add_parser("compare", help="baseline vs current; exit 1 on regression")
    sp.add_argument("baseline")
    sp.add_argument("current")
    sp.add_argument("--threshold", type=float, default=10.0, help="allowed change in percent")
    sp.add_argument("--metrics", help=f"comma list (default {','.join(DEFAULT_COMPARE)})")
    sp.add_argument("--min-delta-ms", type=float, default=1.0, help="ignore latency deltas smaller than this")
    sp.add_argument("--max-error-delta", type=float, default=0.01)
    sp.set_defaults(fn=cmd_compare)
    sp = sub.add_parser("report", help="markdown table across result files")
    sp.add_argument("files", nargs="+")
    sp.add_argument("--out")
    sp.set_defaults(fn=cmd_report)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
