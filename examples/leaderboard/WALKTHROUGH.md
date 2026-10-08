# Example: near-realtime leaderboard, end to end

This folder is a complete devkit run on a realistic feature: **near-realtime leaderboards** for a game platform, from a raw product request to an implementation-ready plan. Every document here was produced by following the devkit skills and agents, and checked by its tools.

It is also an honest record of what the gates catch. The chosen design **changed twice** under review, and the run exposed 21 issues in devkit itself (all fixed in v0.5.0).

> **Read this first.**
> - **Approvals were simulated.** The person running the demo played the product owner. Every simulated answer is labelled "(demo: simulated answer)" in `requirements.md`.
> - **The benchmarks are a proxy.** They come from a stdlib Python proof of concept with 1M players (an in-memory index standing in for Redis, and SQLite standing in for PostgreSQL). They show algorithmic behaviour, not production capacity. The decisive load test (T-002) is deliberately marked **not run**.

## The setup
`Arcadia Games` is a monorepo with `services/game-api`, `services/profile` and a new `services/leaderboard`. Two architecture decisions already existed, in **different formats**:
- `docs/adr/0001-postgresql-as-system-of-record.md` (Nygard / adr-tools);
- `docs/adr/0002-kafka-for-domain-events.md` (MADR with front matter).

The raw request is [`docs/prd/leaderboard.md`](docs/prd/leaderboard.md): global and regional boards, weekly seasons, top-100, "my rank ± 10", friends, ties broken by time reached, anti-cheat, 5M daily players, 20k score updates/s, 60k reads/s, and "never wrong after an outage".

## Where to look
The feature workspace sits next to the service that implements it: [`services/leaderboard/specs/leaderboard/`](services/leaderboard/specs/leaderboard/README.md). Its generated `README.md` indexes every document.

| Stage | Document | What to notice |
|-------|----------|----------------|
| Existing decisions | [`docs/adr/decision-log.md`](docs/adr/decision-log.md) | Both ADR formats detected and indexed |
| 1 Requirements | [`01-requirements/requirements.md`](services/leaderboard/specs/leaderboard/01-requirements/requirements.md) | 14 FR, 11 NFR, 3 🔴 CRITICAL (exactly-once scoring, season snapshot for rewards, never wrong after failure); blocking questions answered before approval |
| 2 Solutioning | [`02-design/solutioning.md`](services/leaderboard/specs/leaderboard/02-design/solutioning.md) | Prior ADRs in §1, the pattern fit table, 3 options, the **scoring history** across 3 challenge rounds in §6, proof-of-concept results in §8, and a **Fallback** in §9 |
| 2.5 Decisions | [`02-design/decisions/`](services/leaderboard/specs/leaderboard/02-design/decisions/) | ADR-0003 and ADR-0005 **Rejected**, each with the challenge that sank it; ADR-0004 and ADR-0006 Accepted, each with a full *Evaluation* section |
| 3–4 Design | [`hld.md`](services/leaderboard/specs/leaderboard/02-design/hld.md), [`lld.md`](services/leaderboard/specs/leaderboard/02-design/lld.md) | C4, sequence, ER and state diagrams, all checked with `devkit lint --render`; transactional outbox plus version-guarded Redis writes |
| 4.5 Review | [`02-design/reviews/design-review.md`](services/leaderboard/specs/leaderboard/02-design/reviews/design-review.md) | 10 blocking findings over 3 rounds, all resolved; verdict APPROVE |
| 5–6 Delivery | [`TASKS.md`](services/leaderboard/specs/leaderboard/03-delivery/TASKS.md), [`execution-plan.md`](services/leaderboard/specs/leaderboard/03-delivery/execution-plan.md) | 25 tasks; the generated schedule **misses the 6-week deadline by 7 days**, and the plan says so and offers options |
| 7–9 Quality | [`test-plan.md`](services/leaderboard/specs/leaderboard/04-quality/test-plan.md), [`traceability.md`](services/leaderboard/specs/leaderboard/04-quality/traceability.md), [`benchmark-plan.md`](services/leaderboard/specs/leaderboard/04-quality/benchmark-plan.md), [`benchmarks/`](services/leaderboard/specs/leaderboard/04-quality/benchmarks/REPORT.md) | All 25 requirements trace to tasks and tests; critical requirements have positive, negative and failure-injection cases; the log watcher caught 729 slow reads |
| 10 Readiness | [`03-delivery/readiness.md`](services/leaderboard/specs/leaderboard/03-delivery/readiness.md) | All 8 checks ✅, so implementation could start (T-001, and the T-002 spike) |

## How the decision changed, and why that is the point
1. **First pick: Redis sorted sets** (ADR-0003). They won the matrix 440 to 375. The PostgreSQL option was benchmarked with `OFFSET` and measured 1 310 ms for around-me.
2. **Challenge round 1 → Rejected.** The dual write could leave Redis permanently *wrong* after a crash between commit and write. Worse, the PostgreSQL baseline was a strawman. A fair keyset version, after fixing an `OR` predicate that defeated the index, measured **15.4 ms**, against 13.6 ms for the Redis proxy.
3. **Second pick: PostgreSQL only** with score-bucket counts (ADR-0005). Round 2 → **Rejected**. The bucket table is hidden derived state, so "correct by construction" was false, and replica lag conflicted with the 2 s freshness target.
4. **Final: PostgreSQL truth + a Redis read model** (ADR-0006). Round 3 (*sound with mitigations*) found that unversioned absolute writes still let an older value land last. The adopted fix: a **transactional outbox** plus **version-guarded Lua writes**. It wins by 22.7% and is robust to ±20% weight changes and ±1 score changes.

Every change is backed by a measurement or a concrete failure scenario, and recorded in the ADRs.

## Reproduce or explore
From a clone of this repo:
```bash
cd examples/leaderboard                     # has its own .devkit.json, so tools anchor here
../../bin/devkit status leaderboard          # document states
../../bin/devkit review leaderboard          # readiness gate → READY
../../bin/devkit review matrix leaderboard   # option scores, margin, weight and score sensitivity
../../bin/devkit review decision 6           # ADR-0006 evaluation completeness
../../bin/devkit adr list                    # all six ADRs with statuses
../../bin/devkit task -f leaderboard schedule --start 2026-10-12 --team 3 --focus 0.7 \
    --deadline 2026-11-20 --phases M1-skeleton,M2-core,M3-hardening,M4-release
../../bin/devkit lint --feature leaderboard  # every document still matches its template
```

Re-run the proof-of-concept benchmarks:
```bash
python3 services/leaderboard/poc/server.py --backend memory        --players 1000000 --port 8091 &
python3 services/leaderboard/poc/server.py --backend sqlite-keyset --players 1000000 --port 8093 &
../../bin/devkit bench http --name optA-around-me \
  --url "http://127.0.0.1:8091/boards/global/around/p{randint:1:1000000}?k=10" -n 300 -c 8 --slo "p95_ms<=50"
../../bin/devkit bench http --name optB2-around-me \
  --url "http://127.0.0.1:8093/boards/global/around/p{randint:1:1000000}?k=10" -n 300 -c 8 --slo "p95_ms<=50"
```

## What this run fixed in devkit (v0.5.0)
Every item below has a test in `tests/`.
- **Bugs:** critical requirements lost when the critical table repeats IDs; "pending" accepted as a completed evaluation; Rejected ADRs blocking the gate forever; benchmark reports ranking different scenarios against each other.
- **New gates:**
  - score sensitivity (decisive cells need evidence);
  - a **Fallback** required for close calls that rest on unmeasured experiments;
  - blocking questions must be answered;
  - the HLD and LLD may only *apply* live decisions;
  - critical requirements need ≥ 3 test cases;
  - tests cited in designs must exist;
  - Mermaid render validation;
  - a confirmation prompt before editing Approved documents or Accepted ADRs.
- **New tools:** `tracker schedule` (deadline check and generated Gantt chart), per-request benchmark placeholders (`{uuid}`, `{randint:a:b}`), `adr retitle`.
- **Better agents:** the challenger checks hidden derived state, gates against NFR targets, decisive scores and concurrent writers, and follows a convergence rule; the design reviewer hunts leftovers from rejected decisions.

## Known limitations of this example
- ADR-0004 and ADR-0006 keep titles from earlier drafts ("applied-events ledger", "absolute re-asserted writes"). Their content was revised during review while still Proposed, which is why `adr retitle` now exists, but they are now Accepted and therefore frozen.
- The services contain only the proof of concept. Implementation starts with the ready tasks in `TASKS.md`.
