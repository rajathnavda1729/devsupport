---
name: adr-author
description: Record a new architecture decision (or supersede / accept / reject an existing one) using the devkit ADR template, with repo-wide numbering that follows the repo's existing ADR naming, and keep the decision log and feature documents in sync. Use when solutioning/HLD/LLD makes a significant decision, when a design must deviate from an accepted ADR, or when the user says "write an ADR", "record this decision", "supersede ADR-x", "accept ADR-x".
argument-hint: "<title> [--feature <slug>] [--supersedes <n>]"
---

# ADR author — record decisions consistently

**Tool:** `devkit/tools/adr.py` · **Template:** `devkit/templates/adr.md`. Status values: Proposed → Accepted | Rejected | Deprecated | Superseded.

## When a decision needs an ADR
Record one when any of these hold:
- the decision is costly to reverse;
- it affects a CRITICAL requirement or an NFR target;
- it chooses between technologies or patterns;
- it constrains other teams or features;
- it deviates from an existing Accepted ADR. This case always needs a superseding ADR.

## Where it goes
| Decision affects | Command | Location |
|------------------|---------|----------|
| Only this feature's internals | `adr.py new --feature <slug> --title "…"` | `<ws>/02-design/decisions/` |
| The repo / other features / platform | `adr.py new --title "…"` | repo decisions dir (`docs/adr/` or the existing ADR folder) |

Numbers are unique across the whole repo. File naming follows the existing ADRs in the target folder, e.g. `0007-…` or `ADR-0007-…`.

## Steps
1. **Check prior decisions first:** run `python3 devkit/tools/adr.py search <keywords>`.
   - If an Accepted ADR already covers the topic, comply with it. Cite it, and do not write a duplicate.
   - If the new decision contradicts that ADR, you need `--supersedes <n>` **and** the user's explicit approval. Say clearly which decision is being replaced and why.
2. **Create the ADR:**
   `python3 devkit/tools/adr.py new --title "<decision as a statement>" [--feature <slug>] [--tags a,b] [--supersedes <n>]`
   Use the printed path.
3. **Fill in every template section.** Keep the headings, their order and the header fields; the format hook rejects drift.
   - **Context:** cite requirement IDs (FR/NFR) and related ADRs.
   - **Considered options:** ≥2 real options, taken from the solutioning comparison where one exists.
   - **Decision:** "We will …", stated so that compliance can be checked in code.
   - **Consequences:** include the trade-offs you are accepting.
   - **Compliance & evidence:** how a reviewer verifies it, such as files, lint rules or tests.
   - **Evaluation:** comparison, sensitivity, evidence quality, reversibility, pre-mortem and challenge, following the `decision-evaluation` skill. A one-way-door decision always gets the `decision-challenger` review.
   - **Revisit when:** a measurable trigger.
4. **Link it into the feature documents:**
   - solutioning §10, *New decisions*;
   - HLD §2 or LLD §13, *Decisions applied*.
5. **If the content changes materially while the ADR is still Proposed** (for example after a challenge round), keep the title truthful: `adr.py retitle <n> --title "…"`. Once Accepted, the title is frozen.
6. **Change its status** only when the user decides: `adr.py set-status <n> accepted` (or `rejected` / `deprecated`). Superseding happens automatically through `--supersedes`, or explicitly with `adr.py supersede <old> <new>`.
7. **Validate:**
   - `python3 devkit/tools/doclint.py <adr file>`
   - `python3 devkit/tools/adr.py check <slug>` (for feature work)
   - `python3 devkit/tools/review.py decision <n>`. It must pass before you ask the user to accept.

## Never
- Edit the decision text of an Accepted ADR. Only its status and links may change. Write a new ADR to change a decision.
- Delete or renumber ADRs.
- Mark a decision Accepted on the user's behalf.
