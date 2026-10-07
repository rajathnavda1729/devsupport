---
name: solutioning
description: Come up with solution options for analysed requirements — load prior architecture decisions (existing ADRs), identify architectural drivers, match standard design patterns to the problem, compare options in a weighted matrix, gather industry benchmarks, plan/run proof-of-concept benchmarks, recommend one option and record ADRs. Use after requirements are written, or when the user asks "how should we build this", "which pattern fits", "compare approaches", "benchmark options".
argument-hint: "<feature-slug>"
---

# Solutioning

> **Workspace:** `<ws>` is this feature's folder in the target repo. Get it with `python3 devkit/tools/scaffold.py where <slug>`. Its documents are grouped: `01-requirements/`, `02-design/` (`decisions/`, `reviews/`), `03-delivery/`, `04-quality/`. Write only there.
>
> **Format contract:** fill in the document that `scaffold.py` created from its template. Never write a document from scratch. Keep these:
> - the `<!-- devkit:doc … -->` marker line;
> - the H1 prefix;
> - the header fields;
> - every H2 section, in its order;
> - the table columns;
> - the mermaid blocks the template has.
>
> Put extra detail under `###`. Write "None" or "N/A — reason" for an empty section. A missing document comes from `scaffold.py doc <slug> <type>`. The lint hook checks every write. Before you finish, run `python3 devkit/tools/doclint.py --feature <slug>`.

**Input:** `<ws>/01-requirements/requirements.md`, approved or at least reviewed.
**Output:** `<ws>/02-design/solutioning.md`, plus one or more ADRs in `<ws>/02-design/decisions/`.
**References:** `devkit/knowledge/design-patterns.md`, `devkit/tools/bench.py`

## Steps
1. **Decision context (§1). Do this before any design thinking.**
   - Run `python3 devkit/tools/adr.py scan`.
   - Run `python3 devkit/tools/adr.py search <3-6 feature keywords: domain, data, integration, tech>`.
   - Read every hit (`adr.py show <n>`). Record each relevant ADR with its impact on this feature:
     - **constrains:** it limits our options;
     - **complies:** we follow it;
     - **supersedes:** we intend to replace it. This needs the user's approval and a superseding ADR in step 10.
   - If the repo clearly has unrecorded decisions that matter here, run the `adr-discovery` skill first.
   - If nothing is relevant, write "None relevant — searched: <terms>".
2. **Drivers (§2).** Pick the architecturally significant requirements: every CRITICAL item, every NFR with a hard target, and any constraint that removes options. Constraints include the Accepted ADRs from §1. Usually 3–8 drivers.
3. **Problem characteristics (§3).** Quantify where you can: read/write ratio, volumes, growth, consistency needs, latency budget, traffic shape, team size and skills.
4. **Pattern matching (§4).** Use the *Signal → pattern index* in the catalog:
   - Shortlist every pattern whose signal appears.
   - For each pattern, decide adopt / maybe / reject, and give a reason tied to a requirement ID or an ADR.
   - Apply the *Evaluating fit* checklist. Prefer the simplest pattern that meets the target.
5. **Options (§5).** Write 2–3 genuinely different options. Make one of them the simplest viable option. Each option lists its patterns, pros, cons, risks and rough effort.
   - Name them **Option A / B / C**. The comparison table's columns use exactly these labels; put an unused column as `n/a`.
   - An option that violates an Accepted ADR must say so in its Risks.
6. **Comparison matrix (§6):**
   - Weight the criteria from the drivers so the weights sum to 100.
   - Score each option 1–5 and compute the weighted totals.
   - If the top two options are within 10%, say so and resolve the tie with a PoC benchmark.
7. **Industry benchmarks (§7).** Give published numbers, with source and date. Label them `external`. If you cannot verify a number, say "unverified".
8. **PoC benchmark (§8).** For each question the matrix cannot settle, define an experiment: the scenario, the metric, and the pass criterion derived from the NFR. If a prototype can be built quickly, run it:
   `python3 devkit/tools/bench.py cmd --name optA-<scenario> -n 30 --warmup 3 "<command>" --out <ws>/04-quality/benchmarks/optA-<scenario>.json`
   (or `bench.py http …`). Do the same for each option, then run `bench.py report <ws>/04-quality/benchmarks/opt*.json`. Never invent measurements. An experiment you did not run is reported as "not run".
9. **Recommendation (§9).** Give the chosen option and the 2–3 decisive reasons. Name the trade-offs you are accepting and the conditions that would make you revisit.
10. **New decisions (§10).** Follow the `adr-author` skill for each significant decision:
    - feature-internal: `adr.py new --feature <slug> --title "…"`;
    - repo-wide: `adr.py new --title "…"`;
    - replacing an ADR: `--supersedes <n>`, after explicit user approval.

    List each ADR in §10 with its status.
11. **Evaluate thoroughly.** Follow the `decision-evaluation` skill:
    - `devkit review matrix <slug>` checks the weights, margin and sensitivity, and requires evidence or an `**Override:**` for close or fragile calls;
    - the `decision-challenger` agent reviews each significant ADR;
    - every ADR's *Evaluation* section is filled in.
12. **Validate:**
    - `python3 devkit/tools/doclint.py <ws>/02-design/solutioning.md`
    - `python3 devkit/tools/adr.py check <slug>`
    - `python3 devkit/tools/review.py matrix <slug>`

## Quality bar
- §1 lists the relevant existing ADRs, or a search note. No option silently contradicts an Accepted ADR.
- Every adopted pattern cites ≥1 requirement ID.
- At least one pattern is explicitly rejected, with a reason.
- The matrix weights are traceable to the drivers.
- The recommendation states what we lose.
