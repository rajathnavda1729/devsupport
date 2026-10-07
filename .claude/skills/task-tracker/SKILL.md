---
name: task-tracker
description: Operate the devkit task tracker — show the board, pick the next task, start/finish/block tasks, add notes, add or re-scope tasks, show dependency graph, waves and critical path, and check requirement/test coverage. Use when the user asks "what's next", "mark T-003 done", "what is blocked", "show progress/board", or while implementing tasks from a devkit plan.
argument-hint: "[feature-slug] [command]"
---

# Task tracker

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

All state lives in `<ws>/03-delivery/tasks.json` and is changed **only** through the CLI. Never edit `tasks.json` or `TASKS.md` by hand. `TASKS.md` is regenerated on every write.

`T` = `python3 devkit/tools/tracker.py -f <slug>`. The `-f` flag can be omitted when only one feature exists or `DEVKIT_FEATURE` is set.

| Intent | Command |
|--------|---------|
| What should I work on? | `T next` |
| Start a task (enforces deps **and the readiness gate**) | `T start T-004` |
| Start despite the gate (recorded) | `T start T-004 --force --note "<who approved, why>"` |
| Send for review | `T review T-004 --note "PR #12"` |
| Finish | `T done T-004 --note "merged #12"` |
| Blocked (reason required) | `T block T-004 --note "waiting for staging DB creds"` |
| Unblock / reopen | `T reopen T-004` |
| Drop scope | `T cancel T-009 --note "descoped by PO 2026-10-07"` |
| New task discovered | `T add --title "..." --type bug --priority P1 --estimate S --reqs FR-002 --deps T-004 -a "criterion"` |
| Edit fields | `T update T-004 --estimate M --owner alice --note "split out T-015"` |
| List / filter | `T list --status in_progress,blocked` · `T list --req FR-003` · `T list --json` |
| Details | `T show T-004` |
| Progress | `T stats` · `T board` (then open `TASKS.md`) |
| Dependencies | `T graph` (mermaid) · `T waves` |
| Coverage gaps | `T validate` · `T trace` (writes `traceability.md`) |

## Working agreement while implementing
1. Before coding, run `T next`, then `T start <id>`, and read the task's acceptance criteria and linked requirements.
   - If `start` refuses with "not ready for implementation", follow the `implementation-readiness` skill.
   - Spike tasks are exempt from the gate.
2. While working, if you discover new work, `T add` it with dependencies. Do not silently grow the current task.
3. When you finish, check every acceptance criterion and run the relevant tests. Then `T done <id> --note "<evidence: test names, PR, commit>"`.
4. If you are stuck, `T block <id> --note "<reason + who can unblock>"` and move on to the next ready task.
5. At the end of a session, report `T stats` and any blocked items.
