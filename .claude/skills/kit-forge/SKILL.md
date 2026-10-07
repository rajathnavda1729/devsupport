---
name: kit-forge
description: Generate new Claude Code skills, sub-agents, rules and document types (templates) (for this devkit or the user's project) from templates — e.g. a project-specific "add-endpoint" skill, a "security-reviewer" agent, or a "no secrets in logs" rule — and register them. Use when the user asks to create/generate a skill, agent, sub-agent, rule, slash command or workflow automation, or to extend the devkit.
argument-hint: "skill|agent|rule <name> <purpose>"
---

# Kit forge — generate skills, agents and rules

**Templates:** `devkit/templates/meta/skill.md`, `agent.md`, `rule.md`, `doc-template.md`
**Locations:**
- skills: `.claude/skills/<name>/SKILL.md`
- agents: `.claude/agents/<name>.md`
- rules: `.claude/rules/<name>.md`

## Choose the right artefact
| Need | Create |
|------|--------|
| A repeatable *procedure* the main agent follows ("how we add an endpoint", "how we cut a release") | **Skill** |
| A *specialist* with its own context window, persona and restricted tools, to delegate to (reviewer, analyst) | **Agent** |
| A *constraint* that must always hold while editing certain files ("migrations are append-only") | **Rule** |
| Something deterministic: parse, validate, count | A **script** under `devkit/tools/`, called by a skill |
| A new kind of document a skill must produce (runbook, threat model, API spec…) | A **document type**: template + manifest entry |

## Steps
1. **Clarify** the trigger (when it should activate), the inputs, the outputs, and the success criteria. Look at 1–2 existing skills or agents in this repo and match their style.
2. **Name it** in kebab-case, verb-noun for skills (`add-endpoint`), role for agents (`security-reviewer`), and the constraint for rules (`migrations-append-only`). Check the name doesn't already exist.
3. **Fill in the template.**
   - **Skill:**
     - The `description` is the trigger. Make it specific about *what* the skill does and *when* to use it, including the phrases users say.
     - The body is an imperative procedure with numbered steps, the exact commands, an output contract, and a quality checklist.
     - Keep it under ~150 lines. Move bulky reference material into `devkit/knowledge/` and link to it.
   - **Agent:**
     - Give the role and the expertise.
     - Grant the least tools needed. Reviewers are read-only: `Read, Grep, Glob, Bash`.
     - Describe the operating procedure and the exact report format it returns. Its final message is all the caller sees.
   - **Rule:**
     - Use `paths:` frontmatter globs to scope it.
     - State the rule plainly with *why*, plus a short good/bad example.
     - Make it enforceable by review.
   - **Document type:**
     1. Copy `devkit/templates/meta/doc-template.md` to `devkit/templates/feature/<type>.md`.
     2. Set the marker to `<!-- devkit:doc type=<type> v=1 -->`.
     3. Keep the header fields (`**Status:**`, `**Feature:**`, `**Updated:**`, `**Upstream:**`).
     4. Use numbered H2 sections. Each one gets guidance in `<!-- TODO -->` comments, and a table header or mermaid block where the structure must be fixed. The linter enforces exactly what the template contains.
     5. Add an entry to `devkit/templates/manifest.json` under `documents`. It needs `type`, `title`, `path` (inside the right group: `01-requirements`, `02-design`, `03-delivery` or `04-quality`), `template`, `kind: authored`, and `pipeline` (true = created by `scaffold.py new`; false = on demand via `scaffold.py doc`). Add any new sub-folder to `dirs`.
     6. Check that the skeleton lints clean: `scaffold.py doc <slug> <type>`, then `doclint.py <file>` must report 0 errors.
     7. Reference the new document from the skill that fills it in.
4. **Wire it in.**
   - Add it to the tables in `README.md` and `CLAUDE.md`.
   - If the skill belongs to the pipeline, add it to the stage table in `.claude/skills/devkit/SKILL.md`.
   - If it needs a script, write one with stdlib only, `--help`, and a test in `tests/`.
5. **Test it.**
   - For a skill or agent, dry-run it on a realistic request. Check that the description triggers and that the output matches its contract.
   - For a script, run `python3 -m unittest discover -s tests`.
6. **Report** the files you created and an example invocation.
