# Testing & verification

- Every CRITICAL requirement needs ≥1 positive, ≥1 negative and ≥1 failure-injection test case in `04-quality/test-plan.md`. `tracker.py validate` must report no errors before a plan is called complete.
- Test case rows start with their `TC-###` ID and list the FR/NFR IDs they verify.
- Performance NFRs are verified by `bench.py` with `--slo` gates whose values come from the NFR target. Never claim an NFR is met without a result file.
- During local end-to-end testing, run `devkit/tools/logwatch.py`. A run with ERROR lines or critical alerts is not a passing run, even if the tests are green.
- Report outcomes faithfully. Failing or skipped tests are stated as such, with their output.
