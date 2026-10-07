# Non-Functional Requirements Checklist

Based on ISO/IEC 25010 quality characteristics. For each category, ask the questions; if the answer matters, write an NFR with a **metric** and a **target**. "Fast", "scalable", "secure" without numbers are not requirements.

| Category | Probing questions | Example metric → target |
|----------|-------------------|-------------------------|
| **Performance – latency** | Which user-facing operations have a latency budget? At what load? | p95 of `POST /orders` ≤ 200 ms at 300 rps |
| **Performance – throughput** | Peak and sustained volume? Burst factor? Growth over 2 years? | Sustain 1 000 msg/s, burst 5 000 msg/s for 60 s |
| **Resource usage** | Memory/CPU limits? Cost ceiling? | ≤ 512 MiB RSS per pod; ≤ $X / month |
| **Scalability** | What grows (users, tenants, data)? Scale up or out? | Linear to 10× load by adding nodes, no redesign |
| **Availability** | Allowed downtime? Maintenance windows? Dependencies' SLAs? | 99.9 % monthly (≤ 43 min downtime) |
| **Reliability / resilience** | Behaviour when a dependency is slow or down? Retries? | No request lost when the DB fails over; recover ≤ 30 s |
| **Recoverability** | RPO / RTO? Backups? | RPO ≤ 5 min, RTO ≤ 1 h |
| **Consistency** | Can users see stale data? For how long? | Read-your-writes for author; others ≤ 5 s eventual |
| **Security – authN/Z** | Who may do what? Multi-tenant isolation? | 100 % endpoints require auth; tenant isolation tested |
| **Security – data** | PII? Encryption? Secrets handling? | AES-256 at rest, TLS 1.2+ in transit, no secrets in logs |
| **Privacy & compliance** | Regulations? Data residency? Retention & erasure? | Erasure request fulfilled ≤ 30 days; EU data stays in EU |
| **Auditability** | Who did what, when — must it be provable? | Immutable audit log for all money movements, kept 7 years |
| **Observability** | How will we know it is broken before users do? | Structured logs with correlation id; RED metrics; alert ≤ 2 min |
| **Maintainability** | Who maintains it? Coupling limits? | New payment provider added in ≤ 3 days, ≥ 80 % unit coverage on domain |
| **Testability** | Can it be tested locally without prod dependencies? | Full suite runs locally in ≤ 10 min with fakes |
| **Deployability** | Release frequency? Zero-downtime? Rollback? | Zero-downtime deploy; rollback ≤ 5 min |
| **Portability / compatibility** | Browsers, OS, API versions, backwards compatibility? | API v1 clients keep working for 12 months |
| **Usability & accessibility** | Who are users? Standards? | WCAG 2.2 AA; task completion ≤ 3 clicks |
| **Localisation** | Languages, currencies, time zones? | All money in minor units with ISO-4217 code |
| **Capacity / data** | Volume, record size, retention? | 50 M rows/year; hot data 90 days |

## Turning a vague statement into an NFR
1. Name the operation or quality ("search", "checkout availability").
2. Pick the metric (p95 latency, error rate, RPO…).
3. Set the target **and** the condition (load, data size, environment).
4. State how it will be verified (benchmark, chaos test, audit, review).

The *Verification* column of every NFR must point to a benchmark scenario (`09-benchmark-plan.md`), a test case (`08-test-plan.md`), or a review activity.
