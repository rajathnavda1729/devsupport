---
paths:
  - "**/specs/**/*.md"
  - "**/adr/**/*.md"
  - "**/decisions/**/*.md"
---

# Document format

Every devkit document is an instance of a template. Its type is declared on line 1 (`<!-- devkit:doc type=<type> v=1 -->`), and the templates and locations are registered in `devkit/templates/manifest.json`. The format is checked by `devkit/tools/doclint.py`, and automatically after every write by the lint hook.

- **Create** documents only with tools: `scaffold.py new`, `scaffold.py doc <slug> <type>`, `adr.py new`. Never create a pipeline document from scratch or copy it from another feature.
- **Keep** the marker line, the H1 prefix, the header fields, every H2 section with its exact name and order, the table column headers, and the mermaid blocks the template requires.
- **Add**:
  - detail under `###` sub-headings inside the right section;
  - extra tables below the template's table;
  - extra diagrams anywhere.
  Never add new H2 sections.
- **Empty sections** say `None` or `N/A — <reason>`. Never delete them.
- **Status lifecycle** is Draft → Review → Approved (ADRs: Proposed → Accepted / Rejected / Deprecated / Superseded). A document in Review or Approved has no TODO markers.
- **Generated documents** (`TASKS.md`, `traceability.md`, the workspace `README.md`, `decision-log.md`) are never edited by hand.
- **New kinds of documents** need a template and a manifest entry first (`kit-forge` skill).

**Why:** consistent structure makes every feature's documents comparable, reviewable and machine-checkable. Tools parse the IDs, tables and sections.

**Bad:** inventing `## Appendix: random thoughts` in the HLD, or renaming the FR table's `Acceptance criteria (Given/When/Then)` column.
**Good:** `### Appendix — capacity maths` under `## 9. NFR realisation`.
