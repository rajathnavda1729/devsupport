"""`devkit` command line.

Built-in commands manage the installation; every other command is forwarded to
the devkit tools (the project's vendored copy when present, else the bundled one).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from devkit_cli import __version__, installer

PASSTHROUGH = {
    # devkit <cmd> ...           -> tool, leading args
    "new": ("scaffold.py", ["new"]), "status": ("scaffold.py", ["status"]), "list": ("scaffold.py", ["list"]),
    "where": ("scaffold.py", ["where"]), "doc": ("scaffold.py", ["doc"]), "types": ("scaffold.py", ["types"]),
    "index": ("scaffold.py", ["index"]), "migrate": ("scaffold.py", ["migrate"]), "init": ("scaffold.py", ["init"]),
    "task": ("tracker.py", []), "adr": ("adr.py", []), "lint": ("doclint.py", []), "bench": ("bench.py", []),
    "logs": ("logwatch.py", []), "review": ("review.py", []),
}
REVIEW_SUBCOMMANDS = {"matrix", "decision", "readiness", "-h", "--help"}

HELP = f"""devkit {__version__} — requirement-to-delivery kit for Claude Code

Install & maintain (always shows a reviewable plan first):
  devkit install [--target DIR] [--user] [--only skills,agents,rules,tools] [--specs-dir D]
                 [--dry-run] [--yes] [--force] [-v]
  devkit update  ...same options...      re-sync with this devkit version
  devkit diff    [--target DIR] [--user] [PATH-FILTER]   what would change, as unified diff
  devkit doctor  [--target DIR]          check installation, versions, hooks, pending changes
  devkit uninstall [--target DIR] [--user] [--yes] [--force]   (never touches specs or ADRs)
  devkit version

Pipeline (run inside the target repo):
  devkit new <slug> [--at <module>] --text "..."   create a grouped feature workspace
  devkit status|where|index|migrate [slug] · devkit list · devkit types · devkit doc <slug> <type>
  devkit adr scan|list|search|show|new|set-status|supersede|check ...
  devkit review <slug>                    implementation-readiness gate (review before implementing)
  devkit review matrix <slug>             weighted comparison + sensitivity of the options
  devkit review decision <ADR>            is a decision thoroughly evaluated?
  devkit task -f <slug> next|start|done|block|add|import|validate|trace|waves ...
  devkit lint [--feature <slug>]          documents vs their templates
  devkit bench cmd|http|compare|report ...   ·   devkit logs <files>|--cmd "..." ...

In Claude Code: /devkit <slug> <requirement>   (skills: devkit, adr-discovery, solutioning, hld, lld, ...)
"""


def project_root(start: Path | None = None) -> Path:
    cwd = (start or Path.cwd()).resolve()
    for marker in (".devkit.json", ".git"):
        for d in (cwd, *cwd.parents):
            if (d / marker).exists():
                return d
    return cwd


def tool_path(tool: str) -> Path:
    vendored = project_root() / "devkit" / "tools" / tool
    return vendored if vendored.exists() else installer.kit_root() / "devkit" / "tools" / tool


def run_tool(cmd: str, args: list[str]) -> int:
    tool, lead = PASSTHROUGH[cmd]
    if cmd == "review" and (not args or args[0] not in REVIEW_SUBCOMMANDS):
        lead = ["readiness"]
    return subprocess.call([sys.executable, str(tool_path(tool)), *lead, *args])


def confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print("not a terminal — review the plan above and re-run with --yes to apply", file=sys.stderr)
        return False
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")


def resolve_target(a) -> tuple[Path, str]:
    if a.user:
        return Path.home() / ".claude", "user"
    root = Path(a.target).resolve() if a.target else project_root()
    if not root.is_dir():
        raise SystemExit(f"error: not a directory: {root}")
    if root.resolve() == installer.kit_root().resolve():
        raise SystemExit("error: the target is the devkit source itself — run inside the repo where requirements "
                         "are realised, or pass --target <repo>")
    return root, "project"


def components_for(a, scope: str) -> list[str]:
    allowed = installer.USER_COMPONENTS if scope == "user" else tuple(installer.COMPONENTS)
    if not getattr(a, "only", None):
        return list(allowed)
    wanted = [c.strip() for c in a.only.split(",") if c.strip()]
    bad = [c for c in wanted if c not in allowed]
    if bad:
        raise SystemExit(f"error: unknown component(s) for {scope} scope: {', '.join(bad)} (choose from {', '.join(allowed)})")
    return wanted


def cmd_install(a) -> int:
    root, scope = resolve_target(a)
    plan = installer.make_plan(root, scope, components_for(a, scope), a.force, a.specs_dir)
    print(installer.render_plan(plan, a.verbose))
    if not plan.has_changes():
        print("\nnothing to change — already up to date")
        return 0
    if a.dry_run:
        print("\ndry run — nothing written. `devkit diff` shows the content changes.")
        return 0
    if not confirm("\nApply these changes?", a.yes):
        print("aborted — nothing written")
        return 1
    installer.apply_plan(plan)
    print(f"\n✅ devkit {__version__} installed ({scope}) at {root}")
    if scope == "project" and "tools" in plan.components:
        subprocess.call([sys.executable, str(root / "devkit/tools/adr.py"), "scan"], cwd=root,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("   decision log refreshed (devkit adr list). Next: open Claude Code here and run /devkit <slug> <requirement>")
    elif scope == "user":
        print("   skills + agents are now available in every project. In each repo you work on, run "
              "`devkit install --only tools,rules` for the tools, hooks and rules they use.")
    return 0


def cmd_diff(a) -> int:
    root, scope = resolve_target(a)
    plan = installer.make_plan(root, scope, components_for(a, scope), False, None)
    print(installer.diff(plan, a.filter))
    return 0


def cmd_doctor(a) -> int:
    root, _ = resolve_target(argparse.Namespace(user=False, target=a.target))
    problems = 0

    def line(ok: bool, msg: str) -> None:
        nonlocal problems
        problems += 0 if ok else 1
        print(f"{'✅' if ok else '❌'} {msg}")

    line(sys.version_info >= (3, 10), f"python {sys.version.split()[0]} (needs ≥ 3.10)")
    print(f"ℹ️  devkit CLI {__version__} · assets: {installer.kit_root()}")
    print(f"ℹ️  claude CLI: {shutil.which('claude') or 'not on PATH (fine if you use the desktop/IDE app)'}")
    for label, base in (("project", root), ("user", Path.home() / ".claude")):
        m = installer.load_manifest(base)
        if not m.get("version"):
            print(f"·  {label}: not installed ({base})")
            continue
        current = m["version"] == __version__
        line(current, f"{label}: devkit {m['version']} ({', '.join(m.get('components', []))})"
             + ("" if current else f" — outdated, run `devkit update{' --user' if label == 'user' else ''}`"))
        scope = "user" if label == "user" else "project"
        plan = installer.make_plan(base, scope, m.get("components", []), False, None)
        missing = [i.rel for i in plan.items if i.action == "new"]
        conflicts = [i.rel for i in plan.items if i.action == "conflict"]
        line(not missing, f"{label}: all files present" if not missing else f"{label}: {len(missing)} file(s) missing")
        if conflicts:
            print(f"⚠️  {label}: {len(conflicts)} locally edited file(s) (kept on update): {', '.join(conflicts[:4])}")
        if scope == "project" and "tools" in m.get("components", []):
            line(plan.settings is None, "settings.json has devkit hooks and permissions" if plan.settings is None
                 else "settings.json is missing devkit hooks/permissions — run `devkit update`")
            line((root / ".devkit.json").exists(), ".devkit.json present")
    return 1 if problems else 0


def cmd_uninstall(a) -> int:
    root, scope = resolve_target(a)
    items, settings, cm = installer.uninstall_plan(root, a.force)
    if not items and settings is None and cm is None:
        print(f"nothing installed at {root}")
        return 0
    print(f"devkit uninstall ({scope}) at {root}")
    for i in items:
        print(f"  {'-' if i.action == 'remove' else '='} {i.action:<7} {i.rel}" + (f"   ({i.note})" if i.note else ""))
    if settings is not None:
        print("  ~ settings.json: remove devkit hooks and permissions (your entries are kept)")
    if cm is not None:
        print("  ~ CLAUDE.md: remove the devkit section")
    print("  feature workspaces, ADRs and .devkit.json are left untouched")
    if a.dry_run or not confirm("\nUninstall?", a.yes):
        print("nothing removed")
        return 0 if a.dry_run else 1
    installer.apply_uninstall(root, items, settings, cm)
    print("✅ devkit removed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="devkit", add_help=False)
    sub = p.add_subparsers(dest="cmd")

    def target_opts(sp):
        sp.add_argument("--target", help="target repo (default: repo containing the current directory)")
        sp.add_argument("--user", action="store_true", help="install skills + agents into ~/.claude for all projects")

    for name in ("install", "update"):
        sp = sub.add_parser(name)
        target_opts(sp)
        sp.add_argument("--only", help="comma list of components: skills,agents,rules,tools")
        sp.add_argument("--specs-dir", help="default workspace folder for this repo (written to .devkit.json)")
        sp.add_argument("--dry-run", action="store_true", help="show the plan only")
        sp.add_argument("--yes", "-y", action="store_true", help="apply without asking")
        sp.add_argument("--force", action="store_true", help="overwrite locally edited files")
        sp.add_argument("--verbose", "-v", action="store_true")
        sp.set_defaults(fn=cmd_install)
    sp = sub.add_parser("diff")
    target_opts(sp)
    sp.add_argument("filter", nargs="?")
    sp.add_argument("--only")
    sp.set_defaults(fn=cmd_diff)
    sp = sub.add_parser("doctor")
    sp.add_argument("--target")
    sp.set_defaults(fn=cmd_doctor)
    sp = sub.add_parser("uninstall")
    target_opts(sp)
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--yes", "-y", action="store_true")
    sp.add_argument("--force", action="store_true", help="also remove locally edited files")
    sp.set_defaults(fn=cmd_uninstall)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(HELP)
        return 0
    if argv[0] in ("version", "--version", "-V"):
        print(f"devkit {__version__}")
        return 0
    if argv[0] in PASSTHROUGH:
        return run_tool(argv[0], argv[1:])
    if argv[0] not in ("install", "update", "diff", "doctor", "uninstall"):
        print(f"devkit: unknown command '{argv[0]}'\n\n{HELP}", file=sys.stderr)
        return 2
    a = build_parser().parse_args(argv)
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
