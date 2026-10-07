#!/usr/bin/env python3
"""devkit document format linter.

Every devkit document starts with a marker (`<!-- devkit:doc type=hld v=1 -->`)
that names its template. The linter derives the expected structure from that
template and checks the document still follows it:
  * marker, H1 title prefix and header fields (**Status:**, **Feature:** …)
  * a valid status value for the document type
  * every template H2 section present, in template order, and no extra H2s
    (add detail as H3 inside the right section)
  * every table the template defines in a section is present with the same columns
  * sections whose template carries a mermaid diagram still have one, and it starts
    with a known diagram type
  * no unclosed code fences; no TODO markers once a document is in Review/Approved
A section whose whole body is "None" / "N/A …" is accepted as intentionally empty.

Examples:
  doclint.py                                    # every devkit doc in the repo
  doclint.py --feature payment-retry            # one workspace
  doclint.py services/payments/specs/payment-retry/02-design/hld.md
  doclint.py --strict                           # warnings fail too
"""
from __future__ import annotations

import argparse
import re
import sys
from functools import lru_cache
from pathlib import Path

from devkit_common import DOCS, MANIFEST, TEMPLATES_DIR, all_features, decisions_dir, read_marker, resolve_feature

ADR_STATUSES = {"Proposed", "Accepted", "Rejected", "Deprecated", "Superseded"}
STATUS_VALUES = {"input": {"Captured"}, "adr": ADR_STATUSES}
DEFAULT_STATUSES = {"Draft", "Review", "Approved"}
FINAL_STATUSES = {"Review", "Approved", "Accepted"}
MERMAID_TYPES = ("flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram", "stateDiagram-v2",
                 "erDiagram", "gantt", "journey", "pie", "mindmap", "timeline", "C4Context", "C4Container",
                 "C4Component", "C4Dynamic", "C4Deployment", "quadrantChart", "gitGraph", "requirementDiagram",
                 "block-beta", "architecture-beta", "sankey-beta", "xychart-beta")
EMPTY_OK_RE = re.compile(r"^\s*(none|n/?a)\b", re.I)


def template_path(doc_type: str) -> Path | None:
    if doc_type == "adr":
        return TEMPLATES_DIR / MANIFEST["adr"]["template"]
    doc = DOCS.get(doc_type)
    return TEMPLATES_DIR / doc["template"] if doc and doc.get("template") else None


def strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def split_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    """(preamble, [(h2 title, body)]) ignoring headings inside code fences."""
    pre, sections, cur_title, buf, fence = [], [], None, [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
        if not fence and line.startswith("## "):
            if cur_title is None:
                pre = buf
            else:
                sections.append((cur_title, "\n".join(buf)))
            cur_title, buf = line[3:].strip(), []
        else:
            buf.append(line)
    if cur_title is None:
        pre = buf
    else:
        sections.append((cur_title, "\n".join(buf)))
    return "\n".join(pre), sections


def table_headers(body: str) -> list[tuple[str, ...]]:
    lines = body.splitlines()
    headers = []
    for i, line in enumerate(lines[:-1]):
        if line.strip().startswith("|") and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]) and "-" in lines[i + 1]:
            headers.append(tuple(c.strip() for c in line.strip().strip("|").split("|")))
    return headers


def mermaid_blocks(body: str) -> list[str]:
    return re.findall(r"```mermaid\s*\n(.*?)```", body, flags=re.S)


@lru_cache(maxsize=None)
def spec_for(doc_type: str) -> dict | None:
    tpl = template_path(doc_type)
    if not tpl or not tpl.exists():
        return None
    text = tpl.read_text(encoding="utf-8")
    pre, sections = split_sections(text)
    h1 = next((ln[2:] for ln in pre.splitlines() if ln.startswith("# ")), "")
    return {
        "h1_prefix": h1.split("{{")[0].strip(),
        "fields": re.findall(r"\*\*([\w -]+):\*\*", pre),
        "sections": [t for t, _ in sections],
        "tables": {t: table_headers(b) for t, b in sections},
        "mermaid": {t: bool(mermaid_blocks(b)) for t, b in sections},
    }


def lint_file(path: Path) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    doc_type, generated = read_marker(path)
    if doc_type is None:
        return [f"missing devkit marker on line 1 (e.g. <!-- devkit:doc type=hld v=1 -->)"], []
    if generated:
        return [], []
    spec = spec_for(doc_type)
    if spec is None:
        return [f"unknown document type '{doc_type}' (no template in devkit/templates/manifest.json)"], []
    text = path.read_text(encoding="utf-8")
    if text.count("```") % 2:
        errors.append("unclosed ``` code fence")
    pre, sections = split_sections(text)

    h1 = next((ln[2:].strip() for ln in pre.splitlines() if ln.startswith("# ")), None)
    if h1 is None:
        errors.append("missing H1 title")
    elif spec["h1_prefix"] and not h1.startswith(spec["h1_prefix"]):
        errors.append(f"H1 must start with '{spec['h1_prefix']}' (got '{h1}')")
    elif doc_type == "adr" and not re.match(r"ADR-\d+:", h1):
        errors.append(f"ADR H1 must look like 'ADR-0001: Title' (got '{h1}')")
    for field in spec["fields"]:
        if f"**{field}:**" not in pre:
            errors.append(f"header field **{field}:** missing")
    m = re.search(r"^\*\*Status:\*\*\s*([A-Za-z-]+)", pre, re.M)
    status = m.group(1) if m else None
    allowed = STATUS_VALUES.get(doc_type, DEFAULT_STATUSES)
    if "Status" in spec["fields"] and status not in allowed:
        errors.append(f"**Status:** must be one of {', '.join(sorted(allowed))} (got {status!r})")

    doc_titles = [t for t, _ in sections]
    expected = spec["sections"]
    for t in expected:
        if t not in doc_titles:
            errors.append(f"missing section '## {t}'")
    positions = [doc_titles.index(t) for t in expected if t in doc_titles]
    if positions != sorted(positions):
        errors.append("sections are out of template order: " + " → ".join(expected))
    for t in doc_titles:
        if t not in expected:
            errors.append(f"extra section '## {t}' is not in the template — put it under the right section as ### heading")

    todo_sections = []
    for title, body in sections:
        if title not in expected:
            continue
        visible = strip_comments(body).strip()
        if "<!--" in body and re.search(r"<!--\s*TODO", body, re.I):
            todo_sections.append(title)
        if EMPTY_OK_RE.match(visible):
            continue
        have = {tuple(h) for h in table_headers(body)}
        for header in spec["tables"].get(title, []):
            if header not in have:
                errors.append(f"§ '{title}': table with columns | {' | '.join(header)} | missing or columns changed")
        if spec["mermaid"].get(title) and not mermaid_blocks(body):
            errors.append(f"§ '{title}': mermaid diagram required by the template")
        for block in mermaid_blocks(body):
            first = next((ln.strip() for ln in block.splitlines() if ln.strip() and not ln.strip().startswith("%%")), "")
            if not first.startswith(MERMAID_TYPES):
                errors.append(f"§ '{title}': mermaid block does not start with a diagram type (got '{first[:30]}')")
    if todo_sections:
        msg = "unresolved TODO in: " + "; ".join(todo_sections)
        (errors if status in FINAL_STATUSES else warnings).append(msg + (f" (not allowed in status {status})"
                                                                          if status in FINAL_STATUSES else ""))
    return errors, warnings


def collect(a) -> list[Path]:
    if a.paths:
        return [Path(p) for p in a.paths]
    roots = [resolve_feature(a.feature)] if a.feature else list(all_features().values())
    files = [f for r in roots for f in sorted(r.rglob("*.md"))]
    if not a.feature and decisions_dir().is_dir():
        files += sorted(decisions_dir().rglob("*.md"))
    seen, out = set(), []
    for f in files:
        if f.resolve() not in seen and read_marker(f)[0]:
            seen.add(f.resolve())
            out.append(f)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("paths", nargs="*", help="documents to lint (default: all devkit docs)")
    p.add_argument("--feature", "-f", help="lint one feature workspace")
    p.add_argument("--strict", action="store_true", help="treat warnings as errors")
    p.add_argument("--quiet", "-q", action="store_true", help="only print problems")
    a = p.parse_args(argv)
    files = collect(a)
    total_e = total_w = 0
    for f in files:
        errors, warnings = lint_file(f)
        total_e += len(errors)
        total_w += len(warnings)
        if errors or warnings or not a.quiet:
            print(f"{'✗' if errors else ('!' if warnings else '✓')} {f}")
        for e in errors:
            print(f"    ERROR {e}")
        for w in warnings:
            print(f"    WARN  {w}")
    print(f"doclint: {len(files)} file(s), {total_e} error(s), {total_w} warning(s)")
    return 1 if total_e or (a.strict and total_w) else 0


if __name__ == "__main__":
    sys.exit(main())
