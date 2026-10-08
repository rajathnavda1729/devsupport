#!/usr/bin/env python3
"""devkit architecture decision records (ADRs).

Detects ADRs already present in the target repo (Nygard / adr-tools, MADR 2 & 3,
Y-statements and devkit's own format), keeps a repo-wide decision log, and
records new decisions from the devkit template so earlier decisions are
considered and later ones stay consistent.

Examples:
  adr.py scan                                  # discover ADRs, write <decisions_dir>/decision-log.{md,json}
  adr.py list --status accepted
  adr.py search payments retry idempotency     # prior decisions relevant to a topic
  adr.py show 7
  adr.py new --title "Use transactional outbox for payment events" --feature payment-retry --tags messaging
  adr.py new --title "PostgreSQL is the system of record" --retroactive --tags data
  adr.py new --title "Move to Kafka" --supersedes 4
  adr.py set-status 12 accepted
  adr.py retitle 12 --title "Revised decision title"     # Proposed ADRs only
  adr.py check payment-retry                   # feature docs cite existing, non-superseded ADRs
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from devkit_common import (ADR_CONF, DOCS, TEMPLATES_DIR, all_features, decisions_dir, die, doc_marker,
                           load_project_config, project_root, read_marker, resolve_feature,
                           save_project_config, today, write_atomic)

STATUSES = ["Proposed", "Accepted", "Rejected", "Deprecated", "Superseded"]
INACTIVE = {"Rejected", "Deprecated", "Superseded"}
ADR_DIR_NAMES = {"adr", "adrs", "decisions", "architecture-decisions", "decision-records", "decision-log"}
SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", ".venv", "venv", "__pycache__", ".next",
             "target", ".tox", ".idea", ".claude", "coverage", ".gradle", "bin", "obj"}
NON_ADR_NAMES = {"readme.md", "index.md", "template.md", "adr-template.md", "decision-log.md", "_template.md"}
ADR_FILE_RE = re.compile(r"^(?:adr[-_ ]?)?(\d{1,5})[-_ ].+\.md$", re.I)
LOG_MD, LOG_JSON = "decision-log.md", "decision-log.json"
ID_RE = re.compile(r"\bADR[-_ ]?(\d{1,5})\b", re.I)


# ---------------------------------------------------------------- parsing

def norm_status(raw: str | None) -> str:
    s = (raw or "").lower()
    for key, status in (("supersed", "Superseded"), ("deprecat", "Deprecated"), ("reject", "Rejected"),
                        ("accept", "Accepted"), ("approv", "Accepted"), ("propos", "Proposed"),
                        ("draft", "Proposed"), ("review", "Proposed")):
        if key in s:
            return status
    return "Unknown"


def front_matter(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end < 0:
        return {}
    fm = {}
    for line in text[4:end].splitlines():
        k, sep, v = line.partition(":")
        if sep and not line.startswith((" ", "-")):
            fm[k.strip().lower()] = v.strip().strip("\"'")
    return fm


def section(text: str, *names: str) -> str:
    """Body of the first H2 whose title starts with one of names (case-insensitive)."""
    for name in names:
        m = re.search(rf"^##\s+{re.escape(name)}[^\n]*\n(.*?)(?=^##\s|\Z)", text, re.M | re.S | re.I)
        if m:
            return m.group(1)
    return ""


def first_paragraph(body: str) -> str:
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    for para in re.split(r"\n\s*\n", body):
        para = " ".join(line.strip() for line in para.strip().splitlines())
        if para:
            return para[:220] + ("…" if len(para) > 220 else "")
    return ""


def detect_format(text: str, fm: dict, marker: str | None) -> str:
    if marker == "adr":
        return "devkit"
    if fm or re.search(r"^##\s+(Context and Problem Statement|Decision Outcome)", text, re.M | re.I):
        return "madr"
    if re.search(r"^##\s+Status", text, re.M | re.I) and re.search(r"^##\s+Decision", text, re.M | re.I):
        return "nygard"
    if re.search(r"\bIn the context of\b", text, re.I):
        return "y-statement"
    return "other"


def parse_adr(path: Path, root: Path, workspaces: dict[str, Path]) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    fm = front_matter(text)
    marker, _ = read_marker(path)
    fmt = detect_format(text, fm, marker)
    h1 = next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")), path.stem)
    title = re.sub(r"^(?:ADR[-_ ]?\d+\s*[:.\-–—]\s*|\d+\.\s*)", "", h1, flags=re.I).strip()
    m = ADR_FILE_RE.match(path.name) or re.match(r"ADR[-_ ]?(\d+)", h1, re.I)
    number = int(m.group(1)) if m else None

    status_text = ""
    for rx in (r"^\*\*Status:\*\*\s*(.+)$", r"^[*-]\s*Status:\s*(.+)$", r"^Status:\s*(.+)$"):
        sm = re.search(rx, text, re.M | re.I)
        if sm:
            status_text = sm.group(1)
            break
    status_text = fm.get("status") or status_text or section(text, "Status")
    status = norm_status(status_text)
    sup_by = re.search(r"Superseded by:?\**\s*\[?(?:ADR[-_ ]?)?(\d+)", text, re.I)
    sups = re.search(r"Supersedes:?\**\s*\[?(?:ADR[-_ ]?)?(\d+)", text, re.I)
    if sup_by and status != "Superseded":
        status = "Superseded"
    date = fm.get("date") or next((dm.group(1) for rx in (r"^\*\*Date:\*\*\s*([\d-]{8,10})", r"^[*-]?\s*Date:\s*([\d-]{8,10})")
                                   if (dm := re.search(rx, text, re.M | re.I))), "")
    tags = fm.get("tags", "")
    tm = re.search(r"\*\*Tags:\*\*\s*([^·\n]+)", text)
    if tm:
        tags = tm.group(1).strip()
    tags = ", ".join(t.strip() for t in re.split(r"[,\[\]]", tags) if t.strip() and t.strip() not in ("-", "{{tags}}"))
    summary = first_paragraph(section(text, "Decision Outcome", "Decision")) or first_paragraph(
        section(text, "Context")) or (first_paragraph(text.split("\n", 1)[-1]) if fmt == "y-statement" else "")

    rel = path.resolve().relative_to(root).as_posix()
    scope = "repo"
    for slug, ws in workspaces.items():
        try:
            path.resolve().relative_to(ws.resolve())
            scope = f"feature:{slug}"
            break
        except ValueError:
            continue
    return {"id": f"ADR-{number:04d}" if number is not None else None, "number": number, "title": title,
            "status": status, "status_raw": " ".join(status_text.split())[:80], "date": date, "tags": tags,
            "superseded_by": int(sup_by.group(1)) if sup_by else None,
            "supersedes": int(sups.group(1)) if sups else None,
            "format": fmt, "scope": scope, "path": rel, "summary": summary}


# ---------------------------------------------------------------- discovery

def adr_dirs(root: Path, workspaces: dict[str, Path]) -> list[Path]:
    dirs: list[Path] = []
    adr_dir_file = root / ".adr-dir"          # adr-tools convention
    if adr_dir_file.exists():
        dirs.append(root / adr_dir_file.read_text().strip())
    cfg = load_project_config()
    if cfg.get("decisions_dir"):
        dirs.append(root / cfg["decisions_dir"])
    for ws in workspaces.values():
        for sub in (ADR_CONF["feature_dir"], "adr"):  # grouped + legacy flat layout
            dirs.append(ws / sub)
    kit = (root / "devkit").resolve()
    for cur, subdirs, _ in os.walk(root):
        subdirs[:] = [d for d in subdirs if d not in SKIP_DIRS and (Path(cur) / d).resolve() != kit]
        for d in subdirs:
            if d.lower() in ADR_DIR_NAMES:
                dirs.append(Path(cur) / d)
    seen, out = set(), []
    for d in dirs:
        r = d.resolve()
        if r not in seen and d.is_dir():
            seen.add(r)
            out.append(d)
    return out


def looks_like_adr(path: Path) -> bool:
    if path.name.lower() in NON_ADR_NAMES or path.suffix.lower() != ".md":
        return False
    marker, generated = read_marker(path)
    if marker:
        return marker == "adr" and not generated
    head = path.read_text(encoding="utf-8", errors="replace")[:4000]
    has_shape = bool(re.search(r"^##\s+(Status|Context|Decision)", head, re.M | re.I)
                     or re.search(r"^(\*\*Status:\*\*|[*-]\s*Status:|status:)", head, re.M | re.I)
                     or re.search(r"\bIn the context of\b", head, re.I))
    return has_shape and (bool(ADR_FILE_RE.match(path.name)) or bool(re.search(r"^##\s+Decision", head, re.M | re.I)))


def discover() -> list[dict]:
    root = project_root()
    workspaces = all_features()
    adrs = []
    for d in adr_dirs(root, workspaces):
        for f in sorted(d.rglob("*.md")):
            if looks_like_adr(f):
                adrs.append(parse_adr(f, root, workspaces))
    adrs.sort(key=lambda a: (a["number"] is None, a["number"] or 0, a["path"]))
    return adrs


def registry_problems(adrs: list[dict]) -> list[str]:
    problems = []
    by_num: dict[int, list[dict]] = {}
    for a in adrs:
        if a["number"] is not None:
            by_num.setdefault(a["number"], []).append(a)
        else:
            problems.append(f"{a['path']}: no ADR number in file name or title")
        if a["status"] == "Unknown":
            problems.append(f"{a['path']}: status not recognised ({a['status_raw'] or 'missing'})")
        if a["superseded_by"] is not None and a["superseded_by"] not in {x["number"] for x in adrs}:
            problems.append(f"{a['path']}: superseded by ADR-{a['superseded_by']:04d}, which does not exist")
    for num, group in sorted(by_num.items()):
        if len(group) > 1:
            problems.append(f"ADR number {num:04d} used by several files: " + ", ".join(g["path"] for g in group))
    return problems


def choose_decisions_dir(adrs: list[dict]) -> str:
    cfg = load_project_config()
    if cfg.get("decisions_dir"):
        return cfg["decisions_dir"]
    root = project_root()
    if (root / ".adr-dir").exists():
        return (root / ".adr-dir").read_text().strip()
    counts: dict[str, int] = {}
    for a in adrs:
        if a["scope"] == "repo":
            parent = str(Path(a["path"]).parent)
            counts[parent] = counts.get(parent, 0) + 1
    return max(counts, key=counts.get) if counts else ADR_CONF["default_repo_dir"]


def write_registry(adrs: list[dict]) -> Path:
    ddir = decisions_dir()
    ddir.mkdir(parents=True, exist_ok=True)
    root = project_root()
    write_atomic(ddir / LOG_JSON, json.dumps({"generated": today(), "adrs": adrs}, indent=2) + "\n")
    rel = lambda p: os.path.relpath(root / p, ddir)
    lines = [doc_marker("decision-log", generated=True), "# Decision Log", "",
             f"_Generated by `devkit/tools/adr.py scan` on {today()} — do not edit by hand. "
             "Accepted decisions are binding for new designs; change them only through a superseding ADR._", ""]
    active = [a for a in adrs if a["status"] not in INACTIVE]
    lines += [f"**{len(adrs)} ADRs** · {sum(a['status'] == 'Accepted' for a in adrs)} accepted · "
              f"{sum(a['status'] == 'Proposed' for a in adrs)} proposed · "
              f"{len(adrs) - len(active)} superseded/deprecated/rejected", ""]
    if not adrs:
        lines += ["No architecture decision records found in this repository yet. "
                  "Use the `adr-discovery` skill to document decisions already in force.", ""]
    for heading, items in (("Repository-wide decisions", [a for a in adrs if a["scope"] == "repo"]),
                           ("Feature decisions", [a for a in adrs if a["scope"] != "repo"])):
        if not items:
            continue
        lines += [f"## {heading}", "", "| ADR | Title | Status | Date | Scope | Tags | Summary |",
                  "|-----|-------|--------|------|-------|------|---------|"]
        for a in items:
            status = a["status"] + (f" → ADR-{a['superseded_by']:04d}" if a["superseded_by"] else "")
            lines.append(f"| [{a['id'] or '?'}]({rel(a['path'])}) | {a['title']} | {status} | {a['date'] or '-'} | "
                         f"{a['scope']} | {a['tags'] or '-'} | {a['summary'].replace('|', '/') or '-'} |")
        lines.append("")
    problems = registry_problems(adrs)
    if problems:
        lines += ["## ⚠️ Registry problems", "", *(f"- {p}" for p in problems), ""]
    write_atomic(ddir / LOG_MD, "\n".join(lines))
    return ddir


def load_registry(refresh: bool = True) -> list[dict]:
    if refresh:
        adrs = discover()
        cfg = load_project_config()
        if not cfg.get("decisions_dir"):
            cfg["decisions_dir"] = choose_decisions_dir(adrs)
            save_project_config(cfg)
        write_registry(adrs)
        return adrs
    path = decisions_dir() / LOG_JSON
    return json.loads(path.read_text())["adrs"] if path.exists() else discover()


def find(adrs: list[dict], ref: str) -> dict:
    m = re.fullmatch(r"(?:ADR[-_ ]?)?(\d{1,5})", ref.strip(), re.I)
    matches = [a for a in adrs if (m and a["number"] == int(m.group(1))) or a["path"] == ref]
    if not matches:
        die(f"no ADR matches {ref!r} (run: adr.py list)")
    if len(matches) > 1:
        die(f"{ref} is ambiguous: " + ", ".join(a["path"] for a in matches) + " — pass the path instead")
    return matches[0]


# ---------------------------------------------------------------- editing

def naming_style(target_dir: Path) -> tuple[str, int]:
    """(prefix, digit width) of existing ADR files: target dir first, then the repo decisions dir; default ADR-0001."""
    for d in (target_dir, decisions_dir()):
        for f in sorted(d.glob("*.md")) if d.is_dir() else []:
            m = re.match(r"^(adr[-_ ]?)?(\d{1,5})[-_ ]", f.name, re.I)
            if m:
                return (m.group(1) or ""), len(m.group(2))
    return "ADR-", 4


def set_status_in_file(path: Path, new_status: str, superseded_by: int | None = None) -> None:
    text = path.read_text(encoding="utf-8")
    label = new_status + (f" by ADR-{superseded_by:04d}" if superseded_by else "")
    marker, _ = read_marker(path)
    fm = front_matter(text)
    if marker == "adr" or re.search(r"^\*\*Status:\*\*", text, re.M):
        text = re.sub(r"^\*\*Status:\*\*.*$", f"**Status:** {new_status}", text, count=1, flags=re.M)
        if superseded_by:
            text = re.sub(r"(\*\*Superseded by:\*\*)\s*[^\n·]*", rf"\1 ADR-{superseded_by:04d}", text, count=1)
    elif fm.get("status") is not None:
        text = re.sub(r"^status:.*$", f"status: {label.lower()}", text, count=1, flags=re.M)
    elif re.search(r"^[*-]\s*Status:", text, re.M | re.I):
        text = re.sub(r"^([*-]\s*Status:).*$", rf"\1 {label.lower()}", text, count=1, flags=re.M | re.I)
    elif re.search(r"^##\s+Status", text, re.M | re.I):
        text = re.sub(r"(^##\s+Status[^\n]*\n)(.*?)(?=^##\s|\Z)", lambda m: f"{m.group(1)}\n{label}\n\n", text,
                      count=1, flags=re.M | re.S | re.I)
    else:
        text = re.sub(r"^(# .*\n)", rf"\1\n**Status:** {label}\n", text, count=1, flags=re.M)
    write_atomic(path, text)


def render_template(ctx: dict) -> str:
    tpl = (TEMPLATES_DIR / ADR_CONF["template"]).read_text(encoding="utf-8")
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: str(ctx.get(m.group(1), m.group(0))), tpl)


# ---------------------------------------------------------------- commands

def print_table(adrs: list[dict]) -> None:
    if not adrs:
        print("(no ADRs)")
        return
    for a in adrs:
        sup = f" → ADR-{a['superseded_by']:04d}" if a["superseded_by"] else ""
        print(f"{a['id'] or '?':<9} {a['status'] + sup:<24} {a['scope']:<22} {a['title'][:60]}  ({a['path']})")


def cmd_scan(a) -> int:
    adrs = load_registry(refresh=True)
    ddir = decisions_dir()
    if a.json:
        print(json.dumps(adrs, indent=2))
        return 0
    formats: dict[str, int] = {}
    for x in adrs:
        formats[x["format"]] = formats.get(x["format"], 0) + 1
    print(f"found {len(adrs)} ADR(s)" + (f" — formats: {', '.join(f'{k}={v}' for k, v in formats.items())}" if adrs else ""))
    print_table(adrs)
    for p in registry_problems(adrs):
        print(f"WARN  {p}")
    print(f"decision log: {ddir / LOG_MD}")
    return 0


def cmd_list(a) -> int:
    adrs = load_registry(refresh=not a.cached)
    if a.status:
        wanted = {norm_status(s) for s in a.status.split(",")}
        adrs = [x for x in adrs if x["status"] in wanted]
    if a.feature:
        adrs = [x for x in adrs if x["scope"] == f"feature:{a.feature}"]
    elif a.scope == "repo":
        adrs = [x for x in adrs if x["scope"] == "repo"]
    print(json.dumps(adrs, indent=2)) if a.json else print_table(adrs)
    return 0


def cmd_search(a) -> int:
    adrs = load_registry(refresh=not a.cached)
    root = project_root()
    terms = [t.lower() for t in a.terms]
    scored = []
    for x in adrs:
        if not a.all and x["status"] in INACTIVE:
            continue
        body = (root / x["path"]).read_text(encoding="utf-8", errors="replace").lower()
        score = sum(3 * x["title"].lower().count(t) + 2 * x["tags"].lower().count(t) + min(body.count(t), 5)
                    for t in terms)
        if score:
            scored.append((score, x))
    scored.sort(key=lambda s: -s[0])
    if not scored:
        print("no matching ADRs" + ("" if a.all else " (active only; --all includes superseded/rejected)"))
        return 0
    for score, x in scored[: a.limit]:
        print(f"[{score:>3}] {x['id'] or '?':<9} {x['status']:<11} {x['title'][:70]}\n      {x['path']}"
              + (f"\n      {x['summary'][:160]}" if x["summary"] else ""))
    return 0


def cmd_show(a) -> int:
    x = find(load_registry(refresh=not a.cached), a.ref)
    print(json.dumps({k: v for k, v in x.items() if k != "summary"}, indent=2))
    print("-" * 60)
    print((project_root() / x["path"]).read_text(encoding="utf-8"))
    return 0


def cmd_new(a) -> int:
    adrs = load_registry(refresh=True)
    numbers = [x["number"] for x in adrs if x["number"] is not None]
    num = (max(numbers) + 1) if numbers else 1
    if a.feature:
        ws = resolve_feature(a.feature)
        target = ws / ADR_CONF["feature_dir"]
        scope = f"feature `{a.feature}`"
    else:
        target = decisions_dir()
        scope = "repository"
    target.mkdir(parents=True, exist_ok=True)
    prefix, width = naming_style(target)
    slug = re.sub(r"[^a-z0-9]+", "-", a.title.lower()).strip("-")
    if len(slug) > 60:  # cut at a word boundary, never mid-word
        slug = slug[:61].rsplit("-", 1)[0]
    path = target / f"{prefix}{num:0{width}d}-{slug}.md"
    old = find(adrs, str(a.supersedes)) if a.supersedes else None
    status = norm_status(a.status) if a.status else ("Accepted" if a.retroactive else "Proposed")
    text = render_template({
        "adr_id": f"ADR-{num:04d}", "title": a.title, "status": status, "date": today(), "scope": scope,
        "tags": a.tags or "-", "supersedes": old["id"] if old else "-"})
    if a.retroactive:
        text = text.replace("## Context\n", "## Context\n> **Retroactive ADR:** documents a decision already in force "
                                            "in the codebase. Evidence is listed under *Compliance & evidence*.\n\n", 1)
    write_atomic(path, text)
    if old:
        set_status_in_file(project_root() / old["path"], "Superseded", superseded_by=num)
    load_registry(refresh=True)
    print(path)
    if old:
        print(f"marked {old['id']} ({old['path']}) as superseded by ADR-{num:04d}")
    return 0


def cmd_supersede(a) -> int:
    adrs = load_registry(refresh=True)
    old, new = find(adrs, a.old), find(adrs, a.new)
    set_status_in_file(project_root() / old["path"], "Superseded", superseded_by=new["number"])
    new_path = project_root() / new["path"]
    text = new_path.read_text(encoding="utf-8")
    if re.search(r"\*\*Supersedes:\*\*", text):
        write_atomic(new_path, re.sub(r"(\*\*Supersedes:\*\*)\s*[^\n·]*", rf"\1 {old['id']} ", text, count=1))
    load_registry(refresh=True)
    print(f"{old['id']} superseded by {new['id']}")
    return 0


def cmd_set_status(a) -> int:
    status = norm_status(a.status)
    if status not in STATUSES or status == "Superseded":
        die(f"status must be one of {', '.join(s for s in STATUSES if s != 'Superseded')} (use 'supersede' for that)")
    x = find(load_registry(refresh=True), a.ref)
    set_status_in_file(project_root() / x["path"], status)
    load_registry(refresh=True)
    print(f"{x['id']} -> {status}")
    return 0


def check_feature(ws: Path, adrs: list[dict]) -> tuple[list[str], list[str]]:
    """A feature's docs must cite ADRs that exist and are still in force, and fill the decision sections."""
    by_num = {x["number"]: x for x in adrs if x["number"] is not None}
    errors, warnings = [], []
    for doc_type in ("solutioning", "hld", "lld", "requirements"):
        path = ws / DOCS[doc_type]["path"]
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        cited = sorted({int(n) for n in ID_RE.findall(re.sub(r"<!--.*?-->", "", text, flags=re.S))})
        for n in cited:
            x = by_num.get(n)
            if not x:
                errors.append(f"{DOCS[doc_type]['path']}: cites ADR-{n:04d}, which does not exist")
            elif x["status"] == "Superseded":
                repl = f" — use ADR-{x['superseded_by']:04d}" if x["superseded_by"] else ""
                warnings.append(f"{DOCS[doc_type]['path']}: cites superseded {x['id']}{repl}")
            elif x["status"] in ("Rejected", "Deprecated"):
                warnings.append(f"{DOCS[doc_type]['path']}: cites {x['status'].lower()} {x['id']}")
    sol = ws / DOCS["solutioning"]["path"]
    if sol.exists():
        ctx = section(sol.read_text(encoding="utf-8"), "1. Decision context")
        rows = [ln for ln in ctx.splitlines() if ln.startswith("|") and not re.match(r"^\|\s*(ADR\s*\||-)", ln)]
        accepted_repo = [x for x in adrs if x["scope"] == "repo" and x["status"] == "Accepted"]
        if accepted_repo and not rows and "none" not in ctx.lower():
            errors.append(f"{DOCS['solutioning']['path']} §1 is empty but the repo has {len(accepted_repo)} accepted "
                          "ADR(s) — run adr.py search and record their impact (or write 'None relevant' with reason)")
    # "Decisions applied" tables must reflect the decisions actually in force.
    applied_sections = {"hld": "2. Architecture decisions applied", "lld": "13. Decisions applied"}
    applied: dict[str, set[int]] = {}
    for doc_type, sec in applied_sections.items():
        path = ws / DOCS[doc_type]["path"]
        if not path.exists():
            continue
        body = re.sub(r"<!--.*?-->", "", section(path.read_text(encoding="utf-8"), sec), flags=re.S)
        ids = {int(n) for ln in body.splitlines() if ln.startswith("|") for n in ID_RE.findall(ln.split("|")[1])}
        applied[doc_type] = ids
        for n in sorted(ids):
            x = by_num.get(n)
            if x and x["status"] in INACTIVE:
                errors.append(f"{DOCS[doc_type]['path']} §{sec.split('.')[0]} applies {x['status'].lower()} {x['id']} — "
                              "remove it or replace it with the decision now in force")
    if sol.exists() and applied.get("hld"):
        in_force = {int(n) for n in ID_RE.findall(re.sub(r"<!--.*?-->", "", section(sol.read_text(encoding="utf-8"),
                                                                                    "10. New decisions"), flags=re.S))}
        for n in sorted(in_force):
            x = by_num.get(n)
            if x and x["status"] not in INACTIVE and n not in applied["hld"]:
                errors.append(f"{DOCS['hld']['path']} §2 does not apply {x['id']} from solutioning §10 — "
                              "the HLD may be stale relative to the chosen solution")
    for x in adrs:
        if x["scope"] == f"feature:{ws.name}" and x["status"] == "Proposed":
            warnings.append(f"{x['id']} ({x['path']}) is still Proposed")
    return errors, warnings


def cmd_retitle(a) -> int:
    """Rename a Proposed ADR (title + file name) after its content was revised before acceptance."""
    adrs = load_registry(refresh=True)
    x = find(adrs, a.ref)
    if x["status"] != "Proposed":
        die(f"{x['id']} is {x['status']} — only Proposed ADRs can be retitled; write a superseding ADR instead")
    old = project_root() / x["path"]
    if read_marker(old)[0] != "adr":
        die(f"{x['path']} is not a devkit-format ADR")
    text = re.sub(r"^# .*$", f"# {x['id']}: {a.title}", old.read_text(encoding="utf-8"), count=1, flags=re.M)
    m = re.match(r"^((?:adr[-_ ]?)?\d+[-_ ])", old.name, re.I)
    slug = re.sub(r"[^a-z0-9]+", "-", a.title.lower()).strip("-")
    if len(slug) > 60:
        slug = slug[:61].rsplit("-", 1)[0]
    new = old.with_name(f"{m.group(1) if m else ''}{slug}.md")
    write_atomic(new, text)
    if new != old:
        old.unlink()
    load_registry(refresh=True)
    print(new)
    return 0


def cmd_check(a) -> int:
    ws = resolve_feature(a.feature)
    errors, warnings = check_feature(ws, load_registry(refresh=True))
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"adr check {ws.name}: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("scan", help="discover ADRs and write the decision log")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_scan)
    sp = sub.add_parser("list", help="list ADRs")
    sp.add_argument("--status", help="comma list, e.g. accepted,proposed")
    sp.add_argument("--scope", choices=["repo", "all"], default="all")
    sp.add_argument("--feature", help="only ADRs recorded in this feature's workspace")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--cached", action="store_true", help="use decision-log.json instead of rescanning")
    sp.set_defaults(fn=cmd_list)
    sp = sub.add_parser("search", help="rank ADRs relevant to keywords")
    sp.add_argument("terms", nargs="+")
    sp.add_argument("--all", action="store_true", help="include superseded/rejected/deprecated")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--cached", action="store_true")
    sp.set_defaults(fn=cmd_search)
    sp = sub.add_parser("show", help="show one ADR (number, ADR-id or path)")
    sp.add_argument("ref")
    sp.add_argument("--cached", action="store_true")
    sp.set_defaults(fn=cmd_show)
    sp = sub.add_parser("new", help="record a new ADR from the template")
    sp.add_argument("--title", required=True)
    sp.add_argument("--feature", help="feature slug: store in its 02-design/decisions/ (default: repo decisions dir)")
    sp.add_argument("--status", help="initial status (default Proposed; Accepted with --retroactive)")
    sp.add_argument("--tags")
    sp.add_argument("--supersedes", help="ADR this one replaces (it is marked Superseded)")
    sp.add_argument("--retroactive", action="store_true", help="documents a decision already in force")
    sp.set_defaults(fn=cmd_new)
    sp = sub.add_parser("supersede", help="mark OLD as superseded by NEW")
    sp.add_argument("old")
    sp.add_argument("new")
    sp.set_defaults(fn=cmd_supersede)
    sp = sub.add_parser("set-status", help="Proposed | Accepted | Rejected | Deprecated")
    sp.add_argument("ref")
    sp.add_argument("status")
    sp.set_defaults(fn=cmd_set_status)
    sp = sub.add_parser("retitle", help="rename a Proposed ADR after revising its content")
    sp.add_argument("ref")
    sp.add_argument("--title", required=True)
    sp.set_defaults(fn=cmd_retitle)
    sp = sub.add_parser("check", help="verify a feature's decision references")
    sp.add_argument("feature", nargs="?")
    sp.set_defaults(fn=cmd_check)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
