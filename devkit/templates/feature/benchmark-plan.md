<!-- devkit:doc type=benchmark-plan v=1 -->
# Benchmark Plan — {{title}}

**Status:** Draft
**Feature:** `{{slug}}` · **Updated:** {{date}} · **Upstream:** `../01-requirements/requirements.md` (NFRs), `../02-design/solutioning.md`

## 1. Objectives
<!-- TODO: which NFRs are being verified and which decisions the numbers inform -->

## 2. SLO gates (from NFRs)
| NFR | Scenario | Metric | Gate (`--slo`) |
|-----|----------|--------|----------------|
<!-- TODO: | NFR-001 | create link | p95 | p95_ms<=150 | -->

## 3. Environment
<!-- TODO: machine, build flags, data volume, warm vs cold cache. Results are only comparable on the same environment. -->

## 4. Scenarios
| ID | Scenario | Kind (cmd/http) | Load (n / concurrency / duration) | Command |
|----|----------|-----------------|-----------------------------------|---------|
<!-- TODO -->

```bash
# Example
python3 devkit/tools/bench.py http --name create-link --url http://localhost:8080/links -X POST \
  -H 'Content-Type: application/json' --data '{"url":"https://example.com"}' \
  -n 500 -c 20 --warmup 20 --slo "p95_ms<=150" --slo "error_rate<=0.01" \
  --out {{ws}}/04-quality/benchmarks/create-link.json
```

## 5. Baseline & regression policy
<!-- TODO: which result file is the baseline; threshold for bench.py compare (default 10%) -->

## 6. Results
<!-- TODO: paste output of bench.py report, with interpretation -->
