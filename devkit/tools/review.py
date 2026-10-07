#!/usr/bin/env python3
"""devkit reviews: decision evaluation and the implementation-readiness gate.

  review.py matrix <slug>        recompute the solutioning comparison matrix: weights, totals,
                                 winner margin and weight-sensitivity (does the winner survive ±20%?)
  review.py decision <ADR>       is this ADR thoroughly evaluated? (options, drivers, evaluation,
                                 trade-offs, evidence, reversibility, pre-mortem, challenge)
  review.py readiness <slug>     may implementation start? Approved designs, resolved design review,
                                 evaluated + accepted decisions, clean docs, valid tracker.
                                 Writes <ws>/03-delivery/readiness.md; exit 1 when not ready.

`tracker.py start` runs the readiness gate for every non-spike task (disable with
.devkit.json → "gates": {"implementation": false}).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import adr as adrlib
import doclint
from devkit_common import (DOCS, artifact_state, die, doc_marker, load_project_config, project_root,
                           read_marker, resolve_feature, today, write_atomic)

READINESS_FILE = DOCS["readiness"]["path"]
APPROVED_REQUIRED = ("requirements", "solutioning", "hld", "lld")
REVIEW_OR_BETTER = ("execution-plan", "test-plan")
CLOSE_CALL_PCT = 10.0
SENSITIVITY_DELTA = 0.20
EVAL_LABELS = ("Comparison", "Sensitivity", "Evidence quality", "Reversibility", "Pre-mortem", "Challenge")
ADR_REQUIRED_SECTIONS = ("Context", "Decision drivers", "Considered options", "Decision", "Consequences",
                         "Compliance & evidence", "Revisit when")
DONE_WORDS = re.compile(r"^(yes|y|done|resolved|fixed|✅|✔|✓)", re.I)


def strip(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S).strip()


def table_rows(body: str) -> list[list[str]]:
    """Data rows (header and separator excluded) of every table in body."""
    rows, lines = [], body.splitlines()
    for i, line in enumerate(lines):
        if not line.strip().startswith("|"):
            continue
        is_sep = re.match(r"^\s*\|[\s:|-]+\|\s*$", line) and "-" in line
        nxt_sep = i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]) and "-" in lines[i + 1]
        if is_sep or nxt_sep:
            continue
        rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows


# ---------------------------------------------------------------- matrix

def parse_matrix(sol_text: str) -> tuple[list[str], list[tuple[str, float, dict[str, float | None]]]]:
    body = adrlib.section(sol_text, "6. Comparison matrix")
    lines = body.splitlines()
    header = next((ln for ln in lines if ln.strip().startswith("|") and "Weight" in ln), None)
    if not header:
        return [], []
    cols = [c.strip() for c in header.strip().strip("|").split("|")]
    options = cols[2:]
    criteria = []
    for row in table_rows(body):
        if len(row) < 3 or re.search(r"\btotal\b", row[0], re.I):
            continue
        wm = re.search(r"\d+(?:\.\d+)?", row[1])
        if not wm:
            continue
        scores = {}
        for opt, cell in zip(options, row[2:]):
            sm = re.match(r"\s*(\d+(?:\.\d+)?)", cell)
            scores[opt] = float(sm.group(1)) if sm else None
        criteria.append((row[0], float(wm.group(0)), scores))
    return options, criteria


def totals(options, criteria, weights=None) -> dict[str, float]:
    weights = weights or [w for _, w, _ in criteria]
    return {o: sum(w * c[2][o] for w, c in zip(weights, criteria)) for o in options}


def evaluate_matrix(ws: Path) -> dict:
    """Errors/warnings plus computed facts for the solutioning comparison."""
    sol_path = ws / DOCS["solutioning"]["path"]
    res = {"errors": [], "warnings": [], "winner": None, "margin_pct": None, "flips": [], "totals": {},
           "recommended": None}
    if not sol_path.exists():
        res["errors"].append("solutioning document missing")
        return res
    text = sol_path.read_text(encoding="utf-8")
    options, criteria = parse_matrix(text)
    if not criteria:
        res["errors"].append("§6 comparison matrix has no scored criteria")
        return res
    scored = [o for o in options if all(c[2].get(o) is not None for c in criteria)]
    partial = [o for o in options if o not in scored and any(c[2].get(o) is not None for c in criteria)]
    for o in partial:
        res["errors"].append(f"§6 {o} is scored on some criteria but not all")
    if len(scored) < 2:
        res["errors"].append(f"§6 needs at least 2 fully scored options (found {len(scored)})")
        return res
    wsum = sum(w for _, w, _ in criteria)
    if abs(wsum - 100) > 0.01:
        res["errors"].append(f"§6 weights sum to {wsum:g}, not 100")
    for name, _, scores in criteria:
        for o in scored:
            if not 1 <= scores[o] <= 5:
                res["errors"].append(f"§6 '{name}' {o} score {scores[o]:g} outside 1–5")
    tot = totals(scored, criteria)
    ranked = sorted(tot, key=tot.get, reverse=True)
    winner, second = ranked[0], ranked[1]
    margin = (tot[winner] - tot[second]) / tot[winner] * 100 if tot[winner] else 0.0
    res.update(totals=tot, winner=winner, margin_pct=round(margin, 1))
    base = [w for _, w, _ in criteria]
    for i, (name, _, _) in enumerate(criteria):
        for factor in (1 - SENSITIVITY_DELTA, 1 + SENSITIVITY_DELTA):
            weights = base.copy()
            weights[i] *= factor
            scale = sum(base) / sum(weights)
            t = totals(scored, criteria, [w * scale for w in weights])
            top = max(t, key=t.get)
            if top != winner:
                res["flips"].append(f"'{name}' weight ×{factor:g} → {top} wins")

    rec = strip(adrlib.section(text, "9. Recommendation"))
    m = re.search(r"\bOption\s+([A-Z])\b", rec)
    override = "**Override:**" in rec
    if not m:
        res["errors"].append("§9 recommendation does not name an option (e.g. 'Option A')")
    else:
        res["recommended"] = f"Option {m.group(1)}"
        if res["recommended"] != winner and not override:
            res["errors"].append(f"§9 recommends {res['recommended']} but the matrix winner is {winner} — "
                                 "fix the scores or add an explicit '**Override:** <reason>' line")
    poc = [r for r in table_rows(adrlib.section(text, "8. Proof-of-concept benchmark"))
           if r and r[-1] and not re.match(r"^(not run|-|tbd|n/?a)?$", strip(r[-1]), re.I)]
    fragile = margin < CLOSE_CALL_PCT or res["flips"]
    if fragile and not poc and not override:
        why = f"margin {margin:.1f}% < {CLOSE_CALL_PCT:g}%" if margin < CLOSE_CALL_PCT else "winner flips under ±20% weights"
        res["errors"].append(f"close call ({why}) without evidence — add a PoC benchmark result to §8 "
                             "or an explicit '**Override:** <reason>' in §9")

    rejected = [r for r in table_rows(adrlib.section(text, "4. Candidate design patterns"))
                if len(r) > 2 and re.search(r"❌|reject", r[2], re.I)]
    if not rejected:
        res["errors"].append("§4 rejects no candidate pattern — record at least one rejected alternative with its reason")
    opts = [h for h in re.findall(r"^###\s+Option\s+[A-Z]\s*[—-]\s*(.*)$", text, re.M) if strip(h)]
    if len(opts) < 2:
        res["errors"].append(f"§5 describes {len(opts)} named option(s); at least 2 genuinely different options required")
    return res


# ---------------------------------------------------------------- decisions

def evaluate_adr(path: Path) -> tuple[list[str], list[str]]:
    """Completeness of a decision record. Only devkit-format ADRs get the full evaluation."""
    errors, warnings = [], []
    text = path.read_text(encoding="utf-8")
    if read_marker(path)[0] != "adr":
        warnings.append("not a devkit-format ADR — evaluation sections not checked")
        return errors, warnings
    retro = "**Retroactive ADR:**" in strip(text)
    for name in ADR_REQUIRED_SECTIONS:
        if not strip(adrlib.section(text, name)):
            errors.append(f"'{name}' is empty")
    opts = strip(adrlib.section(text, "Considered options"))
    n_opts = len(re.findall(r"^\s*(?:\d+[.)]|[-*])\s+\S", opts, re.M))
    if not retro and n_opts < 2:
        errors.append(f"'Considered options' lists {n_opts} option(s); at least 2 required")
    neg = re.search(r"\*\*Negative[^*]*\*\*[ \t]*(.*)", strip(adrlib.section(text, "Consequences")))
    if not neg or not neg.group(1).strip():
        errors.append("'Consequences' has no negative / accepted trade-off — every real decision costs something")
    ev = strip(adrlib.section(text, "Evaluation"))
    for label in EVAL_LABELS:
        m = re.search(rf"\*\*{re.escape(label)}:\*\*[ \t]*(.*)", ev)
        if not m or not m.group(1).strip():
            errors.append(f"Evaluation '{label}' is not filled in")
    rev = re.search(r"\*\*Reversibility:\*\*[ \t]*(.*)", ev)
    if rev and re.search(r"one-way", rev.group(1), re.I):
        pm = re.search(r"\*\*Pre-mortem:\*\*[ \t]*(.*)", ev)
        if pm and len(pm.group(1)) < 40:
            warnings.append("one-way-door decision with a thin pre-mortem — expand failure reasons and mitigations")
    if not strip(adrlib.section(text, "Related")):
        warnings.append("'Related' is empty — link requirements and related ADRs")
    return errors, warnings


def feature_decisions(ws: Path, adrs: list[dict]) -> list[dict]:
    """ADRs stored in the workspace plus repo ADRs listed in solutioning §10."""
    mine = [x for x in adrs if x["scope"] == f"feature:{ws.name}"]
    sol = ws / DOCS["solutioning"]["path"]
    listed = set()
    if sol.exists():
        listed = {int(n) for n in adrlib.ID_RE.findall(strip(adrlib.section(sol.read_text(encoding="utf-8"),
                                                                             "10. New decisions")))}
    extra = [x for x in adrs if x["number"] in listed and x not in mine]
    return mine + extra


# ---------------------------------------------------------------- readiness

def readiness(ws: Path) -> list[tuple[str, bool, list[str]]]:
    checks: list[tuple[str, bool, list[str]]] = []

    problems = []
    for t in APPROVED_REQUIRED:
        state, status = artifact_state(ws / DOCS[t]["path"])
        if status != "Approved":
            problems.append(f"{DOCS[t]['path']} is {status if state != 'missing' else 'missing'} (needs Approved)")
    for t in REVIEW_OR_BETTER:
        state, status = artifact_state(ws / DOCS[t]["path"])
        if status not in ("Review", "Approved"):
            problems.append(f"{DOCS[t]['path']} is {status if state != 'missing' else 'missing'} (needs Review or Approved)")
    checks.append(("Design documents approved", not problems, problems))

    problems = []
    rv = ws / DOCS["design-review"]["path"]
    if not rv.exists():
        problems.append("design review missing — run the design-reviewer agent")
    else:
        text = rv.read_text(encoding="utf-8")
        verdict = strip(adrlib.section(text, "1. Verdict"))
        if not re.search(r"\bAPPROVE\b", verdict) or re.search(r"\bREWORK\b", verdict):
            problems.append(f"verdict is not APPROVE / APPROVE WITH CHANGES ({verdict[:60] or 'empty'})")
        blocking = strip(adrlib.section(text, "3. Blocking findings"))
        if not re.match(r"^(none|n/?a)\b", blocking, re.I):
            for row in table_rows(blocking):
                if len(row) >= 6 and not DONE_WORDS.match(row[5]):
                    problems.append(f"blocking finding #{row[0]} unresolved: {row[2][:70]}")
        _, status = artifact_state(rv)
        if status != "Approved":
            problems.append(f"design review status is {status} (needs Approved)")
    checks.append(("Design review passed, blocking findings resolved", not problems, problems))

    m = evaluate_matrix(ws)
    detail = list(m["errors"])
    if m["winner"]:
        detail.append(f"winner {m['winner']} by {m['margin_pct']}%"
                      + (f"; sensitivity flips: {'; '.join(m['flips'])}" if m["flips"] else "; robust to ±20% weights"))
    checks.append(("Options thoroughly compared (matrix, sensitivity, evidence)", not m["errors"], detail))

    adrs = adrlib.load_registry(refresh=True)
    errors, _ = adrlib.check_feature(ws, adrs)
    checks.append(("Prior decisions respected (ADR check)", not errors, errors))

    problems = []
    decisions = feature_decisions(ws, adrs)
    if not decisions:
        sol = ws / DOCS["solutioning"]["path"]
        new_section = strip(adrlib.section(sol.read_text(encoding="utf-8"), "10. New decisions")) if sol.exists() else ""
        if not re.match(r"^(none|n/?a)\b", new_section, re.I):
            problems.append("no ADR recorded for this feature — significant decisions need ADRs "
                            "(or write 'None — <reason>' in solutioning §10)")
    for x in decisions:
        if x["status"] != "Accepted":
            problems.append(f"{x['id']} '{x['title'][:50]}' is {x['status']} — the user must accept it")
        errs, _ = evaluate_adr(project_root() / x["path"])
        problems += [f"{x['id']}: {e}" for e in errs]
    checks.append(("Decisions evaluated and accepted", not problems, problems))

    problems = []
    for f in sorted(ws.rglob("*.md")):
        if read_marker(f)[0]:
            errs, _ = doclint.lint_file(f)
            problems += [f"{f.relative_to(ws)}: {e}" for e in errs]
    checks.append(("Documents match their templates", not problems, problems))

    from tracker import Store, validation_problems
    store = Store(ws)
    errors, _ = validation_problems(store)
    if not store.tasks:
        errors.append("no tasks in the tracker")
    checks.append(("Tasks valid and traceable", not errors, errors))
    return checks


def render_readiness(ws: Path, checks) -> str:
    ready = all(ok for _, ok, _ in checks)
    out = [doc_marker("readiness", generated=True), f"# Implementation Readiness — {ws.name}", "",
           f"_Generated by `devkit/tools/review.py readiness` on {today()} — do not edit by hand._", "",
           f"**Verdict:** {'✅ READY — implementation may start' if ready else '⛔ NOT READY — resolve the failures below'}",
           "", "| Check | Result | Details |", "|---|---|---|"]
    for name, ok, detail in checks:
        out.append(f"| {name} | {'✅ pass' if ok else '❌ fail'} | {'<br>'.join(d.replace('|', '/') for d in detail) or '-'} |")
    return "\n".join(out) + "\n"


def gate_enabled() -> bool:
    return load_project_config().get("gates", {}).get("implementation", True)


# ---------------------------------------------------------------- CLI

def cmd_matrix(a) -> int:
    ws = resolve_feature(a.feature)
    m = evaluate_matrix(ws)
    for o, t in sorted(m["totals"].items(), key=lambda kv: -kv[1]):
        print(f"{o:<10} {t:g}{'  ← winner' if o == m['winner'] else ''}")
    if m["winner"]:
        print(f"margin: {m['margin_pct']}% · recommended: {m['recommended'] or '-'}")
        print("sensitivity (±20% per criterion): " + ("robust" if not m["flips"] else "FRAGILE — " + "; ".join(m["flips"])))
    for w in m["warnings"]:
        print(f"WARN  {w}")
    for e in m["errors"]:
        print(f"ERROR {e}")
    return 1 if m["errors"] else 0


def cmd_decision(a) -> int:
    x = adrlib.find(adrlib.load_registry(refresh=True), a.ref)
    errors, warnings = evaluate_adr(project_root() / x["path"])
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    status_note = "" if x["status"] == "Accepted" else f" (status {x['status']} — not yet accepted)"
    print(f"{x['id']} {x['title']}: {'thoroughly evaluated' if not errors else f'{len(errors)} gap(s)'}{status_note}")
    return 1 if errors else 0


def cmd_readiness(a) -> int:
    ws = resolve_feature(a.feature)
    checks = readiness(ws)
    write_atomic(ws / READINESS_FILE, render_readiness(ws, checks))
    for name, ok, detail in checks:
        print(f"{'✅' if ok else '❌'} {name}")
        for d in detail if (not ok or a.verbose) else []:
            print(f"     - {d}")
    ready = all(ok for _, ok, _ in checks)
    print(f"\n{'READY' if ready else 'NOT READY'} — report: {ws / READINESS_FILE}")
    return 0 if ready else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("matrix", help="recompute comparison matrix + sensitivity")
    sp.add_argument("feature", nargs="?")
    sp.set_defaults(fn=cmd_matrix)
    sp = sub.add_parser("decision", help="evaluation completeness of one ADR")
    sp.add_argument("ref")
    sp.set_defaults(fn=cmd_decision)
    sp = sub.add_parser("readiness", help="implementation-readiness gate")
    sp.add_argument("feature", nargs="?")
    sp.add_argument("-v", "--verbose", action="store_true")
    sp.set_defaults(fn=cmd_readiness)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
