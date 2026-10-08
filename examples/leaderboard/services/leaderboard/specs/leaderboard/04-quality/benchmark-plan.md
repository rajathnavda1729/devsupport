<!-- devkit:doc type=benchmark-plan v=1 -->
# Benchmark Plan — Near-realtime Leaderboards

**Status:** Review
**Feature:** `leaderboard` · **Updated:** 2026-10-08 · **Upstream:** `../01-requirements/requirements.md` (NFRs), `../02-design/solutioning.md`

## 1. Objectives
- Verify NFR-001 (freshness), NFR-002 (read latency), NFR-003 (throughput) and NFR-004 (board size) at target scale.
- Run the T-002 capacity gate that decides between ADR-0006 and its fallback.
- Keep the proof-of-concept results that informed solutioning §8 as the algorithmic baseline.

## 2. SLO gates (from NFRs)
| NFR | Scenario | Metric | Gate (`--slo`) |
|-----|----------|--------|----------------|
| NFR-002 | read-top100, read-around-me (B1, B2) | p95 latency | `p95_ms<=50` |
| NFR-002 | Redis rank query only (T-002) | p95 latency | `p95_ms<=5` |
| NFR-001 | ingest-freshness (B4) | p95 publish-to-visible | `p95_ms<=2000` |
| NFR-003 | ingest-throughput (B3) | sustained apply rate | `throughput_rps>=20000` |
| NFR-005 | all read scenarios | error rate | `error_rate<=0.001` |

## 3. Environment
- **PoC (done):** a MacBook (`env` recorded in each result file); a single process; 1M players; uniform scores 0–50 000. These numbers show algorithmic behaviour only, not capacity.
- **Staging (T-002, T-011):** production-sized Redis Cluster (2 shards with replicas) and PostgreSQL 15 Multi-AZ; 40M players with a **skewed** distribution; 8 boards; mixed read and write load.
- Results are comparable only on the same environment. `bench.py report` warns when platforms differ.

## 4. Scenarios
| ID | Scenario | Kind (cmd/http) | Load (n / concurrency / duration) | Command |
|----|----------|-----------------|-----------------------------------|---------|
| B1 | read-top100 | http | 400 / 8 (PoC); 60k rps mix (staging) | `bench.py http --name optA-top100 --url http://127.0.0.1:8091/boards/global/top?n=100 -n 400 -c 8 --slo "p95_ms<=50"` |
| B2 | read-around-me, random players | http | 300–400 / 8 | `bench.py http --name optA-around-me --url "http://127.0.0.1:8091/boards/global/around/p{randint:1:1000000}?k=10" -n 300 -c 8 --slo "p95_ms<=50"` |
| B3 | ingest unique events | http | 2 000 / 8 (PoC); 20k/s for 1 h (staging) | `bench.py http --name optA-ingest --url http://127.0.0.1:8091/events -X POST --data '{"event_id":"{uuid}","player_id":"p{randint:1:1000000}","score_delta":{randint:0:500},"completed_at":"now"}' -n 2000 -c 8` |
| B4 | ingest-freshness | cmd | 20k events/s, a probe player every 1 s | `bench.py cmd --name freshness --duration 600 "python3 tests/perf/freshness_probe.py"` (to be created in T-011) |
| B5 | Redis capacity at 40M entries × 4 boards | cmd | 80k Lua writes/s + 60k reads/s | `bench.py cmd --name t002-redis "python3 tests/perf/redis_capacity.py --entries 40000000"` (to be created in T-002) |

```bash
# Example
python3 devkit/tools/bench.py http --name optA-around-me \
  --url "http://127.0.0.1:8091/boards/global/around/p{randint:1:1000000}?k=10" \
  -n 300 -c 8 --warmup 10 --slo "p95_ms<=50" \
  --out services/leaderboard/specs/leaderboard/04-quality/benchmarks/optA-around-me.json
```

## 5. Baseline & regression policy
- **PoC baseline:** the `opt*.json` results in `benchmarks/` stay as the algorithmic reference; they are never compared against staging.
- **Staging baseline:** the first accepted staging run of each scenario is copied to `benchmarks/baseline-<scenario>.json`.
- **Regression check:** every nightly run executes `bench.py compare baseline-<scenario>.json <scenario>.json --threshold 10` and fails on a regression.

## 6. Results
Proof of concept, 2026-10-08, from `benchmarks/REPORT.md`, all on the same laptop with 1M players:

| Scenario | A (ordered index, proxy for Redis) | B naive (COUNT/OFFSET) | B keyset (fair) | NFR-002 gate |
|----------|------------------------------------|------------------------|-----------------|--------------|
| around-me p95 | 13.6 ms | 1 310 ms | 15.4 ms | A ✅, B naive ❌, B keyset ✅ |
| top-100 p95 | 4.0 ms | 8.1 ms | 12.4 ms | all ✅ |
| ingest p95 | 18.1 ms (O(n) list proxy) | 6.1 ms | 8.3 ms | all ✅ |

- The keyset version returned responses identical to the reference for 8 of 8 sampled players.
- The log watcher captured 729 `slow read` warnings for B naive and raised 2 alerts, and nothing for A or B keyset.
- **Interpretation:** the PoC proved the *algorithmic* point that rank queries must be O(log n). It does not prove capacity at 60k reads/s. That is the job of B5 / T-002, still **not run**, and it gates ADR-0006.
