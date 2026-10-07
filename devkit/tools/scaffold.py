#!/usr/bin/env python3
"""devkit workspace scaffolder.

A feature workspace groups its documents by concern; the layout and the
template behind every document come from devkit/templates/manifest.json:

  <ws>/README.md                      generated index (documents, states, decisions)
  <ws>/01-requirements/               input.md, requirements.md
  <ws>/02-design/                     solutioning.md, hld.md, lld.md, decisions/ (ADRs), reviews/
  <ws>/03-delivery/                   tasks.json, TASKS.md, execution-plan.md
  <ws>/04-quality/                    testing-guide.md, test-plan.md, traceability.md,
                                      benchmark-plan.md, test-report.md, benchmarks/

Examples:
  scaffold.py init --specs-dir docs/specs       # once per repo: where workspaces go by default
  scaffold.py new url-shortener --title "URL Shortener" --input requirement.txt
  scaffold.py new payments-retry --at services/payments --text "Retry failed card payments..."
                                        # -> services/payments/specs/payments-retry/ (next to the code)
  scaffold.py doc payments-retry test-report    # create an on-demand document from its template
  scaffold.py types                     # all document types, templates and locations
  scaffold.py where payments-retry      # print a workspace path
  scaffold.py status url-shortener      # pipeline progress for one feature
  scaffold.py index url-shortener       # regenerate the workspace README
  scaffold.py migrate old-feature       # move a pre-grouping (flat) workspace into groups
  scaffold.py list                      # all feature workspaces
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

from devkit_common import (ADR_CONF, ARTIFACTS, CONFIG_NAME, DOCS, INDEX_FILE, LEGACY_LAYOUT, MANIFEST, SLUG_RE,
                           TASKS_FILE, TEMPLATES_DIR, all_features, artifact_state, die, doc_marker,
                           is_legacy_workspace, load_json, load_project_config, project_root, read_marker,
                           decisions_dir, register_feature, resolve_feature, save_project_config, specs_root, today, write_atomic)

def render(text: str, ctx: dict) -> str:
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: str(ctx.get(m.group(1), m.group(0))), text)


def workspace_ctx(fdir: Path, title: str | None = None) -> dict:
    data = load_json(fdir / TASKS_FILE, {})
    title = title or data.get("title") or fdir.name.replace("-", " ").title()
    try:
        ws = fdir.resolve().relative_to(project_root()).as_posix()
    except ValueError:
        ws = str(fdir)
    return {"title": title, "slug": fdir.name, "date": today(), "ws": ws}


def create_doc(fdir: Path, doc_type: str, ctx: dict, force: bool = False) -> str | None:
    """Render one document from its template. Returns 'created', 'kept' or None (no template)."""
    doc = DOCS[doc_type]
    target = fdir / doc["path"]
    if doc_type == "tasks":
        if not target.exists():
            write_atomic(target, json.dumps({"feature": ctx["slug"], "title": ctx["title"], "tasks": []}, indent=2) + "\n")
            return "created"
        return "kept"
    if not doc.get("template"):
        return None
    if target.exists() and not force:
        return "kept"
    write_atomic(target, render((TEMPLATES_DIR / doc["template"]).read_text(encoding="utf-8"), ctx))
    return "created"


def cmd_new(a) -> None:
    if not SLUG_RE.match(a.slug):
        die("slug must be lowercase letters, digits and dashes (e.g. url-shortener)")
    existing = all_features(a.specs_dir).get(a.slug)
    if a.at:
        module = project_root() / a.at
        if not module.is_dir():
            die(f"--at {a.at}: no such directory under {project_root()}")
        fdir = module / "specs" / a.slug
        if existing and existing.resolve() != fdir.resolve():
            die(f"feature {a.slug} already exists at {existing}")
    else:
        fdir = existing or specs_root(a.specs_dir) / a.slug
    if is_legacy_workspace(fdir):
        die(f"{fdir} uses the old flat layout — run: scaffold.py migrate {a.slug}")
    ctx = workspace_ctx(fdir, a.title)
    raw = ""
    if a.input:
        raw = Path(a.input).read_text(encoding="utf-8")
    elif a.text:
        raw = a.text
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    ctx["input"] = raw.strip() or "<!-- TODO: paste the raw requirement here -->"

    created, kept = [], []
    for doc in MANIFEST["documents"]:
        if not doc.get("pipeline"):
            continue
        result = create_doc(fdir, doc["type"], ctx, a.force)
        (created if result == "created" else kept if result == "kept" else []).append(doc["path"])
    for sub in MANIFEST["dirs"]:
        (fdir / sub).mkdir(parents=True, exist_ok=True)
    if a.at:
        register_feature(a.slug, fdir)
    write_index(fdir)
    print(f"workspace: {fdir}")
    print(f"  created: {', '.join(created) or '-'}")
    if kept:
        print(f"  kept existing (use --force to overwrite): {', '.join(kept)}")
    print(f"next: requirements-breakdown on {fdir / DOCS['requirements']['path']}")


def cmd_doc(a) -> None:
    fdir = resolve_feature(a.slug, a.specs_dir)
    if a.type not in DOCS or not DOCS[a.type].get("template"):
        die(f"unknown or generated document type {a.type!r}; templated types: "
            + ", ".join(t for t, d in DOCS.items() if d.get("template")))
    result = create_doc(fdir, a.type, workspace_ctx(fdir), a.force)
    write_index(fdir)
    print(f"{result}: {fdir / DOCS[a.type]['path']}")


def cmd_types(a) -> None:
    for g in MANIFEST["groups"]:
        print(f"{g['id']}/  {g['title']}")
        for d in MANIFEST["documents"]:
            if d["path"].startswith(g["id"] + "/"):
                src = f"template {d['template']}" if d.get("template") else "generated by tool"
                flag = "" if d.get("pipeline") else "  (on demand: scaffold.py doc <slug> " + d["type"] + ")"
                print(f"  {d['type']:<15} {d['path']:<38} {src}{flag}")
    print(f"ADRs: template {ADR_CONF['template']} → <ws>/{ADR_CONF['feature_dir']}/ or the repo decisions dir")


def status_rows(fdir: Path) -> list[tuple[str, str, str, str]]:
    rows = []
    for name, label in ARTIFACTS:
        state, doc_status = artifact_state(fdir / name)
        rows.append((name, label, state, doc_status))
    return rows


def cmd_status(a) -> None:
    fdir = resolve_feature(a.slug, a.specs_dir)
    if is_legacy_workspace(fdir):
        die(f"{fdir} uses the old flat layout — run: scaffold.py migrate {fdir.name}")
    rows = status_rows(fdir)
    icon = {"missing": "·", "draft": "✎", "filled": "✓"}
    print(f"{fdir.name}  ({fdir})")
    for name, label, state, doc_status in rows:
        print(f"  {icon[state]} {name:<38} {state:<8} {doc_status:<10} {label}")
    nxt = next((r for r in rows if r[2] != "filled"), None)
    if nxt:
        print(f"next step: {nxt[0]} ({nxt[1]})")
    else:
        print("all artifacts filled — run: python3 devkit/tools/tracker.py -f "
              f"{fdir.name} validate")
    write_index(fdir)


GENERATORS = {"tasks": "tracker.py -f {slug} import", "board": "tracker.py -f {slug} board",
              "traceability": "tracker.py -f {slug} trace", "readiness": "review.py readiness {slug}"}


def render_index(fdir: Path) -> str:
    import adr  # local import: adr.py imports this module's siblings only
    ctx = workspace_ctx(fdir)
    out = [doc_marker("index", generated=True), f"# {ctx['title']} — feature workspace", "",
           "_Generated by `devkit/tools/scaffold.py index` — do not edit by hand. "
           "Refreshed whenever a document in this workspace changes._", "",
           f"**Slug:** `{ctx['slug']}` · **Location:** `{ctx['ws']}` · **Updated:** {ctx['date']}", ""]
    out += ["## Documents", ""]
    for g in MANIFEST["groups"]:
        docs = [d for d in MANIFEST["documents"] if d["path"].startswith(g["id"] + "/")]
        out += [f"### {g['title']} — `{g['id']}/`", "", "| Document | File | State | Status |", "|---|---|---|---|"]
        for d in docs:
            path = fdir / d["path"]
            if d["kind"] == "generated":
                hint = GENERATORS.get(d["type"], "its tool").format(slug=ctx["slug"])
                state, status = ("generated" if path.exists() else f"not generated yet (`{hint}`)"), "-"
            elif not path.exists() and not d.get("pipeline"):
                state = f"not created (`scaffold.py doc {ctx['slug']} {d['type']}`)"
                status = "-"
            else:
                state, status = artifact_state(path)
            out.append(f"| {d['title']} | [{d['path']}]({d['path']}) | {state} | {status} |")
        out.append("")
    adrs = adr.load_registry(refresh=False)  # decision-log.json; `adr.py scan` refreshes it
    root = project_root()
    mine = [x for x in adrs if x["scope"] == f"feature:{fdir.name}"]
    cited: set[int] = set()
    for f in fdir.rglob("*.md"):
        if f.name != INDEX_FILE:
            cited |= {int(n) for n in adr.ID_RE.findall(re.sub(r"<!--.*?-->", "", f.read_text(encoding="utf-8"), flags=re.S))}
    repo_cited = [x for x in adrs if x["scope"] == "repo" and x["number"] in cited]
    out += ["## Decisions", ""]
    for heading, items in (("Recorded for this feature", mine), ("Repository decisions this feature relies on", repo_cited)):
        out += [f"### {heading}", ""]
        if not items:
            out += ["None yet.", ""]
            continue
        out += ["| ADR | Title | Status |", "|---|---|---|"]
        for x in items:
            link = os.path.relpath(root / x["path"], fdir)
            out.append(f"| [{x['id']}]({link}) | {x['title']} | {x['status']} |")
        out.append("")
    log = decisions_dir() / adr.LOG_MD
    if log.exists():
        out += [f"Full decision log: [{os.path.relpath(log, fdir)}]({os.path.relpath(log, fdir)})", ""]
    return "\n".join(out)


def write_index(fdir: Path) -> Path:
    path = fdir / INDEX_FILE
    if path.exists() and read_marker(path) != ("index", True):
        return path  # never overwrite a README a human wrote
    write_atomic(path, render_index(fdir))
    return path


def cmd_index(a) -> None:
    print(write_index(resolve_feature(a.slug, a.specs_dir)))


def cmd_migrate(a) -> None:
    fdir = resolve_feature(a.slug, a.specs_dir)
    if not is_legacy_workspace(fdir):
        print(f"{fdir} already uses the grouped layout")
        return
    legacy_types = {d["path"]: t for t, d in DOCS.items()}
    for old, new in LEGACY_LAYOUT.items():
        src, dst = fdir / old, fdir / new
        if not src.exists():
            continue
        if dst.exists() and not (dst.is_dir() and not any(dst.iterdir())):
            print(f"  skip {old}: {new} already exists")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_dir():
            dst.rmdir()
        shutil.move(str(src), str(dst))
        doc_type = legacy_types.get(new)
        if dst.suffix == ".md" and doc_type and read_marker(dst)[0] is None:
            generated = DOCS[doc_type]["kind"] == "generated"
            dst.write_text(doc_marker(doc_type, generated) + "\n" + dst.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  {old} -> {new}")
    for sub in MANIFEST["dirs"]:
        (fdir / sub).mkdir(parents=True, exist_ok=True)
    write_index(fdir)
    print("migrated. Run: python3 devkit/tools/doclint.py --feature " + fdir.name
          + "  (older docs may lack newer template sections, e.g. 'Decision context')")


def cmd_list(a) -> None:
    feats = all_features(a.specs_dir)
    if not feats:
        print(f"no feature workspaces (default location: {specs_root(a.specs_dir)}/)")
        return
    for slug, f in sorted(feats.items()):
        if is_legacy_workspace(f):
            print(f"{slug:<30} legacy layout (scaffold.py migrate {slug})  {f}")
            continue
        rows = status_rows(f)
        filled = sum(1 for r in rows if r[2] == "filled")
        print(f"{slug:<30} {filled}/{len(rows)} filled  {f}")


def cmd_where(a) -> None:
    print(resolve_feature(a.slug, a.specs_dir))


def cmd_init(a) -> None:
    cfg = load_project_config()
    if a.specs_dir_default:
        cfg["specs_dir"] = a.specs_dir_default
    if a.decisions_dir:
        cfg["decisions_dir"] = a.decisions_dir
    path = save_project_config(cfg)
    print(f"{path}: default workspace location = {project_root() / cfg['specs_dir']}"
          + (f", decisions = {project_root() / cfg['decisions_dir']}" if cfg.get("decisions_dir") else ""))


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--specs-dir", help="workspace root override (default: .devkit.json specs_dir or env DEVKIT_SPECS_DIR)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("new", help="create a feature workspace from templates")
    sp.add_argument("slug")
    sp.add_argument("--title")
    src = sp.add_mutually_exclusive_group()
    src.add_argument("--input", "-i", help="file containing the raw requirement")
    src.add_argument("--text", "-t", help="raw requirement text")
    sp.add_argument("--at", help="module/service dir (relative to repo root) that realises the requirement; "
                                 "workspace goes to <at>/specs/<slug> and is registered in " + CONFIG_NAME)
    sp.add_argument("--force", action="store_true", help="overwrite existing artifacts")
    sp.set_defaults(fn=cmd_new)
    sp = sub.add_parser("doc", help="create one document of a given type from its template")
    sp.add_argument("slug")
    sp.add_argument("type")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(fn=cmd_doc)
    sub.add_parser("types", help="list document types, templates and locations").set_defaults(fn=cmd_types)
    sp = sub.add_parser("init", help=f"create/update {CONFIG_NAME} at the repo root")
    sp.add_argument("--specs-dir", dest="specs_dir_default", help="default workspace parent, relative to repo root")
    sp.add_argument("--decisions-dir", help="repo-wide ADR directory, relative to repo root (default: detected or docs/adr)")
    sp.set_defaults(fn=cmd_init)
    sp = sub.add_parser("where", help="print a feature's workspace path")
    sp.add_argument("slug", nargs="?")
    sp.set_defaults(fn=cmd_where)
    sp = sub.add_parser("status", help="pipeline progress for a feature")
    sp.add_argument("slug", nargs="?")
    sp.set_defaults(fn=cmd_status)
    sp = sub.add_parser("index", help="regenerate the workspace README index")
    sp.add_argument("slug", nargs="?")
    sp.set_defaults(fn=cmd_index)
    sp = sub.add_parser("migrate", help="move a flat (pre-grouping) workspace into the grouped layout")
    sp.add_argument("slug", nargs="?")
    sp.set_defaults(fn=cmd_migrate)
    sub.add_parser("list", help="list feature workspaces").set_defaults(fn=cmd_list)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
