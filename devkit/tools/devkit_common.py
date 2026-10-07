"""Shared helpers for devkit tools (stdlib only)."""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path

KIT_DIR = Path(__file__).resolve().parent.parent          # .../devkit
TEMPLATES_DIR = KIT_DIR / "templates"
CONFIG_DIR = KIT_DIR / "config"

# The manifest is the single source of truth for document types, templates and
# the grouped layout of a feature workspace.
MANIFEST = json.loads((TEMPLATES_DIR / "manifest.json").read_text(encoding="utf-8"))
DOCS: dict[str, dict] = {d["type"]: d for d in MANIFEST["documents"]}
ADR_CONF: dict = MANIFEST["adr"]

# Ordered pipeline of (relative path, label) inside a workspace.
ARTIFACTS = [(d["path"], d["title"]) for d in MANIFEST["documents"] if d.get("pipeline")]
REQUIREMENTS_FILE = DOCS["requirements"]["path"]
TEST_PLAN_FILE = DOCS["test-plan"]["path"]
TASKS_FILE = DOCS["tasks"]["path"]
BOARD_FILE = DOCS["board"]["path"]
TRACE_FILE = DOCS["traceability"]["path"]
INDEX_FILE = "README.md"

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
TODO_RE = re.compile(r"<!--\s*TODO", re.I)
STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*([A-Za-z-]+)", re.M)
# First line of every devkit document: <!-- devkit:doc type=hld v=1 [generated] -->
MARKER_RE = re.compile(r"<!--\s*devkit:doc\s+type=([\w-]+)(?:\s+v=(\d+))?(\s+generated)?\s*-->")


def doc_marker(doc_type: str, generated: bool = False) -> str:
    return f"<!-- devkit:doc type={doc_type} v=1{' generated' if generated else ''} -->"


def read_marker(path: Path) -> tuple[str | None, bool]:
    """(doc type, is_generated) from a file's devkit marker, or (None, False)."""
    try:
        with open(path, encoding="utf-8") as fh:
            head = fh.read(300)
    except (OSError, UnicodeDecodeError):
        return None, False
    m = MARKER_RE.search(head)
    return (m.group(1), bool(m.group(3))) if m else (None, False)

# A requirement is *defined* by a markdown table row whose first cell is its ID.
REQ_ROW_RE = re.compile(r"^\|\s*((?:FR|NFR)-\d+)\s*\|(.*)$", re.M)
TC_ROW_RE = re.compile(r"^\|\s*(TC-\d+)\s*\|(.*)$", re.M)
REQ_ID_RE = re.compile(r"\b(?:FR|NFR)-\d+\b")


def die(msg: str, code: int = 2) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def today() -> str:
    return _dt.date.today().isoformat()


CONFIG_NAME = ".devkit.json"


def project_root() -> Path:
    """Nearest ancestor of cwd holding .devkit.json (else .git), else cwd.

    Anchoring here means artifacts land in the target repo's configured location
    no matter which sub-directory Claude happens to run a tool from.
    """
    cwd = Path.cwd().resolve()
    for marker in (CONFIG_NAME, ".git"):
        for d in (cwd, *cwd.parents):
            if (d / marker).exists():
                return d
    return cwd


def load_project_config() -> dict:
    path = project_root() / CONFIG_NAME
    cfg = load_json(path, {})
    cfg.setdefault("specs_dir", "specs")
    cfg.setdefault("features", {})
    return cfg


def save_project_config(cfg: dict) -> Path:
    path = project_root() / CONFIG_NAME
    write_atomic(path, json.dumps(cfg, indent=2) + "\n")
    return path


def specs_root(explicit: str | None = None) -> Path:
    """Default workspace parent: --specs-dir / DEVKIT_SPECS_DIR (cwd-relative) or config specs_dir (root-relative)."""
    override = explicit or os.environ.get("DEVKIT_SPECS_DIR")
    if override:
        return Path(override)
    return project_root() / load_project_config()["specs_dir"]


def all_features(specs_dir: str | None = None) -> dict[str, Path]:
    """slug -> workspace dir: everything under the default specs root plus registered workspaces."""
    root = specs_root(specs_dir)
    found = {p.name: p for p in sorted(root.iterdir()) if is_workspace(p)} if root.is_dir() else {}
    for slug, rel in load_project_config()["features"].items():
        found[slug] = project_root() / rel
    return found


LEGACY_LAYOUT = {  # flat layout used before grouping -> grouped path
    "00-input.md": DOCS["input"]["path"], "01-requirements.md": DOCS["requirements"]["path"],
    "02-solutioning.md": DOCS["solutioning"]["path"], "03-hld.md": DOCS["hld"]["path"],
    "04-lld.md": DOCS["lld"]["path"], "tasks.json": TASKS_FILE, "TASKS.md": BOARD_FILE,
    "06-execution-plan.md": DOCS["execution-plan"]["path"], "07-testing-guide.md": DOCS["testing-guide"]["path"],
    "08-test-plan.md": TEST_PLAN_FILE, "09-benchmark-plan.md": DOCS["benchmark-plan"]["path"],
    "traceability.md": TRACE_FILE, "adr": ADR_CONF["feature_dir"], "benchmarks": "04-quality/benchmarks",
}


def is_workspace(p: Path) -> bool:
    if not p.is_dir():
        return False
    first_group = MANIFEST["groups"][0]["id"]
    return (p / first_group).is_dir() or any((p / legacy).exists() for legacy in ("00-input.md", "01-requirements.md"))


def is_legacy_workspace(p: Path) -> bool:
    return (p / "00-input.md").exists() or (p / "01-requirements.md").exists()


def decisions_dir() -> Path:
    """Repo-wide ADR directory (config decisions_dir, else manifest default)."""
    return project_root() / load_project_config().get("decisions_dir", ADR_CONF["default_repo_dir"])


def register_feature(slug: str, workspace: Path) -> None:
    cfg = load_project_config()
    cfg["features"][slug] = workspace.resolve().relative_to(project_root()).as_posix()
    save_project_config(cfg)


def resolve_feature(feature: str | None, specs_dir: str | None = None) -> Path:
    """Return the workspace for <feature>; infer it when exactly one workspace exists."""
    features = all_features(specs_dir)
    feature = feature or os.environ.get("DEVKIT_FEATURE")
    if feature:
        d = features.get(feature, specs_root(specs_dir) / feature)
        if not d.is_dir():
            die(f"feature workspace not found: {d} (create it: python3 devkit/tools/scaffold.py new {feature})")
        return d
    if len(features) == 1:
        return next(iter(features.values()))
    names = ", ".join(features) or "none"
    die(f"specify --feature <slug> or set DEVKIT_FEATURE (workspaces found: {names})")
    raise AssertionError  # unreachable


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{path} is not valid JSON: {e}")


def parse_requirements(feature_dir: Path) -> dict[str, dict]:
    """Parse requirement rows from 01-requirements.md.

    Returns {id: {"critical": bool, "row": str}}. A row is critical when any
    cell contains the word CRITICAL (case-insensitive).
    """
    path = feature_dir / REQUIREMENTS_FILE
    if not path.exists():
        return {}
    reqs: dict[str, dict] = {}
    for m in REQ_ROW_RE.finditer(path.read_text(encoding="utf-8")):
        rid, rest = m.group(1), m.group(2)
        reqs[rid] = {"critical": bool(re.search(r"\bcritical\b", rest, re.I)), "row": rest.strip()}
    return reqs


def parse_test_cases(feature_dir: Path) -> dict[str, list[str]]:
    """Parse TC rows from 08-test-plan.md -> {TC-id: [requirement ids]}."""
    path = feature_dir / TEST_PLAN_FILE
    if not path.exists():
        return {}
    cases: dict[str, list[str]] = {}
    for m in TC_ROW_RE.finditer(path.read_text(encoding="utf-8")):
        cases[m.group(1)] = sorted(set(REQ_ID_RE.findall(m.group(2))))
    return cases


def artifact_state(path: Path) -> tuple[str, str]:
    """(state, doc status) where state is missing | draft | filled."""
    if not path.exists():
        return "missing", "-"
    if path.suffix == ".json":
        data = load_json(path, {})
        return ("filled" if data.get("tasks") else "draft"), "-"
    text = path.read_text(encoding="utf-8")
    m = STATUS_RE.search(text)
    return ("draft" if TODO_RE.search(text) else "filled"), (m.group(1) if m else "-")
