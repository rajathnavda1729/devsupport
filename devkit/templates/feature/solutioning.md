<!-- devkit:doc type=solutioning v=1 -->
# Solutioning — {{title}}

**Status:** Draft
**Feature:** `{{slug}}` · **Updated:** {{date}} · **Upstream:** `../01-requirements/requirements.md`, decision log

## 1. Decision context (existing ADRs)
Accepted decisions already recorded in this repo that bear on this feature. Find them with `python3 devkit/tools/adr.py search <keywords>`. Accepted ADRs are binding: either comply with one, or propose a superseding ADR and get approval.

| ADR | Title | Status | Impact (constrains / complies / supersedes / n.a.) | Notes |
|-----|-------|--------|----------------------------------------------------|-------|
<!-- TODO: | ADR-0003 | Use PostgreSQL for transactional data | Accepted | constrains | rules out a document store for orders | -->

## 2. Architecturally significant requirements (drivers)
The requirements that shape the solution most — every CRITICAL item plus NFRs with hard targets.

| ID | Driver | Why it drives the design |
|----|--------|--------------------------|
<!-- TODO -->

## 3. Problem characteristics
<!-- TODO: read/write ratio, data volume & growth, consistency needs, latency budget, traffic shape (steady/bursty), integration count, team size/skills, change frequency -->

## 4. Candidate design patterns
Pulled from `devkit/knowledge/design-patterns.md`. Reject explicitly — a rejected pattern with a reason is as valuable as an adopted one.

| Pattern | Problem signal it addresses | Fit (✅ adopt / 🤔 maybe / ❌ reject) | Reason | Requirements served |
|---------|-----------------------------|----------------------------------------|--------|---------------------|
<!-- TODO -->

## 5. Solution options
### Option A — <!-- TODO: name -->
- **Summary:**
- **Patterns used:**
- **Pros:**
- **Cons:**
- **Risks:**
- **Rough cost / effort:**

### Option B — <!-- TODO: name -->
- **Summary:**
- **Patterns used:**
- **Pros:**
- **Cons:**
- **Risks:**
- **Rough cost / effort:**

## 6. Comparison matrix
Weights come from the drivers (sum = 100). Score 1–5. Weighted = weight × score.

| Criterion (linked req) | Weight | Option A | Option B | Option C |
|------------------------|--------|----------|----------|----------|
<!-- TODO: | Latency (NFR-001) | 30 | 4 (120) | 3 (90) | … | -->
| **Total** | **100** | | | |

## 7. Industry benchmarks & references
<!-- TODO: published numbers for the technologies under consideration (throughput, latency, cost), with source and date. Mark anything not measured by us as "external". -->

## 8. Proof-of-concept benchmark
Plan for measuring the options we cannot decide on paper. Results stored under `benchmarks/` via `devkit/tools/bench.py`.

| Experiment | Option(s) | Command / endpoint | Metric | Pass criterion | Result |
|------------|-----------|--------------------|--------|----------------|--------|
<!-- TODO -->

## 9. Recommendation
<!-- TODO: chosen option, the 2-3 decisive reasons, what we are trading away, conditions that would make us revisit. Record as ADR: python3 devkit/tools/adr.py new --feature {{slug}} --title "..." -->

## 10. New decisions (ADRs written for this feature)
| ADR | Decision | Status | Supersedes |
|-----|----------|--------|------------|
<!-- TODO -->
