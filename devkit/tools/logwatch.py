#!/usr/bin/env python3
"""devkit log watcher for local testing.

Tails log files (globs, rotation-aware), a command's output, or stdin. It
highlights levels, groups stack traces, filters, raises alerts from pattern
rules with thresholds, and prints/writes a summary of the top error
signatures when it stops.

Examples:
  logwatch.py "logs/*.log"                               # follow files
  logwatch.py --cmd "npm run dev"                        # run & watch a process
  logwatch.py --config devkit/config/logwatch.local.json # project profile
  logwatch.py app.log --once --from-start --report specs/x/benchmarks/log-report.md --fail-on ERROR
  docker compose logs -f api | logwatch.py --stdin --level WARN
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

LEVELS = ["TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"]
RANK = {lvl: i for i, lvl in enumerate(LEVELS)}
ALIASES = {"WARNING": "WARN", "ERR": "ERROR", "CRITICAL": "FATAL", "SEVERE": "ERROR", "PANIC": "FATAL",
           "NOTICE": "INFO", "VERBOSE": "DEBUG", "FINE": "DEBUG"}
LEVEL_UPPER_RE = re.compile(r"\b(TRACE|DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|ERR|SEVERE|FATAL|CRITICAL|PANIC)\b")
LEVEL_ANY_RE = re.compile(r"\b(trace|debug|info|warn(?:ing)?|error|fatal|critical)\b", re.I)
EXC_RE = re.compile(r"^(?:[\w.$]+(?:Error|Exception)|Traceback \(most recent call last\)|panic:)")
EXC_LINE_RE = re.compile(r"^[\w.$]+(?:Error|Exception|Exit|Interrupt|Warning)?: ")
CONTINUATION_RE = re.compile(r"^(?:\s+\S|\s*at\s|Caused by:|\.\.\. \d+ more|\s*File \")")
JSON_LEVEL_KEYS = ("level", "lvl", "severity", "levelname", "log.level")
JSON_MSG_KEYS = ("msg", "message", "event", "text")
JSON_TS_KEYS = ("ts", "time", "timestamp", "@timestamp", "asctime")
SIGNATURE_SUBS = [
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"), ""),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<uuid>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b"), "<ip>"),
    (re.compile(r"\b0x[0-9a-f]+\b", re.I), "<hex>"),
    (re.compile(r"\b[0-9a-f]{16,}\b", re.I), "<hash>"),
    (re.compile(r"\d+(?:\.\d+)?"), "<n>"),
    (re.compile(r"\s+"), " "),
]
COLORS = {"TRACE": "\033[90m", "DEBUG": "\033[36m", "INFO": "\033[32m", "WARN": "\033[33m",
          "ERROR": "\033[31m", "FATAL": "\033[1;37;41m", None: ""}
RESET, DIM, BOLD = "\033[0m", "\033[2m", "\033[1m"


def norm_level(raw) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, int):  # pino / bunyan numeric levels
        return {10: "TRACE", 20: "DEBUG", 30: "INFO", 40: "WARN", 50: "ERROR", 60: "FATAL"}.get(raw)
    s = str(raw).upper()
    s = ALIASES.get(s, s)
    return s if s in RANK else None


def signature(text: str) -> str:
    for rx, repl in SIGNATURE_SUBS:
        text = rx.sub(repl, text)
    return text.strip()[:160]


@dataclass
class Rule:
    name: str
    pattern: re.Pattern
    severity: str = "high"
    threshold: int = 1
    window_sec: float = 60.0
    hits: deque = field(default_factory=deque)
    last_alert: float = -1e18
    fired: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> "Rule":
        flags = re.I if d.get("ignore_case", True) else 0
        return cls(name=d["name"], pattern=re.compile(d["pattern"], flags), severity=d.get("severity", "high"),
                   threshold=int(d.get("threshold", 1)), window_sec=float(d.get("window_sec", 60)))

    def observe(self, now: float) -> bool:
        self.hits.append(now)
        while self.hits and now - self.hits[0] > self.window_sec:
            self.hits.popleft()
        if len(self.hits) >= self.threshold and now - self.last_alert >= self.window_sec:
            self.last_alert = now
            self.fired += 1
            return True
        return False


# ---------------------------------------------------------------- sources

class FileTail:
    """Polling tail that survives truncation and rotation."""

    def __init__(self, path: str, from_start: bool):
        self.path, self.fh, self.ino, self.buf = path, None, None, ""
        self._open(seek_end=not from_start)

    def _open(self, seek_end: bool) -> None:
        try:
            self.fh = open(self.path, "r", encoding="utf-8", errors="replace")
            self.ino = os.fstat(self.fh.fileno()).st_ino
            if seek_end:
                self.fh.seek(0, os.SEEK_END)
        except FileNotFoundError:
            self.fh = None

    def read_lines(self) -> list[str]:
        if self.fh is None:
            if os.path.exists(self.path):
                self._open(seek_end=False)
            return []
        try:
            st = os.stat(self.path)
            if st.st_ino != self.ino or st.st_size < self.fh.tell():  # rotated or truncated
                rest = self.fh.read()
                self.fh.close()
                self._open(seek_end=False)
                chunk = rest
            else:
                chunk = ""
        except FileNotFoundError:
            chunk = ""
        chunk += self.fh.read() if self.fh else ""
        if not chunk:
            return []
        data = self.buf + chunk
        lines = data.split("\n")
        self.buf = lines.pop()  # incomplete trailing line
        return lines

    def flush(self) -> list[str]:
        rest, self.buf = self.buf, ""
        return [rest] if rest else []


def file_reader(patterns: list[str], from_start: bool, out: queue.Queue, stop: threading.Event,
                interval: float, once: bool) -> None:
    tails: dict[str, FileTail] = {}

    def discover(initial: bool):
        for pat in patterns:
            matches = glob.glob(pat) or ([pat] if not glob.has_magic(pat) else [])
            for p in matches:
                if p not in tails and not os.path.isdir(p):
                    # files appearing after start are read from the beginning
                    tails[p] = FileTail(p, from_start or not initial)

    discover(True)
    last_discover = time.monotonic()
    while not stop.is_set():
        got = False
        for p, t in list(tails.items()):
            for line in t.read_lines():
                out.put((p, line))
                got = True
        if once and not got:
            for p, t in tails.items():
                for line in t.flush():
                    out.put((p, line))
            break
        if time.monotonic() - last_discover > 2:
            discover(False)
            last_discover = time.monotonic()
        if not got:
            stop.wait(interval)
    out.put((None, None))


def stream_reader(label: str, stream, out: queue.Queue) -> None:
    for line in iter(stream.readline, ""):
        out.put((label, line.rstrip("\n")))
    out.put((None, None))


# ---------------------------------------------------------------- watcher

class Watcher:
    def __init__(self, a, rules: list[Rule]):
        self.a = a
        self.rules = rules
        self.min_rank = RANK[norm_level(a.level)] if a.level else None
        self.grep = [re.compile(g, re.I) for g in a.grep or []]
        self.exclude = [re.compile(x, re.I) for x in a.exclude or []]
        self.color = not a.no_color and sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        self.counts = Counter()
        self.by_source = defaultdict(Counter)
        self.sigs: dict[str, dict] = {}
        self.alerts: list[dict] = []
        self.cur_level: str | None = None   # level of the current multi-line event
        self.cur_shown = False
        self.in_traceback = False
        self.started = time.time()
        self.multi_source = False

    def c(self, code: str, text: str) -> str:
        return f"{code}{text}{RESET}" if self.color and code else text

    def parse(self, line: str) -> tuple[str | None, str]:
        s = line.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                obj = json.loads(s)
            except json.JSONDecodeError:
                obj = None
            if isinstance(obj, dict):
                lvl = next((norm_level(obj[k]) for k in JSON_LEVEL_KEYS if k in obj), None)
                msg = next((str(obj[k]) for k in JSON_MSG_KEYS if k in obj), "")
                ts = next((str(obj[k]) for k in JSON_TS_KEYS if k in obj), "")
                skip = set(JSON_LEVEL_KEYS + JSON_MSG_KEYS + JSON_TS_KEYS)
                extra = " ".join(f"{k}={json.dumps(v) if not isinstance(v, str) else v}"
                                 for k, v in obj.items() if k not in skip)
                text = " ".join(p for p in (ts, lvl or "", msg) if p)
                return lvl, text + (f"  {self.c(DIM, extra)}" if extra else "")
        m = LEVEL_UPPER_RE.search(line[:120]) or LEVEL_ANY_RE.search(line[:60])
        lvl = norm_level(m.group(1)) if m else None
        if lvl is None and EXC_RE.match(line):
            lvl = "ERROR"
        return lvl, line

    def handle(self, source: str, line: str) -> None:
        if not line.strip():
            return
        for rule in self.rules:
            if rule.pattern.search(line) and rule.observe(time.monotonic()):
                self.alert(rule, source, line)
        if self.cur_level is not None and CONTINUATION_RE.match(line):
            if self.cur_shown:
                self.emit(source, self.cur_level, line, continuation=True)
            return
        if self.in_traceback and EXC_LINE_RE.match(line):
            # final "ValueError: msg" line closes a Python traceback: same event, best signature
            self.in_traceback = False
            self.record_signature("ERROR", line)
            if self.cur_shown:
                self.emit(source, "ERROR", line, continuation=True)
            return
        lvl, text = self.parse(line)
        self.in_traceback = line.startswith("Traceback (most recent call last)")
        self.cur_level = lvl or "INFO"
        self.counts[lvl or "UNLEVELED"] += 1
        self.by_source[source][lvl or "UNLEVELED"] += 1
        if lvl and RANK[lvl] >= RANK["WARN"] and not self.in_traceback:
            self.record_signature(lvl, text)
        self.cur_shown = self.visible(lvl, line)
        if self.cur_shown:
            self.emit(source, lvl, text)

    def record_signature(self, lvl: str, text: str) -> None:
        entry = self.sigs.setdefault(signature(text), {"count": 0, "level": lvl, "first": time.time(),
                                                       "sample": text[:300]})
        entry["count"] += 1
        entry["last"] = time.time()

    def visible(self, lvl: str | None, line: str) -> bool:
        if self.min_rank is not None and (lvl is None or RANK[lvl] < self.min_rank):
            return False
        if self.grep and not any(g.search(line) for g in self.grep):
            return False
        if any(x.search(line) for x in self.exclude):
            return False
        return True

    def emit(self, source: str, lvl: str | None, text: str, continuation: bool = False) -> None:
        if self.a.quiet:
            return
        prefix = self.c(DIM, f"[{Path(source).name}] ") if self.multi_source else ""
        body = self.c(COLORS.get(lvl, ""), text) if (lvl and RANK[lvl] >= RANK["WARN"]) or continuation else (
            text.replace(lvl, self.c(COLORS[lvl], lvl), 1) if lvl and self.color else text)
        print(prefix + body, flush=True)

    def alert(self, rule: Rule, source: str, line: str) -> None:
        rec = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "rule": rule.name, "severity": rule.severity,
               "source": source, "hits_in_window": len(rule.hits), "window_sec": rule.window_sec, "line": line[:500]}
        self.alerts.append(rec)
        banner = f"🚨 ALERT [{rule.severity.upper()}] {rule.name} — {len(rule.hits)} hit(s) in {rule.window_sec:g}s"
        print(self.c(BOLD + COLORS["FATAL"], banner) + ("\a" if self.a.bell else ""), file=sys.stderr, flush=True)
        if self.a.alerts_file:
            with open(self.a.alerts_file, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")

    def summary_md(self) -> str:
        dur = time.time() - self.started
        lines = ["# Log Watch Report", "", f"- Duration: {dur:.1f}s",
                 f"- Lines by level: " + ", ".join(f"{k}={v}" for k, v in sorted(self.counts.items())),
                 f"- Alerts fired: {len(self.alerts)}", ""]
        if len(self.by_source) > 1:
            lines += ["## By source", "", "| Source | " + " | ".join(LEVELS) + " |",
                      "|---" * (len(LEVELS) + 1) + "|"]
            for src, cnt in sorted(self.by_source.items()):
                lines.append(f"| {src} | " + " | ".join(str(cnt.get(lv, 0)) for lv in LEVELS) + " |")
            lines.append("")
        if self.alerts:
            lines += ["## Alerts", "", "| Time | Severity | Rule | Source | Line |", "|---|---|---|---|---|"]
            for al in self.alerts:
                lines.append(f"| {al['time']} | {al['severity']} | {al['rule']} | {al['source']} | "
                             f"`{al['line'][:120].replace('|', '/')}` |")
            lines.append("")
        top = sorted(self.sigs.items(), key=lambda kv: -kv[1]["count"])[: self.a.top]
        if top:
            lines += ["## Top warning/error signatures", "", "| Count | Level | Signature |", "|---|---|---|"]
            for sig, e in top:
                lines.append(f"| {e['count']} | {e['level']} | `{sig.replace('|', '/')}` |")
            lines.append("")
        return "\n".join(lines)

    def failed(self) -> bool:
        if self.a.fail_on:
            threshold = RANK[norm_level(self.a.fail_on)]
            if any(RANK[lv] >= threshold for lv in self.counts if lv in RANK):
                return True
        return any(al["severity"] == "critical" for al in self.alerts)


# ---------------------------------------------------------------- CLI

def load_config(path: str | None) -> dict:
    if not path:
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"error: cannot read config {path}: {e}")


def main(argv=None) -> int:
    default_rules = Path(__file__).resolve().parent.parent / "config" / "logwatch.rules.json"
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("paths", nargs="*", help="files or globs to follow")
    p.add_argument("--cmd", help="run this shell command and watch its stdout+stderr")
    p.add_argument("--stdin", action="store_true", help="read from stdin")
    p.add_argument("--config", help="JSON profile: {sources, cmd, level, grep, exclude, rules, rules_file}")
    p.add_argument("--rules", help=f"alert rules JSON (default: {default_rules.name})")
    p.add_argument("--no-rules", action="store_true")
    p.add_argument("--level", help="minimum level to display (TRACE..FATAL)")
    p.add_argument("--grep", action="append", help="only show lines matching regex (repeatable)")
    p.add_argument("--exclude", action="append", help="hide lines matching regex (repeatable)")
    p.add_argument("--from-start", action="store_true", help="read files from the beginning")
    p.add_argument("--once", action="store_true", help="read what exists, then exit (files only)")
    p.add_argument("--report", help="write markdown summary here on exit")
    p.add_argument("--alerts-file", help="append alerts as JSON lines")
    p.add_argument("--fail-on", help="exit 1 if any line at/above this level was seen")
    p.add_argument("--top", type=int, default=10, help="signatures to include in summary")
    p.add_argument("--interval", type=float, default=0.25)
    p.add_argument("--bell", action="store_true", help="terminal bell on alerts")
    p.add_argument("--quiet", action="store_true", help="no live output, summary only")
    p.add_argument("--no-color", action="store_true")
    a = p.parse_args(argv)

    cfg = load_config(a.config)
    a.paths = a.paths or cfg.get("sources", [])
    a.cmd = a.cmd or cfg.get("cmd")
    a.level = a.level or cfg.get("level")
    a.grep = a.grep or cfg.get("grep")
    a.exclude = (a.exclude or []) + cfg.get("exclude", [])
    if a.level and norm_level(a.level) is None:
        sys.exit(f"error: unknown level {a.level}")
    if a.fail_on and norm_level(a.fail_on) is None:
        sys.exit(f"error: unknown level {a.fail_on}")

    rule_defs = list(cfg.get("rules", []))
    if not a.no_rules:
        rules_path = a.rules or cfg.get("rules_file") or (str(default_rules) if default_rules.exists() else None)
        if rules_path:
            data = load_config(rules_path)
            rule_defs += data.get("rules", data) if isinstance(data, dict) else data
    rules = [Rule.from_dict(r) for r in rule_defs]

    if not (a.paths or a.cmd or a.stdin):
        p.error("give file paths/globs, --cmd, --stdin, or a --config with sources")

    def interrupt(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)  # background stop still prints/writes the summary

    w = Watcher(a, rules)
    q: queue.Queue = queue.Queue()
    stop = threading.Event()
    producers, proc = 0, None
    if a.paths:
        threading.Thread(target=file_reader, args=(a.paths, a.from_start or a.once, q, stop, a.interval, a.once),
                         daemon=True).start()
        producers += 1
    if a.cmd:
        proc = subprocess.Popen(a.cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1, errors="replace")
        threading.Thread(target=stream_reader, args=("cmd", proc.stdout, q), daemon=True).start()
        producers += 1
    if a.stdin:
        threading.Thread(target=stream_reader, args=("stdin", sys.stdin, q), daemon=True).start()
        producers += 1
    w.multi_source = producers > 1 or len(a.paths) > 1 or any(glob.has_magic(x) for x in a.paths)
    if rules and not a.quiet:
        print(w.c(DIM, f"logwatch: {len(rules)} alert rule(s) active · Ctrl+C for summary"), file=sys.stderr)

    try:
        finished = 0
        while finished < producers:
            src, line = q.get()
            if src is None:
                finished += 1
                # a command exiting ends the session even if files are still being followed
                if proc is not None and a.paths and not a.once and proc.stdout.closed is False:
                    try:
                        proc.wait(timeout=5)
                        break
                    except subprocess.TimeoutExpired:
                        pass
                continue
            w.handle(src, line)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if proc:
            if proc.poll() is None:
                proc.terminate()
            proc.wait()

    report = w.summary_md()
    print("\n" + report, file=sys.stderr)
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(report + "\n", encoding="utf-8")
        print(f"report written: {a.report}", file=sys.stderr)
    if w.failed():
        return 1
    return proc.returncode if proc and proc.returncode else 0


if __name__ == "__main__":
    sys.exit(main())
