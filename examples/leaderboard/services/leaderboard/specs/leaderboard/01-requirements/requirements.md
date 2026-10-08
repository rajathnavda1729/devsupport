<!-- devkit:doc type=requirements v=1 -->
# Requirements — Near-realtime Leaderboards

**Status:** Approved
**Feature:** `leaderboard` · **Updated:** 2026-10-08 · **Upstream:** `input.md`

## 1. Problem statement
Players of Arcadia games cannot see where they stand against others. Live Ops wants competitive engagement through seasonal and all-time rankings. Last season, cheaters posted absurd scores and there was no quick way to correct the rankings. Leaderboards must feel live and must be trustworthy enough to drive season rewards.

## 2. Goals & non-goals
**Goals**
- A player sees their updated rank ≤ 2 s (p95) after a match completes.
- Leaderboard views (top 100, my rank ± 10, friends) load with p95 ≤ 50 ms server-side at 60k reads/s.
- Zero incorrect ranks after any outage. The board may be stale, but never wrong.
- A detected cheater is removed from every board within 5 minutes of an operator action.

**Non-goals** (explicitly out of scope)
- Cheat detection itself. A separate anti-cheat team flags players; we validate score plausibility and act on flags.
- Reward distribution. The rewards service consumes our season-end snapshot.
- Historical seasons older than the previous season, and per-game-mode boards (later phase).
- Client UI.

## 3. Stakeholders & actors
| Actor | Type (human/system) | Needs / interaction |
|-------|---------------------|---------------------|
| Player | human | Views top 100, own rank with neighbours, friends board |
| Live Ops operator | human | Removes or restores cheaters, inspects a player's score history |
| game-api | system | Publishes `match.completed` events to Kafka (key = player_id) |
| profile service | system | Source of the friends graph and the player region |
| rewards service | system | Consumes the frozen season-end leaderboard snapshot |
| anti-cheat service | system | Flags suspicious players (out of scope to build; we consume flags) |

## 4. Functional requirements
Priority uses MoSCoW (Must/Should/Could/Won't). Criticality is `CRITICAL` / High / Medium / Low — see `devkit/knowledge/criticality-rubric.md`. Only the first column defines the ID; never renumber.

| ID | Requirement (The system shall…) | Actor | Priority | Criticality | Source | Acceptance criteria (Given/When/Then) |
|----|---------------------------------|-------|----------|-------------|--------|---------------------------------------|
| FR-001 | The system shall update a player's season and all-time score from each `match.completed` event | game-api | Must | High | input: scores from matches | Given a player with season score 100 When a match.completed with score_delta 25 is consumed Then the season and all-time scores are 125 |
| FR-002 | The system shall apply each `match.completed` event exactly once, even when events are redelivered or replayed | game-api | Must | CRITICAL | inferred (Kafka at-least-once; outage requirement) | Given an event already applied When the same event_id is consumed again Then scores are unchanged; Given a consumer crash mid-batch When it restarts Then no event is lost or double-counted |
| FR-003 | The system shall reject score deltas that fail plausibility rules (above the per-match maximum, negative, or from a flagged player) and record them for review | game-api | Must | High | input: bogus scores | Given a max delta of 5 000 When an event with delta 900 000 arrives Then it is not applied and appears in the rejected-scores log with a reason |
| FR-004 | The system shall serve the top 100 of a board (global or region; season or all-time) | Player | Must | High | input | Given 1 000 ranked players When a player requests the global season top 100 Then 100 entries are returned in rank order with rank, player name and score |
| FR-005 | The system shall serve a player's own rank with up to 10 players above and 10 below | Player | Must | High | input | Given a player ranked 5 000 When they request "my rank" Then ranks 4 990–5 010 are returned with their entry marked; Given an unranked player Then their state is shown as unranked |
| FR-006 | The system shall serve a friends leaderboard ranking the player and their friends | Player | Should | Medium | input | Given a player with 30 friends When they open the friends board Then the 31 players are listed by season score with ranks 1–31 |
| FR-007 | The system shall break score ties by the earliest time the score was reached | Player | Must | High | input: ties | Given A and B both at 500 and A reached 500 first When ranks are computed Then A ranks above B |
| FR-008 | The system shall maintain separate boards per region (EU, NA, APAC) using the player's home region | Player | Must | Medium | input | Given an EU player When their score changes Then the global and EU boards change and NA/APAC do not |
| FR-009 | The system shall start a new season every Monday 00:00 UTC with all season scores at zero, keeping all-time scores | Live Ops | Must | High | input: weekly seasons | Given the season rolls over When a player opens the season board Then the new season is shown with no scores until matches complete after 00:00 UTC |
| FR-010 | The system shall freeze an immutable, verifiable snapshot of every season board at season end for the rewards service | rewards service | Must | CRITICAL | inferred (season rewards — assumption A1) | Given the season ends When the snapshot is produced Then it is identical to the board at 00:00:00 UTC excluding late events, carries a checksum, and cannot be modified |
| FR-011 | The system shall let an operator remove a player from all boards and restore them, with an audit trail | Live Ops operator | Must | High | input: remove cheater | Given a flagged player in the top 100 When the operator removes them Then they disappear from every board ≤ 5 min and the action is logged with operator and reason |
| FR-012 | The system shall let an operator view a player's score history (applied and rejected events) | Live Ops operator | Should | Medium | inferred | Given a player When the operator opens the history Then every applied and rejected event is listed with time, delta and reason |
| FR-013 | The system shall rebuild any board from the system of record without downtime of reads | Live Ops operator | Must | High | inferred (ADR-0001: derived stores must be rebuildable) | Given a corrupted derived board When a rebuild is triggered Then reads continue from the old board until the rebuilt one is verified and swapped in |
| FR-014 | The system shall show results only for players who have opted in to public ranking where privacy settings require it | Player | Could | Medium | inferred (privacy) | Given a player with public ranking off When others view boards Then that player is shown as "Anonymous" |

## 5. Non-functional requirements
Every NFR must have a metric and a target (see `devkit/knowledge/nfr-checklist.md`).

| ID | Category | Requirement | Metric | Target | Priority | Criticality | Verification |
|----|----------|-------------|--------|--------|----------|-------------|--------------|
| NFR-001 | Performance | Score-to-visible-rank freshness | p95 time from event publish to rank visible | ≤ 2 s at 20k events/s | Must | High | benchmark ingest-freshness |
| NFR-002 | Performance | Read latency for top-100, around-me and friends | p95 server-side latency | ≤ 50 ms at 60k reads/s | Must | High | benchmark read-mix |
| NFR-003 | Throughput | Sustained score ingestion | events/s applied | 20k/s sustained for 1 h, 40k/s burst 5 min | Must | High | benchmark ingest-throughput |
| NFR-004 | Scalability | Board size | ranked players per board | 40M all-time, 5M per season, without redesign | Must | Medium | benchmark with 40M seeded entries |
| NFR-005 | Availability | Leaderboard reads | monthly availability | 99.9 % | Must | Medium | SLO dashboard |
| NFR-006 | Reliability | Correctness after failure | rank mismatches vs. system of record after crash/failover | 0 (stale allowed ≤ 60 s, wrong never) | Must | CRITICAL | chaos test + reconciliation job |
| NFR-007 | Recoverability | Full rebuild of a board | rebuild time | ≤ 30 min for 40M players | Must | High | rebuild drill |
| NFR-008 | Security | Operator actions | authorised + audited actions | 100 % of remove/restore actions need ops role and are audit-logged | Must | High | test + audit review |
| NFR-009 | Privacy | Personal data exposure | fields returned | only display name, rank, score, opt-in flag; no ids of other players beyond opaque handle | Must | Medium | contract test |
| NFR-010 | Cost | Infrastructure cost | monthly cost | ≤ $6k/month at stated scale | Should | Medium | cost estimate review |
| NFR-011 | Observability | Detect lag before players do | alert latency | alert when consumer lag > 5 s for 1 min | Must | Medium | alert test |

## 6. 🔴 Critical requirements
Why each CRITICAL item is critical, what breaks if it fails, and how it will be protected.

| ID | Why critical (rubric dimension) | Failure impact | Mitigation / design guard | Verification |
|----|---------------------------------|----------------|---------------------------|--------------|
| FR-002 | Data integrity (3): double-applied deltas silently corrupt scores; not detectable by players | Wrong ranks, wrong season rewards, loss of trust | Idempotency on event_id in the same transaction as the score update; consumer offsets committed after apply | Duplicate/replay tests; reconciliation job |
| FR-010 | Financial (3): rewards are paid from the snapshot | Wrong players rewarded; cannot be clawed back | Snapshot from the system of record at a fixed cut-off, checksum, immutable storage, dual-run comparison | Snapshot verification test; season rollover drill |
| NFR-006 | Data integrity (3) + blast radius (3): affects every player | Visibly wrong ranks after an incident | Derived boards rebuilt/reconciled from PostgreSQL (ADR-0001); serve "stale" flag rather than wrong data | Chaos tests (kill cache, kill consumer, replay) + reconciliation |

## 7. Constraints
- ADR-0001: PostgreSQL is the system of record; any cache or derived store must be rebuildable from PostgreSQL or the event log.
- ADR-0002: score input arrives as Kafka `match.completed` events keyed by player_id, retained 7 days.
- Launch in 6 weeks with a team of 3 backend engineers (assumption A3).
- Services are Python 3.12 / FastAPI (existing convention in `services/game-api`).

## 8. Assumptions
| # | Assumption | Risk if wrong | Owner to confirm |
|---|------------|---------------|------------------|
| A1 | Season rewards are paid from the season-end board, so FR-010 is CRITICAL | Over-engineered snapshot if no rewards | Head of Live Ops |
| A2 | Per-match maximum plausible score delta is 5 000 | Legit scores rejected or cheats accepted | Game design |
| A3 | Team of 3 backend engineers for 6 weeks | Scope cut needed | Engineering manager |
| A4 | Average 40 friends per player, max 500 | Friends board slower than NFR-002 | Profile team |
| A5 | Events arriving > 5 min after season end count toward the next season | Disputes from players at the boundary | Head of Live Ops |

## 9. Dependencies
- game-api `match.completed` topic (schema in `services/game-api/src/events.py`).
- profile service API for friends list and home region.
- anti-cheat flag feed (format to be agreed).
- rewards service consuming the season snapshot.

## 10. Open questions
| # | Question | Blocking? | Asked to | Answer |
|---|----------|-----------|----------|--------|
| Q1 | Are season rewards paid from the leaderboard? (A1) | Yes | Head of Live Ops | Yes. Top 1 000 per board get rewards; FR-010 stays CRITICAL (demo: simulated answer) |
| Q2 | What is the maximum plausible score per match per game mode? (A2) | Yes | Game design | 5 000 default; per-mode overrides in config (demo: simulated answer) |
| Q3 | How does anti-cheat deliver flags (Kafka topic or API)? | No | Anti-cheat team | Open |
| Q4 | Can a player change region mid-season, and which board keeps their score? | No | Product | Open |

## 11. Glossary
- **Board**: one ranking, i.e. a scope (global or region) × a period (season or all-time).
- **Season**: Monday 00:00 UTC to the following Monday 00:00 UTC.
- **Around-me**: the player's rank with 10 neighbours above and below.
- **Snapshot**: the frozen, checksummed season-end board handed to rewards.
