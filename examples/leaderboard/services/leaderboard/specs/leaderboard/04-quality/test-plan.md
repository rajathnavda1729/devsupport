<!-- devkit:doc type=test-plan v=1 -->
# Test Plan — Near-realtime Leaderboards

**Status:** Review
**Feature:** `leaderboard` · **Updated:** 2026-10-08 · **Upstream:** `../01-requirements/requirements.md`, `../02-design/lld.md`

## 1. Scope
**In scope:**
- ingest (validation, exactly-once, season assignment);
- the outbox writer and versioned Redis writes;
- the read API (top-N, around-me, friends);
- the ops API (remove, restore, history);
- jobs (season close and snapshot, rebuild, reconcile, failover replay);
- every NFR in `requirements.md` §5.

**Out of scope:** the game client UI, anti-cheat detection logic, and rewards distribution (only the snapshot hand-off is tested).

## 2. Strategy
Testing is risk-based. The CRITICAL requirements (FR-002, FR-010, NFR-006) each get a positive case, a negative case and a failure-injection case. Correctness of the derived Redis state is tested in three layers:
1. property tests, where versioned writes in any order converge to the highest version;
2. integration tests against real PostgreSQL, Redis Cluster and Redpanda;
3. a chaos suite asserting **zero rank mismatches against PostgreSQL within 60 s** after each fault.

Performance is verified with `devkit/tools/bench.py` gates derived from the NFR targets. A local end-to-end run fails if `logwatch.py --fail-on ERROR` reports errors.

## 3. Environments & data
- **Local:** docker compose with PostgreSQL 15, a 3-node Redis 7 cluster and Redpanda, seeded with 1M players from `poc/server.py`'s generator (seed 7).
- **Staging:** 40M players with a **skewed** score distribution (Zipf-like, many low scores), 8 boards, and production-sized instances. T-002 and the NFR tests run here.
- **Data reset:** `make reset-local` truncates the schema and flushes Redis. The rebuild job restores boards from PostgreSQL.

## 4. Entry / exit criteria
- **Entry:**
  - the implementation-readiness gate is READY;
  - the feature is deployed to local or staging with the chaos hooks enabled;
  - test data is seeded.
- **Exit:**
  - all P0/P1 cases pass;
  - no open Sev-1 or Sev-2 defects;
  - every CRITICAL requirement has at least one passing case;
  - the benchmark SLOs pass;
  - the chaos suite shows zero mismatches.

## 5. Test cases
Only the first column defines the ID. The *Requirements* column feeds the traceability matrix (`tracker.py trace`).

| ID | Title | Requirements | Type | Priority | Preconditions | Steps | Expected result | Automated? | Status |
|----|-------|--------------|------|----------|---------------|-------|-----------------|------------|--------|
| TC-001 | Score applied from match.completed | FR-001 | Functional | P0 | player with season score 100 | publish event with delta 25 | season and all-time scores are 125 in PG and Redis | yes (integration) | Not run |
| TC-002 | Regional boards update | FR-008 | Functional | P1 | EU player | apply an event | global and EU boards change; NA and APAC unchanged | yes | Not run |
| TC-003 | Replay of an applied batch is ignored | FR-002 | Functional (positive) | P0 | batch applied | re-deliver the same 500 events | scores, versions and Redis unchanged | yes | Not run |
| TC-004 | Only redis_writer.lua writes Redis | NFR-006 | Static | P0 | — | lint rule over the code base | no ZADD/ZREM outside `redis_writer.lua`; no ZINCRBY | yes (CI lint) | Not run |
| TC-005 | Producer retry with a new event id is not double counted | FR-002 | Functional (negative) | P0 | event applied | publish the same match_id with a new event_id | applied once; second stored as a duplicate | yes | Not run |
| TC-006 | Implausible delta rejected | FR-003 | Functional | P0 | — | publish delta 900 000 | not applied; score_events row with status rejected and reason | yes | Not run |
| TC-007 | Timestamp bounds | FR-003, FR-002 | Boundary | P1 | — | completed_at at now+6 min, now−8 d, now−6 d (replay) | first two rejected; the 6-day replay is accepted | yes | Not run |
| TC-008 | Top 100 in rank order | FR-004 | Functional | P0 | 1 000 ranked players | GET top?n=100 | 100 entries, strictly ordered, ranks 1..100 | yes | Not run |
| TC-009 | Around-me window and edges | FR-005 | Functional | P0 | ranked players | request for rank 5 000, rank 3, an unranked player | 4 990–5 010 with me marked; 1–13 for rank 3; me = null when unranked | yes | Not run |
| TC-010 | Crash after commit at every point | NFR-006, FR-002 | Chaos (failure) | P0 | chaos hooks on | crash the worker after the PG commit (before/after the offset commit); crash the writer between ZADD and DELETE | Redis equals PG within 60 s; no rank ever older than PG | yes (chaos) | Not run |
| TC-011 | Redis failover with lost acknowledgements | NFR-006 | Chaos (failure) | P0 | cluster with replicas | drop acks, force failover under ingest | failover replay converges in ≤ 60 s; stale flag raised meanwhile | yes (chaos) | Not run |
| TC-012 | Rebuild drill | FR-013, NFR-007 | Recovery | P1 | 40M-entry board, live ingest | run rebuild | ≤ 30 min; reads uninterrupted; zero mismatches after the swap | yes (staging) | Not run |
| TC-013 | Removal racing an in-flight batch | FR-011, NFR-006 | Chaos (race) | P0 | player in top 100 | remove while a batch for that player is in flight | player never reappears on any board | yes (chaos) | Not run |
| TC-014 | Out-of-order and zombie writes | NFR-006 | Property | P0 | — | apply random permutations of versioned writes, including stale replays | final state equals the highest version for every player | yes (property) | Not run |
| TC-015 | Remove/restore authorisation and audit | FR-011, NFR-008 | Security | P0 | ops user with and without the role | remove, then restore, with and without a reason | without the role: 403; without a reason: 400; with both: effective ≤ 5 min and audited | yes | Not run |
| TC-016 | No PII in responses | NFR-009, FR-014 | Contract | P1 | — | contract test on every read endpoint | only handle, name, rank, score and stale fields | yes | Not run |
| TC-017 | Lag alert fires | NFR-011 | Operability | P1 | staging | pause the consumer for 90 s | alert within 1 min of lag > 5 s | yes | Not run |
| TC-018 | Tie-break order consistent | FR-007 | Property | P0 | — | random (score, reached_at, player) sets | Redis order equals PG snapshot order (score desc, reached_at asc, player_id desc) | yes (property) | Not run |
| TC-019 | Season rollover assignment | FR-009 | Functional | P0 | season ends Monday 00:00 UTC | events completed at 23:59:59 processed at 00:02 and at 00:07 | first counts toward the old season; second goes to the new season with status late_rollover | yes | Not run |
| TC-023 | Snapshot correct and immutable | FR-010 | Functional (positive) | P0 | season with removed players | run the season close | snapshot equals the PG board at the cut-off without removed players; checksum stored; S3 object locked | yes | Not run |
| TC-024 | Snapshot tampering and drift detected | FR-010 | Failure | P0 | snapshot produced | modify the object; inject a Redis mismatch before publishing | checksum mismatch detected; publishing blocked and on-call paged | yes | Not run |
| TC-031 | Snapshot excludes removed players and late events | FR-010, FR-011 | Functional (negative) | P0 | removed player in top 1 000; events completed before the cut-off but processed after the grace period | run the season close; restore the player afterwards | removed player absent; late events in the next season; restoring later does not change the locked snapshot | yes | Not run |
| TC-032 | Rebuild races a writer that has not seen the target yet | FR-013, NFR-006 | Chaos (race) | P0 | delay one writer's target refresh | rebuild while that writer applies newer versions | the barrier waits for every writer's acknowledgement; after the swap, zero mismatches | yes (chaos) | Not run |
| TC-025 | Score history for operators | FR-012 | Functional | P2 | applied and rejected events | GET history | events newest first with status and reason; cursor pagination | yes | Not run (post-launch) |
| TC-026 | Friends board and degraded mode | FR-006 | Functional | P2 | player with 30 friends | GET friends; then make profile time out | ranks 1–31; then degraded=true from cache | yes | Not run (post-launch) |

## 6. Non-functional tests
| ID | NFR | Scenario | Tool | Pass criterion |
|----|-----|----------|------|----------------|
| TC-020 | NFR-001 | event publish to rank visible, at 20k events/s | `bench.py` + probe consumer | p95 ≤ 2 s |
| TC-021 | NFR-002 | read mix 60 % top / 30 % around-me / 10 % friends at 60k/s | `bench.py http` (staging: k6) | p95 ≤ 50 ms, error rate ≤ 0.1 % |
| TC-022 | NFR-003 | 20k events/s for 1 h, then a 40k/s burst for 5 min | load generator + lag metric | lag ≤ 2 s p95; recovers within 1 min |
| TC-027 | NFR-004 | boards seeded with 40M entries | T-002 | memory within budget; latencies as in TC-021 |
| TC-028 | NFR-005 | availability over the canary month | SLO dashboard | ≥ 99.9 % |
| TC-029 | NFR-010 | itemised monthly cost | cost review | ≤ $6k/month |
| TC-030 | NFR-006 | full local end-to-end run | `logwatch.py --once --fail-on ERROR` | zero ERROR lines and no critical alerts |

## 7. Defect management
- **Sev-1:** wrong rank or score, or a snapshot error. Fix before any rollout step.
- **Sev-2:** SLO breach. Fix before the next canary step.
- **Sev-3:** degraded friends or history. Fix in the next sprint.
- Defects are filed as tracker tasks: `tracker.py add --type bug --reqs <ids>`.

## 8. Risks
- The proxy PoC is not production evidence. TC-021, TC-022 and TC-027 on staging are decisive.
- Chaos tests depend on the reliability of the fault-injection hooks, so the hooks need their own unit tests.
- The skewed score distribution must be realistic. Get it from the game-design simulation data (Q2).
