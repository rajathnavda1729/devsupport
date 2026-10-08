<!-- devkit:doc type=solutioning v=1 -->
# Solutioning — Near-realtime Leaderboards

**Status:** Approved
**Feature:** `leaderboard` · **Updated:** 2026-10-08 · **Upstream:** `../01-requirements/requirements.md`, decision log

## 1. Decision context (existing ADRs)
Accepted decisions already recorded in this repo that bear on this feature. Find them with `python3 devkit/tools/adr.py search <keywords>`. Accepted ADRs are binding: either comply with one, or propose a superseding ADR and get approval.

| ADR | Title | Status | Impact (constrains / complies / supersedes / n.a.) | Notes |
|-----|-------|--------|----------------------------------------------------|-------|
| ADR-0001 | PostgreSQL as the system of record | Accepted | constrains | Scores and applied-event ledger live in PostgreSQL; any ranking store is a derived, rebuildable read model |
| ADR-0002 | Kafka for domain events | Accepted | complies | Consume `match.completed` (keyed by player_id); 7-day retention bounds replay-based recovery |

## 2. Architecturally significant requirements (drivers)
| ID | Driver | Why it drives the design |
|----|--------|--------------------------|
| NFR-002 | Reads p95 ≤ 50 ms at 60k/s incl. around-me on 5M–40M entries | Rank-of-arbitrary-player must be O(log n), not a scan |
| NFR-001 | Rank visible ≤ 2 s after the match | Rules out batch recomputation; needs streaming updates |
| FR-002 / NFR-006 | Exactly-once effect, never wrong after failure (CRITICAL) | Needs idempotent apply in the system of record plus reconciliation of derived boards |
| FR-010 | Immutable season snapshot for rewards (CRITICAL) | Snapshot must come from the system of record at a fixed cut-off |
| NFR-003 | 20k events/s sustained | Write path must batch and partition |
| ADR-0001 | PostgreSQL system of record | Ranking store must be rebuildable from PostgreSQL |
| Constraint | 6 weeks, 3 engineers | Favour managed, well-known components over custom engines |

## 3. Problem characteristics
- Read/write ratio about 3:1 at peak (60k reads/s, 20k writes/s), and spiky during live events.
- Board sizes: 5M per season board, 40M all-time. There are 8 boards (global + 3 regions × season/all-time).
- The rank query for an arbitrary player is the hard part. Top-N alone is easy to cache.
- Consistency: staleness of ≤ 60 s is acceptable, incorrect ranks are not (NFR-006).
- Data is small per entry (player id, score, reached_at): about 40M × ~100 B ≈ 4 GB per all-time board in memory.

## 4. Candidate design patterns
Pulled from `devkit/knowledge/design-patterns.md`. Reject explicitly — a rejected pattern with a reason is as valuable as an adopted one.

| Pattern | Problem signal it addresses | Fit (✅ adopt / 🤔 maybe / ❌ reject) | Reason | Requirements served |
|---------|-----------------------------|----------------------------------------|--------|---------------------|
| CQRS / materialized view | Read model (rank) differs wildly from write model (score ledger) | ✅ adopt | PostgreSQL holds truth; ranking index is a derived read model | NFR-002, ADR-0001 |
| Idempotent receiver (idempotency key) | At-least-once Kafka delivery, replays | ✅ adopt | `applied_events(event_id)` unique insert in the same transaction as the score update | FR-002 |
| Competing consumers + partitioning | 20k events/s | ✅ adopt | Kafka partitions by player_id give per-player ordering and horizontal scale | NFR-003 |
| Cache-aside | Hot, identical top-100 reads | ✅ adopt | 1 s TTL per board absorbs most of the 60k/s | NFR-002 |
| Circuit breaker + fallback | Friends list from profile service | ✅ adopt | Friends board degrades to cached friends list if profile is slow | FR-006, NFR-005 |
| Outbox to derived store + versioned writes | Several writers update the derived ranking store | ✅ adopt | Closes the crash window and the ordering races found in round 3 (ADR-0006) | NFR-006, FR-011 |
| Reconciliation (anti-entropy) job | Derived store can drift after failures | ✅ adopt | Periodic compare of ranking store vs PostgreSQL; repair or rebuild | NFR-006 |
| Event sourcing | Full history | ❌ reject | Kafka retention is 7 days and ADR-0001 makes PostgreSQL the SoR; the applied-events ledger gives the audit we need | — |
| Saga | Multi-service transaction | ❌ reject | Single service owns the write; no cross-service transaction | — |
| Sharding the ranking store by player | Data beyond one node | ❌ reject | Breaks global rank queries; 4 GB per board fits one node — revisit at 10× | NFR-004 |
| Transactional outbox | Publish snapshot event reliably | 🤔 maybe | Useful if rewards consumes a `season.closed` event; decide in LLD | FR-010 |

## 5. Solution options
### Option A — PostgreSQL truth + Redis read model via transactional outbox and versioned writes (A″)
- **Summary:**
  - The Kafka consumer applies each batch to PostgreSQL in one transaction: `score_events` dedupe plus the score upsert (ADR-0004).
  - It then writes the **absolute** current score from PostgreSQL to Redis sorted sets (ZADD, never ZINCRBY) for *every* player in the batch, **including redelivered duplicates**. A crash between the PostgreSQL commit and the Redis write therefore converges on the next delivery.
  - Redis is written only by an outbox writer: the apply transaction upserts `redis_dirty(player, version)`, and the writer re-reads PostgreSQL and applies **version-guarded** Lua writes, so no older value can land last (round 3). A full reconcile runs hourly as a safety net, and a rebuild comes from PostgreSQL.
  - Reads come from Redis.
  - *Revised after two decision-challenger reviews:* the original A had a dual-write hole that left ranks wrong.
- **Patterns used:** CQRS, idempotent receiver, competing consumers, cache-aside, reconciliation, idempotent absolute writes.
- **Pros:** O(log n) rank and range reads with no load on PostgreSQL; freshness bounded by the commit plus the outbox poll (200 ms); no crash window, because the outbox is in the apply transaction; simple to fall back on.
- **Cons:** a second datastore to run; the tie-break needs a 53-bit composite encoding; a reconcile job is required.
- **Risks:** memory at 40M+ entries (about 9–12 GB with rebuild headroom), to be sized in T-002; a hot key on the global board, mitigated by replica reads and the top-100 cache.
- **Rough cost / effort:** about $2.5k/month for Redis, plus the PostgreSQL cluster also needed by B (itemised in T-002); 5–6 weeks.

### Option B — PostgreSQL only (keyset seeks + score-bucket counts)
- **Summary:**
  - Scores live in PostgreSQL with an index on (board, score desc, reached_at). Top-N is an index scan.
  - The neighbours for around-me come from **keyset seeks** in both directions: O(log n).
  - The rank number = the sum of a `score_buckets` table (count per score, updated in the same transaction) for scores above the player's, plus same-score players who reached it earlier.
  - Reads are served from PostgreSQL read replicas, with a 1 s top-100 cache.
  - *Revised after the decision-challenger review:* the first version used COUNT/OFFSET, which was a strawman.
- **Patterns used:** cache-aside, idempotent receiver, read replicas, materialized counts.
- **Pros:**
  - One datastore, with strong consistency on the primary.
  - **No dual write**, so NFR-006 holds by construction.
  - No rebuild or reconciliation of a second store.
  - Native tie-break ordering, with no 53-bit encoding.
- **Cons:**
  - 60k reads/s land on the PostgreSQL cluster, which needs about 3 replicas.
  - Bucket rows are hot on writes at 20k events/s.
  - The bucket SUM is O(distinct scores), so it grows on large all-time boards. It needs two-level buckets.
- **Risks:**
  - Load on the shared system of record. Mitigation: a dedicated PostgreSQL cluster for the `leaderboard` schema, which still complies with ADR-0001.
  - Write contention on hot bucket rows. Mitigation: aggregate bucket deltas per batch.
- **Second challenge (ADR-0005, verdict RECONSIDER):**
  - `score_buckets` is hidden derived state. Drift on removal, restore, rollover or region move gives *wrong* ranks.
  - Statements on a replica run in separate snapshots, so the rank number and the neighbours can disagree.
  - About 8–16 bucket-row updates per event cause hot-row contention.
  - Replica lag competes with NFR-001's 2 s.
  - With skewed score distributions, the tie COUNT becomes O(ties).
  - About 5–6 queries per read, so 60k reads/s is about 100k+ queries/s on the replicas.
- **Rough cost / effort:** about $3k/month (a dedicated primary plus 3 replicas); 4–5 weeks.

### Option C — Custom in-memory ranking service
- **Summary:** Purpose-built service holding order-statistic trees per board, fed from Kafka, snapshotting to PostgreSQL.
- **Patterns used:** CQRS, event-driven, reconciliation.
- **Pros:** Fastest possible; full control of tie-breaking and memory layout.
- **Cons:** Build and operate a stateful, replicated in-memory service — failover, rebalancing and snapshots are all ours.
- **Risks:** Will not fit 6 weeks; on-call burden; bus factor.
- **Rough cost / effort:** ~$2k/month; 10+ weeks.

## 6. Comparison matrix
Weights come from the drivers (sum = 100). Score 1–5. Weighted = weight × score.

| Criterion (linked req) | Weight | Option A | Option B | Option C |
|------------------------|--------|----------|----------|----------|
| Read latency incl. around-me (NFR-002) | 25 | 5 (125) | 3 (75) | 5 (125) |
| Correctness and recovery (FR-002, NFR-006) | 25 | 4 (100) | 4 (100) | 3 (75) |
| Freshness (NFR-001) | 15 | 5 (75) | 3 (45) | 5 (75) |
| Delivery in 6 weeks (constraint) | 15 | 4 (60) | 3 (45) | 1 (15) |
| Rebuild time (NFR-007) | 10 | 4 (40) | 4 (40) | 3 (30) |
| Operability and cost (NFR-010) | 10 | 4 (40) | 3 (30) | 2 (20) |
| **Total** | **100** | **440** | **335** | **340** |

Scoring history. Every change is driven by a decision-challenger review and the evidence it called for:
- **Round 1:**
  - B read latency 1 → 4: the OFFSET PoC was a strawman, and the keyset version meets NFR-002.
  - A correctness 4 → 3: the dual-write hole.
- **Round 2:**
  - B correctness 5 → 4: hidden derived bucket state, and snapshot skew on replicas.
  - B read latency 4 → 3: about 5–6 queries per read on the replicas.
  - B freshness 5 → 3: replica lag against the 2 s target.
  - B delivery 4 → 3: striped and two-level buckets, plus handling skewed ties.
  - A becomes A′ with absolute, re-asserted writes, so its correctness goes 3 → 4.
- **Round 3:** A′ becomes A″, with a transactional outbox and version-guarded writes to close the ordering races. Correctness stays at 4 and delivery stays at 4, with about 1 extra week absorbed by the re-plan.

Each decisive score is backed by the evidence in §8 and the challenge records in ADR-0003, ADR-0005 and ADR-0006.

## 7. Industry benchmarks & references
- Redis sorted sets: ZADD, ZREVRANK and ZRANGE are O(log N) (+M returned). Source: redis.io command docs (external, unverified for our hardware).
- Leaderboards on sorted sets are a widely documented reference pattern, e.g. the AWS ElastiCache leaderboard guide (external).
- PostgreSQL `OFFSET n` must read and discard n rows, so around-me via OFFSET is O(rank). Source: PostgreSQL docs, LIMIT/OFFSET (external).

## 8. Proof-of-concept benchmark
Plan for measuring the options we cannot decide on paper. Results stored under `benchmarks/` via `devkit/tools/bench.py`.

Proxy PoC (`services/leaderboard/poc/server.py`), 1M players on a laptop. An in-memory ordered index stands in for Redis sorted sets (A), and indexed SQLite with COUNT/OFFSET stands in for PostgreSQL ranking (B). These are proxies, not the real stores. They show algorithmic behaviour, not production latency.

| Experiment | Option(s) | Command / endpoint | Metric | Pass criterion | Result |
|------------|-----------|--------------------|--------|----------------|--------|
| around-me, random players | A, B (naive), B (keyset) | `GET /boards/global/around/p{randint}` c=8 | p95 | ≤ 50 ms (NFR-002) | A 13.6 ms ✅ · B naive OFFSET 1 310 ms ❌ · **B keyset 15.4 ms ✅** (`04-quality/benchmarks/REPORT.md`) |
| top-100 | A, B | `GET /boards/global/top?n=100` c=8 | p95 | ≤ 50 ms | A 4.0 ms ✅ · B 8.1 ms ✅ · B keyset 12.4 ms ✅ |
| ingest unique events | A, B | `POST /events` with `{uuid}` ids, c=8 | p95 | ≤ 50 ms | A 18.1 ms ✅ · B 6.1 ms ✅ · B keyset incl. bucket update 8.3 ms ✅ (A proxy is O(n) list insert; Redis is O(log n)) |
| correctness cross-check | A vs B keyset | same seed, 8 sampled players, k=10 | identical responses | 8/8 | 8/8 identical ✅ |
| PostgreSQL at 60k reads/s + 20k writes/s, 40M rows | B | load test on staging PostgreSQL with 3 replicas | p95 + replica lag | ≤ 50 ms, lag ≤ 5 s | not run — needs staging (task T-002); decisive for B |
| Redis at 40M entries | A | redis-benchmark on staging | p95 ZREVRANK | ≤ 5 ms | not run — needs staging Redis (task T-002) |

## 9. Recommendation
We choose Option A (A″): PostgreSQL as the source of truth, and Redis as a read model fed by a transactional outbox with version-guarded writes (ADR-0006).
- After three challenge rounds, A″ is the only option that meets read latency and freshness without hot-row contention on the system of record.
- Its correctness rests on PostgreSQL (ADR-0001, ADR-0004). Every Redis value is a version-guarded copy of committed PostgreSQL state, so it is never wrong, only briefly stale. Staleness is visible through the outbox-age stale flag (≤ 60 s, NFR-006).
- B was a serious contender, but its "correct by construction" claim did not survive the review: its bucket counts are derived state too.

We accept the cost of a second datastore and the reconcile machinery.

**Fallback:** if T-002 shows a single Redis key cannot sustain 80k ZADD/s plus 60k reads/s, split the hot global boards onto a dedicated shard and serve around-me from replicas. If that also fails, re-evaluate B with striped buckets using the T-002 data.

## 10. New decisions (ADRs written for this feature)
| ADR | Decision | Status | Supersedes |
|-----|----------|--------|------------|
| ADR-0003 | Redis sorted sets as the derived ranking store | Rejected (after challenge: dual-write correctness hole; fair Option B meets NFR-002) | - |
| ADR-0004 | Exactly-once scoring via a permanent score-events table keyed by (player_id, match_id), same transaction as the score update | Accepted | - |
| ADR-0005 | PostgreSQL-only ranking with keyset seeks and score-bucket counts | Rejected (second challenge: hidden derived bucket state, replica freshness, hot rows) | - |
| ADR-0006 | PostgreSQL truth + Redis read model: transactional outbox and version-guarded writes (round-3 mitigations) | Accepted | - |
