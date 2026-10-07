---
name: task-breakdown
description: Break a design (HLD/LLD) into small, dependency-ordered, estimable implementation tasks linked to requirement IDs, with acceptance criteria, and load them into the devkit task tracker. Use when the user asks to split work into tasks/tickets/stories, create a backlog or WBS, or after the LLD is done.
argument-hint: "<feature-slug>"
---

# Task breakdown

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

**Input:** `01-requirements/requirements.md`, `02-design/hld.md`, `02-design/lld.md`
**Output:** tasks in `<ws>/03-delivery/tasks.json`, created **only** through `devkit/tools/tracker.py`. The board in `TASKS.md` is generated automatically.

## Slicing rules
- **Size.** Every task is XS/S/M (≤ 3 points, about ≤ 2 days). Split anything L/XL. Point scale: XS=0.5, S=1, M=3, L=5, XL=8.
- **Order.**
  1. A walking skeleton comes first: a deployable end-to-end thread through every layer with trivial logic.
  2. Then vertical slices per FR: API + logic + persistence + test, rather than horizontal "all DB tables" tasks.
- **Critical first.** Tasks for CRITICAL requirements get P0 and are scheduled early, so their risk surfaces early.
- **Spikes.** Any open technical question becomes a time-boxed `spike` task that blocks the tasks depending on its answer.
- **Testing and NFR work are tasks too.** Include test-automation tasks (`type: test`), benchmark tasks for NFRs, log-watcher setup, observability, migration and rollout tasks.
- **Required fields.** Every `feature` or `infra` task lists the requirement IDs it implements and ≥1 acceptance criterion, which is checkable and taken from the requirement's Given/When/Then.
- **Dependencies.** Make them real and minimal. Do not chain tasks that could run in parallel.
- **Components and phases.** `component` matches an HLD component name. `phase` is a milestone: M1-skeleton, M2-core, M3-hardening or M4-release.

## Steps
1. Make sure the tracker exists: `python3 devkit/tools/tracker.py -f <slug> init --title "<Title>"`.
2. Draft all the tasks into a scratch JSON file, then import them in one go:
   ```json
   {"tasks": [
     {"id": "T-001", "title": "Walking skeleton: POST /links returns 201 stub", "type": "infra",
      "priority": "P0", "estimate": "S", "component": "api", "phase": "M1-skeleton",
      "requirements": ["FR-001"], "depends_on": [],
      "acceptance": ["Service starts locally", "POST /links returns 201 with stub body"]}
   ]}
   ```
   `python3 devkit/tools/tracker.py -f <slug> import <scratch.json>`
   - Fields: `id`, `title`, `description`, `type` (feature|infra|test|docs|spike|bug|chore), `priority` (P0–P3), `estimate`, `depends_on`, `requirements`, `component`, `phase`, `owner`, `acceptance`.
   - Re-importing with existing IDs updates those tasks. `--replace` rebuilds the list from scratch, but only before any work has started.
3. Validate: `python3 devkit/tools/tracker.py -f <slug> validate`. Fix every ERROR: unknown dependencies, cycles, critical requirements without tasks. Review the WARNs.
4. Show the waves and the critical path: `python3 devkit/tools/tracker.py -f <slug> waves`.
5. Report to the user: the task count, total points, the number of waves, the critical path, and the ready tasks (`tracker.py next`).
