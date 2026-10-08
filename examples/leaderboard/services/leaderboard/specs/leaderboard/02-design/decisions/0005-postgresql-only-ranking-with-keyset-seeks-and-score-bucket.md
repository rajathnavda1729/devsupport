<!-- devkit:doc type=adr v=1 -->
# ADR-0005: PostgreSQL-only ranking with keyset seeks and score-bucket counts

**Status:** Rejected
**Date:** 2026-10-08 · **Scope:** feature `leaderboard` · **Deciders:** Leaderboard tech lead, Platform architect · **Tags:** ranking,postgresql,read-model
**Supersedes:** - · **Superseded by:** -

## Context
- Players need top-100, around-me (rank ± 10) and friends boards at p95 ≤ 50 ms with 60k reads/s (NFR-002), on boards of 5M (season) and 40M (all-time) entries (NFR-004).
- Ranks must never be wrong after failures (NFR-006, CRITICAL). ADR-0001 makes PostgreSQL the system of record.
- The decision-challenger review of ADR-0003 (Redis) found a dual-write correctness hole, and showed that our first PostgreSQL baseline (OFFSET) was a strawman.

## Decision drivers
- Correctness by construction for FR-002 and NFR-006 (CRITICAL).
- An around-me read in O(log n) (NFR-002).
- Delivery in 6 weeks; the fewest moving parts.

## Considered options
1. PostgreSQL only: keyset seeks for neighbours, score-bucket counts for the rank number, read replicas, a 1 s top-100 cache, on a dedicated cluster (chosen).
2. A PostgreSQL ledger plus Redis sorted sets as a derived ranking store (ADR-0003, rejected; kept as the fallback).
3. A custom in-memory ranking service.

## Evaluation
- **Comparison:** see `../solutioning.md` §6. B 440 · A 415 · C 340, a close call with a 5.7% margin.
- **Sensitivity:** robust. `devkit review matrix leaderboard`: the winner is unchanged under ±20% on every weight. Because the margin is narrow, a **Fallback** is defined (solutioning §9).
- **Evidence quality:**
  - *Measured* with the proxy PoC at 1M rows: around-me p95 15.4 ms (keyset) against 13.6 ms (A); identical results to the reference for 8 out of 8 sampled players (`../../04-quality/benchmarks/REPORT.md`).
  - *Not yet measured*, and decisive: PostgreSQL at 60k reads/s plus 20k writes/s with 40M rows (T-002).
  - *External*: B-tree keyset seeks are O(log n) (PostgreSQL docs).
- **Reversibility:** two-way door. Ranking sits behind the `RankingStore` interface (LLD §2). Adding Redis (ADR-0003) later is additive: a new adapter plus a backfill from PostgreSQL.
- **Pre-mortem:** a year on, this failed because:
  1. Read load saturated the replicas during live events. Mitigation: the top-100 cache, replica autoscaling, and the Redis fallback with a T-002 gate.
  2. Hot `score_buckets` rows serialised writes at 20k/s. Mitigation: aggregate the bucket deltas per batch and order the updates to avoid deadlocks.
  3. The bucket SUM grew slow on large all-time boards with millions of distinct scores. Mitigation: two-level buckets (coarse score/1000 plus fine), measured at 40M rows in T-002.
- **Challenge:** decision-challenger, *RECONSIDER*. Strongest objection: `score_buckets` is an undeclared derived read model, kept by application code across removal, restore, rollover and region moves. Drift gives *wrong* ranks with no reconciliation, and replica reads span several snapshots, so "correct by construction" does not hold. The objection also raised hot bucket rows, replica lag against NFR-001's 2 s, skewed ties and replica query load. Response: accepted. Re-scored in solutioning §6, and this ADR is **rejected** in favour of ADR-0006 (A′).

## Decision
We will store scores, score events and score-bucket counts in a dedicated PostgreSQL 15 cluster for the `leaderboard` schema (complying with ADR-0001). Reads are served from read replicas:
- top-N by index scan;
- the around-me neighbours by keyset seeks;
- the rank number from two-level bucket counts.

Score and bucket updates happen in the same transaction as the score event (ADR-0004).

## Consequences
- **Positive:** no second store that can disagree; native tie-break ordering; no rebuild or reconciliation of derived data; simple operations.
- **Negative / accepted trade-offs:** higher PostgreSQL load and cost (about $3k/month for a dedicated primary plus 3 replicas); write contention on bucket rows; replica lag means reads can be stale for seconds (allowed by NFR-006).
- **Follow-ups:** T-002 staging load test, which gates the decision; the bucket design spike; the replica-lag stale flag.

## Compliance & evidence
- Every rank query goes through `RankingStore`. No OFFSET in rank queries; this is linted in code review and covered by query tests.
- `score_buckets` is updated only inside the apply transaction (integration test TC-005).

## Revisit when
- T-002 fails its gate: p95 > 50 ms or replica lag > 5 s at target load. Then switch on the ADR-0003 fallback.
- Read traffic exceeds 120k/s.

## Related
Rejected 2026-10-08 after the second decision-challenger review. See ADR-0006.

FR-002, FR-004, FR-005, FR-006, FR-007, NFR-002, NFR-004, NFR-006; ADR-0001, ADR-0003 (rejected, fallback), ADR-0004.
