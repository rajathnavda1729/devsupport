---
name: hld
description: Produce a High-Level Design with mermaid diagrams (C4 context & containers, key sequence flows, deployment), component responsibilities, data architecture, interfaces, NFR realisation table and guards for critical requirements. Use after solutioning, or when the user asks for an HLD, architecture doc, system design or architecture diagram.
argument-hint: "<feature-slug>"
---

# High-Level Design

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

**Input:** `01-requirements/requirements.md`, `02-design/solutioning.md` (the recommended option, §1 prior ADRs, §10 new ADRs)
**Output:** `<ws>/02-design/hld.md`
**References:** `devkit/knowledge/mermaid-conventions.md`

## Steps
1. **Overview.** Describe the chosen option in plain language.
2. **Architecture decisions applied (§2).** List every ADR from solutioning §1 (constrains/complies) and §10, and state where the design honours each one. If the design cannot honour an Accepted ADR, stop and go back to solutioning to supersede it through `adr-author`.
3. **Context diagram (C4 L1).** Show all actors and external systems from the requirements. Nothing internal.
4. **Container diagram (C4 L2).** Show every deployable unit and datastore, with the protocols on the edges. Fill in the component table: responsibility, tech, data owned, scaling axis, and the requirement IDs it serves. Every Must FR maps to at least one component.
5. **Key flows.** Draw one sequence diagram per CRITICAL or Must user journey. Include the main failure path with `alt`. Annotate critical steps with the requirement ID.
6. **Data architecture.** Cover the entities, which component owns them, the stores, the consistency model, retention and PII classification.
7. **Interfaces.** Fill in the table for every interface crossing a component boundary: sync/async, protocol, contract location, SLA.
8. **Deployment view.** Cover environments, scaling, network zones and the stateful parts.
9. **NFR realisation (§9).** Every NFR from the requirements appears with its design tactic, component and verification. If an NFR has no tactic, flag it as a risk.
10. **Critical guards (§10).** Every CRITICAL requirement gets a concrete guard, such as idempotency, redundancy, validation, audit or reconciliation, plus the failure mode it handles.
11. **Cross-cutting concerns, risks, open issues.**
12. **Validate:** `python3 devkit/tools/doclint.py <ws>/02-design/hld.md`.

## Quality bar
- Every diagram follows the conventions and renders, so check the syntax mentally: quoted labels with special characters, alphanumeric node ids.
- No component exists without a requirement. No Must FR or NFR is left unmapped.
- The HLD stays at the box-and-arrow level. Classes, tables and endpoint payloads belong in the LLD.
