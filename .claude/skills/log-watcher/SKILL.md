---
name: log-watcher
description: Set up and run a local log watcher for testing — discover the project's log sources (files, dev-server command, docker compose), generate a logwatch profile with alert rules derived from the LLD's log events and critical requirements, run it live while testing, and produce a post-run log report / CI gate. Use when the user asks to watch, tail, monitor or analyse logs locally, catch errors during testing, or build a log watcher.
argument-hint: "[feature-slug] [log path or command]"
---

# Log watcher

**Tool:** `devkit/tools/logwatch.py` (stdlib Python). Default alert rules: `devkit/config/logwatch.rules.json`. Example profile: `devkit/config/logwatch.example.json`.

## Capabilities
- Follows files and globs. It is rotation- and truncation-aware and picks up new files.
- Can also follow a command's output (`--cmd "npm run dev"`) or stdin (`docker compose logs -f | logwatch.py --stdin`).
- Detects levels in plain text and in JSON logs (pino, bunyan, structlog, logback JSON, zap). It colourises output and groups multi-line stack traces with their header.
- Filters: `--level WARN`, `--grep RE`, `--exclude RE`.
- Alert rules: a regex, a threshold within a time window, and a severity. Alerts print a banner, can ring the bell (`--bell`), and can be appended as JSONL (`--alerts-file`).
- Writes a summary on exit or Ctrl+C: counts per level and per source, the alerts, and the top error *signatures* (numbers, ids and timestamps normalised, so repeats group together). `--report file.md` saves it.
- CI or post-mortem mode: `--once --from-start --fail-on ERROR` exits 1 if errors or critical alerts occurred.

## Steps
1. **Discover the sources** in the project:
   - log file paths in the logging config, `logs/`, `*.log`, `tmp/`;
   - the dev-server command in package.json scripts, the Makefile or Procfile;
   - docker-compose services.

   Ask the user only if nothing is discoverable.
2. **Derive the rules.**
   - Start from the defaults: unhandled exceptions, OOM, connection refused, timeouts, 5xx bursts, deadlocks, auth failures, slow queries, port in use.
   - Add feature rules from `02-design/lld.md §11` (log events) and §8 (the error table). Each CRITICAL requirement's failure signal becomes a rule with severity `critical`. Example: a `duplicate_charge_detected` event → `threshold 1`.
   - Add `exclude` patterns for noise such as health checks and metrics scrapes.
3. **Write the profile** to `devkit/config/logwatch.local.json` (or `logwatch.<slug>.json` when it is feature-specific). Use the schema in `logwatch.example.json`: `sources`, `cmd`, `level`, `exclude`, `rules_file`, `rules`. Validate it with `python3 -m json.tool <file>`.
4. **Smoke-test the rules.** Feed in a sample line and confirm the alert fires:
   `printf 'ERROR duplicate_charge_detected order=1\n' | python3 devkit/tools/logwatch.py --stdin --config <profile>`
5. **Document usage** in `04-quality/testing-guide.md §6`: the live command, the post-run gate command, and which lines prove success for each flow.
6. **Running live for the user.** Start it in the background (`run_in_background`) with `--report`. When the user finishes testing, stop it and summarise the report: alerts, top signatures, and suggested causes or next steps. Create tracker bugs for the real defects.

## Quick reference
```bash
python3 devkit/tools/logwatch.py "logs/*.log"                                  # follow
python3 devkit/tools/logwatch.py --cmd "npm run dev" --level INFO --bell       # run + watch
python3 devkit/tools/logwatch.py --config devkit/config/logwatch.local.json    # profile
python3 devkit/tools/logwatch.py app.log --once --from-start --fail-on ERROR --report out.md   # gate
```
