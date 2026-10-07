---
paths:
  - "**/02-design/solutioning.md"
  - "**/02-design/hld.md"
  - "**/02-design/lld.md"
  - "**/02-design/decisions/**"
---

# Design decisions

- Every adopted pattern, technology or component cites the requirement ID(s) that justify it. If nothing justifies it, it does not go in.
- Compare at least two genuinely different options before recommending one. The simplest viable option is always one of them.
- Record significant decisions as ADRs through the `adr-author` skill (`adr.py new`). A decision is significant if it is costly to reverse, affects a CRITICAL requirement or NFR, or picks between technologies. Accepted ADRs already in the repo are binding; see the architecture-decisions rule.
- Measured numbers come from `devkit/tools/bench.py` result files. External numbers cite their source and date. Unmeasured numbers say so. Never fabricate a benchmark.
- Every relevant ADR appears in solutioning §1 and HLD §2. Every NFR has a tactic in HLD §9. Every CRITICAL requirement has a guard in HLD §10.
- Follow `devkit/knowledge/mermaid-conventions.md` for diagrams.
