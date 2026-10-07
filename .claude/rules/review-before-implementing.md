# Review before implementing

- No implementation work (production code, migrations, infrastructure) for a devkit feature starts until `devkit review <slug>` (`python3 devkit/tools/review.py readiness <slug>`) reports **READY**.
- `tracker.py start` enforces this for every task except spikes. Spikes are time-boxed investigations that inform decisions, and they may run earlier.
- A bypass is exceptional:
  - it needs `--force --note "<who approved and why>"`;
  - it is recorded on the task;
  - it must be reported to the user.
- **Thorough evaluation is part of readiness.** Every significant decision must:
  - be compared across ≥2 options with weights that sum to 100;
  - survive the sensitivity analysis, or carry PoC evidence or an explicit `**Override:**`;
  - have its trade-offs, evidence quality, reversibility, pre-mortem and challenge recorded in the ADR;
  - be **Accepted by the user**.
- Claude never approves documents or accepts ADRs on its own. It summarises them and asks the user.

**Why:** design and decision errors cost the least to fix before code exists. The gate makes "we reviewed it" verifiable instead of a claim.
