---
paths:
  - "**/01-requirements/requirements.md"
---

# Requirements quality

- Each FR is atomic, uses "The system shall …", names an actor, and has Given/When/Then acceptance criteria.
- Requirements describe **what**, never **how**. "Store links in Postgres" is a constraint, and only if it is mandated. Otherwise it belongs in solutioning.
- Each NFR has a metric, a target, a condition and a verification method. Banned without a number: fast, scalable, secure, robust, user-friendly, real-time, highly available.
- Anything not stated by the requester is labelled `inferred` or `assumption`, and every assumption has an open question.
- CRITICAL is justified against `devkit/knowledge/criticality-rubric.md` in §6.

**Bad:** `| FR-004 | The system should be fast and use Redis caching |`
**Good:** `| NFR-002 | Performance | Redirect latency | p95 | ≤ 50 ms at 1 000 rps, 10 M links | Must | High | benchmark redirect-hot |`
