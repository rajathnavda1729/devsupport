<!-- devkit:doc type=adr v=1 -->
# ADR-0006: PostgreSQL truth with Redis read model using absolute re-asserted writes

**Status:** Accepted
**Date:** 2026-10-08 · **Scope:** feature `leaderboard` · **Deciders:** Leaderboard tech lead, Platform architect · **Tags:** ranking,redis,read-model,correctness
**Supersedes:** - · **Superseded by:** -

## Context
- Boards must serve top-100, around-me and friends at p95 ≤ 50 ms with 60k reads/s (NFR-002), with ranks fresh within ≤ 2 s (NFR-001) and never wrong (NFR-006, CRITICAL). PostgreSQL is the system of record (ADR-0001).
- Two challenge rounds rejected the earlier designs:
  - ADR-0003, Redis with an event-delta dual write: a crash after the PostgreSQL commit left Redis permanently wrong.
  - ADR-0005, PostgreSQL-only with bucket counts: hidden derived state, replica freshness, hot rows.
- This ADR adopts the steelman from the second review: option A′.

## Decision drivers
- Ranks that converge to the PostgreSQL truth within a bounded time after any failure (NFR-006).
- O(log n) reads without load on the system of record (NFR-002), and freshness ≤ 2 s (NFR-001).
- Reuse of the existing designs (HLD/LLD), to fit 6 weeks.

## Considered options
1. A″, as adopted after round 3: the PostgreSQL apply transaction also upserts `redis_dirty(player_id, version)`, a transactional outbox. A writer re-reads the current PostgreSQL rows and applies a **version-guarded Lua ZADD/ZREM** (compare-and-set on a monotonic `score_version`). The dirty row is deleted only if its version is unchanged (chosen).
2. A′: absolute ZADD from the after-commit `RETURNING` values, plus a 10 s repair queue (round-2 proposal; superseded by round 3 because of ordering races).
3. Redis with event deltas (ZINCRBY) and an apply-once ledger (ADR-0003, rejected).
4. PostgreSQL-only ranking with keyset seeks and bucket counts (ADR-0005, rejected).
5. Redis fed by CDC (Debezium). Same guarantees as option 1, but it adds infrastructure; deferred.

## Evaluation
- **Comparison:** see `../solutioning.md` §6. A 440, C 340, B 335; margin 22.7%. A is now A″ (the outbox); its score is unchanged, because the outbox adds delivery work (still 4) and keeps correctness at 4.
- **Sensitivity:** robust. `devkit review matrix leaderboard` shows the weights robust under ±20% and no decisive single score under ±1.
- **Evidence quality:**
  - Read and ingest latency are *measured* with the proxy PoC (`../../04-quality/benchmarks/REPORT.md`): around-me p95 13.6 ms, top-100 4.0 ms.
  - Convergence of absolute writes rests on *reasoning*: every value written is a committed PostgreSQL value, and ZADD is idempotent. It is verified by chaos test TC-010.
  - Redis capacity at 40M entries and 80k ZADD/s is an *assumption*, to be measured in T-002.
- **Reversibility:** two-way door. Redis is derived. Removing it means serving reads from PostgreSQL (B), using the T-002 data; switching to the CDC variant replaces only the writer.
- **Pre-mortem:** a year on, this failed because:
  1. The repair queue backed up during a Redis incident, and ranks stayed stale for longer than 60 s. Mitigation: the `stale` flag is shown to players, an alert fires on queue depth, and a full rebuild runs if the backlog exceeds 1M.
  2. A single global-board key hit the single-thread CPU limit at peak. Mitigation: a dedicated shard for global boards, replica reads, and a 1 s top-100 cache, gated by T-002.
  3. The tie-break encoding exceeded 53 bits. Mitigation: bounded encoding (LLD §7), overflow rejection and alerts, and property tests.
- **Challenge:** decision-challenger round 3, *SOUND WITH MITIGATIONS*. Strongest objection: "every value is a committed PostgreSQL value" is not "every value is the latest". Unversioned absolute writes let the repair queue, a zombie consumer, an in-flight batch after an operator ZREM, or a rebuild RENAME land an *older* value, which is wrong, not stale, for up to an hour. Other points: the repair enqueue was not atomic with the commit; acknowledged writes can be lost on failover; and the stale-flag and revisit gates were looser than NFR-006, NFR-001 and NFR-010. Response: adopted the outbox with version-guarded Lua writes (option 1), versioned removal tombstones, a stale flag driven by outbox age, a rebuild that replays dirty rows with version > snapshot before RENAME, and a failover replay of the last 15 minutes of updated rows. Gates are aligned with the NFRs below.

## Decision
We will:
- in the apply transaction (ADR-0004), increment `scores.version` and upsert `redis_dirty(player_id, version)` for every touched player;
- run a per-partition Redis writer that drains `redis_dirty`. For each player it re-reads the current rows (score, reached_at, region, removed, version) and runs one Lua script per player across all their boards (hash-tagged keys). The script ZADDs absolute values, or ZREMs when `removed`, **only if** the stored version is lower;
- delete the dirty row only if its version is unchanged;
- make removal and restore bump the version, so they use the same path and in-flight batches cannot resurrect a cheater;
- set the `stale` flag when the oldest dirty row is more than 60 s old; that is an incident, not normal operation;
- rebuild as: snapshot, then load the shadow key, then replay dirty rows with version > snapshot, then RENAME (with `lazyfree-lazy-server-del yes`);
- after a Redis failover, mark boards stale and re-enqueue players updated in the last 15 minutes;
- run an hourly reconcile as a safety net, not as the correctness mechanism.

## Consequences
- **Positive:** no crash window, because the outbox is written in the same transaction; no ordering race, because writes are versioned; one path for scores, removal and restore; a stale signal that maps directly onto NFR-006; no new infrastructure.
- **Negative / accepted trade-offs:** a second datastore (about $2.5k/month); a version column and an outbox table; a Lua script per player write; more delivery work (about 1 extra week, absorbed by rescoping FR-014 and FR-006 to later milestones).
- **Follow-ups:** T-002 Redis capacity, including Lua at 80k writes/s; the chaos suite (offset committed then crash, failover with lost acknowledgements, removal racing a batch, rebuild under ingest); the all-time score distribution for the tie-break bit budget.

## Compliance & evidence
- No ZADD or ZREM outside `redis_writer.lua`, and no ZINCRBY anywhere (lint rule).
- The chaos suite TC-010, TC-011, TC-013 and TC-014 asserts zero rank mismatches against PostgreSQL within 60 s after each fault.

## Revisit when
- T-002 fails its gates: Redis p95 > 5 ms for rank queries (leaving the rest of the 50 ms NFR-002 budget for the API), single-key CPU > 70%, or end-to-end freshness > 2 s p95 (NFR-001).
- A rebuild of a 40M-entry board takes > 30 min (NFR-007).
- Total leaderboard infrastructure cost exceeds $6k/month (NFR-010).
- Any staleness over 60 s is handled as an incident with a postmortem, not as a revisit trigger.

## Related
FR-002, FR-004, FR-005, FR-011, FR-013, NFR-001, NFR-002, NFR-006, NFR-007; ADR-0001, ADR-0002, ADR-0003 (rejected), ADR-0004, ADR-0005 (rejected).
