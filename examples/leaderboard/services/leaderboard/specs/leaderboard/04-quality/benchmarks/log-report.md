# Log Watch Report

- Duration: 196.4s
- Lines by level: WARN=729
- Alerts fired: 2

## Alerts

| Time | Severity | Rule | Source | Line |
|---|---|---|---|---|
| 2026-10-08T00:21:04 | high | slow-read | logs/poc-sqlite.log | `{"ts": "2026-10-08T00:21:04", "level": "WARN", "msg": "slow read", "backend": "sqlite", "path": "/boards/global/around/p` |
| 2026-10-08T00:23:21 | high | slow-read | logs/poc-sqlite.log | `{"ts": "2026-10-08T00:23:21", "level": "WARN", "msg": "slow read", "backend": "sqlite", "path": "/boards/global/around/p` |

## Top warning/error signatures

| Count | Level | Signature |
|---|---|---|
| 729 | WARN | `WARN slow read backend=sqlite path=/boards/global/around/p<n> duration_ms=<n>` |

