# devkit — requirement-to-delivery kit for Claude Code

This repo is a dev kit. It takes a raw requirement through analysis, design, planning, testing and benchmarking. It does this with Claude Code **skills**, **sub-agents** and **rules**, backed by deterministic stdlib-Python tools.

## Start here
- New requirement or feature: run the `devkit` skill (`/devkit <slug> <requirement or file>`).
- Existing decisions: `adr-discovery` skill (`python3 devkit/tools/adr.py scan`).
- Resume a feature: `python3 devkit/tools/scaffold.py status <slug>`, then continue at the first unfinished stage.
- Implementing tasks: follow the `task-tracker` skill (`tracker.py next` → `start` → work → `done`).

## Layout
| Path | What |
|------|------|
| `.claude/skills/<name>/SKILL.md` | One skill per pipeline stage, plus the `devkit` orchestrator and `kit-forge` (generates new skills, agents and rules) |
| `.claude/agents/*.md` | Specialist sub-agents: requirements-analyst, solution-architect, detailed-designer, design-reviewer, delivery-planner, qa-strategist, performance-engineer |
| `.claude/rules/*.md` | Always-on constraints, scoped by path (incl. document-format, architecture-decisions) |
| `devkit/tools/` | `scaffold.py` (workspaces, documents, index), `adr.py` (detect/record ADRs, decision log), `doclint.py` (template conformance), `review.py` (decision evaluation, implementation-readiness gate), `tracker.py` (tasks, waves, traceability), `bench.py` (benchmarks and SLO gates), `logwatch.py` (local log watcher) |
| `src/devkit_cli/`, `bin/devkit`, `pyproject.toml` | The `devkit` CLI: reviewable install/update/diff/doctor/uninstall into target repos or `~/.claude`, plus pass-through to the tools. Assets are bundled into the wheel |
| `devkit/hooks/` | `guard_generated.py` (blocks edits to generated files), `lint_doc.py` (lints every written document) |
| `devkit/templates/` | `manifest.json` (document types, grouped layout), document templates (`feature/`), ADR template, meta templates for skills, agents, rules and new document types |
| `devkit/knowledge/` | Design-pattern catalog, NFR checklist, criticality rubric, mermaid conventions |
| `<ws>` (feature workspace) | Grouped documents per feature: `01-requirements/`, `02-design/` (+`decisions/`, `reviews/`), `03-delivery/`, `04-quality/`, plus a generated `README.md` index. Lives in the **target repo**: `specs/<slug>/` by default (`.devkit.json` → `specs_dir`), or `<module>/specs/<slug>/` via `scaffold.py new --at`. Look it up with `scaffold.py where <slug>` |

## Non-negotiables
- Artifacts in the feature workspace are the source of truth. Write results there, not only in chat.
- IDs (FR/NFR/T/TC/ADR) are permanent. Never renumber them.
- Templates are the contract: documents are created by tools (`scaffold.py new/doc`, `adr.py new`) and must pass `doclint.py`. A hook lints every write.
- Review before implementing: `review.py readiness <slug>` must pass before non-spike tasks start (`tracker.py start` enforces it). Decisions must pass `review.py matrix` and `review.py decision` and be accepted by the user. Claude never approves or accepts on the user's behalf.
- Accepted ADRs in the target repo are binding. Run `adr.py scan` and `adr.py search` before designing. Change a decision only through a superseding ADR, with the user's approval.
- Generated files (`tasks.json`, `TASKS.md`, `traceability.md`, workspace `README.md`, `decision-log.*`) change only through their tools. A hook enforces this.
- Never fabricate benchmark numbers or test results. Mark them "not run" with a reason.
- Every CRITICAL requirement must trace to a design guard, a task and a test (`tracker.py validate` must pass).

## Developing the kit itself
- The tools are stdlib-only Python 3.10+. Each needs `--help` and tests in `tests/`.
- Run the tests: `python3 -m unittest discover -s tests`
- The CLI runs from the clone via `./bin/devkit`. A new file under `.claude/` or `devkit/` ships automatically; check with `devkit install --dry-run --target <scratch repo>`.
- When you add a skill, agent, rule or document type, follow the `kit-forge` skill and update the tables in `README.md` and this file.
