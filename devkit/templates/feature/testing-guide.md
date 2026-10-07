<!-- devkit:doc type=testing-guide v=1 -->
# Testing Guide — {{title}}

**Status:** Draft
**Feature:** `{{slug}}` · **Updated:** {{date}} · **Upstream:** `../02-design/lld.md`

How a developer tests this feature locally, end to end.

## 1. Prerequisites
<!-- TODO: runtimes and versions, tools, accounts, env vars (.env.example) -->

## 2. Local environment setup
```bash
# TODO: exact commands — install deps, start dependencies (docker compose up -d ...), migrate, seed
```

## 3. Test data
<!-- TODO: fixtures, seed scripts, how to reset state -->

## 4. Test pyramid for this feature
| Layer | Scope | Framework | Location | Command |
|-------|-------|-----------|----------|---------|
| Unit | | | | |
| Integration | | | | |
| Contract | | | | |
| End-to-end | | | | |
| Performance | benchmark scenarios | `devkit/tools/bench.py` | `{{ws}}/04-quality/benchmarks/` | see `benchmark-plan.md` |
<!-- TODO -->

## 5. Running the tests
```bash
# TODO: unit, integration, e2e, coverage
```

## 6. Watching logs while testing
```bash
python3 devkit/tools/logwatch.py --config devkit/config/logwatch.local.json
# post-run gate (CI-friendly):
python3 devkit/tools/logwatch.py <logfile> --once --from-start --fail-on ERROR --report {{ws}}/04-quality/benchmarks/log-report.md
```
<!-- TODO: which log lines indicate success for each key flow -->

## 7. Manual / exploratory checks
<!-- TODO: checklist of things not worth automating, with expected results -->

## 8. Debugging tips
<!-- TODO: common failures and fixes, how to attach a debugger, useful queries -->

## 9. CI
<!-- TODO: which suites run where, gates that block merge -->
