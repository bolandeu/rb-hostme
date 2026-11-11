---
id: HOSTME-001
title: PRD.md sections go to living docs, ADRs and ideas
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
- PRD.md
- docs/adr
- docs/usage
- AGENTS.md
- README.md
test_paths: []
docs:
- PRD.md
- docs/adr/
- docs/usage/
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

PRD.md (268 lines) is the product specification kept as a file; the layout check refuses it. Read all of it and sort every section:
- Still true of the product and needed by a newcomer (goals, users, non-goals, target model, config and data paths, exit codes, security rules) -> a living doc: docs/usage/<topic>.md, or a file named in the [docs] living lines of .agents/antagor/antagor.toml (list the line in your report; the Architect adds it to antagor.toml).
- A decision with its reason (tech stack, storage layout, secret handling, accepted risks, command grammar) -> one ADR docs/adr/NNNN-slug.md each, following docs/adr/README.md.
- Something put off ("later", "after MVP", out of scope) or a gap found on the way -> one idea each: antagor idea add --title ... --text ...; list the new idea ids in your report.
Then delete PRD.md and fix every pointer to it (AGENTS.md, README.md, code docstrings).
The report is a table: each PRD section -> its destination (living doc path / ADR number / idea id / drop with reason).

## Read first

- `.agents/antagor/antagor.toml`

## Out of scope

- No code or CLI behaviour change.
- Do not edit .agents/antagor/antagor.toml: the [docs] living lines you need go in your report.
- Nothing is dropped without the Human's yes: leave a to-drop section in the report, do not delete it yet.
