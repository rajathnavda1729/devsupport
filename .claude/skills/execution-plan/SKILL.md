---
name: execution-plan
description: Generate an execution/delivery plan from the task tracker — milestones with exit criteria, parallel waves, mermaid gantt timeline, critical path, resourcing, delivery risks, rollout and rollback plans, definition of done. Use after task breakdown, or when the user asks for a project plan, roadmap, timeline, release or rollout plan.
argument-hint: "<feature-slug> [start-date] [team-size]"
---

# Execution plan

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

**Input:** the tracker (`tracker.py waves --json`, `tracker.py list --json`), the HLD deployment view, and the risks from the requirements and HLD.
**Output:** `<ws>/03-delivery/execution-plan.md`

## Steps
1. Get the facts. Do not estimate by hand.
   - `python3 devkit/tools/tracker.py -f <slug> waves --json` gives the waves, the critical path and the points.
   - `python3 devkit/tools/tracker.py -f <slug> stats`
   - `python3 devkit/tools/tracker.py -f <slug> schedule --start <date> --team <n> --focus 0.7 --deadline <date>` assigns tasks to engineers respecting dependencies, gives the finish date and checks the deadline (exit 1 if it is missed). Add `--mermaid` to generate the gantt chart for §4. Do not hand-write task dates.
   - **If the deadline is missed**, the plan must say so, and propose concrete options: split critical-path tasks, add people to parallel waves, cut Could/Should scope, or move the date. Present them to the user.
2. **Assumptions.** Ask for, or assume and state, the start date, team size, and velocity. The default is 1 point ≈ 1 ideal day per engineer at 70% focus.
3. **Milestones.** Group the work by `phase` (M1-skeleton → M2-core → M3-hardening → M4-release). Each milestone gets demonstrable exit criteria.
4. **Waves.** Within each wave, assign tasks to people so that no one exceeds capacity. Tasks on the critical path get the most experienced owner.
5. **Gantt chart.**
   - Draw a mermaid `gantt` with one section per milestone or wave.
   - Encode dependencies with `after <id>`.
   - Use task IDs without the dash as gantt ids (`T001`).
   - Duration = points ÷ focus factor, rounded up to days.
6. **Critical path.** State its length and what any slip on it does to the end date. Name the buffer explicitly, around 15–25%.
7. **Delivery risks.** Give each risk a trigger, a mitigation and a contingency. Spikes and external dependencies are always risks.
8. **Rollout.**
   - Give the environment sequence.
   - Use feature flags.
   - Plan the canary steps, with the SLOs that gate each step, taken from the NFRs.
   - Give the data migration order: expand → migrate → contract.
   - Plan the communication.
9. **Rollback.** State the measurable trigger conditions, the exact steps, the data recovery approach, and the owner.
10. **Definition of done.** Keep the template's checklist and add feature-specific items.

Update the plan whenever the tracker changes materially, such as new tasks or slipped critical-path items.
