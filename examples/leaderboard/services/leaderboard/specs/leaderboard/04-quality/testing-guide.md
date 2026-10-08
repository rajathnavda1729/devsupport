<!-- devkit:doc type=testing-guide v=1 -->
# Testing Guide — Near-realtime Leaderboards

**Status:** Review
**Feature:** `leaderboard` · **Updated:** 2026-10-08 · **Upstream:** `../02-design/lld.md`

How a developer tests this feature locally, end to end.

## 1. Prerequisites
- Python 3.12, Docker with Compose v2, and `make`.
- Optional: `npm i -g @mermaid-js/mermaid-cli`, so that `devkit lint --render` validates diagrams.
- Env vars come from `services/leaderboard/.env.example` (to be created in T-001): `LB_PG_DSN`, `LB_REDIS_URL`, `KAFKA_BOOTSTRAP`.
- Today only the proof of concept exists (`services/leaderboard/poc/`). It needs nothing beyond Python 3.10+.

## 2. Local environment setup
```bash
# Proof of concept (exists today, verified 2026-10-08)
python3 services/leaderboard/poc/server.py --backend memory --players 1000000 --port 8091 --log-file logs/poc-memory.log

# Service (to be created in T-001 / T-003)
cd services/leaderboard
docker compose up -d postgres redis-cluster redpanda   # PostgreSQL 15, Redis 7 x3, Kafka API
make migrate                                           # schema `leaderboard`
make seed PLAYERS=1000000 SEED=7                       # deterministic players + scores
make run                                               # ingest worker, outbox writer, read API, ops API
```

## 3. Test data
- `make seed` uses the same generator as the PoC (seed 7), so ranks are reproducible across machines.
- Edge cases for the CRITICAL requirements live in `tests/fixtures/`:
  - `duplicates.jsonl`: the same match_id with new event_ids (FR-002);
  - `implausible.jsonl` (FR-003);
  - `season_boundary.jsonl`: completed at 23:59:59 and processed after the grace period (FR-009, FR-010);
  - `removal_race.jsonl`: a removal interleaved with an in-flight batch (FR-011).
- Reset with `make reset-local`. It truncates the schema and flushes Redis; `make rebuild` restores boards from PostgreSQL.

## 4. Test pyramid for this feature
| Layer | Scope | Framework | Location | Command |
|-------|-------|-----------|----------|---------|
| Unit | scoring rules, season assignment, tie-break encoding, Lua CAS logic (with a fake) | pytest + hypothesis (property tests TC-014, TC-018) | `services/leaderboard/tests/unit/`, `tests/property/` | `make test-unit` (to be created in T-007) |
| Integration | apply transaction, outbox writer, Redis Lua against real stores | pytest + testcontainers | `tests/integration/` | `make test-integration` (to be created in T-005) |
| Contract | read API responses, `match.completed` schema with game-api | schemathesis + pact | `tests/contract/` | `make test-contract` (to be created in T-018) |
| End-to-end | event → rank visible; removal; season close; chaos suite TC-010, TC-011, TC-013, TC-032 | pytest + chaos env flags | `tests/chaos/`, `tests/e2e/` | `make test-chaos` (to be created in T-020 / T-024) |
| Performance | benchmark scenarios | `devkit/tools/bench.py` | `services/leaderboard/specs/leaderboard/04-quality/benchmarks/` | see `benchmark-plan.md` |

## 5. Running the tests
```bash
make test-unit test-integration          # every PR (to be created in T-005 / T-007)
make test-chaos                          # nightly + before each rollout step (T-020 / T-024)
python3 devkit/tools/tracker.py -f leaderboard validate    # requirement and test coverage (works today)
python3 devkit/tools/doclint.py --feature leaderboard      # documents match templates (works today)
```

## 6. Watching logs while testing
```bash
python3 devkit/tools/logwatch.py --config devkit/config/logwatch.leaderboard.json
# post-run gate (CI-friendly):
python3 devkit/tools/logwatch.py <logfile> --once --from-start --fail-on ERROR --report services/leaderboard/specs/leaderboard/04-quality/benchmarks/log-report.md
```
- **Profile:** `devkit/config/logwatch.leaderboard.json`. It follows `logs/*.log` and adds four feature rules on top of the defaults:
  - `implausible-score-burst`: more than 20 per minute;
  - `duplicate-event-storm`: more than 100 per minute;
  - `slow-read`: more than 10 per minute;
  - `read-failure`: critical, on the first occurrence.
- **Success signals per flow:**
  - **Ingest:** `score_applied` lines at DEBUG, with no `apply_failed`.
  - **Outbox:** the `lb_outbox_oldest_age_seconds` metric stays below 1 s, with no `redis_write_failed`.
  - **Reads:** no `slow read` warnings.
  - **Removal:** `player_removed`, followed by the player being absent on every board.
- **Failure signals:** any ERROR line, `snapshot_verify_failed`, `score_encoding_overflow`, or a stale incident (`stale = true` in responses).
- **Verified 2026-10-08 against the PoC:** the watcher grouped 729 slow-read warnings from the naive Option B into one signature, and raised the `slow-read` alert twice.

## 7. Manual / exploratory checks
- [ ] Open the top-100 for every scope × period. Ranks are strictly increasing with no gaps.
- [ ] Remove a top-10 player through the Ops API. They disappear from every board within seconds; then restore them.
- [ ] Kill the outbox writer for 2 minutes. Reads show `stale = true` after 60 s and recover after a restart.
- [ ] Trigger a season close in staging with a mocked clock. The snapshot checksum is verified before the S3 write.

## 8. Debugging tips
- **Rank looks wrong:**
  1. Compare PostgreSQL (`SELECT score, reached_at FROM leaderboard.scores WHERE player_id = …`) with Redis (`ZSCORE lb:{global:season:2026-W41} <player>` and `HGET lbv:{global:season:2026-W41} <player>`).
  2. A lower Redis version means a pending `redis_dirty` row.
- **Outbox stuck:** `SELECT part, count(*), min(enqueued_at) FROM leaderboard.redis_dirty GROUP BY part`. A stale `claimed_at` means a crashed writer; the row is reclaimed after 30 s.
- **Lag:** `rpk group describe leaderboard-ingest` shows per-partition lag.

## 9. CI
- **PR:** unit, property and integration tests; `devkit lint --render`; `tracker.py validate`.
- **Nightly:** the chaos suite, `bench.py` gates against the baseline (`bench.py compare … --threshold 10`), and `logwatch --once --fail-on ERROR` on the integration-run logs (T-022).
- **Merge-blocking:** test failures, lint errors, coverage below 85 % on `domain/` and `writer/`, and benchmark regressions.
