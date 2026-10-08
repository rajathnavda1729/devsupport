import json
import unittest

from helpers import ToolTestCase

NYGARD = """# 1. Record architecture decisions

Date: 2021-03-01

## Status

Accepted

## Context

We need to record decisions.

## Decision

We will use Architecture Decision Records.

## Consequences

See Michael Nygard's article.
"""
NYGARD_SUPERSEDED = """# 2. Use MySQL

Date: 2021-04-01

## Status

Accepted

Superseded by [3. Use PostgreSQL](0003-use-postgresql.md)

## Context
Need a database.

## Decision
We will use MySQL.
"""
MADR3 = """---
status: accepted
date: 2022-01-10
tags: [data, storage]
---
# Use PostgreSQL as the system of record

## Context and Problem Statement
Orders need ACID transactions.

## Decision Outcome
Chosen option: "PostgreSQL", because it gives transactional guarantees for payments.
"""
MADR2 = """# Use Kafka for domain events

* Status: proposed
* Date: 2022-06-01

## Context and Problem Statement
Services need events.

## Decision Outcome
Chosen option: Kafka.
"""


class AdrTest(ToolTestCase):
    def setUp(self):
        super().setUp()
        (self.cwd / ".git").mkdir()
        self.adr_dir = self.cwd / "doc" / "architecture" / "decisions"
        self.adr_dir.mkdir(parents=True)
        (self.adr_dir / "0001-record-architecture-decisions.md").write_text(NYGARD)
        (self.adr_dir / "0002-use-mysql.md").write_text(NYGARD_SUPERSEDED)
        (self.adr_dir / "0003-use-postgresql.md").write_text(MADR3)
        (self.adr_dir / "0004-use-kafka.md").write_text(MADR2)
        (self.adr_dir / "README.md").write_text("# Decisions\nIndex of ADRs\n")
        noise = self.cwd / "node_modules" / "pkg" / "adr"
        noise.mkdir(parents=True)
        (noise / "0001-vendored.md").write_text(NYGARD)

    def adr(self, *args, check=True):
        return self.run_tool("adr.py", *args, check=check)

    def registry(self):
        return json.loads(self.adr("scan", "--json").stdout)

    def test_scan_detects_formats_and_statuses(self):
        adrs = {a["number"]: a for a in self.registry()}
        self.assertEqual(sorted(adrs), [1, 2, 3, 4])                     # README and node_modules ignored
        self.assertEqual(adrs[1]["format"], "nygard")
        self.assertEqual(adrs[1]["status"], "Accepted")
        self.assertEqual(adrs[2]["status"], "Superseded")
        self.assertEqual(adrs[2]["superseded_by"], 3)
        self.assertEqual(adrs[3]["format"], "madr")
        self.assertEqual(adrs[3]["status"], "Accepted")
        self.assertEqual(adrs[3]["date"], "2022-01-10")
        self.assertIn("data", adrs[3]["tags"])
        self.assertIn("PostgreSQL", adrs[3]["summary"])
        self.assertEqual(adrs[4]["status"], "Proposed")
        self.assertEqual(adrs[1]["title"], "Record architecture decisions")

    def test_scan_writes_decision_log_in_existing_dir(self):
        self.adr("scan")
        cfg = json.loads((self.cwd / ".devkit.json").read_text())
        self.assertEqual(cfg["decisions_dir"], "doc/architecture/decisions")
        log = (self.adr_dir / "decision-log.md").read_text()
        self.assertIn("generated", log.splitlines()[0])
        self.assertIn("Superseded → ADR-0003", log)
        self.assertIn("[ADR-0003](0003-use-postgresql.md)", log)

    def test_search_ranks_and_hides_superseded(self):
        out = self.adr("search", "database", "mysql", "postgresql").stdout
        self.assertIn("ADR-0003", out)
        self.assertNotIn("ADR-0002", out)
        self.assertIn("ADR-0002", self.adr("search", "mysql", "--all").stdout)

    def test_new_follows_repo_naming_and_numbering(self):
        path = self.adr("new", "--title", "Adopt OpenTelemetry", "--tags", "observability").stdout.splitlines()[0]
        self.assertTrue(path.endswith("doc/architecture/decisions/0005-adopt-opentelemetry.md"), path)
        text = open(path).read()
        self.assertIn("# ADR-0005: Adopt OpenTelemetry", text)
        self.assertIn("**Status:** Proposed", text)

    def test_long_titles_cut_at_word_boundary(self):
        path = self.adr("new", "--title", "Exactly-once scoring via applied-events ledger in the same PostgreSQL transaction").stdout.splitlines()[0]
        self.assertTrue(path.endswith("0005-exactly-once-scoring-via-applied-events-ledger-in-the-same.md"), path)

    def test_retroactive_is_accepted(self):
        path = self.adr("new", "--title", "Monorepo with pnpm", "--retroactive").stdout.splitlines()[0]
        text = open(path).read()
        self.assertIn("**Status:** Accepted", text)
        self.assertIn("Retroactive ADR", text)

    def test_supersede_updates_foreign_formats(self):
        self.adr("new", "--title", "Use NATS instead of Kafka", "--supersedes", "4")
        madr2 = (self.adr_dir / "0004-use-kafka.md").read_text()
        self.assertIn("* Status: superseded by adr-0005", madr2)
        adrs = {a["number"]: a for a in self.registry()}
        self.assertEqual(adrs[4]["status"], "Superseded")
        self.assertIn("**Supersedes:** ADR-0004", open(self.cwd / adrs[5]["path"]).read())
        self.adr("supersede", "1", "5")
        self.assertIn("Superseded by ADR-0005", (self.adr_dir / "0001-record-architecture-decisions.md").read_text())

    def test_retitle_only_while_proposed(self):
        self.adr("new", "--title", "First idea")
        path = self.adr("retitle", "5", "--title", "Better idea").stdout.strip()
        self.assertTrue(path.endswith("0005-better-idea.md"), path)
        self.assertIn("# ADR-0005: Better idea", open(path).read())
        self.assertFalse((self.adr_dir / "0005-first-idea.md").exists())
        self.adr("set-status", "5", "accepted")
        self.assertNotEqual(self.adr("retitle", "5", "--title", "x", check=False).returncode, 0)

    def test_set_status_on_devkit_adr(self):
        self.adr("new", "--title", "X")
        self.adr("set-status", "ADR-0005", "accepted")
        adrs = {a["number"]: a for a in self.registry()}
        self.assertEqual(adrs[5]["status"], "Accepted")

    def test_feature_adrs_are_scoped_and_numbered_globally(self):
        self.run_tool("scaffold.py", "new", "pay", "--text", "x")
        path = self.adr("new", "--feature", "pay", "--title", "Use outbox").stdout.splitlines()[0]
        self.assertIn("specs/pay/02-design/decisions/", path)
        self.assertTrue(path.endswith("/0005-use-outbox.md"), path)  # global numbering, repo naming style
        adrs = {a["number"]: a for a in self.registry()}
        self.assertEqual(adrs[5]["scope"], "feature:pay")

    def test_check_flags_missing_context_and_bad_citations(self):
        self.run_tool("scaffold.py", "new", "pay", "--text", "x")
        sol = self.cwd / "specs/pay/02-design/solutioning.md"
        p = self.adr("check", "pay", check=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn("§1 is empty", p.stdout)
        text = sol.read_text().replace(
            "<!-- TODO: | ADR-0003",
            "| ADR-0002 | Use MySQL | Superseded | constrains | old |\n| ADR-0099 | ghost | ? | ? | ? |\n<!-- TODO: | ADR-0003")
        sol.write_text(text)
        p = self.adr("check", "pay", check=False)
        self.assertIn("cites ADR-0099, which does not exist", p.stdout)
        self.assertIn("cites superseded ADR-0002 — use ADR-0003", p.stdout)


    def test_decisions_applied_must_be_in_force(self):
        self.run_tool("scaffold.py", "new", "pay", "--text", "x")
        self.adr("new", "--feature", "pay", "--title", "Use Redis")          # ADR-0005
        self.adr("new", "--feature", "pay", "--title", "Use PostgreSQL only")  # ADR-0006
        self.adr("set-status", "5", "rejected")
        sol = self.cwd / "specs/pay/02-design/solutioning.md"
        sol.write_text(sol.read_text().replace(
            "## 10. New decisions (ADRs written for this feature)\n",
            "## 10. New decisions (ADRs written for this feature)\nADR-0005 rejected, ADR-0006 chosen.\n"))
        hld = self.cwd / "specs/pay/02-design/hld.md"
        hld.write_text(hld.read_text().replace(
            "|-----|----------|-----------------------------------|\n",
            "|-----|----------|-----------------------------------|\n| ADR-0005 | Redis | read path |\n", 1))
        out = self.adr("check", "pay", check=False).stdout
        self.assertIn("applies rejected ADR-0005", out)
        self.assertIn("does not apply ADR-0006", out)


class AdrEmptyRepoTest(ToolTestCase):
    def test_no_adrs_defaults_to_docs_adr(self):
        (self.cwd / ".git").mkdir()
        out = self.run_tool("adr.py", "scan").stdout
        self.assertIn("found 0 ADR(s)", out)
        self.assertIn("No architecture decision records", (self.cwd / "docs/adr/decision-log.md").read_text())
        path = self.run_tool("adr.py", "new", "--title", "First").stdout.splitlines()[0]
        self.assertTrue(path.endswith("docs/adr/ADR-0001-first.md"))
        self.run_tool("doclint.py", path)


if __name__ == "__main__":
    unittest.main()
