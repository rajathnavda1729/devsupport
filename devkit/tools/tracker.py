#!/usr/bin/env python3
"""devkit task tracker.

Tasks live in specs/<feature>/tasks.json. Every write re-renders
specs/<feature>/TASKS.md (board + dependency graph + waves), so the markdown
board never drifts from the data. Never edit either file by hand.

Examples:
  tracker.py add --title "Create URL table" --type infra --priority P0 --estimate S --reqs FR-001
  tracker.py import tasks.draft.json            # bulk import (list or {"tasks": [...]})
  tracker.py start T-003 ; tracker.py done T-003 --note "merged #42"
  tracker.py block T-004 --note "waiting on API key"
  tracker.py next                               # ready tasks, highest priority first
  tracker.py waves                              # parallelisable waves + critical path
  tracker.py validate                           # deps, cycles, requirement & test coverage
  tracker.py trace                              # writes traceability.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from devkit_common import (BOARD_FILE, TASKS_FILE, TRACE_FILE, die, doc_marker, load_json, now_iso,
                           parse_requirements, parse_test_cases, resolve_feature, write_atomic)

STATUSES = ["todo", "in_progress", "review", "blocked", "done", "cancelled"]
CLOSED = {"done", "cancelled"}
PRIORITIES = ["P0", "P1", "P2", "P3"]
TYPES = ["feature", "infra", "test", "docs", "spike", "bug", "chore"]
ESTIMATE_POINTS = {"XS": 0.5, "S": 1, "M": 3, "L": 5, "XL": 8}
LIST_FIELDS = ("depends_on", "requirements", "acceptance", "notes")
TID_RE = re.compile(r"^T-(\d+)$")


def points(task: dict) -> float:
    est = str(task.get("estimate") or "M").upper()
    if est in ESTIMATE_POINTS:
        return ESTIMATE_POINTS[est]
    try:
        return float(est)
    except ValueError:
        return ESTIMATE_POINTS["M"]


def split_csv(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value).split(",") if v.strip()]


class Store:
    def __init__(self, feature_dir: Path):
        self.dir = feature_dir
        self.path = feature_dir / TASKS_FILE
        self.data = load_json(self.path, {"feature": feature_dir.name, "tasks": []})
        self.data.setdefault("tasks", [])

    @property
    def tasks(self) -> list[dict]:
        return self.data["tasks"]

    def by_id(self) -> dict[str, dict]:
        return {t["id"]: t for t in self.tasks}

    def get(self, tid: str) -> dict:
        task = self.by_id().get(tid)
        if not task:
            die(f"unknown task {tid}")
        return task

    def next_id(self) -> str:
        nums = [int(m.group(1)) for t in self.tasks if (m := TID_RE.match(t["id"]))]
        return f"T-{(max(nums) + 1) if nums else 1:03d}"

    def save(self) -> None:
        self.data["updated"] = now_iso()
        write_atomic(self.path, json.dumps(self.data, indent=2) + "\n")
        write_atomic(self.dir / BOARD_FILE, render_board(self))


def normalize(raw: dict, store: Store, existing: dict | None = None) -> dict:
    task = dict(existing or {})
    task.update({k: v for k, v in raw.items() if v is not None})
    task["id"] = task.get("id") or store.next_id()
    if not task.get("title"):
        die(f"task {task['id']} needs a title")
    task.setdefault("description", "")
    task.setdefault("type", "feature")
    task.setdefault("status", "todo")
    task.setdefault("priority", "P2")
    task.setdefault("estimate", "M")
    task.setdefault("component", "")
    task.setdefault("phase", "")
    task.setdefault("owner", "")
    for f in LIST_FIELDS:
        task[f] = split_csv(task.get(f)) if f in ("depends_on", "requirements") else list(task.get(f) or [])
    for field, allowed in (("status", STATUSES), ("priority", PRIORITIES), ("type", TYPES)):
        if task[field] not in allowed:
            die(f"task {task['id']}: {field} must be one of {', '.join(allowed)} (got {task[field]!r})")
    task.setdefault("created", now_iso())
    task["updated"] = now_iso()
    return task


# ---------------------------------------------------------------- graph logic

def dependency_waves(tasks: list[dict]) -> tuple[list[list[str]], list[str]]:
    """Kahn topological levels over open tasks. Returns (waves, ids_in_cycles)."""
    open_tasks = {t["id"]: t for t in tasks if t["status"] != "cancelled"}
    indeg = {tid: 0 for tid in open_tasks}
    children = defaultdict(list)
    for tid, t in open_tasks.items():
        for dep in t["depends_on"]:
            if dep in open_tasks:
                indeg[tid] += 1
                children[dep].append(tid)
    wave = sorted(tid for tid, d in indeg.items() if d == 0)
    waves, seen = [], set()
    while wave:
        waves.append(wave)
        seen.update(wave)
        nxt = []
        for tid in wave:
            for child in children[tid]:
                indeg[child] -= 1
                if indeg[child] == 0:
                    nxt.append(child)
        wave = sorted(nxt)
    return waves, sorted(set(open_tasks) - seen)


def critical_path(tasks: list[dict]) -> tuple[list[str], float]:
    """Longest chain of remaining work (by estimate points) through open tasks."""
    waves, cyclic = dependency_waves(tasks)
    if cyclic:
        return [], 0.0
    tmap = {t["id"]: t for t in tasks}
    best: dict[str, tuple[float, str | None]] = {}
    for wave in waves:
        for tid in wave:
            t = tmap[tid]
            own = 0.0 if t["status"] == "done" else points(t)
            prev = max(((best[d][0], d) for d in t["depends_on"] if d in best), default=(0.0, None))
            best[tid] = (prev[0] + own, prev[1])
    if not best:
        return [], 0.0
    end = max(best, key=lambda k: best[k][0])
    total, path, cur = best[end][0], [], end
    while cur:
        path.append(cur)
        cur = best[cur][1]
    return list(reversed(path)), total


def ready_tasks(store: Store) -> list[dict]:
    tmap = store.by_id()
    crit = set(critical_path(store.tasks)[0])
    ready = [t for t in store.tasks if t["status"] == "todo"
             and all(tmap.get(d, {}).get("status") in CLOSED for d in t["depends_on"])]
    return sorted(ready, key=lambda t: (t["priority"], t["id"] not in crit, t["id"]))


def mermaid_graph(tasks: list[dict]) -> str:
    node = lambda tid: tid.replace("-", "")
    lines = ["flowchart LR"]
    for t in tasks:
        title = t["title"].replace('"', "'")
        lines.append(f'  {node(t["id"])}["{t["id"]}: {title}"]:::{t["status"]}')
    for t in tasks:
        for d in t["depends_on"]:
            lines.append(f"  {node(d)} --> {node(t['id'])}")
    lines += [
        "  classDef todo fill:#eef,stroke:#88a",
        "  classDef in_progress fill:#ffd,stroke:#cc0",
        "  classDef review fill:#def,stroke:#39c",
        "  classDef blocked fill:#fdd,stroke:#c33",
        "  classDef done fill:#dfd,stroke:#3a3",
        "  classDef cancelled fill:#eee,stroke:#999,stroke-dasharray:3",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- rendering

def row(t: dict) -> str:
    return (f"| {t['id']} | {t['title']} | {t['type']} | {t['priority']} | {t['estimate']} | "
            f"{', '.join(t['depends_on']) or '-'} | {', '.join(t['requirements']) or '-'} | {t['owner'] or '-'} |")


def render_board(store: Store) -> str:
    tasks = store.tasks
    title = store.data.get("title") or store.data.get("feature")
    total = len([t for t in tasks if t["status"] != "cancelled"])
    done = len([t for t in tasks if t["status"] == "done"])
    pts_total = sum(points(t) for t in tasks if t["status"] != "cancelled")
    pts_done = sum(points(t) for t in tasks if t["status"] == "done")
    pct = int(100 * done / total) if total else 0
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    out = [doc_marker("board", generated=True), f"# Task Board — {title}", "",
           "_Generated by `devkit/tools/tracker.py` — do not edit by hand._", "",
           f"**Progress:** `{bar}` {done}/{total} tasks ({pct}%) · {pts_done:g}/{pts_total:g} points", ""]
    ready_ids = {t["id"] for t in ready_tasks(store)}
    header = ["| ID | Title | Type | Pri | Est | Depends on | Requirements | Owner |",
              "|----|-------|------|-----|-----|------------|--------------|-------|"]
    sections = [("🚧 In progress", "in_progress"), ("👀 In review", "review"), ("⛔ Blocked", "blocked"),
                ("✅ Ready to start", "ready"), ("⏳ Waiting on dependencies", "waiting"),
                ("✔️ Done", "done"), ("🗑️ Cancelled", "cancelled")]
    for label, key in sections:
        if key == "ready":
            items = [t for t in tasks if t["id"] in ready_ids]
        elif key == "waiting":
            items = [t for t in tasks if t["status"] == "todo" and t["id"] not in ready_ids]
        else:
            items = [t for t in tasks if t["status"] == key]
        if not items:
            continue
        out += [f"## {label} ({len(items)})", "", *header, *(row(t) for t in items), ""]
        if key == "blocked":
            out += [f"- **{t['id']}**: {t['notes'][-1] if t['notes'] else '(no reason recorded)'}" for t in items]
            out.append("")
    if tasks:
        waves, cyclic = dependency_waves(tasks)
        path, length = critical_path(tasks)
        out += ["## Dependency graph", "", "```mermaid", mermaid_graph(tasks), "```", "",
                "## Execution waves", "", "Tasks in the same wave can run in parallel.", ""]
        out += [f"- **Wave {i}:** {', '.join(w)}" for i, w in enumerate(waves, 1)]
        if cyclic:
            out.append(f"- ⚠️ **Dependency cycle:** {', '.join(cyclic)}")
        out += ["", f"**Critical path ({length:g} points remaining):** {' → '.join(path) or '-'}", ""]
    return "\n".join(out)


def render_trace(store: Store) -> tuple[str, list[str], list[str]]:
    reqs = parse_requirements(store.dir)
    cases = parse_test_cases(store.dir)
    tasks_for, tests_for = defaultdict(list), defaultdict(list)
    for t in store.tasks:
        if t["status"] != "cancelled":
            for r in t["requirements"]:
                tasks_for[r].append(t["id"])
    for tc, rids in cases.items():
        for r in rids:
            tests_for[r].append(tc)
    errors, warnings = [], []
    lines = [doc_marker("traceability", generated=True), "# Traceability Matrix", "", "_Generated by `devkit/tools/tracker.py trace`._", "",
             "| Requirement | Critical | Tasks | Test cases | Status |",
             "|-------------|----------|-------|------------|--------|"]
    for rid in sorted(reqs, key=lambda r: (r.split("-")[0], int(r.split("-")[1]))):
        crit = reqs[rid]["critical"]
        gaps = []
        if not tasks_for[rid]:
            gaps.append("no task")
        if cases and not tests_for[rid]:
            gaps.append("no test")
        status = "✅" if not gaps else ("❌ " if crit else "⚠️ ") + ", ".join(gaps)
        for g in gaps:
            (errors if crit else warnings).append(f"{'critical ' if crit else ''}requirement {rid} has {g}")
        lines.append(f"| {rid} | {'🔴 yes' if crit else 'no'} | {', '.join(tasks_for[rid]) or '-'} | "
                     f"{', '.join(tests_for[rid]) or '-'} | {status} |")
    unknown = sorted((set(tasks_for) | set(tests_for)) - set(reqs)) if reqs else []
    for rid in unknown:
        errors.append(f"{rid} is referenced by tasks/tests but not defined in requirements")
    if not reqs:
        warnings.append("no requirements found (01-requirements.md missing or has no FR-/NFR- table rows)")
    return "\n".join(lines) + "\n", errors, warnings


# ---------------------------------------------------------------- commands

def refresh_index(store: Store) -> None:
    from scaffold import write_index  # lazy: only structural changes touch the workspace README
    write_index(store.dir)


def cmd_init(store: Store, a) -> None:
    if a.title:
        store.data["title"] = a.title
    store.save()
    refresh_index(store)
    print(f"tracker ready: {store.path}")


def cmd_add(store: Store, a) -> None:
    raw = {k: getattr(a, k) for k in ("title", "description", "type", "priority", "estimate",
                                      "component", "phase", "owner")}
    raw["depends_on"], raw["requirements"] = a.deps, a.reqs
    raw["acceptance"] = a.acceptance or []
    task = normalize(raw, store)
    store.tasks.append(task)
    store.save()
    print(f"added {task['id']}: {task['title']}")


def cmd_import(store: Store, a) -> None:
    payload = json.loads(Path(a.file).read_text(encoding="utf-8"))
    items = payload.get("tasks", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        die("import file must be a JSON list of tasks or {\"tasks\": [...]}")
    if a.replace:
        store.data["tasks"] = []
    if isinstance(payload, dict) and payload.get("title"):
        store.data["title"] = payload["title"]
    existing = store.by_id()
    added = updated = 0
    for raw in items:
        if raw.get("id") in existing:
            idx = store.tasks.index(existing[raw["id"]])
            store.tasks[idx] = normalize(raw, store, existing[raw["id"]])
            updated += 1
        else:
            task = normalize(raw, store)
            store.tasks.append(task)
            existing[task["id"]] = task
            added += 1
    store.save()
    refresh_index(store)
    print(f"imported: {added} added, {updated} updated -> {store.path}")


def cmd_update(store: Store, a) -> None:
    task = store.get(a.id)
    changes = {k: getattr(a, k) for k in ("title", "description", "type", "priority", "estimate",
                                          "component", "phase", "owner", "status")
               if getattr(a, k, None) is not None}
    if a.deps is not None:
        changes["depends_on"] = a.deps
    if a.reqs is not None:
        changes["requirements"] = a.reqs
    if a.acceptance:
        changes["acceptance"] = task["acceptance"] + a.acceptance
    if a.note:
        changes["notes"] = task["notes"] + [f"{now_iso()} {a.note}"]
    store.tasks[store.tasks.index(task)] = normalize(changes, store, task)
    store.save()
    print(f"updated {a.id}" + (f" -> {changes['status']}" if "status" in changes else ""))


def check_readiness_gate(store: Store, task: dict, a) -> None:
    """Review before implementing: non-spike work starts only when the feature passes readiness."""
    import review  # lazy: heavy (ADR scan, lint) and only needed when starting work
    if task["type"] == "spike" or not review.gate_enabled():
        return
    checks = review.readiness(store.dir)
    failed = [name for name, ok, _ in checks if not ok]
    if not failed:
        return
    if a.force:
        a.note = f"READINESS GATE BYPASSED ({', '.join(failed)}): {a.note or ''}".strip()
        return
    die(f"{task['id']} cannot start: feature '{store.dir.name}' is not ready for implementation.\n  failing: "
        + "\n  failing: ".join(failed)
        + f"\n  details: python3 devkit/tools/review.py readiness {store.dir.name}"
        + "\n  (spike tasks are exempt; bypass with --force --note '<reason>', which is recorded on the task)")


def set_status(status: str):
    def run(store: Store, a) -> None:
        if status == "blocked" and not a.note:
            die("blocking a task requires --note '<reason>'")
        if a.force and not a.note:
            die("--force requires --note '<why the check is being bypassed>'")
        task = store.get(a.id)
        if status == "in_progress":
            tmap = store.by_id()
            pending = [d for d in task["depends_on"] if tmap.get(d, {}).get("status") not in CLOSED]
            if pending and not a.force:
                die(f"{a.id} depends on unfinished {', '.join(pending)} (use --force to override)")
            check_readiness_gate(store, task, a)
        a.status = status
        for k in ("title", "description", "type", "priority", "estimate", "component", "phase",
                  "owner", "deps", "reqs", "acceptance"):
            setattr(a, k, None)
        cmd_update(store, a)
    return run


def cmd_list(store: Store, a) -> None:
    items = store.tasks
    if a.status:
        items = [t for t in items if t["status"] in a.status.split(",")]
    if a.priority:
        items = [t for t in items if t["priority"] in a.priority.split(",")]
    if a.req:
        items = [t for t in items if a.req in t["requirements"]]
    if a.phase:
        items = [t for t in items if t["phase"] == a.phase]
    if a.json:
        print(json.dumps(items, indent=2))
        return
    if not items:
        print("(no tasks)")
        return
    for t in items:
        print(f"{t['id']:<6} {t['status']:<11} {t['priority']} {t['estimate']:<3} {t['title']}"
              + (f"  [deps: {', '.join(t['depends_on'])}]" if t["depends_on"] else ""))


def cmd_show(store: Store, a) -> None:
    print(json.dumps(store.get(a.id), indent=2))


def cmd_next(store: Store, a) -> None:
    ready = ready_tasks(store)[: a.limit]
    if not ready:
        active = [t["id"] for t in store.tasks if t["status"] in ("in_progress", "review", "blocked")]
        print("no ready tasks" + (f" (active/blocked: {', '.join(active)})" if active else ""))
        return
    for t in ready:
        print(f"{t['id']}  {t['priority']}  {t['estimate']:<3} {t['title']}  reqs={','.join(t['requirements']) or '-'}")


def cmd_board(store: Store, a) -> None:
    store.save()
    print(f"board written: {store.dir / BOARD_FILE}")


def cmd_graph(store: Store, a) -> None:
    print(mermaid_graph(store.tasks))


def cmd_waves(store: Store, a) -> None:
    waves, cyclic = dependency_waves(store.tasks)
    tmap = store.by_id()
    if a.json:
        path, length = critical_path(store.tasks)
        print(json.dumps({"waves": waves, "cycle": cyclic, "critical_path": path,
                          "critical_path_points": length}, indent=2))
        return
    for i, wave in enumerate(waves, 1):
        pts = sum(points(tmap[t]) for t in wave if tmap[t]["status"] != "done")
        print(f"Wave {i} ({pts:g} pts remaining): " + ", ".join(
            f"{t}{'✓' if tmap[t]['status'] == 'done' else ''}" for t in wave))
    if cyclic:
        print(f"CYCLE: {', '.join(cyclic)}")
    path, length = critical_path(store.tasks)
    print(f"Critical path ({length:g} pts): {' -> '.join(path) or '-'}")


def cmd_stats(store: Store, a) -> None:
    by_status = defaultdict(int)
    for t in store.tasks:
        by_status[t["status"]] += 1
    print("  ".join(f"{s}={by_status[s]}" for s in STATUSES))
    total = sum(points(t) for t in store.tasks if t["status"] != "cancelled")
    done = sum(points(t) for t in store.tasks if t["status"] == "done")
    print(f"points: {done:g}/{total:g} done")


def validation_problems(store: Store) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    ids = [t["id"] for t in store.tasks]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"duplicate task id {dup}")
    known = set(ids)
    for t in store.tasks:
        for d in t["depends_on"]:
            if d == t["id"]:
                errors.append(f"{t['id']} depends on itself")
            elif d not in known:
                errors.append(f"{t['id']} depends on unknown task {d}")
        if t["status"] == "blocked" and not t["notes"]:
            warnings.append(f"{t['id']} is blocked with no reason note")
        if t["type"] in ("feature", "infra") and not t["requirements"]:
            warnings.append(f"{t['id']} ({t['type']}) is not linked to any requirement")
        if t["type"] == "feature" and not t["acceptance"]:
            warnings.append(f"{t['id']} has no acceptance criteria")
    _, cyclic = dependency_waves(store.tasks)
    if cyclic:
        errors.append(f"dependency cycle among: {', '.join(cyclic)}")
    _, terr, twarn = render_trace(store)
    errors += terr
    warnings += twarn
    return errors, warnings


def cmd_validate(store: Store, a) -> None:
    errors, warnings = validation_problems(store)
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"validate: {len(errors)} error(s), {len(warnings)} warning(s)")
    if errors and not a.warn_only:
        sys.exit(1)


def cmd_trace(store: Store, a) -> None:
    text, errors, warnings = render_trace(store)
    write_atomic(store.dir / TRACE_FILE, text)
    print(text)
    print(f"written: {store.dir / TRACE_FILE} ({len(errors)} error(s), {len(warnings)} warning(s))")


# ---------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--feature", "-f", help="feature slug under specs/ (or env DEVKIT_FEATURE)")
    p.add_argument("--specs-dir", help="specs root (default: specs or env DEVKIT_SPECS_DIR)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def task_fields(sp, defaults: bool):
        sp.add_argument("--title", required=defaults)
        sp.add_argument("--description", "-d")
        sp.add_argument("--type", choices=TYPES)
        sp.add_argument("--priority", "-p", choices=PRIORITIES)
        sp.add_argument("--estimate", "-e", help="XS|S|M|L|XL or numeric points")
        sp.add_argument("--deps", type=split_csv, help="comma-separated task ids")
        sp.add_argument("--reqs", type=split_csv, help="comma-separated requirement ids (FR-001,NFR-002)")
        sp.add_argument("--component")
        sp.add_argument("--phase")
        sp.add_argument("--owner")
        sp.add_argument("--acceptance", "-a", action="append", help="acceptance criterion (repeatable)")

    sp = sub.add_parser("init", help="create tasks.json/TASKS.md")
    sp.add_argument("--title")
    sp.set_defaults(fn=cmd_init)
    sp = sub.add_parser("add", help="add one task")
    task_fields(sp, True)
    sp.set_defaults(fn=cmd_add)
    sp = sub.add_parser("import", help="bulk add/update tasks from JSON")
    sp.add_argument("file")
    sp.add_argument("--replace", action="store_true", help="drop existing tasks first")
    sp.set_defaults(fn=cmd_import)
    sp = sub.add_parser("update", help="edit fields / add a note")
    sp.add_argument("id")
    task_fields(sp, False)
    sp.add_argument("--status", choices=STATUSES)
    sp.add_argument("--note", "-n")
    sp.set_defaults(fn=cmd_update)
    for name, status in (("start", "in_progress"), ("review", "review"), ("done", "done"),
                         ("block", "blocked"), ("reopen", "todo"), ("cancel", "cancelled")):
        sp = sub.add_parser(name, help=f"set status to {status}")
        sp.add_argument("id")
        sp.add_argument("--note", "-n")
        sp.add_argument("--force", action="store_true")
        sp.set_defaults(fn=set_status(status))
    sp = sub.add_parser("list", help="list tasks")
    sp.add_argument("--status")
    sp.add_argument("--priority")
    sp.add_argument("--req")
    sp.add_argument("--phase")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_list)
    sp = sub.add_parser("show")
    sp.add_argument("id")
    sp.set_defaults(fn=cmd_show)
    sp = sub.add_parser("next", help="tasks ready to start")
    sp.add_argument("--limit", type=int, default=5)
    sp.set_defaults(fn=cmd_next)
    sub.add_parser("board", help="re-render TASKS.md").set_defaults(fn=cmd_board)
    sub.add_parser("graph", help="print mermaid dependency graph").set_defaults(fn=cmd_graph)
    sp = sub.add_parser("waves", help="parallel waves + critical path")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_waves)
    sub.add_parser("stats").set_defaults(fn=cmd_stats)
    sp = sub.add_parser("validate", help="check deps, cycles, coverage")
    sp.add_argument("--warn-only", action="store_true")
    sp.set_defaults(fn=cmd_validate)
    sub.add_parser("trace", help="write traceability.md").set_defaults(fn=cmd_trace)
    return p


def main(argv=None) -> None:
    a = build_parser().parse_args(argv)
    store = Store(resolve_feature(a.feature, a.specs_dir))
    a.fn(store, a)


if __name__ == "__main__":
    main()
