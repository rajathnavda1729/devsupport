---
name: requirements-breakdown
description: Break a raw requirement into functional and non-functional requirements with IDs, MoSCoW priority, Given/When/Then acceptance criteria, and a highlighted list of CRITICAL requirements; also captures assumptions, constraints and open questions. Use when the user shares a requirement, user story, PRD, ticket or idea and wants it analysed or broken down.
argument-hint: "<feature-slug>"
---

# Requirements breakdown

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

**Input:** `<ws>/01-requirements/input.md`. Create it with `scaffold.py new` if it is missing.
**Output:** a filled-in `<ws>/01-requirements/requirements.md`. Keep the template structure.
**References:** `devkit/knowledge/nfr-checklist.md`, `devkit/knowledge/criticality-rubric.md`

## Steps
1. **Read the input twice.** On the first pass, understand the intent. On the second pass, mark each sentence as one of:
   - a need (a requirement candidate);
   - a constraint;
   - an assumption;
   - a solution in disguise. Rewrite it as the underlying need and note the original as a constraint only if it is truly mandated.
2. **Problem, goals and non-goals.** Make the goals measurable. Put scope boundaries in the non-goals explicitly.
3. **Actors.** List the humans and the systems. Every FR names an actor.
4. **Functional requirements.** For each requirement, write one row:
   - Use the form "The system shall …". Make it atomic: one behaviour per row. Split anything joined by "and".
   - Give it a MoSCoW priority.
   - Give it a source reference to the input section/line, or `inferred`, or `assumption A#`.
   - Give it at least one acceptance criterion in Given/When/Then form. Include the main negative case for Must items.
   - Cover the obvious implied behaviours the requester forgot: validation, permissions, empty states, errors, concurrency, deletion, notifications. Mark them `inferred`.
5. **Non-functional requirements.** Walk every category in the NFR checklist. Write an NFR wherever it matters. Each NFR needs a metric, a target, a condition and a verification method. If the requester gave no number, propose a sensible target, mark it `assumption`, and add an open question.
6. **Criticality.** Score each requirement with the rubric. Write `CRITICAL` in the Criticality column for qualifying rows; the tooling detects the word. Fill in §6 with why each item is critical, what fails, the guard you expect, and how it is verified. Expect roughly 5–20% of requirements to be critical. If every requirement is critical, none is.
7. **Assumptions, constraints, dependencies, open questions.** For the constraints, run `python3 devkit/tools/adr.py search <domain keywords>`. List the Accepted ADRs that limit scope, citing their ADR ids, for example "must use the existing event bus (ADR-0006)". For each open question, mark whether it is blocking.
8. **Self-check before finishing:**
   - [ ] IDs are sequential, unique and never reused (FR-001…, NFR-001…).
   - [ ] No FR describes an implementation ("use Kafka"). Implementation choices are constraints or belong in solutioning.
   - [ ] Every NFR has a number and a verification method.
   - [ ] Every CRITICAL row appears in §6.
   - [ ] Every row is testable. A tester could write a pass/fail check from it.
   - [ ] No `<!-- TODO` markers remain in the sections you filled. Write "None" where a section is empty.
   - [ ] `python3 devkit/tools/doclint.py <ws>/01-requirements/requirements.md` reports 0 errors.
9. Set `**Status:** Draft` (or `Review` if you are handing it to the user), and update the date.

## Output to the user
Report the counts (FR by priority, NFR by category), the 🔴 critical list in one line each, the blocking open questions, and the assumptions that need confirmation.
