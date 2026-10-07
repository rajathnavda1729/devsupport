---
paths:
  - "specs/**"
  - "**/specs/**"
---

# Devkit artifacts

- Each feature lives in one workspace in the **target repo**, created by `devkit/tools/scaffold.py`. That is `specs/<slug>/` by default (`.devkit.json` → `specs_dir`), or `<module>/specs/<slug>/` next to the code that realises it (`--at`). Find it with `scaffold.py where <slug>`. Never create a second copy elsewhere.
- Documents are **grouped** as defined in `devkit/templates/manifest.json`:
  - `01-requirements/`: input, requirements
  - `02-design/`: solutioning, hld, lld, `decisions/` (feature ADRs), `reviews/`
  - `03-delivery/`: tasks.json, TASKS.md, execution-plan
  - `04-quality/`: testing-guide, test-plan, traceability, benchmark-plan, test-report, `benchmarks/`

  `<ws>/README.md` is the generated index. Do not invent other file names or folders for the pipeline documents.
- Follow the document-format rule: the template is the contract. Remove the `<!-- TODO` markers you have resolved; tools use them to detect unfinished drafts.
- Keep the `**Status:**` line accurate. The values are Draft → Review → Approved. Only the user approves.
- `01-requirements/input.md` is the verbatim requirement. Never rewrite it.
- **IDs are permanent:** FR-###, NFR-###, T-###, TC-###, ADR-####. Never renumber or reuse an ID. Mark a removed item `Won't` or `cancelled` instead of deleting it.
- A requirement or test case is *defined* by a table row whose **first cell is its ID**. The tooling parses this, so keep it.

**Why:** traceability tooling (`tracker.py validate/trace`) and pipeline status (`scaffold.py status`) depend on these conventions.
