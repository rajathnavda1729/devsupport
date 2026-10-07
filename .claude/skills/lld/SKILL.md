---
name: lld
description: Produce a Low-Level Design — module structure, class diagrams with design patterns, API contracts, data model (ER), state machines, detailed sequence diagrams with error paths, algorithms, error handling, concurrency, configuration, logging/metrics and testability. Use after the HLD, or when the user asks for an LLD, detailed design, API spec, schema design or class design.
argument-hint: "<feature-slug> [component]"
---

# Low-Level Design

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

**Input:** `02-design/hld.md`, plus `01-requirements/requirements.md` for the acceptance criteria.
**Output:** `<ws>/02-design/lld.md`. For large systems, write one LLD section per component.

## Steps
1. **Read the codebase if one exists.** Match the existing conventions for language, frameworks, folder layout and error handling. State which conventions you are following.
2. **Module structure.** Give the proposed tree with one line of purpose per module. Keep domain logic separate from I/O, using ports and adapters where it helps.
3. **Class / module design.** Draw a `classDiagram` with the interfaces, the main classes and their relations. In the table, name the design pattern each one realises, from the solutioning doc, and the requirement IDs it serves.
4. **API contracts.** For every endpoint or message, give:
   - the purpose, with its FR ID;
   - auth;
   - the request and response JSON;
   - the error codes;
   - idempotency;
   - pagination;
   - rate limits;
   - versioning.

   For CRITICAL operations, spell out exactly how duplicates and partial failures behave.
5. **Data model.** Give an `erDiagram`, then indexes justified by the query patterns, the partition or shard key, retention, and the migration and backfill approach.
6. **State machines.** Draw one for every entity with a lifecycle. List the invalid transitions and how they are rejected.
7. **Detailed flows.** Draw sequence diagrams that include timeouts, retries (with limits), and the compensation or rollback paths.
8. **Algorithms.** Write pseudo-code for the non-trivial logic, with its time and space complexity and the edge cases.
9. **Error handling table.** Cover every error class: where it is detected, the response, whether to retry, its log level, and whether it alerts.
10. **Concurrency and consistency.** Cover locking, isolation level, idempotency keys and ordering.
11. **Configuration.** Cover the keys, the defaults, and which values are secrets.
12. **Logging and metrics.** Name the log events with their level and fields, and use a correlation id. This list becomes the input to the `log-watcher` skill's rules.
13. **Testability.** Cover the seams, the fakes, and the contract-test needs.
14. **Decisions applied (§13).** List the implementation constraints that come from ADRs (repo-wide and feature), for example "all money in minor units (ADR-0004)", and where each is applied.
15. **Validate:** `python3 devkit/tools/doclint.py <ws>/02-design/lld.md` and `python3 devkit/tools/adr.py check <slug>`.

## Quality bar
- A competent engineer could implement each module without asking a design question.
- Every acceptance criterion in the requirements is satisfiable by something in the LLD.
- Every error path from the HLD sequences has a concrete handler here.
