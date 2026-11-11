---
id: HOSTME-003
title: Webinoly, wildcard SSL and surge references become records and living docs
status: in_review
attempts: 2
blocked: false
blocked_reason: null
phase: null
tests_hash: null
publish_stage: null
created_by: architect
approved_by: human
worker: pi
type: docs
owns_paths:
- docs
- WILDCARD-SSL.md
- AGENTS.md
- README.md
- scripts/provision-server.sh
- src/hostme/commands/domain.py
- src/hostme/commands/help.py
- src/hostme/commands/site.py
- src/hostme/core/services.py
- src/hostme/data/nginx-defaults.conf
- src/hostme/providers/webinoly.py
- tests/snapshots/describe.json
- tests/snapshots/help/domain-add.txt
test_paths: []
docs:
- docs/webinoly.md
- WILDCARD-SSL.md
- docs/surge-cli.md
- docs/usage/
- docs/adr/
- docs/research/
- AGENTS.md
- README.md
tools: []
worker_args: null
class: mechanical
decision: false
visual: null
review: true
depends_on: []
budget_usd: null
epic: E-001
spec_refs: []
checks: manual
resident: null
tool: null
pr: null
---

Three reference documents are kept as files; the layout check refuses them: docs/webinoly.md (526 lines, Webinoly behaviour verified on the servers), WILDCARD-SSL.md (112, a verified wildcard-SSL procedure and the history of what went wrong), docs/surge-cli.md (36, the surge.sh commands whose shape hostme copies). Read all three.
For each section pick one destination:
- Facts the code and the agents need all the time (Webinoly command shapes and output formats, the real deploy path, the wildcard procedure as it is run) -> a living doc: docs/usage/webinoly.md, docs/usage/wildcard-ssl.md; list any [docs] living line the Architect must add to .agents/antagor/antagor.toml in your report.
- What was found out on a date and how: the bugs (open_file_cache, rights on releases/, fail2ban on frequent ssh), the Beget DNS history, the surge.sh command reference -> a dated research record docs/research/YYYY-MM-DD-<slug>.md, the date taken from git log of the file's first commit.
- A decision taken because of a finding (ControlMaster reuse, six NS, the MVP SSL path) -> one ADR docs/adr/NNNN-slug.md each.
- Something put off (automation of SSL through the registrar API, Brotli) -> one idea each with antagor idea add; list the ids in your report. Check the idea list first: Brotli and file times are already there.
Then delete the three files and fix every pointer to them (AGENTS.md, README.md, code docstrings, skills under src/hostme/data/).
The report is a table: each section of each file -> its destination.

## Read first

- `.agents/antagor/antagor.toml`

## Out of scope

- No code or CLI behaviour change; no new Webinoly checks run against a server.
- Do not edit .agents/antagor/antagor.toml: the [docs] living lines go in your report.
- Nothing is dropped without the Human's yes: leave a to-drop section in the report.

## Feedback

### Attempt 1: the Architect's verdict

Your branch is based on main before v0.6.2 (HOSTME-001/002 landed there): PRD.md and TODO.md must stay deleted, and a plain merge has 4 conflicts. Bring main into your branch and resolve them this way:
1. `git merge main` in your worktree.
2. AGENTS.md — main's version is the rewrite from HOSTME-001/002 (no PRD.md, no TODO.md, docs under docs/usage/ and docs/adr/). Keep main's text; only re-apply your own pointer edits on top (docs/usage/webinoly.md, docs/usage/wildcard-ssl.md, docs/research/...).
3. WILDCARD-SSL.md and docs/webinoly.md — take your deletion (git rm). main's side only changed 6 lines each, pointers from HOSTME-002; the files are gone by design.
4. src/hostme/providers/webinoly.py — keep both: main's renamed pointers (docs/usage/webinoly.md) and your new module docstring.
5. Do not reintroduce PRD.md/TODO.md, keep ADR numbers 0007-0009.
Then `uv run pytest -q tests/unit` (219 passed before) and keep tests/snapshots/help/ in step with any docstring change.

### Attempt 2: the Architect's verdict

The review found blockers; close each:

- [blocker] `docs/usage/webinoly.md`: the closing code fences are written as ` ```text ` (lines 11, 35, 73). A CommonMark closing fence must not carry an info string, so ` ```text ` does not close the block opened at line 9 — it is literal content, and the rest of the file renders as one giant code block. Failing case: any CommonMark renderer (verified with commonmark.py on the exact file: exactly 1 `<pre><code>` block, its content swallows the prose after line 9). Fix: closing fences become bare ` ``` `.
- [blocker] `docs/research/2026-09-08-wildcard-ssl-dns.md:15`: same defect — the block opened at line 11 runs to end of file; the «Первый прогон упал на рассинхроне NS» prose after line 15 renders as code. Failing case: same renderer check.

Minor remarks of the review: optional, if they do not widen the task:

- [minor] wrong `src/hostme/providers/webinoly.py:332,392`: the docstrings point to «Кастомный Nginx-конфиг» in `docs/usage/webinoly.md`, but that section does not exist in the new living doc — it became «Свои nginx-сниппеты». The file path is fixed, the section name is stale — «Then delete the three files and fix every pointer to them (AGENTS.md, README.md, code docstrings, skills under src/hostme/data/).»
