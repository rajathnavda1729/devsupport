<!-- devkit:doc type=adr v=1 -->
# ADR-0003: Redis sorted sets as the derived ranking store with PostgreSQL ledger as source of truth

**Status:** Rejected
**Date:** 2026-10-08 · **Scope:** feature `leaderboard` · **Deciders:** Leaderboard tech lead, Platform architect · **Tags:** ranking,redis,read-model
**Supersedes:** - · **Superseded by:** -

## Context
Players need top-100, around-me (rank ± 10) and friends boards at p95 ≤ 50 ms with 60k reads/s (NFR-002). Boards are 5M entries per season and 40M all-time (NFR-004). Ranks must be visible ≤ 2 s after a match (NFR-001). ADR-0001 makes PostgreSQL the system of record, and requires derived stores to be rebuildable. Ranks must never be wrong after a failure (NFR-006, CRITICAL).

## Decision drivers
- O(log n) rank of an arbitrary player (around-me) on boards of 5M–40M entries.
- Correctness anchored in the system of record (ADR-0001, NFR-006).
- Delivery in 6 weeks with 3 engineers.

## Considered options
1. PostgreSQL ledger + Redis sorted sets as the derived ranking store (chosen).
2. PostgreSQL only, ranking via indexed COUNT/OFFSET plus caching.
3. A custom in-memory ranking service with order-statistic trees.

## Evaluation
- **Comparison:** see `../solutioning.md` §6. A 440 · B 375 · C 340.
- **Sensitivity:** robust. `devkit review matrix leaderboard`: margin 14.8%, and the winner is unchanged under ±20% on every weight.
- **Evidence quality:** around-me latency is *measured* with a proxy PoC (`../../04-quality/benchmarks/REPORT.md`: A p95 13.6 ms against B 1 310 ms at 1M rows). Redis O(log N) complexity is *external* (redis.io docs). Redis latency at 40M entries is *assumption*, not yet measured: follow-up T-002.
- **Reversibility:** two-way door. Redis is a derived store, so swapping it for another ranking engine means rebuilding from the PostgreSQL ledger (NFR-007, ≤ 30 min) and changing the read adapter.
- **Pre-mortem:** a year on, this failed because:
  1. Redis and PostgreSQL silently diverged after failovers. Mitigation: a reconciliation job every 5 min, plus a stale flag.
  2. Memory grew past budget as all-time boards reached 100M+. Mitigation: a memory alert at 70%, and capping all-time boards to active players.
  3. The composite score encoding overflowed double precision and broke tie order. Mitigation: a bounded encoding with property tests (LLD §7).
- **Challenge:** decision-challenger, *SOUND WITH MITIGATIONS*. Strongest objection: the dual write loses updates permanently, leaving ranks **wrong**, not just stale. A crash after the PostgreSQL commit but before ZADD means the redelivered events are deduplicated and Redis is never written, and asynchronous Redis failover drops acknowledged writes. The challenger also showed that the Option B baseline was a strawman (OFFSET). Response: re-ran a fair Option B. It meets NFR-002 with no dual write, so this ADR is **rejected** in favour of ADR-0005, and kept as the documented fallback.

## Decision
We will:
- keep each player's scores and the applied-events ledger in PostgreSQL (source of truth);
- maintain one Redis sorted set per board (`lb:{scope}:{period}`), updated after each committed PostgreSQL transaction;
- serve top-N, around-me and friends reads from Redis;
- rebuild or reconcile Redis from PostgreSQL. Redis is never the only copy of a score.

## Consequences
- **Positive:** O(log n) reads for every board view; a simple, well-known operational model; full rebuild capability.
- **Negative / accepted trade-offs:** a second datastore to run (about $2.5k/month); a dual write that needs reconciliation; Redis can briefly lag PostgreSQL, so reads may be stale for up to 60 s (allowed by NFR-006).
- **Follow-ups:** T-002 Redis 40M benchmark on staging; reconciliation job; memory alerting.

## Compliance & evidence
- No code path writes a score to Redis without a committed PostgreSQL transaction. Checked by code review and the integration test TC-004.
- The rebuild command exists and is exercised in the rebuild drill (TC-012).

## Revisit when
- All-time board size exceeds 150M entries.
- Redis cost exceeds $5k/month.
- The reconciliation job finds more than 0.01% drift in a week.

## Related
Rejected 2026-10-08 after the decision-challenger review and the fair Option B PoC. See ADR-0005 and solutioning §6–§9.

FR-002, FR-004, FR-005, FR-013, NFR-001, NFR-002, NFR-004, NFR-006, NFR-007; ADR-0001, ADR-0002, ADR-0004.
