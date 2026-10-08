---
name: devkit
description: End-to-end delivery pipeline orchestrator. Use when the user gives a new requirement / feature request / PRD and wants it taken through decision context (existing ADRs) → requirements → solutioning with thorough decision evaluation → HLD → LLD → design review → tasks → execution plan → testing guide → test plan → benchmarks → implementation-readiness review, or asks "where are we" on a feature. Also triggers on "/devkit", "start a new feature", "run the full pipeline".
argument-hint: "<feature-slug> [requirement text | path to requirement file]"
---

# devkit — pipeline orchestrator

You run a gated pipeline. Each stage fills in one templated document in the feature workspace `<ws>`, and each stage has its own skill that you follow when you reach it. Do not skip stages. Do not start a stage before its upstream document exists.

## Workspace layout (grouped; defined in `devkit/templates/manifest.json`)
```text
<ws>/README.md                 generated index: documents, states, decisions
<ws>/01-requirements/          input.md, requirements.md
<ws>/02-design/                solutioning.md, hld.md, lld.md, decisions/ (feature ADRs), reviews/design-review.md
<ws>/03-delivery/              tasks.json + TASKS.md (tracker), execution-plan.md
<ws>/04-quality/               testing-guide.md, test-plan.md, traceability.md, benchmark-plan.md, test-report.md, benchmarks/
<decisions_dir>/               repo-wide ADRs + generated decision-log.md
```

## Stages

| # | Stage | Skill | Document(s) | Specialist agent (optional) |
|---|-------|-------|-------------|-----------------------------|
| 0 | Capture + placement | (this skill) | `01-requirements/input.md` | — |
| 0.5 | Decision context: existing ADRs | `adr-discovery` | decision log | `decision-archaeologist` |
| 1 | Requirements: FR / NFR / critical | `requirements-breakdown` | `01-requirements/requirements.md` | `requirements-analyst` |
| 2 | Solutioning: prior decisions, patterns, options, comparison, benchmark | `solutioning`, `adr-author` | `02-design/solutioning.md`, `02-design/decisions/` | `solution-architect` |
| 2.5 | Decision evaluation: sensitivity, evidence, pre-mortem, challenge | `decision-evaluation` | ADR *Evaluation* section | `decision-challenger` |
| 3 | High-level design | `hld` | `02-design/hld.md` | `solution-architect` |
| 4 | Low-level design | `lld` | `02-design/lld.md` | `detailed-designer` |
| 4.5 | Design review | — | `02-design/reviews/design-review.md` | `design-reviewer` |
| 5 | Task breakdown + tracker | `task-breakdown`, `task-tracker` | `03-delivery/tasks.json`, `TASKS.md` | `delivery-planner` |
| 6 | Execution plan | `execution-plan` | `03-delivery/execution-plan.md` | `delivery-planner` |
| 7 | Testing guide | `testing-guide` | `04-quality/testing-guide.md` | `qa-strategist` |
| 8 | Test plan | `test-plan` | `04-quality/test-plan.md`, `traceability.md` | `qa-strategist` |
| 9 | Benchmarks + log watcher | `benchmark`, `log-watcher` | `04-quality/benchmark-plan.md`, `benchmarks/` | `performance-engineer` |
| 10 | **Implementation readiness: review before implementing** | `implementation-readiness` | `03-delivery/readiness.md` (generated) | — |

## Procedure

0. **Check you are in the target repo.** This is the repository where the requirement will be implemented. Run every command from its root. If `devkit/tools/` is missing there, stop and tell the user to run `<devkit-repo>/install.sh <target-repo>`. Never write a feature's documents into the devkit repo itself, unless the feature is about the devkit.
1. **Locate or create the workspace.**
   - Run `python3 devkit/tools/scaffold.py list`.
     - If the feature exists, run `scaffold.py status <slug>` and resume at the first stage that is not `filled`.
     - If it shows "legacy layout", run `scaffold.py migrate <slug>` first.
   - Otherwise decide **where the requirement is realised**. Explore the repo layout: monorepo packages, `services/*`, `apps/*`, `modules/*`, and existing `docs/`.
     - **One module/service owns the change:** use `--at <module-dir>`, which creates `<module-dir>/specs/<slug>/`.
     - **Cross-cutting, or a single-app repo:** use the repo default (`.devkit.json` → `specs_dir`).
     - **Unclear:** ask the user, listing the candidate dirs.
   - Create the workspace:
     `python3 devkit/tools/scaffold.py new <slug> --title "<Title>" [--at <module-dir>] --input <file>` (or `--text "<requirement>"`).
     Every document is created from its template at this point. You fill them in; you never write them from scratch.
   - `<ws>` = `python3 devkit/tools/scaffold.py where <slug>`.
2. **Decision context (stage 0.5).**
   - Run `python3 devkit/tools/adr.py scan`.
   - If the repo has code but few or no ADRs, run the `adr-discovery` skill, or delegate to `decision-archaeologist`, so that decisions already in force are known before you design.
   - Then run `adr.py search <feature keywords>` and keep the relevant ADRs for solutioning §1. Every later design stage must honour the Accepted ADRs.
3. **Run stages 1–10 in order.** For each one, load its skill and follow it exactly. You may delegate a stage to its specialist agent; pass the slug, `<ws>`, and the upstream document paths.
4. **Format gate after every stage.**
   - Run `python3 devkit/tools/doclint.py --feature <slug>`. Errors must be zero before you move on.
   - A PostToolUse hook also lints each document as you write it and refreshes `<ws>/README.md`.
5. **Approval gates after stages 1, 2 and 4.**
   - Show the user:
     - a short summary (FR/NFR counts, the critical items, the chosen option, the ADRs complied with, created or superseded);
     - the questions that block progress.
   - Blocking open questions must be answered before the requirements are approved. Record each answer in requirements §10, and update any affected requirements and assumptions.
   - Ask for approval. When the user approves, set `**Status:** Approved`. An Approved document must have no TODO markers; doclint enforces this.
   - New ADRs stay `Proposed` until the user accepts them (`adr.py set-status <n> accepted`).
   - If the user says "run it all without stopping", skip the gates but still list the open questions and the Proposed ADRs at the end.
5b. **Decision evaluation (stage 2.5)** happens before the solutioning approval gate. Follow `decision-evaluation`:
    - `devkit review matrix <slug>` must pass, including sensitivity, and evidence for close calls;
    - run the `decision-challenger` agent on each significant ADR (always for one-way doors);
    - `devkit review decision <ADR>` must pass.

    Present the margin, the sensitivity, the evidence and the strongest objection when you ask for approval.
6. **Design review (stage 4.5).**
   - Run `scaffold.py doc <slug> design-review` if the review document is missing.
   - Have the `design-reviewer` agent fill it in, checking the HLD and LLD against the requirements **and the ADRs**.
   - Fix the blocking findings before you break down tasks.
7. **After stage 8**, run all of these and fix every error before you declare the plan complete:
   - `tracker.py -f <slug> validate`
   - `tracker.py -f <slug> trace`
   - `adr.py check <slug>`
   - `doclint.py --feature <slug>`
7b. **Implementation readiness (stage 10). Review before implementing.**
    - Run `devkit review <slug>` (`python3 devkit/tools/review.py readiness <slug>`) and follow `implementation-readiness` until it reports READY.
    - Implementation never starts before that: `tracker.py start` enforces it for non-spike tasks.
    - Only the user approves documents and accepts ADRs. Ask; never set these yourself without their explicit go-ahead.
8. **Finish** with:
   - the workspace path (`<ws>/README.md` is the index);
   - `scaffold.py status <slug>`;
   - the critical requirements and how each is covered;
   - the decisions (complied with / new / superseded);
   - the top risks;
   - the readiness verdict;
   - the next ready tasks (`tracker.py -f <slug> next`).

## Rules
- **When a decision changes** (an ADR is rejected or superseded), regenerate every HLD and LLD section it touches from the new ADR's *Decision*. Do not patch individual lines: patching leaves contradictory leftovers in diagrams and tables. Then re-run the design review.
- The documents are the source of truth, not the chat. Write findings into the files.
- **Templates are the contract.**
  - Keep each document's marker line, H1, header fields, H2 sections (names and order), table columns and required diagrams.
  - Put extra detail under `###` inside the right section.
  - Write "None" or "N/A — reason" for a section that is empty.
  - A new kind of document needs a template first: use the `kit-forge` skill.
- IDs (FR-###, NFR-###, T-###, TC-###, ADR-####) are permanent. Never renumber them.
- Leave `01-requirements/input.md` as captured. Record clarifications in `requirements.md §10`.
- If information is missing, write an explicit assumption and raise it as an open question. Never invent facts.
