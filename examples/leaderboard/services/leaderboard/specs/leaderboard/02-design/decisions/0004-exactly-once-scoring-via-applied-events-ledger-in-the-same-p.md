<!-- devkit:doc type=adr v=1 -->
# ADR-0004: Exactly-once scoring via applied-events ledger in the same PostgreSQL transaction

**Status:** Accepted
**Date:** 2026-10-08 · **Scope:** feature `leaderboard` · **Deciders:** Leaderboard tech lead · **Tags:** idempotency,kafka,correctness
**Supersedes:** - · **Superseded by:** -

## Context
Kafka delivers `match.completed` at least once (ADR-0002). Consumer crashes, rebalances and replays will redeliver events. FR-002 (CRITICAL) requires each event to affect scores exactly once, because double counting silently corrupts ranks and season rewards (FR-010).

## Decision drivers
- Zero double-applied or lost events (FR-002, NFR-006).
- Throughput of 20k events/s (NFR-003).
- No new infrastructure (6-week constraint).

## Considered options
1. A permanent `score_events(player_id, match_id, …)` table with `UNIQUE(player_id, match_id, completed_month)`, written in the same transaction as the score update; offsets committed after the commit (chosen, revised after the challenge).
2. A short-retention `applied_events(event_id)` ledger in the same transaction (the original proposal).
3. Kafka transactions with exactly-once semantics end to end.
4. Deduplication in Redis with `SETNX` on event_id and a TTL.

## Evaluation
- **Comparison:**
  - Option 1 deduplicates on the natural key, so it also catches producer retries that mint a new event_id. It is permanent, so it also serves FR-012 history and score recomputation.
  - Option 2 misses producer duplicates. Its 14-day retention breaks FR-012 and rebuilds.
  - Option 3 does not cover the PostgreSQL side effect.
  - Option 4 is not atomic with the score write.
- **Sensitivity:** not a weighted choice. Option 1 is the only option that is atomic, catches producer duplicates and keeps history, so it is a correctness requirement.
- **Evidence quality:**
  - Atomicity comes from PostgreSQL transaction semantics (*external*: PostgreSQL docs).
  - Dedupe behaviour is *measured* in the PoC: duplicates are ignored, see `logs/poc-memory.log`.
  - Storage is *estimated*. Average volume is about 5M DAU × ~10 matches ≈ 50M rows/day × ~120 B ≈ 6 GB/day, about 180 GB/month. Peaks of 20k/s are event-only.
  - Throughput at 20k/s is an *assumption*, to be verified in T-011.
- **Reversibility:** two-way door for the mechanism. The table becomes the score history of record, so its schema is costly to change later.
- **Pre-mortem:** a year on, this failed because:
  1. Storage cost grew. Mitigation: monthly partitions by `completed_at`; partitions older than 13 months go to cold storage (Parquet on S3).
  2. Insert throughput fell short at 20k/s. Mitigation: 500-event batches with `INSERT … ON CONFLICT DO NOTHING RETURNING`, on a dedicated PostgreSQL instance for the `leaderboard` schema if T-011 shows contention with other services.
  3. game-api reused `match_id` across players incorrectly. Mitigation: the key includes `player_id`, and a contract test with game-api.
- **Challenge:** decision-challenger, *SOUND WITH MITIGATIONS*. Strongest objection: an event_id-only ledger with 14-day retention could not cover producer retries, FR-012 history or rebuilds, and its storage maths contradicted the revisit trigger. Response: adopted the challenger's steelman of a permanent `score_events` keyed by `(player_id, match_id)`, partitioned by `completed_at` month, with storage re-estimated above.

## Decision
We will:
- insert each event into `score_events` (player_id, match_id, delta, status, reason, completed_at) with `ON CONFLICT (player_id, match_id, completed_month) DO NOTHING RETURNING`;
- apply score deltas for the newly inserted rows, increment `scores.version` and upsert the `redis_dirty` outbox (ADR-0006), all in one PostgreSQL transaction of up to 500 events;
- record rejected events (FR-003) in the same table with `status = rejected`;
- commit Kafka offsets only after the transaction commits.

## Consequences
- **Positive:** exactly-once effect, including producer retries; permanent per-event history for FR-012, audit and recomputation; one mechanism instead of a ledger plus a history table.
- **Negative / accepted trade-offs:** about 180 GB/month of storage; monthly partition maintenance; a write per event on the system of record.
- **Follow-ups:** T-011 ingest throughput test; confirm with game-api that match_id is stable across retries; archival job.

## Compliance & evidence
- Integration test TC-003 replays a batch twice and asserts the scores are unchanged.
- Chaos test TC-010 kills the consumer between the transaction commit and the offset commit.

## Revisit when
- Ingest p95 lag exceeds 2 s at 20k events/s.
- `score_events` storage exceeds 3 TB.

## Related
FR-001, FR-002, NFR-003, NFR-006; ADR-0002, ADR-0003.
