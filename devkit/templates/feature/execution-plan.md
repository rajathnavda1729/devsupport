<!-- devkit:doc type=execution-plan v=1 -->
# Execution Plan — {{title}}

**Status:** Draft
**Feature:** `{{slug}}` · **Updated:** {{date}} · **Upstream:** `tasks.json` (`TASKS.md`)

## 1. Summary
<!-- TODO: scope, total points, number of waves, critical path length, target dates -->

## 2. Milestones
| Milestone | Exit criteria | Tasks | Target date |
|-----------|---------------|-------|-------------|
<!-- TODO: M1 walking skeleton → M2 core Must FRs → M3 NFR hardening → M4 release -->

## 3. Waves (from `tracker.py waves`)
<!-- TODO: paste waves; note which can be parallelised across people -->

## 4. Timeline
```mermaid
gantt
  title {{title}}
  dateFormat YYYY-MM-DD
  section Wave 1
  T-001 placeholder :t1, {{date}}, 1d
```
<!-- TODO -->

## 5. Critical path
<!-- TODO: from tracker; what happens if any item slips -->

## 6. Resourcing & ownership
<!-- TODO -->

## 7. Risks to delivery
| Risk | Trigger | Mitigation | Contingency |
|------|---------|------------|-------------|
<!-- TODO -->

## 8. Rollout plan
<!-- TODO: environments, feature flags, canary %, data migration order, comms -->

## 9. Rollback plan
<!-- TODO: trigger conditions (link to NFR/SLO), steps, data recovery, owner -->

## 10. Definition of done
- [ ] All Must FRs implemented with passing acceptance tests
- [ ] All CRITICAL requirements covered by tests (`tracker.py validate` clean)
- [ ] Benchmarks meet NFR SLOs (`bench.py` gates pass)
- [ ] Log watcher shows no ERROR/critical alerts in a full local test run
- [ ] Docs and runbook updated
