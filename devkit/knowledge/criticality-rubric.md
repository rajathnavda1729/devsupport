# Criticality Rubric

Use this to decide whether a requirement is **CRITICAL**. A requirement is CRITICAL if it scores **3 on any one dimension** or **≥ 10 in total**. Otherwise rate it High (7–9), Medium (4–6) or Low (≤ 3).

| Dimension | 0 | 1 | 2 | 3 |
|-----------|---|---|---|---|
| **Safety / harm** | none | minor inconvenience | injury or harm possible in edge cases | harm to people likely if it fails |
| **Security & privacy** | no sensitive data | internal data | PII / credentials exposed to insiders | PII, secrets or money exposed externally |
| **Regulatory / legal** | none | internal policy | contractual SLA | law or regulation (GDPR, PCI-DSS, HIPAA, SOX…) |
| **Financial** | none | < 1 day of revenue at risk | material revenue at risk | direct money loss, double charge, incorrect ledger |
| **Data integrity / irreversibility** | recoverable instantly | recoverable with effort | partial loss / manual repair | permanent loss or corruption |
| **Availability of core journey** | cosmetic | degraded secondary feature | core journey degraded | core journey down for all users |
| **Blast radius** | single user | team / tenant | many tenants | every user / downstream system |

## How to record it
- Put `CRITICAL` in the *Criticality* column of the requirement row (tools detect the word).
- Add a row to *§6 Critical requirements* stating the dimension(s) that scored 3, the failure impact, and the design guard.
- Every CRITICAL requirement must end up with: a design guard in HLD §9, at least one task, and at least one test case (positive **and** negative / failure). `tracker.py validate` treats missing coverage as an error.

## Signals that a requirement is probably critical
"must never", "exactly once", "audit", "payment", "balance", "consent", "delete my data", "medical", "legal hold", "authentication", "authorisation", "encryption", "SLA", "real money", "irreversible", "regulator".
