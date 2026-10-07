"""Plan / apply / diff / uninstall the devkit into a project or the user's ~/.claude.

Every install is reviewable before it happens: a plan lists each file as
new / update / unchanged / conflict / remove, plus the settings and CLAUDE.md
merges. Installed files are recorded with their hashes, so files edited locally
are detected and never overwritten without --force.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from devkit_cli import __version__

COMPONENTS = {
    "skills": ".claude/skills",
    "agents": ".claude/agents",
    "rules": ".claude/rules",
    "tools": "devkit",
}
USER_COMPONENTS = ("skills", "agents")      # tools/hooks/rules are per project
EXCLUDE_NAMES = {"__pycache__", ".DS_Store", "logwatch.local.json"}
EXCLUDE_SUFFIXES = {".pyc", ".tmp"}
MANIFEST_NAME = "devkit-install.json"
HOOK_MARK = "devkit/hooks/"
BLOCK_BEGIN, BLOCK_END = "<!-- devkit:begin -->", "<!-- devkit:end -->"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def kit_root() -> Path:
    pkg = Path(__file__).resolve().parent
    if (pkg / "kit" / "devkit" / "tools").is_dir():          # installed wheel
        return pkg / "kit"
    repo = pkg.parents[1]                                      # running from a clone / editable install
    if (repo / "devkit" / "tools").is_dir():
        return repo
    raise SystemExit("error: devkit assets not found (broken installation?)")


@dataclass
class Item:
    rel: str            # destination path, relative to the install root
    action: str         # new | update | unchanged | conflict | overwrite | remove | keep
    src: Path | None = None
    note: str = ""


@dataclass
class Plan:
    root: Path
    scope: str
    components: list[str]
    items: list[Item] = field(default_factory=list)
    settings: tuple[dict, dict] | None = None      # (current, merged)
    claude_md: tuple[str, str] | None = None       # (current, new)
    config: tuple[dict | None, dict] | None = None  # (.devkit.json current, new)

    @property
    def changes(self) -> list[Item]:
        return [i for i in self.items if i.action in ("new", "update", "overwrite", "remove")]

    def has_changes(self) -> bool:
        return bool(self.changes or self.settings or self.claude_md or self.config)


def manifest_path(root: Path) -> Path:
    return root / (MANIFEST_NAME if root.name == ".claude" else f".claude/{MANIFEST_NAME}")


def load_manifest(root: Path) -> dict:
    p = manifest_path(root)
    return json.loads(p.read_text()) if p.exists() else {"files": {}}


def kit_files(components: list[str], scope: str) -> dict[str, Path]:
    """destination rel path -> source file in the kit."""
    kit = kit_root()
    out: dict[str, Path] = {}
    for comp in components:
        base = kit / COMPONENTS[comp]
        for f in sorted(base.rglob("*")):
            if f.is_dir() or f.suffix in EXCLUDE_SUFFIXES or any(p in EXCLUDE_NAMES for p in f.parts):
                continue
            rel = f.relative_to(kit).as_posix()
            if scope == "user":
                rel = rel.removeprefix(".claude/")
            out[rel] = f
    if scope == "project" and "tools" in components:
        out["devkit/README-DEVKIT.md"] = kit / "README.md"
    return out


def merged_settings(current: dict) -> dict:
    kit = json.loads((kit_root() / ".claude" / "settings.json").read_text())
    merged = json.loads(json.dumps(current))
    allow = merged.setdefault("permissions", {}).setdefault("allow", [])
    for rule in kit["permissions"]["allow"]:
        if rule not in allow:
            allow.append(rule)
    hooks = merged.setdefault("hooks", {})
    for event, groups in kit.get("hooks", {}).items():
        existing = hooks.setdefault(event, [])
        have = {h.get("command") for g in existing for h in g.get("hooks", [])}
        for g in groups:
            if not any(h["command"] in have for h in g["hooks"]):
                existing.append(g)
    return merged


def unmerged_settings(current: dict) -> dict:
    kit = json.loads((kit_root() / ".claude" / "settings.json").read_text())
    out = json.loads(json.dumps(current))
    allow = out.get("permissions", {}).get("allow", [])
    out.setdefault("permissions", {})["allow"] = [r for r in allow if r not in kit["permissions"]["allow"]]
    for event, groups in list(out.get("hooks", {}).items()):
        kept = [g for g in groups if not any(HOOK_MARK in h.get("command", "") for h in g.get("hooks", []))]
        if kept:
            out["hooks"][event] = kept
        else:
            del out["hooks"][event]
    if not out.get("hooks"):
        out.pop("hooks", None)
    if not out["permissions"]["allow"]:
        out["permissions"].pop("allow")
    if not out["permissions"]:
        out.pop("permissions")
    return out


def claude_md_block() -> str:
    body = (kit_root() / "devkit" / "templates" / "meta" / "claude-md-section.md").read_text().strip()
    return f"{BLOCK_BEGIN}\n{body}\n{BLOCK_END}"


def with_block(text: str, block: str | None) -> str:
    if BLOCK_BEGIN in text and BLOCK_END in text:
        head, _, rest = text.partition(BLOCK_BEGIN)
        _, _, tail = rest.partition(BLOCK_END)
        if block is None:
            remaining = (head.rstrip() + "\n\n" + tail.lstrip()).strip()
            return remaining + "\n" if remaining else ""
        return head + block + tail
    if block is None:
        return text
    return (text.rstrip() + "\n\n" if text.strip() else "") + block + "\n"


def make_plan(root: Path, scope: str, components: list[str], force: bool, specs_dir: str | None) -> Plan:
    plan = Plan(root=root, scope=scope, components=components)
    recorded = load_manifest(root).get("files", {})
    files = kit_files(components, scope)
    for rel, src in files.items():
        dest = root / rel
        kit_hash = sha(src.read_bytes())
        if not dest.exists():
            plan.items.append(Item(rel, "new", src))
            continue
        cur = sha(dest.read_bytes())
        if cur == kit_hash:
            plan.items.append(Item(rel, "unchanged", src))
        elif recorded.get(rel) == cur:
            plan.items.append(Item(rel, "update", src, "newer devkit version"))
        elif force:
            plan.items.append(Item(rel, "overwrite", src, "local changes will be lost (--force)"))
        else:
            why = "edited locally" if rel in recorded else "file not installed by devkit"
            plan.items.append(Item(rel, "conflict", src, f"{why} — kept; see `devkit diff`, or --force"))
    for rel, h in recorded.items():
        if rel not in files and any(rel.startswith(COMPONENTS[c].removeprefix(".claude/") if scope == "user"
                                                   else COMPONENTS[c]) for c in components):
            dest = root / rel
            if dest.exists():
                same = sha(dest.read_bytes()) == h
                plan.items.append(Item(rel, "remove" if same or force else "keep", None,
                                       "no longer part of devkit" + ("" if same else " (edited locally — kept)")))
    if scope == "project" and "tools" in components:
        sp = root / ".claude" / "settings.json"
        current = json.loads(sp.read_text()) if sp.exists() else {}
        merged = merged_settings(current)
        if merged != current:
            plan.settings = (current, merged)
        cm = root / "CLAUDE.md"
        cur_md = cm.read_text() if cm.exists() else ""
        new_md = with_block(cur_md, claude_md_block())
        if new_md != cur_md:
            plan.claude_md = (cur_md, new_md)
        cfg_path = root / ".devkit.json"
        cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else None
        new_cfg = dict(cfg or {"specs_dir": "specs", "features": {}})
        if specs_dir:
            new_cfg["specs_dir"] = specs_dir
        if new_cfg != cfg:
            plan.config = (cfg, new_cfg)
    return plan


SYMBOL = {"new": "+", "update": "~", "overwrite": "!", "conflict": "!", "remove": "-", "keep": "=", "unchanged": "="}


def render_plan(plan: Plan, verbose: bool = False) -> str:
    out = [f"devkit {__version__} → {plan.scope} install at {plan.root}",
           f"components: {', '.join(plan.components)}", ""]
    groups: dict[str, list[Item]] = {}
    for i in plan.items:
        groups.setdefault(i.action, []).append(i)
    for action in ("new", "update", "overwrite", "remove", "conflict", "keep"):
        for i in groups.get(action, []):
            out.append(f"  {SYMBOL[action]} {action:<9} {i.rel}" + (f"   ({i.note})" if i.note else ""))
    unchanged = groups.get("unchanged", [])
    if unchanged:
        out += [f"  = unchanged {i.rel}" for i in unchanged] if verbose else [f"  = {len(unchanged)} file(s) unchanged"]
    if plan.settings:
        cur, new = plan.settings
        added_perms = len(new.get("permissions", {}).get("allow", [])) - len(cur.get("permissions", {}).get("allow", []))
        added_hooks = sum(len(v) for v in new.get("hooks", {}).values()) - sum(len(v) for v in cur.get("hooks", {}).values())
        out.append(f"  ~ merge     .claude/settings.json   (+{added_perms} permission(s), +{added_hooks} hook group(s); "
                   "your entries are kept)")
    if plan.claude_md:
        out.append("  ~ " + ("update    " if BLOCK_BEGIN in plan.claude_md[0] else "append    ")
                   + "CLAUDE.md               (devkit section between devkit:begin/end markers)")
    if plan.config:
        out.append(f"  {'+' if plan.config[0] is None else '~'} config    .devkit.json            (specs_dir = {plan.config[1]['specs_dir']})")
    n = len(plan.changes) + bool(plan.settings) + bool(plan.claude_md) + bool(plan.config)
    conflicts = len(groups.get("conflict", []))
    out += ["", f"{n} change(s)" + (f", {conflicts} conflict(s) kept as-is" if conflicts else "")]
    return "\n".join(out)


def apply_plan(plan: Plan) -> None:
    root = plan.root
    manifest = load_manifest(root)
    files = manifest.get("files", {})
    for i in plan.items:
        dest = root / i.rel
        if i.action in ("new", "update", "overwrite"):
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(i.src, dest)
            if dest.suffix == ".py" or dest.parent.name == "bin":
                dest.chmod(dest.stat().st_mode | 0o111)
            files[i.rel] = sha(i.src.read_bytes())
        elif i.action == "unchanged":
            files[i.rel] = sha(i.src.read_bytes())
        elif i.action == "remove":
            dest.unlink(missing_ok=True)
            files.pop(i.rel, None)
            prune_empty(dest.parent, root)
    if plan.settings:
        sp = root / ".claude" / "settings.json"
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(plan.settings[1], indent=2) + "\n")
    if plan.claude_md:
        (root / "CLAUDE.md").write_text(plan.claude_md[1])
    if plan.config:
        (root / ".devkit.json").write_text(json.dumps(plan.config[1], indent=2) + "\n")
    manifest.update({"version": __version__, "scope": plan.scope, "installed_at": datetime.now().isoformat(timespec="seconds"),
                     "components": sorted(set(manifest.get("components", [])) | set(plan.components)), "files": files})
    mp = manifest_path(root)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(manifest, indent=2) + "\n")


def prune_empty(d: Path, stop: Path) -> None:
    while d != stop and d.is_dir() and not any(d.iterdir()):
        d.rmdir()
        d = d.parent


def diff(plan: Plan, only: str | None = None) -> str:
    chunks = []
    for i in plan.items:
        if i.action not in ("update", "conflict", "overwrite") or (only and only not in i.rel):
            continue
        cur = (plan.root / i.rel).read_text(errors="replace").splitlines(keepends=True)
        new = i.src.read_text(errors="replace").splitlines(keepends=True)
        chunks.append("".join(difflib.unified_diff(cur, new, f"installed/{i.rel}", f"devkit-{__version__}/{i.rel}")))
    if plan.settings and (not only or "settings" in only):
        a = json.dumps(plan.settings[0], indent=2).splitlines(keepends=True)
        b = json.dumps(plan.settings[1], indent=2).splitlines(keepends=True)
        chunks.append("".join(difflib.unified_diff(a, b, "installed/.claude/settings.json", "merged/.claude/settings.json")))
    return "\n".join(c for c in chunks if c) or "no differences"


def uninstall_plan(root: Path, force: bool) -> tuple[list[Item], dict | None, str | None]:
    manifest = load_manifest(root)
    items = []
    for rel, h in manifest.get("files", {}).items():
        dest = root / rel
        if not dest.exists():
            continue
        same = sha(dest.read_bytes()) == h
        items.append(Item(rel, "remove" if same or force else "keep", None, "" if same else "edited locally — kept"))
    settings = cm = None
    sp = root / ".claude" / "settings.json"
    if sp.exists() and manifest.get("scope") == "project":
        cur = json.loads(sp.read_text())
        new = unmerged_settings(cur)
        settings = new if new != cur else None
    cmp = root / "CLAUDE.md"
    if cmp.exists() and BLOCK_BEGIN in cmp.read_text():
        cm = with_block(cmp.read_text(), None)
    return items, settings, cm


def apply_uninstall(root: Path, items: list[Item], settings: dict | None, cm: str | None) -> None:
    for i in items:
        if i.action == "remove":
            (root / i.rel).unlink(missing_ok=True)
            prune_empty((root / i.rel).parent, root)
    if settings is not None:
        sp = root / ".claude" / "settings.json"
        if settings:
            sp.write_text(json.dumps(settings, indent=2) + "\n")
        else:
            sp.unlink()
    if cm is not None:
        cmp = root / "CLAUDE.md"
        if cm.strip():
            cmp.write_text(cm)
        else:
            cmp.unlink()
    manifest_path(root).unlink(missing_ok=True)
