---
name: benchmark
description: Design and run benchmark tests for a solution — derive SLO gates from NFRs, write the benchmark plan, run command or HTTP load benchmarks with devkit/tools/bench.py, compare against a baseline to detect regressions, and compare candidate solutions side by side. Use when the user asks to benchmark, load test, performance test, measure latency/throughput, check SLOs, or compare implementations.
argument-hint: "<feature-slug> [scenario]"
---

# Benchmark

> **Workspace:** `<ws>` is this feature's folder in the target repo. Get it with `python3 devkit/tools/scaffold.py where <slug>`. Its documents are grouped: `01-requirements/`, `02-design/` (`decisions/`, `reviews/`), `03-delivery/`, `04-quality/`. Write only there.
>
> **Format contract:** fill in the document that `scaffold.py` created from its template. Never write a document from scratch. Keep these:
> - the `<!-- devkit:doc … -->` marker line;
> - the H1 prefix;
> - the header fields;
> - every H2 section, in its order;
> - the table columns;
> - the mermaid blocks the template has.
>
> Put extra detail under `###`. Write "None" or "N/A — reason" for an empty section. A missing document comes from `scaffold.py doc <slug> <type>`. The lint hook checks every write. Before you finish, run `python3 devkit/tools/doclint.py --feature <slug>`.

**Input:** the NFRs in `01-requirements/requirements.md`, the PoC experiments in `02-design/solutioning.md §7`, and a runnable system or command.
**Output:** `<ws>/04-quality/benchmark-plan.md`, result JSON files in `<ws>/04-quality/benchmarks/`, and `benchmarks/REPORT.md`.

## Tool reference (`devkit/tools/bench.py`)
```bash
# Shell command (CLI tools, scripts, functions wrapped in a one-liner)
python3 devkit/tools/bench.py cmd --name <scenario> -n 30 --warmup 3 [-c 4] [--duration 60] \
  --slo "p95_ms<=200" --out <ws>/04-quality/benchmarks/<scenario>.json "<command>"
# HTTP endpoint
python3 devkit/tools/bench.py http --name <scenario> --url http://localhost:8080/x -X POST \
  -H 'Content-Type: application/json' --data '{...}' -n 500 -c 20 --warmup 20 \
  --slo "p95_ms<=150" --slo "error_rate<=0.01" --slo "throughput_rps>=200" --out <ws>/04-quality/benchmarks/<scenario>.json
# Regression check (exit 1 on regression)
python3 devkit/tools/bench.py compare <ws>/04-quality/benchmarks/baseline-<scenario>.json <ws>/04-quality/benchmarks/<scenario>.json --threshold 10
# Side-by-side report (also used to compare solution options)
python3 devkit/tools/bench.py report <ws>/04-quality/benchmarks/*.json --out <ws>/04-quality/benchmarks/REPORT.md
```
- Metrics available in `--slo`: `p50_ms p90_ms p95_ms p99_ms mean_ms max_ms min_ms stdev_ms error_rate throughput_rps`.
- The command exits 1 when any SLO fails, so it can be used as a CI gate.
- For heavy load (more than a few thousand rps), recommend k6, wrk or vegeta, and keep `bench.py` for local and CI gates.

## Steps
1. **Map NFRs to scenarios.** Every performance, throughput or reliability NFR gets a scenario with a gate. The gate value comes from the NFR target, and so does the load condition (concurrency, data size).
2. **Write the plan** in `04-quality/benchmark-plan.md`: objectives, gates, environment, scenarios with exact commands, and the baseline policy.
3. **Prepare the environment.**
   - Use a release build.
   - Seed a realistic data volume.
   - Close noisy apps.
   - Record the machine; the tool records the env automatically.
   - Run the log watcher in parallel to catch errors under load:
     `python3 devkit/tools/logwatch.py --config devkit/config/logwatch.local.json --quiet --report <ws>/04-quality/benchmarks/log-report.md`
4. **Run.**
   - Use warmup. Repeat noisy scenarios 3× and take the median run.
   - Never report a single tiny sample. Use n ≥ 30 for commands and ≥ 200 requests for HTTP.
5. **Baseline.** The first accepted run is copied to `baseline-<scenario>.json`. After every change, run `compare`.
6. **Report.**
   - Generate `REPORT.md` and fill in §6 of the plan with your interpretation: pass/fail per NFR, bottleneck hypotheses, next actions.
   - Add failing SLOs as P0/P1 tracker tasks: `tracker.py add --type bug --reqs NFR-xxx ...`.
7. **Comparing solution options.** Run identical scenarios per option with names `optA-<scenario>`, `optB-<scenario>`, on the same machine, with the same data and the same load, then `report` them together.

## Integrity rules
- Never fabricate or "estimate" a measured number. If a benchmark could not run, write "not run" and the reason.
- Results from different machines are not comparable. The report warns about this.
