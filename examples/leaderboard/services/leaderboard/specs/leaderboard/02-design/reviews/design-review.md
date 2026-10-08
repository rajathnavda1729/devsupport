<!-- devkit:doc type=design-review v=1 -->
# Design Review — Near-realtime Leaderboards

**Status:** Approved
**Feature:** `leaderboard` · **Updated:** 2026-10-08 · **Upstream:** `../solutioning.md`, `../hld.md`, `../lld.md`, decision log

## 1. Verdict
**APPROVE** (re-review, round 3). The HLD and LLD implement ADR-0006 and ADR-0004 consistently throughout, and I found no leftovers from ADR-0003 or ADR-0005. All blocking findings are fixed, B1–B10 alike:
- **B9:** the rebuild now uses a barrier (LLD §6 Rebuild steps 1–5): writers acknowledge in `rebuild_targets_ack`, the shadow load runs, a catch-up re-stream since `started_at − 1 s` follows, and the dual-written keys are swapped.
- **B10:** failover detection now sets `redis_health.stale_until`, and the replay bumps versions (LLD §6 Redis failover).

The round-2 non-blocking items N2, N3, N5, N11 and N12 are resolved. N4, N7 and N9 remain open: none is blocking, and they can be tracked as tasks. Approval of the documents is the user's call; this review stays Draft.

## 2. Coverage summary
| Check | Result |
|-------|--------|
| Must FRs mapped to components (HLD) and modules/APIs (LLD) | 11/11: FR-001–005, 007–011 and 013 each map to an HLD §4 component and an LLD §2 module or §3 API. FR-008's region source is still open (N4, non-blocking) |
| NFRs with tactic + verification | 11/11 (HLD §9) |
| CRITICAL requirements with a guard | 3/3. FR-002: HLD §10 and LLD §6. FR-010: HLD §10 and LLD §6 season close. NFR-006: HLD §10 and LLD §6 and §9 (rebuild barrier, failover stale and replay) |
| Accepted ADRs complied with (or superseded with approval) | 4/4 |

## 3. Blocking findings
| # | Artifact § | Finding | Requirement / ADR | Suggested fix | Resolved |
|---|------------|---------|-------------------|---------------|----------|
| B1 | LLD §6 Apply batch | The outbox write ran after `COMMIT`. **Re-review:** steps 2–4 (events, scores, `players_lb.version + 1`, `redis_dirty` upsert) now come before the single `COMMIT` in step 5, and the offsets are committed in step 6. | ADR-0004, ADR-0006, FR-002, NFR-006 | Reorder into one transaction | yes |
| B2 | HLD §1/§4/§8/§9/§12; LLD §1/§2 | Dual-write leftovers from A/A′ (ingest and ops writing Redis, `redis_sync.py`, the repair queue). **Re-review:** gone. HLD §1 says the ingest worker "never writes to Redis". In HLD §4 and §8, only the outbox writer and jobs connect to Redis. LLD §1 adds `writer/`, and LLD §2 splits Redis access into `RankingWriter` and `RankingReader`. | ADR-0006 Compliance; ADR-0003 (Rejected) | Remove the direct writes | yes |
| B3 | LLD §6 Removal | Removal used a direct, unversioned ZREM, and restore was not specified. **Re-review:** removal and restore are one transaction (removed flag, version bump, `redis_dirty`, `operator_actions`), and the writer tombstones or re-adds the player. | ADR-0006 bullet 4, FR-011 | Route both through the outbox | yes |
| B4 | LLD §4, HLD §6 | Five data-model gaps: no version or `updated_at`, `REDIS_DIRTY` missing, `APPLIED_EVENTS` still present, an ambiguous per-row version, and a partition key that does not work. **Re-review:** `players_lb(version, updated_at)` holds a single per-player version, `REDIS_DIRTY` is in the ER diagram with `part`, `APPLIED_EVENTS` is removed, and `score_events` is `PARTITION BY RANGE (completed_month)` with that column in the PK. | ADR-0004, ADR-0006, ADR-0001 | Fix the schema | yes |
| B5 | LLD §2/§4/§9/§10, HLD §6 | Lua across two shards plus a version hash in a different slot could not run. **Re-review:** each board has the pair `lb:{<board>}` and `lbv:{<board>}` sharing one hash tag, with one Lua CAS per board (LLD §7) on one Redis Cluster URL (LLD §10). The per-board fan-out and its convergence are covered in LLD §9. | ADR-0006 bullet 2, NFR-006 | Per-board guard in one slot | yes |
| B6 | HLD §6 | The stale flag came from the reconcile watermark. **Re-review:** it is now "oldest `redis_dirty` row older than 60 s" (HLD §6, LLD §10 `LB_STALE_AFTER_S`, LLD §11 metric). | ADR-0006 bullet 5, NFR-006 | Use outbox age | yes |
| B7 | LLD §6 Rebuild | There was no global version watermark, and dirty rows drained to the live key were missing from the shadow key. **Re-review:** dual-target writes go through `rebuild_targets` plus a CAS-guarded shadow load, followed by an atomic RENAME of both keys. The design works, apart from the hand-over race in B9. | ADR-0006 bullet 6, FR-013, NFR-006 | Dual-target writes during rebuild | yes |
| B8 | LLD §6 Season close, §7 | The snapshot included removed players, season assignment was undefined, the Redis comparison was missing, and the 24 h age rule rejected legitimate replays. **Re-review:** the snapshot uses `removed = false` (step 3) and compares with Redis (step 5). Event-time season assignment with `late_rollover` is in LLD §7. The age limit is 8 days, which exceeds the 7-day retention. | FR-010, FR-011, FR-002, A5, ADR-0002 | Specify season close | yes |
| B9 | LLD §6 Rebuild, step 1 and step 2; §9 | New. The design does not say how or when writers notice `rebuild_targets`. A writer that read the target list before step 1 committed, and applies version v3 after the shadow stream (step 2) has already read v2, writes only the live key, then deletes the dirty row. The shadow keeps v2. After the RENAME (step 4) the board shows an older value, which is *wrong*, not stale. The count-and-sample check (step 3) and the hourly reconcile would not reliably catch it. `rebuild_targets` is also missing from the LLD §4 data model. | NFR-006 (CRITICAL), FR-013, ADR-0006 | Add a barrier. Writers read `rebuild_targets` in the same transaction as their claim (step 1 of the writer). The shadow stream starts only once every writer has acknowledged the new target epoch, or after waiting longer than the maximum writer batch duration plus one poll. Alternatively, step 2 can re-stream every player whose `updated_at` is at or after step 1's timestamp just before RENAME. Add `rebuild_targets` to §4 and a chaos case to TC-014. **Re-review (round 3):** fixed. LLD §6 Rebuild step 2 waits until all 16 writers have acknowledged in `rebuild_targets_ack`. Step 4 then re-streams every player with `updated_at ≥ started_at − 1 s`, so any write applied to the live key only before the barrier reaches the shadow at its current version. After the barrier, writers dual-write until the swap (step 5). `rebuild_targets` and `rebuild_targets_ack` are in LLD §4. | yes |
| B10 | LLD §6 Redis failover; HLD §9/§10 (NFR-006) | New. ADR-0006 says "after a Redis failover, **mark boards stale** and re-enqueue players updated in the last 15 minutes". The rewrite keeps only the re-enqueue. Re-enqueued rows get `enqueued_at = now()`, so outbox age stays under 60 s. Boards that lost acknowledged writes would then serve rolled-back values with `stale = false` until the replay drains. The failover trigger (how `failover_replay.py` is started) is also not specified. | ADR-0006 Decision bullet 7, NFR-006 | Set a `stale_until` (or failover epoch) flag that `read/staleness.py` honours until the replay rows are drained. Define the trigger, e.g. an ElastiCache failover event or a change of primary run id. **Re-review (round 3):** fixed. `failover_replay.py` polls `CLUSTER NODES` every 5 s, sets `redis_health.stale_until` per shard and re-enqueues 15 min of players with a version bump, so the replay gets past surviving version hashes. `stale_until` is cleared once the outbox has drained those rows, and outbox age covers a drain that takes longer than 5 min (HLD §6, LLD §2, §4, §6). The detection gap of at most about 5 s is only staleness, within NFR-006. | yes |

## 4. Non-blocking findings
| # | Artifact § | Finding | Suggested fix |
|---|------------|---------|---------------|
| N1 | LLD §6 Apply step 3 | Resolved: `reached_at` is now the event's `completed_at` with `GREATEST`. | — |
| N2 | LLD §7; §6 Season close step 3 | Resolved (round 3): the snapshot orders by `score DESC, tie_bucket(reached_at) ASC, player_id DESC`, which matches the encoding granularity exactly. | — |
| N3 | LLD §6 Reconcile repair | Resolved (round 3): reconcile bumps the version before enqueueing, so the guard accepts the repair. | — |
| N4 | LLD §6 Apply; `players_lb.region` | Open: how `region` is filled (profile call or cache, and behaviour when profile is down) is still unspecified (FR-008, Q4). | Specify region resolution in `apply.py`. |
| N5 | LLD §6 Outbox writer step 1 | Resolved (round 3): a short claim transaction with a `claimed_by`/`claimed_at` lease (30 s) and SKIP LOCKED. A zombie writer acting after its lease expires is harmless because of the version guard. | — |
| N6 | LLD §8/§11, HLD §11 | Resolved: the log names are aligned and the outbox-age metric appears in both documents. | — |
| N7 | HLD §4 Read API (FR-014) | Open: FR-014 is mapped, but the LLD has no opt-in or "Anonymous" handling, and ADR-0006 defers it. | Mark it deferred, or add it to the contract. |
| N8 | HLD §1/§2 | Resolved: the wording now matches ADR-0006 (A″). | — |
| N9 | solutioning §7/§9 | Open (upstream, approved): it still describes the A′ repair queue. | Add a pointer note to ADR-0006. |
| N10 | LLD §3 removal | Resolved: a reason is required, and both removal and restore are audited. | — |
| N11 | HLD §6; LLD §2 `read/*` | Resolved (round 3): each pod caches the stale inputs (outbox age and `stale_until`) for 1 s, so there is no PostgreSQL query per request. | — |
| N12 | LLD §6 Season close, steps 2–5 | Resolved (round 3): the barrier is on `enqueued_at ≤ cut-off + grace`, and Object Lock is written only after verification passes. | — |

## 5. ADR compliance
| ADR | Status | Complies? | Evidence / section |
|-----|--------|-----------|--------------------|
| ADR-0001 | Accepted | yes | HLD §2/§6; LLD §13: every Redis value is derived from PostgreSQL rows, and Redis is rebuildable (LLD §6 Rebuild) |
| ADR-0002 | Accepted | yes | HLD §2; LLD §7 (8-day age limit is above the 7-day retention), LLD §9 (keyed by player_id) |
| ADR-0004 | Accepted | yes | LLD §6 steps 2–6 (natural-key dedupe, one transaction, offsets after the commit); LLD §4 partitioning on `completed_month` |
| ADR-0006 | Accepted | yes | Outbox in the transaction, single Lua writer, per-board CAS, removal through the outbox, outbox-age stale flag and rebuild replay are all present (HLD §1/§6/§10; LLD §6/§7/§9/§13). The rebuild barrier (B9) and the failover stale mark with version-bumped replay (B10) were added in round 3 |
| ADR-0003 | Rejected | n/a (record) | No leftovers in the HLD or LLD |
| ADR-0005 | Rejected | n/a (record) | No leftovers |
