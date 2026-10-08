---
name: implementation-readiness
description: Review-before-implementing gate. Checks that a feature is ready to build — requirements/solutioning/HLD/LLD approved, design review passed with blocking findings resolved, decisions thoroughly evaluated and accepted, prior ADRs respected, documents match templates, tasks valid — and drives the fixes. Use before starting implementation, when `tracker.py start` refuses a task, or when the user asks "can we start building", "are we ready", "review before implementing".
argument-hint: "<feature-slug>"
---

# Implementation readiness — review before implementing

**Command:** `devkit review <slug>`, or `python3 devkit/tools/review.py readiness <slug>`.
**Output:** `<ws>/03-delivery/readiness.md`, which is generated. The command exits 1 when the feature is not ready.
**Enforced by:** `tracker.py start` refuses any non-spike task until the gate passes.
- Spikes are exempt, because they exist to inform decisions.
- A bypass needs `--force --note "<reason>"`, and the bypass is recorded on the task.

## The gate
| Check | Passes when |
|-------|-------------|
| Design documents approved | requirements, solutioning, hld and lld are `Approved`; execution-plan and test-plan are at least `Review` |
| Blocking open questions answered | every row in requirements §10 marked *Blocking? Yes* has an answer |
| Design review | `02-design/reviews/design-review.md` is Approved, its verdict is APPROVE or APPROVE WITH CHANGES, and every blocking finding is marked resolved |
| Options thoroughly compared | the matrix is valid (weights = 100, ≥2 options), and any close or fragile call has evidence or an explicit override, and the recommendation matches the winner or carries an `**Override:**` line; ≥1 rejected alternative |
| Prior decisions respected | `adr.py check` is clean: decision context filled, no citation of a missing ADR; HLD §2 and LLD §13 apply only ADRs in force, and HLD §2 includes every live decision from solutioning §10 |
| Decisions evaluated and accepted | every feature ADR, and every ADR in solutioning §10, passes `review decision` and is `Accepted`. Rejected, deprecated and superseded ADRs are records, so they don't block |
| Documents match templates | `doclint` reports 0 errors |
| Tasks valid and traceable | `tracker.py validate` is clean, with ≥1 task |

## Steps
1. Run `devkit review <slug>` (add `-v` for details on passing checks too).
2. For each failing check, fix the cause in the right place. Never edit `readiness.md`.
   - **Unapproved documents:** summarise each one for the user and ask for approval. Only the user approves. Then set `**Status:** Approved`; TODO markers must be gone first.
   - **Missing or failed design review:** run the `design-reviewer` agent. Fix the blocking findings in the HLD or LLD, then mark them resolved in the review.
   - **Matrix or decision gaps:** follow the `decision-evaluation` skill.
   - **ADR not accepted:** present it to the user. Only they accept it.
   - **Lint or tracker errors:** fix them as the tool reports.
3. Re-run until it reports **READY**, then tell the user that implementation can start, and show `devkit task -f <slug> next`.
4. If the user insists on starting early, they may bypass the gate for one task: `devkit task -f <slug> start T-00x --force --note "<who approved and why>"`. Report the bypass in your summary.
