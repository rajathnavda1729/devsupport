> **Example snapshot:** the vendored `devkit/` and `.claude/` folders that `devkit install` adds are omitted here. Run the tools with `../../bin/devkit …`, and see `WALKTHROUGH.md`.

<!-- devkit:begin -->
## devkit
This repo uses the devkit delivery pipeline (guide: `devkit/README-DEVKIT.md`, CLI: `devkit --help`).
- Start a feature with `/devkit <slug> <requirement>`. Documents are written **in this repo**, grouped under the feature workspace (`devkit where <slug>`): `01-requirements/`, `02-design/`, `03-delivery/`, `04-quality/`.
- Before designing, run `devkit adr scan` and `devkit adr search <keywords>`. Accepted ADRs are binding; change one only through a superseding ADR (`adr-author` skill).
- Decisions must be thoroughly evaluated (`devkit review matrix <slug>`, `devkit review decision <ADR>`, `decision-challenger` agent) and accepted by a human.
- **Review before implementing:** `devkit review <slug>` must report READY before any non-spike task starts. `tracker.py start` enforces this.
- Documents follow their templates (`devkit/templates/manifest.json`) and must pass `devkit lint`. Generated files (`tasks.json`, `TASKS.md`, `traceability.md`, `readiness.md`, workspace `README.md`, `decision-log.*`) change only through their tools.
<!-- devkit:end -->
