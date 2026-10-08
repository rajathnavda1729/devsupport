# Benchmark Report

_Generated 2026-10-08 08:08 by `devkit/tools/bench.py`._

| Name | Kind | n | p50_ms | p95_ms | p99_ms | mean_ms | stdev_ms | throughput_rps | error_rate | SLOs |
|---|---|---|---|---|---|---|---|---|---|---|
| optA-around-me | http | 300 | 3.515 | 13.58 | 63.918 | 5.81 | 9.471 | 1319.93 | 0.0 | ✅ |
| optA-ingest | http | 2000 | 8.112 | 18.138 | 101.631 | 11.398 | 28.139 | 699.68 | 0.0 | ✅ |
| optA-top100 | http | 400 | 2.602 | 4.005 | 33.64 | 3.735 | 8.073 | 1917.32 | 0.0 | ✅ |
| optB-around-me | http | 300 | 814.735 | 1310.488 | 1871.613 | 841.761 | 286.085 | 9.43 | 0.0 | ❌ p95_ms<=50 |
| optB-ingest | http | 2000 | 3.074 | 6.147 | 17.472 | 3.656 | 3.761 | 2175.01 | 0.0 | ✅ |
| optB-top100 | http | 400 | 4.847 | 8.091 | 12.77 | 5.462 | 5.006 | 1392.95 | 0.0 | ✅ |
| optB2-around-me | http | 400 | 10.629 | 15.376 | 19.904 | 10.94 | 2.808 | 724.9 | 0.0 | ✅ |
| optB2-ingest | http | 2000 | 3.014 | 8.252 | 35.011 | 4.227 | 5.995 | 1866.26 | 0.0 | ✅ |
| optB2-top100 | http | 400 | 5.675 | 12.386 | 13.716 | 6.964 | 5.628 | 1136.43 | 0.0 | ✅ |

### Per-scenario comparison (p95)

| Scenario | Best | p95 ms | Others |
|---|---|---|---|
| around-me | optA-around-me | 13.58 | optB2-around-me 15.376 ms, optB-around-me 1310.488 ms |
| ingest | optB-ingest | 6.147 | optB2-ingest 8.252 ms, optA-ingest 18.138 ms |
| top100 | optA-top100 | 4.005 | optB-top100 8.091 ms, optB2-top100 12.386 ms |
