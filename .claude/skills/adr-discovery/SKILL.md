---
name: adr-discovery
description: Detect and document the architecture decisions that already exist in the target repo. Finds ADR files in any common format (Nygard/adr-tools, MADR, Y-statements, devkit), builds the repo decision log, and writes retroactive ADRs for important decisions that are in force in the code but were never recorded. Use before designing a feature in an existing codebase, when the user asks "what decisions were made", "document our architecture decisions", "find/scan ADRs", or when the decision log is missing or stale.
argument-hint: "[focus area, e.g. 'payments' or 'data layer']"
---

# ADR discovery — know the decisions before you design

**Tool:** `devkit/tools/adr.py`
**Output:**
- the repo decision log, `<decisions_dir>/decision-log.md` (+ `.json`), which is generated;
- retroactive ADRs in `<decisions_dir>/`.

`<decisions_dir>` is the existing ADR folder when the repo has one (detected, or set in `.devkit.json` → `decisions_dir`), otherwise `docs/adr/`.

## Steps
1. **Scan for recorded decisions:** `python3 devkit/tools/adr.py scan`.
   - It searches `.adr-dir`, `docs/adr`, `doc/architecture/decisions`, `decisions/` and similar folders anywhere in the repo, plus every feature's `02-design/decisions/`. It skips `node_modules`, `vendor` and build output.
   - It reports the formats found, the statuses, and any registry problems: duplicate numbers, unknown status, or a "superseded by" that points nowhere.
2. **Read the active decisions.** Use `adr.py list --status accepted,proposed` and open the ones relevant to the focus area (`adr.py show <n>`). Summarise them for the user in one line each.
3. **Fix registry problems** with the user's agreement. Typical fixes:
   - Set an unknown status: `adr.py set-status <n> accepted`.
   - Link a superseded pair: `adr.py supersede <old> <new>`.
   - Never renumber or delete an existing ADR.
4. **Decision archaeology: document the decisions that are in force but unrecorded.**
   1. Inspect the codebase for architecturally significant choices that have no ADR:
      - language and framework, and the monolith/services split;
      - datastores and ORMs;
      - messaging and queues;
      - API style (REST/gRPC/GraphQL) and versioning;
      - authN/Z approach;
      - multi-tenancy;
      - caching;
      - deployment target (k8s/serverless/VMs) and IaC;
      - CI/CD;
      - observability stack;
      - testing strategy;
      - repo layout (monorepo tool);
      - error-handling and logging conventions.
   2. Look for evidence in manifests (package.json, pyproject, go.mod, pom), docker-compose, IaC, CI config, config files and the code structure. `git log` on key files can date a decision.
   3. Keep only the decisions that are **costly to reverse** or **constrain new features**. Expect roughly 5–15 for a typical service. Skip trivia like the formatter choice.
   4. Present the candidate list to the user (decision, evidence, proposed status) and ask which ones to record. Do not create retroactive ADRs without that confirmation.
   5. For each confirmed decision, run:
      `python3 devkit/tools/adr.py new --retroactive --title "<decision as a statement>" --tags <area>`
      Then fill in the ADR from its template:
      - **Context:** what the evidence shows.
      - **Considered options:** "Not recorded (retroactive)", unless history shows the alternatives.
      - **Decision:** "We use …".
      - **Compliance & evidence:** `file:line` references.
      - **Revisit when:** the trigger that would reopen it.

      Never invent rationale. Write "Rationale not recorded" where it is unknown.
5. **Validate:** `python3 devkit/tools/doclint.py <new ADR files>`, then `adr.py scan` again to refresh the log.
6. **Report:** how many ADRs exist and in which formats, which are active, which retroactive ADRs you added, and the open problems. Name the decisions most likely to constrain upcoming work.

## Rules
- Existing ADRs keep their own format. The devkit template applies only to ADRs that devkit creates.
- An Accepted ADR is binding for new design work until it is superseded through `adr-author`.
- The decision log is generated. Never edit `decision-log.md` or `decision-log.json` by hand.
