# Design Pattern Catalog

Used by the **solutioning** skill. Start from the *signal* you see in the requirements, shortlist patterns, then argue fit using the drivers. Every adopted pattern must name the requirement(s) it serves; every rejected candidate gets a one-line reason.

## Signal → pattern index

| Signal in requirements | Candidate patterns |
|------------------------|--------------------|
| Read-heavy, latency-sensitive, data changes rarely | Cache-aside, Read replicas, CDN, Materialized view |
| Write and read models differ wildly / complex queries | CQRS, Materialized view |
| Need full history / audit / temporal queries | Event sourcing, Append-only audit log |
| Work spans several services and must be all-or-nothing | Saga (orchestrated / choreographed), Transactional outbox |
| "Exactly once", duplicate requests, retries by clients | Idempotency key, Outbox + inbox (dedupe), Optimistic concurrency |
| Must publish an event whenever DB changes | Transactional outbox, Change data capture |
| Slow / unreliable downstream dependency | Timeout + retry with backoff & jitter, Circuit breaker, Bulkhead, Fallback, Async via queue |
| Spiky traffic, background or long jobs | Queue-based load levelling, Competing consumers, Async request-reply (202 + status) |
| Protect service from abuse / fairness across tenants | Rate limiting (token bucket), Throttling, Quotas |
| Many clients with different needs (web, mobile, partners) | API gateway, Backend-for-frontend (BFF) |
| Gradually replacing a legacy system | Strangler fig, Anti-corruption layer |
| Integrating with a messy external model | Anti-corruption layer, Adapter |
| Business rules change often / per customer | Strategy, Rules engine, Specification, Feature flags |
| Multi-step processing of data | Pipes & filters, Chain of responsibility |
| Entities with lifecycle and transitions | State machine (State pattern) |
| Many independent reactions to one occurrence | Observer / Pub-sub, Event-driven architecture |
| Swappable infrastructure, testability | Hexagonal (ports & adapters), Repository, Dependency injection |
| Large data / throughput beyond one node | Sharding / partitioning, Consistent hashing, Leader–follower replication |
| Single active worker needed among replicas | Leader election, Distributed lock (with fencing token) |
| Multi-tenant SaaS | Tenant-per-schema / per-db / shared-with-tenant-id, Bulkhead per tenant |
| Complex object creation / variants | Factory, Builder, Abstract factory |
| Add behaviour without modifying classes | Decorator, Middleware |
| Expensive object or remote resource | Proxy, Object pool, Lazy loading |
| Undo / queueing of operations | Command |
| Small team, unclear domain, early product | Modular monolith (layered or hexagonal) — defer microservices |

## Architectural styles

| Style | Use when | Avoid when | Trade-offs | NFRs it helps / hurts |
|-------|----------|------------|------------|------------------------|
| **Modular monolith** | Small/medium team, evolving domain, need speed | Parts need very different scaling or release cadence | Simple ops; discipline needed to keep modules apart | + maintainability, deployability early; − independent scalability |
| **Microservices** | Many teams, clear bounded contexts, independent scaling | One team, unclear boundaries, no platform/ops maturity | Autonomy vs distributed-systems cost | + scalability, team autonomy; − latency, consistency, operability |
| **Event-driven** | Many consumers of facts, loose coupling, async OK | Strict request/response consistency needed everywhere | Decoupling vs harder debugging & ordering | + scalability, extensibility; − traceability, consistency |
| **Layered (n-tier)** | CRUD-heavy apps, simple domains | Rich domain logic leaking into layers | Familiar; tends toward anaemic models | + simplicity |
| **Hexagonal / clean** | Rich domain, many integrations, high test needs | Trivial CRUD | More interfaces / indirection | + testability, maintainability |
| **Serverless** | Spiky/low traffic, event triggers, small functions | Long-running, latency-critical with cold starts, heavy state | Zero ops vs vendor lock-in, cold starts | + cost at low load; − p99 latency |
| **Pipes & filters / stream processing** | Continuous data transformation | Request/response interactions | Composable vs operational complexity | + throughput |

## Distributed-data & integration patterns

| Pattern | Problem | How it works | Pitfalls | Serves |
|---------|---------|--------------|----------|--------|
| **Cache-aside** | Repeated expensive reads | App reads cache, on miss loads DB and populates with TTL | Stale data, stampede (use jittered TTL / single-flight), invalidation on write | latency, throughput |
| **CQRS** | Read/write needs diverge | Separate write model and denormalised read models | Eventual consistency, more moving parts | performance, scalability |
| **Event sourcing** | Need full history / rebuildable state | Store events; state = fold(events) | Schema evolution of events, snapshots, steep learning curve | auditability, temporal queries |
| **Saga** | Cross-service transaction | Sequence of local txns with compensations | Compensation design, visibility of in-flight sagas | consistency without 2PC |
| **Transactional outbox** | Atomically update DB and publish event | Write event to outbox table in same txn; relay publishes | Relay lag, consumer must dedupe | reliability, consistency |
| **Idempotency key** | Client retries cause duplicates | Store key → result; replay result on repeat | Key scope/TTL, concurrent duplicates need lock/unique constraint | correctness (exactly-once effect) |
| **Optimistic concurrency** | Lost updates | Version column; update `WHERE version = n` | Retry on conflict | data integrity |
| **Change data capture** | Propagate DB changes without dual writes | Read DB log (e.g. Debezium) and stream | Ops complexity, schema coupling | consistency, decoupling |
| **Sharding** | Data/throughput > single node | Partition by key | Hot keys, cross-shard queries, resharding | scalability |
| **Read replicas** | Read scaling | Async replicas serve reads | Replication lag → stale reads | throughput, availability |
| **Leader election** | One active worker | Lease via consensus store (etcd/ZK/DB lock) | Split brain — use fencing tokens | correctness |

## Resilience patterns

| Pattern | Problem | Key parameters | Pitfalls | Serves |
|---------|---------|----------------|----------|--------|
| **Timeout** | Hung calls exhaust resources | Per-call deadline < caller's budget | Missing timeouts are the #1 outage cause | availability, latency |
| **Retry + exponential backoff + jitter** | Transient failures | max attempts, base delay, cap, jitter | Retry storms; only retry idempotent ops | reliability |
| **Circuit breaker** | Failing dependency drags everything down | failure threshold, open duration, half-open probes | Needs fallback; tune per dependency | availability |
| **Bulkhead** | One noisy part exhausts shared pools | Separate pools/queues per dependency or tenant | Under-utilisation | availability, fairness |
| **Fallback / graceful degradation** | Dependency down | Cached/default response, feature off | Users must not get wrong data silently | availability |
| **Queue-based load levelling** | Bursts overwhelm service | Queue depth, consumer count, DLQ | Latency increases; need back-pressure | throughput, availability |
| **Rate limiting (token bucket)** | Abuse, fairness | rate, burst, key (user/tenant/IP) | Distributed limits need shared store | availability, security |
| **Health check & self-healing** | Detect and replace bad instances | liveness vs readiness | Deep checks that cascade failures | availability |

## Classic (GoF) patterns — quick reference

| Pattern | Intent | Typical use in services |
|---------|--------|-------------------------|
| Strategy | Swap algorithms at runtime | Pricing rules, payment providers, retry policies |
| Factory / Abstract factory | Encapsulate creation | Creating provider clients per config/tenant |
| Builder | Step-wise construction of complex objects | Building queries, test fixtures, requests |
| Adapter | Make incompatible interfaces work together | Wrapping third-party SDKs behind a port |
| Facade | Simple interface over a subsystem | Module public API |
| Decorator | Add behaviour transparently | Caching/metrics/logging around repositories |
| Proxy | Control access to an object | Lazy loading, remote proxies, auth checks |
| Observer | Notify dependents of changes | Domain events within a process |
| Command | Encapsulate a request as an object | Job queues, undo, audit of actions |
| Chain of responsibility | Pass request along handlers | Middleware, validation pipelines |
| State | Behaviour depends on state | Order / payment lifecycle |
| Template method | Fixed algorithm, variable steps | Import pipelines with per-source steps |
| Repository | Collection-like access to aggregates | Isolate persistence from domain |
| Specification | Composable business predicates | Eligibility rules, query filters |
| Singleton | One instance | Rarely justified — prefer DI-managed scope |

## Evaluating fit — checklist
1. Which driver (requirement ID) does this pattern serve? If none, reject it.
2. What does it cost in complexity, latency, ops, and team learning?
3. Does it conflict with another driver (e.g. event sourcing vs. "simple CRUD, 2-person team")?
4. Is there a simpler pattern that meets the target? Prefer it.
5. Can we prove the fit with a small benchmark or spike? Plan it in `02-solutioning.md §7`.
