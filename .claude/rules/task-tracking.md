# Task tracking

- Every workspace's `tasks.json` and `TASKS.md` are modified **only** via `python3 devkit/tools/tracker.py`. Never edit them with Write or Edit.
- When implementing work from a devkit plan:
  1. `tracker.py next`, then `tracker.py start <id>`.
  2. Do the work.
  3. Verify the task's acceptance criteria.
  4. `tracker.py done <id> --note "<evidence>"`.
- Newly discovered work becomes a new task (`tracker.py add`) with requirement links and dependencies. Do not silently expand the current task.
- A blocked task always carries a reason: `tracker.py block <id> --note "..."`.

**Why:** the board, waves, critical path and traceability matrix are derived from tasks.json. Hand edits break the derivations and the audit trail.
