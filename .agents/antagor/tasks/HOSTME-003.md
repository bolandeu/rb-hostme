---
id: HOSTME-003
title: Webinoly, wildcard SSL and surge references become records and living docs
status: queue
attempts: 0
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
