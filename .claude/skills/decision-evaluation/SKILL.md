---
name: decision-evaluation
description: Thoroughly evaluate a design or technology decision before it is accepted — criteria from drivers, at least two real options, weighted scoring, sensitivity analysis, evidence quality, reversibility (one-way vs two-way door), pre-mortem, and an adversarial challenge — then record the evaluation in the solutioning doc and the ADR. Use whenever solutioning picks an option, before an ADR is accepted, or when the user asks "are we sure", "evaluate this decision", "compare options properly", "stress-test this choice".
argument-hint: "<feature-slug> | <ADR id>"
---

# Decision evaluation

A decision counts as **thoroughly evaluated** only when all of the following are written down and the tools agree:

| # | Element | Where it lives | Checked by |
|---|---------|----------------|------------|
| 1 | Drivers: the requirements and ADRs that matter, weighted to sum to 100 | solutioning §2, §6 | `devkit review matrix` |
| 2 | ≥2 genuinely different options, including the simplest viable one | solutioning §5, ADR *Considered options* | matrix, `review decision` |
| 3 | Scores 1–5 per criterion, with weighted totals | solutioning §6 | matrix |
| 4 | Sensitivity: the winner survives ±20% on each weight | `devkit review matrix` output | matrix |
| 5 | Evidence for close calls (<10% margin) or fragile winners: a PoC benchmark result, or an explicit `**Override:**` with its reason | solutioning §8 / §9 | matrix |
| 6 | At least one rejected pattern or alternative, with the reason | solutioning §4 | matrix |
| 7 | Trade-offs accepted (negative consequences) | ADR *Consequences* | `review decision` |
| 8 | Evidence quality for each decisive claim: measured, external, judgement or assumption | ADR *Evaluation* | `review decision` |
| 9 | Reversibility: a one-way door gets extra scrutiny | ADR *Evaluation* | `review decision` |
| 10 | Pre-mortem: "12 months on, this failed because…", with mitigations | ADR *Evaluation* | `review decision` |
| 11 | Challenge: the strongest counter-argument and our response | ADR *Evaluation* | `review decision` |
| 12 | Human acceptance: status Accepted, set by the user | ADR status | readiness gate |

## Steps
1. **Score honestly.**
   - Fill in solutioning §6. Every score needs a one-line justification in §5's pros and cons.
   - Never tune weights after scoring to favour a preferred option. If the weights change, say why.
2. **Run the numbers:** `devkit review matrix <slug>`, or `python3 devkit/tools/review.py matrix <slug>`.
   - **Margin under 10%, or "FRAGILE":** do not pick by gut feel. Get evidence: run a PoC with the `benchmark` skill and put the result in §8.
   - **Evidence impossible to get:** write `**Override:** <reason>` in §9 and flag it to the user.
   - **Recommending the non-winner:** this always needs an `**Override:**` line.
3. **Classify reversibility.**
   - A **one-way door** is something like a data store, a public API contract, a vendor lock-in or a data model. It requires the PoC evidence or a strong external benchmark, a full pre-mortem, and the `decision-challenger` review.
   - A **two-way door** can be lighter, but still needs the elements listed above.
4. **Challenge it.** Delegate to the `decision-challenger` agent, with the slug and the ADR path.
   - Address each serious objection: change the decision, add a mitigation, or record why it is accepted.
   - Put the strongest objection and your response into the ADR's *Challenge* line.
5. **Write the ADR's Evaluation section:** comparison, sensitivity, evidence quality, reversibility, pre-mortem and challenge. Then run `devkit review decision <ADR>` until it passes.
6. **Ask the user to accept.** Present the decision, the margin, the sensitivity result, the evidence and the main risk in about five lines. Only the user moves the ADR to Accepted: `devkit adr set-status <n> accepted`.

## Never
- Present external or assumed numbers as measured.
- Accept an ADR on the user's behalf.
- Hide a fragile or overridden decision. Call it out in the summary.
