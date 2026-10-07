<!-- devkit:doc type=test-plan v=1 -->
# Test Plan — {{title}}

**Status:** Draft
**Feature:** `{{slug}}` · **Updated:** {{date}} · **Upstream:** `../01-requirements/requirements.md`, `../02-design/lld.md`

## 1. Scope
**In scope:** <!-- TODO -->
**Out of scope:** <!-- TODO -->

## 2. Strategy
<!-- TODO: risk-based — CRITICAL requirements get positive, negative, boundary and failure-injection cases -->

## 3. Environments & data
<!-- TODO -->

## 4. Entry / exit criteria
- **Entry:** <!-- TODO -->
- **Exit:** all P0/P1 cases pass; no open Sev-1/Sev-2 defects; every CRITICAL requirement has ≥1 passing case; benchmark SLOs pass.

## 5. Test cases
Only the first column defines the ID. The *Requirements* column feeds the traceability matrix (`tracker.py trace`).

| ID | Title | Requirements | Type | Priority | Preconditions | Steps | Expected result | Automated? | Status |
|----|-------|--------------|------|----------|---------------|-------|-----------------|------------|--------|
<!-- TODO: | TC-001 | Create short link happy path | FR-001 | Functional | P0 | user authenticated | POST /links {url} | 201 + code | yes | Not run | -->

## 6. Non-functional tests
| ID | NFR | Scenario | Tool | Pass criterion |
|----|-----|----------|------|----------------|
<!-- TODO: performance via bench.py, security scans, resilience/chaos, accessibility -->

## 7. Defect management
<!-- TODO: severity definitions, where bugs are filed (also as tracker tasks with type=bug) -->

## 8. Risks
<!-- TODO -->
