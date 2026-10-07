#!/usr/bin/env python3
"""PostToolUse hook: after Claude writes a devkit document, lint it against its
template and refresh the workspace index. Lint errors are fed back to Claude
(exit 2) so the format is fixed immediately instead of drifting."""
import contextlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from devkit_common import all_features, read_marker  # noqa: E402

try:
    payload = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)
path = Path(str(payload.get("tool_input", {}).get("file_path", "")))
if path.suffix != ".md" or not path.exists():
    sys.exit(0)
doc_type, generated = read_marker(path)
if doc_type is None or generated:
    sys.exit(0)

import doclint  # noqa: E402

errors, _ = doclint.lint_file(path)

with contextlib.suppress(Exception), contextlib.redirect_stdout(io.StringIO()):
    from scaffold import write_index
    for ws in all_features().values():
        try:
            path.resolve().relative_to(ws.resolve())
        except ValueError:
            continue
        write_index(ws)
        break

if errors:
    print(f"{path.name} no longer matches its template ({doc_type}). Fix before continuing:\n"
          + "\n".join(f"- {e}" for e in errors)
          + "\nThe template is the contract: keep its H2 sections, order, tables and diagrams; add detail as ### "
            "subsections. Template: devkit/templates/ (see manifest.json).", file=sys.stderr)
    sys.exit(2)
